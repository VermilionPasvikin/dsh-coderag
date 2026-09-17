"""M3 / M10: code_search always returns a structured status, never a bare list."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag.server import build_server


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[ClientSession]:
    server = build_server(root=tmp_path)
    async with create_connected_server_and_client_session(server) as session:
        yield session


def _text(result: Any) -> str:
    return result.content[0].text


def _status_of(text: str) -> str:
    return text.splitlines()[0].split(":", 1)[1].strip()


async def _index_and_wait(client: ClientSession) -> None:
    payload = json.loads(_text(await client.call_tool("code_index", {})))
    for _ in range(200):
        state = json.loads(
            _text(await client.call_tool("index_status", {"task_id": payload["taskId"]}))
        )
        if state["state"] in {"ready", "failed"}:
            return
        await anyio.sleep(0.02)
    raise AssertionError("indexing did not finish")


@pytest.mark.anyio
async def test_search_without_index_returns_a_structured_status(
    client: ClientSession,
) -> None:
    """RL-06: an absent index must not look like an empty result array."""
    text = _text(await client.call_tool("code_search", {"query": "anything"}))
    assert text.strip() != "[]"
    assert text.startswith("status:")
    assert _status_of(text) in {"indexing", "empty", "error"}


@pytest.mark.anyio
async def test_search_with_no_matches_is_empty_not_a_bare_array(
    client: ClientSession, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text(
        "def present() -> None:\n    return None\n", encoding="utf-8"
    )
    await _index_and_wait(client)
    text = _text(await client.call_tool("code_search", {"query": "zzzabsentzzz"}))
    assert text.strip() != "[]"
    assert text.startswith("status: empty")


@pytest.mark.anyio
async def test_missing_workspace_config_returns_a_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M10 / RL-09: an internal failure must not surface as a transport error."""
    monkeypatch.delenv("CODERAG_ROOT", raising=False)
    server = build_server()
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("code_search", {"query": "x"})
    assert result.isError is not True
    assert _status_of(_text(result)) == "error"
