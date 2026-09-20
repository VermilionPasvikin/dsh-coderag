"""Tests for the L1 per-query diff and regression gate (T3-04c).

Everything here is a pure function over two run reports, so no corpus and no
index are needed. Expected counts are written by hand in each test, and the
gate tests deliberately cover the case EVAL.md 2.7 cares about: the mean goes up
while individual queries regress.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dsh_coderag.eval.report import (
    CHANGE_IMPROVEMENT,
    CHANGE_RANK_IMPROVED,
    CHANGE_RANK_REGRESSED,
    CHANGE_REGRESSION,
    CHANGE_UNCHANGED,
    DIFF_SCHEMA,
    MAX_REGRESSIONS_DEFAULT,
    REPORT_SCHEMA,
    ReportDiffError,
    build_report,
    diff_runs,
    gate_diff,
    render_diff_markdown,
)
from dsh_coderag.eval.runner import EvalRun


def entry(
    task_id: str,
    *,
    task_class: str = "exact",
    hit: bool,
    rank: int | None = None,
    matched_path: str | None = None,
    query: str = "q",
) -> dict[str, Any]:
    """Build one `results` row as `build_report` would emit it."""
    return {
        "id": task_id,
        "class": task_class,
        "query": query,
        "hit": hit,
        "rank": rank,
        "matched_path": matched_path,
    }


def report(
    *entries: dict[str, Any], k: int = 5, golden_version: str | None = "m3-b1"
) -> dict[str, Any]:
    """Build a minimal run report around the given result rows."""
    return {
        "schema": REPORT_SCHEMA,
        "k": k,
        "golden_version": golden_version,
        "results": list(entries),
    }


def changes(diff: dict[str, Any]) -> list[str]:
    return [row["change"] for row in diff["per_query"]]


# ── change classification ───────────────────────────────────────────────
def test_hit_becoming_a_miss_is_the_only_thing_called_a_regression() -> None:
    baseline = report(entry("L-001", hit=True, rank=1, matched_path="a.py"))
    current = report(entry("L-001", hit=False))
    diff = diff_runs(baseline, current)

    assert diff["schema"] == DIFF_SCHEMA
    assert diff["regression_count"] == 1
    assert diff["change_counts"][CHANGE_REGRESSION] == 1
    assert changes(diff) == [CHANGE_REGRESSION]
    assert diff["per_query"][0]["baseline_matched_path"] == "a.py"
    assert diff["per_query"][0]["current_matched_path"] is None


def test_miss_becoming_a_hit_is_an_improvement_not_a_regression() -> None:
    baseline = report(entry("L-001", hit=False))
    current = report(entry("L-001", hit=True, rank=2, matched_path="b.py"))
    diff = diff_runs(baseline, current)

    assert diff["improvement_count"] == 1
    assert diff["regression_count"] == 0
    assert changes(diff) == [CHANGE_IMPROVEMENT]


def test_rank_moves_among_hits_are_reported_separately() -> None:
    baseline = report(
        entry("up", hit=True, rank=5),
        entry("down", hit=True, rank=2),
        entry("same", hit=True, rank=3),
    )
    current = report(
        entry("up", hit=True, rank=2),
        entry("down", hit=True, rank=4),
        entry("same", hit=True, rank=3),
    )
    diff = diff_runs(baseline, current)

    assert changes(diff) == [CHANGE_RANK_IMPROVED, CHANGE_RANK_REGRESSED, CHANGE_UNCHANGED]
    assert diff["regression_count"] == 0
    assert diff["change_counts"][CHANGE_RANK_IMPROVED] == 1
    assert diff["change_counts"][CHANGE_RANK_REGRESSED] == 1
    assert diff["change_counts"][CHANGE_UNCHANGED] == 1


def test_both_sides_miss_is_unchanged() -> None:
    diff = diff_runs(report(entry("L-001", hit=False)), report(entry("L-001", hit=False)))
    assert changes(diff) == [CHANGE_UNCHANGED]


def test_a_hit_without_a_rank_is_still_a_hit() -> None:
    """A missing rank must not be read as a rank of zero."""
    diff = diff_runs(
        report(entry("L-001", hit=True)),
        report(entry("L-001", hit=False)),
    )
    assert diff["regression_count"] == 1
    diff2 = diff_runs(report(entry("L-001", hit=True)), report(entry("L-001", hit=True)))
    assert changes(diff2) == [CHANGE_UNCHANGED]


# ── one-sided queries and rates ─────────────────────────────────────────
def test_queries_present_on_one_side_are_listed_but_never_counted() -> None:
    baseline = report(entry("A", hit=True, rank=1), entry("B", hit=True, rank=1))
    current = report(entry("A", hit=True, rank=1), entry("C", hit=True, rank=1))
    diff = diff_runs(baseline, current)

    assert diff["only_in_baseline"] == ["B"]
    assert diff["only_in_current"] == ["C"]
    assert diff["compared"] == 1
    assert diff["regression_count"] == 0


def test_rates_are_computed_over_the_compared_set_only() -> None:
    """A query that exists on one side alone must not move the rate."""
    baseline = report(entry("A", hit=True, rank=1), entry("B", hit=True, rank=1))
    current = report(entry("A", hit=True, rank=1))  # B was dropped from the set
    diff = diff_runs(baseline, current)

    assert diff["rates"]["n"] == 1
    assert diff["rates"]["baseline_hit_rate"] == 1.0
    assert diff["rates"]["current_hit_rate"] == 1.0
    assert diff["rates"]["delta"] == 0.0


def test_rates_are_layered_by_class() -> None:
    baseline = report(
        entry("A", task_class="exact", hit=True, rank=1),
        entry("B", task_class="natural", hit=False),
    )
    current = report(
        entry("A", task_class="exact", hit=False),
        entry("B", task_class="natural", hit=True, rank=1),
    )
    rates = diff_runs(baseline, current)["rates"]

    assert rates["baseline_hit_rate"] == 0.5
    assert rates["current_hit_rate"] == 0.5
    assert rates["delta"] == 0.0
    assert rates["by_class"]["exact"] == {
        "n": 1,
        "baseline_hit_rate": 1.0,
        "current_hit_rate": 0.0,
    }
    assert rates["by_class"]["natural"]["current_hit_rate"] == 1.0
    assert rates["by_class"]["crossfile"]["n"] == 0
    assert rates["by_class"]["crossfile"]["baseline_hit_rate"] is None


def test_per_query_follows_baseline_order() -> None:
    baseline = report(entry("L-003", hit=True), entry("L-001", hit=True), entry("L-002", hit=True))
    current = report(entry("L-003", hit=True), entry("L-001", hit=True), entry("L-002", hit=True))
    assert [row["id"] for row in diff_runs(baseline, current)["per_query"]] == [
        "L-003",
        "L-001",
        "L-002",
    ]


# ── input validation ────────────────────────────────────────────────────
def test_a_different_k_is_rejected() -> None:
    with pytest.raises(ReportDiffError, match="k 不一致"):
        diff_runs(report(entry("A", hit=True), k=5), report(entry("A", hit=True), k=10))


def test_a_non_run_report_is_rejected() -> None:
    with pytest.raises(ReportDiffError, match="schema"):
        diff_runs({"schema": "something-else", "k": 5, "results": []}, report())


def test_a_missing_results_list_is_rejected() -> None:
    with pytest.raises(ReportDiffError, match="results"):
        diff_runs({"schema": REPORT_SCHEMA, "k": 5}, report())


def test_a_malformed_result_row_is_rejected() -> None:
    bad = {"schema": REPORT_SCHEMA, "k": 5, "results": [{"hit": True}]}
    with pytest.raises(ReportDiffError, match="非法条目"):
        diff_runs(bad, report())


# ── gate on the regression count ────────────────────────────────────────
def test_gate_fails_on_a_single_regression_by_default() -> None:
    assert MAX_REGRESSIONS_DEFAULT == 0
    baseline = report(entry("A", hit=True, rank=1))
    current = report(entry("A", hit=False))
    verdict = gate_diff(diff_runs(baseline, current))

    assert verdict["regression_count"] == 1
    assert verdict["active_regressions"] == ["A"]
    assert verdict["passed"] is False


def test_gate_passes_when_nothing_regressed() -> None:
    baseline = report(entry("A", hit=True, rank=1))
    current = report(entry("A", hit=True, rank=3))
    assert gate_diff(diff_runs(baseline, current))["passed"] is True


def test_a_rising_mean_does_not_rescue_regressions() -> None:
    """The case EVAL.md 2.7 is about: mean up, individual queries broken."""
    baseline = report(
        entry("R1", hit=True, rank=1),
        entry("R2", hit=True, rank=1),
        entry("I1", hit=False),
        entry("I2", hit=False),
        entry("I3", hit=False),
    )
    current = report(
        entry("R1", hit=False),
        entry("R2", hit=False),
        entry("I1", hit=True, rank=1),
        entry("I2", hit=True, rank=1),
        entry("I3", hit=True, rank=1),
    )
    diff = diff_runs(baseline, current)
    verdict = gate_diff(diff)

    assert diff["rates"]["baseline_hit_rate"] == 0.4
    assert diff["rates"]["current_hit_rate"] == 0.6  # mean went *up*
    assert diff["regression_count"] == 2
    assert verdict["passed"] is False


def test_waivers_keep_a_regression_visible_but_not_fatal() -> None:
    baseline = report(entry("A", hit=True, rank=1), entry("B", hit=True, rank=1))
    current = report(entry("A", hit=False), entry("B", hit=True, rank=1))
    verdict = gate_diff(diff_runs(baseline, current), waivers=["A"])

    assert verdict["regression_count"] == 1
    assert verdict["waived_regressions"] == ["A"]
    assert verdict["active_regressions"] == []
    assert verdict["passed"] is True


def test_a_waiver_that_matches_nothing_is_surfaced() -> None:
    baseline = report(entry("A", hit=True, rank=1))
    current = report(entry("A", hit=True, rank=1))
    verdict = gate_diff(diff_runs(baseline, current), waivers=["NOPE"])

    assert verdict["unused_waivers"] == ["NOPE"]
    assert verdict["passed"] is True


def test_max_regressions_can_be_raised_explicitly() -> None:
    baseline = report(entry("A", hit=True, rank=1), entry("B", hit=True, rank=1))
    current = report(entry("A", hit=False), entry("B", hit=False))
    diff = diff_runs(baseline, current)

    assert gate_diff(diff)["passed"] is False
    assert gate_diff(diff, max_regressions=1)["passed"] is False
    assert gate_diff(diff, max_regressions=2)["passed"] is True


def test_gate_rejects_a_negative_tolerance() -> None:
    diff = diff_runs(report(entry("A", hit=True)), report(entry("A", hit=True)))
    with pytest.raises(ReportDiffError, match="max_regressions"):
        gate_diff(diff, max_regressions=-1)


def test_gate_rejects_something_that_is_not_a_diff() -> None:
    with pytest.raises(ReportDiffError, match="diff 报告"):
        gate_diff({"schema": REPORT_SCHEMA, "results": []})


# ── markdown ────────────────────────────────────────────────────────────
def test_markdown_lists_each_regression_and_the_verdict() -> None:
    baseline = report(entry("L-002", hit=True, rank=3, matched_path="x.py", query="令牌在哪"))
    current = report(entry("L-002", hit=False, query="令牌在哪"))
    diff = diff_runs(baseline, current)
    text = render_diff_markdown(diff, gate_diff(diff))

    assert "门禁：FAIL" in text
    assert "## 回归（命中 → 未命中）" in text
    assert "L-002" in text
    assert "令牌在哪" in text
    assert "#3 (x.py)" in text
    assert "| query | 类 | baseline | current | 变化 |" in text


def test_markdown_says_pass_and_flags_unused_waivers() -> None:
    diff = diff_runs(report(entry("A", hit=True)), report(entry("A", hit=True)))
    text = render_diff_markdown(diff, gate_diff(diff, waivers=["NOPE"]))

    assert "门禁：PASS" in text
    assert "未匹配到任何回归的 waiver" in text
    assert "## 回归" not in text


# ── golden_version provenance ───────────────────────────────────────────
def test_build_report_records_the_golden_version() -> None:
    run = EvalRun(
        corpus_root=Path("/tmp/anywhere"), k=5, results=(), golden_version="m3-b1"
    )
    assert build_report(run)["golden_version"] == "m3-b1"

    unpinned = EvalRun(corpus_root=Path("/tmp/anywhere"), k=5, results=())
    assert build_report(unpinned)["golden_version"] is None


def test_a_matching_golden_version_is_reported_as_a_match() -> None:
    diff = diff_runs(report(entry("A", hit=True)), report(entry("A", hit=True)))

    assert diff["golden_version"] == {
        "baseline": "m3-b1",
        "current": "m3-b1",
        "match": True,
    }
    assert gate_diff(diff)["passed"] is True


def test_a_golden_version_mismatch_fails_the_gate_with_no_regression_at_all() -> None:
    baseline = report(entry("A", hit=True), golden_version="m3-b1")
    current = report(entry("A", hit=True), golden_version="m3-b2")
    diff = diff_runs(baseline, current)
    verdict = gate_diff(diff)

    assert diff["regression_count"] == 0
    assert diff["golden_version"]["match"] is False
    assert verdict["passed"] is False
    assert any("golden_version 不一致" in reason for reason in verdict["reasons"])


def test_missing_versions_are_not_treated_as_a_mismatch() -> None:
    """Absent metadata is not verification, so it must not read as a mismatch."""
    baseline = report(entry("A", hit=True), golden_version=None)
    current = report(entry("A", hit=True), golden_version="m3-b1")
    diff = diff_runs(baseline, current)
    verdict = gate_diff(diff)

    assert diff["golden_version"]["match"] is None
    assert verdict["golden_version_match"] is None
    assert verdict["passed"] is True


def test_markdown_flags_a_golden_version_mismatch() -> None:
    diff = diff_runs(
        report(entry("A", hit=True), golden_version="m3-b1"),
        report(entry("A", hit=True), golden_version="m3-b2"),
    )
    text = render_diff_markdown(diff, gate_diff(diff))

    assert "golden_version：m3-b1 → m3-b2" in text
    assert "题集不同" in text
    assert "门禁：FAIL" in text
