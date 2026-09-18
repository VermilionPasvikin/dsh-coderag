"""Tests for token-budget trimming (PROJECT.md 5.4, T2-15)."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.indexer import index_sync
from dsh_coderag.render import render_search_result
from dsh_coderag.searcher import search


def _make_repo(tmp_path: Path, count: int = 5) -> None:
    for index in range(count):
        (tmp_path / f"f{index}.py").write_text(
            f'def f{index}():\n    return "zzzterm" + "." * 100\n', encoding="utf-8"
        )
    index_sync(tmp_path)


def test_token_budget_trims_and_reports_omitted(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = search(tmp_path, "zzzterm", k=10, max_tokens=20)
    assert len(result.hits) == 1
    assert result.omitted == 4


def test_token_budget_keeps_everything_when_it_fits(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = search(tmp_path, "zzzterm", k=10, max_tokens=100000)
    assert len(result.hits) == 5
    assert result.omitted == 0


def test_token_budget_renders_an_omitted_note(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    out = render_search_result(search(tmp_path, "zzzterm", k=10, max_tokens=20))
    assert "[4 more hits omitted by token budget; raise max_tokens to see them]" in out


def test_token_budget_uses_the_singular_note() -> None:
    from dsh_coderag.types import SearchResult, SearchStatus

    result = SearchResult(status=SearchStatus.READY, query="x", omitted=1)
    out = render_search_result(result)
    assert "[1 more hit omitted by token budget; raise max_tokens to see it]" in out


def test_token_budget_keeps_at_least_one_hit(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = search(tmp_path, "zzzterm", k=10, max_tokens=1)
    assert len(result.hits) == 1
    assert result.omitted == 4
