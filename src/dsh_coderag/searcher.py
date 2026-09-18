"""FTS5 search over the dsh_coderag index.

This module turns a query into a full-text match expression, ranks chunks
with bm25 and reports a structured status so callers never have to infer
"nothing is there" from an empty list (RL-06). It does not build the index
and does not render model-visible text.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from dsh_coderag.chunker import DECLARATION_KINDS, WRAPPER_NODE_TYPES
from dsh_coderag.config import DEFAULT_MAX_TOKENS
from dsh_coderag.indexer import connect
from dsh_coderag.parser import detect_language, get_parser
from dsh_coderag.text import to_bigrams
from dsh_coderag.types import ErrorCode, Hit, SearchResult, SearchStatus, SkipReport
from dsh_coderag.walker import walk_with_report

PUNCTUATION_QUERY_HINT = (
    "This looks like an exact code search. Use the grep tool instead"
    " — it matches punctuation."
)

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CJK = re.compile(r"[\u4e00-\u9fff]")

_TYPE_KINDS = frozenset({"class", "struct", "union", "interface"})
_NAME_NODE_TYPES = frozenset(
    {
        "identifier",
        "field_identifier",
        "type_identifier",
        "operator_name",
        "property_identifier",
        "qualified_identifier",
    }
)


@dataclass(frozen=True)
class OutlineSymbol:
    """One node of a file's symbol tree (PROJECT.md 3.5 code_outline)."""

    kind: str
    name: str | None
    start_line: int
    end_line: int
    children: tuple[OutlineSymbol, ...] = ()


def search(
    root: Path,
    query: str,
    k: int = 5,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    path: str | None = None,
) -> SearchResult:
    """Search the index under root and always return a structured status.

    The best k chunks are selected by bm25, re-sorted into source order and
    then trimmed to max_tokens; the number dropped is reported as omitted.
    path restricts the search to a workspace-relative subdirectory (or file);
    None searches the whole workspace.
    """
    base = root.resolve()
    try:
        path_prefix = _path_prefix(base, path)
    except ValueError as exc:
        return SearchResult(
            status=SearchStatus.ERROR,
            query=query,
            message=str(exc),
            code=ErrorCode.SEARCH_INVALID_QUERY,
        )
    db_path = base / ".coderag" / "index.sqlite3"
    if not db_path.exists():
        return SearchResult(
            status=SearchStatus.INDEXING,
            query=query,
            message="The code index for this workspace has not been built.",
            hint="Call code_index for this workspace, or use grep for exact identifiers.",
            code=ErrorCode.INDEX_NOT_FOUND,
        )
    connection = connect(db_path)
    try:
        files, chunks = _index_counts(connection)
        punctuation_only = _is_punctuation_only(query)
        match = None if punctuation_only else _build_match(query)
        candidates = (
            []
            if match is None
            else _search(connection, match, k, path_prefix)
        )
    finally:
        connection.close()
    skipped = SkipReport(reasons=walk_with_report(root).reasons)
    if not candidates:
        hint = (
            PUNCTUATION_QUERY_HINT
            if punctuation_only
            else "No matches. Try different keywords, or use grep for exact identifiers."
        )
        return SearchResult(
            status=SearchStatus.EMPTY,
            query=query,
            scanned_files=files,
            scanned_chunks=chunks,
            hint=hint,
            skipped=skipped,
        )
    hits, omitted = _trim_to_budget(candidates, max_tokens)
    return SearchResult(
        status=SearchStatus.READY,
        query=query,
        hits=hits,
        scanned_files=files,
        scanned_chunks=chunks,
        skipped=skipped,
        omitted=omitted,
    )


def _trim_to_budget(hits: list[Hit], max_tokens: int) -> tuple[list[Hit], int]:
    """Keep hits in output order until len(text)/3.5 exceeds max_tokens.

    The first hit is always kept so a non-empty result never renders as empty.
    """
    kept: list[Hit] = []
    used = 0.0
    for hit in hits:
        estimate = len(hit.text) / 3.5
        if kept and used + estimate > max_tokens:
            break
        kept.append(hit)
        used += estimate
    return kept, len(hits) - len(kept)


