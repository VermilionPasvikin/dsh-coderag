"""Failure attribution for the L1 evaluation (EVAL.md 2.8).

Every failed query must be assigned exactly one attribution code A1-A7, because
the R2 decision ("do we need embeddings?") is defined as "Success@5 < 0.80 and
A5 is >= 50% of natural-class failures". Without a mechanical code per failure
that condition cannot be evaluated.

The work is split in two so the decision rule stays testable without an index:

* `collect_evidence` performs the I/O — it inspects the corpus, the index and
  a wider probe search, and returns a `FailureEvidence` record.
* `classify` is pure: it turns one `FailureEvidence` into one code by a fixed
  precedence, documented below.

Precedence (first match wins):

1. `must_not_paths` inside the returned prefix          -> A4 (ranking)
2. target retrievable only beyond the run's k            -> A4 (rank too low)
3. target returned but a declared symbol was not         -> A4 (ranking/chunk)
4. the index holds no files at all                       -> A6 (empty corpus)
5. target not in the index at all                        -> A7 if the path is
   missing or not indexable, else A2 (filtered/parse/limit)
6. no query token appears anywhere in the target's text  -> A5 (zero overlap)
7. the query tokenized to nothing, or some token is      -> A1 (tokenization /
   absent from the target's own text                        query construction)
8. otherwise every token is in the target, but never in  -> A3 (chunk split)
   one chunk

The A1/A3 split keys on the **target file**, not the whole corpus: since
`_build_match` ANDs every token, a token missing from the target alone already
guarantees the miss. Corpus-wide absence (recorded in the evidence as
`corpus_tokens_missing`) distinguishes "the tokenizer invented a token nothing
can match" from "the token exists elsewhere but not here"; both are A1.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from dsh_coderag import searcher
from dsh_coderag.eval.metrics import is_hit_at
from dsh_coderag.eval.runner import EvalResult, EvalRun
from dsh_coderag.eval.tasks import TASK_CLASSES, EvalTask
from dsh_coderag.indexer import connect
from dsh_coderag.text import to_bigrams
from dsh_coderag.walker import CODE_EXTENSIONS

PROBE_K = 50
"""How far to look for a target before calling the failure a ranking problem."""

PROBE_MAX_TOKENS = 10**9
"""Disable token-budget trimming during the probe so ranks stay comparable."""

_EDGE = re.compile(r"^[^0-9A-Za-z_\u4e00-\u9fff]+|[^0-9A-Za-z_\u4e00-\u9fff]+$")


class AttributionCode(str, Enum):
    """The seven failure classes of EVAL.md 2.8."""

    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"
    A5 = "A5"
    A6 = "A6"
    A7 = "A7"


CODE_MEANINGS: dict[AttributionCode, str] = {
    AttributionCode.A1: "分词失败：中文词被切错或短词无法匹配",
    AttributionCode.A2: "索引缺失：目标文件没进索引（被过滤 / 解析失败 / 超限）",
    AttributionCode.A3: "分块切断：答案横跨两个 chunk，两边都不完整",
    AttributionCode.A4: "排名过低：命中了但排在 k 之外（或错误文件挤入前缀）",
    AttributionCode.A5: "零词法重叠：query 与目标代码没有任何共同词",
    AttributionCode.A6: "检索集不含答案：答案不在被检索的范围里",
    AttributionCode.A7: "标注错误：expect_paths 指向不存在或不可索引的路径",
}

VECTOR_RELEVANT: frozenset[AttributionCode] = frozenset({AttributionCode.A5})
"""Only A5 supports "introduce embeddings" (EVAL.md 2.8); the rest are bugs."""


@dataclass(frozen=True)
class FailureEvidence:
    """Everything the classifier is allowed to look at for one failure."""

    task_id: str
    task_class: str
    query: str
    run_k: int
    probe_k: int
    expect_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    non_code_paths: tuple[str, ...]
    unindexed_paths: tuple[str, ...]
    indexed_paths: tuple[str, ...]
    index_file_count: int
    probe_rank: int | None
    """1-based position of a target inside the probe's **source-ordered** hits.

    This is NOT a relevance rank: `searcher.search` returns hits in source
    order (ADR-05), so the number itself carries no ranking meaning. Only
    `is None` is meaningful — it says no target file was among the probe's
    top-`probe_k` candidates at all. Use `target_in_probe` instead of
    comparing this number to `run_k`.
    """

    target_tokens_present: tuple[str, ...]
    target_tokens_missing: tuple[str, ...]
    corpus_tokens_missing: tuple[str, ...]
    symbol_missing: bool
    must_not_hits: tuple[str, ...]

    @property
    def target_in_probe(self) -> bool:
        """Whether a target was retrievable within `probe_k` (hence ranked too low).

        A failing task whose target still shows up in the wider probe was
        retrieved but placed beyond the run's k, which is A4.
        """
        return self.probe_rank is not None


@dataclass(frozen=True)
class Attribution:
    """One failure's code, its human-readable reason and the evidence behind it."""

    task_id: str
    task_class: str
    code: AttributionCode
    reason: str
    evidence: FailureEvidence


