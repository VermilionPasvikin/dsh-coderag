"""Tests for dsh_coderag.admin (T7-01): status, health and resumable vectorize.

Everything here runs offline (T-02). The vector tests inject a deterministic
transport, the health tests use a loopback stub or a monkeypatched urllib seam,
and no test needs a real embedding backend or a real API key. The one fake key
is a sentinel used to prove it never reaches stdout, stderr or a payload.
"""

from __future__ import annotations

import io
import json
import struct
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from dsh_coderag import admin, index_sync, vectors
from dsh_coderag.config import SemanticConfig
from dsh_coderag.embed import CHECKPOINT_FILENAME, CHECKPOINT_MAGIC
from dsh_coderag.indexer import connect
from dsh_coderag.vectors import (
    EMBEDDINGS_FILENAME,
    MANIFEST_FILENAME,
    checkpoint_slug,
    vectors_dir,
)

DIM = 2
SENTINEL_KEY = "sk-test-not-a-real-key"


def _config(**overrides: object) -> SemanticConfig:
    """An enabled loopback config; the openai shape avoids Ollama's input cap."""
    values: dict[str, object] = {
        "enabled": True,
        "backend": "openai",
        "url": "http://127.0.0.1:9/v1",
        "model": "bge-m3",
        "timeout_s": 5,
        "batch": 2,
    }
    values.update(overrides)
    return SemanticConfig(**values)  # type: ignore[arg-type]


class _Recorder:
    """A deterministic transport that records every batch it receives."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(
        self, url: str, model: str, texts: Sequence[str], timeout: float
    ) -> list[list[float]]:
        batch = list(texts)
        self.calls.append(batch)
        return [[float(len(text) % 7), 1.0] for text in batch]


def _records(stream: io.StringIO) -> list[dict[str, Any]]:
    """Parse every JSON line the command wrote."""
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def _chunk_count(root: Path) -> int:
    """Return how many chunks one workspace index holds."""
    connection = connect(root / ".coderag" / "index.sqlite3")
    try:
        return int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    finally:
        connection.close()


def _checkpoint_file(root: Path, model: str = "bge-m3") -> Path:
    """Return the on-disk checkpoint path for one model."""
    return (
        vectors_dir(root) / vectors.CHECKPOINT_SUBDIR / checkpoint_slug(model) / CHECKPOINT_FILENAME
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A four-file workspace with a built BM25 index and no vector store.

    The semantic switch is cleared before indexing so an ambient value cannot
    make `index_sync` start a real backend build (T-02).
    """
    monkeypatch.delenv("CODERAG_SEMANTIC", raising=False)
    root = tmp_path / "ws"
    (root / "pkg").mkdir(parents=True)
    for name in ("alpha", "beta", "gamma", "delta"):
        (root / "pkg" / f"{name}.py").write_text(
            f"def {name}():\n    return '{name}'\n", encoding="utf-8"
        )
    index_sync(root)
    return root


def _build_vectors(root: Path, config: SemanticConfig | None = None) -> None:
    """Build a complete vector index through the public admin path."""
    stream = io.StringIO()
    code = admin.vectorize(
        root,
        config=config or _config(),
        transport=_Recorder(),
        out=stream,
    )
    assert code == admin.EXIT_OK, stream.getvalue()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_reports_an_absent_index_and_vector_store_without_raising(
    tmp_path: Path,
) -> None:
    root = tmp_path / "never-indexed"
    payload = admin.status(root, _config())

    assert set(payload) == {
        "ok",
        "index_exists",
        "vector_exists",
        "model",
        "dim",
        "total_chunks",
        "vectorized_chunks",
        "pending_chunks",
        "stale_chunks",
        "generated_at",
        "checkpoint_vectors",
        "config",
    }
    assert payload["ok"] is True
    assert payload["index_exists"] is False
    assert payload["vector_exists"] is False
    assert payload["total_chunks"] == 0
    assert payload["vectorized_chunks"] == 0
    assert payload["pending_chunks"] == 0
    assert payload["stale_chunks"] == 0
    assert payload["model"] == "bge-m3"
    assert payload["dim"] is None
    assert payload["generated_at"] is None
    assert payload["checkpoint_vectors"] == 0
    assert payload["config"] == {
        "enabled": True,
        "backend": "openai",
        "url": "http://127.0.0.1:9/v1",
        "model": "bge-m3",
        "allow_remote": False,
        "key_present": False,
    }
    assert not (root / ".coderag").exists(), "status must not create state"


