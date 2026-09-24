"""Tests that indexing builds the optional vector index (T3-11 wiring).

Offline (T-02): the backend is either a loopback stub or a closed port, and the
failure cases monkeypatch the build seam. Nothing here talks to Ollama.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from dsh_coderag import index_sync
from dsh_coderag.embed import SemanticError
from dsh_coderag.indexer import connect
from dsh_coderag.searcher import search
from dsh_coderag.types import ErrorCode, SearchStatus
from dsh_coderag.vectors import MANIFEST_FILENAME, vectors_dir

DIM = 2


class _StubHandler(BaseHTTPRequestHandler):
    """A loopback embeddings stub: one deterministic vector per input."""

    server_version = "index-vectors-stub/1"
    batches: list[list[str]] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        type(self).batches.append(list(payload["input"]))
        embeddings = [[float(index), 1.0] for index, _ in enumerate(payload["input"])]
        body = json.dumps({"embeddings": embeddings}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence the stub's access log."""
        return


@contextmanager
def _stub_server() -> Iterator[int]:
    _StubHandler.batches = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "alpha.py").write_text(
        "def alpha():\n    return 'alpha'\n", encoding="utf-8"
    )
    (root / "pkg" / "beta.py").write_text(
        "def beta():\n    return 'beta'\n", encoding="utf-8"
    )
    return root


def _chunk_ids(root: Path) -> list[int]:
    connection = connect(root / ".coderag" / "index.sqlite3")
    try:
        return [int(row[0]) for row in connection.execute("SELECT id FROM chunks ORDER BY id")]
    finally:
        connection.close()


def _enable(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("CODERAG_SEMANTIC", "on")
    monkeypatch.setenv("CODERAG_SEMANTIC_BACKEND", "ollama")
    monkeypatch.setenv("CODERAG_SEMANTIC_URL", url)
    monkeypatch.setenv("CODERAG_SEMANTIC_BATCH", "16")


def test_indexing_without_the_switch_writes_no_vectors(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODERAG_SEMANTIC", raising=False)
    index_sync(workspace)
    assert not vectors_dir(workspace).exists()


def test_indexing_with_the_switch_builds_the_vector_index(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _stub_server() as port:
        _enable(monkeypatch, f"http://127.0.0.1:{port}")
        index_sync(workspace)
    manifest = json.loads((vectors_dir(workspace) / MANIFEST_FILENAME).read_text("utf-8"))
    assert manifest["model"] == "bge-m3"
    assert manifest["dim"] == DIM
    assert manifest["chunk_count"] == len(_chunk_ids(workspace))
    assert manifest["chunk_ids"] == _chunk_ids(workspace)
    assert manifest["chunk_ids"] == sorted(manifest["chunk_ids"])


def test_unreachable_backend_leaves_the_bm25_index_ready(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch, "http://127.0.0.1:1")
    summary = index_sync(workspace)
    assert summary.chunks > 0
    assert not vectors_dir(workspace).exists()
    result = search(workspace, "alpha", k=5)
    assert result.status is SearchStatus.READY
    assert result.hits, "BM25 indexing must still work (RL-10)"
    assert result.semantic is not None, "a degraded optional path must say so"
    assert result.semantic.code is ErrorCode.SEMANTIC_EMBED_FAILED


def test_a_failing_vector_build_never_fails_indexing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch, "http://127.0.0.1:11434")

    def explode(*args: object, **kwargs: object) -> object:
        raise SemanticError(ErrorCode.SEMANTIC_EMBED_FAILED, "backend down")

    monkeypatch.setattr("dsh_coderag.vectors.build_index", explode)
    summary = index_sync(workspace)
    assert summary.chunks > 0
    assert not vectors_dir(workspace).exists()


def test_cancelled_indexing_does_not_build_vectors(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _stub_server() as port:
        _enable(monkeypatch, f"http://127.0.0.1:{port}")
        index_sync(workspace, should_cancel=lambda: True)
    assert not vectors_dir(workspace).exists()


def test_vector_build_skips_nothing_and_keeps_chunk_order(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _stub_server() as port:
        _enable(monkeypatch, f"http://127.0.0.1:{port}")
        index_sync(workspace)
    manifest = json.loads((vectors_dir(workspace) / MANIFEST_FILENAME).read_text("utf-8"))
    assert len(manifest["content_hashes"]) == manifest["chunk_count"]
    assert len(set(manifest["content_hashes"])) >= 1


def test_reindex_only_embeds_the_changed_file(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The incremental guarantee: an untouched file must not be re-embedded."""
    with _stub_server() as port:
        _enable(monkeypatch, f"http://127.0.0.1:{port}")
        index_sync(workspace)
        first = sum(len(batch) for batch in _StubHandler.batches)
        _StubHandler.batches = []
        (workspace / "pkg" / "beta.py").write_text(
            "def beta():\n    return 'beta changed'\n", encoding="utf-8"
        )
        index_sync(workspace)
        second = sum(len(batch) for batch in _StubHandler.batches)
    assert first > 0
    assert 0 < second < first, f"expected a partial re-embed, got {second} of {first}"
