"""Shared data types and enums for dsh_coderag.

This module defines the value objects passed between the walker, chunker,
indexer, searcher, renderer and task manager, plus the two stable enums
that appear in model-visible payloads. It contains no behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SearchStatus(str, Enum):
    """Status of a search response (PROJECT.md 5.6; model-visible)."""

    READY = "ready"
    INDEXING = "indexing"
    EMPTY = "empty"
    STALE = "stale"
    ERROR = "error"


class ErrorCode(str, Enum):
    """Stable error codes carried by structured error payloads."""

    INDEX_NOT_FOUND = "INDEX_NOT_FOUND"
    FTS5_UNAVAILABLE = "FTS5_UNAVAILABLE"
    INDEX_RUNNING = "INDEX_RUNNING"
    INDEX_TOO_MANY_FILES = "INDEX_TOO_MANY_FILES"
    INDEX_READ_FAILED = "INDEX_READ_FAILED"
    INDEX_WRITE_FAILED = "INDEX_WRITE_FAILED"
    SEARCH_INVALID_QUERY = "SEARCH_INVALID_QUERY"
    SEARCH_FAILED = "SEARCH_FAILED"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Chunk:
    """One indexable unit of a source file.

    Line numbers are 1-based and inclusive. path is a workspace-relative
    path using forward slashes (AGENTS.md C-07).
    """

    path: str
    seq: int
    start_line: int
    end_line: int
    text: str
    symbol_kind: str | None = None
    symbol_name: str | None = None
    lang: str | None = None
    low_confidence: bool = False


@dataclass(frozen=True)
class Hit:
    """A retrieved chunk together with its relevance score."""

    path: str
    seq: int
    start_line: int
    end_line: int
    text: str
    score: float
    symbol_kind: str | None = None
    symbol_name: str | None = None
    low_confidence: bool = False


@dataclass(frozen=True)
class SkipReport:
    """Files the index filter kept out, counted by reason (PROJECT.md 4.2).

    Model-visible: search and index status report these so a filtered file
    never looks like absent code.
    """

    reasons: dict[str, int] = field(default_factory=dict)

    @property
    def count(self) -> int:
        """Total number of skipped files across every reason."""
        return sum(self.reasons.values())


@dataclass(frozen=True)
class SearchResult:
    """A search outcome: a status plus, when ready, the hits."""

    status: SearchStatus
    query: str
    hits: list[Hit] = field(default_factory=list)
    scanned_files: int = 0
    scanned_chunks: int = 0
    message: str | None = None
    hint: str | None = None
    code: ErrorCode | None = None
    skipped: SkipReport = field(default_factory=SkipReport)
    omitted: int = 0


@dataclass
class IndexRun:
    """Persisted state of one indexing task (PROJECT.md 3.6 index_runs).

    state holds one of the task states pending, running, ready, failed or
    cancelled; it is a plain string because the task manager owns that
    state machine.
    """

    task_id: str
    root: str
    state: str
    total_files: int = 0
    done_files: int = 0
    total_chunks: int = 0
    done_chunks: int = 0
    message: str | None = None
    started_at: int = 0
    finished_at: int | None = None
