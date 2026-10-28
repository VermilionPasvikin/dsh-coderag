"""Vector-index administration CLI for the DSH settings page (T7-01).

`python -m dsh_coderag.admin status|health|vectorize --root <path>` is the
machine-facing surface behind the CodeRAG operations panel. `status` reports
what the workspace index and vector store contain, `health` probes the
configured embedding backend over HTTP, and `vectorize` streams JSON progress
while building the optional vector index through `vectors.build_index` and its
resumable `DiskEmbeddingCache` checkpoint (T6-31).

stdout is the protocol channel: every command writes only JSON, as one object
for `status` and `health` and as one object per line for `vectorize`.
Diagnostics go to stderr through `log_event`. This module does not search, does
not start the MCP server, does not write a second vector store, and never
prints or stores the API key (S-05, RL-02). Numpy is imported only by
`vectors.build_index`, so `status` reads the manifest without loading the
embedding matrix.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, TextIO

from dsh_coderag import vectors
from dsh_coderag.config import (
    DEFAULT_SEMANTIC_BACKEND,
    DEFAULT_SEMANTIC_MODEL,
    DEFAULT_SEMANTIC_URL,
    ENV_SEMANTIC,
    ENV_SEMANTIC_ALLOW_REMOTE,
    ENV_SEMANTIC_API_KEY,
    ENV_SEMANTIC_BACKEND,
    ENV_SEMANTIC_MODEL,
    ENV_SEMANTIC_URL,
    SEMANTIC_ALLOW_REMOTE_VALUE,
    SEMANTIC_ENABLED_VALUE,
    ConfigError,
    SemanticConfig,
    load_semantic_config,
)
from dsh_coderag.embed import (
    CHECKPOINT_FILENAME,
    DiskEmbeddingCache,
    SemanticError,
    Transport,
    _http_transport,
    count_checkpoint_records,
    open_without_redirects,
)
from dsh_coderag.log import log_event
from dsh_coderag.types import ErrorCode
from dsh_coderag.vectors import EMBEDDINGS_FILENAME, MANIFEST_FILENAME

EXIT_OK = 0
EXIT_FAILED = 1
HEALTH_TIMEOUT_S = 5.0
"""Total deadline for one health probe; the settings page must never hang on it."""

HEALTH_MAX_BODY_BYTES = 1024 * 1024
"""Upper bound on a health response body; `/models` never needs more than this."""

HEALTH_READ_CHUNK_BYTES = 64 * 1024
"""Bytes read per call while enforcing the health body cap."""

INDEX_SUBDIR = Path(".coderag")
INDEX_FILENAME = "index.sqlite3"
HEALTH_PATHS: dict[str, str] = {"ollama": "/api/tags", "openai": "/models"}
"""Endpoint appended to the configured base URL for each health check."""

ENV_SEMANTIC_KEY_PRESENT = "CODERAG_SEMANTIC_KEY_PRESENT"
"""Marker the Host sets for `status` so `key_present` needs no credential (T8-02)."""

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_REMOTE_NOT_ALLOWED = "REMOTE_NOT_ALLOWED"
_HEALTH_REQUEST_FAILED = "HEALTH_REQUEST_FAILED"
_HEALTH_INVALID_RESPONSE = "HEALTH_INVALID_RESPONSE"
_HEALTH_REDIRECT_REFUSED = "HEALTH_REDIRECT_REFUSED"
_HEALTH_TIMEOUT = "HEALTH_TIMEOUT"
_HEALTH_RESPONSE_TOO_LARGE = "HEALTH_RESPONSE_TOO_LARGE"
_VECTORIZE_FAILED = "VECTORIZE_FAILED"

_monotonic: Callable[[], float] = time.monotonic
"""Monotonic clock seam; tests replace it to prove the total health deadline."""


class _AdminFailure(Exception):
    """A command failure with the stable code and safe message a caller renders."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _ManifestFacts:
    """What `manifest.json` says, read without touching `embeddings.npy`.

    `exists` means both files of a vector store are present on disk. `pairs` is
    populated only when the manifest satisfies the same contract `vectors`
    requires for reuse, so a corrupt or half-written manifest contributes no
    reusable rows instead of raising.
    """

    exists: bool = False
    model: str | None = None
    dim: int | None = None
    generated_at: str | None = None
    pairs: frozenset[tuple[int, str]] = frozenset()


