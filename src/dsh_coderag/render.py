"""Render search hits and status payloads into the model-visible contract.

This module formats hits and status messages exactly as documented in
PROJECT.md 3.5, which is a byte-stable contract for the model. It does not
search, rank or trim by token budget.
"""

from __future__ import annotations

from dsh_coderag.types import ErrorCode, Hit, SearchResult, SearchStatus

_CONTEXT_PREFIX_MARKER = "// file: "


def strip_context_prefix(text: str) -> str:
    """Remove the chunker's contextual prefix line from one hit body.

    dsh_coderag.chunker prepends a "// file: ... | ... | lines M-N" line so
    the path, symbol and line range are searchable. The hit's location is
    already rendered as its own line, so the body drops the prefix to avoid
    repeating it and to keep the code body clean.
    """
    first_line, separator, remainder = text.partition("\n")
    if (
        separator
        and first_line.startswith(_CONTEXT_PREFIX_MARKER)
        and "  |  " in first_line
    ):
        return remainder
    return text


def render_search_result(result: SearchResult, *, omitted: int = 0) -> str:
    """Render a search result as the model-visible text.

    Any change to the output must be reflected in tests/test_render.py.
    """
    header = "\n".join(
        [
            f"status: {result.status.value}",
            f'query: "{result.query}"',
            f"scanned: {result.scanned_files} files / {result.scanned_chunks} chunks",
            f"hits: {len(result.hits)} (sorted by source order)",
        ]
    )
    blocks = [header]
    for hit in result.hits:
        blocks.append(f"{_format_location(hit)}\n{strip_context_prefix(hit.text)}")
    if omitted > 0:
        noun = "hit" if omitted == 1 else "hits"
        pronoun = "it" if omitted == 1 else "them"
        blocks.append(
            f"[{omitted} more {noun} omitted by token budget;"
            f" raise max_tokens to see {pronoun}]"
        )
    return "\n\n".join(blocks) + "\n"


def render_status(
    status: SearchStatus,
    *,
    message: str | None = None,
    code: ErrorCode | None = None,
    hint: str | None = None,
) -> str:
    """Render a status or error payload as model-visible plain text.

    Fields appear in a fixed order and every dynamic value is collapsed onto
    one line so it cannot forge an extra status field.
    """
    lines = [f"status: {status.value}"]
    if code is not None:
        lines.append(f"code: {code.value}")
    if message is not None:
        lines.append(f"message: {_one_line(message)}")
    if hint is not None:
        lines.append(f"hint: {_one_line(hint)}")
    return "\n".join(lines) + "\n"


def _format_location(hit: Hit) -> str:
    """Format the separator line that precedes each hit body."""
    parts = [f"── {hit.path}:{hit.start_line}-{hit.end_line}"]
    label = " ".join(part for part in (hit.symbol_kind, hit.symbol_name) if part)
    if label:
        parts.append(f"[{label}]")
    parts.append(f"(chunk {hit.seq})")
    return "  ".join(parts)


def _one_line(value: str) -> str:
    """Collapse a dynamic value to one line of single-spaced words."""
    return " ".join(value.split())
