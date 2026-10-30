"""Tests for dsh_coderag.embed (T3-08).

Everything here runs offline (T-02): most cases inject a fake transport, and the
two end-to-end cases point the real urllib transport at a loopback-only stub, so
no request can leave this machine and no API key is needed.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from dsh_coderag import embed
from dsh_coderag.config import SemanticConfig, load_semantic_config
from dsh_coderag.embed import (
    CHECKPOINT_FILENAME,
    CHECKPOINT_MAGIC,
    RETRY_LIMIT,
    SEMANTIC_TIMEOUT,
    DiskEmbeddingCache,
    EmbeddingCache,
    SemanticError,
    count_checkpoint_records,
    embed_query,
    embed_texts,
    endpoint_for,
    validate_local_backend,
)
from dsh_coderag.types import ErrorCode


def _config(**overrides: object) -> SemanticConfig:
    """An enabled loopback config, with per-test overrides."""
    values: dict[str, object] = {
        "enabled": True,
        "backend": "ollama",
        "url": "http://127.0.0.1:11434",
        "model": "bge-m3",
        "timeout_s": 5,
        "batch": 16,
    }
    values.update(overrides)
    return SemanticConfig(**values)  # type: ignore[arg-type]


class _Recorder:
    """A transport that returns deterministic vectors and records each call."""

    def __init__(self, dimensions: int = 3) -> None:
        self.calls: list[tuple[str, str, list[str], float]] = []
        self._dimensions = dimensions

    def __call__(
        self, url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        batch = list(texts)
        self.calls.append((url, model, batch, timeout))
        return [[float(len(text)), float(index)] for index, text in enumerate(batch)]

    @property
    def batch_sizes(self) -> list[int]:
        return [len(call[2]) for call in self.calls]

    @property
    def embedded_texts(self) -> list[str]:
        return [text for call in self.calls for text in call[2]]


def test_import_needs_no_numpy_and_no_network() -> None:
    code = (
        "import sys, dsh_coderag.embed as e;"
        "assert 'numpy' not in sys.modules, 'embed must not import numpy';"
        "print(e.RETRY_LIMIT)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(RETRY_LIMIT)


def test_disabled_backend_is_reported_without_any_request() -> None:
    recorder = _Recorder()
    with pytest.raises(SemanticError) as caught:
        embed_texts(_config(enabled=False), ["a"], transport=recorder)
    assert caught.value.code is ErrorCode.SEMANTIC_BACKEND_UNAVAILABLE
    assert recorder.calls == []


def test_same_text_twice_is_served_from_cache() -> None:
    recorder = _Recorder()
    cache = EmbeddingCache()
    config = _config()
    first = embed_texts(config, ["alpha", "beta"], cache=cache, transport=recorder)
    second = embed_texts(config, ["alpha", "beta"], cache=cache, transport=recorder)
    assert first == second
    assert len(recorder.calls) == 1
    assert cache.hits == 2 and cache.misses == 2


def test_batching_follows_the_configured_batch_size() -> None:
    recorder = _Recorder()
    embed_texts(_config(batch=2), ["a", "b", "c", "d", "e"], transport=recorder)
    assert recorder.batch_sizes == [2, 2, 1]


def test_repeated_text_inside_one_call_is_embedded_once() -> None:
    recorder = _Recorder()
    result = embed_texts(_config(), ["same", "other", "same"], transport=recorder)
    assert recorder.embedded_texts == ["same", "other"]
    assert result[0] == result[2]
    assert result[1] != result[0]


def test_non_loopback_url_is_refused_before_any_request() -> None:
    recorder = _Recorder()
    with pytest.raises(SemanticError) as caught:
        embed_texts(_config(url="http://10.0.0.5:11434"), ["a"], transport=recorder)
    assert caught.value.code is ErrorCode.SEMANTIC_BACKEND_NOT_LOCAL
    assert recorder.calls == []


def test_unknown_backend_is_reported_as_unsupported() -> None:
    recorder = _Recorder()
    with pytest.raises(SemanticError) as caught:
        embed_texts(_config(backend="acme"), ["a"], transport=recorder)
    assert caught.value.code is ErrorCode.SEMANTIC_BACKEND_UNSUPPORTED
    assert recorder.calls == []


def test_endpoint_is_built_from_the_configured_base_url() -> None:
    assert endpoint_for(_config()) == "http://127.0.0.1:11434/api/embed"
    assert endpoint_for(_config(url="http://127.0.0.1:11434/")) == (
        "http://127.0.0.1:11434/api/embed"
    )


def test_local_backend_accepts_every_loopback_spelling() -> None:
    for url in ("http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"):
        validate_local_backend(_config(url=url))


def test_retries_are_bounded_and_fail_loudly() -> None:
    calls: list[int] = []

    def always_fails(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        calls.append(1)
        raise OSError("connection refused")

    with pytest.raises(SemanticError) as caught:
        embed_texts(_config(), ["a"], transport=always_fails)
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED
    assert len(calls) == RETRY_LIMIT + 1


def test_response_length_mismatch_is_an_embed_failure() -> None:
    def wrong_length(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        return [[1.0]]

    with pytest.raises(SemanticError) as caught:
        embed_texts(_config(), ["a", "b"], transport=wrong_length)
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED


def test_api_key_never_appears_in_the_error_text() -> None:
    sentinel = "sk-sentinel-not-a-real-key"

    def always_fails(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        raise OSError("connection refused")

    config = load_semantic_config(
        {
            "CODERAG_SEMANTIC": "on",
            "CODERAG_SEMANTIC_BACKEND": "ollama",
            "CODERAG_SEMANTIC_API_KEY": sentinel,
        }
    )
    with pytest.raises(SemanticError) as caught:
        embed_texts(config, ["a"], transport=always_fails)
    assert sentinel not in str(caught.value)
    assert sentinel not in (caught.value.hint or "")


class _StubHandler(BaseHTTPRequestHandler):
    """A loopback embeddings stub that echoes one vector per input."""

    server_version = "embed-stub/1"
    requests: list[dict[str, object]] = []
    delay_seconds = 0.0

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append(payload)
        if type(self).delay_seconds:
            import time

            time.sleep(type(self).delay_seconds)
        embeddings = [[float(index)] * 2 for index, _ in enumerate(payload["input"])]
        body = json.dumps({"embeddings": embeddings}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence the stub's stderr access log."""
        return


