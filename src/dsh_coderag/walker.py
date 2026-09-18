"""Workspace traversal and the project ignore filter.

This module collects code files by extension, then applies layer 1 (the
built-in secret blacklist from dsh_coderag.sanitize) and layer 2 (the project
ignore rules: .gitignore followed by .coderagignore, via pathspec). It does
not read file contents; the layer 3 content scan runs in the indexer over
each chunk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from dsh_coderag.config import DEFAULT_MAX_FILES
from dsh_coderag.sanitize import is_secret_path
from dsh_coderag.types import ErrorCode

CODE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".c", ".h", ".cpp", ".hpp", ".ts", ".js"}
)

IGNORE_FILES: tuple[str, ...] = (".gitignore", ".coderagignore")


def load_ignore_spec(root: Path) -> pathspec.GitIgnoreSpec:
    """Build the combined GitIgnoreSpec from .gitignore and .coderagignore.

    .coderagignore is read last so its patterns can override .gitignore.
    """
    lines: list[str] = []
    for name in IGNORE_FILES:
        ignore_file = root / name
        if ignore_file.is_file():
            text = ignore_file.read_text(encoding="utf-8", errors="replace")
            lines.extend(text.splitlines())
    return pathspec.GitIgnoreSpec.from_lines(lines)


class TooManyFilesError(Exception):
    """Raised when a walk finds more indexable files than max_files (RL-08).

    Carries the real count so callers can report it instead of silently
    truncating the workspace.
    """

    def __init__(self, actual_count: int, max_files: int) -> None:
        super().__init__(
            f"workspace has {actual_count} indexable files, over max_files={max_files}"
        )
        self.actual_count = actual_count
        self.max_files = max_files
        self.code = ErrorCode.INDEX_TOO_MANY_FILES

    @property
    def payload(self) -> dict[str, object]:
        """Structured error body for model-visible returns (PROJECT.md 5.6)."""
        return {
            "code": self.code.value,
            "actual_count": self.actual_count,
            "max_files": self.max_files,
            "message": str(self),
        }


@dataclass
class WalkReport:
    """One walk's collected files plus the per-reason skip counts."""

    files: list[tuple[Path, int, int]] = field(default_factory=list)
    reasons: dict[str, int] = field(default_factory=dict)


def walk(
    root: Path, max_files: int = DEFAULT_MAX_FILES
) -> list[tuple[Path, int, int]]:
    """Collect whitelisted, non-secret, non-ignored files below root."""
    return walk_with_report(root, max_files=max_files).files


def walk_with_report(
    root: Path, max_files: int = DEFAULT_MAX_FILES
) -> WalkReport:
    """Collect code files under root and count why others were skipped.

    Returns (absolute path, size in bytes, mtime in nanoseconds) for every
    regular file whose suffix is in CODE_EXTENSIONS, sorted by path, plus the
    number of code files dropped per reason (secret_file, gitignored). A file
    that is not a code extension at all is not a skip.

    Raises:
        TooManyFilesError: If more than max_files indexable files exist. The
            error carries the real count; the walk never truncates silently.
    """
    base = root.resolve()
    spec = load_ignore_spec(base)
    report = WalkReport()
    for candidate in base.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in CODE_EXTENSIONS:
            continue
        relative = candidate.relative_to(base).as_posix()
        if is_secret_path(Path(relative)):
            _count(report.reasons, "secret_file")
            continue
        if spec.match_file(relative):
            _count(report.reasons, "gitignored")
            continue
        stat = candidate.stat()
        report.files.append((candidate, stat.st_size, stat.st_mtime_ns))
    report.files.sort(key=lambda entry: str(entry[0]))
    if len(report.files) > max_files:
        raise TooManyFilesError(actual_count=len(report.files), max_files=max_files)
    return report


def _count(reasons: dict[str, int], reason: str) -> None:
    reasons[reason] = reasons.get(reason, 0) + 1
