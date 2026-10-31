"""Tests for RRF fusion and the optional backend's clean fallback (T3-10).

Everything runs offline (T-02): the unavailable-backend case points at a closed
loopback port, and the available case injects candidates through the private
seam instead of talking to Ollama.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from dsh_coderag import index_sync
from dsh_coderag.config import SemanticConfig
from dsh_coderag.render import render_search_result
from dsh_coderag.searcher import (
    RRF_K,
    fuse_candidates,
    fusion_key,
    is_test_path,
    reciprocal_rank_fusion,
    search,
)
from dsh_coderag.types import ErrorCode, Hit, SearchStatus


def _hit(path: str, seq: int, start: int = 1, end: int = 2, text: str = "x = 1\n") -> Hit:
    return Hit(path=path, seq=seq, start_line=start, end_line=end, text=text, score=0.0)


def _disabled() -> SemanticConfig:
    return SemanticConfig(enabled=False)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A tiny indexed workspace with one non-test and one test source file."""
    root = tmp_path / "ws"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "alpha.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "alpha.spec.py").write_text(
        "def test_alpha():\n    assert True\n", encoding="utf-8"
    )
    index_sync(root)
    return root


def test_rrf_k_is_the_frozen_sixty() -> None:
    """Qdrant's default is 2; using it here would silently change every score."""
    assert RRF_K == 60


def test_rrf_scores_follow_the_frozen_formula() -> None:
    first = [("a", 0), ("b", 0)]
    second = [("b", 0), ("c", 0)]
    scores = reciprocal_rank_fusion([first, second])
    assert scores[("a", 0)] == pytest.approx(1 / 61)
    assert scores[("b", 0)] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[("c", 0)] == pytest.approx(1 / 62)


def test_rrf_only_depends_on_rank_not_on_score_scale() -> None:
    lexical = [("a", 0), ("b", 0), ("c", 0)]
    vector = [("c", 0), ("b", 0), ("a", 0)]
    scores = reciprocal_rank_fusion([lexical, vector])
    assert scores[("a", 0)] == scores[("c", 0)] == pytest.approx(1 / 61 + 1 / 63)
    assert scores[("b", 0)] == pytest.approx(2 / 62)


def test_fusion_keeps_chunks_that_only_the_vector_found() -> None:
    lexical = [_hit("pkg/a.py", 0)]
    vector = [_hit("pkg/b.py", 0)]
    fused = fuse_candidates(lexical, vector, limit=5)
    assert {hit.path for hit in fused} == {"pkg/a.py", "pkg/b.py"}


def test_fusion_applies_the_frozen_non_test_first_tier() -> None:
    lexical = [_hit("tests/a.spec.py", 0)]
    vector = [_hit("tests/a.spec.py", 0)]
    only_test = fuse_candidates(lexical, vector, limit=1)
    assert only_test[0].path == "tests/a.spec.py"
    mixed = fuse_candidates(
        [_hit("tests/a.spec.py", 0), _hit("pkg/a.py", 0)],
        [_hit("tests/a.spec.py", 0), _hit("pkg/a.py", 0)],
        limit=1,
    )
    assert mixed[0].path == "pkg/a.py"


def test_fusion_output_follows_fusion_order() -> None:
    """T8-09: trimming must see relevance order, not the ADR-05 render order."""
    fused = fuse_candidates(
        [_hit("pkg/z.py", 0, 5), _hit("pkg/a.py", 0, 9)],
        [_hit("pkg/z.py", 0, 5)],
        limit=5,
    )
    assert [(hit.path, hit.start_line) for hit in fused] == [("pkg/z.py", 5), ("pkg/a.py", 9)]