@contextmanager
def _stub_server() -> Iterator[int]:
    """Run the stub on a loopback port and yield that port."""
    _StubHandler.requests = []
    _StubHandler.delay_seconds = 0.0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_transport_posts_model_and_input_to_a_loopback_stub() -> None:
    with _stub_server() as port:
        config = _config(url=f"http://127.0.0.1:{port}")
        result = embed_texts(config, ["one", "two"])
    assert result == [[0.0, 0.0], [1.0, 1.0]]
    assert _StubHandler.requests == [{"model": "bge-m3", "input": ["one", "two"]}]


def test_real_transport_maps_a_timeout_to_embed_failed() -> None:
    with _stub_server() as port:
        _StubHandler.delay_seconds = 3.0
        config = _config(url=f"http://127.0.0.1:{port}", timeout_s=1)
        with pytest.raises(SemanticError) as caught:
            embed_texts(config, ["slow"], transport=None)
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED


def test_real_transport_reports_a_closed_port_as_embed_failed() -> None:
    with _stub_server() as port:
        pass
    # The server is closed now, so connecting to that port must fail.
    with pytest.raises(SemanticError) as caught:
        embed_texts(_config(url=f"http://127.0.0.1:{port}"), ["a"])
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED


class _CapturingResponse:
    """The minimum of an HTTP response the transport reads."""

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _CapturingResponse:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_the_openai_backend_posts_to_embeddings_with_a_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6-27: the cloud route exists, and the key travels in the header.

    Until this task `openai` had no entry in the endpoint table at all, so an
    enabled cloud backend failed with SEMANTIC_BACKEND_UNSUPPORTED before it
    could even try to authenticate.
    """
    captured: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request, timeout: float | None = None
    ) -> _CapturingResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data or b"{}")
        return _CapturingResponse({"embeddings": [[1.0, 0.0]]})

    monkeypatch.setattr(embed, "open_without_redirects", fake_urlopen)
    config = _config(
        backend="openai",
        url="https://api.example.invalid/v1",
        model="text-embedding-3-small",
        api_key="sk-not-a-real-key",
    )

    assert embed_texts(config, ["hello"]) == [[1.0, 0.0]]
    assert captured["url"] == "https://api.example.invalid/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer sk-not-a-real-key"
    assert captured["body"] == {"model": "text-embedding-3-small", "input": ["hello"]}


def test_a_remote_openai_backend_without_a_key_fails_before_any_request() -> None:
    """A missing credential is reported as its own code, not as an embed failure."""
    recorder = _Recorder()
    config = _config(
        backend="openai",
        url="https://api.example.invalid/v1",
        model="text-embedding-3-small",
        api_key=None,
    )

    with pytest.raises(SemanticError) as caught:
        embed_texts(config, ["hello"], transport=recorder)

    assert caught.value.code is ErrorCode.SEMANTIC_AUTH_MISSING
    assert recorder.calls == [], "nothing may be sent without a credential"


def test_a_loopback_openai_backend_needs_no_key() -> None:
    """Local OpenAI-compatible servers are a supported offline case (S-01)."""
    recorder = _Recorder()
    config = _config(
        backend="openai", url="http://127.0.0.1:8080/v1", model="local", api_key=None
    )

    assert embed_texts(config, ["hello"], transport=recorder) == [[5.0, 0.0]]


def test_a_rejected_credential_is_not_retried_and_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 401/403 is deterministic: retrying wastes the budget, and the key stays out."""
    attempts = {"count": 0}

    def fake_urlopen(
        request: urllib.request.Request, timeout: float | None = None
    ) -> _CapturingResponse:
        attempts["count"] += 1
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(embed, "open_without_redirects", fake_urlopen)
    config = _config(
        backend="openai",
        url="https://api.example.invalid/v1",
        model="text-embedding-3-small",
        api_key="sk-secret-value",
    )

    with pytest.raises(SemanticError) as caught:
        embed_texts(config, ["hello"])

    assert caught.value.code is ErrorCode.SEMANTIC_AUTH_REJECTED
    assert attempts["count"] == 1, "a rejected credential must not be retried"
    assert "sk-secret-value" not in str(caught.value)
    assert "sk-secret-value" not in (caught.value.hint or "")


