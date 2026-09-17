"""Render search hits into the model-visible text contract.

This module formats hits exactly as documented in PROJECT.md 3.5, which is
a byte-stable contract for the model. It does not search, rank or trim by
token budget; it only formats the hits and counters it is given.
"""

from __future__ import annotations

from dsh_coderag.types import Hit, SearchStatus


def render_search_result(
    hits: list[Hit],
    *,
    query: str,
    scanned_files: int,
    scanned_chunks: int,
    status: SearchStatus = SearchStatus.READY,
    omitted: int = 0,
) -> str:
    """Render hits as the model-visible search result text.

    Any change to the output must be reflected in tests/test_render.py.
    """
    header = "\n".join(
        [
            f"status: {status.value}",
            f'query: "{query}"',
            f"scanned: {scanned_files} files / {scanned_chunks} chunks",
            f"hits: {len(hits)} (sorted by source order)",
        ]
    )
    blocks = [header]
    for hit in hits:
        blocks.append(f"{_format_location(hit)}\n{hit.text}")
    if omitted > 0:
        noun = "hit" if omitted == 1 else "hits"
        pronoun = "it" if omitted == 1 else "them"
        blocks.append(
            f"[{omitted} more {noun} omitted by token budget;"
            f" raise max_tokens to see {pronoun}]"
        )
    return "\n\n".join(blocks) + "\n"


def _format_location(hit: Hit) -> str:
    """Format the separator line that precedes each hit body."""
    parts = [f"── {hit.path}:{hit.start_line}-{hit.end_line}"]
    label = " ".join(part for part in (hit.symbol_kind, hit.symbol_name) if part)
    if label:
        parts.append(f"[{label}]")
    parts.append(f"(chunk {hit.seq})")
    return "  ".join(parts)
