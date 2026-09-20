"""Command line for the L1 retrieval evaluation.

This is a thin wrapper over `load_tasks` / `validate_tasks` / `run_eval` /
`build_report` so a human or `scripts/eval-gate.sh` can run the golden set
against a corpus copy. It writes JSON to stdout unless `--out` is given; the
human-readable summary always goes to stderr, keeping stdout valid JSON.

`run` also enforces the golden-set isolation rule (EVAL.md 2.7): it reads
`tasks.meta.json` next to the tasks file and fails with exit code 2 when
`--expect-golden-version` does not match, unless `--rebaseline` is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dsh_coderag.config import DEFAULT_MAX_TOKENS
from dsh_coderag.eval.report import build_report, write_report
from dsh_coderag.eval.runner import (
    DEFAULT_K,
    GOLDEN_META_FILENAME,
    GoldenVersionError,
    check_golden_version,
    load_golden_meta,
    run_eval,
)
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
    run_parser.add_argument(
        "--expect-golden-version",
        help=(
            "Fail when the golden set's version differs from this value "
            "(EVAL.md 2.7). Omit to run without pinning a baseline."
        ),
    )
    run_parser.add_argument(
        "--rebaseline",
        action="store_true",
        help="Explicitly accept a golden_version mismatch. Human opt-out, never inferred.",
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
    golden_version: str | None = None
    if args.command == "run":
        # Checked before anything touches the corpus: a methodology break must
        # fail fast, not after a full run.
        try:
            meta = load_golden_meta(Path(args.tasks).with_name(GOLDEN_META_FILENAME))
            check_golden_version(
                args.expect_golden_version,
                meta.golden_version,
                rebaseline=args.rebaseline,
            )
        except GoldenVersionError as exc:
            sys.stderr.write(f"{exc}\n")
            return 2
        golden_version = meta.golden_version
    errors = validate_tasks(tasks, Path(args.root))
    if errors:
        for error in errors:
            sys.stderr.write(f"{error}\n")
        sys.stderr.write(f"FAIL: {len(errors)} 项校验失败（{len(tasks)} 条任务）\n")
        return 2
    if args.command == "validate":
        sys.stdout.write(f"OK: {len(tasks)} 条任务通过校验\n")
        return 0
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
