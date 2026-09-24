"""Tests for dsh_coderag.embed (T3-08).

Everything here runs offline (T-02): most cases inject a fake transport, and the
two end-to-end cases point the real urllib transport at a loopback-only stub, so
no request can leave this machine and no API key is needed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dsh_coderag.config import SemanticConfig, load_semantic_config
from dsh_coderag.embed import (
    RETRY_LIMIT,
    EmbeddingCache,
    SemanticError,
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
