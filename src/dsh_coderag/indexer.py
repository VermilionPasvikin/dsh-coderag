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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from dsh_coderag import sqlite_caps
from dsh_coderag.chunker import chunk_text
from dsh_coderag.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_FILES,
    IndexConfig,
    adaptive_workers,
    next_batch_size,
)
from dsh_coderag.log import build_audit_record, log_event, write_audit_dump
from dsh_coderag.sanitize import scan_secret
from dsh_coderag.text import to_bigrams
from dsh_coderag.types import Chunk
from dsh_coderag.walker import WalkReport, walk_with_report

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
    redacted: int


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


def _walk_targets(
    base: Path, config: IndexConfig | None
) -> tuple[WalkReport, set[str]]:
    """Walk the workspace and return its report plus the relative paths seen."""
    max_files = config.max_files if config is not None else DEFAULT_MAX_FILES
    max_file_bytes = (
        config.max_file_bytes if config is not None else DEFAULT_MAX_FILE_BYTES
    )
    report = walk_with_report(base, max_files=max_files, max_file_bytes=max_file_bytes)
    current_paths = {
        absolute.relative_to(base).as_posix() for absolute, _, _ in report.files
    }
    return report, current_paths


def _known_hashes(connection: sqlite3.Connection) -> dict[str, str]:
    """Read the path -> content hash map that drives incremental skipping."""
    return {
        str(row[0]): str(row[1])
        for row in connection.execute("SELECT path, content_hash FROM files").fetchall()
    }


def _write_batches(
    connection: sqlite3.Connection,
    prepared: list[_PreparedFile],
    batch_size: int,
    check: Callable[[], bool],
) -> tuple[int, float]:
    """Write prepared files in adaptive batches.

    Returns the chunk count written and the milliseconds spent writing, so the
    caller can report the write phase without owning the loop.
    """
    total_chunks = 0
    written_ms = 0.0
    position = 0
    while position < len(prepared) and not check():
        end = min(position + batch_size, len(prepared))
        started = time.monotonic()
        with connection:
            for item in prepared[position:end]:
                if check():
                    break
                total_chunks += _write_prepared(connection, item)
        batch_ms = _ms(started)
        written_ms += batch_ms
        batch_size = next_batch_size(batch_size, batch_ms / 1000.0)
        position = end
    return total_chunks, written_ms


def _log_index_error(run_started: float, exc: Exception) -> None:
    """Log the structured failure event for an aborted indexing run."""
    log_event(
        "index_error",
        level="error",
        duration_ms=_ms(run_started),
        error=type(exc).__name__,
    )


def _report_index_done(
    base: Path,
    report: WalkReport,
    total_chunks: int,
    redacted: int,
    phase_ms: dict[str, float],
    run_started: float,
) -> IndexSummary:
    """Write the audit dump, log completion and build the run summary."""
    total_ms = _ms(run_started)
    record = build_audit_record(
        root=str(base),
        task_id=None,
        files=len(report.files),
        chunks=total_chunks,
        skipped=dict(report.reasons),
        redacted=redacted,
        duration_ms={**phase_ms, "total": total_ms},
    )
    write_audit_dump(base, record)
    log_event(
        "index_done",
        duration_ms=total_ms,
        files=len(report.files),
        chunks=total_chunks,
        skipped=sum(report.reasons.values()),
        redacted=redacted,
    )
    return IndexSummary(root=base, files=len(report.files), chunks=total_chunks)


def _run_options(
    config: IndexConfig | None, should_cancel: Callable[[], bool] | None
) -> tuple[int, int, Callable[[], bool]]:
    """Resolve workers, starting batch size and the cancellation check."""
    workers = config.workers if config is not None else adaptive_workers()
    batch_size = config.start_batch_size if config is not None else DEFAULT_BATCH_SIZE
    check = should_cancel if should_cancel is not None else _never_cancelled
    return workers, batch_size, check


def index_sync(
    root: Path,
    config: IndexConfig | None = None,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> IndexSummary:
    """Index a workspace synchronously and return the resulting counts.

    config tunes batching and concurrency; the workspace root always comes
    from the root argument. should_cancel is polled at every file boundary;
    once it returns True no further rows are written and the workspace index
    is not marked ready. Re-running replaces only the files whose content
    hash changed, adds new files and cascade-deletes removed ones.
    """
    if not sqlite_caps.fts5_available():
        raise sqlite_caps.Fts5UnavailableError(sqlite_caps.FTS5_HINT)
    base = root.resolve()
    db_path = base / ".coderag" / "index.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = open_index(db_path)
    workers, batch_size, check = _run_options(config, should_cancel)
    phase_ms = {"walk": 0.0, "prepare": 0.0, "write": 0.0, "cleanup": 0.0}
    run_started = time.monotonic()
    log_event("index_start", root=str(base))
    try:
        started = time.monotonic()
        report, current_paths = _walk_targets(base, config)
        phase_ms["walk"] = _ms(started)
        started = time.monotonic()
        prepared = _prepare_files(
            report.files, base, _known_hashes(connection), workers, check
        )
        phase_ms["prepare"] = _ms(started)
        redacted = sum(item.redacted for item in prepared)
        total_chunks, written_ms = _write_batches(connection, prepared, batch_size, check)
        phase_ms["write"] += written_ms
        started = time.monotonic()
        if not check():
            _remove_missing_files(connection, current_paths)
            _mark_ready(connection, base)
        phase_ms["cleanup"] = _ms(started)
        return _report_index_done(
            base, report, total_chunks, redacted, phase_ms, run_started
        )
    except Exception as exc:
        _log_index_error(run_started, exc)
        raise
    finally:
        connection.close()


def _ms(started: float) -> float:
    """Return milliseconds elapsed since a time.monotonic() reading."""
    return (time.monotonic() - started) * 1000.0


def _never_cancelled() -> bool:
    """Default cancellation check for callers that do not cancel."""
    return False


def _prepare_files(
    entries: list[tuple[Path, int, int]],
    base: Path,
    known: dict[str, str],
    workers: int,
    should_cancel: Callable[[], bool],
) -> list[_PreparedFile]:
    """Prepare every changed file, in parallel when there is more than one.

    Cancellation is polled before each file; files prepared after the flag
    is set are dropped without being written.
    """
    prepared: list[_PreparedFile] = []
    if workers <= 1 or len(entries) <= 1:
        for absolute, size, mtime_ns in entries:
            if should_cancel():
                break
            item = _prepare_file(absolute, base, size, mtime_ns, known)
            if item is not None:
                prepared.append(item)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for absolute, size, mtime_ns in entries:
                if should_cancel():
                    break
                futures.append(pool.submit(_prepare_file, absolute, base, size, mtime_ns, known))
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
    surviving: list[Chunk] = []
    redacted = 0
    for chunk in chunks:
        if scan_secret(chunk.text) is None:
            surviving.append(chunk)
        else:
            redacted += 1
    return _PreparedFile(
        relative=relative,
        size=size,
        mtime_ns=mtime_ns,
        digest=digest,
        chunks=tuple(surviving),
        redacted=redacted,
    )


def _write_prepared(connection: sqlite3.Connection, prepared: _PreparedFile) -> int:
    """Replace one prepared file's rows; return the chunks written."""
    existing = connection.execute(
        "SELECT id FROM files WHERE path = ?", (prepared.relative,)
    ).fetchone()
    existing_id = existing[0] if existing is not None else None
    if prepared.redacted > 0 and not prepared.chunks:
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