def query_tokens(query: str) -> tuple[str, ...]:
    """Searchable tokens of a query, using the same bigram step as the indexer.

    Punctuation is stripped from each token edge only, so `CONTEXT_WINDOW_
    EXCEEDED_CODE定义在哪？` yields the identifier plus the CJK bigrams.
    """
    tokens: list[str] = []
    for raw in to_bigrams(query).split():
        token = _EDGE.sub("", raw)
        if token and token not in tokens:
            tokens.append(token)
    return tuple(tokens)


def classify(evidence: FailureEvidence) -> tuple[AttributionCode, str]:
    """Return the single attribution code for one failure, by fixed precedence."""
    if evidence.must_not_hits:
        return (
            AttributionCode.A4,
            f"must_not_paths 落入前 k 条：{list(evidence.must_not_hits)}",
        )
    if evidence.target_in_probe:
        return (
            AttributionCode.A4,
            f"目标在 probe_k={evidence.probe_k} 的候选集内可检索到，但不在 k={evidence.run_k} 内"
            "（命中但排名过低）",
        )
    if evidence.symbol_missing and evidence.indexed_paths:
        return (AttributionCode.A4, "目标文件已收录但声明的 expect_symbols 未出现在返回 chunk 中")
    if evidence.index_file_count == 0:
        return (AttributionCode.A6, "索引不含任何文件，检索集为空")
    if not evidence.indexed_paths:
        if evidence.missing_paths or evidence.non_code_paths:
            broken = list(evidence.missing_paths) + list(evidence.non_code_paths)
            return (AttributionCode.A7, f"expect_paths 不可解析为可索引文件：{broken}")
        return (
            AttributionCode.A2,
            f"目标文件在磁盘上但未进索引：{list(evidence.unindexed_paths)}",
        )
    if not evidence.target_tokens_present and not evidence.target_tokens_missing:
        return (AttributionCode.A1, "query 分词后没有任何可检索词（纯标点或短符号）")
    if not evidence.target_tokens_present:
        return (AttributionCode.A5, "query 的任何一个词都不出现在目标文件的索引文本中")
    if evidence.target_tokens_missing:
        missing = list(evidence.target_tokens_missing)
        extra = ""
        if evidence.corpus_tokens_missing:
            extra = f"；其中 {list(evidence.corpus_tokens_missing)} 在整个索引中也不存在"
        return (
            AttributionCode.A1,
            f"query 要求命中目标文件里不存在的词 {missing}{extra}，"
            "而 _build_match 把它们一并 AND，必然落空",
        )
    return (AttributionCode.A3, "query 的词都存在于目标文件，但没有任何单个 chunk 同时包含它们")


def collect_evidence(
    task: EvalTask,
    result: EvalResult,
    corpus_root: Path,
    *,
    run_k: int,
    probe_k: int = PROBE_K,
) -> FailureEvidence:
    """Gather the observable facts for one failed task.

    This reads the filesystem, the index and one wider probe search. It never
    writes anything.
    """
    base = corpus_root.resolve()
    missing: list[str] = []
    non_code: list[str] = []
    for rel in task.expect_paths:
        if not (base / rel).is_file():
            missing.append(rel)
        elif Path(rel).suffix not in CODE_EXTENSIONS:
            non_code.append(rel)
    resolvable = [rel for rel in task.expect_paths if rel not in missing and rel not in non_code]

    db_path = base / ".coderag" / "index.sqlite3"
    index_file_count = 0
    indexed: list[str] = []
    unindexed: list[str] = []
    target_present: list[str] = []
    target_missing: list[str] = []
    corpus_missing: list[str] = []
    if db_path.is_file():
        connection = connect(db_path)
        try:
            index_file_count = int(
                connection.execute("SELECT count(*) FROM files").fetchone()[0]
            )
            for rel in resolvable:
                if _path_indexed(connection, rel):
                    indexed.append(rel)
                else:
                    unindexed.append(rel)
            for token in query_tokens(task.query):
                if any(_token_in_path(connection, token, rel) for rel in indexed):
                    target_present.append(token)
                else:
                    target_missing.append(token)
                if not _token_in_corpus(connection, token):
                    corpus_missing.append(token)
        finally:
            connection.close()

    probe_rank: int | None = None
    if resolvable:
        probe = searcher.search(
            corpus_root, task.query, k=probe_k, max_tokens=PROBE_MAX_TOKENS
        )
        expected = set(task.expect_paths)
        for position, hit in enumerate(probe.hits, start=1):
            if hit.path in expected:
                probe_rank = position
                break

    return FailureEvidence(
        task_id=task.id,
        task_class=task.task_class,
        query=task.query,
        run_k=run_k,
        probe_k=probe_k,
        expect_paths=task.expect_paths,
        missing_paths=tuple(missing),
        non_code_paths=tuple(non_code),
        unindexed_paths=tuple(unindexed),
        indexed_paths=tuple(indexed),
        index_file_count=index_file_count,
        probe_rank=probe_rank,
        target_tokens_present=tuple(target_present),
        target_tokens_missing=tuple(target_missing),
        corpus_tokens_missing=tuple(corpus_missing),
        symbol_missing=result.symbol_hit is False,
        must_not_hits=result.must_not_hit,
    )


