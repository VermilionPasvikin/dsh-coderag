"""Tests for the SQLite schema in dsh_coderag.indexer."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from dsh_coderag.indexer import connect, init_schema

EXPECTED_TABLES = {"index_runs", "files", "chunks", "chunks_fts", "workspace_index"}


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {name for (name,) in rows}


@pytest.fixture
def schema_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "index.sqlite3")
    init_schema(connection)
    try:
        yield connection
    finally:
        connection.close()


def test_all_documented_tables_are_created(schema_conn: sqlite3.Connection) -> None:
    assert _table_names(schema_conn) >= EXPECTED_TABLES


def test_embeddings_table_is_not_created(schema_conn: sqlite3.Connection) -> None:
    assert "embeddings" not in _table_names(schema_conn)


def test_journal_mode_is_wal(schema_conn: sqlite3.Connection) -> None:
    assert schema_conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_foreign_keys_are_enabled(schema_conn: sqlite3.Connection) -> None:
    assert schema_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_chunks_fts_uses_the_unicode61_tokenizer(schema_conn: sqlite3.Connection) -> None:
    row = schema_conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'"
    ).fetchone()
    assert row is not None
    assert "unicode61" in row[0]
    schema_conn.execute(
        "INSERT INTO chunks_fts (text_bigram, symbol, path, chunk_id, file_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("校验", "verify_token", "a.py", 1, 1),
    )
    assert schema_conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] == 1


def test_init_schema_is_idempotent(index_db: Path) -> None:
    connection = connect(index_db)
    try:
        init_schema(connection)
        init_schema(connection)
        assert _table_names(connection) >= EXPECTED_TABLES
    finally:
        connection.close()