def test_an_openai_shaped_response_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6-28: a compatible endpoint answers `data`, not `embeddings`.

    Verified against a live OpenAI-compatible endpoint (2026-09-30): the payload
    was `{"data": [{"embedding": [...], "index": n}], "usage": {...}}` with no
    `embeddings` key at all, so parsing only Ollama's shape rejected every answer.
    Rows are ordered by `index`, because the specification does not promise order.
    """
    payload = {
        "object": "list",
        "model": "qwen3.7-text-embedding",
        "data": [
            {"object": "embedding", "index": 1, "embedding": [0.0, 2.0]},
            {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
        ],
        "usage": {"prompt_tokens": 17, "total_tokens": 17},
    }

    def fake_urlopen(
        request: urllib.request.Request, timeout: float | None = None
    ) -> _CapturingResponse:
        return _CapturingResponse(payload)

    monkeypatch.setattr(embed, "open_without_redirects", fake_urlopen)
    config = _config(
        backend="openai",
        url="https://api.example.invalid/v1",
        model="qwen3.7-text-embedding",
        api_key="sk-not-a-real-key",
    )

    assert embed_texts(config, ["first", "second"]) == [[1.0, 0.0], [0.0, 2.0]]


def test_ollama_shaped_response_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """The local backend's `embeddings` shape keeps working alongside `data`."""

    def fake_urlopen(
        request: urllib.request.Request, timeout: float | None = None
    ) -> _CapturingResponse:
        return _CapturingResponse({"embeddings": [[1.0, 1.0]]})

    monkeypatch.setattr(embed, "open_without_redirects", fake_urlopen)
    config = _config(url="http://127.0.0.1:11434", model="bge-m3")

    assert embed_texts(config, ["hello"]) == [[1.0, 1.0]]


def test_a_response_with_no_vectors_is_reported_as_embed_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A payload with neither shape must fail loudly, not silently produce nothing."""

    def fake_urlopen(
        request: urllib.request.Request, timeout: float | None = None
    ) -> _CapturingResponse:
        return _CapturingResponse({"result": []})

    monkeypatch.setattr(embed, "open_without_redirects", fake_urlopen)
    config = _config(
        backend="openai",
        url="https://api.example.invalid/v1",
        model="m",
        api_key="sk-not-a-real-key",
    )

    with pytest.raises(SemanticError) as caught:
        embed_texts(config, ["hello"])

    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED


def test_a_long_chunk_is_shortened_for_the_local_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6-29: Ollama cuts silently at its context, so the engine cuts and counts.

    Measured on this machine: `nomic-embed-text` reported exactly 2,048 tokens for
    7,990, 19,992 and 79,968 characters alike, with no error and nothing in the
    response to say so.
    """
    monkeypatch.setattr(embed, "_local_context_tokens", lambda config: 10)
    recorder = _Recorder()
    long_text = "x" * 500

    embed_texts(_config(model="m", batch=4), [long_text], transport=recorder)

    sent = recorder.embedded_texts[0]
    assert len(sent) == 10 * embed.CHARS_PER_TOKEN_BUDGET
    assert sent == "x" * (10 * embed.CHARS_PER_TOKEN_BUDGET)


