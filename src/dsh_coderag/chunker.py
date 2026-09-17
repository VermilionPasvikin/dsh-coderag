"""Naive fixed-size line chunker for dsh_coderag.

This module splits source text into overlapping fixed-size line windows.
It exists so the M1 loop can run before the tree-sitter based, declaration
aware chunker replaces it in M2. It assigns no symbol metadata and does not
write to the database.
"""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.types import Chunk

CHUNK_LINES = 80
OVERLAP_LINES = 20
_STRIDE = CHUNK_LINES - OVERLAP_LINES


def chunk_text(text: str, path: str, lang: str | None = None) -> list[Chunk]:
    """Split text into overlapping chunks of at most CHUNK_LINES lines.

    Every input line is covered by at least one chunk and consecutive chunks
    overlap by OVERLAP_LINES lines. Line numbers are 1-based inclusive; seq
    is 0-based.
    """
    lines = text.splitlines()
    total = len(lines)
    chunks: list[Chunk] = []
    start = 0
    seq = 0
    while start < total:
        end = min(start + CHUNK_LINES, total)
        chunks.append(
            Chunk(
                path=path,
                seq=seq,
                start_line=start + 1,
                end_line=end,
                text="\n".join(lines[start:end]),
                lang=lang,
            )
        )
        if end == total:
            break
        start += _STRIDE
        seq += 1
    return chunks


def chunk_file(path: Path, root: Path) -> list[Chunk]:
    """Read one file and label its chunks with a workspace-relative path."""
    text = path.read_text(encoding="utf-8", errors="replace")
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return chunk_text(text, relative)
