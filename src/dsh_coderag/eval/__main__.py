"""Command line for the L1 retrieval evaluation.

Thin wrapper over `load_tasks` / `validate_tasks` / `run_eval` / `build_report`
so a human or `scripts/eval-gate.sh` can drive the golden set. `run` writes JSON
to stdout unless `--out` is given; the human-readable summary always goes to
stderr, keeping stdout valid JSON.

`run` and `gate` enforce the golden-set isolation rule (EVAL.md 2.7): they read
`tasks.meta.json` next to the tasks file and fail with exit code 2 when the
expected version does not match, unless `--rebaseline` is passed. `gate` pins
the version the baseline report used, so a silent edit to the golden set fails
instead of quietly changing the meaning of the comparison.

`gate` performs the whole L1 decision (T3-04c): layered metrics (S1/S2/S4), a
per-query diff against a baseline report, and a verdict keyed on the regression
count. Exit codes: 0 PASS, 1 FAIL, 2 unusable input or environment.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dsh_coderag.config import DEFAULT_MAX_TOKENS
from dsh_coderag.eval.metrics import MetricSet, layered_metrics
from dsh_coderag.eval.report import (
    ReportDiffError,
    build_report,
    diff_runs,
    gate_diff,
    render_diff_markdown,
    write_report,
)
from dsh_coderag.eval.runner import (
    DEFAULT_K,
    GOLDEN_META_FILENAME,
    GoldenVersionError,
    check_golden_version,
    load_golden_meta,
    run_eval,
)
from dsh_coderag.eval.tasks import EvalTask, EvalTaskError, load_tasks, validate_tasks

GATE_SCHEMA = "dsh-coderag/eval-gate/v1"
"""Schema of the `gate --gate-out` payload."""

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INPUT = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for `python -m dsh_coderag.eval`."""
    parser = argparse.ArgumentParser(
        prog="python -m dsh_coderag.eval",
        description="Run the dsh-coderag L1 retrieval evaluation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the golden set and emit JSON.")
    _add_run_arguments(run_parser)
    run_parser.add_argument("--out", help="Write JSON here instead of stdout.")

    gate_parser = subparsers.add_parser(
        "gate", help="Run the golden set, print metrics, and gate on regressions."
    )
    _add_run_arguments(gate_parser)
    gate_parser.add_argument(
        "--baseline", required=True, help="Baseline report.json to diff against."
    )
    gate_parser.add_argument(
        "--waiver",
        action="append",
        default=[],
        help="Task id whose regression a human accepted; repeatable.",
    )
    gate_parser.add_argument(
        "--max-regressions",
        type=int,
        default=0,
        help="Unwaived regressions tolerated before failing (default: 0).",
    )
    gate_parser.add_argument("--out", help="Write the new run report here.")
    gate_parser.add_argument("--gate-out", help="Write the gate JSON here.")
    gate_parser.add_argument("--markdown", help="Write the diff Markdown here.")

    validate_parser = subparsers.add_parser(
        "validate", help="Check the golden set without searching."
    )
    validate_parser.add_argument("--tasks", required=True, help="Path to tasks.jsonl.")
    validate_parser.add_argument("--root", required=True, help="Corpus root for path checks.")
    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tasks", required=True, help="Path to tasks.jsonl.")
    parser.add_argument("--root", required=True, help="Indexed corpus root.")
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="Top-k (default: 5).")
    parser.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="Per-query token budget."
    )
    parser.add_argument(
        "--expect-golden-version",
        help=(
            "Fail when the golden set's version differs from this value "
            "(EVAL.md 2.7). Omit to run without pinning a baseline."
        ),
    )
    parser.add_argument(
        "--rebaseline",
        action="store_true",
        help="Explicitly accept a golden_version mismatch. Human opt-out, never inferred.",
    )


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        tasks = load_tasks(Path(args.tasks))
    except EvalTaskError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_INPUT
    if args.command == "validate":
        return _cmd_validate(args, tasks)
    if args.command == "run":
        return _cmd_run(args, tasks)
    return _cmd_gate(args, tasks)


def _cmd_validate(args: argparse.Namespace, tasks: list[EvalTask]) -> int:
    errors = validate_tasks(tasks, Path(args.root))
    if errors:
        return _report_validation_errors(errors, len(tasks))
    sys.stdout.write(f"OK: {len(tasks)} 条任务通过校验\n")
    return EXIT_PASS


def _cmd_run(args: argparse.Namespace, tasks: list[EvalTask]) -> int:
    try:
        meta = load_golden_meta(Path(args.tasks).with_name(GOLDEN_META_FILENAME))
        check_golden_version(
            args.expect_golden_version, meta.golden_version, rebaseline=args.rebaseline
        )
    except GoldenVersionError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_INPUT
    golden_version = meta.golden_version
    errors = validate_tasks(tasks, Path(args.root))
    if errors:
        return _report_validation_errors(errors, len(tasks))
    run = run_eval(
        tasks,
        Path(args.root),
        k=args.k,
        max_tokens=args.max_tokens,
        golden_version=golden_version,
    )
    report = build_report(run, tasks_file=str(args.tasks))
    if args.out:
        write_report(report, Path(args.out))
        sys.stderr.write(f"wrote {args.out}\n")
    else:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    sys.stderr.write(
        f"tasks {report['task_count']} / hit {report['hit_count']} "
        f"(k={report['k']}, corpus={report['corpus_root']}, "
        f"golden_version={golden_version})\n"
    )
    return EXIT_PASS


