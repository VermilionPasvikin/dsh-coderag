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
            "Search the workspace codebase for relevant code. Returns ranked code"
            " snippets with exact file paths and line numbers. Prefer this over grep"
            " when you do not know the exact identifier, or when searching for"
            " behaviour across multiple files. When the index is not ready the result"
            " reports a structured status instead of an empty list.",
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
