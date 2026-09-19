"""Retrieval-quality evaluation for dsh-coderag (EVAL.md L1).

This package loads the golden task set, runs each query through the production
searcher and writes a per-query JSON report. It never participates in the
production retrieval path and never calls a model. Future pieces live in
their own modules: metrics (T3-04), attribution (T3-04b), diff (T3-04c) and
golden_version checks (T3-04d).
"""

from __future__ import annotations

from dsh_coderag.eval.report import REPORT_SCHEMA, build_report, write_report
from dsh_coderag.eval.runner import DEFAULT_K, EvalResult, EvalRun, run_eval
from dsh_coderag.eval.tasks import (
    TASK_CLASSES,
    EvalError,
    EvalTask,
    EvalTaskError,
    load_tasks,
    validate_tasks,
)

__all__ = [
    "DEFAULT_K",
    "REPORT_SCHEMA",
    "TASK_CLASSES",
    "EvalError",
    "EvalResult",
    "EvalRun",
    "EvalTask",
    "EvalTaskError",
    "build_report",
    "load_tasks",
    "run_eval",
    "validate_tasks",
    "write_report",
]
