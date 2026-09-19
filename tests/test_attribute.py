"""Tests for failure attribution (T3-04b).

`classify` is tested purely against hand-built `FailureEvidence`, one case per
code, so the precedence rule is pinned down. `collect_evidence` / `attribute_run`
are tested end-to-end on a tiny indexed corpus under tmp_path (T-03/T-04).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dsh_coderag.eval.attribute import (
    VECTOR_RELEVANT,
    AttributionCode,
    FailureEvidence,
    attribute_run,
    attribution_distribution,
    build_attribution_report,
    classify,
    collect_evidence,
    natural_a5_share,
    query_tokens,
)
from dsh_coderag.eval.runner import run_eval
from dsh_coderag.eval.tasks import EvalTask
from dsh_coderag.indexer import index_sync

CORPUS_FILES = {
    "src/alpha.py": "def alpha_one():\n    return 1\n\n\ndef beta_two():\n    return 2\n",
    "src/other.py": "def verify_token(token):\n    return token\n",
}
SHARED_FILES = {
    "src/a.py": "def shared_word():\n    return 1\n",
    "src/b.py": "def shared_word():\n    return 1\n",
    "src/c.py": "def shared_word():\n    return 1\n",
}


def make_corpus(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A small indexed corpus with two independent declarations in alpha.py."""
    root = make_corpus(tmp_path / "corpus", CORPUS_FILES)
    index_sync(root)
    return root


def make_task(
    query: str,
    expect_paths: tuple[str, ...],
    *,
    task_id: str = "L-001",
    task_class: str = "exact",
    expect_symbols: tuple[str, ...] = (),
) -> EvalTask:
    return EvalTask(
        id=task_id,
        task_class=task_class,
        query=query,
        expect_paths=expect_paths,
        added="2026-09-19",
        expect_symbols=expect_symbols,
    )


def evidence(**overrides: Any) -> FailureEvidence:
    """A baseline 'indexed target, tokens overlap' record; override per test."""
    fields: dict[str, Any] = {
        "task_id": "L-001",
        "task_class": "exact",
        "query": "q",
        "run_k": 5,
        "probe_k": 50,
        "expect_paths": ("src/a.py",),
        "missing_paths": (),
        "non_code_paths": (),
        "unindexed_paths": (),
        "indexed_paths": ("src/a.py",),
        "index_file_count": 10,
        "probe_rank": None,
        "target_tokens_present": ("q",),
        "target_tokens_missing": (),
        "corpus_tokens_missing": (),
        "symbol_missing": False,
        "must_not_hits": (),
    }
    fields.update(overrides)
    return FailureEvidence(**fields)


# ── query tokenization ──────────────────────────────────────────────────
def test_query_tokens_mix_identifier_and_cjk_bigrams() -> None:
    tokens = query_tokens("verify_token未知词汇")
    assert tokens[0] == "verify_token"
    assert set(tokens[1:]) == {"未知", "知词", "词汇"}


def test_query_tokens_strip_edge_punctuation_and_dedupe() -> None:
    assert query_tokens("alpha, alpha!") == ("alpha",)
    assert query_tokens("CONTEXT_WINDOW_EXCEEDED_CODE定义在哪？")[0] == (
        "CONTEXT_WINDOW_EXCEEDED_CODE"
    )


# ── classification precedence ───────────────────────────────────────────
def test_a4_when_must_not_path_falls_inside_the_prefix() -> None:
    code, reason = classify(evidence(must_not_hits=("src/b.py",)))
    assert code is AttributionCode.A4
    assert "must_not_paths" in reason


def test_a4_when_target_is_only_retrievable_beyond_k() -> None:
    code, _ = classify(evidence(probe_rank=8, run_k=5))
    assert code is AttributionCode.A4


def test_a4_when_declared_symbol_is_missing_from_returned_chunks() -> None:
    code, _ = classify(evidence(symbol_missing=True))
    assert code is AttributionCode.A4


def test_a6_when_the_index_holds_no_files() -> None:
    code, _ = classify(evidence(index_file_count=0, indexed_paths=()))
    assert code is AttributionCode.A6


def test_a7_when_expect_path_is_missing_on_disk() -> None:
    code, reason = classify(
        evidence(indexed_paths=(), missing_paths=("src/ghost.py",))
    )
    assert code is AttributionCode.A7
    assert "src/ghost.py" in reason


