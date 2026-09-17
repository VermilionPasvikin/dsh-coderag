"""FTS5 search over the dsh_coderag index.

This module turns a query into a full-text match expression, ranks chunks
with bm25 and reports a structured status so callers never have to infer
"nothing is there" from an empty list (RL-06). It does not build the index
and does not render model-visible text.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from dsh_coderag.indexer import connect
from dsh_coderag.text import to_bigrams
from dsh_coderag.types import ErrorCode, Hit, SearchStatus


@dataclass(frozen=True)
class SearchResult:
    """A search outcome: a status plus, when ready, the hits."""

    status: SearchStatus
    query: str
    hits: list[Hit] = field(default_factory=list)
    scanned_files: int = 0
    scanned_chunks: int = 0
    message: str | None = None
    hint: str | None = None
    code: ErrorCode | None = None


def search(root: Path, query: str, k: int = 5) -> SearchResult:
    """Search the index under root and always return a structured status."""
    db_path = root.resolve() / ".coderag" / "index.sqlite3"
    if not db_path.exists():
        return SearchResult(
            status=SearchStatus.INDEXING,
            query=query,
            message="The code index for this workspace has not been built.",
            hint="Call code_index for this workspace, or use grep for exact identifiers.",
            code=ErrorCode.INDEX_NOT_FOUND,
        )
    connection = connect(db_path)
    try:
        files, chunks = _index_counts(connection)
        hits = _search(connection, query, k)
    finally:
        connection.close()
    if not hits:
        return SearchResult(
            status=SearchStatus.EMPTY,
            query=query,
            scanned_files=files,
            scanned_chunks=chunks,
            hint="No matches. Try different keywords, or use grep for exact identifiers.",
        )
    return SearchResult(
        status=SearchStatus.READY,
        query=query,
        hits=hits,
        scanned_files=files,
        scanned_chunks=chunks,
    )


def _search(connection: sqlite3.Connection, query: str, k: int) -> list[Hit]:
    match = _build_match(query)
    if match is None:
        return []
    rows = connection.execute(
        """
        SELECT f.path, c.seq, c.start_line, c.end_line, c.symbol_kind,
               c.symbol_name, c.text, bm25(chunks_fts)
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.chunk_id
        JOIN files f ON f.id = c.file_id
        WHERE chunks_fts MATCH ?
        ORDER BY bm25(chunks_fts)
        LIMIT ?
        """,
        (match, k),
    ).fetchall()
    return [
        Hit(
            path=path,
            seq=seq,
            start_line=start_line,
            end_line=end_line,
            text=text,
            score=score,
            symbol_kind=symbol_kind,
            symbol_name=symbol_name,
        )
        for path, seq, start_line, end_line, symbol_kind, symbol_name, text, score in rows
    ]


def _index_counts(connection: sqlite3.Connection) -> tuple[int, int]:
    files = connection.execute("SELECT count(*) FROM files").fetchone()[0]
    chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
    return int(files), int(chunks)


def _build_match(query: str) -> str | None:
    """Turn a query into an FTS5 MATCH expression of quoted phrases."""
    tokens = to_bigrams(query).split()
    if not tokens:
        return None
    return " ".join(_quote(token) for token in tokens)


def _quote(token: str) -> str:
    """Quote one token as an FTS5 phrase, doubling embedded quotes."""
    return '"' + token.replace('"', '""') + '"'
