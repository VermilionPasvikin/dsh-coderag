"""Optional embedding generation and caching (ADR-16 4-6, ADR-17 4-6).

This module talks to an embedding backend over HTTP and caches the vectors it
receives. It does not rank, does not persist a vector index and does not import
numpy: storing vectors and computing cosine is T3-09, RRF fusion and BM25
fallback are T3-10, and the cloud backend is T5-20.

When CODERAG_SEMANTIC is not `on` nothing here runs, so importing this module
must never touch the network, never require numpy and never block startup
(RL-10). Failures are raised as SemanticError carrying one of the frozen
ErrorCode values, so the caller can report a structured status and keep serving
BM25 instead of turning it into an MCP isError (RL-06, RL-09).
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from dsh_coderag.config import ENV_SEMANTIC, SemanticConfig
from dsh_coderag.log import log_event
from dsh_coderag.types import ErrorCode

RETRY_LIMIT = 2
"""Extra attempts after the first one; retries are always bounded (ADR-16 6)."""

_ENDPOINT_PATHS: dict[str, str] = {"ollama": "/api/embed"}
"""Request path per backend. T5-20 adds the `openai` entry (`/embeddings`)."""

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

_SUPPORTED_BACKENDS = frozenset(_ENDPOINT_PATHS)


class SemanticError(Exception):
    """An optional-backend failure carrying one frozen ErrorCode.

    Callers turn this into a structured status and keep serving BM25; it must
    never reach the MCP layer as an isError (RL-09).
    """

    def __init__(self, code: ErrorCode, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


Transport = Callable[[str, str, Sequence[str], float], list[list[float]]]
"""HTTP seam: (url, model, texts, timeout) -> one vector per text."""


@dataclass
class EmbeddingCache:
    """In-process cache of embeddings keyed by (model, sha256(text)).

    The cache makes a repeated chunk text cost nothing. It is owned by the
    caller, so no cache size is hardcoded here (RL-07); `hits` and `misses`
    exist so a caller can report cache behaviour.

    The key is a digest, never the text itself, so the cache never holds a
    second copy of code content under a model name.
    """

    hits: int = 0
    misses: int = 0
    _vectors: dict[tuple[str, str], list[float]] = field(default_factory=dict)

    def get(self, model: str, text: str) -> list[float] | None:
        """Return the cached vector for text under model, or None."""
        vector = self._vectors.get((model, _text_key(text)))
        if vector is None:
            self.misses += 1
        else:
            self.hits += 1
        return vector

    def put(self, model: str, text: str, vector: list[float]) -> None:
        """Store one vector for text under model."""
        self._vectors[(model, _text_key(text))] = vector


def _text_key(text: str) -> str:
    """Return the cache key of one text (a digest, so text is not the key)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _host_of(url: str) -> str:
    """Return the lowercased host of url, or an empty string when it has none."""
    return (urllib.parse.urlparse(url).hostname or "").lower()


def endpoint_for(config: SemanticConfig) -> str:
    """Return the request URL for the configured backend.

    Raises:
        SemanticError: SEMANTIC_BACKEND_UNSUPPORTED for a backend this version
            cannot talk to. It carries a code rather than a traceback so the
            caller can degrade to BM25 (RL-09).
    """
    path = _ENDPOINT_PATHS.get(config.backend)
    if path is None:
        raise SemanticError(
            ErrorCode.SEMANTIC_BACKEND_UNSUPPORTED,
            f"unsupported embedding backend {config.backend!r}",
            "supported backends: " + ", ".join(sorted(_SUPPORTED_BACKENDS)),
        )
    return config.url.rstrip("/") + path


def validate_local_backend(config: SemanticConfig) -> None:
    """Refuse a local backend that points off this machine (ADR-16 8.1).

    Raises:
        SemanticError: SEMANTIC_BACKEND_NOT_LOCAL when the `ollama` backend's
            URL is not loopback. This is the last gate before user code would
            be sent somewhere unexpected.
    """
    if config.backend == "ollama" and _host_of(config.url) not in _LOOPBACK_HOSTS:
        raise SemanticError(
            ErrorCode.SEMANTIC_BACKEND_NOT_LOCAL,
            f"the local Ollama backend refuses non-loopback URL {config.url!r}",
            "point CODERAG_SEMANTIC_URL at 127.0.0.1, ::1 or localhost",
        )


