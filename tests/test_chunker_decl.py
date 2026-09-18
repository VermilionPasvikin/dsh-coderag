"""Tests for declaration-aware chunking in dsh_coderag.chunker."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dsh_coderag.chunker import chunk_file, chunk_text
from dsh_coderag.types import Chunk

# (symbol_kind, symbol_name, start_line, end_line) for every chunk, in source
# order. Annotated by hand from tests/fixtures/decl/*.
EXPECTED_CHUNKS: dict[str, list[tuple[str | None, str | None, int, int]]] = {
    "sample.py": [
        (None, None, 1, 1),
        ("function", "add", 4, 5),
        ("function", "decorator", 8, 9),
        ("function", "run", 12, 14),
        ("class", "Pool", 17, 19),
    ],
    "sample.c": [
        (None, None, 1, 1),
        ("struct", "Point", 3, 6),
        ("function", "add", 8, 10),
    ],
    "sample.cpp": [
        (None, None, 1, 1),
        ("class", "Pool", 3, 6),
        ("struct", "Point", 8, 11),
        ("function", "add", 13, 15),
    ],
    "sample.ts": [
        (None, None, 1, 1),
        ("function", "add", 3, 5),
        ("class", "Pool", 7, 11),
        (None, None, 13, 13),
    ],
}

EXPECTED_DECLARATION_COUNTS: dict[str, int] = {
    "sample.py": 4,
    "sample.c": 2,
    "sample.cpp": 3,
    "sample.ts": 2,
}


def _spans(chunks: list[Chunk]) -> list[tuple[str | None, str | None, int, int]]:
    return [(c.symbol_kind, c.symbol_name, c.start_line, c.end_line) for c in chunks]


def _normalize(text: str) -> str:
    return "".join(text.split())


@pytest.mark.parametrize("filename", sorted(EXPECTED_CHUNKS))
def test_declaration_chunks_match_manual_annotation(decl_repo: Path, filename: str) -> None:
    path = decl_repo / filename
    chunks = chunk_text(path.read_text(encoding="utf-8"), filename)
    assert _spans(chunks) == EXPECTED_CHUNKS[filename]


@pytest.mark.parametrize("filename", sorted(EXPECTED_CHUNKS))
def test_declaration_count_matches_manual_annotation(decl_repo: Path, filename: str) -> None:
    path = decl_repo / filename
    chunks = chunk_text(path.read_text(encoding="utf-8"), filename)
    declarations = [c for c in chunks if c.symbol_kind is not None]
    assert len(declarations) == EXPECTED_DECLARATION_COUNTS[filename]


@pytest.mark.parametrize("filename", sorted(EXPECTED_CHUNKS))
def test_chunks_cover_content_without_overlap(decl_repo: Path, filename: str) -> None:
    path = decl_repo / filename
    source = path.read_text(encoding="utf-8")
    chunks = chunk_text(source, filename)
    assert _normalize("".join(chunk.text for chunk in chunks)) == _normalize(source)
    spans = sorted((chunk.start_line, chunk.end_line) for chunk in chunks)
    assert all(later[0] > earlier[1] for earlier, later in zip(spans, spans[1:], strict=False))


def test_chunk_file_matches_chunk_text_on_a_declaration_fixture(decl_repo: Path) -> None:
    path = decl_repo / "sample.py"
    file_chunks = chunk_file(path, decl_repo)
    text_chunks = chunk_text(path.read_text(encoding="utf-8"), "sample.py")
    assert [(c.seq, c.start_line, c.end_line, c.symbol_name) for c in file_chunks] == [
        (c.seq, c.start_line, c.end_line, c.symbol_name) for c in text_chunks
    ]
    assert file_chunks[1].path == "sample.py"


def test_lang_argument_overrides_path_detection() -> None:
    chunks = chunk_text("int add(int a, int b) { return a + b; }\n", "notes.txt", lang="c")
    assert _spans(chunks) == [("function", "add", 1, 1)]


# tree-sitter counts rows by newline, while str.splitlines() also breaks on
# CR, VT, FF and Unicode separators; the alphabet keeps the two in agreement.
_LINE_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="\r\v\f\x1c\x1d\x1e\x85\u2028\u2029",
    ),
    min_size=1,
    max_size=2000,
)


@settings(max_examples=100, deadline=None)
@given(_LINE_TEXT)
def test_chunker_never_loses_content(text: str) -> None:
    chunks = chunk_text(text, lang="python")
    assert _normalize("".join(chunk.text for chunk in chunks)) == _normalize(text)


@settings(max_examples=100, deadline=None)
@given(_LINE_TEXT)
def test_chunker_never_overlaps(text: str) -> None:
    chunks = chunk_text(text, lang="python")
    spans = sorted((chunk.start_line, chunk.end_line) for chunk in chunks)
    assert all(
        later[0] > earlier[1] for earlier, later in zip(spans, spans[1:], strict=False)
    )
