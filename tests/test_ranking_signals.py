"""Structured re-ranking signals (T3-14, PROJECT.md 3.3 step 3).

Selection happens over a widened candidate pool: test paths are demoted and an
exact `symbol_name` match is boosted, before the best k are chosen. Output order
is still source order (ADR-05), so these tests separate selection from ordering.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import query_symbols, search, selection_key
from dsh_coderag.types import Hit


def make_hit(
    path: str, *, score: float = 0.0, symbol_name: str | None = None
) -> Hit:
    return Hit(
        path=path,
        seq=0,
        start_line=1,
        end_line=1,
        text="x",
        score=score,
        symbol_name=symbol_name,
    )


@pytest.fixture
def ranking_corpus(tmp_path: Path) -> Path:
    """One implementation file and one test file that repeats the token 30x."""
    root = tmp_path / "ranking"
    (root / "src" / "tests").mkdir(parents=True)
    (root / "src" / "impl.py").write_text("# needle\n", encoding="utf-8")
    (root / "src" / "tests" / "impl_spec.py").write_text(
        "# needle\n" * 30, encoding="utf-8"
    )
    index_sync(root)
    return root


# ── selection_key (pure) ────────────────────────────────────────────────
def test_non_test_paths_are_never_demoted_below_test_paths() -> None:
    test = make_hit("src/tests/x.py", score=-100.0)
    impl = make_hit("src/x.py", score=-1.0)
    assert selection_key(impl, frozenset()) < selection_key(test, frozenset())


@pytest.mark.parametrize(
    "path",
    ["src/tests/x.py", "tests/x.py", "src/__tests__/x.py", "src/x.spec.ts", "a.test.py"],
)
def test_test_paths_are_recognised(path: str) -> None:
    assert selection_key(make_hit(path), frozenset())[0] is True


@pytest.mark.parametrize(
    "path",
    ["src/tests_helper.py", "src/latest.py", "src/contest.py", "src/spec.py"],
)
def test_lookalike_paths_are_not_treated_as_tests(path: str) -> None:
    assert selection_key(make_hit(path), frozenset())[0] is False


def test_exact_symbol_match_lowers_the_score() -> None:
    matched = make_hit("src/a.py", score=-5.0, symbol_name="retry_call")
    unmatched = make_hit("src/b.py", score=-5.0, symbol_name="other")
    key = selection_key(matched, frozenset({"retry_call"}))
    assert key < selection_key(unmatched, frozenset({"retry_call"}))
    assert key[1] < -5.0


def test_symbol_boost_does_not_apply_to_a_partial_match() -> None:
    partial = make_hit("src/a.py", score=-5.0, symbol_name="retry_call_extra")
    assert selection_key(partial, frozenset({"retry_call"}))[1] == -5.0


def test_query_symbols_extracts_ascii_identifiers() -> None:
    symbols = query_symbols("CONTEXT_WINDOW_EXCEEDED_CODE定义在哪？")
    assert "CONTEXT_WINDOW_EXCEEDED_CODE" in symbols
    assert query_symbols("中文查询") == frozenset()


# ── end-to-end selection ────────────────────────────────────────────────
def test_test_file_does_not_crowd_out_the_implementation(ranking_corpus: Path) -> None:
    """The spec has 30 occurrences and impl has 1: bm25 alone picks the spec."""
    connection = sqlite3.connect(ranking_corpus / ".coderag" / "index.sqlite3")
    try:
        row = connection.execute(
            "SELECT f.path FROM chunks_fts "
            "JOIN chunks c ON c.id = chunks_fts.chunk_id "
            "JOIN files f ON f.id = c.file_id "
            "WHERE chunks_fts MATCH '\"needle\"' "
            "ORDER BY bm25(chunks_fts), c.id LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    assert row[0] == "src/tests/impl_spec.py"  # the raw bm25 winner is the test
    result = search(ranking_corpus, "needle", k=1)
    assert [hit.path for hit in result.hits] == ["src/impl.py"]


def test_result_order_is_still_source_order(ranking_corpus: Path) -> None:
    result = search(ranking_corpus, "needle", k=5)
    positions = [(hit.path, hit.start_line) for hit in result.hits]
    assert positions == sorted(positions)


def test_selection_is_deterministic(ranking_corpus: Path) -> None:
    first = [hit.path for hit in search(ranking_corpus, "needle", k=5).hits]
    second = [hit.path for hit in search(ranking_corpus, "needle", k=5).hits]
    assert first == second


def test_demotion_can_promote_a_candidate_from_beyond_k(ranking_corpus: Path) -> None:
    """With k=1 the demoted test would leave room only via the wider pool."""
    result = search(ranking_corpus, "needle", k=1)
    assert result.hits[0].path == "src/impl.py"
    assert len(result.hits) == 1