@dataclass(frozen=True)
class _VectorizePlan:
    """How `vectors.build_index` will split the still-missing chunks.

    `batches` mirrors `embed_texts`: unique missing texts in first-occurrence
    order, sliced by `config.batch`. `counts` maps each text to how many chunk
    rows it represents, and `baseline` is how many pending chunks the checkpoint
    already answers, so progress can count chunks rather than HTTP calls.
    """

    batches: tuple[tuple[str, ...], ...]
    counts: dict[str, int]
    baseline: int
    pending: int


class _ProgressTransport:
    """Forward to the real transport, emitting one progress object per batch.

    A retry of the same batch never reaches `_emit`, because the exception
    propagates before the counters move; only a successful call advances the
    plan. The reported count is pending chunks resolved so far (checkpoint hits
    plus freshly embedded rows), so `pending` reaches zero when the build ends.
    """

    def __init__(
        self,
        inner: Transport,
        plan: _VectorizePlan,
        emit: Callable[[dict[str, Any]], None],
    ) -> None:
        self._inner = inner
        self._plan = plan
        self._emit_event = emit
        self._next_batch = 0
        self._resolved = plan.baseline

    def __call__(
        self, url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        vectors = self._inner(url, model, texts, timeout)
        self._resolved = min(self._plan.pending, self._resolved + self._resolve_batch(len(texts)))
        self._emit_event(
            {
                "event": "progress",
                "embedded": self._resolved,
                "pending": self._plan.pending - self._resolved,
            }
        )
        return vectors

    def finish(self) -> None:
        """Emit a final progress object when no transport batch completed it."""
        if self._resolved >= self._plan.pending:
            return
        self._resolved = self._plan.pending
        self._emit_event({"event": "progress", "embedded": self._resolved, "pending": 0})

    def _resolve_batch(self, sent: int) -> int:
        """Return how many chunks one successful batch of `sent` texts resolved."""
        if self._next_batch >= len(self._plan.batches):
            return sent
        batch = self._plan.batches[self._next_batch]
        self._next_batch += 1
        if len(batch) != sent:
            return sent
        return sum(self._plan.counts[text] for text in batch)


def _index_path(root: Path) -> Path:
    """Return the workspace index path without creating anything."""
    return Path(root) / INDEX_SUBDIR / INDEX_FILENAME


def _open_index_readonly(path: Path) -> sqlite3.Connection:
    """Open an existing index read-only, so status cannot create or mutate it."""
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _read_chunk_pairs(root: Path) -> tuple[bool, list[tuple[int, str]]]:
    """Return whether the chunks table is readable and each (id, content_hash).

    A missing, unreadable or schema-less database is a normal "not indexed yet"
    state for the settings page, so it is reported as False with no rows rather
    than raised.
    """
    path = _index_path(root)
    if not path.is_file():
        return False, []
    try:
        connection = _open_index_readonly(path)
    except sqlite3.Error as exc:
        log_event("admin_index_unreadable", level="warning", error=type(exc).__name__)
        return False, []
    try:
        rows = connection.execute("SELECT id, content_hash FROM chunks ORDER BY id").fetchall()
    except sqlite3.Error as exc:
        log_event("admin_index_unreadable", level="warning", error=type(exc).__name__)
        return False, []
    finally:
        connection.close()
    return True, [(int(row[0]), str(row[1])) for row in rows]


def _read_manifest_facts(root: Path) -> _ManifestFacts:
    """Read the vector manifest's identity and row pairs without its matrix."""
    directory = vectors.vectors_dir(root)
    manifest_path = directory / MANIFEST_FILENAME
    if not manifest_path.is_file() or not (directory / EMBEDDINGS_FILENAME).is_file():
        return _ManifestFacts()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log_event(
            "admin_manifest_unreadable",
            level="warning",
            error=type(exc).__name__,
        )
        return _ManifestFacts(exists=True)
    return _facts_from_payload(payload)


def _facts_from_payload(payload: object) -> _ManifestFacts:
    """Validate a parsed manifest exactly as far as reuse requires."""
    if not isinstance(payload, dict):
        return _ManifestFacts(exists=True)
    model = payload.get("model")
    dim = payload.get("dim")
    generated_at = payload.get("generated_at")
    facts = _ManifestFacts(
        exists=True,
        model=model if isinstance(model, str) else None,
        dim=dim if isinstance(dim, int) else None,
        generated_at=generated_at if isinstance(generated_at, str) else None,
    )
    chunk_ids = payload.get("chunk_ids")
    hashes = payload.get("content_hashes")
    if (
        not isinstance(payload.get("format_version"), int)
        or not isinstance(model, str)
        or not isinstance(dim, int)
        or not isinstance(generated_at, str)
        or not isinstance(chunk_ids, list)
        or not isinstance(hashes, list)
        or len(chunk_ids) != len(hashes)
        or not all(isinstance(value, int) for value in chunk_ids)
        or not all(isinstance(value, str) for value in hashes)
    ):
        return facts
    pairs = frozenset(zip(chunk_ids, hashes, strict=True))
    return _ManifestFacts(
        exists=True,
        model=model,
        dim=dim,
        generated_at=generated_at,
        pairs=pairs,
    )


def _reusable_pairs(manifest: _ManifestFacts, config: SemanticConfig) -> frozenset[tuple[int, str]]:
    """Return manifest rows the next build may reuse for the configured model.

    A manifest built for another model cannot be validly reused: dimensions may
    differ and `vectors.load_index` refuses it. Counting its rows as vectorized
    would tell the settings page that no work is pending when a full rebuild is
    actually required.
    """
    if not manifest.exists or manifest.model != config.model:
        return frozenset()
    return manifest.pairs


def _checkpoint_path(root: Path, config: SemanticConfig) -> Path:
    """Return one model's checkpoint file without opening or loading it."""
    directory = vectors.vectors_dir(root) / vectors.CHECKPOINT_SUBDIR
    return directory / vectors.checkpoint_slug(config.model) / CHECKPOINT_FILENAME


def _checkpoint_vectors(root: Path, config: SemanticConfig) -> int:
    """Count checkpoint records read-only, never materializing their vectors.

    `vectors.checkpoint_cache` is deliberately not used here: its `load` builds
    the full in-memory vector dict and truncates a torn tail. A status poll can
    run while `vectorize` is appending, so counting must neither allocate the
    vectors nor write to the file being written (P1-3).
    """
    try:
        return count_checkpoint_records(_checkpoint_path(root, config))
    except (OSError, SemanticError) as exc:
        log_event(
            "admin_checkpoint_unreadable",
            level="warning",
            error=type(exc).__name__,
        )
        return 0


def _key_present(config: SemanticConfig) -> bool:
    """Report credential presence without resolving or printing the credential.

    The settings Host no longer passes the key to `status`; it passes the
    `CODERAG_SEMANTIC_KEY_PRESENT=1` marker instead, so a configured key is still
    visible in the panel while the secret stays out of the child process (S-05).
    """
    if config.api_key is not None:
        return True
    return _read_env(ENV_SEMANTIC_KEY_PRESENT) == "1"


def _config_facts(config: SemanticConfig) -> dict[str, Any]:
    """Return the non-secret configuration view the settings page renders."""
    return {
        "enabled": config.enabled,
        "backend": config.backend,
        "url": config.url,
        "model": config.model,
        "allow_remote": config.allow_remote,
        "key_present": _key_present(config),
    }


def _display_config() -> SemanticConfig:
    """Load the optional-backend settings, falling back to raw env for display.

    A half-filled cloud configuration (enabled, but URL or model still blank)
    makes `load_semantic_config` raise by design. The status card must stay
    usable while the user is editing those fields, so the fallback reports what
    is set instead of turning a settings draft into a CLI failure.
    """
    try:
        return load_semantic_config()
    except ConfigError as exc:
        log_event("admin_config_invalid", level="warning", message=str(exc))
        return _raw_semantic_config()


def _raw_semantic_config() -> SemanticConfig:
    """Build a display-only config from the environment without validation."""
    switch = _read_env(ENV_SEMANTIC)
    return SemanticConfig(
        enabled=switch == SEMANTIC_ENABLED_VALUE,
        backend=_read_env(ENV_SEMANTIC_BACKEND) or DEFAULT_SEMANTIC_BACKEND,
        url=_read_env(ENV_SEMANTIC_URL) or DEFAULT_SEMANTIC_URL,
        model=_read_env(ENV_SEMANTIC_MODEL) or DEFAULT_SEMANTIC_MODEL,
        api_key=_read_env(ENV_SEMANTIC_API_KEY),
        allow_remote=_read_env(ENV_SEMANTIC_ALLOW_REMOTE) == SEMANTIC_ALLOW_REMOTE_VALUE,
        switch_value=switch,
    )


def _read_env(name: str) -> str | None:
    """Return a stripped environment value, treating blank as unset."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip()


def status(root: Path, config: SemanticConfig | None = None) -> dict[str, Any]:
    """Report the index and vector store state as one JSON-serializable object.

    `chunks` rows are compared with the manifest by `(chunk_id, content_hash)`;
    the embedding matrix is never loaded. `vectorized_chunks` counts rows that
    are reusable under the configured model, `pending_chunks` is the remainder,
    and `stale_chunks` counts manifest rows that no longer match a current
    chunk. A workspace with no index and no vector store is a normal state:
    `ok` is True and the two `*_exists` booleans are False.

    `model` describes the store on disk when one exists and falls back to the
    configured model otherwise; `dim` and `generated_at` are null without a
    usable manifest. The API key is reported only as `config.key_present`.
    """
    settings = config if config is not None else _display_config()
    index_exists, chunk_pairs = _read_chunk_pairs(root)
    manifest = _read_manifest_facts(root)
    reusable = _reusable_pairs(manifest, settings)
    total = len(chunk_pairs)
    vectorized = sum(1 for pair in chunk_pairs if pair in reusable)
    current = set(chunk_pairs)
    return {
        "ok": True,
        "index_exists": index_exists,
        "vector_exists": manifest.exists,
        "model": manifest.model if manifest.model is not None else settings.model,
        "dim": manifest.dim,
        "total_chunks": total,
        "vectorized_chunks": vectorized,
        "pending_chunks": total - vectorized,
        "stale_chunks": len(manifest.pairs.difference(current)),
        "generated_at": manifest.generated_at,
        "checkpoint_vectors": _checkpoint_vectors(root, settings),
        "config": _config_facts(settings),
    }


def _host(url: str) -> str:
    """Return the lowercased host of one URL, or an empty string."""
    return (urllib.parse.urlparse(url).hostname or "").lower()


def _is_loopback(url: str) -> bool:
    """Return whether url points at this machine."""
    return _host(url) in _LOOPBACK_HOSTS


def _health_base(config: SemanticConfig) -> dict[str, Any]:
    """Return the fields every health payload carries, with a failed default."""
    return {
        "ok": False,
        "backend": config.backend,
        "url": config.url,
        "model": config.model,
        "model_present": False,
        "detail": "",
        "models": [],
    }


def _health_failure(config: SemanticConfig, code: str, message: str) -> dict[str, Any]:
    """Build one structured, credential-free health failure payload."""
    safe = _scrub(message, config.api_key)
    return {**_health_base(config), "detail": safe, "code": code, "message": safe}


def _read_bounded(response: IO[bytes], deadline: float) -> bytes:
    """Read a health body within the size cap and the monotonic-clock deadline.

    `urlopen`'s timeout applies to each blocking socket operation, so a
    slow-dripping server could otherwise keep a probe alive indefinitely. The
    deadline is re-checked around every chunk, and the accumulated body is
    capped at HEALTH_MAX_BODY_BYTES.

    Raises:
        _AdminFailure: HEALTH_RESPONSE_TOO_LARGE past the cap, or HEALTH_TIMEOUT
            once the deadline has passed; both are returned as structured JSON
            codes by the health command instead of an exception traceback.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        if _monotonic() >= deadline:
            raise _AdminFailure(
                _HEALTH_TIMEOUT,
                f"the health probe exceeded its {HEALTH_TIMEOUT_S:g}s deadline",
            )
        chunk = response.read(HEALTH_READ_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > HEALTH_MAX_BODY_BYTES:
            raise _AdminFailure(
                _HEALTH_RESPONSE_TOO_LARGE,
                f"the health response exceeded {HEALTH_MAX_BODY_BYTES} bytes; refusing to read it",
            )
        chunks.append(chunk)


def _fetch_models(config: SemanticConfig, path: str) -> list[str]:
    """GET one backend's model list, mapping every transport failure to a code.

    Only `openai` receives the credential, and only in the Authorization header;
    a rejected credential is never retried and is never echoed back (S-05). The
    request is opened by `embed.open_without_redirects`, so a 3xx cannot forward
    the header to the host named by its Location (T8-02).
    """
    url = config.url.rstrip("/") + path
    headers = {"Accept": "application/json"}
    if config.backend == "openai" and config.api_key is not None:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = urllib.request.Request(url, headers=headers)
    deadline = _monotonic() + HEALTH_TIMEOUT_S
    try:
        with open_without_redirects(request, HEALTH_TIMEOUT_S) as response:
            raw = _read_bounded(response, deadline)
    except urllib.error.HTTPError as exc:
        # The HTTPError owns the response socket; close it before the structured
        # code replaces the exception, or the probe leaks a ResourceWarning.
        try:
            if exc.code in (401, 403):
                raise _AdminFailure(
                    ErrorCode.SEMANTIC_AUTH_REJECTED.value,
                    f"{url} rejected the credential (HTTP {exc.code}); the key is not retried",
                ) from exc
            if 300 <= exc.code < 400:
                raise _AdminFailure(
                    _HEALTH_REDIRECT_REFUSED,
                    f"{url} answered HTTP {exc.code}; redirects are refused so the "
                    "credential cannot be forwarded to another host",
                ) from exc
            raise _AdminFailure(_HEALTH_REQUEST_FAILED, f"{url} answered HTTP {exc.code}") from exc
        finally:
            exc.close()
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise _AdminFailure(_HEALTH_TIMEOUT, f"the health probe to {url} timed out") from exc
        raise _AdminFailure(
            _HEALTH_REQUEST_FAILED, f"could not reach {url}: {type(exc).__name__}"
        ) from exc
    except TimeoutError as exc:
        raise _AdminFailure(_HEALTH_TIMEOUT, f"the health probe to {url} timed out") from exc
    except OSError as exc:
        raise _AdminFailure(
            _HEALTH_REQUEST_FAILED, f"could not reach {url}: {type(exc).__name__}"
        ) from exc
    return _models_from_payload(url, config.backend, raw)


def _models_from_payload(url: str, backend: str, raw: bytes) -> list[str]:
    """Extract model ids from Ollama's `models` or OpenAI's `data` shape."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _AdminFailure(
            _HEALTH_INVALID_RESPONSE,
            f"{url} did not return JSON: {type(exc).__name__}",
        ) from exc
    key = "models" if backend == "ollama" else "data"
    entries = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise _AdminFailure(_HEALTH_INVALID_RESPONSE, f"{url} returned an unexpected JSON shape")
    models: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("id")
        if isinstance(name, str) and name:
            models.append(name)
    return models


def _model_present(model: str, models: Sequence[str]) -> bool:
    """Return whether any reported model satisfies the configured name.

    Ollama reports tags (`bge-m3:latest`) while the configuration names the
    bare model, so the tag is ignored on both sides.
    """
    wanted = model.split(":", 1)[0]
    return any(name == model or name.split(":", 1)[0] == wanted for name in models)


def health(root: Path, config: SemanticConfig | None = None) -> dict[str, Any]:
    """Probe the configured embedding backend and return one JSON object.

    Ollama is checked at `/api/tags` and the OpenAI-compatible backend at
    `/models` with a Bearer key when one is configured. The probe is allowed
    only at a loopback URL or with `CODERAG_SEMANTIC_ALLOW_REMOTE=1` (S-01), has
    a five-second total deadline and a one-megabyte body cap, and refuses every
    redirect so the credential cannot be forwarded to another host (T8-02).
    This is a diagnostic probe, so it does not require `CODERAG_SEMANTIC` to be
    on.

    `ok` reports reachability; `model_present` separately reports whether the
    configured model is listed. Failures carry `code` and `message` and never a
    credential.
    """
    try:
        settings = config if config is not None else load_semantic_config()
    except ConfigError as exc:
        return _health_failure(_raw_semantic_config(), "CONFIG_INVALID", str(exc))
    path = HEALTH_PATHS.get(settings.backend)
    if path is None:
        return _health_failure(
            settings,
            ErrorCode.SEMANTIC_BACKEND_UNSUPPORTED.value,
            f"unsupported embedding backend {settings.backend!r}; supported: ollama, openai",
        )
    if not _is_loopback(settings.url) and not settings.allow_remote:
        return _health_failure(
            settings,
            _REMOTE_NOT_ALLOWED,
            f"{settings.url} is not loopback and {ENV_SEMANTIC_ALLOW_REMOTE} "
            "is not 1; refusing to contact a remote endpoint (S-01)",
        )
    try:
        models = _fetch_models(settings, path)
    except _AdminFailure as failure:
        return _health_failure(settings, failure.code, failure.message)
    present = _model_present(settings.model, models)
    detail = f"{settings.backend} at {settings.url} answered; {len(models)} model(s) available"
    if not present:
        detail += f"; model {settings.model!r} is not available"
    return {
        **_health_base(settings),
        "ok": True,
        "model_present": present,
        "detail": detail,
        "models": models,
    }


def _read_chunk_rows(root: Path) -> list[tuple[int, str, str]]:
    """Return (chunk_id, text, content_hash) for the build, or raise a coded failure."""
    path = _index_path(root)
    if not path.is_file():
        raise _AdminFailure(
            ErrorCode.INDEX_NOT_FOUND.value,
            f"no code index under {path}; index the workspace before vectorizing",
        )
    try:
        connection = _open_index_readonly(path)
    except sqlite3.Error as exc:
        raise _AdminFailure(
            ErrorCode.INDEX_READ_FAILED.value,
            f"cannot read {path}: {type(exc).__name__}",
        ) from exc
    try:
        rows = connection.execute(
            "SELECT id, text, content_hash FROM chunks ORDER BY id"
        ).fetchall()
    except sqlite3.Error as exc:
        raise _AdminFailure(
            ErrorCode.INDEX_READ_FAILED.value,
            f"cannot read chunks from {path}: {type(exc).__name__}",
        ) from exc
    finally:
        connection.close()
    if not rows:
        raise _AdminFailure(
            ErrorCode.SEMANTIC_EMBED_FAILED.value,
            "no chunks to vectorize; index the workspace before building vectors",
        )
    return [(int(row[0]), str(row[1]), str(row[2])) for row in rows]


def _open_checkpoint(root: Path, config: SemanticConfig) -> DiskEmbeddingCache:
    """Open the resumable checkpoint for the configured model, or fail coded."""
    try:
        return vectors.checkpoint_cache(root, config)
    except (OSError, SemanticError) as exc:
        raise _AdminFailure(
            "CHECKPOINT_UNREADABLE",
            f"cannot read the embedding checkpoint: {type(exc).__name__}",
        ) from exc


def _plan_vectorize(
    pending_rows: Sequence[tuple[int, str, str]],
    config: SemanticConfig,
    cache: DiskEmbeddingCache,
) -> _VectorizePlan:
    """Mirror `embed_texts`' dedup and batching over the still-missing chunks.

    Probing the checkpoint with the public `get` seam separates "already
    recovered" chunks from "must be sent", which is what lets progress count
    chunks accurately even when a text is shared by several rows.
    """
    counts: dict[str, int] = {}
    baseline = 0
    for _, text, _ in pending_rows:
        if cache.get(config.model, text) is not None:
            baseline += 1
        else:
            counts[text] = counts.get(text, 0) + 1
    unique = list(counts)
    batches = tuple(
        tuple(unique[start : start + config.batch]) for start in range(0, len(unique), config.batch)
    )
    # The probe above went through the public get seam, which counts hits and
    # misses. Reset those reporting counters so build_index's log describes the
    # real build instead of this planning pass.
    cache.hits = 0
    cache.misses = 0
    return _VectorizePlan(
        batches=batches,
        counts=counts,
        baseline=baseline,
        pending=len(pending_rows),
    )


def _transport_for(config: SemanticConfig, transport: Transport | None) -> Transport:
    """Return the injected transport, or the real one carrying the key."""
    if transport is not None:
        return transport

    def post(url: str, model: str, texts: Sequence[str], timeout: float) -> list[list[float]]:
        return _http_transport(url, model, texts, timeout, api_key=config.api_key)

    return post


def _emit_json(payload: dict[str, Any], stream: TextIO | None = None) -> None:
    """Write one compact JSON object on one line and flush it immediately."""
    target = sys.stdout if stream is None else stream
    target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    target.flush()


def _scrub(value: str, secret: str | None) -> str:
    """Remove a resolved credential from text that may surface to the caller."""
    if secret is None or secret == "":
        return value
    return value.replace(secret, "[redacted]")


def _vectorize_error(
    stream: TextIO | None, code: str, message: str, secret: str | None = None
) -> int:
    """Emit one `error` event, log it without content, and return the exit code."""
    safe = _scrub(message, secret)
    _emit_json({"event": "error", "code": code, "message": safe}, stream)
    log_event("admin_vectorize_failed", level="error", code=code, message=safe)
    return EXIT_FAILED


def _vectorize_rows(
    root: Path,
    settings: SemanticConfig,
    stream: TextIO,
    transport: Transport | None,
) -> int:
    """Run one resumable build, streaming start/progress/done objects."""
    rows = _read_chunk_rows(root)
    manifest = _read_manifest_facts(root)
    cache = _open_checkpoint(root, settings)
    try:
        reusable = _reusable_pairs(manifest, settings)
        pending_rows = [row for row in rows if (row[0], row[2]) not in reusable]
        _emit_json(
            {
                "event": "start",
                "total_chunks": len(rows),
                "pending_chunks": len(pending_rows),
                "checkpoint_vectors": cache.records,
            },
            stream,
        )
        plan = _plan_vectorize(pending_rows, settings, cache)
        progress = _ProgressTransport(
            _transport_for(settings, transport),
            plan,
            lambda event: _emit_json(event, stream),
        )
        index = vectors.build_index(
            root,
            settings,
            [(chunk_id, text) for chunk_id, text, _ in rows],
            cache=cache,
            transport=progress,
        )
        progress.finish()
        _emit_json(
            {
                "event": "done",
                "chunks": len(index.chunk_ids),
                "model": index.model,
                "generated_at": index.generated_at,
            },
            stream,
        )
        return EXIT_OK
    finally:
        cache.close()


def vectorize(
    root: Path,
    *,
    config: SemanticConfig | None = None,
    transport: Transport | None = None,
    out: TextIO | None = None,
) -> int:
    """Build or resume the vector index, streaming JSON Lines on stdout.

    The build reuses `vectors.build_index` and the existing `DiskEmbeddingCache`
    checkpoint, so a process killed by the Host keeps every vector already
    acknowledged; the next invocation recovers them and embeds only what is
    still missing. Output is `start`, then one `progress` per successful HTTP
    batch, then `done`; any failure emits one `error` object and returns 1.
    """
    stream = sys.stdout if out is None else out
    try:
        settings = config if config is not None else load_semantic_config()
    except ConfigError as exc:
        return _vectorize_error(stream, "CONFIG_INVALID", str(exc))
    if not settings.enabled:
        return _vectorize_error(
            stream,
            ErrorCode.SEMANTIC_BACKEND_UNAVAILABLE.value,
            f"{ENV_SEMANTIC} is not 'on', so no embedding backend is configured",
            settings.api_key,
        )
    try:
        return _vectorize_rows(root, settings, stream, transport)
    except _AdminFailure as failure:
        return _vectorize_error(stream, failure.code, failure.message, settings.api_key)
    except SemanticError as exc:
        return _vectorize_error(stream, exc.code.value, exc.message, settings.api_key)
    except OSError as exc:
        return _vectorize_error(
            stream,
            _VECTORIZE_FAILED,
            f"{type(exc).__name__}: {exc}",
            settings.api_key,
        )
    except Exception as exc:  # noqa: BLE001 - the streamed protocol needs an error line
        return _vectorize_error(stream, _VECTORIZE_FAILED, type(exc).__name__, settings.api_key)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the admin CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m dsh_coderag.admin",
        description="Vector-index administration for the CodeRAG settings page.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    commands = (
        ("status", "Report index and vector-store facts as one JSON object."),
        ("health", "Probe the embedding backend and print one JSON object."),
        ("vectorize", "Build or resume the vector index, streaming JSON lines."),
    )
    for name, help_text in commands:
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument(
            "--root",
            required=True,
            type=Path,
            help="Workspace root whose .coderag/ directory is inspected.",
        )
    return parser


def _report_error(command: str, code: str, message: str) -> int:
    """Report a non-vectorize command failure as one JSON object."""
    if command == "vectorize":
        return _vectorize_error(None, code, message)
    _emit_json({"ok": False, "code": code, "message": _scrub(message, _api_key())})
    return EXIT_FAILED


def _api_key() -> str | None:
    """Read the credential for scrubbing only; it is never emitted."""
    return _read_env(ENV_SEMANTIC_API_KEY)


def main(argv: list[str] | None = None) -> int:
    """Run one admin command and return its process exit code."""
    args = build_parser().parse_args(argv)
    root: Path = args.root
    try:
        if args.command == "status":
            _emit_json(status(root))
            return EXIT_OK
        if args.command == "health":
            _emit_json(health(root))
            return EXIT_OK
        return vectorize(root)
    except ConfigError as exc:
        return _report_error(args.command, "CONFIG_INVALID", str(exc))
    except KeyboardInterrupt:
        return _report_error(
            args.command,
            ErrorCode.CANCELLED.value,
            "operation interrupted; the vector checkpoint is kept",
        )
    except Exception as exc:  # noqa: BLE001 - a traceback is not a CLI contract (RL-09)
        log_event("admin_unexpected_error", level="error", error=type(exc).__name__)
        return _report_error(args.command, "ADMIN_UNEXPECTED_ERROR", type(exc).__name__)


if __name__ == "__main__":
    sys.exit(main())