def test_status_reports_an_index_with_every_chunk_pending(workspace: Path) -> None:
    payload = admin.status(workspace, _config())

    assert payload["index_exists"] is True
    assert payload["vector_exists"] is False
    assert payload["total_chunks"] == _chunk_count(workspace) == 4
    assert payload["vectorized_chunks"] == 0
    assert payload["pending_chunks"] == 4
    assert payload["stale_chunks"] == 0
    assert payload["checkpoint_vectors"] == 0


def test_status_reports_only_key_presence(tmp_path: Path) -> None:
    payload = admin.status(tmp_path / "ws", _config(api_key=SENTINEL_KEY))

    assert payload["config"]["key_present"] is True
    assert SENTINEL_KEY not in json.dumps(payload)


def test_status_compares_manifest_rows_by_chunk_id_and_content_hash(
    workspace: Path,
) -> None:
    _build_vectors(workspace)
    built = admin.status(workspace, _config())
    assert built["vector_exists"] is True
    assert built["vectorized_chunks"] == 4
    assert built["pending_chunks"] == 0
    assert built["stale_chunks"] == 0
    assert built["dim"] == DIM
    assert built["generated_at"] is not None
    assert built["checkpoint_vectors"] == 4

    connection = connect(workspace / ".coderag" / "index.sqlite3")
    try:
        with connection:
            connection.execute(
                "UPDATE chunks SET content_hash = ? WHERE id = (SELECT MIN(id) FROM chunks)",
                ("0" * 64,),
            )
    finally:
        connection.close()

    changed = admin.status(workspace, _config())
    assert changed["vectorized_chunks"] == 3
    assert changed["pending_chunks"] == 1
    assert changed["stale_chunks"] == 1


