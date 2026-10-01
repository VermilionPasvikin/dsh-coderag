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
from functools import partial

from dsh_coderag.config import ENV_SEMANTIC, ENV_SEMANTIC_API_KEY, SemanticConfig
from dsh_coderag.log import log_event
from dsh_coderag.types import ErrorCode

RETRY_LIMIT = 2
"""Extra attempts after the first one; retries are always bounded (ADR-16 6)."""

_ENDPOINT_PATHS: dict[str, str] = {"ollama": "/api/embed", "openai": "/embeddings"}
"""Request path per backend, appended to the configured URL."""

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

DEFAULT_CONTEXT_TOKENS = 2048
"""Context assumed for the local backend until `/api/show` answers (T6-29)."""

CHARS_PER_TOKEN_BUDGET = 2
"""Characters per token assumed when deciding how much of a chunk to send.

Measured on this corpus: 2.05 (Qwen tokenizer) to 4.46 (BERT-ish) characters per
token, and 2.0 for the densest XML tested. Two is therefore the conservative end,
so what this engine sends normally fits the model's context; content denser than
that is still cut by the server, which is exactly why the count below exists — the
loss is ours, counted and logged, instead of silent. With a 2,048-token model that
means 4,096 characters per chunk; `bge-m3` (8,192) would allow 16,384 and cut
essentially nothing in this corpus.
"""

_CONTEXT_CACHE: dict[str, int] = {}
"""Model name to context length, remembered for the process (one probe per model)."""

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


def _require_credentials(config: SemanticConfig) -> None:
    """Refuse a remote OpenAI-compatible endpoint that has no key (T6-27).

    A loopback endpoint is deliberately exempt: local OpenAI-compatible servers
    (LM Studio, vLLM, llama.cpp) usually need no credential, and demanding one
    would break the offline case (S-01).

    Raises:
        SemanticError: SEMANTIC_AUTH_MISSING, raised before any request is made.
    """
    if config.backend != "openai" or config.api_key is not None:
        return
    if _host_of(config.url) in _LOOPBACK_HOSTS:
        return
    raise SemanticError(
        ErrorCode.SEMANTIC_AUTH_MISSING,
        f"the {config.backend} backend at {config.url} needs an API key and none is set",
        f"set {ENV_SEMANTIC_API_KEY} (in the environment, or in the profile's "
        f"cordis.patch.yml for the desktop app) and retry",
    )


def _auth_rejected(url: str) -> SemanticError:
    """Build the non-retryable rejection error for an HTTP 401/403 (T6-27).

    The message names the URL only: a rejected credential is never echoed back
    into a message, a log line or a status payload (S-05, RL-02).
    """
    return SemanticError(
        ErrorCode.SEMANTIC_AUTH_REJECTED,
        f"the embedding backend at {url} rejected the credential (HTTP 401/403)",
        f"check {ENV_SEMANTIC_API_KEY}; a rejected key is not retried",
    )


