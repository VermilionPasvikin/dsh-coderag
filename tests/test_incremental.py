"""Tests for content-hash incremental indexing (PROJECT.md 5.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

import dsh_coderag.indexer as indexer
from dsh_coderag.indexer import index_sync, open_index


def _rows(repo: Path, sql: str) -> list[tuple[object, ...]]:
    connection = open_index(repo / ".coderag" / "index.sqlite3")
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def test_incremental_reindex_adds_no_new_rows(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    before_files = _rows(tiny_repo, "SELECT id, path, content_hash FROM files ORDER BY path")
    before_chunks = _rows(
        tiny_repo, "SELECT id, file_id, seq, content_hash FROM chunks ORDER BY id"
    )
    summary = index_sync(tiny_repo)
    assert summary.chunks == 0
    assert (
        _rows(tiny_repo, "SELECT id, path, content_hash FROM files ORDER BY path")
        == before_files
    )
    assert (
        _rows(tiny_repo, "SELECT id, file_id, seq, content_hash FROM chunks ORDER BY id")
        == before_chunks
    )


def test_incremental_skips_chunking_unchanged_files(
    tiny_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index_sync(tiny_repo)
    chunked: list[str] = []
    original = indexer.chunk_text

    def spy(*args: object, **kwargs: object) -> object:
        chunked.append(str(args[1]))
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(indexer, "chunk_text", spy)
    index_sync(tiny_repo)
    assert chunked == []


def test_incremental_reindexes_a_changed_file(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("def one():\n    return 1\n", encoding="utf-8")
    index_sync(tmp_path)
    target.write_text("def two():\n    return 2\n", encoding="utf-8")
    index_sync(tmp_path)
    texts = [row[0] for row in _rows(tmp_path, "SELECT text FROM chunks")]
    assert len(texts) == 1
    assert "def two" in str(texts[0])
    assert "def one" not in str(texts[0])


def test_incremental_keeps_unchanged_files_intact_when_another_changes(tmp_path: Path) -> None:
    (tmp_path / "kept.py").write_text("def kept():\n    return 1\n", encoding="utf-8")
    (tmp_path / "changed.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    index_sync(tmp_path)
    kept_file_id = _rows(tmp_path, "SELECT id FROM files WHERE path = 'kept.py'")[0][0]
    (tmp_path / "changed.py").write_text("def new():\n    return 2\n", encoding="utf-8")
    index_sync(tmp_path)
    assert _rows(tmp_path, "SELECT id FROM files WHERE path = 'kept.py'")[0][0] == kept_file_id
    changed = _rows(
        tmp_path,
        "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
        " WHERE f.path = 'changed.py'",
    )
    assert "def new" in str(changed[0][0])


def test_incremental_records_a_file_that_becomes_redacted(tmp_path: Path) -> None:
    target = tmp_path / "leak.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    index_sync(tmp_path)
    assert _rows(tmp_path, "SELECT count(*) FROM files") == [(1,)]
    target.write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    index_sync(tmp_path)
    assert _rows(tmp_path, "SELECT count(*) FROM files") == [(0,)]
    assert _rows(tmp_path, "SELECT count(*) FROM chunks") == [(0,)]
