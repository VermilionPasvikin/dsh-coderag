"""Command line for the L1 retrieval evaluation.

This is a thin wrapper over `load_tasks` / `validate_tasks` / `run_eval` /
`build_report` so a human or `scripts/eval-gate.sh` can run the golden set
against a corpus copy. It writes JSON to stdout unless `--out` is given; the
human-readable summary always goes to stderr, keeping stdout valid JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dsh_coderag.config import DEFAULT_MAX_TOKENS
from dsh_coderag.eval.report import build_report, write_report
from dsh_coderag.eval.runner import DEFAULT_K, run_eval
from dsh_coderag.eval.tasks import EvalTaskError, load_tasks, validate_tasks


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for `python -m dsh_coderag.eval`."""
    parser = argparse.ArgumentParser(
        prog="python -m dsh_coderag.eval",
        description="Run the dsh-coderag L1 retrieval evaluation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the golden set and emit JSON.")
    run_parser.add_argument("--tasks", required=True, help="Path to tasks.jsonl.")
    run_parser.add_argument("--root", required=True, help="Indexed corpus root.")
    run_parser.add_argument("--k", type=int, default=DEFAULT_K, help="Top-k (default: 5).")
    run_parser.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="Per-query token budget."
    )
    run_parser.add_argument("--out", help="Write JSON here instead of stdout.")

    validate_parser = subparsers.add_parser(
        "validate", help="Check the golden set without searching."
    )
    validate_parser.add_argument("--tasks", required=True, help="Path to tasks.jsonl.")
    validate_parser.add_argument("--root", required=True, help="Corpus root for path checks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        tasks = load_tasks(Path(args.tasks))
    except EvalTaskError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    errors = validate_tasks(tasks, Path(args.root))
    if errors:
        for error in errors:
            sys.stderr.write(f"{error}\n")
        sys.stderr.write(f"FAIL: {len(errors)} 项校验失败（{len(tasks)} 条任务）\n")
        return 2
    if args.command == "validate":
        sys.stdout.write(f"OK: {len(tasks)} 条任务通过校验\n")
        return 0
    run = run_eval(tasks, Path(args.root), k=args.k, max_tokens=args.max_tokens)
    report = build_report(run, tasks_file=str(args.tasks))
    if args.out:
        write_report(report, Path(args.out))
        sys.stderr.write(f"wrote {args.out}\n")
    else:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    sys.stderr.write(
        f"tasks {report['task_count']} / hit {report['hit_count']} "
        f"(k={report['k']}, corpus={report['corpus_root']})\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
