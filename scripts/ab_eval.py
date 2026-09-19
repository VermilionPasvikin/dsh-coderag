#!/usr/bin/env python3
"""CLI for the self-built L2 A/B runner (EVAL.md 3.6).

All logic lives in `dsh_coderag.eval.ab` so it can be type-checked and tested;
this file is only argument parsing and I/O.

Usage:
    python scripts/ab_eval.py run --cases cases --group eval-coderag \\
        --out eval/runs/b-v1 --profile headless --patch cordis.patch.yml \\
        --workspace /tmp/dsh-coderag-l2-corpus --trials 3
    python scripts/ab_eval.py gate --baseline eval/runs/a-v1/report.json \\
        --current eval/runs/b-v1/report.json --markdown eval/runs/gate.md

Every `dsh` invocation goes through the pinned wrapper `./scripts/dsh`
(AGENTS.md E-07). The runner itself never calls a model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dsh_coderag.eval.ab import (
    AbError,
    gate,
    iter_attempt_errors,
    load_cases,
    render_gate_markdown,
    render_markdown,
    run_group,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ab_eval.py",
        description="L2 end-to-end A/B runner for dsh-coderag.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one group over every case.")
    run_parser.add_argument("--cases", required=True, help="Directory of *.json cases.")
    run_parser.add_argument("--group", required=True, help="Group name recorded in the report.")
    run_parser.add_argument("--out", required=True, help="Output directory for report.json.")
    run_parser.add_argument("--workspace", required=True, help="Working directory dsh runs in.")
    run_parser.add_argument(
        "--profile", default="headless", help="DSH profile (default: headless)."
    )
    run_parser.add_argument("--dsh", default="./scripts/dsh", help="dsh wrapper (E-07).")
    run_parser.add_argument(
        "--patch", action="append", default=[], help="Extra --patch overlay; repeatable."
    )
    run_parser.add_argument("--trials", type=int, default=1, help="Attempts per case.")
    run_parser.add_argument(
        "--timeout", type=float, default=900.0, help="Per-attempt timeout in seconds."
    )
    run_parser.add_argument(
        "--dsh-home", help="DSH_HOME holding the profile; default keeps the ambient one."
    )

    gate_parser = subparsers.add_parser("gate", help="Compare a baseline and a current report.")
    gate_parser.add_argument("--baseline", required=True, help="Baseline report.json.")
    gate_parser.add_argument("--current", required=True, help="Current report.json.")
    gate_parser.add_argument("--out", help="Write the gate JSON here.")
    gate_parser.add_argument("--markdown", help="Write the gate Markdown here.")
    return parser


def _load_report(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "cases" not in payload:
        raise AbError(f"{path}: 不是一份 run 报告")
    return payload


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "run":
        try:
            cases = load_cases(Path(args.cases))
        except AbError as exc:
            sys.stderr.write(f"{exc}\n")
            return 2
        try:
            report = run_group(
                cases,
                group=args.group,
                out_dir=Path(args.out),
                dsh=[args.dsh],
                profile=args.profile,
                workspace=Path(args.workspace),
                patches=[Path(patch) for patch in args.patch],
                trials=args.trials,
                timeout_s=args.timeout,
                dsh_home=Path(args.dsh_home) if args.dsh_home else None,
            )
        except AbError as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        write_json(report, Path(args.out) / "report.json")
        (Path(args.out) / "report.md").write_text(render_markdown(report), encoding="utf-8")
        sys.stderr.write(
            f"{args.group}: taskSuccess {report['task_success_rate']} "
            f"({report['successes']}/{report['attempts']}) -> {args.out}/report.json\n"
        )
        for failure in iter_attempt_errors(report):
            sys.stderr.write(f"  attempt error: {failure}\n")
        return 0
    if args.command == "gate":
        try:
            result = gate(_load_report(args.baseline), _load_report(args.current))
        except AbError as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        if args.out:
            write_json(result, Path(args.out))
        if args.markdown:
            Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
            Path(args.markdown).write_text(render_gate_markdown(result), encoding="utf-8")
        sys.stderr.write(render_gate_markdown(result))
        return 0 if result["passed"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