def _cmd_gate(args: argparse.Namespace, tasks: list[EvalTask]) -> int:
    try:
        baseline = _load_report(Path(args.baseline))
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_INPUT
    try:
        meta = load_golden_meta(Path(args.tasks).with_name(GOLDEN_META_FILENAME))
    except GoldenVersionError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_INPUT
    try:
        check_golden_version(
            _pinned_version(args, baseline), meta.golden_version, rebaseline=args.rebaseline
        )
    except GoldenVersionError as exc:
        # A methodology break is a verdict about the run, not unusable input.
        sys.stderr.write(f"{exc}\n")
        return EXIT_FAIL
    golden_version = meta.golden_version
    errors = validate_tasks(tasks, Path(args.root))
    if errors:
        return _report_validation_errors(errors, len(tasks))

    run = run_eval(
        tasks,
        Path(args.root),
        k=args.k,
        max_tokens=args.max_tokens,
        golden_version=golden_version,
    )
    report = build_report(run, tasks_file=str(args.tasks))
    metrics = layered_metrics(run)
    _print_metrics(metrics)
    if args.out:
        write_report(report, Path(args.out))
    diff = diff_runs(baseline, report)
    try:
        verdict = gate_diff(
            diff, waivers=args.waiver, max_regressions=args.max_regressions
        )
    except ReportDiffError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_INPUT
    sys.stderr.write(
        f"S3 不在此处（属 L2）｜ 回归条数 = {diff['regression_count']}"
        f"（改善 {diff['improvement_count']}）｜ 门禁：{'PASS' if verdict['passed'] else 'FAIL'}\n"
    )
    for reason in verdict["reasons"]:
        sys.stderr.write(f"  - {reason}\n")
    if args.markdown:
        _write_text(Path(args.markdown), render_diff_markdown(diff, verdict))
    if args.gate_out:
        write_report(
            {
                "schema": GATE_SCHEMA,
                "golden_version": golden_version,
                "baseline": str(args.baseline),
                "metrics": _metrics_to_json(metrics),
                "regression_count": diff["regression_count"],
                "improvement_count": diff["improvement_count"],
                "verdict": verdict,
            },
            Path(args.gate_out),
        )
    return EXIT_PASS if verdict["passed"] else EXIT_FAIL


def _pinned_version(
    args: argparse.Namespace, baseline: Mapping[str, Any] | None
) -> str | None:
    """Return the golden version this job expects, if it pins one.

    `--expect-golden-version` wins; otherwise the baseline report's own version
    is used, so a silent edit to the golden set fails the gate instead of
    redefining what the comparison means.
    """
    if args.expect_golden_version:
        return str(args.expect_golden_version)
    if baseline is not None:
        pinned = baseline.get("golden_version")
        if isinstance(pinned, str) and pinned:
            return pinned
    return None


def _load_report(path: Path) -> dict[str, Any]:
    """Read a baseline report, raising ValueError with an actionable message."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{path}: 无法读取 baseline 报告：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: 非法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: baseline 报告顶层必须是 JSON 对象")
    return payload


def _report_validation_errors(errors: list[str], task_count: int) -> int:
    for error in errors:
        sys.stderr.write(f"{error}\n")
    sys.stderr.write(f"FAIL: {len(errors)} 项校验失败（{task_count} 条任务）\n")
    return EXIT_INPUT


def _print_metrics(metrics: Mapping[str, MetricSet]) -> None:
    """Print the L1 success criteria this layer owns (S1, S2, S4)."""
    overall = metrics.get("overall")
    if overall is None:
        return
    per_class = " / ".join(
        f"{name} {_fmt(_success_at(metrics, name, 5))}"
        for name in ("exact", "crossfile", "natural")
    )
    sys.stderr.write(f"S1 Success@5 = {_fmt(overall.success.get(5))}  ({per_class})\n")
    sys.stderr.write(f"S2 MRR = {_fmt(overall.mrr)}\n")
    sys.stderr.write(f"S4 token_median = {_fmt(overall.token_median)}\n")


def _success_at(metrics: Mapping[str, MetricSet], name: str, k: int) -> float | None:
    metric_set = metrics.get(name)
    return None if metric_set is None else metric_set.success.get(k)


def _metrics_to_json(metrics: Mapping[str, MetricSet]) -> dict[str, Any]:
    return {
        name: {
            "n": metric_set.total,
            "success": {str(k): v for k, v in sorted(metric_set.success.items())},
            "mrr": metric_set.mrr,
            "token_median": metric_set.token_median,
        }
        for name, metric_set in metrics.items()
        if metric_set is not None
    }


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    sys.exit(main())
