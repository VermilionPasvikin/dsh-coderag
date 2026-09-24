"""Optional vector index storage and brute-force cosine ranking (ADR-16 5).

The vector index lives inside the workspace at `<root>/.coderag/vectors/`, as
`embeddings.npy` (float32, one row per chunk in ascending chunk-id order) plus
`manifest.json` (model, dimension, chunk ids, per-chunk content hashes,
generation time and format version). Nothing here ever writes outside the
workspace (S-03), and nothing is truncated silently: exceeding
CODERAG_SEMANTIC_MAX_CHUNKS fails and reports the real count (RL-08).

numpy is imported lazily, so the default BM25 path never needs the optional
extra (RL-10). This module does not search, does not fuse with BM25 and does not
render model-visible text; fusion is T3-10.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from dsh_coderag.config import SemanticConfig
from dsh_coderag.embed import EmbeddingCache, SemanticError, Transport, embed_texts
from dsh_coderag.log import log_event
from dsh_coderag.types import ErrorCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

VECTORS_SUBDIR = Path(".coderag") / "vectors"
EMBEDDINGS_FILENAME = "embeddings.npy"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_FORMAT_VERSION = 1


@dataclass(frozen=True)
class VectorIndex:
    """One loaded vector index: a float32 row per chunk, in chunk-id order."""

    model: str
    dim: int
    chunk_ids: tuple[int, ...]
    content_hashes: tuple[str, ...]
    matrix: np.ndarray[Any, Any]
    generated_at: str
    format_version: int = MANIFEST_FORMAT_VERSION


def _numpy() -> Any:
    """Import numpy on demand.

    Raises:
        SemanticError: SEMANTIC_BACKEND_UNAVAILABLE when the optional extra is
            not installed. The default BM25 path never reaches here (RL-10).
    """
    try:
        import numpy
    except ModuleNotFoundError as exc:
        raise SemanticError(
            ErrorCode.SEMANTIC_BACKEND_UNAVAILABLE,
            "numpy is required for the optional vector backend",
            'install the optional extra: pip install -e ".[semantic]"',
        ) from exc
    return numpy


def vectors_dir(root: Path) -> Path:
    """Return the vector index directory, asserting it stays inside the root.

    Raises:
        SemanticError: SEMANTIC_EMBED_FAILED when the resolved path would leave
            the workspace, which S-03 forbids.
    """
    base = Path(root).resolve()
    directory = (base / VECTORS_SUBDIR).resolve()
    if base != directory and base not in directory.parents:
        raise SemanticError(
            ErrorCode.SEMANTIC_EMBED_FAILED,
            f"vector index path {directory} would leave the workspace {base}",
            "the index must live under <root>/.coderag/vectors/",
        )
    return directory


def content_hash(text: str) -> str:
    """Return the sha256 of one chunk's text, used for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_chunk_budget(config: SemanticConfig, chunk_count: int) -> None:
    """Refuse to vectorize more chunks than the configured ceiling.

    Raises:
        SemanticError: SEMANTIC_INDEX_TOO_LARGE naming the actual count and the
            configured ceiling. Nothing is truncated (RL-08).
    """
    if chunk_count > config.max_chunks:
        raise SemanticError(
            ErrorCode.SEMANTIC_INDEX_TOO_LARGE,
            f"{chunk_count} chunks exceed CODERAG_SEMANTIC_MAX_CHUNKS="
            f"{config.max_chunks}; nothing was truncated",
            "raise CODERAG_SEMANTIC_MAX_CHUNKS or index a smaller workspace",
        )


