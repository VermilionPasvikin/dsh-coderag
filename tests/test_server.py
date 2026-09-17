"""Tests for the MCP server in dsh_coderag.server (M4 / M9)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path

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


@pytest.mark.anyio
async def test_code_outline_returns_a_structured_status(client: ClientSession) -> None:
    result = await client.call_tool("code_outline", {"path": "a.py"})
    text = result.content[0].text
    assert '"status"' in text
    assert "not implemented" in text


@pytest.mark.anyio
async def test_no_stdout_pollution_during_tool_call(
    capsys: pytest.CaptureFixture[str], client: ClientSession
) -> None:
    await client.call_tool("code_outline", {"path": "a.py"})
    assert capsys.readouterr().out == ""


@pytest.mark.anyio
async def test_code_index_reports_ready_with_counts(
    client: ClientSession, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )
    result = await client.call_tool("code_index", {})
    payload = json.loads(result.content[0].text)
    assert payload["state"] == "ready"
    assert payload["files"] == 1
    assert payload["chunks"] == 1


@pytest.mark.anyio
async def test_code_search_finds_indexed_code(
    client: ClientSession, tmp_path: Path
) -> None:
    (tmp_path / "token.py").write_text(
        "def verify_token() -> bool:\n    return True\n", encoding="utf-8"
    )
    await client.call_tool("code_index", {})
    text = (await client.call_tool("code_search", {"query": "verify_token"})).content[0].text
    assert text.startswith("status: ready")
    assert "token.py" in text
