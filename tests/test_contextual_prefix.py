"""Tests for the chunk context prefix (PROJECT.md 5.1)."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.chunker import chunk_file
from dsh_coderag.indexer import index_sync, open_index
from dsh_coderag.render import render_search_result, strip_context_prefix
from dsh_coderag.types import Hit, SearchResult, SearchStatus

PREFIX_MARKER = "// file: "


def test_contextual_prefix_leads_every_chunk(decl_repo: Path) -> None:
    chunks = chunk_file(decl_repo / "sample.c", decl_repo)
    assert chunks
    for chunk in chunks:
        first_line = chunk.text.split("\n", 1)[0]
        assert first_line.startswith(PREFIX_MARKER)
        assert f"lines {chunk.start_line}-{chunk.end_line}" in first_line


def test_contextual_prefix_names_the_matching_symbol(decl_repo: Path) -> None:
    chunks = chunk_file(decl_repo / "sample.c", decl_repo)
    function = next(chunk for chunk in chunks if chunk.symbol_name == "add")
    assert "symbol: function add" in function.text


def test_contextual_prefix_is_stored_in_the_index(tiny_repo: Path) -> None:
    index_sync(tiny_repo)
    connection = open_index(tiny_repo / ".coderag" / "index.sqlite3")
    try:
        texts = [row[0] for row in connection.execute("SELECT text FROM chunks")]
        bigrams = [row[0] for row in connection.execute("SELECT text_bigram FROM chunks_fts")]
    finally:
        connection.close()
    assert texts and all(text.startswith(PREFIX_MARKER) for text in texts)
    assert all(text.startswith(PREFIX_MARKER) for text in bigrams)


def test_contextual_prefix_is_not_repeated_in_render() -> None:
    prefixed = (
        "// file: src/auth/token.py  |  symbol: function verify_token  |  lines 42-67\n"
        "def verify_token(raw):\n"
        "    ..."
    )
    hit = Hit(
        path="src/auth/token.py",
        seq=7,
        start_line=42,
        end_line=67,
        text=prefixed,
        score=0.0,
        symbol_kind="function",
        symbol_name="verify_token",
    )
    out = render_search_result(
        SearchResult(
            status=SearchStatus.READY,
            query="verify_token",
            hits=[hit],
            scanned_files=1,
            scanned_chunks=1,
        )
    )
    assert out.count("// file:") == 0
    assert out.count("def verify_token(raw):") == 1
    assert "── src/auth/token.py:42-67  [function verify_token]  (chunk 7)" in out


def test_strip_context_prefix_leaves_plain_code_unchanged() -> None:
    assert strip_context_prefix("def f():\n    return 1\n") == "def f():\n    return 1\n"
    assert (
        strip_context_prefix("// file: not a prefix\ndef f():\n")
        == "// file: not a prefix\ndef f():\n"
    )
