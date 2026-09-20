"""Tests for the L1 `gate` subcommand (T3-12).

`gate` is what `scripts/eval-gate.sh` drives: run the golden set, print the
metrics this layer owns, diff against a baseline per query, and exit 0/1/2.
Everything runs offline against a tiny really-indexed corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsh_coderag.eval.__main__ import main
from dsh_coderag.eval.runner import GOLDEN_META_FILENAME
from dsh_coderag.indexer import index_sync

VERSION = "m3-b1"
MISSING_QUERY = "zzz_no_such_identifier_anywhere"


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A two-file indexed corpus; the golden task targets the irrelevant file."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "other.py").write_text("def other():\n    return 1\n", encoding="utf-8")
    (root / "verify.py").write_text(
        "def verify_token(token):\n    return bool(token)\n", encoding="utf-8"
    )
    index_sync(root)
    return root


def write_task_set(tmp_path: Path) -> Path:
    tasks = tmp_path / "tasks.jsonl"
    task = {
        "id": "L-001",
        "class": "exact",
        "query": MISSING_QUERY,
        "expect_paths": ["other.py"],
        "added": "2026-09-20",
    }
    tasks.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp_path / GOLDEN_META_FILENAME).write_text(
        json.dumps({"golden_version": VERSION}), encoding="utf-8"
    )
    return tasks


def make_baseline(tmp_path: Path, corpus: Path) -> Path:
    """Produce a real baseline report through the `run` subcommand."""
    baseline = tmp_path / "baseline.json"
    code = main(
        [
            "run",
            "--tasks",
            str(write_task_set(tmp_path)),
            "--root",
            str(corpus),
            "--expect-golden-version",
            VERSION,
            "--out",
            str(baseline),
        ]
    )
    assert code == 0
    return baseline


def run_gate(tmp_path: Path, corpus: Path, baseline: Path, gate_out: Path) -> int:
    return main(
        [
            "gate",
            "--tasks",
            str(tmp_path / "tasks.jsonl"),
            "--root",
            str(corpus),
            "--baseline",
            str(baseline),
            "--gate-out",
            str(gate_out),
            "--out",
            str(tmp_path / "current.json"),
        ]
    )


def test_gate_passes_against_an_unchanged_baseline(tmp_path: Path, corpus: Path) -> None:
    baseline = make_baseline(tmp_path, corpus)
    gate_out = tmp_path / "gate.json"

    assert run_gate(tmp_path, corpus, baseline, gate_out) == 0

    gate = json.loads(gate_out.read_text(encoding="utf-8"))
    assert gate["schema"] == "dsh-coderag/eval-gate/v1"
    assert gate["regression_count"] == 0
    assert gate["verdict"]["passed"] is True
    assert gate["golden_version"] == VERSION


def test_gate_reports_the_metrics_it_owns(tmp_path: Path, corpus: Path) -> None:
    baseline = make_baseline(tmp_path, corpus)
    gate_out = tmp_path / "gate.json"
    run_gate(tmp_path, corpus, baseline, gate_out)

    gate = json.loads(gate_out.read_text(encoding="utf-8"))
    metrics = gate["metrics"]
    assert set(metrics) >= {"overall", "exact", "crossfile", "natural"}
    assert metrics["overall"]["success"]["5"] is not None
    assert metrics["overall"]["mrr"] is not None
    assert metrics["natural"]["n"] == 0


def test_gate_fails_when_the_baseline_held_a_hit_that_is_now_gone(
    tmp_path: Path, corpus: Path
) -> None:
    baseline = make_baseline(tmp_path, corpus)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    row = payload["results"][0]
    assert row["hit"] is False, "探测查询必须未命中，否则这个用例没有意义"
    row["hit"], row["rank"], row["matched_path"] = True, 1, "other.py"
    baseline.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    gate_out = tmp_path / "gate.json"

    assert run_gate(tmp_path, corpus, baseline, gate_out) == 1

    gate = json.loads(gate_out.read_text(encoding="utf-8"))
    assert gate["regression_count"] == 1
    assert gate["verdict"]["active_regressions"] == ["L-001"]
    assert gate["verdict"]["passed"] is False


def test_gate_fails_on_a_golden_version_break(tmp_path: Path, corpus: Path) -> None:
    baseline = make_baseline(tmp_path, corpus)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["golden_version"] = "m3-b2"
    baseline.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    gate_out = tmp_path / "gate.json"

    # A methodology break is a verdict (1), not unusable input (2).
    assert run_gate(tmp_path, corpus, baseline, gate_out) == 1


def test_gate_needs_an_executable_baseline(
    tmp_path: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_task_set(tmp_path)
    code = run_gate(tmp_path, corpus, tmp_path / "absent.json", tmp_path / "gate.json")

    assert code == 2
    assert "无法读取 baseline 报告" in capsys.readouterr().err
