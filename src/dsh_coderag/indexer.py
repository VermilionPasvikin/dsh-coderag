"""SQLite schema, connection setup and synchronous indexing for dsh_coderag.

This module owns the index database layout, the connection pragmas and the
first synchronous writer that walks a workspace, chunks each file and stores
files, chunks and the full-text index. Incremental hash-based skipping,
safety filtering and asynchronous task management live in later tasks.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from dsh_coderag.chunker import chunk_text
from dsh_coderag.sanitize import scan_secret
from dsh_coderag.text import to_bigrams
from dsh_coderag.walker import walk

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS index_runs (
  task_id       TEXT PRIMARY KEY,
  root          TEXT    NOT NULL,
  state         TEXT    NOT NULL,
  total_files   INTEGER NOT NULL DEFAULT 0,
  done_files    INTEGER NOT NULL DEFAULT 0,
  total_chunks  INTEGER NOT NULL DEFAULT 0,
  done_chunks   INTEGER NOT NULL DEFAULT 0,
  message       TEXT,
  started_at    INTEGER NOT NULL,
  finished_at   INTEGER
);

CREATE TABLE IF NOT EXISTS files (
  id            INTEGER PRIMARY KEY,
  path          TEXT    NOT NULL UNIQUE,
  size          INTEGER NOT NULL,
  mtime_ns      INTEGER NOT NULL,
  content_hash  TEXT    NOT NULL,
  lang          TEXT,
  indexed_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id            INTEGER PRIMARY KEY,
  file_id       INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  start_line    INTEGER NOT NULL,
  end_line      INTEGER NOT NULL,
  symbol_kind   TEXT,
  symbol_name   TEXT,
  text          TEXT    NOT NULL,
  content_hash  TEXT    NOT NULL,
  UNIQUE (file_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_chunks_order ON chunks (file_id, seq);
CREATE INDEX IF NOT EXISTS idx_chunks_symbol ON chunks (symbol_name);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5 (
  text_bigram,
  symbol,
  path,
  chunk_id UNINDEXED,
  file_id  UNINDEXED,
  tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS workspace_index (
  root          TEXT PRIMARY KEY,
  db_schema     INTEGER NOT NULL,
  ready         INTEGER NOT NULL DEFAULT 0,
  last_task_id  TEXT,
  updated_at    INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class IndexSummary:
    """Counts produced by one synchronous indexing run."""

    root: Path
    files: int
    chunks: int


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the index database with the pragmas this project relies on."""
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    """Create every index table and index that does not already exist."""
    connection.executescript(SCHEMA_SQL)


def open_index(db_path: Path) -> sqlite3.Connection:
    """Open the index database and make sure its schema exists."""
    connection = connect(db_path)
    init_schema(connection)
    return connection


def index_sync(root: Path) -> IndexSummary:
    """Index a workspace synchronously and return the resulting counts.

    Re-running replaces each file's rows, so the index never accumulates
    duplicates. Hash-based skipping of unchanged files is added in T2-08.
    """
    base = root.resolve()
    db_path = base / ".coderag" / "index.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = open_index(db_path)
    try:
        entries = walk(base)
        total_chunks = 0
        current_paths: set[str] = set()
        for absolute, size, mtime_ns in entries:
            current_paths.add(absolute.relative_to(base).as_posix())
            total_chunks += _index_file(connection, base, absolute, size, mtime_ns)
        _remove_missing_files(connection, current_paths)
        _mark_ready(connection, base)
        return IndexSummary(root=base, files=len(entries), chunks=total_chunks)
    finally:
        connection.close()


def _index_file(
    connection: sqlite3.Connection,
    base: Path,
    absolute: Path,
    size: int,
    mtime_ns: int,
) -> int:
    """Replace one file's rows; return the number of chunks written."""
    relative = absolute.relative_to(base).as_posix()
    raw = absolute.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    existing = connection.execute(
        "SELECT id, content_hash FROM files WHERE path = ?", (relative,)
    ).fetchone()
    if existing is not None and existing[1] == digest:
        return 0
    existing_id = existing[0] if existing is not None else None
    text = raw.decode("utf-8", errors="replace")
    chunks = chunk_text(text, relative)
    # Layer 3: drop chunks whose text matches a secret pattern. A file whose
    # chunks are all redacted is not recorded at all.
    surviving = [chunk for chunk in chunks if scan_secret(chunk.text) is None]
    if chunks and not surviving:
        if existing_id is not None:
            with connection:
                _delete_file_rows(connection, existing_id)
        return 0
    chunks = surviving
    with connection:
        if existing_id is not None:
            _delete_file_rows(connection, existing_id)
        cursor = connection.execute(
            "INSERT INTO files (path, size, mtime_ns, content_hash, lang, indexed_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (relative, size, mtime_ns, digest, None, int(time.time())),
        )
        assert cursor.lastrowid is not None
        file_id = cursor.lastrowid
        for chunk in chunks:
            chunk_digest = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            chunk_cursor = connection.execute(
                "INSERT INTO chunks"
                " (file_id, seq, start_line, end_line, symbol_kind, symbol_name,"
                "  text, content_hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    chunk.seq,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.symbol_kind,
                    chunk.symbol_name,
                    chunk.text,
                    chunk_digest,
                ),
            )
            assert chunk_cursor.lastrowid is not None
            connection.execute(
                "INSERT INTO chunks_fts (text_bigram, symbol, path, chunk_id, file_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    to_bigrams(chunk.text),
                    chunk.symbol_name or "",
                    relative,
                    chunk_cursor.lastrowid,
                    file_id,
                ),
            )
    return len(chunks)


def _remove_missing_files(
    connection: sqlite3.Connection, current_paths: set[str]
) -> None:
    """Cascade-delete rows for files that no longer exist in the workspace."""
    stale = [
        file_id
        for file_id, path in connection.execute("SELECT id, path FROM files").fetchall()
        if path not in current_paths
    ]
    if not stale:
        return
    with connection:
        for deleted_id in stale:
            _delete_file_rows(connection, deleted_id)


def _delete_file_rows(connection: sqlite3.Connection, file_id: int) -> None:
    """Delete one file's chunks (including FTS rows) and the file row."""
    connection.execute("DELETE FROM chunks_fts WHERE file_id = ?", (file_id,))
    connection.execute("DELETE FROM files WHERE id = ?", (file_id,))


def _mark_ready(connection: sqlite3.Connection, base: Path) -> None:
    """Record that the workspace index is complete and usable."""
    with connection:
        connection.execute(
            "INSERT INTO workspace_index (root, db_schema, ready, last_task_id, updated_at)"
            " VALUES (?, ?, 1, NULL, ?)"
            " ON CONFLICT(root) DO UPDATE SET"
            " db_schema = excluded.db_schema,"
            " ready = excluded.ready,"
            " last_task_id = excluded.last_task_id,"
            " updated_at = excluded.updated_at",
            (str(base), SCHEMA_VERSION, int(time.time())),
        )
