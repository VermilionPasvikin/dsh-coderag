"""Tests for source-order output (ADR-05, T2-14)."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search


def test_order_preserving_sorts_hits_by_source_not_score(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 'zzzterm'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(
        "def beta():\n    return 'zzzterm zzzterm zzzterm zzzterm'\n", encoding="utf-8"
    )
    index_sync(tmp_path)
    hits = search(tmp_path, "zzzterm", k=10).hits
    assert [hit.path for hit in hits] == ["a.py", "b.py"]
    # b.py matches more often, so its bm25 score is better (lower); without the
    # source-order pass it would have been returned first.
    assert hits[0].score > hits[1].score


def test_order_preserving_keeps_chunks_in_line_order(tmp_path: Path) -> None:
    (tmp_path / "multi.py").write_text(
        "def first():\n    return 'zzzterm'\n"
        "\n"
        "\n"
        "def second():\n    return 'zzzterm'\n",
        encoding="utf-8",
    )
    index_sync(tmp_path)
    lines = [
        hit.start_line for hit in search(tmp_path, "zzzterm", k=10).hits if hit.path == "multi.py"
    ]
    assert len(lines) >= 2
    assert lines == sorted(lines)


def test_order_preserving_is_stable_across_files_and_lines(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 'zzzterm'\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(
        "def b1():\n    return 'zzzterm'\n"
        "\n"
        "\n"
        "def b2():\n    return 'zzzterm'\n",
        encoding="utf-8",
    )
    index_sync(tmp_path)
    keys = [(hit.path, hit.start_line) for hit in search(tmp_path, "zzzterm", k=10).hits]
    assert keys == sorted(keys)
