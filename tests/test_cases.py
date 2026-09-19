"""Gates on the committed L2 cases (T3-16).

Structural checks always run. The index check is opt-in because it needs the
prepared DSH copy: `CODERAG_L2_CORPUS=/tmp/dsh-coderag-t3-03-corpus pytest ...`.
That check exists for a specific fairness trap — a case whose answer file is
filtered out of the index can never be answered by the retrieval group.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import pytest

from dsh_coderag.eval.ab import Assertions, Case, load_cases, render_case_review

CASES_DIR = Path(__file__).resolve().parents[1] / "cases"
CORPUS = os.environ.get("CODERAG_L2_CORPUS")
BUCKETS = {"locate", "crossfile", "regression", "negative"}


@pytest.fixture(scope="module")
def cases() -> list[Case]:
    return load_cases(CASES_DIR)


def output_ok(case: Case, text: str) -> bool:
    """Apply only the output-level assertions to one candidate answer."""
    if any(needle not in text for needle in case.expect.output_contains):
        return False
    return all(re.search(pattern, text, re.MULTILINE) for pattern in case.expect.output_matches)


def test_case_count_is_within_the_l2_budget(cases: list[Case]) -> None:
    """EVAL.md 3.4: 12-15 cases. More than that and each run gets too expensive."""
    assert 12 <= len(cases) <= 15, f"用例数 {len(cases)} 不在 12-15"


def test_case_names_are_unique(cases: list[Case]) -> None:
    assert len({case.name for case in cases}) == len(cases)


def test_every_bucket_is_present(cases: list[Case]) -> None:
    tags = {tag for case in cases for tag in case.tags}
    assert tags >= BUCKETS, f"缺少桶：{sorted(BUCKETS - tags)}"


def test_every_case_asserts_at_least_one_thing(cases: list[Case]) -> None:
    for case in cases:
        assert case.expect != Assertions(), f"{case.name} 没有任何断言"


def test_negative_cases_have_no_answer_paths_and_others_do(cases: list[Case]) -> None:
    for case in cases:
        if "negative" in case.tags:
            assert case.answer_paths == (), f"{case.name} 是反臆造控制组，不应有答案文件"
        else:
            assert case.answer_paths, f"{case.name} 缺 answer_paths，无法复核答案位置"


def test_every_case_documents_its_source_and_rationale(cases: list[Case]) -> None:
    for case in cases:
        assert case.notes and "出处" in case.notes and "理由" in case.notes, case.name


def test_prompts_are_chinese_questions(cases: list[Case]) -> None:
    """The project's real usage is Chinese questions; that is what L2 must measure."""
    for case in cases:
        assert any("\u4e00" <= char <= "\u9fff" for char in case.prompt), case.name


def test_every_case_carries_reviewed_answer_samples(cases: list[Case]) -> None:
    for case in cases:
        assert len(case.accept) >= 2, f"{case.name} 至少要有 2 条『应接受』样例"
        assert len(case.reject) >= 2, f"{case.name} 至少要有 2 条『应拒绝』样例"


def test_output_assertions_accept_and_reject_the_reviewed_samples(cases: list[Case]) -> None:
    """An over-tight regex causes false failures; an over-loose one false passes.

    Both directions are checked here, before any model ever runs, so the
    accept/reject samples in each case stay meaningful.
    """
    for case in cases:
        for text in case.accept:
            assert output_ok(case, text), f"{case.name} 拒绝了正确答案：{text!r}"
        for text in case.reject:
            assert not output_ok(case, text), f"{case.name} 接受了错误答案：{text!r}"


def test_review_table_matches_the_cases(cases: list[Case]) -> None:
    """`cases/REVIEW.md` is generated; a stale table would mislead the reviewer."""
    committed = (CASES_DIR / "REVIEW.md").read_text(encoding="utf-8")
    assert committed == render_case_review(cases), "REVIEW.md 已过期，跑 scripts/case-review.py"


@pytest.mark.skipif(
    CORPUS is None, reason="set CODERAG_L2_CORPUS to the prepared DSH copy"
)
def test_every_answer_path_is_inside_the_index(cases: list[Case]) -> None:
    """A filtered answer file would make the case unwinnable for the retrieval group."""
    database = Path(CORPUS) / ".coderag" / "index.sqlite3"  # type: ignore[arg-type]
    assert database.is_file(), f"没有索引：{database}"
    connection = sqlite3.connect(database)
    try:
        indexed = {row[0] for row in connection.execute("select path from files")}
    finally:
        connection.close()
    missing = [
        (case.name, path) for case in cases for path in case.answer_paths
        if path not in indexed
    ]
    assert not missing, f"答案文件不在索引里：{missing}"
