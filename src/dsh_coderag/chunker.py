"""Declaration-aware chunking for dsh_coderag.

This module turns source text into indexable chunks. When the file's language
has a declaration mapping, chunks follow tree-sitter declaration boundaries
(functions, classes, structs, methods and namespaces). The leading
non-declaration block becomes a symbol_kind="module" header chunk of at most
MODULE_HEADER_LINES lines, other non-declaration content is emitted as gap
chunks, and a declaration longer than MAX_CHUNK_LINES is split into
consecutive "#part/N" parts at its internal statement boundaries. Languages
without a grammar fall back to blank-line paragraphs and mark every chunk
low_confidence. Chunks never overlap and cover all non-whitespace content.
Chunk text carries no contextual prefix yet (T2-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from dsh_coderag.parser import detect_language, get_parser
from dsh_coderag.types import Chunk

MAX_CHUNK_LINES = 200
MODULE_HEADER_LINES = 40

# Grammar name -> tree-sitter node type -> model-visible symbol kind.
DECLARATION_KINDS: dict[str, dict[str, str]] = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
        "union_specifier": "union",
        "enum_specifier": "enum",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
        "union_specifier": "union",
        "enum_specifier": "enum",
        "namespace_definition": "namespace",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "abstract_class_declaration": "class",
        "interface_declaration": "interface",
        "method_definition": "method",
    },
    "javascript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
}

# Wrapper nodes that contain exactly one declaration. The chunk spans the
# wrapper (so decorators, export and template keywords stay with the symbol)
# while its kind and name come from the inner declaration.
WRAPPER_NODE_TYPES: dict[str, frozenset[str]] = {
    "python": frozenset({"decorated_definition"}),
    "cpp": frozenset({"template_declaration"}),
    "typescript": frozenset({"export_statement"}),
    "javascript": frozenset({"export_statement"}),
}

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

# (start_line, end_line, symbol_kind, symbol_name, low_confidence)
Span = tuple[int, int, str | None, str | None, bool]


@dataclass(frozen=True)
class _Declaration:
    """One declaration found in a source file."""

    start_line: int
    end_line: int
    symbol_kind: str
    symbol_name: str | None
    breaks: tuple[int, ...] = ()


def chunk_text(
    text: str,
    path: str = "",
    lang: str | None = None,
    max_chunk_lines: int = MAX_CHUNK_LINES,
) -> list[Chunk]:
    """Split text into chunks, preferring declaration boundaries.

    path provides the chunk's workspace-relative path and, when lang is None,
    the language to detect. Line numbers are 1-based inclusive and seq is
    0-based in source order. Every non-whitespace line falls in exactly one
    chunk. Declarations longer than max_chunk_lines are split into parts.
    """
    lines = text.splitlines()
    if not lines:
        return []
    language = lang if lang is not None else detect_language(path)
    if language in DECLARATION_KINDS:
        declarations = _extract_declarations(text, language)
        spans = _declaration_spans(lines, declarations, max_chunk_lines)
    else:
        spans = _fallback_spans(lines)
    return [
        Chunk(
            path=path,
            seq=seq,
            start_line=start,
            end_line=end,
            text="\n".join(lines[start - 1 : end]),
            symbol_kind=symbol_kind,
            symbol_name=symbol_name,
            lang=language,
            low_confidence=low_confidence,
        )
        for seq, (start, end, symbol_kind, symbol_name, low_confidence) in enumerate(spans)
    ]


def chunk_file(
    path: Path, root: Path, max_chunk_lines: int = MAX_CHUNK_LINES
) -> list[Chunk]:
    """Read one file and label its chunks with a workspace-relative path."""
    text = path.read_text(encoding="utf-8", errors="replace")
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return chunk_text(text, relative, max_chunk_lines=max_chunk_lines)


def _extract_declarations(text: str, language: str) -> list[_Declaration]:
    """Return the outermost declarations of text, in source order."""
    # tree-sitter nodes read their text from the source buffer, so both the
    # encoded bytes and the tree must stay referenced for the whole traversal.
    source = text.encode("utf-8")
    tree = get_parser(language).parse(source)
    root = tree.root_node
    kinds = DECLARATION_KINDS[language]
    wrappers = WRAPPER_NODE_TYPES.get(language, frozenset())
    declarations: list[_Declaration] = []
    for child in root.children:
        declaration = _declaration_for(child, kinds, wrappers)
        if declaration is not None:
            declarations.append(declaration)
    declarations.sort(key=lambda item: item.start_line)
    return declarations


def _declaration_for(
    node: Node, kinds: dict[str, str], wrappers: frozenset[str]
) -> _Declaration | None:
    """Return the declaration node represents, unwrapping a wrapper if needed."""
    kind = kinds.get(node.type)
    if kind is not None:
        return _make_declaration(node, kind, _symbol_name(node), node)
    if node.type in wrappers:
        inner = _find_inner_declaration(node, kinds, wrappers)
        if inner is not None:
            return _make_declaration(node, kinds[inner.type], _symbol_name(inner), inner)
    return None


def _find_inner_declaration(
    node: Node, kinds: dict[str, str], wrappers: frozenset[str]
) -> Node | None:
    """Find the single declaration wrapped by node, descending through wrappers."""
    for child in node.children:
        if child.type in kinds:
            return child
        if child.type in wrappers:
            found = _find_inner_declaration(child, kinds, wrappers)
            if found is not None:
                return found
    return None


def _make_declaration(
    node: Node, symbol_kind: str, symbol_name: str | None, declaration: Node
) -> _Declaration:
    return _Declaration(
        start_line=node.start_point.row + 1,
        end_line=_end_line(node),
        symbol_kind=symbol_kind,
        symbol_name=symbol_name,
        breaks=_break_lines(declaration.child_by_field_name("body")),
    )


def _end_line(node: Node) -> int:
    """Return the 1-based last line holding content of node."""
    end = node.end_point
    line = end.row + 1
    if end.column == 0 and end.row > node.start_point.row:
        line -= 1
    return line


def _symbol_name(node: Node) -> str | None:
    """Return the declared symbol's name, or None for anonymous declarations."""
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


