"""Serialize an eval run, and diff two runs query by query (EVAL.md 2.7).

`build_report` turns an `EvalRun` into a plain JSON-serializable dict that lists
every task's outcome plus raw hit/miss counts per class.

`diff_runs` compares two such reports **per query** and counts regressions;
`gate_diff` turns that count into a pass/fail verdict, optionally waiving
individual queries; `render_diff_markdown` renders both for a human.

EVAL.md 2.7 requires the gate to look at the regression count rather than the
mean alone, because a change can lift the average while quietly breaking
individual queries.

What this module does not do: it computes no Success@k / MRR / confidence
interval (that is `metrics`), no failure attribution (that is `attribute`), and
no `golden_version` check (that is `runner`, T3-04d).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dsh_coderag.eval.runner import EvalResult, EvalRun
from dsh_coderag.eval.tasks import TASK_CLASSES, EvalError

REPORT_SCHEMA = "dsh-coderag/eval-run/v1"
DIFF_SCHEMA = "dsh-coderag/eval-diff/v1"

CHANGE_REGRESSION = "regression"
CHANGE_IMPROVEMENT = "improvement"
CHANGE_RANK_IMPROVED = "rank_improved"
CHANGE_RANK_REGRESSED = "rank_regressed"
CHANGE_UNCHANGED = "unchanged"

CHANGE_KINDS = (
    CHANGE_REGRESSION,
    CHANGE_IMPROVEMENT,
    CHANGE_RANK_IMPROVED,
    CHANGE_RANK_REGRESSED,
    CHANGE_UNCHANGED,
)

MAX_REGRESSIONS_DEFAULT = 0
"""Unwaived regressions tolerated by default.

EVAL.md 2.7 quotes the industry starting point "two regressions fail the gate",
then states this project must be **stricter** because 10-30 queries make a
single flip worth 3.3-10 points. The L2 gate in `ab` already fails on any
regression, so this module tolerates none by default; pass a larger
`max_regressions` to adopt the looser rule explicitly.
"""


class ReportDiffError(EvalError):
    """A report is not a valid run report, or two reports cannot be compared."""


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
        "golden_version": run.golden_version,
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


@dataclass(frozen=True)
class QueryDiff:
    """One query's outcome before and after, with its derived change kind."""

    task_id: str
    task_class: str
    query: str
    baseline_hit: bool
    current_hit: bool
    baseline_rank: int | None
    current_rank: int | None
    baseline_matched_path: str | None
    current_matched_path: str | None

    @property
    def change(self) -> str:
        """Classify the change between the two outcomes.

        A hit that becomes a miss is the only thing called a regression; a
        worse rank among hits is a separate, weaker signal.
        """
        if self.baseline_hit and not self.current_hit:
            return CHANGE_REGRESSION
        if self.current_hit and not self.baseline_hit:
            return CHANGE_IMPROVEMENT
        if self.baseline_hit and self.current_hit:
            if self.baseline_rank is None or self.current_rank is None:
                return CHANGE_UNCHANGED
            if self.current_rank < self.baseline_rank:
                return CHANGE_RANK_IMPROVED
            if self.current_rank > self.baseline_rank:
                return CHANGE_RANK_REGRESSED
        return CHANGE_UNCHANGED

    def to_json(self) -> dict[str, Any]:
        """Return the JSON-serializable form recorded in the diff report."""
        return {
            "id": self.task_id,
            "class": self.task_class,
            "query": self.query,
            "baseline_hit": self.baseline_hit,
            "current_hit": self.current_hit,
            "baseline_rank": self.baseline_rank,
            "current_rank": self.current_rank,
            "baseline_matched_path": self.baseline_matched_path,
            "current_matched_path": self.current_matched_path,
            "change": self.change,
        }


