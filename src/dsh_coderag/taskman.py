"""Indexing task ids and state machine backed by the index_runs table.

This module owns task creation and the pending / running / ready / failed /
cancelled state machine. It does not run indexing itself: callers drive the
transitions while they do the work.
"""

from __future__ import annotations

import secrets
import sqlite3
import time
from enum import Enum
from pathlib import Path

from dsh_coderag.indexer import open_index
from dsh_coderag.types import IndexRun


class TaskState(str, Enum):
    """The states an indexing task moves through."""

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskNotFoundError(Exception):
    """Raised when a task id does not exist."""


class TaskStateError(Exception):
    """Raised when a transition is not allowed from the current state."""


class TaskManager:
    """Create and update indexing tasks stored in the index_runs table."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create(self, root: Path) -> str:
        """Insert a pending task for root and return its id."""
        task_id = self._new_task_id()
        connection = open_index(self._db_path)
        try:
            with connection:
                connection.execute(
                    "INSERT INTO index_runs (task_id, root, state, started_at)"
                    " VALUES (?, ?, ?, ?)",
                    (task_id, str(root.resolve()), TaskState.PENDING.value, int(time.time())),
                )
        finally:
            connection.close()
        return task_id

    def status(self, task_id: str) -> IndexRun:
        """Return the persisted run; raise TaskNotFoundError if unknown."""
        connection = open_index(self._db_path)
        try:
            row = connection.execute(
                "SELECT task_id, root, state, total_files, done_files, total_chunks,"
                " done_chunks, message, started_at, finished_at"
                " FROM index_runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise TaskNotFoundError(task_id)
        return IndexRun(*row)

    def mark_running(self, task_id: str) -> None:
        """Move a pending task to running."""
        connection = open_index(self._db_path)
        try:
            with connection:
                self._require_from(connection, task_id, (TaskState.PENDING,))
                connection.execute(
                    "UPDATE index_runs SET state = ? WHERE task_id = ?",
                    (TaskState.RUNNING.value, task_id),
                )
        finally:
            connection.close()

    def mark_ready(
        self,
        task_id: str,
        *,
        total_files: int = 0,
        done_files: int = 0,
        total_chunks: int = 0,
        done_chunks: int = 0,
    ) -> None:
        """Move a running task to ready and record its counts."""
        connection = open_index(self._db_path)
        try:
            with connection:
                self._require_from(connection, task_id, (TaskState.RUNNING,))
                connection.execute(
                    "UPDATE index_runs SET state = ?, total_files = ?, done_files = ?,"
                    " total_chunks = ?, done_chunks = ?, finished_at = ?"
                    " WHERE task_id = ?",
                    (
                        TaskState.READY.value,
                        total_files,
                        done_files,
                        total_chunks,
                        done_chunks,
                        int(time.time()),
                        task_id,
                    ),
                )
        finally:
            connection.close()

    def mark_failed(self, task_id: str, message: str) -> None:
        """Move a pending or running task to failed and record the reason."""
        connection = open_index(self._db_path)
        try:
            with connection:
                self._require_from(connection, task_id, (TaskState.PENDING, TaskState.RUNNING))
                connection.execute(
                    "UPDATE index_runs SET state = ?, message = ?, finished_at = ?"
                    " WHERE task_id = ?",
                    (TaskState.FAILED.value, message, int(time.time()), task_id),
                )
        finally:
            connection.close()

    def cancel(self, task_id: str) -> None:
        """Move a pending or running task to cancelled."""
        connection = open_index(self._db_path)
        try:
            with connection:
                self._require_from(connection, task_id, (TaskState.PENDING, TaskState.RUNNING))
                connection.execute(
                    "UPDATE index_runs SET state = ?, finished_at = ? WHERE task_id = ?",
                    (TaskState.CANCELLED.value, int(time.time()), task_id),
                )
        finally:
            connection.close()

    def _require_from(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        allowed: tuple[TaskState, ...],
    ) -> None:
        row = connection.execute(
            "SELECT state FROM index_runs WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(task_id)
        allowed_values = {state.value for state in allowed}
        if row[0] not in allowed_values:
            raise TaskStateError(
                f"task {task_id} is {row[0]}, expected one of {sorted(allowed_values)}"
            )

    @staticmethod
    def _new_task_id() -> str:
        return f"idx-{time.strftime('%Y%m%d')}-{secrets.token_hex(2)}"
