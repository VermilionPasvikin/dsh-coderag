"""FTS5 search over the dsh_coderag index.

This module turns a query into a full-text match expression, ranks chunks
with bm25 and reports a structured status so callers never have to infer
"nothing is there" from an empty list (RL-06). A query is matched in
precision mode first (every token), then by an identifier-only OR, and only
then by a full OR that includes CJK bigrams, per PROJECT.md 5.3.1. It does not
build the index and does not render model-visible text.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from dsh_coderag import sqlite_caps, vectors
from dsh_coderag.chunker import DECLARATION_KINDS, WRAPPER_NODE_TYPES
from dsh_coderag.config import (
    DEFAULT_MAX_TOKENS,
    ConfigError,
    SemanticConfig,
    load_semantic_config,
)
from dsh_coderag.embed import SemanticError, embed_texts
from dsh_coderag.indexer import connect
from dsh_coderag.log import log_event
from dsh_coderag.parser import detect_language, get_parser
from dsh_coderag.text import to_bigrams
from dsh_coderag.types import (
    ErrorCode,
    Hit,
    SearchResult,
    SearchStatus,
    SemanticNotice,
    SkipReport,
)
from dsh_coderag.vectors import VectorIndex
from dsh_coderag.walker import walk_with_report

PUNCTUATION_QUERY_HINT = (
    "This looks like an exact code search. Use the grep tool instead"
    " — it matches punctuation."
)

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CJK = re.compile(r"[\u4e00-\u9fff]")

# ── 结构化加分（PROJECT.md §3.3 第 3 步）─────────────────────────────────
# Selection is by score, output stays in source order (ADR-05).
SYMBOL_MATCH_BOOST = 2.0
"""bm25 delta subtracted when a chunk's symbol_name matches a query identifier.

Exact symbol equality is a strong, cheap signal (PROJECT.md §3.3). The value
is deliberately small: it should break near-ties, not override a much better
lexical match."""

TEST_PATH_TIER_SQL = (
    "(f.path LIKE 'tests/%' OR f.path LIKE '%/tests/%'"
    " OR f.path LIKE '__tests__/%' OR f.path LIKE '%/__tests__/%'"
    " OR f.path LIKE '%.spec.%' OR f.path LIKE '%.test.%')"
)
"""SQL predicate selecting test paths, used as the first ORDER BY tier.

A test asserts on a symbol, it rarely defines it, so every non-test chunk is
ranked before every test chunk. Doing this in SQL (rather than over a widened
Python candidate pool) keeps the demotion exact: no pool size has to be large
enough to see past a run of test chunks. The LIKE patterns mirror the previous
Python regex; `tests_helper.py`, `latest.py`, `contest.py` and `spec.py` are
deliberately not matches.
"""

RRF_K = 60
"""Reciprocal-rank-fusion constant (PROJECT.md 5.3, ADR-16 2).

The Elasticsearch/Azure/Weaviate default. Deliberately not 2: that is Qdrant's
default and a known trap when moving between libraries.
"""

_TEST_PATH_RE = re.compile(r"(^|/)tests/|(^|/)__tests__/|\.spec\.|\.test\.")
"""Python twin of `TEST_PATH_TIER_SQL`, used when ordering fused candidates.

