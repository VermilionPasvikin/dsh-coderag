"""Tests for dsh_coderag.chunker."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.chunker import CHUNK_LINES, OVERLAP_LINES, chunk_file, chunk_text
from dsh_coderag.types import Chunk


def _make_text(line_count: int) -> str:
    return "\n".join(f"line {number}" for number in range(1, line_count + 1))


def _covered_lines(chunks: list[Chunk]) -> set[int]:
    covered: set[int] = set()
    for chunk in chunks:
        covered.update(range(chunk.start_line, chunk.end_line + 1))
    return covered


@pytest.mark.parametrize("line_count", [0, 1, 79, 80, 81, 140, 141, 250])
def test_chunks_cover_every_line_without_gaps(line_count: int) -> None:
    chunks = chunk_text(_make_text(line_count), "f.py")
    assert _covered_lines(chunks) == set(range(1, line_count + 1))


def test_consecutive_chunks_overlap_by_twenty_lines() -> None:
    chunks = chunk_text(_make_text(250), "big.py")
    assert [chunk.start_line for chunk in chunks] == [1, 61, 121, 181]
    assert [chunk.end_line for chunk in chunks] == [80, 140, 200, 250]
    assert chunks[1].start_line - chunks[0].start_line == CHUNK_LINES - OVERLAP_LINES


def test_chunk_text_preserves_the_source_lines() -> None:
    lines = [f"line {number}" for number in range(1, 101)]
    chunks = chunk_text("\n".join(lines), "f.py")
    assert chunks[0].text == "\n".join(lines[0:80])
    assert chunks[1].text == "\n".join(lines[60:100])


def test_chunks_carry_no_symbol_metadata() -> None:
    chunks = chunk_text(_make_text(100), "f.py")
    assert all(chunk.symbol_kind is None for chunk in chunks)
    assert all(chunk.symbol_name is None for chunk in chunks)


def test_short_file_becomes_a_single_chunk() -> None:
    chunks = chunk_text("a\nb\nc", "small.py")
    assert chunks == [
        Chunk(path="small.py", seq=0, start_line=1, end_line=3, text="a\nb\nc")
    ]


def test_empty_file_produces_no_chunks() -> None:
    assert chunk_text("", "empty.py") == []


def test_chunk_file_uses_workspace_relative_posix_paths(tiny_repo: Path) -> None:
    chunks = chunk_file(tiny_repo / "main.py", tiny_repo)
    assert len(chunks) == 1
    assert chunks[0].path == "main.py"
