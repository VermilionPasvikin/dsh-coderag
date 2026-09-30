"""Tests for the code_search path filter (T2-20) and the stored path form (C-07)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path, PureWindowsPath

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search
from dsh_coderag.server import build_server
from dsh_coderag.types import ErrorCode, SearchStatus

WINDOWS_STYLE_SUBDIR = PureWindowsPath("pkg", "sub")
"""Renders as `pkg\\sub` on every host, which is the separator form Windows users type."""


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


def _nested_repo(tmp_path: Path) -> Path:
    """A workspace with one nested file, so a stored path crosses a separator."""
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "sub" / "util.py").write_text(
        "def zzzterm():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "top.py").write_text("def zzzterm():\n    return 2\n", encoding="utf-8")
    index_sync(tmp_path)
    return tmp_path


def test_stored_paths_are_forward_slashed_and_workspace_relative(tmp_path: Path) -> None:
    """C-07: what reaches the database is POSIX-style and relative, on every OS.

    Windows hands the walker `...\\pkg\\sub\\util.py`. Storing that form would
    make the database contents differ per platform, break the prefix match the
    `path` filter relies on, and hand the model an absolute host path.
    """
    repo = _nested_repo(tmp_path)
    connection = sqlite3.connect(repo / ".coderag" / "index.sqlite3")
    try:
        stored = sorted(row[0] for row in connection.execute("SELECT path FROM files"))
    finally:
        connection.close()

    assert stored == ["pkg/sub/util.py", "top.py"]
    for value in stored:
        assert "\\" not in value, value
        assert not PureWindowsPath(value).is_absolute(), value
        assert ":" not in value, value


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="backslash separators only resolve as path separators on Windows",
)
@pytest.mark.parametrize(
    "argument",
    ["pkg/sub", str(WINDOWS_STYLE_SUBDIR), ".\\pkg\\sub"],
)
def test_path_filter_accepts_windows_style_separators(tmp_path: Path, argument: str) -> None:
    """A Windows user's `pkg\\sub` must select the same files as `pkg/sub`."""
    hits = search(_nested_repo(tmp_path), "zzzterm", k=10, path=argument).hits

    assert [hit.path for hit in hits] == ["pkg/sub/util.py"]



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
