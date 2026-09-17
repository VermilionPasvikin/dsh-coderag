"""Tests for the indexing task state machine in dsh_coderag.taskman."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.taskman import TaskManager, TaskNotFoundError, TaskState, TaskStateError


@pytest.fixture
def manager(index_db: Path) -> TaskManager:
    return TaskManager(index_db)


def test_create_returns_idx_prefixed_id_in_pending_state(
    manager: TaskManager, tmp_path: Path
) -> None:
    task_id = manager.create(tmp_path)
    assert task_id.startswith("idx-")
    assert manager.status(task_id).state == TaskState.PENDING.value


def test_state_machine_progresses_pending_running_ready(
    manager: TaskManager, tmp_path: Path
) -> None:
    task_id = manager.create(tmp_path)
    manager.mark_running(task_id)
    assert manager.status(task_id).state == TaskState.RUNNING.value
    manager.mark_ready(task_id, total_files=3, done_files=3, total_chunks=6, done_chunks=6)
    run = manager.status(task_id)
    assert run.state == TaskState.READY.value
    assert (run.total_files, run.done_files, run.total_chunks, run.done_chunks) == (3, 3, 6, 6)
    assert run.finished_at is not None


def test_ready_requires_running_first(manager: TaskManager, tmp_path: Path) -> None:
    task_id = manager.create(tmp_path)
    with pytest.raises(TaskStateError):
        manager.mark_ready(task_id)


def test_cancel_moves_a_pending_task_to_cancelled(
    manager: TaskManager, tmp_path: Path
) -> None:
    task_id = manager.create(tmp_path)
    manager.cancel(task_id)
    assert manager.status(task_id).state == TaskState.CANCELLED.value


def test_failure_records_the_message(manager: TaskManager, tmp_path: Path) -> None:
    task_id = manager.create(tmp_path)
    manager.mark_running(task_id)
    manager.mark_failed(task_id, "disk full")
    run = manager.status(task_id)
    assert run.state == TaskState.FAILED.value
    assert run.message == "disk full"


def test_status_raises_for_an_unknown_task(manager: TaskManager) -> None:
    with pytest.raises(TaskNotFoundError):
        manager.status("idx-20260101-dead")


def test_state_survives_a_new_manager_instance(index_db: Path, tmp_path: Path) -> None:
    task_id = TaskManager(index_db).create(tmp_path)
    TaskManager(index_db).mark_running(task_id)
    assert TaskManager(index_db).status(task_id).state == TaskState.RUNNING.value
