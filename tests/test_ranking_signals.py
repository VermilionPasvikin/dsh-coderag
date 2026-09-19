"""Structured re-ranking signals (T3-14, PROJECT.md 3.3 step 3).

Selection ordering lives in SQL so `LIMIT k` sees the final ranking: non-test
paths first, then bm25 adjusted by an exact `symbol_name` match, then the chunk
id. Output order is still source order (ADR-05), so selection is asserted on the
*set* of returned paths rather than their order.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dsh_coderag.indexer import connect, index_sync
from dsh_coderag.searcher import SYMBOL_MATCH_BOOST, _search, query_symbols, search

TIER_FILES = {
    "src/plain.py": "# tierneedle\n",
    "src/tests_helper.py": "# tierneedle\n",  # lookalike, must not be demoted
    "src/tests/spec.py": "# tierneedle\n",
    "src/__tests__/spec2.py": "# tierneedle\n",
    "src/x.spec.py": "# tierneedle\n",
    "src/y.test.py": "# tierneedle\n",
}
SYMBOL_FILES = {
    "src/defs.py": "def target_symbol():\n    return 1\n",
    "src/uses.py": "# target_symbol\n" * 50,
}


def make_corpus(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def ranking_corpus(tmp_path: Path) -> Path:
    """One implementation file and one test file that repeats the token 30x."""
    root = make_corpus(
        tmp_path / "ranking",
        {"src/impl.py": "# needle\n", "src/tests/impl_spec.py": "# needle\n" * 30},
    )
    index_sync(root)
    return root


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


@pytest.mark.parametrize("k", [1, 2])
def test_only_non_test_paths_are_selected_first(tmp_path: Path, k: int) -> None:
    root = make_corpus(tmp_path / "tiers", TIER_FILES)
    index_sync(root)
    selected = {hit.path for hit in search(root, "tierneedle", k=k).hits}
    assert selected <= {"src/plain.py", "src/tests_helper.py"}
    if k == 2:
        assert selected == {"src/plain.py", "src/tests_helper.py"}


def test_every_test_path_shape_is_demoted(tmp_path: Path) -> None:
    root = make_corpus(tmp_path / "all-tiers", TIER_FILES)
    index_sync(root)
    selected = {hit.path for hit in search(root, "tierneedle", k=6).hits}
    assert selected == set(TIER_FILES)  # all present at k=6 ...
    first_two = {hit.path for hit in search(root, "tierneedle", k=2).hits}
    assert first_two == {"src/plain.py", "src/tests_helper.py"}  # ... tests last


def test_result_order_is_still_source_order(ranking_corpus: Path) -> None:
    result = search(ranking_corpus, "needle", k=5)
    positions = [(hit.path, hit.start_line) for hit in result.hits]
    assert positions == sorted(positions)


def test_selection_is_deterministic(ranking_corpus: Path) -> None:
    first = [hit.path for hit in search(ranking_corpus, "needle", k=5).hits]
    second = [hit.path for hit in search(ranking_corpus, "needle", k=5).hits]
    assert first == second


def test_exact_symbol_match_can_be_promoted(tmp_path: Path) -> None:
    """With a decisive boost, the declaring chunk outranks a heavier mention."""
    root = make_corpus(tmp_path / "symbols", SYMBOL_FILES)
    index_sync(root)
    connection = connect(root / ".coderag" / "index.sqlite3")
    try:
        plain = _search(connection, '"target_symbol"', 2, None, frozenset(), 0.0)
        boosted = _search(
            connection, '"target_symbol"', 2, None, frozenset({"target_symbol"}), 100.0
        )
    finally:
        connection.close()
    assert plain[0].path == "src/uses.py"  # bm25 favours the heavier mention
    assert boosted[0].path == "src/defs.py"  # the symbol match is boosted in SQL


def test_partial_symbol_names_are_not_boosted(tmp_path: Path) -> None:
    root = make_corpus(tmp_path / "partial", SYMBOL_FILES)
    index_sync(root)
    connection = connect(root / ".coderag" / "index.sqlite3")
    try:
        hits = _search(connection, '"target_symbol"', 2, None, frozenset({"target"}), 100.0)
    finally:
        connection.close()
    assert hits[0].path == "src/uses.py"


def test_query_symbols_extracts_ascii_identifiers() -> None:
    symbols = query_symbols("CONTEXT_WINDOW_EXCEEDED_CODE定义在哪？")
    assert "CONTEXT_WINDOW_EXCEEDED_CODE" in symbols
    assert query_symbols("中文查询") == frozenset()


def test_symbol_boost_default_is_positive() -> None:
    assert SYMBOL_MATCH_BOOST > 0
