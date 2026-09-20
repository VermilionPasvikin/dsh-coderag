"""Tests for `golden_version` validation (T3-04d).

EVAL.md 2.7 requires a run to declare the golden version it expects and to fail
immediately on a mismatch, unless the job is explicitly a rebaseline; otherwise
"the questions changed" and "the engine changed" are indistinguishable.

Everything runs offline. The CLI tests use a small tmp corpus that is really
indexed, so exit code 0 means the run actually happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsh_coderag.eval.__main__ import main
from dsh_coderag.eval.runner import (
    GOLDEN_META_FILENAME,
    GoldenMeta,
    GoldenVersionError,
    check_golden_version,
    load_golden_meta,
    run_eval,
)
from dsh_coderag.eval.tasks import load_tasks
from dsh_coderag.indexer import index_sync

VERSION = "m3-b1"


def write_meta(directory: Path, payload: object) -> Path:
    """Write a `tasks.meta.json` with arbitrary content."""
    path = directory / GOLDEN_META_FILENAME
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def write_tasks(directory: Path, *, expect_path: str = "verify.py") -> Path:
    """Write a one-task golden set whose query leaks no path fragment."""
    path = directory / "tasks.jsonl"
    task = {
        "id": "L-001",
        "class": "exact",
        "query": "令牌校验入口",
        "expect_paths": [expect_path],
        "added": "2026-09-20",
    }
    path.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A tiny really-indexed corpus so a CLI run can actually complete."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "verify.py").write_text(
        "def verify_token(token):\n    return bool(token)\n", encoding="utf-8"
    )
    index_sync(root)
    return root


# ── load_golden_meta ────────────────────────────────────────────────────
def test_loads_the_version(tmp_path: Path) -> None:
    path = write_meta(tmp_path, {"golden_version": VERSION})
    assert load_golden_meta(path) == GoldenMeta(golden_version=VERSION)


def test_a_missing_meta_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(GoldenVersionError, match="无法读取"):
        load_golden_meta(tmp_path / GOLDEN_META_FILENAME)


def test_malformed_json_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / GOLDEN_META_FILENAME
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(GoldenVersionError, match="非法 JSON"):
        load_golden_meta(path)


def test_a_non_object_top_level_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(GoldenVersionError, match="JSON 对象"):
        load_golden_meta(write_meta(tmp_path, ["m3-b1"]))


@pytest.mark.parametrize("payload", [{}, {"golden_version": ""}, {"golden_version": 3}])
def test_a_missing_or_blank_version_is_an_error(tmp_path: Path, payload: object) -> None:
    with pytest.raises(GoldenVersionError, match="golden_version"):
        load_golden_meta(write_meta(tmp_path, payload))


# ── check_golden_version ────────────────────────────────────────────────
def test_a_matching_version_passes() -> None:
    assert check_golden_version(VERSION, VERSION) is None


def test_no_pinned_version_never_fails() -> None:
    assert check_golden_version(None, VERSION) is None


def test_a_mismatch_fails_and_names_the_escape_hatch() -> None:
    with pytest.raises(GoldenVersionError) as excinfo:
        check_golden_version("m3-b1", "m3-b2")
    message = str(excinfo.value)
    assert "m3-b1" in message and "m3-b2" in message
    assert "--rebaseline" in message


def test_rebaseline_bypasses_the_mismatch() -> None:
    assert check_golden_version("m3-b1", "m3-b2", rebaseline=True) is None


# ── run_eval provenance ─────────────────────────────────────────────────
def test_run_eval_records_the_golden_version(tmp_path: Path, corpus: Path) -> None:
    tasks = load_tasks(write_tasks(tmp_path))
    run = run_eval(tasks, corpus, golden_version=VERSION)
    assert run.golden_version == VERSION
    assert run_eval(tasks, corpus).golden_version is None


# ── CLI exit behaviour ──────────────────────────────────────────────────
def _run_cli(tmp_path: Path, corpus: Path, *extra: str, version: object = VERSION,
             meta: bool = True) -> int:
    tasks_path = write_tasks(tmp_path)
    if meta:
        write_meta(tmp_path, {"golden_version": version})
    return main(
        ["run", "--tasks", str(tasks_path), "--root", str(corpus), *extra]
    )


def test_cli_runs_when_the_version_matches(
    tmp_path: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_cli(tmp_path, corpus, "--expect-golden-version", VERSION)

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["task_count"] == 1
    assert f"golden_version={VERSION}" in captured.err


def test_cli_fails_on_a_version_mismatch(
    tmp_path: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_cli(tmp_path, corpus, "--expect-golden-version", "m3-b2")

    captured = capsys.readouterr()
    assert code == 2
    assert "golden_version 不匹配" in captured.err
    assert "--rebaseline" in captured.err
    assert captured.out == ""  # nothing ran


def test_cli_rebaseline_accepts_a_mismatch(
    tmp_path: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_cli(
        tmp_path, corpus, "--expect-golden-version", "m3-b2", "--rebaseline"
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "golden_version 不匹配" not in captured.err
    # the version actually on disk is what gets recorded
    assert f"golden_version={VERSION}" in captured.err


def test_cli_without_a_pinned_version_runs(
    tmp_path: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_cli(tmp_path, corpus) == 0
    assert capsys.readouterr().out != ""


def test_cli_without_a_meta_file_fails(
    tmp_path: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_cli(tmp_path, corpus, meta=False)

    captured = capsys.readouterr()
    assert code == 2
    assert "无法读取 golden 集元数据" in captured.err


def test_the_version_check_runs_before_the_corpus_is_touched(
    tmp_path: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A methodology break must fail fast, not after path validation."""
    tasks_path = write_tasks(tmp_path, expect_path="does-not-exist.py")
    write_meta(tmp_path, {"golden_version": VERSION})
    code = main(
        [
            "run",
            "--tasks",
            str(tasks_path),
            "--root",
            str(corpus),
            "--expect-golden-version",
            "m3-b2",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "golden_version 不匹配" in captured.err
    assert "校验失败" not in captured.err
