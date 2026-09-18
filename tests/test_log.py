"""Tests for structured logging and the audit dump (PROJECT.md 5.7, T2-16)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dsh_coderag.indexer import index_sync
from dsh_coderag.log import log_event


def _stderr_records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    output = capsys.readouterr().err
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def test_log_event_writes_one_json_object_per_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_event("demo", task_id="idx-1", duration_ms=1.5, extra="value")
    records = _stderr_records(capsys)
    assert len(records) == 1
    record = records[0]
    assert record["level"] == "info"
    assert record["event"] == "demo"
    assert record["task_id"] == "idx-1"
    assert record["duration_ms"] == 1.5
    assert record["extra"] == "value"
    assert "ts" in record


def test_index_writes_json_lines_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_sync(tmp_path)
    records = _stderr_records(capsys)
    assert [record["event"] for record in records] == ["index_start", "index_done"]
    assert all(
        {"ts", "level", "event", "task_id", "duration_ms"} <= set(record)
        for record in records
    )


def test_index_writes_the_audit_dump(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_sync(tmp_path)
    audit = json.loads(
        (tmp_path / ".coderag" / "last-index.json").read_text(encoding="utf-8")
    )
    assert set(audit) == {
        "root",
        "task_id",
        "files",
        "chunks",
        "skipped",
        "redacted",
        "duration_ms",
    }
    assert audit["files"] == 1
    assert audit["chunks"] == 1
    assert audit["skipped"] == {"count": 0, "reasons": {}}
    assert audit["redacted"] == {"count": 0}
    assert set(audit["duration_ms"]) == {"walk", "prepare", "write", "cleanup", "total"}


def test_audit_dump_counts_skipped_and_redacted(tmp_path: Path) -> None:
    (tmp_path / "normal.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "credentials.py").write_text("USER = 'x'\n", encoding="utf-8")
    (tmp_path / "leak.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    index_sync(tmp_path)
    audit = json.loads(
        (tmp_path / ".coderag" / "last-index.json").read_text(encoding="utf-8")
    )
    assert audit["skipped"]["reasons"] == {"secret_file": 1}
    assert audit["redacted"]["count"] == 1


def test_logger_never_writes_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    log_event("demo")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() != ""
