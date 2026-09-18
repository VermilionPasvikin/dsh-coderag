"""Declaration-aware chunking for dsh_coderag.

This module turns source text into indexable chunks. When the file's language
has a declaration mapping, chunks follow tree-sitter declaration boundaries
(functions, classes, structs, methods and namespaces); any non-whitespace
region outside a declaration is emitted as its own chunk, so no content is
lost and chunks never overlap. Languages without a mapping fall back to fixed
line windows. Chunk text carries no contextual prefix yet (T2-05) and this
module never reads or writes the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from dsh_coderag.parser import detect_language, get_parser
from dsh_coderag.types import Chunk

FALLBACK_LINES = 80

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


@dataclass(frozen=True)
class _Declaration:
    """One declaration found in a source file."""

    start_line: int
    end_line: int
    symbol_kind: str
    symbol_name: str | None


def chunk_text(text: str, path: str = "", lang: str | None = None) -> list[Chunk]:
    """Split text into chunks, preferring declaration boundaries.

    path provides the chunk's workspace-relative path and, when lang is None,
    the language to detect. Line numbers are 1-based inclusive and seq is
    0-based in source order. Every non-whitespace line falls in exactly one
    chunk.
    """
    lines = text.splitlines()
    if not lines:
        return []
    language = lang if lang is not None else detect_language(path)
    if language in DECLARATION_KINDS:
        declarations = _extract_declarations(text, language)
        spans = _declaration_spans(lines, declarations)
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
        )
        for seq, (start, end, symbol_kind, symbol_name) in enumerate(spans)
    ]


def chunk_file(path: Path, root: Path) -> list[Chunk]:
    """Read one file and label its chunks with a workspace-relative path."""
    text = path.read_text(encoding="utf-8", errors="replace")
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return chunk_text(text, relative)


def _extract_declarations(text: str, language: str) -> list[_Declaration]:
    """Return the outermost declarations of text, in source order."""
    root = get_parser(language).parse(text.encode("utf-8")).root_node
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
        return _make_declaration(node, kind, _symbol_name(node))
    if node.type in wrappers:
        inner = _find_inner_declaration(node, kinds, wrappers)
        if inner is not None:
            return _make_declaration(node, kinds[inner.type], _symbol_name(inner))
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


def _make_declaration(node: Node, symbol_kind: str, symbol_name: str | None) -> _Declaration:
    return _Declaration(
        start_line=node.start_point.row + 1,
        end_line=_end_line(node),
        symbol_kind=symbol_kind,
        symbol_name=symbol_name,
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


def _declaration_spans(
    lines: list[str], declarations: list[_Declaration]
) -> list[tuple[int, int, str | None, str | None]]:
    """Combine declaration spans with chunks for uncovered non-whitespace lines."""
    covered: set[int] = set()
    spans: list[tuple[int, int, str | None, str | None]] = []
    for declaration in declarations:
        spans.append(
            (
                declaration.start_line,
                declaration.end_line,
                declaration.symbol_kind,
                declaration.symbol_name,
            )
        )
        covered.update(range(declaration.start_line, declaration.end_line + 1))
    for start, end in _uncovered_regions(lines, covered):
        spans.append((start, end, None, None))
    spans.sort(key=lambda span: (span[0], span[1]))
    return spans


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


def _fallback_spans(lines: list[str]) -> list[tuple[int, int, str | None, str | None]]:
    """Split a file with no declaration mapping into non-overlapping windows."""
    spans: list[tuple[int, int, str | None, str | None]] = []
    total = len(lines)
    start = 1
    while start <= total:
        end = min(start + FALLBACK_LINES - 1, total)
        spans.append((start, end, None, None))
        start = end + 1
    return spans