def test_status_never_loads_the_embeddings_matrix(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build_vectors(workspace)

    def explode(*args: object, **kwargs: object) -> object:
        raise AssertionError("status must not load embeddings.npy")

    monkeypatch.setattr(np, "load", explode)
    payload = admin.status(workspace, _config())

    assert payload["vectorized_chunks"] == 4
    assert (vectors_dir(workspace) / EMBEDDINGS_FILENAME).is_file()


def test_status_treats_a_manifest_from_another_model_as_not_vectorized(
    workspace: Path,
) -> None:
    """A model change makes every stored vector unusable, so all work is pending."""
    _build_vectors(workspace, _config(model="bge-m3"))

    payload = admin.status(workspace, _config(model="other-model"))

    assert payload["vector_exists"] is True
    assert payload["model"] == "bge-m3"
    assert payload["vectorized_chunks"] == 0
    assert payload["pending_chunks"] == 4
    assert payload["checkpoint_vectors"] == 0


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


class _HealthHandler(BaseHTTPRequestHandler):
    """A loopback backend stub: `/api/tags` and `/models`, with header capture."""

    server_version = "admin-health-stub/1"
    ollama_models: list[str] = []
    openai_models: list[str] = []
    status = 200
    authorization: list[str | None] = []
    redirect_to: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        type(self).authorization.append(self.headers.get("Authorization"))
        if type(self).redirect_to is not None:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if type(self).status != 200:
            self.send_response(type(self).status)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/api/tags":
            payload: dict[str, object] = {
                "models": [{"name": name} for name in type(self).ollama_models]
            }
        elif self.path == "/models":
            payload = {"data": [{"id": name} for name in type(self).openai_models]}
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps(payload).encode("utf-8")
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
    """Run one loopback stub handler and yield its port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def _health_server() -> Iterator[int]:
    """Run the stub on a random loopback port and yield it."""
    _HealthHandler.ollama_models = ["bge-m3:latest"]
    _HealthHandler.openai_models = ["bge-m3"]
    _HealthHandler.status = 200
    _HealthHandler.authorization = []
    _HealthHandler.redirect_to = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_health_reports_a_reachable_ollama_and_never_sends_the_key(tmp_path: Path) -> None:
    with _health_server() as port:
        payload = admin.health(
            tmp_path,
            _config(
                backend="ollama",
                url=f"http://127.0.0.1:{port}",
                model="bge-m3",
                api_key=SENTINEL_KEY,
            ),
        )

    assert payload["ok"] is True
    assert payload["backend"] == "ollama"
    assert payload["model_present"] is True
    assert payload["models"] == ["bge-m3:latest"]
    assert "code" not in payload
    assert _HealthHandler.authorization == [None], "Ollama never receives a key"
    assert SENTINEL_KEY not in json.dumps(payload)


def test_health_reports_an_openai_backend_with_a_bearer_header(tmp_path: Path) -> None:
    with _health_server() as port:
        payload = admin.health(
            tmp_path,
            _config(
                backend="openai",
                url=f"http://127.0.0.1:{port}",
                model="bge-m3",
                api_key=SENTINEL_KEY,
            ),
        )

    assert payload["ok"] is True
    assert payload["model_present"] is True
    assert payload["models"] == ["bge-m3"]
    assert _HealthHandler.authorization == [f"Bearer {SENTINEL_KEY}"]
    assert SENTINEL_KEY not in json.dumps(payload)


def test_health_reports_a_missing_model_without_failing_the_probe(tmp_path: Path) -> None:
    with _health_server() as port:
        payload = admin.health(
            tmp_path,
            _config(backend="ollama", url=f"http://127.0.0.1:{port}", model="absent"),
        )

    assert payload["ok"] is True
    assert payload["model_present"] is False
    assert "not available" in payload["detail"]


def test_health_maps_a_closed_port_to_a_structured_failure(tmp_path: Path) -> None:
    with _health_server() as port:
        pass
    # The server is closed now, so the port refuses the connection.
    payload = admin.health(tmp_path, _config(backend="ollama", url=f"http://127.0.0.1:{port}"))

    assert payload["ok"] is False
    assert payload["code"] == "HEALTH_REQUEST_FAILED"
    assert payload["message"]
    assert payload["models"] == []


def test_health_refuses_a_remote_url_without_allow_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: object, **kwargs: object) -> object:
        raise AssertionError("a remote URL without the switch must not be contacted")

    monkeypatch.setattr(admin, "open_without_redirects", explode)
    payload = admin.health(tmp_path, _config(url="http://10.0.0.5:11434", allow_remote=False))

    assert payload["ok"] is False
    assert payload["code"] == "REMOTE_NOT_ALLOWED"
    assert "CODERAG_SEMANTIC_ALLOW_REMOTE" in payload["message"]


class _CapturingResponse:
    """The minimum of an HTTP response the health probe reads."""

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self._offset = 0

    def __enter__(self) -> _CapturingResponse:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._body[self._offset :]
        else:
            chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_health_allows_a_remote_url_only_with_allow_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request, timeout: float | None = None
    ) -> _CapturingResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _CapturingResponse({"data": [{"id": "bge-m3"}]})

    monkeypatch.setattr(admin, "open_without_redirects", fake_urlopen)
    payload = admin.health(
        tmp_path,
        _config(
            backend="openai",
            url="https://api.example.invalid/v1",
            model="bge-m3",
            api_key=SENTINEL_KEY,
            allow_remote=True,
        ),
    )

    assert payload["ok"] is True
    assert payload["model_present"] is True
    assert captured["url"] == "https://api.example.invalid/v1/models"
    assert captured["headers"]["Authorization"] == f"Bearer {SENTINEL_KEY}"
    assert captured["timeout"] == admin.HEALTH_TIMEOUT_S == 5.0
    assert SENTINEL_KEY not in json.dumps(payload)


def test_health_reports_a_rejected_credential_without_echoing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float | None = None
    ) -> _CapturingResponse:
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(admin, "open_without_redirects", fake_urlopen)
    payload = admin.health(
        tmp_path,
        _config(
            backend="openai",
            url="https://api.example.invalid/v1",
            api_key=SENTINEL_KEY,
            allow_remote=True,
        ),
    )

    assert payload["ok"] is False
    assert payload["code"] == "SEMANTIC_AUTH_REJECTED"
    assert SENTINEL_KEY not in json.dumps(payload)


# ---------------------------------------------------------------------------
# vectorize
# ---------------------------------------------------------------------------


def test_vectorize_streams_start_progress_and_done(workspace: Path) -> None:
    recorder = _Recorder()
    stream = io.StringIO()

    code = admin.vectorize(workspace, config=_config(), transport=recorder, out=stream)

    assert code == admin.EXIT_OK
    events = _records(stream)
    assert [event["event"] for event in events] == [
        "start",
        "progress",
        "progress",
        "done",
    ]
    assert events[0] == {
        "event": "start",
        "total_chunks": 4,
        "pending_chunks": 4,
        "checkpoint_vectors": 0,
    }
    assert events[1] == {"event": "progress", "embedded": 2, "pending": 2}
    assert events[2] == {"event": "progress", "embedded": 4, "pending": 0}
    assert events[3]["event"] == "done"
    assert events[3]["chunks"] == 4
    assert events[3]["model"] == "bge-m3"
    assert isinstance(events[3]["generated_at"], str) and events[3]["generated_at"]
    assert [len(batch) for batch in recorder.calls] == [2, 2]
    assert (vectors_dir(workspace) / MANIFEST_FILENAME).is_file()

    settled = admin.status(workspace, _config())
    assert settled["pending_chunks"] == 0
    assert settled["vectorized_chunks"] == 4


def test_vectorize_resumes_from_the_checkpoint_after_a_killed_build(
    workspace: Path,
) -> None:
    config = _config(batch=2)
    sent_before: list[str] = []
    attempts = {"count": 0}

    def dying(url: str, model: str, texts: Sequence[str], timeout: float) -> list[list[float]]:
        attempts["count"] += 1
        if attempts["count"] > 1:
            raise OSError("the Host killed the process")
        sent_before.extend(texts)
        return [[float(len(text) % 7), 1.0] for text in texts]

    first = io.StringIO()
    assert admin.vectorize(workspace, config=config, transport=dying, out=first) == 1
    first_events = _records(first)
    assert [event["event"] for event in first_events] == ["start", "progress", "error"]
    assert first_events[-1]["code"] == "SEMANTIC_EMBED_FAILED"
    assert len(sent_before) == 2, "the first batch is acknowledged in the checkpoint"
    assert attempts["count"] == 1 + 3, "the failed batch is retried, then reported"
    assert not (vectors_dir(workspace) / MANIFEST_FILENAME).exists()

    interrupted = admin.status(workspace, config)
    assert interrupted["vector_exists"] is False
    assert interrupted["checkpoint_vectors"] == 2

    sent_after: list[str] = []
    second = io.StringIO()

    def recording(url: str, model: str, texts: Sequence[str], timeout: float) -> list[list[float]]:
        sent_after.extend(texts)
        return [[float(len(text) % 7), 1.0] for text in texts]

    assert admin.vectorize(workspace, config=config, transport=recording, out=second) == 0
    second_events = _records(second)
    assert second_events[0] == {
        "event": "start",
        "total_chunks": 4,
        "pending_chunks": 4,
        "checkpoint_vectors": 2,
    }
    assert second_events[-1]["event"] == "done"
    assert second_events[-1]["chunks"] == 4

    assert len(sent_after) == 2
    assert set(sent_after).isdisjoint(sent_before), "checkpointed texts are not re-sent"
    progress = [event for event in second_events if event["event"] == "progress"]
    assert progress[-1] == {"event": "progress", "embedded": 4, "pending": 0}
    assert admin.status(workspace, config)["pending_chunks"] == 0


def test_a_second_vectorize_run_reuses_the_index_without_transport_calls(
    workspace: Path,
) -> None:
    config = _config()
    assert (
        admin.vectorize(workspace, config=config, transport=_Recorder(), out=io.StringIO())
        == admin.EXIT_OK
    )

    def explode(url: str, model: str, texts: Sequence[str], timeout: float) -> list[list[float]]:
        raise AssertionError("an unchanged workspace must not call the backend")

    stream = io.StringIO()
    assert admin.vectorize(workspace, config=config, transport=explode, out=stream) == 0
    events = _records(stream)
    assert events[0]["event"] == "start"
    assert events[0]["pending_chunks"] == 0
    assert events[0]["checkpoint_vectors"] == 4
    assert events[-1]["event"] == "done"
    assert events[-1]["chunks"] == 4


def test_vectorize_embeds_only_the_chunks_pending_in_status(workspace: Path) -> None:
    """The streamed start total must be the same pending count status reports."""
    config = _config()
    _build_vectors(workspace)
    (workspace / "pkg" / "alpha.py").write_text(
        "def alpha():\n    return 'alpha changed'\n", encoding="utf-8"
    )
    index_sync(workspace)

    pending = admin.status(workspace, config)
    assert pending["vectorized_chunks"] == 3
    assert pending["pending_chunks"] == 1
    assert pending["stale_chunks"] == 1

    recorder = _Recorder()
    stream = io.StringIO()
    assert admin.vectorize(workspace, config=config, transport=recorder, out=stream) == 0
    events = _records(stream)
    assert events[0]["pending_chunks"] == pending["pending_chunks"] == 1
    assert len(recorder.calls) == 1
    assert len(recorder.calls[0]) == 1
    progress = [event for event in events if event["event"] == "progress"]
    assert progress == [{"event": "progress", "embedded": 1, "pending": 0}]
    assert events[-1]["chunks"] == 4
    assert admin.status(workspace, config)["pending_chunks"] == 0


def test_vectorize_reports_a_missing_index_as_an_error_event(tmp_path: Path) -> None:
    stream = io.StringIO()

    code = admin.vectorize(tmp_path / "never-indexed", config=_config(), out=stream)

    assert code == admin.EXIT_FAILED
    lines = _records(stream)
    assert len(lines) == 1
    assert lines[0]["event"] == "error"
    assert lines[0]["code"] == "INDEX_NOT_FOUND"
    assert "Traceback" not in stream.getvalue()
    assert not (tmp_path / "never-indexed" / ".coderag").exists()


def test_vectorize_reports_a_disabled_backend_as_an_error_event(workspace: Path) -> None:
    stream = io.StringIO()

    code = admin.vectorize(workspace, config=_config(enabled=False), out=stream)

    assert code == admin.EXIT_FAILED
    lines = _records(stream)
    assert len(lines) == 1
    assert lines[0]["event"] == "error"
    assert lines[0]["code"] == "SEMANTIC_BACKEND_UNAVAILABLE"
    assert lines[0]["message"]


def test_vectorize_never_echoes_the_api_key_on_failure(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(url: str, model: str, texts: Sequence[str], timeout: float) -> list[list[float]]:
        raise OSError("connection refused")

    config = _config(
        backend="openai",
        url="http://127.0.0.1:9/v1",
        api_key=SENTINEL_KEY,
    )
    stream = io.StringIO()

    code = admin.vectorize(workspace, config=config, transport=failing, out=stream)

    assert code == admin.EXIT_FAILED
    assert SENTINEL_KEY not in stream.getvalue()
    assert SENTINEL_KEY not in capsys.readouterr().err
    lines = _records(stream)
    assert lines[-1]["event"] == "error"
    assert lines[-1]["code"] == "SEMANTIC_EMBED_FAILED"


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def test_main_status_prints_exactly_one_json_object(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODERAG_SEMANTIC", raising=False)

    code = admin.main(["status", "--root", str(tmp_path / "ws")])

    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["ok"] is True
    assert payload["index_exists"] is False
    assert payload["vector_exists"] is False


def test_main_vectorize_reports_a_missing_index_on_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODERAG_SEMANTIC", "on")
    monkeypatch.setenv("CODERAG_SEMANTIC_BACKEND", "openai")
    monkeypatch.setenv("CODERAG_SEMANTIC_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("CODERAG_SEMANTIC_MODEL", "bge-m3")
    monkeypatch.delenv("CODERAG_SEMANTIC_API_KEY", raising=False)

    code = admin.main(["vectorize", "--root", str(tmp_path / "ws")])

    assert code == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "error"
    assert event["code"] == "INDEX_NOT_FOUND"


def test_main_index_reports_counts_and_skips_vectorization(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings-page index button must never start the vector build."""
    calls: list[bool] = []

    def fake_index(root: Path, *, build_vectors: bool = True) -> SimpleNamespace:
        calls.append(build_vectors)
        return SimpleNamespace(files=2, chunks=5, seen_files=9, other_extensions=1)

    monkeypatch.setattr("dsh_coderag.indexer.index_sync", fake_index)

    code = admin.main(["index", "--root", str(tmp_path / "ws")])

    assert code == 0
    assert calls == [False]
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "files": 2,
        "chunks": 5,
        "seen_files": 9,
        "other_extensions": 1,
    }


