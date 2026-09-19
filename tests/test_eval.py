"""Tests for the L1 evaluation package (T3-03).

Every filesystem test builds its corpus under tmp_path (TESTING.md T-03/T-04)
and offline (T-02). One opt-in integration test replays the real A-batch
against an already-indexed corpus copy when CODERAG_EVAL_CORPUS is set; it is
skipped otherwise so the default suite stays hermetic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from dsh_coderag.eval import (
    DEFAULT_K,
    EvalTask,
    EvalTaskError,
    build_report,
    load_tasks,
    run_eval,
    validate_tasks,
    write_report,
)
from dsh_coderag.indexer import index_sync

REPO_TASKS = Path(__file__).resolve().parents[1] / "eval" / "tasks.jsonl"
INTEGRATION_CORPUS = os.environ.get("CODERAG_EVAL_CORPUS")


@pytest.fixture
def eval_corpus(tmp_path: Path) -> Path:
    """A tiny indexed workspace with two searchable modules (T-03/T-04)."""
    root = tmp_path / "corpus"
    (root / "src" / "net").mkdir(parents=True)
    (root / "src" / "auth.py").write_text(
        "def verify_token(token: str) -> bool:\n    return token == 'ok'\n",
        encoding="utf-8",
    )
    (root / "src" / "net" / "retry.py").write_text(
        "def retry_call(attempts: int) -> int:\n"
        "    return token_retry(attempts)\n",
        encoding="utf-8",
    )
    (root / "src" / "depth.py").write_text(
        "def delegationDepthOf(session):\n    return 0\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("docs only, never indexed\n", encoding="utf-8")
    index_sync(root)
    return root


def make_task(**overrides: Any) -> EvalTask:
    """Build a valid task, letting each test override exactly what it tests."""
    fields: dict[str, Any] = {
        "id": "L-001",
        "task_class": "exact",
        "query": "retry_call",
        "expect_paths": ("src/net/retry.py",),
        "added": "2026-09-19",
    }
    fields.update(overrides)
    return EvalTask(**fields)


def write_tasks(path: Path, payloads: list[dict[str, Any]]) -> Path:
    """Serialize task dicts to a JSONL file the loader can read."""
    path.write_text(
        "\n".join(json.dumps(payload, ensure_ascii=False) for payload in payloads) + "\n",
        encoding="utf-8",
    )
    return path


def task_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "L-001",
        "class": "exact",
        "query": "retry_call",
        "expect_paths": ["src/net/retry.py"],
        "added": "2026-09-19",
    }
    payload.update(overrides)
    return payload


# ── load ────────────────────────────────────────────────────────────────
def test_load_tasks_reads_every_jsonl_line(tmp_path: Path) -> None:
    path = write_tasks(
        tmp_path / "tasks.jsonl",
        [
            task_payload(id="L-001"),
            task_payload(
                **{"class": "natural"},
                id="L-002",
                query="失败以后怎么办",
                expect_symbols=["x"],
            ),
        ],
    )
    tasks = load_tasks(path)
    assert [task.id for task in tasks] == ["L-001", "L-002"]
    assert tasks[0].expect_paths == ("src/net/retry.py",)
    assert tasks[0].must_not_paths == ()
    assert tasks[1].task_class == "natural"
    assert tasks[1].expect_symbols == ("x",)


def test_load_tasks_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(EvalTaskError):
        load_tasks(tmp_path / "absent.jsonl")


def test_load_tasks_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "tasks.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(EvalTaskError, match="未解析到任何任务"):
        load_tasks(path)


def test_load_tasks_rejects_blank_line(tmp_path: Path) -> None:
    path = tmp_path / "tasks.jsonl"
    path.write_text(json.dumps(task_payload()) + "\n\n", encoding="utf-8")
    with pytest.raises(EvalTaskError, match="空行"):
        load_tasks(path)


def test_load_tasks_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "tasks.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(EvalTaskError, match="非法 JSON"):
        load_tasks(path)


def test_load_tasks_rejects_missing_required_field(tmp_path: Path) -> None:
    payload = task_payload()
    del payload["expect_paths"]
    path = write_tasks(tmp_path / "tasks.jsonl", [payload])
    with pytest.raises(EvalTaskError, match="缺少必填字段"):
        load_tasks(path)


def test_load_tasks_rejects_unknown_field(tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.jsonl", [task_payload(klass="exact")])
    with pytest.raises(EvalTaskError, match="未知字段"):
        load_tasks(path)


def test_load_tasks_rejects_wrong_type_for_expect_paths(tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.jsonl", [task_payload(expect_paths="src/a.py")])
    with pytest.raises(EvalTaskError, match="必须是数组"):
        load_tasks(path)


# ── validate ────────────────────────────────────────────────────────────
def test_validate_accepts_wellformed_task(eval_corpus: Path, tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.jsonl", [task_payload()])
    assert validate_tasks(load_tasks(path), eval_corpus) == []


def test_validate_reports_duplicate_ids(eval_corpus: Path, tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.jsonl", [task_payload(), task_payload()])
    errors = validate_tasks(load_tasks(path), eval_corpus)
    assert any("重复" in error for error in errors)


def test_validate_reports_missing_expect_path(eval_corpus: Path, tmp_path: Path) -> None:
    path = write_tasks(
        tmp_path / "tasks.jsonl", [task_payload(expect_paths=["src/absent.py"])]
    )
    errors = validate_tasks(load_tasks(path), eval_corpus)
    assert any("不存在" in error for error in errors)


def test_validate_reports_absolute_path(eval_corpus: Path, tmp_path: Path) -> None:
    path = write_tasks(
        tmp_path / "tasks.jsonl", [task_payload(expect_paths=["/src/net/retry.py"])]
    )
    errors = validate_tasks(load_tasks(path), eval_corpus)
    assert any("绝对路径" in error for error in errors)


def test_validate_reports_leaked_path_fragment(eval_corpus: Path, tmp_path: Path) -> None:
    path = write_tasks(
        tmp_path / "tasks.jsonl", [task_payload(query="retry.py 在哪里")]
    )
    errors = validate_tasks(load_tasks(path), eval_corpus)
    assert any("泄漏目标路径片段" in error for error in errors)


def test_validate_ignores_path_stem_inside_longer_identifier(
    eval_corpus: Path, tmp_path: Path
) -> None:
    """`depth` inside `delegationDepthOf` is not a leak (identifier boundary)."""
    path = write_tasks(
        tmp_path / "tasks.jsonl",
        [task_payload(query="delegationDepthOf", expect_paths=["src/depth.py"])],
    )
    assert validate_tasks(load_tasks(path), eval_corpus) == []


def test_validate_reports_unknown_class(eval_corpus: Path, tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.jsonl", [task_payload(**{"class": "semantic"})])
    errors = validate_tasks(load_tasks(path), eval_corpus)
    assert any("class" in error for error in errors)


def test_validate_reports_bad_added_date(eval_corpus: Path, tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.jsonl", [task_payload(added="2026-9-19")])
    errors = validate_tasks(load_tasks(path), eval_corpus)
    assert any("added" in error for error in errors)


def test_validate_reports_expect_and_must_not_overlap(
    eval_corpus: Path, tmp_path: Path
) -> None:
    path = write_tasks(
        tmp_path / "tasks.jsonl",
        [task_payload(must_not_paths=["src/net/retry.py"])],
    )
    errors = validate_tasks(load_tasks(path), eval_corpus)
    assert any("must_not_paths" in error for error in errors)


def test_validate_reports_nonexistent_corpus_root(tmp_path: Path) -> None:
    path = write_tasks(tmp_path / "tasks.jsonl", [task_payload()])
    errors = validate_tasks(load_tasks(path), tmp_path / "absent")
    assert any("不存在" in error for error in errors)


# ── run ─────────────────────────────────────────────────────────────────
def test_run_marks_hit_when_expect_path_returned(eval_corpus: Path) -> None:
    run = run_eval([make_task()], eval_corpus)
    result = run.results[0]
    assert result.status == "ready"
    assert result.hit is True
    assert result.matched_path == "src/net/retry.py"
    assert result.rank == 1
    assert run.k == DEFAULT_K


def test_run_marks_miss_when_answer_not_returned(eval_corpus: Path) -> None:
    task = make_task(query="retry_call", expect_paths=("src/auth.py",))
    result = run_eval([task], eval_corpus).results[0]
    assert result.status == "ready"
    assert result.hit is False
    assert result.matched_path is None
    assert result.rank is None


def test_run_reports_indexing_status_when_index_absent(tmp_path: Path) -> None:
    unindexed = tmp_path / "no-index"
    unindexed.mkdir()
    result = run_eval([make_task()], unindexed).results[0]
    assert result.status == "indexing"
    assert result.hit is False


def test_run_fails_task_when_must_not_path_returned(eval_corpus: Path) -> None:
    task = make_task(
        query="token",
        expect_paths=("src/auth.py",),
        must_not_paths=("src/net/retry.py",),
    )
    result = run_eval([task], eval_corpus).results[0]
    assert "src/net/retry.py" in result.returned_paths
    assert result.must_not_hit == ("src/net/retry.py",)
    assert result.hit is False


def test_run_requires_declared_expect_symbol(eval_corpus: Path) -> None:
    present = make_task(
        query="token",
        expect_paths=("src/auth.py",),
        expect_symbols=("verify_token",),
    )
    absent = make_task(
        query="token",
        expect_paths=("src/auth.py",),
        expect_symbols=("symbol_that_does_not_exist",),
    )
    present_result, absent_result = run_eval([present, absent], eval_corpus).results
    assert present_result.symbol_hit is True
    assert present_result.hit is True
    assert absent_result.symbol_hit is False
    assert absent_result.hit is False


def test_run_limits_returned_paths_to_k(eval_corpus: Path) -> None:
    task = make_task(query="token", expect_paths=("src/auth.py",))
    result = run_eval([task], eval_corpus, k=1).results[0]
    assert len(result.returned_paths) <= 1


# ── report ──────────────────────────────────────────────────────────────
def test_build_report_lists_every_query_and_class_counts(eval_corpus: Path) -> None:
    tasks = [
        make_task(id="L-001"),
        make_task(
            id="L-002",
            task_class="natural",
            query="不存在的概念",
            expect_paths=("src/auth.py",),
        ),
    ]
    report = build_report(run_eval(tasks, eval_corpus), tasks_file="eval/tasks.jsonl")
    assert report["schema"] == "dsh-coderag/eval-run/v1"
    assert report["k"] == DEFAULT_K
    assert report["tasks_file"] == "eval/tasks.jsonl"
    assert report["task_count"] == 2
    assert report["hit_count"] == 1
    assert report["class_counts"]["exact"] == {"total": 1, "hit": 1}
    assert report["class_counts"]["natural"] == {"total": 1, "hit": 0}
    assert [entry["id"] for entry in report["results"]] == ["L-001", "L-002"]
    assert report["results"][0]["matched_path"] == "src/net/retry.py"


def test_build_report_reflects_requested_k(eval_corpus: Path) -> None:
    report = build_report(run_eval([make_task()], eval_corpus, k=3))
    assert report["k"] == 3


def test_write_report_writes_parseable_json(eval_corpus: Path, tmp_path: Path) -> None:
    report = build_report(run_eval([make_task()], eval_corpus))
    out = tmp_path / "runs" / "l1.json"
    write_report(report, out)
    assert json.loads(out.read_text(encoding="utf-8"))["task_count"] == 1


# ── integration: the real A-batch (opt-in) ──────────────────────────────
@pytest.mark.skipif(
    INTEGRATION_CORPUS is None,
    reason="set CODERAG_EVAL_CORPUS to an indexed DSH copy to replay the A-batch",
)
def test_a_batch_runs_against_indexed_corpus(tmp_path: Path) -> None:
    """Replay the frozen 10-task A-batch and write its per-query JSON."""
    corpus = Path(INTEGRATION_CORPUS or "")
    tasks = load_tasks(REPO_TASKS)
    assert len(tasks) == 10
    assert validate_tasks(tasks, corpus) == []
    run = run_eval(tasks, corpus, k=DEFAULT_K)
    assert len(run.results) == 10
    assert all(result.status != "indexing" for result in run.results)
    report = build_report(run, tasks_file=str(REPO_TASKS))
    out = tmp_path / "a-batch.json"
    write_report(report, out)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["task_count"] == 10
    assert len(written["results"]) == 10
