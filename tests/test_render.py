"""Snapshot tests for the model-visible search result format (M9)."""

from __future__ import annotations

from pathlib import Path

import pytest
from inline_snapshot import snapshot

from dsh_coderag.indexer import index_sync
from dsh_coderag.render import render_search_result
from dsh_coderag.searcher import search
from dsh_coderag.types import Hit, SearchStatus


def _hit(path: str, seq: int, start: int, end: int, text: str) -> Hit:
    return Hit(path=path, seq=seq, start_line=start, end_line=end, text=text, score=0.0)


@pytest.mark.snapshot
def test_render_search_result_matches_the_contract() -> None:
    hits = [
        _hit("src/auth/token.py", 0, 1, 4, "def verify_token(raw):\n    ..."),
        _hit("src/auth/middleware.py", 3, 15, 33, "def require_auth():\n    ..."),
    ]
    out = render_search_result(
        hits, query="verify_token", scanned_files=3, scanned_chunks=7
    )
    assert out == snapshot("""\
status: ready
query: "verify_token"
scanned: 3 files / 7 chunks
hits: 2 (sorted by source order)

── src/auth/token.py:1-4  (chunk 0)
def verify_token(raw):
    ...

── src/auth/middleware.py:15-33  (chunk 3)
def require_auth():
    ...
""")


@pytest.mark.snapshot
def test_render_includes_symbol_and_omitted_note() -> None:
    hits = [
        Hit(
            path="src/auth/token.py",
            seq=7,
            start_line=42,
            end_line=67,
            text="def verify_token(raw: str) -> Claims:\n    ...",
            score=0.0,
            symbol_kind="function",
            symbol_name="verify_token",
        )
    ]
    out = render_search_result(
        hits,
        query="如何校验用户令牌",
        scanned_files=1284,
        scanned_chunks=9632,
        omitted=1,
    )
    assert out == snapshot("""\
status: ready
query: "如何校验用户令牌"
scanned: 1284 files / 9632 chunks
hits: 1 (sorted by source order)

── src/auth/token.py:42-67  [function verify_token]  (chunk 7)
def verify_token(raw: str) -> Claims:
    ...

[1 more hit omitted by token budget; raise max_tokens to see it]
""")


def test_render_uses_the_given_status() -> None:
    out = render_search_result(
        [], query="x", scanned_files=0, scanned_chunks=0, status=SearchStatus.EMPTY
    )
    assert out.startswith("status: empty\n")


def test_render_of_real_search_output_contains_the_hit_location(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    hits = search(tiny_repo, "add", k=5)
    out = render_search_result(hits, query="add", scanned_files=3, scanned_chunks=3)
    assert "status: ready" in out
    assert "main.py:1-2" in out
