"""Tests for the three index change classes (PROJECT.md 5.2)."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.indexer import index_sync, open_index


def _rows(repo: Path, sql: str) -> list[tuple[object, ...]]:
    connection = open_index(repo / ".coderag" / "index.sqlite3")
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def _chunk_paths(repo: Path) -> set[str]:
    rows = _rows(
        repo,
        "SELECT DISTINCT f.path FROM chunks c JOIN files f ON f.id = c.file_id",
    )
    return {str(row[0]) for row in rows}


def test_add_modify_delete_adds_a_new_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_sync(tmp_path)
    assert _chunk_paths(tmp_path) == {"a.py"}

    (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    index_sync(tmp_path)
    assert _chunk_paths(tmp_path) == {"a.py", "b.py"}
    assert _rows(tmp_path, "SELECT count(*) FROM files") == [(2,)]


def test_add_modify_delete_replaces_chunks_for_a_changed_file(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("def old_one():\n    return 1\n", encoding="utf-8")
    index_sync(tmp_path)

    target.write_text("def new_two():\n    return 2\n", encoding="utf-8")
    index_sync(tmp_path)
    texts = [
        str(row[0])
        for row in _rows(
            tmp_path,
            "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
            " WHERE f.path = 'a.py'",
        )
    ]
    assert len(texts) == 1
    assert "new_two" in texts[0]
    assert "old_one" not in texts[0]
    assert _rows(tmp_path, "SELECT count(*) FROM files") == [(1,)]


def test_add_modify_delete_cascades_a_deleted_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    index_sync(tmp_path)

    (tmp_path / "b.py").unlink()
    index_sync(tmp_path)
    assert _chunk_paths(tmp_path) == {"a.py"}
    assert _rows(tmp_path, "SELECT count(*) FROM files") == [(1,)]
    assert _rows(tmp_path, "SELECT count(*) FROM chunks") == [(1,)]
    assert _rows(tmp_path, "SELECT count(*) FROM chunks_fts") == [(1,)]
