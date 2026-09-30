"""Tests for the MCP server in dsh_coderag.server (M3 / M4 / M9)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import anyio
import pytest
from inline_snapshot import snapshot
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag.server import build_server


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path) -> AsyncGenerator[ClientSession, None]:
    server = build_server(root=tmp_path)
    async with create_connected_server_and_client_session(
        server, raise_exceptions=True
    ) as session:
        yield session


async def _wait_for_ready(client: ClientSession, task_id: str) -> dict[str, Any]:
    for _ in range(200):
        text = (await client.call_tool("index_status", {"task_id": task_id})).content[0].text
        payload: dict[str, Any] = json.loads(text)
        if payload["state"] in {"ready", "failed", "cancelled"}:
            return payload
        await anyio.sleep(0.02)
    raise AssertionError("indexing did not finish in time")


@pytest.mark.anyio
async def test_tools_list_exposes_exactly_four_tools(client: ClientSession) -> None:
    tools = await client.list_tools()
    assert [tool.name for tool in tools.tools] == snapshot(
        ["code_search", "code_outline", "code_index", "index_status"]
    )


@pytest.mark.anyio
async def test_tool_schemas_match_the_contract(client: ClientSession) -> None:
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert tools["code_search"].inputSchema["required"] == ["query"]
    assert list(tools["code_search"].inputSchema["properties"]) == [
        "query",
        "path",
        "limit",
        "max_tokens",
    ]
    assert tools["code_outline"].inputSchema["required"] == ["path"]
    assert list(tools["code_outline"].inputSchema["properties"]) == ["path", "max_depth"]
    assert list(tools["code_index"].inputSchema["properties"]) == ["path", "force"]
    assert "required" not in tools["code_index"].inputSchema
    assert list(tools["index_status"].inputSchema["properties"]) == ["task_id"]


@pytest.mark.snapshot
@pytest.mark.anyio
async def test_tool_descriptions_are_stable(client: ClientSession) -> None:
    """M9: tool descriptions are a model-visible contract."""
    tools = await client.list_tools()
    assert [tool.description for tool in tools.tools] == snapshot(
        [
            "Find code in this workspace by describing what you are looking for, in"
            " natural language or as an identifier. Use this first for any question"
            " about where something lives, how a behaviour is implemented, or which"
            " files are involved — including when you already know the exact"
            " identifier, because a single call returns exact file paths and line"
            " ranges. Use a literal text search only when you must match an exact"
            " string or regex, and read the returned files to confirm. When nothing"
            " is searchable yet, the result says so instead of reporting no matches.",
            "Return the symbol outline (classes, functions, methods) of one file, with"
            " line numbers. Use this to understand a file's structure before reading"
            " it in full.",
            "Start (or refresh) the code index for a workspace directory. Returns"
            " immediately with a task id; indexing continues in the background. Poll"
            " index_status for progress.",
            "Report the state and progress of an indexing task, or of the workspace"
            " index when no task id is given.",
        ]
    )


@pytest.mark.anyio
async def test_code_outline_returns_a_structured_status(client: ClientSession) -> None:
    result = await client.call_tool("code_outline", {"path": "a.py"})
    text = result.content[0].text
    assert text.startswith("status: empty")
    assert "no such file" in text


@pytest.mark.anyio
async def test_no_stdout_pollution_during_tool_call(
    capsys: pytest.CaptureFixture[str], client: ClientSession
) -> None:
    await client.call_tool("code_outline", {"path": "a.py"})
    assert capsys.readouterr().out == ""


@pytest.mark.anyio
async def test_code_index_returns_immediately_and_becomes_ready(
    client: ClientSession, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )
    started = time.monotonic()
    payload = json.loads((await client.call_tool("code_index", {})).content[0].text)
    elapsed = time.monotonic() - started
    assert elapsed < 0.2, f"code_index blocked for {elapsed:.3f}s"
    assert payload["state"] == "pending"
    final = await _wait_for_ready(client, payload["taskId"])
    assert final["state"] == "ready"
    assert final["total_files"] == 1
    assert final["total_chunks"] == 1


@pytest.mark.anyio
async def test_code_search_finds_indexed_code(
    client: ClientSession, tmp_path: Path
) -> None:
    (tmp_path / "token.py").write_text(
        "def verify_token() -> bool:\n    return True\n", encoding="utf-8"
    )
    payload = json.loads((await client.call_tool("code_index", {})).content[0].text)
    await _wait_for_ready(client, payload["taskId"])
    text = (await client.call_tool("code_search", {"query": "verify_token"})).content[0].text
    assert text.startswith("status: ready")
    assert "token.py" in text


# ── the CODERAG_* tuning variables must reach the path the MCP server uses ──
# The engine's own unit tests hand an IndexConfig straight to `index_sync` /
# `search`, which is exactly the wiring the server used to skip: it called the
# indexer bare and hardcoded the search budget. These three go through the
# tools instead, so a regression in that wiring fails here.
#
# Each test drops CODERAG_ROOT so the server has to satisfy the config from the
# `build_server(root=...)` argument it was built with.


@pytest.mark.anyio
async def test_code_index_honours_max_files_instead_of_indexing_past_it(
    client: ClientSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RL-08: over the limit the task fails and reports the real count."""
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
    monkeypatch.delenv("CODERAG_ROOT", raising=False)
    monkeypatch.setenv("CODERAG_MAX_FILES", "1")

    payload = json.loads((await client.call_tool("code_index", {})).content[0].text)
    final = await _wait_for_ready(client, payload["taskId"])

    assert final["state"] == "failed"
    assert final["message"] == snapshot(
        "TooManyFilesError: workspace has 2 indexable files, over max_files=1"
    )


