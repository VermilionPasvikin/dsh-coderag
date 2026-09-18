"""Workspace traversal and the project ignore filter.

This module collects code files by extension, then applies layer 1 (the
built-in secret blacklist from dsh_coderag.sanitize) and layer 2 (the project
ignore rules: .gitignore followed by .coderagignore, via pathspec). It does
not read file contents; the layer 3 content scan runs in the indexer over
each chunk.
"""

from __future__ import annotations

from pathlib import Path

import pathspec

from dsh_coderag.sanitize import is_secret_path

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


def walk(root: Path) -> list[tuple[Path, int, int]]:
    """Collect whitelisted, non-secret, non-ignored files below root.

    Returns (absolute path, size in bytes, mtime in nanoseconds) for every
    regular file whose suffix is in CODE_EXTENSIONS, sorted by path so the
    result is deterministic.
    """
    base = root.resolve()
    spec = load_ignore_spec(base)
    found: list[tuple[Path, int, int]] = []
    for candidate in base.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in CODE_EXTENSIONS:
            continue
        relative = candidate.relative_to(base).as_posix()
        if is_secret_path(Path(relative)) or spec.match_file(relative):
            continue
        stat = candidate.stat()
        found.append((candidate, stat.st_size, stat.st_mtime_ns))
    found.sort(key=lambda entry: str(entry[0]))
    return found
