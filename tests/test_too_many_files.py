"""Tests for the maxFiles limit (PROJECT.md 5.2, RL-08)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.config import IndexConfig
from dsh_coderag.indexer import index_sync, open_index
from dsh_coderag.types import ErrorCode
from dsh_coderag.walker import TooManyFilesError, walk, walk_with_report


def _make_files(root: Path, count: int) -> None:
    for index in range(count):
        (root / f"f{index}.py").write_text(
            f"def f{index}():\n    return {index}\n", encoding="utf-8"
        )


def test_too_many_files_raises_with_the_actual_count(tmp_path: Path) -> None:
    _make_files(tmp_path, 3)
    with pytest.raises(TooManyFilesError) as excinfo:
        walk(tmp_path, max_files=2)
    error = excinfo.value
    assert error.actual_count == 3
    assert error.max_files == 2
    assert error.code is ErrorCode.INDEX_TOO_MANY_FILES
    assert error.payload == {
        "code": "INDEX_TOO_MANY_FILES",
        "actual_count": 3,
        "max_files": 2,
        "message": str(error),
    }


def test_too_many_files_allows_exactly_the_limit(tmp_path: Path) -> None:
    _make_files(tmp_path, 2)
    assert len(walk_with_report(tmp_path, max_files=2).files) == 2


def test_too_many_files_counts_only_indexable_files(tmp_path: Path) -> None:
    _make_files(tmp_path, 2)
    (tmp_path / ".env").write_text("KEY=value\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("not code\n", encoding="utf-8")
    assert len(walk_with_report(tmp_path, max_files=2).files) == 2


def test_too_many_files_fails_the_index_instead_of_truncating(tmp_path: Path) -> None:
    _make_files(tmp_path, 3)
    with pytest.raises(TooManyFilesError) as excinfo:
        index_sync(tmp_path, IndexConfig(root=tmp_path, max_files=2))
    assert excinfo.value.actual_count == 3
    connection = open_index(tmp_path / ".coderag" / "index.sqlite3")
    try:
        assert connection.execute("SELECT count(*) FROM files").fetchone() == (0,)
    finally:
        connection.close()
