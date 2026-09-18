"""Structured JSON-Lines logging and the per-run audit dump (PROJECT.md 5.7).

This module writes newline-delimited JSON to stderr -- never stdout, which is
the MCP protocol channel (RL-04) -- and writes the run's audit record to
<root>/.coderag/last-index.json. It never logs code content and does not
index, search or read the database.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, TextIO

AUDIT_DIR = ".coderag"
AUDIT_FILENAME = "last-index.json"


def log_event(
    event: str,
    *,
    level: str = "info",
    task_id: str | None = None,
    duration_ms: float | None = None,
    stream: TextIO | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Write one JSON object on one line to stderr; return the record.

    Every record carries ts, level, event, task_id and duration_ms; extra
    keyword fields are merged in. Nothing is ever written to stdout.
    """
    record: dict[str, Any] = {
        "ts": time.time(),
        "level": level,
        "event": event,
        "task_id": task_id,
        "duration_ms": duration_ms,
    }
    record.update(fields)
    target = sys.stderr if stream is None else stream
    target.write(json.dumps(record, ensure_ascii=False) + "\n")
    target.flush()
    return record


def build_audit_record(
    *,
    root: str,
    task_id: str | None,
    files: int,
    chunks: int,
    skipped: dict[str, int],
    redacted: int,
    duration_ms: dict[str, float],
) -> dict[str, Any]:
    """Build the audit record written after each indexing run (5.7)."""
    return {
        "root": root,
        "task_id": task_id,
        "files": files,
        "chunks": chunks,
        "skipped": {"count": sum(skipped.values()), "reasons": dict(skipped)},
        "redacted": {"count": redacted},
        "duration_ms": dict(duration_ms),
    }


def write_audit_dump(root: Path, record: dict[str, Any]) -> Path:
    """Write the audit record to <root>/.coderag/last-index.json."""
    directory = root / AUDIT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / AUDIT_FILENAME
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path