def test_a7_when_expect_path_is_not_an_indexable_extension() -> None:
    code, _ = classify(evidence(indexed_paths=(), non_code_paths=("README.md",)))
    assert code is AttributionCode.A7


def test_a2_when_target_is_on_disk_but_not_indexed() -> None:
    code, reason = classify(
        evidence(indexed_paths=(), unindexed_paths=("src/late.py",), index_file_count=10)
    )
    assert code is AttributionCode.A2
    assert "src/late.py" in reason


def test_a5_when_no_query_token_appears_in_the_target() -> None:
    code, _ = classify(
        evidence(
            indexed_paths=("src/a.py",),
            target_tokens_present=(),
            target_tokens_missing=("q",),
        )
    )
    assert code is AttributionCode.A5


def test_a1_when_a_query_token_is_absent_from_the_target() -> None:
    code, reason = classify(
        evidence(
            target_tokens_present=("verify_token",),
            target_tokens_missing=("义在",),
            corpus_tokens_missing=("义在",),
        )
    )
    assert code is AttributionCode.A1
    assert "义在" in reason


def test_a1_when_the_query_tokenizes_to_nothing() -> None:
    code, reason = classify(
        evidence(target_tokens_present=(), target_tokens_missing=())
    )
    assert code is AttributionCode.A1
    assert "可检索词" in reason


def test_a3_when_terms_exist_in_the_target_but_never_in_one_chunk() -> None:
    code, _ = classify(
        evidence(target_tokens_present=("alpha_one", "beta_two"), target_tokens_missing=())
    )
    assert code is AttributionCode.A3


def test_a5_takes_precedence_over_a1_when_nothing_overlaps() -> None:
    """A pure-CJK query over English code shares no vocabulary: A5, not A1."""
    code, _ = classify(
        evidence(
            target_tokens_present=(),
            target_tokens_missing=("重试", "试哪"),
            corpus_tokens_missing=("重试", "试哪"),
        )
    )
    assert code is AttributionCode.A5


def test_only_a5_is_vector_relevant() -> None:
    assert set(VECTOR_RELEVANT) == {AttributionCode.A5}


# ── evidence collection end-to-end ──────────────────────────────────────
def test_collect_and_classify_a5_on_real_index(corpus: Path) -> None:
    task = make_task("zzz_semantic_concept", ("src/other.py",))
    run = run_eval([task], corpus, k=5)
    attribution = attribute_run(run, [task], corpus)[0]
    assert attribution.code is AttributionCode.A5


def test_collect_and_classify_a1_for_mixed_cjk_query(corpus: Path) -> None:
    task = make_task("verify_token未知词汇", ("src/other.py",))
    run = run_eval([task], corpus, k=5)
    attribution = attribute_run(run, [task], corpus)[0]
    assert attribution.code is AttributionCode.A1
    assert "未知" in attribution.reason


def test_collect_and_classify_a3_when_terms_span_chunks(corpus: Path) -> None:
    task = make_task("alpha_one beta_two", ("src/alpha.py",))
    run = run_eval([task], corpus, k=5)
    attribution = attribute_run(run, [task], corpus)[0]
    assert attribution.code is AttributionCode.A3
    assert attribution.evidence.target_tokens_present == ("alpha_one", "beta_two")


def test_collect_and_classify_a1_for_a_punctuation_only_query(corpus: Path) -> None:
    """ADR-13 routes punctuation to grep; that is a query-construction issue."""
    task = make_task("->", ("src/alpha.py",))
    run = run_eval([task], corpus, k=5)
    attribution = attribute_run(run, [task], corpus)[0]
    assert attribution.code is AttributionCode.A1
    assert attribution.evidence.target_tokens_present == ()


def test_collect_and_classify_a2_when_file_is_added_after_indexing(
    corpus: Path,
) -> None:
    (corpus / "src" / "late.py").write_text(
        "def late_addition():\n    return 3\n", encoding="utf-8"
    )
    task = make_task("late_addition", ("src/late.py",))
    run = run_eval([task], corpus, k=5)
    attribution = attribute_run(run, [task], corpus)[0]
    assert attribution.code is AttributionCode.A2
    assert attribution.evidence.unindexed_paths == ("src/late.py",)


