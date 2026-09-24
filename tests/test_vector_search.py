"""Tests for the optional vector recall path (T3-09).

The cosine math is checked against a literal brute-force loop, and the recall is
checked end to end on a real (tiny) index built in tmp_path. Embeddings come
from a deterministic injected transport, so everything is offline (T-02).
"""

from __future__ import annotations

import math
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from dsh_coderag import index_sync
from dsh_coderag.config import SemanticConfig
from dsh_coderag.embed import SemanticError
from dsh_coderag.indexer import connect
from dsh_coderag.searcher import vector_candidates
from dsh_coderag.types import ErrorCode
from dsh_coderag.vectors import build_index, cosine_top_k, load_index


def _config() -> SemanticConfig:
    return SemanticConfig(enabled=True, model="bge-m3", batch=16)


def _transport(
    url: str, model: str, texts: Sequence[str], timeout: float
) -> list[list[float]]:
    """Score each text by how often it mentions alpha and beta."""
    return [
        [float(text.count("alpha")), float(text.count("beta"))] for text in texts
    ]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A tiny indexed workspace whose chunks are separable by keyword."""
    root = tmp_path / "ws"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "alpha.py").write_text(
        "def alpha():\n    return 'alpha alpha alpha'\n", encoding="utf-8"
    )
    (root / "pkg" / "beta.py").write_text(
        "def beta():\n    return 'beta'\n", encoding="utf-8"
    )
    index_sync(root)
    return root


def _chunks(root: Path) -> list[tuple[int, str]]:
    connection = connect(root / ".coderag" / "index.sqlite3")
    try:
        rows = connection.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
        return [(int(row[0]), str(row[1])) for row in rows]
    finally:
        connection.close()


def _brute_force(matrix: np.ndarray, query: Sequence[float]) -> list[tuple[int, float]]:
    """A literal cosine loop, used as the reference implementation."""
    scored: list[tuple[int, float]] = []
    for index, row in enumerate(matrix):
        dot = sum(float(a) * float(b) for a, b in zip(row, query, strict=True))
        norm = math.sqrt(sum(float(a) ** 2 for a in row)) * math.sqrt(
            sum(float(b) ** 2 for b in query)
        )
        scored.append((index, 0.0 if norm == 0.0 else dot / norm))
    return sorted(scored, key=lambda item: (-item[1], item[0]))


def test_vector_search_path_does_not_import_numpy_at_module_load() -> None:
    """RL-10: the default BM25 path must not need the optional extra."""
    code = (
        "import sys, dsh_coderag.searcher, dsh_coderag.vectors;"
        "assert 'numpy' not in sys.modules, 'loading the search path pulled in numpy';"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_vector_search_matches_a_brute_force_cosine() -> None:
    matrix = np.asarray(
        [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 0.25], [0.0, 0.0]], dtype=np.float32
    )
    query = [0.6, 0.8]
    expected = _brute_force(matrix, query)[:3]
    actual = cosine_top_k(matrix, query, 3)
    assert [row for row, _ in actual] == [row for row, _ in expected]
    for (_, got), (_, want) in zip(actual, expected, strict=True):
        assert got == pytest.approx(want, abs=1e-6)


def test_vector_search_returns_at_most_k() -> None:
    matrix = np.asarray([[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]], dtype=np.float32)
    assert len(cosine_top_k(matrix, [1.0, 0.0], 2)) == 2
    assert len(cosine_top_k(matrix, [1.0, 0.0], 99)) == 3


def test_vector_search_on_an_empty_index_returns_nothing() -> None:
    empty = np.zeros((0, 4), dtype=np.float32)
    assert cosine_top_k(empty, [1.0, 0.0, 0.0, 0.0], 5) == []


def test_vector_search_with_a_zero_query_returns_nothing() -> None:
    matrix = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    assert cosine_top_k(matrix, [0.0, 0.0], 5) == []


def test_vector_search_ranks_the_matching_chunk_first(workspace: Path) -> None:
    index = build_index(workspace, _config(), _chunks(workspace), transport=_transport)
    hits = vector_candidates(workspace, index, [1.0, 0.0], 5)
    assert hits, "the recall must return candidates"
    assert hits[0].path == "pkg/alpha.py"
    assert [hit.score for hit in hits] == sorted(
        [hit.score for hit in hits], reverse=True
    )


def test_vector_search_prefers_the_other_chunk_for_the_other_query(workspace: Path) -> None:
    index = build_index(workspace, _config(), _chunks(workspace), transport=_transport)
    hits = vector_candidates(workspace, index, [0.0, 1.0], 1)
    assert len(hits) == 1
    assert hits[0].path == "pkg/beta.py"


def test_vector_search_candidates_carry_location_and_text(workspace: Path) -> None:
    index = build_index(workspace, _config(), _chunks(workspace), transport=_transport)
    hits = vector_candidates(workspace, index, [1.0, 0.0], 5)
    for hit in hits:
        assert not hit.path.startswith("/")
        assert "\\" not in hit.path
        assert hit.start_line >= 1 and hit.end_line >= hit.start_line
        assert hit.text


def test_vector_search_reports_index_drift_instead_of_truncating(workspace: Path) -> None:
    index = build_index(workspace, _config(), _chunks(workspace), transport=_transport)
    top_row = cosine_top_k(index.matrix, [1.0, 0.0], 1)[0][0]
    deleted_chunk = index.chunk_ids[top_row]
    connection = connect(workspace / ".coderag" / "index.sqlite3")
    try:
        connection.execute("DELETE FROM chunks WHERE id = ?", (deleted_chunk,))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(SemanticError) as caught:
        vector_candidates(workspace, index, [1.0, 0.0], 5)
    assert caught.value.code is ErrorCode.SEMANTIC_INDEX_MISSING


def test_vector_search_reloads_the_persisted_index(workspace: Path) -> None:
    build_index(workspace, _config(), _chunks(workspace), transport=_transport)
    reloaded = load_index(workspace, _config())
    hits = vector_candidates(workspace, reloaded, [1.0, 0.0], 3)
    assert hits and hits[0].path == "pkg/alpha.py"


def test_vector_search_applies_the_tier_before_the_top_k_cut(tmp_path: Path) -> None:
    """A test chunk with a higher cosine must not take the only slot.

    Cutting to top-k before applying the tier is exactly what made the C group
    score natural@5 = 0.000 while the probe ceiling was 0.429.
    """
    root = tmp_path / "ws"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pkg" / "alpha.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (root / "tests" / "alpha.spec.py").write_text(
        "def test_alpha():\n    alpha = beta + alpha + beta + alpha\n", encoding="utf-8"
    )
    index_sync(root)
    index = build_index(root, _config(), _chunks(root), transport=_transport)
    query = [1.0, 1.0]
    scored = cosine_top_k(index.matrix, query, len(index.chunk_ids))
    best_row, best_score = scored[0]
    best_path = _path_of(root, index.chunk_ids[best_row])
    assert best_path.startswith("tests/"), "fixture must make the test chunk win on cosine"
    hits = vector_candidates(root, index, query, 1)
    assert [hit.path for hit in hits] == ["pkg/alpha.py"]
    assert best_score > 0.85, "the test chunk really is the closer one"


def _path_of(root: Path, chunk_id: int) -> str:
    connection = connect(root / ".coderag" / "index.sqlite3")
    try:
        row = connection.execute(
            "SELECT f.path FROM chunks c JOIN files f ON f.id = c.file_id WHERE c.id = ?",
            (chunk_id,),
        ).fetchone()
        return str(row[0])
    finally:
        connection.close()


def test_vector_search_rejects_a_non_finite_query() -> None:
    matrix = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    with pytest.raises(SemanticError) as caught:
        cosine_top_k(matrix, [float("nan"), 0.0], 2)
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED
