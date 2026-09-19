"""Tests for L1 metrics (T3-04).

Every expected number is computed by hand in the test, not by re-running the
implementation, so the arithmetic itself is what is under test. No corpus and
no index are needed: metrics are pure functions over `EvalResult` rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.eval.metrics import (
    DEFAULT_KS,
    Interval,
    compute_metrics,
    count_hits,
    is_hit_at,
    layered_metrics,
    mean_reciprocal_rank,
    median_tokens,
    success_at_k,
    wilson_interval,
)
from dsh_coderag.eval.runner import EvalResult, EvalRun


def make_result(
    rank: int | None,
    *,
    task_class: str = "exact",
    returned: tuple[str, ...] = (),
    must_not: tuple[str, ...] = (),
    symbol_hit: bool | None = None,
    tokens: int = 0,
    task_id: str = "L-001",
) -> EvalResult:
    """Build one result row; only the fields a test exercises are meaningful."""
    return EvalResult(
        task_id=task_id,
        task_class=task_class,
        query="q",
        status="ready",
        hit=rank is not None,
        matched_path=None,
        rank=rank,
        returned_paths=returned,
        must_not_hit=must_not,
        symbol_hit=symbol_hit,
        token_estimate=tokens,
        error=None,
    )


# ── Success@k ───────────────────────────────────────────────────────────
def test_success_at_k_counts_hits_within_cutoff() -> None:
    results = [
        make_result(1),
        make_result(3),
        make_result(None),
        make_result(6),
    ]
    assert success_at_k(results, 1) == 0.25
    assert success_at_k(results, 3) == 0.5
    assert success_at_k(results, 5) == 0.5
    assert success_at_k(results, 6) == 0.75


def test_rank_equal_to_cutoff_is_a_hit_and_one_past_is_not() -> None:
    assert is_hit_at(make_result(5), 5) is True
    assert is_hit_at(make_result(6), 5) is False


def test_target_must_have_been_returned() -> None:
    assert is_hit_at(make_result(None), 5) is False


def test_must_not_path_only_fails_inside_the_cutoff() -> None:
    result = make_result(1, returned=("a.py", "b.py", "c.py"), must_not=("c.py",))
    assert is_hit_at(result, 2) is True
    assert is_hit_at(result, 3) is False


def test_missing_declared_symbol_is_a_miss_at_every_cutoff() -> None:
    result = make_result(1, symbol_hit=False)
    assert is_hit_at(result, 1) is False
    assert is_hit_at(result, 5) is False


def test_success_at_k_is_none_for_an_empty_bucket() -> None:
    assert success_at_k([], 5) is None
    assert count_hits([], 5) == 0


# ── MRR ─────────────────────────────────────────────────────────────────
def test_mean_reciprocal_rank_hand_computed() -> None:
    # (1/1 + 1/2 + 0 + 1/4) / 4
    results = [make_result(1), make_result(2), make_result(None), make_result(4)]
    assert mean_reciprocal_rank(results, 5) == pytest.approx(0.4375)


def test_mean_reciprocal_rank_ignores_ranks_beyond_the_cutoff() -> None:
    results = [make_result(1), make_result(2), make_result(6)]
    assert mean_reciprocal_rank(results, 5) == pytest.approx(0.5)


def test_mean_reciprocal_rank_is_zero_when_must_not_is_violated() -> None:
    result = make_result(1, returned=("bad.py",), must_not=("bad.py",))
    assert mean_reciprocal_rank([result], 5) == 0.0


def test_mean_reciprocal_rank_is_none_for_an_empty_bucket() -> None:
    assert mean_reciprocal_rank([], 5) is None


# ── token median ────────────────────────────────────────────────────────
def test_median_tokens_odd_count() -> None:
    results = [make_result(1, tokens=10), make_result(2, tokens=30), make_result(3, tokens=20)]
    assert median_tokens(results) == 20.0


def test_median_tokens_even_count_averages_the_middle() -> None:
    results = [make_result(1, tokens=t) for t in (10, 20, 30, 40)]
    assert median_tokens(results) == 25.0


def test_median_tokens_is_none_for_an_empty_bucket() -> None:
    assert median_tokens([]) is None


# ── Wilson interval ─────────────────────────────────────────────────────
def test_wilson_interval_matches_the_evals_documented_example() -> None:
    # EVAL.md 2.6: 24/30 -> 0.800 (95% CI ~ [0.63, 0.90])
    interval = wilson_interval(24, 30)
    assert interval is not None
    assert interval.low == pytest.approx(0.626943, abs=1e-6)
    assert interval.high == pytest.approx(0.904949, abs=1e-6)
    assert (round(interval.low, 2), round(interval.high, 2)) == (0.63, 0.90)


def test_wilson_interval_stays_inside_zero_and_one_at_the_boundaries() -> None:
    none_hit = wilson_interval(0, 10)
    all_hit = wilson_interval(10, 10)
    assert none_hit is not None and all_hit is not None
    assert none_hit.low == 0.0
    assert none_hit.high == pytest.approx(0.277533, abs=1e-6)
    assert all_hit.high == 1.0
    assert all_hit.low == pytest.approx(0.722467, abs=1e-6)


def test_wilson_interval_is_none_without_samples() -> None:
    assert wilson_interval(0, 0) is None


def test_wilson_interval_narrows_with_lower_confidence() -> None:
    wide = wilson_interval(24, 30, confidence=0.95)
    narrow = wilson_interval(24, 30, confidence=0.90)
    assert wide is not None and narrow is not None
    assert narrow.low > wide.low
    assert narrow.high < wide.high


@pytest.mark.parametrize(
    "successes, total, confidence",
    [(31, 30, 0.95), (-1, 30, 0.95), (1, 0, 0.95), (1, 2, 0.0), (1, 2, 1.0)],
)
def test_wilson_interval_rejects_illegal_inputs(
    successes: int, total: int, confidence: float
) -> None:
    with pytest.raises(ValueError):
        wilson_interval(successes, total, confidence)


# ── metric sets ─────────────────────────────────────────────────────────
def test_compute_metrics_reports_every_cutoff() -> None:
    results = [make_result(1), make_result(4), make_result(None)]
    metrics = compute_metrics(results, name="exact", k=5)
    assert metrics.name == "exact"
    assert metrics.total == 3
    assert metrics.k == 5
    assert set(metrics.hits) == set(DEFAULT_KS)
    assert metrics.hits[1] == 1
    assert metrics.hits[3] == 1
    assert metrics.hits[5] == 2
    assert metrics.success[5] == pytest.approx(2 / 3)
    assert metrics.intervals[5] == wilson_interval(2, 3)
    assert metrics.mrr == pytest.approx((1 + 0.25 + 0) / 3)


def test_compute_metrics_reports_undefined_values_as_none() -> None:
    metrics = compute_metrics([], name="natural", k=5)
    assert metrics.total == 0
    assert metrics.hits == {1: 0, 3: 0, 5: 0}
    assert metrics.success == {1: None, 3: None, 5: None}
    assert metrics.intervals == {1: None, 3: None, 5: None}
    assert metrics.mrr is None
    assert metrics.token_median is None


def test_layered_metrics_covers_overall_then_every_class() -> None:
    results = [
        make_result(1, task_class="exact", tokens=10),
        make_result(5, task_class="exact", tokens=30),
        make_result(None, task_class="crossfile", tokens=20),
        make_result(None, task_class="crossfile", tokens=40),
        make_result(None, task_class="natural", tokens=50),
        make_result(2, task_class="natural", tokens=60),
    ]
    run = EvalRun(corpus_root=Path("/tmp/x"), k=5, results=tuple(results))
    layered = layered_metrics(run)
    assert list(layered) == ["overall", "exact", "crossfile", "natural"]
    assert layered["overall"].total == 6
    assert layered["exact"].total == 2
    assert layered["crossfile"].total == 2
    assert layered["natural"].total == 2
    assert layered["exact"].hits[5] == 2
    assert layered["crossfile"].hits[5] == 0
    assert layered["natural"].hits[5] == 1


def test_layered_overall_is_macro_average_over_queries_not_class_means() -> None:
    """One exact hit plus three natural misses: 1/4 overall, not (1.0+0.0)/2."""
    results = [
        make_result(1, task_class="exact"),
        make_result(None, task_class="natural"),
        make_result(None, task_class="natural"),
        make_result(None, task_class="natural"),
    ]
    run = EvalRun(corpus_root=Path("/tmp/x"), k=5, results=tuple(results))
    layered = layered_metrics(run)
    assert layered["overall"].success[5] == 0.25
    assert layered["exact"].success[5] == 1.0
    assert layered["natural"].success[5] == 0.0


def test_layered_metrics_reports_an_empty_class_as_undefined() -> None:
    run = EvalRun(
        corpus_root=Path("/tmp/x"),
        k=5,
        results=(make_result(1, task_class="exact"),),
    )
    layered = layered_metrics(run)
    assert layered["natural"].total == 0
    assert layered["natural"].success == {1: None, 3: None, 5: None}
    assert layered["natural"].mrr is None


def test_interval_is_a_frozen_value_object() -> None:
    assert Interval(low=0.1, high=0.2) == Interval(low=0.1, high=0.2)