def diff_runs(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two run reports query by query and count regressions.

    Only queries present on **both** sides are compared; those present on one
    side alone are listed separately and never counted as a regression, because
    there is nothing to compare them against. Rates are computed over the
    compared set only, so a query that only exists on one side cannot move them.

    Raises:
        ReportDiffError: If either report is not a run report, or the two use
            different `k` (ranks from different cut-offs are not comparable).
    """
    baseline_results = _run_results(baseline, "baseline")
    current_results = _run_results(current, "current")
    baseline_k = baseline.get("k")
    current_k = current.get("k")
    if baseline_k != current_k:
        raise ReportDiffError(
            f"k 不一致（baseline={baseline_k!r}, current={current_k!r}）：排名不可比"
        )
    current_by_id = {str(entry["id"]): entry for entry in current_results}
    baseline_by_id = {str(entry["id"]): entry for entry in baseline_results}

    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    diffs: list[QueryDiff] = []
    for entry in baseline_results:
        other = current_by_id.get(str(entry["id"]))
        if other is None:
            continue
        pairs.append((entry, other))
        diffs.append(_query_diff(entry, other))

    per_query = [diff.to_json() for diff in diffs]
    change_counts = {kind: sum(1 for diff in diffs if diff.change == kind) for kind in CHANGE_KINDS}
    return {
        "schema": DIFF_SCHEMA,
        "k": baseline_k,
        "compared": len(diffs),
        "change_counts": change_counts,
        "regression_count": change_counts[CHANGE_REGRESSION],
        "improvement_count": change_counts[CHANGE_IMPROVEMENT],
        "golden_version": _version_comparison(baseline, current),
        "only_in_baseline": sorted(set(baseline_by_id) - set(current_by_id)),
        "only_in_current": sorted(set(current_by_id) - set(baseline_by_id)),
        "rates": _rates(pairs),
        "per_query": per_query,
    }


def _diff_regression_ids(per_query: list[Any]) -> list[str]:
    """Return the ids that regressed (hit -> miss) in a diff report."""
    return [
        str(entry["id"])
        for entry in per_query
        if isinstance(entry, Mapping) and entry.get("change") == CHANGE_REGRESSION
    ]


def _gate_reasons(
    version_match: Any, active_count: int, max_regressions: int
) -> list[str]:
    """Explain why the gate fails, if it does."""
    reasons: list[str] = []
    if version_match is False:
        reasons.append(
            "golden_version 不一致：两份报告跑的不是同一份题集，逐条对比无效"
            "（EVAL.md 2.7：改题集必须同步升版本号）"
        )
    if active_count > max_regressions:
        reasons.append(f"未豁免回归 {active_count} 条 > 容忍 {max_regressions}")
    return reasons


def gate_diff(
    diff: Mapping[str, Any],
    *,
    waivers: Sequence[str] = (),
    max_regressions: int = MAX_REGRESSIONS_DEFAULT,
) -> dict[str, Any]:
    """Turn a query diff into a verdict keyed on the regression count.

    `waivers` lists task ids whose regression a human has explicitly accepted
    and explained (EVAL.md 2.7 allows that escape hatch). Waived regressions are
    still reported; they just do not fail the gate. A waiver that matches no
    actual regression is surfaced as `unused_waivers` rather than silently
    ignored.

    Raises:
        ReportDiffError: If `max_regressions` is negative or the diff is not a
            diff report.
    """
    if max_regressions < 0:
        raise ReportDiffError(f"max_regressions 必须 ≥ 0，实际 {max_regressions}")
    per_query = diff.get("per_query")
    if diff.get("schema") != DIFF_SCHEMA or not isinstance(per_query, list):
        raise ReportDiffError(f"不是一份 diff 报告：schema={diff.get('schema')!r}")
    regressed = _diff_regression_ids(per_query)
    waiver_set = set(waivers)
    waived = [task_id for task_id in regressed if task_id in waiver_set]
    active = [task_id for task_id in regressed if task_id not in waiver_set]
    version = diff.get("golden_version")
    version_match = version.get("match") if isinstance(version, Mapping) else None
    reasons = _gate_reasons(version_match, len(active), max_regressions)
    return {
        "schema": DIFF_SCHEMA,
        "regression_count": len(regressed),
        "waived_regressions": waived,
        "active_regressions": active,
        "unused_waivers": sorted(waiver_set - set(regressed)),
        "golden_version_match": version_match,
        "max_regressions": max_regressions,
        "reasons": reasons,
        "passed": not reasons,
    }


def _version_note(version: Mapping[str, Any]) -> str:
    """Explain the golden_version comparison as one short suffix."""
    if version.get("match") is False:
        return " ｜ ⚠️ 不一致：两份报告的题集不同，逐条对比无效"
    if version.get("match") is None:
        return " ｜ （至少一份报告缺版本号，未能核验）"
    return ""


def _diff_summary(
    diff: Mapping[str, Any],
    verdict: Mapping[str, Any],
    rates: Mapping[str, Any],
    counts: Mapping[str, Any],
    version: Mapping[str, Any],
) -> list[str]:
    """Build the header bullets: counts, versions, rates and the verdict."""
    lines = [
        "# L1 逐 query diff",
        "",
        f"- 对比条数：{diff.get('compared')}（k={diff.get('k')}）",
        f"- golden_version：{version.get('baseline')} → {version.get('current')}"
        f"{_version_note(version)}",
        f"- 命中率：{_rate(rates.get('baseline_hit_rate'))} → "
        f"{_rate(rates.get('current_hit_rate'))}（{_pp(rates.get('delta'))}）",
        f"- 回归：{diff.get('regression_count')} ｜ 改善：{diff.get('improvement_count')} ｜ "
        f"名次变好：{counts.get(CHANGE_RANK_IMPROVED)} ｜ "
        f"名次变差：{counts.get(CHANGE_RANK_REGRESSED)}",
        f"- 门禁：{'PASS' if verdict.get('passed') else 'FAIL'}"
        f"（未豁免回归 {len(verdict.get('active_regressions', []))} 条，"
        f"容忍 {verdict.get('max_regressions')}）",
    ]
    lines += [f"  - {reason}" for reason in verdict.get("reasons", [])]
    if diff.get("only_in_baseline") or diff.get("only_in_current"):
        lines.append(
            f"- 仅单侧存在：baseline {diff.get('only_in_baseline')} ｜ "
            f"current {diff.get('only_in_current')}"
        )
    return lines


def _change_sections(diff: Mapping[str, Any]) -> list[str]:
    """Build the regression and improvement sections from the per-query rows."""
    lines: list[str] = []
    for change, title in (
        (CHANGE_REGRESSION, "## 回归（命中 → 未命中）"),
        (CHANGE_IMPROVEMENT, "## 改善（未命中 → 命中）"),
    ):
        entries = [
            entry for entry in diff.get("per_query", []) if entry["change"] == change
        ]
        if entries:
            lines += ["", title, ""]
            lines += [_describe(entry) for entry in entries]
    return lines


def _verdict_sections(verdict: Mapping[str, Any]) -> list[str]:
    """Build the waived-regression section and the unused-waiver note."""
    lines: list[str] = []
    if verdict.get("waived_regressions"):
        lines += ["", "## 已豁免的回归（需人工说明）", ""]
        lines += [f"- {task_id}" for task_id in verdict["waived_regressions"]]
    if verdict.get("unused_waivers"):
        lines += ["", f"- ⚠️ 未匹配到任何回归的 waiver：{verdict['unused_waivers']}"]
    return lines


def _comparison_table(diff: Mapping[str, Any]) -> list[str]:
    """Build the per-query comparison table."""
    lines = [
        "",
        "## 逐条对比",
        "",
        "| query | 类 | baseline | current | 变化 |",
        "|---|---|---|---|---|",
    ]
    for entry in diff.get("per_query", []):
        lines.append(
            f"| {entry['id']} | {entry['class']} | {_side(entry, 'baseline')} "
            f"| {_side(entry, 'current')} | {entry['change']} |"
        )
    lines.append("")
    return lines


def render_diff_markdown(diff: Mapping[str, Any], verdict: Mapping[str, Any]) -> str:
    """Render a query diff and its gate verdict as Markdown."""
    rates = diff.get("rates")
    rates = rates if isinstance(rates, Mapping) else {}
    counts = diff.get("change_counts")
    counts = counts if isinstance(counts, Mapping) else {}
    version = diff.get("golden_version")
    version = version if isinstance(version, Mapping) else {}
    lines = _diff_summary(diff, verdict, rates, counts, version)
    lines += _change_sections(diff)
    lines += _verdict_sections(verdict)
    lines += _comparison_table(diff)
    return "\n".join(lines)


def _side(entry: Mapping[str, Any], prefix: str) -> str:
    if not entry.get(f"{prefix}_hit"):
        return "miss"
    rank = entry.get(f"{prefix}_rank")
    path = entry.get(f"{prefix}_matched_path")
    return f"hit #{rank} ({path})"


def _describe(entry: Mapping[str, Any]) -> str:
    return (
        f"- **{entry['id']}**（{entry['class']}）："
        f"{_side(entry, 'baseline')} → {_side(entry, 'current')} ｜ {entry['query']}"
    )


def _rates(pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, Any]:
    """Hit rates over the compared pairs, overall and per class."""
    baseline_entries = [before for before, _ in pairs]
    current_entries = [after for _, after in pairs]
    baseline_rate = _hit_rate(baseline_entries)
    current_rate = _hit_rate(current_entries)
    class_rates: dict[str, dict[str, Any]] = {}
    for task_class in TASK_CLASSES:
        class_pairs = [
            (before, after)
            for before, after in pairs
            if before.get("class") == task_class
        ]
        class_rates[task_class] = {
            "n": len(class_pairs),
            "baseline_hit_rate": _hit_rate([before for before, _ in class_pairs]),
            "current_hit_rate": _hit_rate([after for _, after in class_pairs]),
        }
    return {
        "n": len(pairs),
        "baseline_hit_rate": baseline_rate,
        "current_hit_rate": current_rate,
        "delta": (
            current_rate - baseline_rate
            if baseline_rate is not None and current_rate is not None
            else None
        ),
        "by_class": class_rates,
    }


def _version_comparison(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare the golden versions the two reports ran against.

    `match` is None when either report predates the field: absent metadata is
    not evidence of a mismatch, but it is also not verification.
    """
    baseline_version = _optional_str(baseline.get("golden_version"))
    current_version = _optional_str(current.get("golden_version"))
    match: bool | None = None
    if baseline_version is not None and current_version is not None:
        match = baseline_version == current_version
    return {"baseline": baseline_version, "current": current_version, "match": match}


def _hit_rate(entries: Sequence[Mapping[str, Any]]) -> float | None:
    if not entries:
        return None
    return sum(1 for entry in entries if entry.get("hit") is True) / len(entries)


def _run_results(report: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    if report.get("schema") != REPORT_SCHEMA:
        raise ReportDiffError(
            f"{label}: schema 期望 {REPORT_SCHEMA!r}，实际 {report.get('schema')!r}"
        )
    results = report.get("results")
    if not isinstance(results, list):
        raise ReportDiffError(f"{label}: 缺少 results 列表")
    checked: list[Mapping[str, Any]] = []
    for entry in results:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("id"), str):
            raise ReportDiffError(f"{label}: results 含非法条目 {entry!r}")
        checked.append(entry)
    return checked


def _query_diff(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> QueryDiff:
    return QueryDiff(
        task_id=str(baseline["id"]),
        task_class=str(baseline.get("class", "")),
        query=str(baseline.get("query", "")),
        baseline_hit=baseline.get("hit") is True,
        current_hit=current.get("hit") is True,
        baseline_rank=_rank(baseline.get("rank")),
        current_rank=_rank(current.get("rank")),
        baseline_matched_path=_optional_str(baseline.get("matched_path")),
        current_matched_path=_optional_str(current.get("matched_path")),
    )


def _rank(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


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


def _rate(value: Any) -> str:
    return "n/a" if not isinstance(value, (int, float)) else f"{float(value):.3f}"


def _pp(value: Any) -> str:
    return "n/a" if not isinstance(value, (int, float)) else f"{float(value) * 100:+.1f}pp"
