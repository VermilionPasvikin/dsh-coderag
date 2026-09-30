"""Tests for synchronous indexing in dsh_coderag.indexer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.indexer import SCHEMA_VERSION, index_sync, open_index


def test_index_sync_refuses_a_root_that_does_not_exist(tmp_path: Path) -> None:
    """Indexing under a mistyped path used to create it and report zero files."""
    missing = tmp_path / "typo" / "not" / "here"

    with pytest.raises(FileNotFoundError):
        index_sync(missing)

    assert not missing.exists()


def _query(repo: Path, sql: str) -> list[tuple[object, ...]]:
    connection = open_index(repo / ".coderag" / "index.sqlite3")
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def test_index_sync_writes_every_tiny_file(tiny_repo: Path) -> None:
    summary = index_sync(tiny_repo)
    assert summary.files == 3
    assert summary.chunks == 3
    assert (tiny_repo / ".coderag" / "index.sqlite3").exists()


def test_files_use_relative_posix_paths(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    paths = {row[0] for row in _query(tiny_repo, "SELECT path FROM files")}
    assert paths == {"app.ts", "lib.c", "main.py"}


def test_full_text_table_has_one_row_per_chunk(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    assert _query(tiny_repo, "SELECT count(*) FROM chunks_fts") == [(3,)]


def test_chunk_line_ranges_match_the_source(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    rows = _query(
        tiny_repo,
        "SELECT f.path, c.start_line, c.end_line"
        " FROM chunks c JOIN files f ON f.id = c.file_id"
        " ORDER BY f.path, c.seq",
    )
    assert rows == [("app.ts", 1, 3), ("lib.c", 1, 3), ("main.py", 1, 2)]


def test_reindex_does_not_duplicate_rows(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    index_sync(tiny_repo)
    assert _query(tiny_repo, "SELECT count(*) FROM files") == [(3,)]
    assert _query(tiny_repo, "SELECT count(*) FROM chunks") == [(3,)]
    assert _query(tiny_repo, "SELECT count(*) FROM chunks_fts") == [(3,)]


def test_workspace_index_is_marked_ready(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    assert _query(tiny_repo, "SELECT ready, db_schema FROM workspace_index") == [
        (1, SCHEMA_VERSION)
    ]


def test_interrupted_index_stops_claiming_the_workspace_is_ready(
    tiny_repo: Path,
) -> None:
    """T6-23: a Ctrl+C after an earlier completed run used to leave ready = 1.

    Measured on a real workspace: 80,437 of 103,002 files indexed at the moment of
    the interrupt, while the state row still said ready - so a fifth of the
    workspace looked searchable-complete.
    """
    index_sync(tiny_repo)
    assert _query(tiny_repo, "SELECT ready FROM workspace_index") == [(1,)]

    calls = {"count": 0}

    def interrupt_on_second_check() -> bool:
        calls["count"] += 1
        if calls["count"] > 1:
            raise KeyboardInterrupt
        return False

    with pytest.raises(KeyboardInterrupt):
        index_sync(tiny_repo, should_cancel=interrupt_on_second_check)

    assert _query(tiny_repo, "SELECT ready FROM workspace_index") == [(0,)]


def test_a_cancelled_run_also_does_not_claim_readiness(tiny_repo: Path) -> None:
    """Cancellation is a normal outcome: no ready flag, and no cleanup either."""
    index_sync(tiny_repo)

    index_sync(tiny_repo, should_cancel=lambda: True)

    assert _query(tiny_repo, "SELECT ready FROM workspace_index") == [(0,)]