def test_search_trims_by_rank_before_rendering_in_source_order(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T8-09: an exact hit that sorts late must survive the token budget."""
    root = workspace
    big = "alpha = '" + "x" * 1200 + "'\n"
    (root / "pkg" / "a_big.py").write_text(big, encoding="utf-8")
    (root / "pkg" / "b_big.py").write_text(big.replace("x", "y"), encoding="utf-8")
    (root / "pkg" / "z1_exact.py").write_text("alpha = 1\n", encoding="utf-8")
    (root / "pkg" / "z2_exact.py").write_text("alpha = 2\n", encoding="utf-8")
    index_sync(root)

    indexed = search(root, "alpha", k=10, semantic=_disabled())
    exact = {hit.path: hit for hit in indexed.hits if hit.path.startswith("pkg/z")}
    assert set(exact) == {"pkg/z1_exact.py", "pkg/z2_exact.py"}

    monkeypatch.setattr(
        "dsh_coderag.searcher._semantic_candidates",
        lambda base, query, config, k: [exact["pkg/z1_exact.py"], exact["pkg/z2_exact.py"]],
    )
    enabled = SemanticConfig(
        enabled=True, backend="ollama", url="http://127.0.0.1:11434", timeout_s=1
    )
    result = search(root, "alpha", k=10, max_tokens=450, semantic=enabled)
    assert [hit.path for hit in result.hits] == [
        "pkg/a_big.py",
        "pkg/alpha.py",
        "pkg/z1_exact.py",
        "pkg/z2_exact.py",
    ]
    assert result.omitted == 2
    assert result.ranking is not None
    assert [path for path, _ in result.ranking][:2] == [
        "pkg/z1_exact.py",
        "pkg/z2_exact.py",
    ]


def test_fusion_ranks_lexical_candidates_by_bm25_not_source_order(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T8-10: RRF must receive BM25 selection order, not ADR-05 render order."""
    root = workspace
    (root / "pkg" / "a.py").write_text("zebra = 1\n" + "# filler\n" * 40, encoding="utf-8")
    (root / "pkg" / "m.py").write_text("zebra = 1\n" + "# filler\n" * 200, encoding="utf-8")
    (root / "pkg" / "z.py").write_text(
        "zebra = 1\nzebra = 2\nzebra = 3\nzebra = 4\nzebra = 5\n", encoding="utf-8"
    )
    index_sync(root)

    indexed = search(root, "zebra", k=10, semantic=_disabled())
    middle = next(hit for hit in indexed.hits if hit.path == "pkg/m.py")

    monkeypatch.setattr(
        "dsh_coderag.searcher._semantic_candidates",
        lambda base, query, config, k: [middle],
    )
    enabled = SemanticConfig(
        enabled=True, backend="ollama", url="http://127.0.0.1:11434", timeout_s=1
    )
    result = search(root, "zebra", k=2, semantic=enabled)
    assert [hit.path for hit in result.hits] == ["pkg/m.py", "pkg/z.py"]


def test_fusion_respects_the_limit_and_is_deterministic() -> None:
    lexical = [_hit(f"pkg/f{index}.py", 0) for index in range(6)]
    vector = list(reversed(lexical))
    first = fuse_candidates(lexical, vector, limit=3)
    second = fuse_candidates(list(reversed(vector)), list(reversed(lexical)), limit=3)
    assert len(first) == 3
    assert [fusion_key(hit) for hit in first] == [fusion_key(hit) for hit in second]


def test_fusion_of_nothing_is_empty() -> None:
    assert fuse_candidates([], [], limit=5) == []


def test_is_test_path_matches_the_sql_tier_predicate() -> None:
    """The Python tier and TEST_PATH_TIER_SQL must select exactly the same paths."""
    paths = [
        "tests/a.py",
        "pkg/tests/a.py",
        "__tests__/a.py",
        "pkg/__tests__/a.py",
        "pkg/a.spec.ts",
        "pkg/a.test.ts",
        "pkg/a.py",
        "pkg/tests_helper.py",
        "pkg/latest.py",
        "pkg/contest.py",
        "pkg/spec.py",
        "test/a.py",
    ]
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE files (path TEXT)")
        connection.executemany("INSERT INTO files VALUES (?)", [(path,) for path in paths])
        sql_rows = {
            row[0]
            for row in connection.execute(
                "SELECT path FROM files WHERE path LIKE 'tests/%' OR path LIKE '%/tests/%'"
                " OR path LIKE '__tests__/%' OR path LIKE '%/__tests__/%'"
                " OR path LIKE '%.spec.%' OR path LIKE '%.test.%'"
            )
        }
    finally:
        connection.close()
    assert {path for path in paths if is_test_path(path)} == sql_rows


def test_search_is_byte_identical_while_the_switch_is_off(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODERAG_SEMANTIC", raising=False)
    implicit = search(workspace, "alpha", k=5)
    explicit = search(workspace, "alpha", k=5, semantic=_disabled())
    assert implicit.semantic is None and explicit.semantic is None
    assert render_search_result(implicit) == render_search_result(explicit)
    assert implicit.hits and [hit.path for hit in implicit.hits] == [
        hit.path for hit in explicit.hits
    ]


def test_search_falls_back_cleanly_when_the_backend_is_unreachable(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T8-05: with an index present, a dead backend still degrades to BM25."""
    monkeypatch.setattr(
        "dsh_coderag.searcher.vectors.load_index", lambda base, config: object()
    )
    baseline = search(workspace, "alpha", k=5, semantic=_disabled())
    enabled = SemanticConfig(
        enabled=True, backend="ollama", url="http://127.0.0.1:1", timeout_s=1
    )
    degraded = search(workspace, "alpha", k=5, semantic=enabled)
    assert degraded.status is SearchStatus.READY
    assert [hit.path for hit in degraded.hits] == [hit.path for hit in baseline.hits]
    assert degraded.hits, "a clean fallback must not become an empty result (RL-06)"
    assert degraded.semantic is not None
    assert degraded.semantic.code is ErrorCode.SEMANTIC_EMBED_FAILED


def test_search_reports_a_missing_vector_index_without_contacting_the_backend(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T8-05: the index is checked before the query is embedded."""
    calls: list[int] = []

    def must_not_run(*args: object, **kwargs: object) -> list[float]:
        calls.append(1)
        raise AssertionError("embedding must not run without a vector index")

    monkeypatch.setattr("dsh_coderag.searcher.embed_query", must_not_run)
    enabled = SemanticConfig(
        enabled=True, backend="ollama", url="http://127.0.0.1:1", timeout_s=1
    )
    degraded = search(workspace, "alpha", k=5, semantic=enabled)
    assert degraded.semantic is not None
    assert degraded.semantic.code is ErrorCode.SEMANTIC_INDEX_MISSING
    assert calls == []


def test_search_reports_an_unknown_backend_as_a_notice(workspace: Path) -> None:
    baseline = search(workspace, "alpha", k=5, semantic=_disabled())
    enabled = SemanticConfig(enabled=True, backend="acme", url="http://127.0.0.1:1")
    degraded = search(workspace, "alpha", k=5, semantic=enabled)
    assert [hit.path for hit in degraded.hits] == [hit.path for hit in baseline.hits]
    assert degraded.semantic is not None
    assert degraded.semantic.code is ErrorCode.SEMANTIC_BACKEND_UNSUPPORTED


def test_search_uses_vector_candidates_when_the_backend_works(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    injected = [_hit("pkg/injected.py", 0, text="def injected():\n    return 1\n")]

    def fake(base: Path, query: str, config: SemanticConfig, k: int) -> list[Hit]:
        return list(injected)

    monkeypatch.setattr("dsh_coderag.searcher._semantic_candidates", fake)
    enabled = SemanticConfig(enabled=True, backend="ollama", url="http://127.0.0.1:1")
    result = search(workspace, "alpha", k=5, semantic=enabled)
    assert result.semantic is None, "a working backend reports no notice"
    assert "pkg/injected.py" in [hit.path for hit in result.hits]


def test_search_without_bm25_candidates_can_still_return_vector_hits(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The natural-language case: BM25 finds nothing, the vector path answers."""
    injected = [_hit("pkg/semantic.py", 0, text="def semantic():\n    return 1\n")]

    monkeypatch.setattr(
        "dsh_coderag.searcher._semantic_candidates",
        lambda base, query, config, k: list(injected),
    )
    enabled = SemanticConfig(enabled=True, backend="ollama", url="http://127.0.0.1:1")
    result = search(workspace, "zzz-no-lexical-overlap", k=5, semantic=enabled)
    assert result.status is SearchStatus.READY
    assert [hit.path for hit in result.hits] == ["pkg/semantic.py"]


def test_search_survives_a_malformed_semantic_environment(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODERAG_SEMANTIC", "on")
    monkeypatch.setenv("CODERAG_SEMANTIC_BACKEND", "openai")
    monkeypatch.delenv("CODERAG_SEMANTIC_URL", raising=False)
    monkeypatch.delenv("CODERAG_SEMANTIC_MODEL", raising=False)
    baseline = search(workspace, "alpha", k=5, semantic=_disabled())
    result = search(workspace, "alpha", k=5)
    assert result.status is SearchStatus.READY
    assert [hit.path for hit in result.hits] == [hit.path for hit in baseline.hits]
    assert result.semantic is not None
    assert result.semantic.code is ErrorCode.SEMANTIC_BACKEND_UNSUPPORTED


def test_search_does_not_load_numpy_or_network_while_disabled(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODERAG_SEMANTIC", raising=False)
    calls: list[Sequence[str]] = []

    def explode(*args: object, **kwargs: object) -> list[Hit]:
        calls.append(("called",))
        raise AssertionError("the optional path must not run while disabled")

    monkeypatch.setattr("dsh_coderag.searcher._semantic_candidates", explode)
    result = search(workspace, "alpha", k=5, semantic=_disabled())
    assert result.hits
    assert calls == []
