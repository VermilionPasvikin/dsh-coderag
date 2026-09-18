"""Tests for dsh_coderag.chunker dispatch and fallback behaviour."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.chunker import FALLBACK_LINES, chunk_file, chunk_text


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


def test_unknown_language_falls_back_to_line_windows() -> None:
    text = "\n".join(f"line {number}" for number in range(1, 200))
    chunks = chunk_text(text, "notes.txt")
    assert [c.start_line for c in chunks] == [
        1,
        FALLBACK_LINES + 1,
        2 * FALLBACK_LINES + 1,
    ]
    assert all(c.symbol_kind is None for c in chunks)


def test_fallback_chunks_cover_all_non_whitespace_content() -> None:
    text = "\n".join(f"token{number}" for number in range(1, 200))
    chunks = chunk_text(text, "notes.txt")
    assert _normalize("".join(c.text for c in chunks)) == _normalize(text)


def test_fallback_chunks_do_not_overlap() -> None:
    text = "\n".join(f"token{number}" for number in range(1, 200))
    chunks = chunk_text(text, "notes.txt")
    spans = sorted((c.start_line, c.end_line) for c in chunks)
    assert all(later[0] > earlier[1] for earlier, later in zip(spans, spans[1:], strict=False))


def test_chunk_file_uses_workspace_relative_posix_paths(tiny_repo: Path) -> None:
    chunks = chunk_file(tiny_repo / "main.py", tiny_repo)
    assert len(chunks) == 1
    assert chunks[0].path == "main.py"
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 2)
