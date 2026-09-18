"""Tests for the code_search path filter (T2-20)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search
from dsh_coderag.server import build_server
from dsh_coderag.types import ErrorCode, SearchStatus


def _repo(tmp_path: Path) -> Path:
    for directory in ("pkg", "other", "my_pkg", "myXpkg"):
        (tmp_path / directory).mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        "def alpha():\n    return 'zzzterm'\n", encoding="utf-8"
    )
    (tmp_path / "other" / "b.py").write_text(
        "def beta():\n    return 'zzzterm'\n", encoding="utf-8"
    )
    (tmp_path / "my_pkg" / "c.py").write_text(
        "def gamma():\n    return 'zzzterm'\n", encoding="utf-8"
    )
    (tmp_path / "myXpkg" / "d.py").write_text(
        "def delta():\n    return 'zzzterm'\n", encoding="utf-8"
    )
    index_sync(tmp_path)
    return tmp_path


def test_path_filter_returns_only_hits_under_the_subdirectory(tmp_path: Path) -> None:
    hits = search(_repo(tmp_path), "zzzterm", k=10, path="pkg").hits
    assert [hit.path for hit in hits] == ["pkg/a.py"]


def test_path_filter_is_optional(tmp_path: Path) -> None:
    paths = {hit.path for hit in search(_repo(tmp_path), "zzzterm", k=10).hits}
    assert {"pkg/a.py", "other/b.py", "my_pkg/c.py", "myXpkg/d.py"} <= paths


def test_path_filter_accepts_a_single_file(tmp_path: Path) -> None:
    hits = search(_repo(tmp_path), "zzzterm", k=10, path="other/b.py").hits
    assert [hit.path for hit in hits] == ["other/b.py"]


def test_path_filter_escapes_like_wildcards(tmp_path: Path) -> None:
    paths = {hit.path for hit in search(_repo(tmp_path), "zzzterm", k=10, path="my_pkg").hits}
    assert paths == {"my_pkg/c.py"}


def test_path_filter_rejects_an_escaping_path(tmp_path: Path) -> None:
    result = search(_repo(tmp_path), "zzzterm", k=10, path="../outside")
    assert result.status is SearchStatus.ERROR
    assert result.code is ErrorCode.SEARCH_INVALID_QUERY
    assert result.hits == []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_path_filter_via_the_tool(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    server = build_server(root=repo)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("code_search", {"query": "zzzterm", "path": "pkg"})
    text = result.content[0].text
    assert "pkg/a.py" in text
    assert "other/b.py" not in text
