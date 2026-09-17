"""Naive workspace traversal for dsh_coderag.

This module collects code files by extension whitelist only. It does not
read file contents and, in this first version, applies no ignore rules;
T2-06 adds gitignore handling, the secret blacklist and size limits.
"""

from __future__ import annotations

from pathlib import Path

CODE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".c", ".h", ".cpp", ".hpp", ".ts", ".js"}
)


def walk(root: Path) -> list[tuple[Path, int, int]]:
    """Collect whitelisted code files below root, recursively.

    Returns (absolute path, size in bytes, mtime in nanoseconds) for every
    regular file whose suffix is in CODE_EXTENSIONS, sorted by path so the
    result is deterministic.
    """
    base = root.resolve()
    found: list[tuple[Path, int, int]] = []
    for candidate in base.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in CODE_EXTENSIONS:
            continue
        stat = candidate.stat()
        found.append((candidate, stat.st_size, stat.st_mtime_ns))
    found.sort(key=lambda entry: str(entry[0]))
    return found
