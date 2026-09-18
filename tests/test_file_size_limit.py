"""Tests for the per-file size limit (PROJECT.md 5.2, T2-21)."""

from __future__ import annotations

import json
from pathlib import Path

from dsh_coderag.config import DEFAULT_MAX_FILE_BYTES, IndexConfig, load_config
from dsh_coderag.indexer import index_sync, open_index
from dsh_coderag.walker import walk_with_report


def _big_file(tmp_path: Path, name: str = "big.py", lines: int = 50) -> Path:
    path = tmp_path / name
    path.write_text("x = 1\n" * lines, encoding="utf-8")
    return path


def test_too_large_files_are_skipped_before_reading(tmp_path: Path) -> None:
    path = _big_file(tmp_path)
    report = walk_with_report(tmp_path, max_file_bytes=50)
    assert report.files == []
    assert report.reasons == {"too_large": 1}
    assert path.stat().st_size > 50


def test_too_large_files_are_not_indexed(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    _big_file(tmp_path)
    index_sync(tmp_path, IndexConfig(root=tmp_path, max_file_bytes=50))
    connection = open_index(tmp_path / ".coderag" / "index.sqlite3")
    try:
        paths = {row[0] for row in connection.execute("SELECT path FROM files")}
    finally:
        connection.close()
    assert paths == {"small.py"}


def test_too_large_reason_is_reported_in_the_audit(tmp_path: Path) -> None:
    _big_file(tmp_path)
    index_sync(tmp_path, IndexConfig(root=tmp_path, max_file_bytes=50))
    audit = json.loads(
        (tmp_path / ".coderag" / "last-index.json").read_text(encoding="utf-8")
    )
    assert audit["skipped"]["reasons"] == {"too_large": 1}


def test_too_large_boundary_is_inclusive(tmp_path: Path) -> None:
    path = tmp_path / "exact.py"
    path.write_text("x" * 100, encoding="utf-8")
    report = walk_with_report(tmp_path, max_file_bytes=100)
    assert len(report.files) == 1
    assert report.reasons == {}


def test_too_large_default_is_one_mib(tmp_path: Path) -> None:
    config = load_config({"CODERAG_ROOT": str(tmp_path)})
    assert config.max_file_bytes == DEFAULT_MAX_FILE_BYTES
    assert DEFAULT_MAX_FILE_BYTES == 1024 * 1024


def test_too_large_env_override(tmp_path: Path) -> None:
    config = load_config(
        {"CODERAG_ROOT": str(tmp_path), "CODERAG_MAX_FILE_BYTES": "123"}
    )
    assert config.max_file_bytes == 123
