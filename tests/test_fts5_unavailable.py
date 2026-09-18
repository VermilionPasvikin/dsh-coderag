"""Tests for FTS5 capability handling and dispatch safety (TESTING 4.2, T2-22)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag import sqlite_caps
from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search
from dsh_coderag.server import build_server
from dsh_coderag.types import ErrorCode, SearchStatus


def test_fts5_unavailable_probe_returns_true_on_this_machine() -> None:
    assert sqlite_caps.fts5_available() is True


def test_fts5_unavailable_search_returns_a_structured_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlite_caps, "fts5_available", lambda: False)
    result = search(tmp_path, "anything")
    assert result.status is SearchStatus.ERROR
    assert result.code is ErrorCode.FTS5_UNAVAILABLE
    assert result.hits == []
    assert result.hint == sqlite_caps.FTS5_HINT


def test_fts5_unavailable_index_refuses_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_caps, "fts5_available", lambda: False)
    with pytest.raises(sqlite_caps.Fts5UnavailableError):
        index_sync(tmp_path)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_fts5_unavailable_code_search_is_not_an_mcp_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlite_caps, "fts5_available", lambda: False)
    server = build_server(root=tmp_path)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("code_search", {"query": "x"})
    assert result.isError is not True
    text = result.content[0].text
    assert text.startswith("status: error")
    assert "FTS5_UNAVAILABLE" in text


@pytest.mark.anyio
async def test_fts5_unavailable_code_index_is_not_an_mcp_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlite_caps, "fts5_available", lambda: False)
    server = build_server(root=tmp_path)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("code_index", {})
    assert result.isError is not True
    text = result.content[0].text
    assert "FTS5_UNAVAILABLE" in text


@pytest.mark.anyio
async def test_fts5_unavailable_dispatch_catches_unexpected_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("dsh_coderag.server.search", boom)
    server = build_server(root=tmp_path)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("code_search", {"query": "x"})
    assert result.isError is not True
    text = result.content[0].text
    assert text.startswith("status: error")
    assert "SEARCH_FAILED" in text