def _break_lines(body: Node | None) -> tuple[int, ...]:
    """Return candidate cut lines: the body's direct statements and comments.

    The node is read here, while the parsed tree is still alive; declarations
    keep only plain line numbers so no tree-sitter node escapes the parse.
    """
    if body is None:
        return ()
    return tuple(sorted({child.start_point.row + 1 for child in body.children}))


def _declaration_spans(
    lines: list[str], declarations: list[_Declaration], max_chunk_lines: int
) -> list[Span]:
    """Combine declaration, module header and gap spans without overlap."""
    covered: set[int] = set()
    spans: list[Span] = []
    for declaration in declarations:
        for start, end, name in _declaration_parts(declaration, max_chunk_lines):
            spans.append((start, end, declaration.symbol_kind, name, False))
        covered.update(range(declaration.start_line, declaration.end_line + 1))
    header = _module_header(lines, declarations)
    if header is not None:
        spans.append((header[0], header[1], "module", None, False))
        covered.update(range(header[0], header[1] + 1))
    for start, end in _uncovered_regions(lines, covered):
        spans.append((start, end, None, None, False))
    spans.sort(key=lambda span: (span[0], span[1]))
    return spans


def _module_header(
    lines: list[str], declarations: list[_Declaration]
) -> tuple[int, int] | None:
    """Return the leading module header span (first non-whitespace block)."""
    first_declaration = declarations[0].start_line if declarations else len(lines) + 1
    limit = min(MODULE_HEADER_LINES, first_declaration - 1)
    end = 0
    for line_number in range(1, limit + 1):
        if lines[line_number - 1].strip() != "":
            end = line_number
    return (1, end) if end >= 1 else None


def _declaration_parts(
    declaration: _Declaration, max_chunk_lines: int
) -> list[tuple[int, int, str | None]]:
    """Split one oversized declaration into (#part/N) spans, or return it whole."""
    length = declaration.end_line - declaration.start_line + 1
    if length <= max_chunk_lines:
        return [(declaration.start_line, declaration.end_line, declaration.symbol_name)]
    breaks = declaration.breaks
    ranges: list[tuple[int, int]] = []
    start = declaration.start_line
    while start <= declaration.end_line:
        limit = start + max_chunk_lines - 1
        if limit >= declaration.end_line:
            ranges.append((start, declaration.end_line))
            break
        candidates = [point for point in breaks if start < point <= limit + 1]
        cut_end = max(candidates) - 1 if candidates else limit
        ranges.append((start, cut_end))
        start = cut_end + 1
    return [
        (start, end, _part_name(declaration.symbol_name, index))
        for index, (start, end) in enumerate(ranges, start=1)
    ]


def _part_name(symbol_name: str | None, index: int) -> str | None:
    """Return the #part/N symbol name for one split part."""
    if symbol_name is None:
        return None
    return f"{symbol_name}#part/{index}"


def _uncovered_regions(lines: list[str], covered: set[int]) -> list[tuple[int, int]]:
    """Group uncovered non-whitespace lines into consecutive regions."""
    regions: list[tuple[int, int]] = []
    index = 1
    total = len(lines)
    while index <= total:
        if index in covered or lines[index - 1].strip() == "":
            index += 1
            continue
        start = index
        while index <= total and index not in covered and lines[index - 1].strip() != "":
            index += 1
        regions.append((start, index - 1))
    return regions


def _fallback_spans(lines: list[str]) -> list[Span]:
    """Split a file without a grammar into low-confidence blank-line paragraphs."""
    spans: list[Span] = []
    index = 1
    total = len(lines)
    while index <= total:
        if lines[index - 1].strip() == "":
            index += 1
            continue
        start = index
        while index <= total and lines[index - 1].strip() != "":
            index += 1
        for window_start, window_end in _windows(start, index - 1):
            spans.append((window_start, window_end, None, None, True))
    return spans


def _windows(start: int, end: int) -> list[tuple[int, int]]:
    """Split [start, end] into non-overlapping windows of MAX_CHUNK_LINES lines."""
    windows: list[tuple[int, int]] = []
    current = start
    while current <= end:
        stop = min(current + MAX_CHUNK_LINES - 1, end)
        windows.append((current, stop))
        current = stop + 1
    return windows