def test_main_remove_vectors_keeps_the_code_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deleting the vector store must leave the lexical index untouched."""
    root = tmp_path / "ws"
    store = root / ".coderag" / "vectors"
    (store / "cache" / "bge").mkdir(parents=True)
    (store / "embeddings.npy").write_bytes(b"vectors")
    (store / "manifest.json").write_bytes(b"{}")
    (store / "cache" / "bge" / "embed-cache.bin").write_bytes(b"cache")
    index = root / ".coderag" / "index.sqlite3"
    index.write_bytes(b"sqlite")

    assert admin.main(["remove-vectors", "--root", str(root)]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "removed": True,
        "path": str(store),
    }
    assert not store.exists()
    assert index.read_bytes() == b"sqlite"

    assert admin.main(["remove-vectors", "--root", str(root)]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "removed": False,
        "path": str(store),
    }


def test_remove_vectors_unlinks_a_symlink_without_deleting_its_target(
    tmp_path: Path,
) -> None:
    """A crafted store path must not turn the action into a foreign delete."""
    outside = tmp_path / "outside"
    outside.mkdir()
    keep = outside / "keep.txt"
    keep.write_text("keep")
    root = tmp_path / "ws"
    (root / ".coderag").mkdir(parents=True)
    (root / ".coderag" / "vectors").symlink_to(outside, target_is_directory=True)

    assert admin.main(["remove-vectors", "--root", str(root)]) == 0

    assert not (root / ".coderag" / "vectors").exists()
    assert keep.read_text() == "keep"


def test_status_does_not_open_a_write_connection(tmp_path: Path) -> None:
    """The read-only URI means a workspace without an index gains no files."""
    root = tmp_path / "ws"
    admin.status(root, _config())
    assert not root.exists()
    assert not (root / ".coderag").exists()
    assert not any(tmp_path.iterdir()), "status must not create wal/shm files"


def test_sqlite_read_only_failure_is_reported_as_unindexed(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / ".coderag").mkdir(parents=True)
    (root / ".coderag" / "index.sqlite3").write_bytes(b"not a database")

    payload = admin.status(root, _config())

    assert payload["ok"] is True
    assert payload["index_exists"] is False
    assert payload["total_chunks"] == 0


def test_a_corrupt_manifest_yields_no_reusable_rows(tmp_path: Path) -> None:
    (vectors_dir(tmp_path)).mkdir(parents=True)
    (vectors_dir(tmp_path) / EMBEDDINGS_FILENAME).write_bytes(b"not a matrix")
    (vectors_dir(tmp_path) / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")

    payload = admin.status(tmp_path, _config())

    assert payload["vector_exists"] is True
    assert payload["vectorized_chunks"] == 0
    assert payload["pending_chunks"] == 0


def test_status_counts_the_checkpoint_without_loading_or_writing_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-3: status must not call checkpoint_cache/load on a file a build owns."""
    _build_vectors(workspace)
    path = _checkpoint_file(workspace)
    before = path.read_bytes()

    def explode(*args: object, **kwargs: object) -> object:
        raise AssertionError("status must not load the embedding checkpoint")

    monkeypatch.setattr(vectors, "checkpoint_cache", explode)
    monkeypatch.setattr("dsh_coderag.embed.DiskEmbeddingCache.load", explode)

    payload = admin.status(workspace, _config())

    assert payload["checkpoint_vectors"] == 4
    assert path.read_bytes() == before
    assert path.stat().st_size == len(before)