@pytest.mark.anyio
async def test_code_index_honours_max_file_bytes(
    client: ClientSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file over the byte limit is skipped and counted, not indexed."""
    (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("y = '" + "A" * 40 + "'\n", encoding="utf-8")
    monkeypatch.delenv("CODERAG_ROOT", raising=False)
    monkeypatch.setenv("CODERAG_MAX_FILE_BYTES", "20")

    payload = json.loads((await client.call_tool("code_index", {})).content[0].text)
    final = await _wait_for_ready(client, payload["taskId"])
    status = json.loads((await client.call_tool("index_status", {})).content[0].text)

    assert final["state"] == "ready"
    assert final["total_files"] == 1
    assert status["skipped"] == snapshot({"count": 1, "reasons": {"too_large": 1}})


@pytest.mark.anyio
async def test_index_status_reports_what_the_walk_saw(
    client: ClientSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An index over nothing must say so, or the model reads it as "no results"."""
    (tmp_path / "ship.MXML").write_text("<mx:Canvas/>", encoding="utf-8")
    monkeypatch.delenv("CODERAG_ROOT", raising=False)

    payload = json.loads((await client.call_tool("code_index", {})).content[0].text)
    await _wait_for_ready(client, payload["taskId"])
    status = json.loads((await client.call_tool("index_status", {})).content[0].text)

    assert status["files"] == snapshot({"indexable": 0, "seen": 1, "other_extensions": 1})
    assert status["skipped"] == snapshot({"count": 0, "reasons": {}})


@pytest.mark.anyio
async def test_index_status_counts_files_the_user_whitelisted(
    client: ClientSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server's walk must use the effective whitelist too (T6-17)."""
    (tmp_path / "screen.MXML").write_text("<mx:Canvas/>", encoding="utf-8")
    monkeypatch.delenv("CODERAG_ROOT", raising=False)
    monkeypatch.setenv("CODERAG_EXTRA_EXTENSIONS", ".mxml")

    payload = json.loads((await client.call_tool("code_index", {})).content[0].text)
    final = await _wait_for_ready(client, payload["taskId"])
    status = json.loads((await client.call_tool("index_status", {})).content[0].text)

    assert final["total_files"] == 1
    assert status["files"] == snapshot({"indexable": 1, "seen": 1, "other_extensions": 0})


@pytest.mark.anyio
async def test_code_search_honours_max_tokens_as_its_default_budget(
    client: ClientSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a `max_tokens` argument the budget comes from the environment."""
    for index in range(2):
        (tmp_path / f"mod{index}.py").write_text(
            f"def alpha{index}():\n    return 'zzzterm {index}'\n", encoding="utf-8"
        )
    monkeypatch.delenv("CODERAG_ROOT", raising=False)
    monkeypatch.setenv("CODERAG_MAX_TOKENS", "1")
    payload = json.loads((await client.call_tool("code_index", {})).content[0].text)
    await _wait_for_ready(client, payload["taskId"])

    text = (await client.call_tool("code_search", {"query": "zzzterm", "limit": 5})).content[0].text

    assert text.startswith("status: ready")
    assert "hits: 2" not in text, "the budget must have dropped one hit"
    omitted = [line for line in text.splitlines() if "omitted by token budget" in line]
    assert omitted == snapshot(
        ["[1 more hit omitted by token budget; raise max_tokens to see it]"]
    )
