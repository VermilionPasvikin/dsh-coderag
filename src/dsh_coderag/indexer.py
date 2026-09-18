"""SQLite schema, connection setup and synchronous indexing for dsh_coderag.

This module owns the index database layout, the connection pragmas and the
indexing writer that walks a workspace, prepares each file off the database
thread (read, hash, chunk, secret scan), then writes the prepared files in
adaptive batches. Concurrency and batch size come from IndexConfig when set
and are otherwise derived from the machine (PROJECT.md 5.2, C8 / RL-07).
Incremental hash-based skipping and add/modify/delete transactions live here;
asynchronous task management lives in taskman.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from dsh_coderag.chunker import chunk_text
from dsh_coderag.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_FILES,
    IndexConfig,
    adaptive_workers,
    next_batch_size,
)
from dsh_coderag.sanitize import scan_secret
from dsh_coderag.text import to_bigrams
from dsh_coderag.types import Chunk
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


@dataclass(frozen=True)
class _PreparedFile:
    """One file prepared off the database thread, ready to be written."""

    relative: str
    size: int
    mtime_ns: int
    digest: str
    chunks: tuple[Chunk, ...]
    redacted: bool


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


def index_sync(root: Path, config: IndexConfig | None = None) -> IndexSummary:
    """Index a workspace synchronously and return the resulting counts.

    config tunes batching and concurrency; the workspace root always comes
    from the root argument. Re-running replaces only the files whose content
    hash changed, adds new files and cascade-deletes removed ones.
    """
    base = root.resolve()
    db_path = base / ".coderag" / "index.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = open_index(db_path)
    workers = config.workers if config is not None else adaptive_workers()
    batch_size = config.start_batch_size if config is not None else DEFAULT_BATCH_SIZE
    try:
        max_files = config.max_files if config is not None else DEFAULT_MAX_FILES
        entries = walk(base, max_files=max_files)
        current_paths = {
            absolute.relative_to(base).as_posix() for absolute, _, _ in entries
        }
        known = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT path, content_hash FROM files"
            ).fetchall()
        }
        prepared = _prepare_files(entries, base, known, workers)
        total_chunks = 0
        position = 0
        while position < len(prepared):
            end = min(position + batch_size, len(prepared))
            started = time.monotonic()
            with connection:
                for item in prepared[position:end]:
                    total_chunks += _write_prepared(connection, item)
            elapsed = time.monotonic() - started
            batch_size = next_batch_size(batch_size, elapsed)
            position = end
        _remove_missing_files(connection, current_paths)
        _mark_ready(connection, base)
        return IndexSummary(root=base, files=len(entries), chunks=total_chunks)
    finally:
        connection.close()


def _prepare_files(
    entries: list[tuple[Path, int, int]],
    base: Path,
    known: dict[str, str],
    workers: int,
) -> list[_PreparedFile]:
    """Prepare every changed file, in parallel when there is more than one."""
    prepared: list[_PreparedFile] = []
    if workers <= 1 or len(entries) <= 1:
        for absolute, size, mtime_ns in entries:
            item = _prepare_file(absolute, base, size, mtime_ns, known)
            if item is not None:
                prepared.append(item)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_prepare_file, absolute, base, size, mtime_ns, known)
                for absolute, size, mtime_ns in entries
            ]
            for future in as_completed(futures):
                item = future.result()
                if item is not None:
                    prepared.append(item)
    prepared.sort(key=lambda item: item.relative)
    return prepared


def _prepare_file(
    absolute: Path,
    base: Path,
    size: int,
    mtime_ns: int,
    known: dict[str, str],
) -> _PreparedFile | None:
    """Read, hash, chunk and secret-scan one file, or None when unchanged."""
    relative = absolute.relative_to(base).as_posix()
    raw = absolute.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if known.get(relative) == digest:
        return None
    text = raw.decode("utf-8", errors="replace")
    chunks = chunk_text(text, relative)
    # Layer 3: drop chunks whose text matches a secret pattern. A file whose
    # chunks are all redacted is not recorded at all.
    surviving = tuple(chunk for chunk in chunks if scan_secret(chunk.text) is None)
    return _PreparedFile(
        relative=relative,
        size=size,
        mtime_ns=mtime_ns,
        digest=digest,
        chunks=surviving,
        redacted=bool(chunks) and not surviving,
    )


def _write_prepared(connection: sqlite3.Connection, prepared: _PreparedFile) -> int:
    """Replace one prepared file's rows; return the chunks written."""
    existing = connection.execute(
        "SELECT id FROM files WHERE path = ?", (prepared.relative,)
    ).fetchone()
    existing_id = existing[0] if existing is not None else None
    if prepared.redacted:
        if existing_id is not None:
            _delete_file_rows(connection, existing_id)
        return 0
    if existing_id is not None:
        _delete_file_rows(connection, existing_id)
    cursor = connection.execute(
        "INSERT INTO files (path, size, mtime_ns, content_hash, lang, indexed_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            prepared.relative,
            prepared.size,
            prepared.mtime_ns,
            prepared.digest,
            None,
            int(time.time()),
        ),
    )
    assert cursor.lastrowid is not None
    file_id = cursor.lastrowid
    for chunk in prepared.chunks:
        _write_chunk(connection, file_id, prepared.relative, chunk)
    return len(prepared.chunks)


def _write_chunk(
    connection: sqlite3.Connection, file_id: int, relative: str, chunk: Chunk
) -> None:
    """Insert one chunk row and its full-text row."""
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