def test_collect_and_classify_a7_for_absent_path(corpus: Path) -> None:
    task = make_task("alpha_one", ("src/ghost.py",))
    run = run_eval([task], corpus, k=5)
    attribution = attribute_run(run, [task], corpus)[0]
    assert attribution.code is AttributionCode.A7


def test_collect_and_classify_a6_without_an_index(tmp_path: Path) -> None:
    root = make_corpus(tmp_path / "unindexed", CORPUS_FILES)
    task = make_task("alpha_one", ("src/alpha.py",))
    run = run_eval([task], root, k=5)
    attribution = attribute_run(run, [task], root)[0]
    assert attribution.code is AttributionCode.A6


def test_collect_and_classify_a4_when_target_ranks_past_k(tmp_path: Path) -> None:
    root = make_corpus(tmp_path / "shared", SHARED_FILES)
    index_sync(root)
    task = make_task("shared_word", ("src/c.py",))
    run = run_eval([task], root, k=1)
    attribution = attribute_run(run, [task], root)[0]
    assert attribution.code is AttributionCode.A4
    assert attribution.evidence.probe_rank is not None
    assert attribution.evidence.probe_rank > 1


# ── distribution and report ─────────────────────────────────────────────
def test_attribution_distribution_splits_by_class(corpus: Path) -> None:
    tasks = [
        make_task("zzz_semantic_concept", ("src/other.py",), task_id="L-001"),
        make_task(
            "另一个不存在的概念",
            ("src/other.py",),
            task_id="L-002",
            task_class="natural",
        ),
        make_task("alpha_one", ("src/alpha.py",), task_id="L-003"),  # passes
    ]
    run = run_eval(tasks, corpus, k=5)
    attributions = attribute_run(run, tasks, corpus)
    assert [item.task_id for item in attributions] == ["L-001", "L-002"]
    distribution = attribution_distribution(attributions)
    assert distribution["overall"] == {"A5": 2}
    assert distribution["exact"] == {"A5": 1}
    assert distribution["natural"] == {"A5": 1}
    assert distribution["crossfile"] == {}


def test_natural_a5_share_is_none_without_natural_failures(corpus: Path) -> None:
    task = make_task("alpha_one", ("src/ghost.py",))
    run = run_eval([task], corpus, k=5)
    assert natural_a5_share(attribute_run(run, [task], corpus)) is None


def test_natural_a5_share_computes_the_r2_ratio(corpus: Path) -> None:
    tasks = [
        make_task(
            "zzz_semantic_concept",
            ("src/other.py",),
            task_id="L-001",
            task_class="natural",
        ),
        make_task(
            "verify_token未知词汇",
            ("src/other.py",),
            task_id="L-002",
            task_class="natural",
        ),
    ]
    run = run_eval(tasks, corpus, k=5)
    share = natural_a5_share(attribute_run(run, tasks, corpus))
    assert share == 0.5


def test_build_attribution_report_is_json_serializable(corpus: Path) -> None:
    import json

    task = make_task("zzz_semantic_concept", ("src/other.py",))
    run = run_eval([task], corpus, k=5)
    report = build_attribution_report(attribute_run(run, [task], corpus))
    assert report["total_failures"] == 1
    failure = report["failures"][0]
    assert failure["id"] == "L-001"
    assert failure["code"] == "A5"
    assert failure["leads_to_vector"] is True
    assert "零词法重叠" in failure["meaning"]
    json.dumps(report, ensure_ascii=False)


def test_collect_evidence_does_not_need_a_task_to_be_missing(corpus: Path) -> None:
    """A passing task is skipped by attribute_run, not attributed."""
    task = make_task("alpha_one", ("src/alpha.py",))
    run = run_eval([task], corpus, k=5)
    assert attribute_run(run, [task], corpus) == ()


def test_unmatched_result_id_is_skipped(corpus: Path) -> None:
    task = make_task("alpha_one", ("src/ghost.py",), task_id="L-001")
    run = run_eval([task], corpus, k=5)
    assert attribute_run(run, [], corpus) == ()


def test_collect_evidence_reports_probe_rank_none_when_unresolvable(
    tmp_path: Path,
) -> None:
    root = make_corpus(tmp_path / "empty", CORPUS_FILES)
    task = make_task("alpha_one", ("src/ghost.py",))
    run = run_eval([task], root, k=5)
    result = run.results[0]
    collected = collect_evidence(task, result, root, run_k=run.k)
    assert collected.probe_rank is None