def test_status_leaves_a_torn_checkpoint_tail_untouched(workspace: Path) -> None:
    """P1-3: a poll during a build must not truncate a partially written record."""
    _build_vectors(workspace)
    path = _checkpoint_file(workspace)
    torn = path.read_bytes() + b"\x03\x00\x00\x00torn"
    path.write_bytes(torn)

    payload = admin.status(workspace, _config())

    assert payload["checkpoint_vectors"] == 4
    assert path.read_bytes() == torn
    assert path.stat().st_size == len(torn)


def test_status_counts_a_forged_huge_dimension_as_zero_without_allocating(
    workspace: Path,
) -> None:
    """P1-3: a forged header must not make status allocate a giant vector."""
    _build_vectors(workspace)
    path = _checkpoint_file(workspace)
    forged = CHECKPOINT_MAGIC + struct.pack("<I32s", 1_000_000_000, b"\0" * 32)
    path.write_bytes(forged)

    payload = admin.status(workspace, _config())

    assert payload["checkpoint_vectors"] == 0
    assert path.read_bytes() == forged


def test_status_counts_an_empty_checkpoint_as_zero_and_keeps_it_empty(
    workspace: Path,
) -> None:
    path = _checkpoint_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")

    payload = admin.status(workspace, _config())

    assert payload["checkpoint_vectors"] == 0
    assert path.read_bytes() == b""