def _search(
    connection: sqlite3.Connection,
    match: str,
    k: int,
    path_prefix: str | None = None,
) -> list[Hit]:
    sql = """
        SELECT f.path, c.seq, c.start_line, c.end_line, c.symbol_kind,
               c.symbol_name, c.text, bm25(chunks_fts)
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.chunk_id
        JOIN files f ON f.id = c.file_id
        WHERE chunks_fts MATCH ?
    """
    params: list[object] = [match]
    if path_prefix is not None:
        escaped = _escape_like(path_prefix)
        sql += " AND (f.path = ? OR f.path LIKE ? ESCAPE '\\')"
        params.extend([escaped, f"{escaped}/%"])
    sql += " ORDER BY bm25(chunks_fts), c.id LIMIT ?"
    params.append(k)
    rows = connection.execute(sql, params).fetchall()
    hits = [
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
    # ADR-05: selection is by score, but output follows source order.
    hits.sort(key=lambda hit: (hit.path, hit.start_line))
    return hits


def _index_counts(connection: sqlite3.Connection) -> tuple[int, int]:
    files = connection.execute("SELECT count(*) FROM files").fetchone()[0]
    chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
    return int(files), int(chunks)


def _path_prefix(base: Path, path: str | None) -> str | None:
    """Return the workspace-relative prefix to filter on, or None for all.

    Raises:
        ValueError: If path escapes the workspace.
    """
    if path is None or path.strip() in ("", ".", "./"):
        return None
    target = (base / path).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"path escapes the workspace: {path}")
    relative = target.relative_to(base).as_posix()
    return None if relative in ("", ".") else relative


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a directory name matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _is_punctuation_only(query: str) -> bool:
    """True when the query has no identifier or CJK character to search.

    Short punctuation sequences cannot be matched by FTS5, so these queries
    route to grep instead of scanning (ADR-13).
    """
    if not query.strip():
        return False
    return _IDENTIFIER.search(query) is None and _CJK.search(query) is None


def _build_match(query: str) -> str | None:
    """Turn a query into an FTS5 MATCH expression of quoted phrases."""
    tokens = to_bigrams(query).split()
    if not tokens:
        return None
    return " ".join(_quote(token) for token in tokens)


def _quote(token: str) -> str:
    """Quote one token as an FTS5 phrase, doubling embedded quotes."""
    return '"' + token.replace('"', '""') + '"'


def outline(root: Path, path: str, max_depth: int = 2) -> list[OutlineSymbol]:
    """Return the symbol tree of one workspace file.

    Only declarations become symbols. Functions directly inside a class,
    struct, union or interface are labelled "method". A language without a
    grammar yields an empty outline.

    Raises:
        ValueError: If path escapes the workspace.
        FileNotFoundError: If path is not an existing file.
    """
    base = root.resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"path escapes the workspace: {path}")
    if not target.is_file():
        raise FileNotFoundError(path)
    language = detect_language(path)
    if language not in DECLARATION_KINDS:
        return []
    source = target.read_bytes()
    tree = get_parser(language).parse(source)
    kinds = DECLARATION_KINDS[language]
    wrappers = WRAPPER_NODE_TYPES.get(language, frozenset())
    symbols: list[OutlineSymbol] = []
    for child in tree.root_node.children:
        symbol = _outline_node(
            child, kinds, wrappers, parent_is_type=False, remaining_depth=max_depth
        )
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def _outline_node(
    node: Node,
    kinds: dict[str, str],
    wrappers: frozenset[str],
    parent_is_type: bool,
    remaining_depth: int,
) -> OutlineSymbol | None:
    """Turn one tree node into an outline symbol, recursing into its body."""
    kind = kinds.get(node.type)
    declaration = node
    if kind is None:
        if node.type not in wrappers:
            return None
        inner = _find_inner_declaration(node, kinds, wrappers)
        if inner is None:
            return None
        kind = kinds[inner.type]
        declaration = inner
    if kind == "function" and parent_is_type:
        kind = "method"
    children: list[OutlineSymbol] = []
    if remaining_depth > 1:
        body = declaration.child_by_field_name("body")
        if body is not None:
            child_parent_is_type = kind in _TYPE_KINDS
            for child in body.children:
                child_symbol = _outline_node(
                    child,
                    kinds,
                    wrappers,
                    parent_is_type=child_parent_is_type,
                    remaining_depth=remaining_depth - 1,
                )
                if child_symbol is not None:
                    children.append(child_symbol)
    return OutlineSymbol(
        kind=kind,
        name=_symbol_name(declaration),
        start_line=node.start_point.row + 1,
        end_line=_end_line(node),
        children=tuple(children),
    )


def _find_inner_declaration(
    node: Node, kinds: dict[str, str], wrappers: frozenset[str]
) -> Node | None:
    """Find the declaration a wrapper node contains."""
    for child in node.children:
        if child.type in kinds:
            return child
        if child.type in wrappers:
            found = _find_inner_declaration(child, kinds, wrappers)
            if found is not None:
                return found
    return None


def _symbol_name(node: Node) -> str | None:
    """Return a declaration's name, or None when it is anonymous."""
    named = node.child_by_field_name("name")
    if named is not None:
        return _node_text(named)
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        return _name_from_declarator(declarator)
    return None


def _name_from_declarator(node: Node) -> str | None:
    """Descend a C/C++ declarator chain to the identifier that names it."""
    inner = node.child_by_field_name("declarator")
    if inner is not None:
        found = _name_from_declarator(inner)
        if found is not None:
            return found
    if node.type in _NAME_NODE_TYPES:
        return _node_text(node)
    for child in node.children:
        if child.type in _NAME_NODE_TYPES:
            return _node_text(child)
    return None


def _node_text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", "replace")


def _end_line(node: Node) -> int:
    """Return the 1-based last line holding content of node."""
    end = node.end_point
    line = end.row + 1
    if end.column == 0 and end.row > node.start_point.row:
        line -= 1
    return line
