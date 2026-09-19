"""Retrieval-quality metrics for the L1 evaluation (EVAL.md 2.5-2.7).

This module turns per-task `EvalResult` rows into aggregate numbers:
Success@k (overall and per class), MRR, the median token estimate and Wilson
confidence intervals. It is pure arithmetic over already-collected results —
it never searches, never reads the index and never calls a model, so it can be
verified against hand-built samples.

Aggregation is a macro-average (every query counts once), as EVAL.md 2.7
requires. `must_not_paths` and `expect_symbols` are folded in at each k: a
task that violates either is a miss even when a target path was returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist, median

from dsh_coderag.eval.runner import EvalResult, EvalRun
from dsh_coderag.eval.tasks import TASK_CLASSES

DEFAULT_KS: tuple[int, ...] = (1, 3, 5)
"""Cut-offs reported by default; 5 must equal the k the model actually sees."""

DEFAULT_CONFIDENCE = 0.95
"""Confidence level for the Wilson interval."""


@dataclass(frozen=True)
class Interval:
    """A closed confidence interval on a proportion, clamped to [0, 1]."""

    low: float
    high: float


@dataclass(frozen=True)
class MetricSet:
    """Metrics for one bucket (the whole run or one task class).

    `hits[k]` is always present for every requested k. `success[k]` and
    `intervals[k]` are None when the bucket holds no tasks — an undefined
    proportion is reported as None, never as 0.0. `mrr` and `token_median`
    are likewise None for an empty bucket.
    """

    name: str
    total: int
    k: int
    hits: dict[int, int]
    success: dict[int, float | None]
    intervals: dict[int, Interval | None]
    mrr: float | None
    token_median: float | None


def is_hit_at(result: EvalResult, k: int) -> bool:
    """Whether this task counts as a hit within the first k returned hits.

    Requires a target path at position <= k, no `must_not_paths` entry inside
    that prefix, and no declared `expect_symbols` entry missing. Positions come
    from the returned list, which ADR-05 puts in source order.
    """
    if result.symbol_hit is False:
        return False
    if result.rank is None or result.rank > k:
        return False
    offending = set(result.must_not_hit)
    return not (
        offending and any(path in offending for path in result.returned_paths[:k])
    )


def count_hits(results: Sequence[EvalResult], k: int) -> int:
    """Number of tasks that are a hit within the first k returned hits."""
    return sum(1 for result in results if is_hit_at(result, k))


def success_at_k(results: Sequence[EvalResult], k: int) -> float | None:
    """Success@k = hits / total; None when there are no tasks."""
    if not results:
        return None
    return count_hits(results, k) / len(results)


def mean_reciprocal_rank(results: Sequence[EvalResult], k: int) -> float | None:
    """Mean of 1/rank of the best target hit within k; misses contribute 0."""
    if not results:
        return None
    total = 0.0
    for result in results:
        if is_hit_at(result, k) and result.rank is not None:
            total += 1.0 / result.rank
    return total / len(results)


def median_tokens(results: Sequence[EvalResult]) -> float | None:
    """Median of the per-query token estimates; None for an empty bucket."""
    if not results:
        return None
    return float(median([result.token_estimate for result in results]))


def wilson_interval(
    successes: int,
    total: int,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Interval | None:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because it stays inside [0, 1] and
    behaves at 0/n and n/n, which is exactly where a 10-30 task set lands
    (EVAL.md 2.6). Returns None when total is 0.

    Raises:
        ValueError: If total is negative, successes is outside [0, total], or
            confidence is not strictly between 0 and 1.
    """
    if total < 0 or not 0 <= successes <= total:
        raise ValueError(f"successes/total 非法：{successes}/{total}")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence 必须在 (0, 1)：{confidence}")
    if total == 0:
        return None
    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * ((proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)) ** 0.5)
        / denominator
    )
    return Interval(low=max(0.0, center - margin), high=min(1.0, center + margin))


def compute_metrics(
    results: Sequence[EvalResult],
    *,
    name: str,
    k: int,
    ks: Sequence[int] = DEFAULT_KS,
    confidence: float = DEFAULT_CONFIDENCE,
) -> MetricSet:
    """Compute every metric for one bucket.

    `k` is the run's cut-off and is what MRR uses; `ks` are the Success@k
    cut-offs to report. A cut-off above `k` is still reported but cannot hit,
    since no result in the run was retrieved beyond k.
    """
    hits = {cutoff: count_hits(results, cutoff) for cutoff in ks}
    success: dict[int, float | None] = {}
    intervals: dict[int, Interval | None] = {}
    for cutoff in ks:
        if not results:
            success[cutoff] = None
            intervals[cutoff] = None
        else:
            success[cutoff] = hits[cutoff] / len(results)
            intervals[cutoff] = wilson_interval(hits[cutoff], len(results), confidence)
    return MetricSet(
        name=name,
        total=len(results),
        k=k,
        hits=hits,
        success=success,
        intervals=intervals,
        mrr=mean_reciprocal_rank(results, k),
        token_median=median_tokens(results),
    )


def layered_metrics(
    run: EvalRun,
    *,
    ks: Sequence[int] = DEFAULT_KS,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict[str, MetricSet]:
    """Compute metrics for the whole run and for every task class.

    The returned dict always starts with the ``overall`` key followed by the
    classes in `TASK_CLASSES` order, so callers can report stratified numbers
    without recomputing them (EVAL.md 2.7: a single combined number has no
    diagnostic value).
    """
    results = list(run.results)
    layered: dict[str, MetricSet] = {
        "overall": compute_metrics(
            results, name="overall", k=run.k, ks=ks, confidence=confidence
        )
    }
    for task_class in TASK_CLASSES:
        subset = [result for result in results if result.task_class == task_class]
        layered[task_class] = compute_metrics(
            subset, name=task_class, k=run.k, ks=ks, confidence=confidence
        )
    return layered