def test_a_long_chunk_is_not_shortened_for_the_cloud_backend() -> None:
    """The cloud path is left alone: its providers take far larger inputs."""
    recorder = _Recorder()
    long_text = "y" * 500
    config = _config(
        backend="openai",
        url="https://api.example.invalid/v1",
        model="m",
        api_key="sk-not-a-real-key",
    )

    embed_texts(config, [long_text], transport=recorder)

    assert recorder.embedded_texts == [long_text]


def test_shortening_is_reported_in_a_log_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The count is the whole point: a silent cut is what this task fixes."""
    monkeypatch.setattr(embed, "_local_context_tokens", lambda config: 1)
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        embed, "log_event", lambda name, **fields: events.append((name, fields))
    )

    embed_texts(_config(model="m"), ["z" * 40], transport=_Recorder())

    names = [name for name, _ in events]
    assert "semantic_chunk_shortened" in names
    summary = dict(events)["semantic_shortened_summary"]
    assert summary["chunks"] == 1
    assert summary["of"] == 1
    assert summary["context_tokens"] == 1


def test_count_checkpoint_records_counts_without_unpacking_vectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T8-02: counting is not loading; only the 36-byte headers may be unpacked."""
    cache = DiskEmbeddingCache(tmp_path, "m")
    cache.put("m", "alpha", [1.0, 2.0, 3.0])
    cache.put("m", "beta", [4.0, 5.0, 6.0])
    cache.close()
    path = tmp_path / CHECKPOINT_FILENAME

    formats: list[str] = []
    real_unpack = struct.unpack

    def spy(fmt: str, data: bytes) -> tuple[object, ...]:
        formats.append(fmt)
        return real_unpack(fmt, data)

    monkeypatch.setattr(struct, "unpack", spy)

    assert count_checkpoint_records(path) == 2
    assert formats == ["<I32s", "<I32s"], "vector payloads must never be unpacked"


def test_count_checkpoint_records_never_truncates_a_torn_tail(tmp_path: Path) -> None:
    """T8-02: status must not repair the file a running build is still appending to."""
    cache = DiskEmbeddingCache(tmp_path, "m")
    cache.put("m", "alpha", [1.0, 2.0, 3.0])
    cache.close()
    path = tmp_path / CHECKPOINT_FILENAME
    torn = path.read_bytes() + b"\x03\x00\x00\x00torn"
    path.write_bytes(torn)

    assert count_checkpoint_records(path) == 1
    assert path.read_bytes() == torn
    assert path.stat().st_size == len(torn)


def test_count_checkpoint_records_refuses_a_huge_dimension_without_allocating(
    tmp_path: Path,
) -> None:
    """A forged header must not make the counter allocate or read a giant payload."""
    path = tmp_path / CHECKPOINT_FILENAME
    path.write_bytes(CHECKPOINT_MAGIC + struct.pack("<I32s", 1_000_000_000, b"\0" * 32))
    before = path.read_bytes()

    assert count_checkpoint_records(path) == 0
    assert path.read_bytes() == before


def test_count_checkpoint_records_handles_absent_empty_and_foreign_files(
    tmp_path: Path,
) -> None:
    path = tmp_path / CHECKPOINT_FILENAME
    assert count_checkpoint_records(path) == 0

    path.write_bytes(b"")
    assert count_checkpoint_records(path) == 0

    path.write_bytes(b"not a coderag checkpoint")
    assert count_checkpoint_records(path) == 0


