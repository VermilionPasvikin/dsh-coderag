"""Run retrieval eval tasks against an indexed corpus (EVAL.md 2.5).

`run_eval` sends every query through the production `searcher.search` path
with `k=5` (EVAL.md 2.5 option A) and records, per task, whether a target path
was hit, where it landed, and the raw returned paths. It deliberately computes
no metrics, no attribution and no diff — those are T3-04, T3-04b and T3-04c.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dsh_coderag import searcher
from dsh_coderag.config import DEFAULT_MAX_TOKENS
from dsh_coderag.eval.tasks import EvalTask
from dsh_coderag.types import Hit, SearchStatus

DEFAULT_K = 5
"""Top-k used for Success@k; must equal what the model would actually see."""

_CHARS_PER_TOKEN = 3.5


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
    """Every task's outcome for one corpus and one k."""

    corpus_root: Path
    k: int
    results: tuple[EvalResult, ...]


def run_eval(
    tasks: list[EvalTask],
    corpus_root: Path,
    *,
    k: int = DEFAULT_K,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> EvalRun:
    """Search each task's query against `corpus_root` and record the outcome.

    A task counts as a hit when at least one `expect_paths` entry is among the
    returned hits, unless a `must_not_paths` entry was also returned or a
    declared `expect_symbols` entry is missing (EVAL.md 2.5).
    """
    results = tuple(
        _run_task(task, corpus_root, k=k, max_tokens=max_tokens) for task in tasks
    )
    return EvalRun(corpus_root=corpus_root, k=k, results=results)


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