def _http_transport(
    url: str,
    model: str,
    texts: Sequence[str],
    timeout: float,
    *,
    api_key: str | None = None,
) -> list[list[float]]:
    """POST one batch and parse the returned vectors.

    Only `embeddings` is read. A response whose length differs from the request
    cannot be trusted, so it fails loudly instead of silently truncating
    (RL-08). The credential, when there is one, travels in an
    `Authorization: Bearer` header — the one place it is used, never logged.

    Raises:
        SemanticError: SEMANTIC_AUTH_REJECTED on HTTP 401/403. It is raised as a
            SemanticError rather than an HTTPError so the retry loop lets it
            through instead of retrying a credential that will keep failing.
        ValueError: If the response is not JSON, is not an object, or does not
            carry exactly one vector per input.
    """
    body = json.dumps({"model": model, "input": list(texts)}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise _auth_rejected(url) from error
        raise
    return _vectors_from(payload, len(texts))


def _vectors_from(payload: object, expected: int) -> list[list[float]]:
    """Read the vectors out of either documented response shape (T6-28).

    An OpenAI-compatible endpoint answers
    `{"data": [{"embedding": [...], "index": 0}, ...], "usage": {...}}`, while
    Ollama's `/api/embed` answers `{"embeddings": [[...], ...]}`. Both are
    accepted — verified against a live compatible endpoint on 2026-09-30, which
    returned `data` and no `embeddings` at all — and the row count is still
    enforced, so a truncated or reordered response cannot pass silently (RL-08).

    Raises:
        ValueError: If neither shape is present, a row is not a vector, or the
            count differs from the number of inputs.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"embedding response was {type(payload).__name__}, not an object")
    rows = payload.get("embeddings")
    if isinstance(rows, list):
        vectors: list[object] = list(rows)
    else:
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError(
                "embedding response carried neither 'embeddings' nor 'data'"
            )
        ordered = sorted(
            (row for row in data if isinstance(row, dict)),
            key=lambda row: row.get("index", 0),
        )
        vectors = [row.get("embedding") for row in ordered]
    if len(vectors) != expected:
        raise ValueError(
            f"embedding response carried {len(vectors)} vectors for {expected} inputs"
        )
    result: list[list[float]] = []
    for vector in vectors:
        if not isinstance(vector, list):
            raise ValueError("embedding response carried a row that is not a vector")
        result.append([float(value) for value in vector])
    return result


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


def _local_context_tokens(config: SemanticConfig) -> int:
    """Ask the local backend how many tokens its model accepts (T6-29).

    `/api/show` reports the model's own `*.context_length`; on this machine that is
    2,048 for `nomic-embed-text`, which is exactly where Ollama silently cut every
    longer input. The probe is cached per model, never raises, and falls back to
    DEFAULT_CONTEXT_TOKENS so a missing or older server cannot break a build.
    """
    if config.model in _CONTEXT_CACHE:
        return _CONTEXT_CACHE[config.model]
    context = DEFAULT_CONTEXT_TOKENS
    try:
        body = json.dumps({"model": config.model}).encode("utf-8")
        request = urllib.request.Request(
            config.url.rstrip("/") + "/api/show",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
        info = payload.get("model_info") if isinstance(payload, dict) else None
        if isinstance(info, dict):
            for key, value in info.items():
                if key.endswith("context_length") and isinstance(value, int) and value > 0:
                    context = value
                    break
    except (urllib.error.URLError, OSError, ValueError):
        context = DEFAULT_CONTEXT_TOKENS
    _CONTEXT_CACHE[config.model] = context
    return context


def _cap_for_local(
    texts: Sequence[str], config: SemanticConfig
) -> tuple[list[str], int]:
    """Shorten texts to what the local model will actually read, and count them.

    Ollama truncates to the model's context without saying so (measured: 2,048
    tokens for 7,990, 19,992 and 79,968 characters alike). The engine now decides
    the cut itself so the loss can be reported: at most `context * 2` characters
    per chunk, with the number of shortened chunks returned for logging. The cloud
    backend is untouched - its inputs are not capped here at all.
    """
    if config.backend != "ollama":
        return list(texts), 0
    limit = _local_context_tokens(config) * CHARS_PER_TOKEN_BUDGET
    capped: list[str] = []
    shortened = 0
    for text in texts:
        if len(text) > limit:
            capped.append(text[:limit])
            shortened += 1
        else:
            capped.append(text)
    return capped, shortened


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
    _require_credentials(config)
    url = endpoint_for(config)
    post = (
        transport
        if transport is not None
        else partial(_http_transport, api_key=config.api_key)
    )

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
    shortened_total = 0
    for start in range(0, len(unique), config.batch):
        batch_texts = unique[start : start + config.batch]
        capped, shortened = _cap_for_local(batch_texts, config)
        if shortened:
            shortened_total += shortened
            log_event(
                "semantic_chunk_shortened",
                level="warning",
                model=config.model,
                chunks=shortened,
                running_total=shortened_total,
                context_tokens=_local_context_tokens(config),
            )
        batch = _post_with_retry(
            post, url, config.model, capped, float(config.timeout_s)
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
    if shortened_total:
        log_event(
            "semantic_shortened_summary",
            level="warning",
            model=config.model,
            chunks=shortened_total,
            of=len(unique),
            context_tokens=_local_context_tokens(config),
        )
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