def _http_transport(
    url: str, model: str, texts: Sequence[str], timeout: float
) -> list[list[float]]:
    """POST one batch and parse the returned vectors.

    Only `embeddings` is read. A response whose length differs from the request
    cannot be trusted, so it fails loudly instead of silently truncating
    (RL-08).

    Raises:
        ValueError: If the response is not JSON, is not an object, or does not
            carry exactly one vector per input.
    """
    body = json.dumps({"model": model, "input": list(texts)}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        actual = len(embeddings) if isinstance(embeddings, list) else None
        raise ValueError(
            f"embedding response carried {actual} vectors for {len(texts)} inputs"
        )
    return [[float(value) for value in vector] for vector in embeddings]


def _post_with_retry(
    post: Transport,
    url: str,
    model: str,
    texts: Sequence[str],
    timeout: float,
    retry_limit: int = RETRY_LIMIT,
) -> list[list[float]]:
    """Call the transport, retrying at most retry_limit times (ADR-16 6).

    Raises:
        SemanticError: SEMANTIC_EMBED_FAILED after the last attempt. The message
            names the URL, the model and the attempt count, and never includes
            a credential (S-05).
    """
    last: Exception | None = None
    for attempt in range(1, retry_limit + 2):
        try:
            return post(url, model, texts, timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            log_event(
                "semantic_embed_attempt_failed",
                level="warning",
                url=url,
                model=model,
                attempt=attempt,
                error=type(exc).__name__,
            )
    raise SemanticError(
        ErrorCode.SEMANTIC_EMBED_FAILED,
        f"embedding request to {url} (model {model}) failed after "
        f"{retry_limit + 1} attempts: {type(last).__name__}",
        "check that the backend is running, the model is pulled and "
        "CODERAG_SEMANTIC_URL / _TIMEOUT are correct",
    ) from last


def embed_texts(
    config: SemanticConfig,
    texts: Sequence[str],
    *,
    cache: EmbeddingCache | None = None,
    transport: Transport | None = None,
) -> list[list[float]]:
    """Embed every text in order, serving repeat texts from cache.

    Texts are deduplicated within the call and sent in batches of
    `config.batch`, so the request count follows the configuration instead of a
    hardcoded constant (RL-07).

    Args:
        config: Settings from `load_semantic_config`.
        texts: Texts to embed, in order.
        cache: Optional cache reused across calls; when absent nothing is cached.
        transport: HTTP seam; defaults to the urllib implementation.

    Returns:
        One vector per input text, in the input order.

    Raises:
        SemanticError: SEMANTIC_BACKEND_UNAVAILABLE when the backend is off,
            SEMANTIC_BACKEND_UNSUPPORTED / SEMANTIC_BACKEND_NOT_LOCAL when the
            configuration is refused, SEMANTIC_EMBED_FAILED when the backend
            keeps failing.
    """
    if not config.enabled:
        raise SemanticError(
            ErrorCode.SEMANTIC_BACKEND_UNAVAILABLE,
            f"{ENV_SEMANTIC} is not 'on', so no embedding backend is configured",
            "enable the optional backend explicitly, or keep using BM25",
        )
    validate_local_backend(config)
    url = endpoint_for(config)
    post = transport if transport is not None else _http_transport

    vectors: list[list[float] | None] = [None] * len(texts)
    pending: dict[str, list[int]] = {}
    _fill_from_cache(config, texts, cache, vectors, pending)
    if pending:
        embedded = _embed_pending(config, post, url, pending, cache)
        for text, indices in pending.items():
            for index in indices:
                vectors[index] = embedded[text]
    return _require_complete(vectors)


def _fill_from_cache(
    config: SemanticConfig,
    texts: Sequence[str],
    cache: EmbeddingCache | None,
    vectors: list[list[float] | None],
    pending: dict[str, list[int]],
) -> None:
    """Fill cache hits in place and group the remaining positions by text."""
    for index, text in enumerate(texts):
        cached = cache.get(config.model, text) if cache is not None else None
        if cached is not None:
            vectors[index] = cached
        else:
            pending.setdefault(text, []).append(index)


def _embed_pending(
    config: SemanticConfig,
    post: Transport,
    url: str,
    pending: dict[str, list[int]],
    cache: EmbeddingCache | None,
) -> dict[str, list[float]]:
    """Embed each pending text once, in batches of `config.batch`.

    Raises:
        SemanticError: SEMANTIC_EMBED_FAILED when a batch comes back with the
            wrong number of vectors (never a silent truncation, RL-08).
    """
    unique = list(pending)
    embedded: dict[str, list[float]] = {}
    for start in range(0, len(unique), config.batch):
        batch_texts = unique[start : start + config.batch]
        batch = _post_with_retry(
            post, url, config.model, batch_texts, float(config.timeout_s)
        )
        if len(batch) != len(batch_texts):
            raise SemanticError(
                ErrorCode.SEMANTIC_EMBED_FAILED,
                f"transport returned {len(batch)} vectors for {len(batch_texts)} inputs",
            )
        for text, vector in zip(batch_texts, batch, strict=True):
            if cache is not None:
                cache.put(config.model, text, vector)
            embedded[text] = vector
    return embedded


def _require_complete(vectors: Sequence[list[float] | None]) -> list[list[float]]:
    """Return every vector, failing loudly if any text was left unresolved."""
    resolved: list[list[float]] = []
    for candidate in vectors:
        if candidate is None:
            raise SemanticError(
                ErrorCode.SEMANTIC_EMBED_FAILED,
                "internal error: at least one text was left without an embedding",
            )
        resolved.append(candidate)
    return resolved
