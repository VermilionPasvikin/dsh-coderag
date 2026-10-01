"""Tests for synchronous indexing in dsh_coderag.indexer."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from dsh_coderag import indexer
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


def test_the_vector_build_forwards_the_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6-27: this wrapper is the index build's only route to HTTP.

    It used to call the transport without the configured key, so a cloud build went
    out unauthenticated while `embed_texts` — which the unit tests call directly —
    sent the header correctly. Only the end-to-end run against a stub endpoint
    could see the difference.
    """
    from dsh_coderag import indexer

    seen: dict[str, object] = {}

    def fake_transport(
        url: str,
        model: str,
        texts: Sequence[str],
        timeout: float,
        *,
        api_key: str | None = None,
    ) -> list[list[float]]:
        seen["api_key"] = api_key
        return [[1.0] for _ in texts]

    monkeypatch.setattr(indexer, "_http_transport", fake_transport)
    transport = indexer._cancellable_transport(lambda: False, "k-123")

    assert transport("http://127.0.0.1:1/v1/embeddings", "m", ["a"], 1.0) == [[1.0]]
    assert seen["api_key"] == "k-123"


def test_pruning_many_stale_files_is_set_based(tmp_path: Path) -> None:
    """T6-30: one statement per table, not one per stale file.

    Deleting file rows one at a time made every `chunks_fts` delete a full scan of
    that table, because `file_id` is an UNINDEXED FTS column: removing 478,263 of
    894,964 chunks that way ran for over twenty minutes, read 288 GB and had
    written 1.9 MB when it was stopped. This asserts the shape of the fix - a
    constant number of statements however many files go - and that the FTS rows
    stay in step with `chunks`.
    """
    stale_count = 20_000
    db_path = tmp_path / "index.sqlite3"
    connection = open_index(db_path)
    statements: list[str] = []
    try:
        now = int(time.time())
        connection.executemany(
            "INSERT INTO files (id, path, size, mtime_ns, content_hash, lang, indexed_at)"
            " VALUES (?, ?, 1, 1, 'h', NULL, ?)",
            ((n, f"gone/f{n}.py", now) for n in range(1, stale_count + 1)),
        )
        connection.execute(
            "INSERT INTO files (id, path, size, mtime_ns, content_hash, lang, indexed_at)"
            " VALUES (?, ?, 1, 1, 'h', NULL, ?)",
            (stale_count + 1, "kept/one.py", now),
        )
        connection.executemany(
            "INSERT INTO chunks (id, file_id, seq, start_line, end_line, text, content_hash)"
            " VALUES (?, ?, 1, 1, 1, ?, 'h')",
            ((n, n, f"body {n}") for n in range(1, stale_count + 2)),
        )
        connection.executemany(
            "INSERT INTO chunks_fts (text_bigram, symbol, path, chunk_id, file_id)"
            " VALUES (?, '', '', ?, ?)",
            ((f"body {n}", n, n) for n in range(1, stale_count + 2)),
        )
        connection.set_trace_callback(statements.append)
        started = time.monotonic()
        removed = indexer._remove_missing_files(connection, {"kept/one.py"})
        elapsed = time.monotonic() - started
        connection.set_trace_callback(None)
    finally:
        connection.close()

    assert removed == stale_count
    assert elapsed < 20, f"pruning {stale_count} files took {elapsed:.1f}s"
    # Exactly one statement touches chunks_fts, however many files go: that table
    # has no index on file_id, so a per-file delete meant a full scan per file.
    # `DELETE FROM files` is traced once per cascaded row instead, which is simply
    # what SQLite's ON DELETE CASCADE does and is cheap through idx_chunks_order.
    fts_deletes = [s for s in statements if s.startswith("DELETE FROM chunks_fts")]
    assert len(fts_deletes) == 1, f"{len(fts_deletes)} of {len(statements)} statements"

    reopened = open_index(db_path)
    try:
        counts = (
            reopened.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            reopened.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            reopened.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0],
        )
    finally:
        reopened.close()
    assert counts == (1, 1, 1)
