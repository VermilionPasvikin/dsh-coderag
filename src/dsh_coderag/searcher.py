"""FTS5 search over the dsh_coderag index.

This module turns a query into a full-text match expression, ranks chunks
with bm25 and returns them as hits. It does not build the index and does
not render model-visible text; the status contract is added in T1-13.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dsh_coderag.indexer import connect
from dsh_coderag.text import to_bigrams
from dsh_coderag.types import Hit


def search(root: Path, query: str, k: int = 5) -> list[Hit]:
    """Return up to k hits for query from the index under root, best first.

    Raises FileNotFoundError when the workspace has no index, rather than
    returning an empty list that would read as "the code is not there".
    """
    db_path = root.resolve() / ".coderag" / "index.sqlite3"
    if not db_path.exists():
        raise FileNotFoundError(f"no index for {root}; run 'dsh-coderag index' first")
    connection = connect(db_path)
    try:
        return _search(connection, query, k)
    finally:
        connection.close()


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


def _build_match(query: str) -> str | None:
    """Turn a query into an FTS5 MATCH expression of quoted phrases."""
    tokens = to_bigrams(query).split()
    if not tokens:
        return None
    return " ".join(_quote(token) for token in tokens)


def _quote(token: str) -> str:
    """Quote one token as an FTS5 phrase, doubling embedded quotes."""
    return '"' + token.replace('"', '""') + '"'