The vector path must inherit the same tier (ADR-16, update of 2026-09-24), and
fusion happens in Python, so the predicate has to exist on both sides. A test
asserts the two agree.
"""


def is_test_path(path: str) -> bool:
    """Whether `path` is a test path under the frozen tier predicate."""
    return _TEST_PATH_RE.search(path) is not None


def fusion_key(hit: Hit) -> tuple[str, int]:
    """Identify one chunk in both rankings: its path plus its sequence."""
    return (hit.path, hit.seq)


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[tuple[str, int]]], k: int = RRF_K
) -> dict[tuple[str, int], float]:
    """Score every document as `sum(1 / (k + rank))` over the given rankings.

    Only ranks matter, so the incomparable BM25 and cosine score scales never
    meet (PROJECT.md 5.3).
    """
    scores: dict[tuple[str, int], float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


def fuse_candidates(
    lexical: Sequence[Hit],
    vector: Sequence[Hit],
    *,
    limit: int,
    k: int = RRF_K,
) -> list[Hit]:
    """Fuse the BM25 and vector rankings and return at most `limit` hits.

    Ordering follows the frozen contract: the non-test-first tier comes first
    (ADR-16, update of 2026-09-24), then the descending RRF score, then a
    deterministic tie-break. The selected hits are returned in source order, so
    ADR-05 still holds for what the model sees.
    """
    by_key: dict[tuple[str, int], Hit] = {}
    for hit in (*lexical, *vector):
        by_key.setdefault(fusion_key(hit), hit)
    if not by_key:
        return []
    scores = reciprocal_rank_fusion(
        [
            [fusion_key(hit) for hit in lexical],
            [fusion_key(hit) for hit in vector],
        ],
        k,
    )
    ordered = sorted(
        by_key.values(),
        key=lambda hit: (
            is_test_path(hit.path),
            -scores[fusion_key(hit)],
            hit.path,
            hit.start_line,
        ),
    )[:limit]
    return sorted(ordered, key=lambda hit: (hit.path, hit.start_line))


def query_symbols(query: str) -> frozenset[str]:
    """ASCII identifiers in a query, used for exact `symbol_name` matching."""
    return frozenset(_IDENTIFIER.findall(query))

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


def _fts5_unavailable(query: str) -> SearchResult:
    """Return the structured error for an SQLite build without FTS5."""
    return SearchResult(
        status=SearchStatus.ERROR,
        query=query,
        message="SQLite FTS5 is not available in this Python build.",
        code=ErrorCode.FTS5_UNAVAILABLE,
        hint=sqlite_caps.FTS5_HINT,
    )


def _index_not_built(query: str) -> SearchResult:
    """Return the structured "not indexed yet" status (never an empty list)."""
    return SearchResult(
        status=SearchStatus.INDEXING,
        query=query,
        message="The code index for this workspace has not been built.",
        hint="Call code_index for this workspace, or use grep for exact identifiers.",
        code=ErrorCode.INDEX_NOT_FOUND,
    )


def _first_non_empty_rung(
    connection: sqlite3.Connection,
    query: str,
    k: int,
    path_prefix: str | None,
    symbols: frozenset[str],
) -> tuple[list[Hit], bool]:
    """Walk the three match rungs and return the first non-empty hit list.

    Returns the hits plus whether the query was punctuation-only, which the
    caller needs in order to pick the hint when nothing matched at all.
    """
    if _is_punctuation_only(query):
        return [], True
    # Three rungs, first non-empty wins (PROJECT.md 5.3.1): precision AND,
    # then an identifier-only OR, then the full OR including CJK bigrams.
    matches = [
        _build_match(query),
        _build_identifier_recall_match(query),
        _build_recall_match(query),
    ]
    seen: set[str] = set()
    for match in matches:
        if match is None or match in seen:
            continue
        seen.add(match)
        candidates = _search(connection, match, k, path_prefix, symbols)
        if candidates:
            return candidates, False
    return [], False


def _empty_result(
    query: str,
    files: int,
    chunks: int,
    skipped: SkipReport,
    punctuation_only: bool,
) -> SearchResult:
    """Return the structured empty status with a hint matched to the query."""
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


def _ready_result(
    query: str,
    candidates: list[Hit],
    files: int,
    chunks: int,
    skipped: SkipReport,
    max_tokens: int,
    semantic: SemanticNotice | None = None,
) -> SearchResult:
    """Trim candidates to the token budget and build the READY result.

    `semantic` is None on the default path, which is what keeps the rendered
    output byte-identical to 1.0.0 (ADR-16 2).
    """
    hits, omitted = _trim_to_budget(candidates, max_tokens)
    return SearchResult(
        status=SearchStatus.READY,
        query=query,
        hits=hits,
        scanned_files=files,
        scanned_chunks=chunks,
        skipped=skipped,
        omitted=omitted,
        semantic=semantic,
    )


def search(
    root: Path,
    query: str,
    k: int = 5,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    path: str | None = None,
    *,
    semantic: SemanticConfig | None = None,
) -> SearchResult:
    """Search the index under root and always return a structured status.

    The query is matched in three rungs (precision, identifier-only OR, then the
    full OR with CJK bigrams); the best k are re-sorted into source order
    (ADR-05) and trimmed to max_tokens, reporting how many hits were dropped.
    `path` restricts the search to a workspace-relative subdirectory or file.

    The optional backend participates only when `semantic` (by default
    CODERAG_SEMANTIC) is enabled. An enabled but unusable backend returns
    exactly the BM25 result plus a `semantic` notice (ADR-16 2/6).
    """
    if not sqlite_caps.fts5_available():
        return _fts5_unavailable(query)
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
        return _index_not_built(query)
    connection = connect(db_path)
    try:
        files, chunks = _index_counts(connection)
        candidates, punctuation_only = _first_non_empty_rung(
            connection, query, k, path_prefix, query_symbols(query)
        )
    finally:
        connection.close()
    skipped = SkipReport(reasons=walk_with_report(root).reasons)
    candidates, notice = _apply_semantic(base, query, k, candidates, semantic)
    if not candidates:
        return _empty_result(query, files, chunks, skipped, punctuation_only)
    return _ready_result(query, candidates, files, chunks, skipped, max_tokens, notice)


def _apply_semantic(
    base: Path,
    query: str,
    k: int,
    candidates: list[Hit],
    semantic: SemanticConfig | None,
) -> tuple[list[Hit], SemanticNotice | None]:
    """Fuse the optional backend's candidates in, or explain why it could not.

    Returns the candidates to use and the notice to report. Any failure of the
    optional path leaves `candidates` exactly as BM25 produced them, which is
    the frozen meaning of a clean fallback (ADR-16 2).
    """
    config, notice = _resolve_semantic(semantic)
    if config is None or not config.enabled:
        return candidates, notice
    try:
        vector_hits = _semantic_candidates(base, query, config, k)
    except SemanticError as exc:
        return candidates, SemanticNotice(code=exc.code, message=exc.message, hint=exc.hint)
    if not vector_hits:
        return candidates, notice
    return fuse_candidates(candidates, vector_hits, limit=k), notice


def _resolve_semantic(
    semantic: SemanticConfig | None,
) -> tuple[SemanticConfig | None, SemanticNotice | None]:
    """Return the effective semantic settings plus any notice to report.

    An unset or non-`on` switch yields no settings and no notice, so the default
    response carries no semantic field at all. A malformed switch value is
    logged instead of rendered, because ADR-16 2 freezes the non-`on` output as
    byte-identical to 1.0.0 (a rendered notice would break that and S6).
    """
    if semantic is not None:
        return semantic, None
    try:
        loaded = load_semantic_config()
    except ConfigError as exc:
        return None, SemanticNotice(
            code=ErrorCode.SEMANTIC_BACKEND_UNSUPPORTED, message=str(exc)
        )
    if loaded.switch_invalid:
        log_event(
            "semantic_switch_invalid",
            level="warning",
            value=loaded.switch_value,
        )
    return loaded, None


def _semantic_candidates(
    base: Path, query: str, config: SemanticConfig, k: int
) -> list[Hit]:
    """Embed the query and return the vector index's nearest chunks.

    Raises:
        SemanticError: Whatever the embedding client or the vector index raises;
            the caller converts it into a notice and keeps serving BM25.
    """
    query_vectors = embed_texts(config, [query])
    index = vectors.load_index(base, config)
    return vector_candidates(base, index, query_vectors[0], k)


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


def _search_sql(
    match: str,
    k: int,
    path_prefix: str | None,
    symbols: frozenset[str],
    symbol_boost: float,
) -> tuple[str, list[object]]:
    """Build the SELECT and its parameters for one match expression.

    Ordering lives in SQL so the `LIMIT` sees the final ranking: non-test
    chunks first, then bm25 adjusted by an exact `symbol_name` match, then
    `c.id` as the deterministic tiebreak.
    """
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
    order = [f"CASE WHEN {TEST_PATH_TIER_SQL} THEN 1 ELSE 0 END"]
    if symbols:
        placeholders = ", ".join("?" for _ in symbols)
        order.append(
            "bm25(chunks_fts) - (CASE WHEN c.symbol_name IN "
            f"({placeholders}) THEN ? ELSE 0 END)"
        )
        params.extend(sorted(symbols))
        params.append(symbol_boost)
    else:
        order.append("bm25(chunks_fts)")
    order.append("c.id")
    sql += f" ORDER BY {', '.join(order)} LIMIT ?"
    params.append(k)
    return sql, params


def _search(
    connection: sqlite3.Connection,
    match: str,
    k: int,
    path_prefix: str | None = None,
    symbols: frozenset[str] = frozenset(),
    symbol_boost: float = SYMBOL_MATCH_BOOST,
) -> list[Hit]:
    """Select the k best chunks, then return them in source order (ADR-05).

    Ordering is expressed in SQL so the `LIMIT` sees the final ranking:
    non-test chunks first, then the bm25 score adjusted by an exact
    `symbol_name` match, then `c.id` as the deterministic tiebreak.
    """
    sql, params = _search_sql(match, k, path_prefix, symbols, symbol_boost)
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


def vector_candidates(
    root: Path,
    index: VectorIndex,
    query_vector: Sequence[float],
    k: int,
) -> list[Hit]:
    """Return the k chunks whose vectors are closest to query_vector.

    The optional backend's recall step. Candidates come back in descending
    cosine order; ADR-05's source ordering is applied by the caller that fuses
    them with BM25.

    The frozen non-test-first tier (ADR-16, update of 2026-09-24) is applied
    **here, before the top-k cut**, not only at fusion time: this corpus is
    mostly test chunks, so cutting first would fill every slot with test files
    and the real implementation would never become a candidate at all.

    Args:
        root: Workspace root holding `.coderag/index.sqlite3`.
        index: A loaded `VectorIndex` from `vectors.load_index`.
        query_vector: The embedded query.
        k: Maximum number of candidates.

    Returns:
        At most k hits, non-test paths first, then closest first.

    Raises:
        SemanticError: SEMANTIC_INDEX_MISSING when a scored chunk is no longer
            in the BM25 index. That is index drift, not a partial answer, so it
            is reported instead of silently returning fewer candidates (RL-08).
    """
    connection = connect(root.resolve() / ".coderag" / "index.sqlite3")
    try:
        tiers = _row_tiers(connection, index.chunk_ids)
        scored = vectors.cosine_top_k(index.matrix, query_vector, k, tier=tiers)
        if not scored:
            return []
        return _load_scored_hits(connection, index, scored)
    finally:
        connection.close()


def _row_tiers(
    connection: sqlite3.Connection, chunk_ids: Sequence[int]
) -> list[int]:
    """Return 1 for rows whose path is a test path, 0 otherwise.

    Uses `TEST_PATH_TIER_SQL` itself, so the Python-side vector tier and the
    SQL-side BM25 tier can never drift apart.
    """
    test_ids = {
        int(row[0])
        for row in connection.execute(
            "SELECT c.id FROM chunks c JOIN files f ON f.id = c.file_id"
            f" WHERE {TEST_PATH_TIER_SQL}"
        )
    }
    return [1 if chunk_id in test_ids else 0 for chunk_id in chunk_ids]


def _load_scored_hits(
    connection: sqlite3.Connection,
    index: VectorIndex,
    scored: Sequence[tuple[int, float]],
) -> list[Hit]:
    """Load the scored chunks by id, preserving cosine order."""
    wanted = [index.chunk_ids[row] for row, _ in scored]
    placeholders = ", ".join("?" for _ in wanted)
    rows = connection.execute(
        "SELECT c.id, f.path, c.seq, c.start_line, c.end_line, c.symbol_kind,"
        " c.symbol_name, c.text FROM chunks c JOIN files f ON f.id = c.file_id"
        f" WHERE c.id IN ({placeholders})",
        wanted,
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    hits: list[Hit] = []
    for row_index, score in scored:
        chunk_id = index.chunk_ids[row_index]
        row = by_id.get(chunk_id)
        if row is None:
            raise SemanticError(
                ErrorCode.SEMANTIC_INDEX_MISSING,
                f"vector index row {row_index} points at chunk {chunk_id}, which is no "
                "longer in the BM25 index",
                "rebuild both indexes with code_index",
            )
        _, path, seq, start_line, end_line, symbol_kind, symbol_name, text = row
        hits.append(
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
        )
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
    """Precision match: every token must be present (AND of quoted phrases).

    For a CJK run the overlapping bigrams make this equivalent to an exact
    substring match (PROJECT.md 5.3.1).
    """
    return _join_phrases(to_bigrams(query).split(), " ")


def _build_identifier_recall_match(query: str) -> str | None:
    """Middle rung: OR over the query's ASCII identifiers only.

    CJK bigrams are high-recall but very low precision — in a repository with
    localization catalogs they match translation strings that outrank the real
    code, so they are held back for the last rung. Identifiers carry the
    discriminative intent, so they are tried first (PROJECT.md 5.3.1).
    """
    identifiers = list(dict.fromkeys(_IDENTIFIER.findall(query)))
    return _join_phrases(identifiers, " OR ")


def _build_recall_match(query: str) -> str | None:
    """Last rung: OR over every token, including CJK bigrams.

    Used only when both the precision match and the identifier-only recall
    found nothing, so a query whose only content is CJK can still hit
    (PROJECT.md 5.3.1, step 2).
    """
    return _join_phrases(to_bigrams(query).split(), " OR ")


def _join_phrases(tokens: list[str], operator: str) -> str | None:
    """Join quoted tokens with an FTS5 operator; None when there is no token."""
    if not tokens:
        return None
    return operator.join(_quote(token) for token in tokens)


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
