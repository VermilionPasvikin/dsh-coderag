"""Tests for oversized declaration splitting (PROJECT.md 5.1 L2)."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.chunker import MAX_CHUNK_LINES, chunk_file, chunk_text
from dsh_coderag.types import Chunk


def _declarations(chunks: list[Chunk]) -> list[Chunk]:
    return [chunk for chunk in chunks if chunk.symbol_kind not in (None, "module")]


def test_oversized_function_is_split_into_at_least_five_parts(oversized_repo: Path) -> None:
    path = oversized_repo / "big.py"
    declarations = _declarations(chunk_file(path, oversized_repo))
    assert len(declarations) >= 5
    assert all(
        declaration.end_line - declaration.start_line + 1 <= MAX_CHUNK_LINES
        for declaration in declarations
    )
    assert all(
        declaration.symbol_name is not None
        and declaration.symbol_name.startswith("big_function#part/")
        for declaration in declarations
    )


def test_oversized_parts_are_numbered_in_source_order(oversized_repo: Path) -> None:
    path = oversized_repo / "big.py"
    declarations = _declarations(chunk_file(path, oversized_repo))
    names = [declaration.symbol_name for declaration in declarations]
    assert names == [f"big_function#part/{index}" for index in range(1, len(declarations) + 1)]


def test_oversized_parts_cover_the_declaration_without_gaps_or_overlap(
    oversized_repo: Path,
) -> None:
    path = oversized_repo / "big.py"
    chunks = chunk_file(path, oversized_repo)
    spans = [(c.start_line, c.end_line) for c in _declarations(chunks)]
    assert spans[0][0] == 1
    assert spans[-1][1] == 1000
    assert all(
        later[0] == earlier[1] + 1
        for earlier, later in zip(spans, spans[1:], strict=False)
    )
    all_spans = sorted((c.start_line, c.end_line) for c in chunks)
    assert all(
        later[0] > earlier[1]
        for earlier, later in zip(all_spans, all_spans[1:], strict=False)
    )


def test_oversized_split_preserves_symbol_kind(oversized_repo: Path) -> None:
    path = oversized_repo / "big.py"
    declarations = _declarations(chunk_file(path, oversized_repo))
    assert {declaration.symbol_kind for declaration in declarations} == {"function"}


def test_small_declaration_is_not_split(decl_repo: Path) -> None:
    path = decl_repo / "sample.py"
    declarations = _declarations(chunk_file(path, decl_repo))
    assert all("#part/" not in (declaration.symbol_name or "") for declaration in declarations)


def test_max_chunk_lines_can_be_overridden() -> None:
    text = (
        "def f():\n"
        + "".join(f"    x{index} = {index}\n" for index in range(1, 50))
        + "    return x1\n"
    )
    chunks = chunk_text(text, "big.py", max_chunk_lines=10)
    declarations = _declarations(chunks)
    assert len(declarations) >= 5
    assert all(
        declaration.end_line - declaration.start_line + 1 <= 10
        for declaration in declarations
    )
