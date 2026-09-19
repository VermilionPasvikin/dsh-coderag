#!/usr/bin/env python3
"""Regenerate `cases/REVIEW.md` from `cases/*.json` (T3-16).

The review table is generated so it cannot drift from the case files; a test
asserts the committed file matches this renderer's output.

    python scripts/case-review.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dsh_coderag.eval.ab import load_cases, render_case_review

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"


def main() -> int:
    """Render the review table and write it next to the cases."""
    cases = load_cases(CASES_DIR)
    target = CASES_DIR / "REVIEW.md"
    target.write_text(render_case_review(cases), encoding="utf-8")
    sys.stderr.write(f"wrote {target} ({len(cases)} cases)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