class _RedirectHandler(BaseHTTPRequestHandler):
    """Answer every embeddings POST with a redirect to a canary host."""

    target = ""
    requests: list[tuple[str, str | None]] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        type(self).requests.append((self.path, self.headers.get("Authorization")))
        self.send_response(302)
        self.send_header("Location", type(self).target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence the stub's access log."""
        return


class _CanaryHandler(BaseHTTPRequestHandler):
    """Records every request that reaches the redirect target."""

    requests: list[tuple[str, str | None]] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        type(self).requests.append((self.path, self.headers.get("Authorization")))
        body = json.dumps({"embeddings": [[1.0, 0.0]]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence the stub's access log."""
        return


@contextmanager
def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_transport_refuses_a_redirect_without_forwarding_the_key() -> None:
    """T8-02: following a 3xx would forward the Bearer key past ALLOW_REMOTE."""
    _CanaryHandler.requests = []
    _RedirectHandler.requests = []
    with _serve(_CanaryHandler) as canary_port:
        _RedirectHandler.target = f"http://127.0.0.1:{canary_port}/capture"
        with _serve(_RedirectHandler) as redirect_port:
            config = _config(
                backend="openai",
                url=f"http://127.0.0.1:{redirect_port}",
                model="bge-m3",
                api_key="sk-redirect-secret",
            )
            with pytest.raises(SemanticError) as caught:
                embed_texts(config, ["hello"])

    assert caught.value.code.value == "SEMANTIC_REDIRECT_REFUSED"
    assert _CanaryHandler.requests == []
    assert _RedirectHandler.requests == [("/embeddings", "Bearer sk-redirect-secret")]
    assert "sk-redirect-secret" not in str(caught.value)
    assert "sk-redirect-secret" not in (caught.value.hint or "")


def test_embed_query_returns_the_single_vector_and_uses_the_http_timeout() -> None:
    """T8-05: one request, with the configured HTTP timeout (not the budget)."""
    recorder = _Recorder()
    vector = embed_query(_config(), "question", budget_s=2, transport=recorder)
    assert vector == [8.0, 0.0]
    assert recorder.calls == [
        ("http://127.0.0.1:11434/api/embed", "bge-m3", ["question"], 5.0)
    ]


def test_embed_query_does_not_retry() -> None:
    """T8-05: a deadline-bearing query makes exactly one attempt."""
    calls: list[int] = []

    def failing(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        calls.append(1)
        raise OSError("connection refused")

    with pytest.raises(SemanticError) as caught:
        embed_query(_config(), "q", budget_s=2, transport=failing)
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED
    assert len(calls) == 1


def test_embed_query_reports_a_budget_overrun_as_semantic_timeout() -> None:
    """T8-05: the caller stops waiting, but the request keeps warming the model."""
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        started.set()
        release.wait(5)
        finished.set()
        return [[1.0, 2.0]]

    with pytest.raises(SemanticError) as caught:
        embed_query(_config(), "q", budget_s=0.05, transport=slow)
    assert caught.value.code.value == SEMANTIC_TIMEOUT
    assert "background" in (caught.value.hint or "")

    assert started.is_set()
    release.set()
    assert finished.wait(2), "the abandoned request must keep running, not be cancelled"


def test_embed_query_maps_a_request_timeout_to_semantic_timeout() -> None:
    """T8-05: an HTTP timeout is a budget failure, not a generic embed failure."""

    def timed_out(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        raise TimeoutError("timed out")

    with pytest.raises(SemanticError) as caught:
        embed_query(_config(), "q", budget_s=2, transport=timed_out)
    assert caught.value.code.value == SEMANTIC_TIMEOUT


def test_embed_query_keeps_structured_backend_errors_intact() -> None:
    """T8-05: a credential rejection stays SEMANTIC_AUTH_REJECTED."""

    def rejected(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        raise SemanticError(ErrorCode.SEMANTIC_AUTH_REJECTED, "rejected", "check the key")

    with pytest.raises(SemanticError) as caught:
        embed_query(_config(), "q", budget_s=2, transport=rejected)
    assert caught.value.code is ErrorCode.SEMANTIC_AUTH_REJECTED


def test_embed_query_validates_the_backend_before_any_request() -> None:
    """T8-05: an unsupported backend is reported even without a vector index."""
    recorder = _Recorder()
    with pytest.raises(SemanticError) as caught:
        embed_query(_config(backend="acme"), "q", transport=recorder)
    assert caught.value.code is ErrorCode.SEMANTIC_BACKEND_UNSUPPORTED
    assert recorder.calls == []


def test_embed_query_refuses_the_off_switch_without_a_request() -> None:
    recorder = _Recorder()
    with pytest.raises(SemanticError) as caught:
        embed_query(_config(enabled=False), "q", transport=recorder)
    assert caught.value.code is ErrorCode.SEMANTIC_BACKEND_UNAVAILABLE
    assert recorder.calls == []


def test_embed_query_rejects_more_than_one_vector() -> None:
    def two(
        url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        return [[1.0], [2.0]]

    with pytest.raises(SemanticError) as caught:
        embed_query(_config(), "q", budget_s=2, transport=two)
    assert caught.value.code is ErrorCode.SEMANTIC_EMBED_FAILED
