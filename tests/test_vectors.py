"""Tests for dsh_coderag.vectors (T3-09): storage, budget and manifest contract.

Everything is offline: embeddings come from a deterministic injected transport,
so no backend and no API key are needed (T-02). numpy is used only through the
module under test and is installed as the optional extra.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from dsh_coderag.config import SemanticConfig
from dsh_coderag.embed import SemanticError
from dsh_coderag.types import ErrorCode
from dsh_coderag.vectors import (
    EMBEDDINGS_FILENAME,
    MANIFEST_FILENAME,
    VectorIndex,
    build_index,
    check_chunk_budget,
    content_hash,
    load_index,
    save_index,
    vectors_dir,
)

DIM = 4


def _config(**overrides: object) -> SemanticConfig:
    values: dict[str, object] = {"enabled": True, "model": "bge-m3", "batch": 16}
    values.update(overrides)
    return SemanticConfig(**values)  # type: ignore[arg-type]


def _transport(
    url: str, model: str, texts: Sequence[str], timeout: float
) -> list[list[float]]:
    """Deterministic one-vector-per-text transport, no network."""
    return [
        [float(len(text) % 7), float(index % 3), 1.0, 0.5]
        for index, text in enumerate(texts)
    ]


def test_content_hash_is_stable_and_text_specific() -> None:
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("abc")) == 64


def test_vectors_dir_stays_inside_the_workspace(tmp_path: Path) -> None:
    directory = vectors_dir(tmp_path)
    assert directory.is_relative_to(tmp_path.resolve())
    assert directory.parts[-2:] == (".coderag", "vectors")


def test_budget_allows_the_limit_and_refuses_above_it() -> None:
    config = _config(max_chunks=3)
    check_chunk_budget(config, 3)
    with pytest.raises(SemanticError) as caught:
        check_chunk_budget(config, 4)
    assert caught.value.code is ErrorCode.SEMANTIC_INDEX_TOO_LARGE
    assert "4" in str(caught.value) and "3" in str(caught.value)


def test_build_index_writes_both_files_inside_the_workspace(tmp_path: Path) -> None:
    chunks = [(1, "alpha"), (2, "beta beta"), (3, "gamma")]
    index = build_index(tmp_path, _config(), chunks, transport=_transport)
    directory = tmp_path / ".coderag" / "vectors"
    assert (directory / EMBEDDINGS_FILENAME).is_file()
    assert (directory / MANIFEST_FILENAME).is_file()
    assert index.chunk_ids == (1, 2, 3)
    assert index.dim == DIM
    assert index.model == "bge-m3"
    assert index.matrix.shape == (3, DIM)
    assert not (tmp_path / ".coderag" / "vectors").is_symlink()


def test_saved_manifest_records_the_frozen_fields(tmp_path: Path) -> None:
    chunks = [(7, "one"), (8, "two")]
    build_index(tmp_path, _config(), chunks, transport=_transport)
    manifest = json.loads((vectors_dir(tmp_path) / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["format_version"] == 1
    assert manifest["model"] == "bge-m3"
    assert manifest["dim"] == DIM
    assert manifest["chunk_count"] == 2
    assert manifest["chunk_ids"] == [7, 8]
    assert manifest["content_hashes"] == [content_hash("one"), content_hash("two")]
    assert isinstance(manifest["generated_at"], str) and manifest["generated_at"]


def test_round_trip_reloads_the_same_matrix(tmp_path: Path) -> None:
    chunks = [(1, "alpha"), (2, "beta")]
    written = build_index(tmp_path, _config(), chunks, transport=_transport)
    loaded = load_index(tmp_path, _config())
    assert loaded.chunk_ids == written.chunk_ids
    assert loaded.content_hashes == written.content_hashes
    assert loaded.model == written.model and loaded.dim == written.dim
    np.testing.assert_allclose(loaded.matrix, written.matrix)


def test_missing_index_is_reported_as_a_structured_failure(tmp_path: Path) -> None:
    with pytest.raises(SemanticError) as caught:
        load_index(tmp_path, _config())
    assert caught.value.code is ErrorCode.SEMANTIC_INDEX_MISSING


def test_changing_the_model_requires_a_rebuild(tmp_path: Path) -> None:
    build_index(tmp_path, _config(), [(1, "alpha")], transport=_transport)
    with pytest.raises(SemanticError) as caught:
        load_index(tmp_path, _config(model="other-model"))
    assert caught.value.code is ErrorCode.SEMANTIC_MODEL_MISMATCH


def test_corrupt_manifest_requires_a_rebuild(tmp_path: Path) -> None:
    build_index(tmp_path, _config(), [(1, "alpha")], transport=_transport)
    (vectors_dir(tmp_path) / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(SemanticError) as caught:
        load_index(tmp_path, _config())
    assert caught.value.code is ErrorCode.SEMANTIC_MODEL_MISMATCH


def test_manifest_missing_fields_requires_a_rebuild(tmp_path: Path) -> None:
    build_index(tmp_path, _config(), [(1, "alpha")], transport=_transport)
    manifest_path = vectors_dir(tmp_path) / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps({"model": "bge-m3"}), encoding="utf-8")
    with pytest.raises(SemanticError) as caught:
        load_index(tmp_path, _config())
    assert caught.value.code is ErrorCode.SEMANTIC_MODEL_MISMATCH


def test_save_index_writes_an_unmodified_matrix(tmp_path: Path) -> None:
    matrix = np.asarray([[1.0, 0.0], [0.0, 2.0]], dtype=np.float32)
    index = VectorIndex(
        model="bge-m3",
        dim=2,
        chunk_ids=(1, 2),
        content_hashes=(content_hash("a"), content_hash("b")),
        matrix=matrix,
        generated_at="2026-09-24T00:00:00+00:00",
    )
    save_index(tmp_path, index)
    reloaded = load_index(tmp_path, _config())
    np.testing.assert_allclose(reloaded.matrix, matrix)


class _Counting:
    """A text-only transport that records how many texts it was asked to embed."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def __call__(
        self, url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        batch = list(texts)
        self.texts.extend(batch)
        return [
            [float(len(text) % 7), float(text.count("a")), 1.0, 0.5] for text in batch
        ]