def attribute_run(
    run: EvalRun,
    tasks: Sequence[EvalTask],
    corpus_root: Path,
    *,
    probe_k: int = PROBE_K,
) -> tuple[Attribution, ...]:
    """Attribute every task that is not a hit within the run's k.

    `tasks` supplies `expect_paths` and `expect_symbols`, which an `EvalResult`
    does not carry; it is matched to results by task id.
    """
    by_id = {task.id: task for task in tasks}
    attributions: list[Attribution] = []
    for result in run.results:
        if is_hit_at(result, run.k):
            continue
        task = by_id.get(result.task_id)
        if task is None:
            continue
        evidence = collect_evidence(task, result, corpus_root, run_k=run.k, probe_k=probe_k)
        code, reason = classify(evidence)
        attributions.append(
            Attribution(
                task_id=result.task_id,
                task_class=result.task_class,
                code=code,
                reason=reason,
                evidence=evidence,
            )
        )
    return tuple(attributions)


def attribution_distribution(
    attributions: Sequence[Attribution],
) -> dict[str, dict[str, int]]:
    """Count codes per class plus an `overall` row; only nonzero cells appear."""
    distribution: dict[str, dict[str, int]] = {"overall": {}}
    for task_class in TASK_CLASSES:
        distribution[task_class] = {}
    for attribution in attributions:
        code = attribution.code.value
        distribution["overall"][code] = distribution["overall"].get(code, 0) + 1
        bucket = distribution.setdefault(attribution.task_class, {})
        bucket[code] = bucket.get(code, 0) + 1
    return distribution


def natural_a5_share(attributions: Sequence[Attribution]) -> float | None:
    """Share of A5 among natural-class failures; None when there are none.

    This is the second half of the precise R2 condition in EVAL.md 2.8.
    """
    natural = [item for item in attributions if item.task_class == "natural"]
    if not natural:
        return None
    return sum(1 for item in natural if item.code is AttributionCode.A5) / len(natural)


def build_attribution_report(attributions: Sequence[Attribution]) -> dict[str, Any]:
    """JSON-serializable attribution section for the eval report."""
    return {
        "total_failures": len(attributions),
        "distribution": attribution_distribution(attributions),
        "natural_a5_share": natural_a5_share(attributions),
        "failures": [
            {
                "id": item.task_id,
                "class": item.task_class,
                "code": item.code.value,
                "meaning": CODE_MEANINGS[item.code],
                "reason": item.reason,
                "leads_to_vector": item.code in VECTOR_RELEVANT,
            }
            for item in attributions
        ],
    }


def _path_indexed(connection: sqlite3.Connection, rel: str) -> bool:
    row = connection.execute("SELECT 1 FROM files WHERE path = ? LIMIT 1", (rel,)).fetchone()
    return row is not None


def _token_in_path(connection: sqlite3.Connection, token: str, rel: str) -> bool:
    sql = (
        "SELECT 1 FROM chunks_fts "
        "JOIN chunks c ON c.id = chunks_fts.chunk_id "
        "JOIN files f ON f.id = c.file_id "
        "WHERE chunks_fts MATCH ? AND f.path = ? LIMIT 1"
    )
    return _match_exists(connection, sql, (token, rel))


def _token_in_corpus(connection: sqlite3.Connection, token: str) -> bool:
    sql = "SELECT 1 FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 1"
    return _match_exists(connection, sql, (token,))


def _match_exists(
    connection: sqlite3.Connection, sql: str, params: tuple[str, ...]
) -> bool:
    """Run an FTS MATCH probe, treating an unparseable token as 'absent'."""
    phrase = '"' + params[0].replace('"', '""') + '"'
    try:
        return connection.execute(sql, (phrase, *params[1:])).fetchone() is not None
    except sqlite3.OperationalError:
        return False
