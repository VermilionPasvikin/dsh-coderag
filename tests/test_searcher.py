"""Tests for FTS5 search in dsh_coderag.searcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search


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
    hits = search(indexed_tiny, "add", k=5)
    assert hits
    assert {hit.path for hit in hits} == {"app.ts", "lib.c", "main.py"}
    assert all(hit.start_line <= hit.end_line for hit in hits)


def test_search_puts_the_matching_file_first(ranking_repo: Path) -> None:
    hits = search(ranking_repo, "uniqueterm", k=5)
    assert [hit.path for hit in hits] == ["rare.py"]


def test_search_respects_the_result_limit(ranking_repo: Path) -> None:
    assert len(search(ranking_repo, "commonterm", k=1)) == 1


def test_search_returns_no_hits_for_an_absent_term(ranking_repo: Path) -> None:
    assert search(ranking_repo, "zzzabsentzzz", k=5) == []


def test_search_raises_when_the_index_is_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        search(tmp_path / "not-indexed", "anything")


def test_search_finds_two_character_cjk_terms(tmp_path: Path) -> None:
    repo = tmp_path / "cjk"
    repo.mkdir()
    _write(
        repo,
        "token.py",
        "def verify_token(raw: str) -> str:\n    # 校验用户令牌\n    return raw\n",
    )
    index_sync(repo)
    hits = search(repo, "令牌", k=5)
    assert [hit.path for hit in hits] == ["token.py"]
