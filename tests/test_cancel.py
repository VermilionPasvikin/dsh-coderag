"""Tests for task cancellation (T2-12)."""

from __future__ import annotations

import time
from pathlib import Path

from dsh_coderag.config import IndexConfig
from dsh_coderag.indexer import IndexSummary, index_sync, open_index
from dsh_coderag.taskman import TaskManager, TaskState


def _make_files(root: Path, count: int) -> None:
    for index in range(count):
        (root / f"f{index}.py").write_text(
            f"def f{index}():\n    return {index}\n", encoding="utf-8"
        )


def _count(repo: Path, table: str) -> int:
    connection = open_index(repo / ".coderag" / "index.sqlite3")
    try:
        return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()


def _ready(repo: Path) -> int:
    connection = open_index(repo / ".coderag" / "index.sqlite3")
    try:
        rows = connection.execute("SELECT ready FROM workspace_index").fetchall()
        return int(rows[0][0]) if rows else 0
    finally:
        connection.close()


class _CancelAfter:
    """Return False for the first allowed calls, then True."""

    def __init__(self, allowed: int) -> None:
        self.calls = 0
        self.allowed = allowed

    def __call__(self) -> bool:
        self.calls += 1
        return self.calls > self.allowed


def test_cancel_moves_a_running_task_to_cancelled(index_db: Path, tmp_path: Path) -> None:
    manager = TaskManager(index_db)

    def blocking_worker(root: Path, *, should_cancel: object) -> IndexSummary:
        deadline = time.monotonic() + 5
        while not should_cancel() and time.monotonic() < deadline:  # type: ignore[operator]
            time.sleep(0.005)
        return IndexSummary(root=root, files=0, chunks=0)

    task_id = manager.start(tmp_path, blocking_worker)  # type: ignore[arg-type]
    deadline = time.monotonic() + 5
    while manager.status(task_id).state != TaskState.RUNNING.value and time.monotonic() < deadline:
        time.sleep(0.005)
    manager.cancel(task_id)
    assert manager.status(task_id).state == TaskState.CANCELLED.value
    time.sleep(0.05)
    assert manager.status(task_id).state == TaskState.CANCELLED.value


def test_cancel_before_any_write_leaves_the_index_empty(tmp_path: Path) -> None:
    _make_files(tmp_path, 5)
    summary = index_sync(
        tmp_path,
        IndexConfig(root=tmp_path, batch_size=1, max_workers=1),
        should_cancel=lambda: True,
    )
    assert summary.chunks == 0
    assert _count(tmp_path, "files") == 0
    assert _ready(tmp_path) == 0


def test_cancel_stops_writing_after_a_signal(tmp_path: Path) -> None:
    _make_files(tmp_path, 10)
    summary = index_sync(
        tmp_path,
        IndexConfig(root=tmp_path, batch_size=1, max_workers=1),
        should_cancel=_CancelAfter(allowed=12),
    )
    assert 0 < summary.chunks < 10
    assert _ready(tmp_path) == 0


def test_cancel_does_not_mark_the_workspace_ready(tmp_path: Path) -> None:
    _make_files(tmp_path, 4)
    index_sync(
        tmp_path,
        IndexConfig(root=tmp_path, batch_size=1, max_workers=1),
        should_cancel=lambda: True,
    )
    assert _ready(tmp_path) == 0
