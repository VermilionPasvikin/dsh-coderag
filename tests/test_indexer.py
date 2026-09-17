"""Tests for synchronous indexing in dsh_coderag.indexer."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.indexer import SCHEMA_VERSION, index_sync, open_index


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
