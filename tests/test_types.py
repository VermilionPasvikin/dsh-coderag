"""Tests for dsh_coderag.types."""

from __future__ import annotations

from dsh_coderag.types import Chunk, ErrorCode, Hit, IndexRun, SearchStatus


def test_error_code_matches_the_documented_contract() -> None:
    assert [code.name for code in ErrorCode] == [
        "INDEX_NOT_FOUND",
        "FTS5_UNAVAILABLE",
        "INDEX_RUNNING",
        "INDEX_TOO_MANY_FILES",
        "INDEX_READ_FAILED",
        "INDEX_WRITE_FAILED",
        "SEARCH_INVALID_QUERY",
        "SEARCH_FAILED",
        "TASK_NOT_FOUND",
        "CANCELLED",
    ]


def test_search_status_matches_the_documented_contract() -> None:
    assert [status.value for status in SearchStatus] == [
        "ready",
        "indexing",
        "empty",
        "stale",
        "error",
    ]


def test_chunk_has_no_symbol_by_default() -> None:
    chunk = Chunk(path="a/b.py", seq=0, start_line=1, end_line=2, text="x = 1\n")
    assert chunk.symbol_kind is None
    assert chunk.symbol_name is None
    assert chunk.low_confidence is False


def test_hit_carries_its_score_and_location() -> None:
    hit = Hit(path="a/b.py", seq=3, start_line=10, end_line=12, text="x", score=1.5)
    assert (hit.path, hit.start_line, hit.end_line, hit.seq) == ("a/b.py", 10, 12, 3)
    assert hit.score == 1.5


def test_index_run_defaults_for_a_new_task() -> None:
    run = IndexRun(task_id="idx-1", root="/repo", state="pending")
    assert run.done_files == 0
    assert run.done_chunks == 0
    assert run.finished_at is None
