"""CJK bigram preprocessing for dsh_coderag.

FTS5's unicode61 tokenizer treats a run of CJK characters as a single
token, so a two-character word such as 令牌 cannot be matched directly.
This module expands every CJK run into overlapping bigrams before both
indexing and querying. The same function must be used on both sides
(PROJECT.md 5.3.1, ADR-07); applying it only on one side causes silent
zero recall.
"""

from __future__ import annotations

import re

CJK = re.compile(r"[\u4e00-\u9fff]+")


def to_bigrams(text: str) -> str:
    """Expand every CJK run in text into overlapping bigrams.

    Latin words and code are preserved and text without CJK is returned
    unchanged. Whitespace already present is kept; a single space is added
    only between pieces that would otherwise touch. The transformation is
    idempotent.
    """
    pieces: list[str] = []
    pos = 0
    for match in CJK.finditer(text):
        pieces.append(text[pos : match.start()])
        pieces.append(_bigram_run(match.group()))
        pos = match.end()
    pieces.append(text[pos:])
    return _join_pieces(pieces)


def _bigram_run(run: str) -> str:
    """Expand one CJK run into bigrams; a single character stays as-is."""
    if len(run) == 1:
        return run
    return " ".join(run[index : index + 2] for index in range(len(run) - 1))


def _join_pieces(pieces: list[str]) -> str:
    """Concatenate pieces, inserting a space only where they would touch."""
    result = ""
    for piece in pieces:
        if not piece:
            continue
        if result and not result[-1].isspace() and not piece[0].isspace():
            result += " "
        result += piece
    return result
