"""Tests for FTS5 search in dsh_coderag.searcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search
from dsh_coderag.types import SearchStatus


def _write(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")


@pytest.fixture
def indexed_tiny(tiny_repo: Path) -> Path:
    index_sync(tiny_repo)
    return tiny_repo


@pytest.fixture
def ranking_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "ranking"
    repo.mkdir()
    _write(repo, "rare.py", "def uniqueterm() -> None:\n    return None\n")
    _write(repo, "common.py", "def commonterm() -> None:\n    return None\n")
    _write(repo, "other.py", "def commonterm() -> None:\n    return None\n")
    index_sync(repo)
    return repo


def test_search_returns_matching_file_and_lines(indexed_tiny: Path) -> None:
    result = search(indexed_tiny, "add", k=5)
    assert result.status is SearchStatus.READY
    assert {hit.path for hit in result.hits} == {"app.ts", "lib.c", "main.py"}
    assert all(hit.start_line <= hit.end_line for hit in result.hits)
    assert (result.scanned_files, result.scanned_chunks) == (3, 3)


def test_search_puts_the_matching_file_first(ranking_repo: Path) -> None:
    result = search(ranking_repo, "uniqueterm", k=5)
    assert [hit.path for hit in result.hits] == ["rare.py"]


def test_search_respects_the_result_limit(ranking_repo: Path) -> None:
    assert len(search(ranking_repo, "commonterm", k=1).hits) == 1


def test_search_without_matches_is_empty(ranking_repo: Path) -> None:
    result = search(ranking_repo, "zzzabsentzzz", k=5)
    assert result.status is SearchStatus.EMPTY
    assert result.hits == []


def test_search_without_an_index_reports_indexing(tmp_path: Path) -> None:
    result = search(tmp_path / "not-indexed", "anything")
    assert result.status is SearchStatus.INDEXING
    assert result.hits == []
    assert result.code is not None


def test_search_finds_two_character_cjk_terms(tmp_path: Path) -> None:
    repo = tmp_path / "cjk"
    repo.mkdir()
    _write(
        repo,
        "token.py",
        "def verify_token(raw: str) -> str:\n    # 校验用户令牌\n    return raw\n",
    )
    index_sync(repo)
    result = search(repo, "令牌", k=5)
    assert [hit.path for hit in result.hits] == ["token.py"]
