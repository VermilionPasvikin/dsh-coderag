"""Tests for dsh_coderag.chunker dispatch and fallback behaviour."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.chunker import chunk_file, chunk_text


def _normalize(text: str) -> str:
    return "".join(text.split())


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_text("", "empty.py") == []


def test_language_is_detected_from_the_path() -> None:
    chunks = chunk_text("def add(a, b):\n    return a + b\n", "src/add.py")
    assert [(c.symbol_kind, c.symbol_name, c.start_line, c.end_line) for c in chunks] == [
        ("function", "add", 1, 2)
    ]
    assert chunks[0].lang == "python"
    assert chunks[0].low_confidence is False


def test_fallback_splits_paragraphs_on_blank_lines() -> None:
    chunks = chunk_text("alpha\nbeta\n\ngamma\n\n\ndelta\n", "notes.txt")
    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(1, 2), (4, 4), (7, 7)]


def test_fallback_marks_chunks_low_confidence() -> None:
    chunks = chunk_text("alpha\n\ngamma\n", "notes.txt")
    assert all(chunk.low_confidence for chunk in chunks)
    assert all(chunk.symbol_kind is None for chunk in chunks)


def test_fallback_chunks_cover_all_non_whitespace_content() -> None:
    text = "\n".join(f"token{number}" for number in range(1, 250))
    chunks = chunk_text(text, "notes.txt")
    assert _normalize("".join(chunk.text for chunk in chunks)) == _normalize(text)


def test_fallback_chunks_do_not_overlap() -> None:
    text = "\n".join(f"token{number}" for number in range(1, 250))
    chunks = chunk_text(text, "notes.txt")
    spans = sorted((chunk.start_line, chunk.end_line) for chunk in chunks)
    assert all(later[0] > earlier[1] for earlier, later in zip(spans, spans[1:], strict=False))


def test_chunk_file_uses_workspace_relative_posix_paths(tiny_repo: Path) -> None:
    chunks = chunk_file(tiny_repo / "main.py", tiny_repo)
    assert len(chunks) == 1
    assert chunks[0].path == "main.py"
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 2)