def build_index(
    root: Path,
    config: SemanticConfig,
    chunks: Sequence[tuple[int, str]],
    *,
    cache: EmbeddingCache | None = None,
    transport: Transport | None = None,
) -> VectorIndex:
    """Embed the chunks and persist the vector index, reusing unchanged rows.

    `chunks` are (chunk_id, text) pairs in ascending chunk-id order, the row
    order frozen by ADR-16 5. A row whose chunk id and content hash both match
    the index already on disk is copied instead of re-embedded, so a re-index
    only pays for what changed.

    Raises:
        SemanticError: SEMANTIC_INDEX_TOO_LARGE past the configured ceiling, or
            whatever `embed_texts` raises (see its docstring).
    """
    check_chunk_budget(config, len(chunks))
    _require_chunks(chunks)
    numpy = _numpy()
    texts = [text for _, text in chunks]
    ids = [chunk_id for chunk_id, _ in chunks]
    hashes = [content_hash(text) for text in texts]
    previous = _load_previous(root, config)
    matrix, pending = _seed_from_previous(numpy, previous, ids, hashes)
    matrix = _fill_pending(numpy, matrix, config, texts, pending, cache, transport)
    log_event(
        "semantic_index_built",
        model=config.model,
        chunks=len(ids),
        reused=len(ids) - len(pending),
        embedded=len(pending),
    )
    index = VectorIndex(
        model=config.model,
        dim=int(matrix.shape[1]),
        chunk_ids=tuple(ids),
        content_hashes=tuple(hashes),
        matrix=matrix,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    save_index(root, index)
    return index


def _require_chunks(chunks: Sequence[tuple[int, str]]) -> None:
    """Refuse to write a vector index for a workspace with no chunks.

    Raises:
        SemanticError: SEMANTIC_EMBED_FAILED; an empty index would be a file
            that claims to exist but can never answer a query (RL-08).
    """
    if not chunks:
        raise SemanticError(
            ErrorCode.SEMANTIC_EMBED_FAILED,
            "no chunks to vectorize; nothing was written",
            "index the workspace before building the vector index",
        )


def _fill_pending(
    numpy: Any,
    matrix: Any | None,
    config: SemanticConfig,
    texts: Sequence[str],
    pending: Sequence[int],
    cache: EmbeddingCache | None,
    transport: Transport | None,
) -> Any:
    """Embed the pending rows into the matrix, allocating it when it is new.

    Raises:
        SemanticError: SEMANTIC_EMBED_FAILED when no matrix could be produced.
    """
    if pending:
        embedded = embed_texts(
            config,
            [texts[row] for row in pending],
            cache=cache,
            transport=transport,
        )
        if matrix is None:
            matrix = numpy.asarray(embedded, dtype=numpy.float32)
        else:
            for row, vector in zip(pending, embedded, strict=True):
                matrix[row] = numpy.asarray(vector, dtype=numpy.float32)
    if matrix is None:
        raise SemanticError(
            ErrorCode.SEMANTIC_EMBED_FAILED,
            "internal error: no vector matrix was produced",
        )
    return matrix


def _load_previous(root: Path, config: SemanticConfig) -> VectorIndex | None:
    """Load the existing index so unchanged rows can be reused.

    Returns None when there is nothing compatible to reuse; that is the normal
    first-run and post-model-change path, so the reason is logged rather than
    raised (a rebuild is always a correct answer, just a slower one).
    """
    try:
        return load_index(root, config)
    except SemanticError as exc:
        log_event(
            "semantic_index_no_reuse",
            code=exc.code.value,
            reason=exc.message,
        )
        return None


def _seed_from_previous(
    numpy: Any,
    previous: VectorIndex | None,
    chunk_ids: Sequence[int],
    content_hashes: Sequence[str],
) -> tuple[Any | None, list[int]]:
    """Copy unchanged rows out of `previous`; return the matrix and pending rows.

    A row is reused only when both its chunk id and its content hash still
    match, so an edit to a file re-embeds that file's chunks (its rows are
    rewritten under new ids) while untouched files cost nothing. When there is
    no previous index the matrix is None and every row is pending.
    """
    if previous is None:
        return None, list(range(len(chunk_ids)))
    reusable = {
        (chunk_id, digest): row
        for row, (chunk_id, digest) in enumerate(
            zip(previous.chunk_ids, previous.content_hashes, strict=True)
        )
    }
    matrix = numpy.empty((len(chunk_ids), previous.dim), dtype=numpy.float32)
    pending: list[int] = []
    for row, (chunk_id, digest) in enumerate(
        zip(chunk_ids, content_hashes, strict=True)
    ):
        old_row = reusable.get((chunk_id, digest))
        if old_row is None:
            pending.append(row)
        else:
            matrix[row] = previous.matrix[old_row]
    return matrix, pending


def save_index(root: Path, index: VectorIndex) -> Path:
    """Write `embeddings.npy` and `manifest.json` for one index.

    Returns:
        The vectors directory that was written.
    """
    directory = vectors_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    numpy = _numpy()
    numpy.save(directory / EMBEDDINGS_FILENAME, index.matrix)
    manifest = {
        "format_version": index.format_version,
        "model": index.model,
        "dim": index.dim,
        "chunk_count": len(index.chunk_ids),
        "chunk_ids": list(index.chunk_ids),
        "content_hashes": list(index.content_hashes),
        "generated_at": index.generated_at,
    }
    (directory / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return directory


def load_index(root: Path, config: SemanticConfig) -> VectorIndex:
    """Load the persisted vector index, or raise a structured failure.

    Raises:
        SemanticError: SEMANTIC_INDEX_MISSING when nothing has been written yet,
            SEMANTIC_MODEL_MISMATCH when the manifest's model or dimension no
            longer matches the current configuration or the stored matrix.
    """
    directory = vectors_dir(root)
    manifest_path = directory / MANIFEST_FILENAME
    matrix_path = directory / EMBEDDINGS_FILENAME
    if not manifest_path.is_file() or not matrix_path.is_file():
        raise SemanticError(
            ErrorCode.SEMANTIC_INDEX_MISSING,
            f"no vector index under {directory}",
            "run code_index with the optional backend enabled, then retry",
        )
    manifest = _read_manifest(manifest_path)
    numpy = _numpy()
    matrix = numpy.load(matrix_path)
    stored_model = manifest["model"]
    stored_dim = manifest["dim"]
    if stored_model != config.model or int(matrix.shape[1]) != stored_dim:
        raise SemanticError(
            ErrorCode.SEMANTIC_MODEL_MISMATCH,
            f"vector index was built for model {stored_model!r} (dim {stored_dim}), "
            f"but the configured model is {config.model!r} (dim {matrix.shape[1]})",
            "rebuild the vector index with code_index",
        )
    return VectorIndex(
        model=stored_model,
        dim=stored_dim,
        chunk_ids=tuple(manifest["chunk_ids"]),
        content_hashes=tuple(manifest["content_hashes"]),
        matrix=matrix,
        generated_at=manifest["generated_at"],
        format_version=manifest["format_version"],
    )


class _Manifest(TypedDict):
    """The validated shape of manifest.json (extra keys are ignored)."""

    format_version: int
    model: str
    dim: int
    chunk_ids: list[int]
    content_hashes: list[str]
    generated_at: str


def _invalid_manifest(path: Path, reason: str) -> SemanticError:
    """Build the structured failure used for every malformed manifest."""
    return SemanticError(
        ErrorCode.SEMANTIC_MODEL_MISMATCH,
        f"{path} is not a usable vector manifest: {reason}",
        "rebuild the vector index with code_index",
    )


def _read_manifest(path: Path) -> _Manifest:
    """Parse and validate one manifest file.

    Raises:
        SemanticError: SEMANTIC_MODEL_MISMATCH when the file is unreadable, is
            not JSON, or does not match the manifest contract. A corrupt
            manifest can only be fixed by rebuilding.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _invalid_manifest(path, str(exc)) from exc
    if not isinstance(payload, dict):
        raise _invalid_manifest(path, "top level is not a JSON object")
    format_version = payload.get("format_version")
    model = payload.get("model")
    dim = payload.get("dim")
    chunk_ids = payload.get("chunk_ids")
    hashes = payload.get("content_hashes")
    generated_at = payload.get("generated_at")
    if not isinstance(format_version, int) or not isinstance(model, str):
        raise _invalid_manifest(path, "format_version/model have the wrong type")
    if not isinstance(dim, int) or not isinstance(generated_at, str):
        raise _invalid_manifest(path, "dim/generated_at have the wrong type")
    if not isinstance(chunk_ids, list) or not all(isinstance(v, int) for v in chunk_ids):
        raise _invalid_manifest(path, "chunk_ids must be a list of integers")
    if not isinstance(hashes, list) or not all(isinstance(v, str) for v in hashes):
        raise _invalid_manifest(path, "content_hashes must be a list of strings")
    return _Manifest(
        format_version=format_version,
        model=model,
        dim=dim,
        chunk_ids=chunk_ids,
        content_hashes=hashes,
        generated_at=generated_at,
    )


def cosine_top_k(
    matrix: np.ndarray[Any, Any],
    query_vector: Sequence[float],
    k: int,
    tier: Sequence[int] | None = None,
) -> list[tuple[int, float]]:
    """Return the k best (row index, cosine) pairs, highest cosine first.

    The comparison is a plain brute-force dot product on L2-normalized rows,
    which is what ADR-14 allows below 100k chunks: no vector database.

    `tier` is an optional per-row rank class (0 before 1). It is applied
    **before** the top-k cut, which is what makes the frozen non-test-first
    ordering effective: cutting first would let a run of test chunks fill every
    slot and the real implementation would never reach the caller at all
    (ADR-16, update of 2026-09-24).

    Float32 BLAS on macOS (Accelerate) raises spurious divide-by-zero and
    overflow flags for large products; results are verified finite here and the
    flags are suppressed so they cannot pollute the JSON-Lines error log.
    """
    numpy = _numpy()
    rows = numpy.asarray(matrix, dtype=numpy.float32)
    query = numpy.asarray(query_vector, dtype=numpy.float32)
    if rows.size == 0:
        return []
    row_norms = numpy.linalg.norm(rows, axis=1)
    query_norm = float(numpy.linalg.norm(query))
    if query_norm == 0.0:
        return []
    safe_norms = numpy.where(row_norms == 0.0, 1.0, row_norms)
    with numpy.errstate(all="ignore"):
        scores = (rows @ query) / (safe_norms * query_norm)
    scores = numpy.where(row_norms == 0.0, 0.0, scores)
    if not bool(numpy.isfinite(scores).all()):
        raise SemanticError(
            ErrorCode.SEMANTIC_EMBED_FAILED,
            "cosine scoring produced non-finite values",
            "rebuild the vector index; the stored matrix or the query is corrupt",
        )
    order = numpy.argsort(-scores, kind="stable")
    if tier is not None:
        classes = numpy.asarray(tier, dtype=numpy.int8)
        order = order[numpy.argsort(classes[order], kind="stable")]
    order = order[:k]
    return [(int(index), float(scores[int(index)])) for index in order]
