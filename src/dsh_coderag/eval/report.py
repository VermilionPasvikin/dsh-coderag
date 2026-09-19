"""Serialize an eval run into the per-query JSON report (EVAL.md 2.7 / 2.14).

`build_report` turns an `EvalRun` into a plain JSON-serializable dict that
lists every task's outcome plus raw hit/miss counts per class. It computes no
Success@k, MRR or confidence interval — those metrics are T3-04 — and no
before/after diff, which is T3-04c.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dsh_coderag.eval.runner import EvalResult, EvalRun
from dsh_coderag.eval.tasks import TASK_CLASSES

REPORT_SCHEMA = "dsh-coderag/eval-run/v1"


def build_report(run: EvalRun, *, tasks_file: str | None = None) -> dict[str, Any]:
    """Build the report dict for one run.

    `tasks_file` is recorded as provenance only; it does not affect the run.
    """
    class_counts: dict[str, dict[str, int]] = {}
    for task_class in TASK_CLASSES:
        results = [result for result in run.results if result.task_class == task_class]
        class_counts[task_class] = {
            "total": len(results),
            "hit": sum(1 for result in results if result.hit),
        }
    return {
        "schema": REPORT_SCHEMA,
        "k": run.k,
        "corpus_root": str(run.corpus_root),
        "tasks_file": tasks_file,
        "task_count": len(run.results),
        "hit_count": sum(1 for result in run.results if result.hit),
        "class_counts": class_counts,
        "results": [_result_to_json(result) for result in run.results],
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    """Write a report as UTF-8 JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _result_to_json(result: EvalResult) -> dict[str, Any]:
    return {
        "id": result.task_id,
        "class": result.task_class,
        "query": result.query,
        "status": result.status,
        "hit": result.hit,
        "matched_path": result.matched_path,
        "rank": result.rank,
        "returned_paths": list(result.returned_paths),
        "must_not_hit": list(result.must_not_hit),
        "symbol_hit": result.symbol_hit,
        "token_estimate": result.token_estimate,
        "error": result.error,
    }
