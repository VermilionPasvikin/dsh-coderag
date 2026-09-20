"""Run retrieval eval tasks against an indexed corpus, and gate the golden set.

`run_eval` sends every query through the production `searcher.search` path with
`k=5` (EVAL.md 2.5 option A) and records, per task, whether a target path was
hit, where it landed, and the raw returned paths.

`load_golden_meta` and `check_golden_version` implement the isolation rule of
EVAL.md 2.7: a run declares the `golden_version` it expects, and a mismatch
fails immediately unless the job is explicitly a rebaseline. Without it, a
change to the golden set is indistinguishable from a change to the engine
(EVAL.md 2.9 trap 15, "a silent methodology break").

It deliberately computes no metrics, no attribution and no diff — those are
T3-04, T3-04b and T3-04c.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from dsh_coderag import searcher
from dsh_coderag.config import DEFAULT_MAX_TOKENS
from dsh_coderag.eval.tasks import EvalError, EvalTask
from dsh_coderag.types import Hit, SearchStatus

DEFAULT_K = 5
"""Top-k used for Success@k; must equal what the model would actually see."""

GOLDEN_META_FILENAME = "tasks.meta.json"
"""File-level golden-set metadata kept next to the tasks file (T3-01)."""

_CHARS_PER_TOKEN = 3.5


class GoldenVersionError(EvalError):
    """The golden-set metadata is missing, malformed, or does not match."""


@dataclass(frozen=True)
class GoldenMeta:
    """File-level metadata describing one golden set."""

    golden_version: str


def load_golden_meta(path: Path) -> GoldenMeta:
    """Load the metadata file that owns `golden_version`.

    Raises:
        GoldenVersionError: If the file is missing, is not a JSON object, or has
            no non-empty string `golden_version`. A missing version is a
            methodology hole, so it is never defaulted around.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GoldenVersionError(f"{path}: 无法读取 golden 集元数据：{exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GoldenVersionError(f"{path}: 非法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise GoldenVersionError(f"{path}: 顶层必须是 JSON 对象")
    version = payload.get("golden_version")
    if not isinstance(version, str) or not version:
        raise GoldenVersionError(f"{path}: 缺少非空字符串字段 golden_version")
    return GoldenMeta(golden_version=version)


def check_golden_version(
    expected: str | None,
    actual: str,
    *,
    rebaseline: bool = False,
) -> None:
    """Fail when the golden set on disk is not the one the job expects.

    `expected` of `None` means the job has nothing pinned, so only `actual` is
    reported. `rebaseline` is the explicit human opt-out that EVAL.md 2.7
    requires: it is never inferred.

    Raises:
        GoldenVersionError: On a mismatch without `rebaseline`.
    """
    if rebaseline or expected is None or expected == actual:
        return
    raise GoldenVersionError(
        f"golden_version 不匹配：期望 {expected!r}，实际 {actual!r}。"
        "改了 golden 集就必须同步升版本号，否则分数变化无法归因"
        "（EVAL.md 2.7 / 2.9 陷阱 15）。若本次确实是在重建基线，请显式传 --rebaseline。"
    )


@dataclass(frozen=True)
class EvalResult:
    """One task's outcome against a corpus.

    `rank` is the 1-based position of the best matching target inside the
    returned hits. Hits come back in source order (ADR-05), so rank is a
    position in the returned list, not a relevance rank.
    """

    task_id: str
    task_class: str
    query: str
    status: str
    hit: bool
    matched_path: str | None
    rank: int | None
    returned_paths: tuple[str, ...]
    must_not_hit: tuple[str, ...]
    symbol_hit: bool | None
    token_estimate: int
    error: str | None


@dataclass(frozen=True)
class EvalRun:
    """Every task's outcome for one corpus and one k.

    `golden_version` is carried through from the metadata file so a caller can
    attribute a score to the exact golden set that produced it.
    """

    corpus_root: Path
    k: int
    results: tuple[EvalResult, ...]
    golden_version: str | None = None


def run_eval(
    tasks: list[EvalTask],
    corpus_root: Path,
    *,
    k: int = DEFAULT_K,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    golden_version: str | None = None,
) -> EvalRun:
    """Search each task's query against `corpus_root` and record the outcome.

    A task counts as a hit when at least one `expect_paths` entry is among the
    returned hits, unless a `must_not_paths` entry was also returned or a
    declared `expect_symbols` entry is missing (EVAL.md 2.5).

    `golden_version` is provenance only; callers gate on it with
    `check_golden_version` before running.
    """
    results = tuple(
        _run_task(task, corpus_root, k=k, max_tokens=max_tokens) for task in tasks
    )
    return EvalRun(
        corpus_root=corpus_root,
        k=k,
        results=results,
        golden_version=golden_version,
    )


def _run_task(
    task: EvalTask, corpus_root: Path, *, k: int, max_tokens: int
) -> EvalResult:
    outcome = searcher.search(corpus_root, task.query, k=k, max_tokens=max_tokens)
    returned = tuple(hit.path for hit in outcome.hits)
    expect = set(task.expect_paths)
    ranked = [
        (position, hit)
        for position, hit in enumerate(outcome.hits, start=1)
        if hit.path in expect
    ]
    matched_path = ranked[0][1].path if ranked else None
    rank = ranked[0][0] if ranked else None
    must_not_hit = tuple(path for path in returned if path in set(task.must_not_paths))
    symbol_hit: bool | None = None
    if task.expect_symbols:
        symbol_hit = any(
            _symbol_present(hit, symbol)
            for hit in outcome.hits
            for symbol in task.expect_symbols
        )
    hit = bool(ranked) and not must_not_hit and symbol_hit is not False
    error: str | None = None
    if outcome.status is SearchStatus.ERROR:
        error = outcome.code.value if outcome.code is not None else outcome.message
    token_estimate = int(sum(len(hit.text) for hit in outcome.hits) / _CHARS_PER_TOKEN)
    return EvalResult(
        task_id=task.id,
        task_class=task.task_class,
        query=task.query,
        status=outcome.status.value,
        hit=hit,
        matched_path=matched_path,
        rank=rank,
        returned_paths=returned,
        must_not_hit=must_not_hit,
        symbol_hit=symbol_hit,
        token_estimate=token_estimate,
        error=error,
    )


def _symbol_present(hit: Hit, symbol: str) -> bool:
    """Whether a returned hit declares or contains `symbol` as an identifier."""
    if hit.symbol_name == symbol:
        return True
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(symbol) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, hit.text) is not None