def test_status_reports_key_present_from_the_host_marker_only(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T8-02: the Host no longer passes the key to status, only its presence marker."""
    monkeypatch.delenv("CODERAG_SEMANTIC_API_KEY", raising=False)
    monkeypatch.setenv(admin.ENV_SEMANTIC_KEY_PRESENT, "0")
    assert admin.status(workspace, _config())["config"]["key_present"] is False

    monkeypatch.setenv(admin.ENV_SEMANTIC_KEY_PRESENT, "1")
    payload = admin.status(workspace, _config())

    assert payload["config"]["key_present"] is True
    assert SENTINEL_KEY not in json.dumps(payload)


def test_health_refuses_a_redirect_without_reaching_the_target(tmp_path: Path) -> None:
    """P1-4: a 302 must not forward the Bearer key to its Location target."""

    class _Canary(_HealthHandler):
        redirect_to = None
        authorization: list[str | None] = []
        ollama_models: list[str] = []
        openai_models: list[str] = ["bge-m3"]
        status = 200

    class _Redirect(_HealthHandler):
        redirect_to = ""
        authorization: list[str | None] = []
        status = 200

    with _serve(_Canary) as canary_port:
        _Redirect.redirect_to = f"http://127.0.0.1:{canary_port}/capture"
        with _serve(_Redirect) as redirect_port:
            payload = admin.health(
                tmp_path,
                _config(
                    backend="openai",
                    url=f"http://127.0.0.1:{redirect_port}",
                    model="bge-m3",
                    api_key=SENTINEL_KEY,
                ),
            )

    assert payload["ok"] is False
    assert payload["code"] == "HEALTH_REDIRECT_REFUSED"
    assert _Canary.authorization == [], "the redirect target must never be called"
    assert _Redirect.authorization == [f"Bearer {SENTINEL_KEY}"]
    assert SENTINEL_KEY not in json.dumps(payload)


class _EndlessResponse:
    """A response whose body never ends, to exercise the health body cap."""

    def __enter__(self) -> _EndlessResponse:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        return b"x" * (size if size > 0 else 1)


def test_health_refuses_an_oversized_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P2-7: a health payload larger than 1 MiB is refused, not buffered forever."""
    monkeypatch.setattr(
        admin, "open_without_redirects", lambda request, timeout: _EndlessResponse()
    )

    payload = admin.health(
        tmp_path,
        _config(backend="openai", url="http://127.0.0.1:9", model="bge-m3"),
    )

    assert payload["ok"] is False
    assert payload["code"] == "HEALTH_RESPONSE_TOO_LARGE"
    assert payload["message"]


class _UnreadResponse:
    """A response that must never be read before the total deadline is checked."""

    def __enter__(self) -> _UnreadResponse:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        raise AssertionError("the deadline must be checked before a blocking read")


def test_health_enforces_a_total_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P2-7: the socket timeout is per read, so a monotonic total deadline is needed."""
    monkeypatch.setattr(admin, "open_without_redirects", lambda request, timeout: _UnreadResponse())
    times = iter([100.0, 106.0])
    monkeypatch.setattr(admin, "_monotonic", lambda: next(times))

    payload = admin.health(
        tmp_path,
        _config(backend="openai", url="http://127.0.0.1:9", model="bge-m3"),
    )

    assert payload["ok"] is False
    assert payload["code"] == "HEALTH_TIMEOUT"
    assert payload["message"]


def test_health_maps_a_socket_timeout_to_health_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2-7: a per-socket timeout is reported as the structured timeout code."""

    def timed_out(request: object, timeout: float) -> object:
        raise TimeoutError("timed out")

    monkeypatch.setattr(admin, "open_without_redirects", timed_out)

    payload = admin.health(
        tmp_path,
        _config(backend="openai", url="http://127.0.0.1:9"),
    )

    assert payload["ok"] is False
    assert payload["code"] == "HEALTH_TIMEOUT"