def test_build_refuses_an_empty_workspace(tmp_path: Path) -> None:
    with pytest.raises(SemanticError) as caught:
        build_index(tmp_path, _config(), [], transport=_transport)
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED


def test_first_build_embeds_every_chunk(tmp_path: Path) -> None:
    counter = _Counting()
    chunks = [(1, "alpha"), (2, "beta"), (3, "gamma")]
    build_index(tmp_path, _config(), chunks, transport=counter)
    assert len(counter.texts) == 3


def test_rebuild_reuses_unchanged_rows_and_embeds_only_the_change(tmp_path: Path) -> None:
    counter = _Counting()
    config = _config()
    original = build_index(
        tmp_path, config, [(1, "alpha"), (2, "beta"), (3, "gamma")], transport=counter
    )
    counter.texts.clear()
    changed = build_index(
        tmp_path, config, [(1, "alpha"), (2, "beta!"), (3, "gamma")], transport=counter
    )
    assert counter.texts == ["beta!"], "only the changed chunk may be re-embedded"
    np.testing.assert_allclose(changed.matrix[0], original.matrix[0])
    np.testing.assert_allclose(changed.matrix[2], original.matrix[2])
    assert changed.content_hashes[0] == original.content_hashes[0]
    assert changed.content_hashes[1] != original.content_hashes[1]


def test_rebuild_with_no_changes_never_calls_the_transport(tmp_path: Path) -> None:
    config = _config()
    chunks = [(1, "alpha"), (2, "beta")]
    first = build_index(tmp_path, config, chunks, transport=_Counting())

    def explode(url: str, model: str, texts: Sequence[str], timeout: float) -> list[list[float]]:
        raise AssertionError("an unchanged workspace must not be re-embedded")

    second = build_index(tmp_path, config, chunks, transport=explode)
    np.testing.assert_allclose(second.matrix, first.matrix)


def test_rebuild_after_a_model_change_embeds_every_chunk(tmp_path: Path) -> None:
    counter = _Counting()
    build_index(tmp_path, _config(), [(1, "alpha"), (2, "beta")], transport=counter)
    counter.texts.clear()
    build_index(tmp_path, _config(model="other"), [(1, "alpha"), (2, "beta")], transport=counter)
    assert sorted(counter.texts) == ["alpha", "beta"]


def test_rebuild_after_a_corrupt_manifest_embeds_every_chunk(tmp_path: Path) -> None:
    counter = _Counting()
    build_index(tmp_path, _config(), [(1, "alpha")], transport=counter)
    (vectors_dir(tmp_path) / MANIFEST_FILENAME).write_text("{broken", encoding="utf-8")
    counter.texts.clear()
    build_index(tmp_path, _config(), [(1, "alpha")], transport=counter)
    assert counter.texts == ["alpha"]


def test_rebuild_drops_removed_chunks_and_keeps_the_rest(tmp_path: Path) -> None:
    counter = _Counting()
    config = _config()
    original = build_index(
        tmp_path, config, [(1, "alpha"), (2, "beta"), (3, "gamma")], transport=counter
    )
    counter.texts.clear()
    rebuilt = build_index(tmp_path, config, [(1, "alpha"), (3, "gamma")], transport=counter)
    assert counter.texts == []
    assert rebuilt.chunk_ids == (1, 3)
    np.testing.assert_allclose(rebuilt.matrix[0], original.matrix[0])
    np.testing.assert_allclose(rebuilt.matrix[1], original.matrix[2])
