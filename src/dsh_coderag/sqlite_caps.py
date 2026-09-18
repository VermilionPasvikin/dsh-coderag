"""SQLite capability probing for dsh_coderag (TESTING.md 4.2).

FTS5 is a compile-time SQLite feature that genuinely varies across
distributions, so it is probed at runtime rather than assumed. This module
only answers capability questions; it does not open the index database.
"""

from __future__ import annotations

import sqlite3

FTS5_HINT = (
    "This Python build's SQLite has no FTS5. Install a Python/SQLite build"
    " compiled with -DSQLITE_ENABLE_FTS5 (for example a current conda or"
    " python.org build) and retry."
)


class Fts5UnavailableError(RuntimeError):
    """Raised when indexing is requested without SQLite FTS5 support."""


def fts5_available() -> bool:
    """Return True when the current SQLite is compiled with FTS5.

    The PRAGMA compile_options name drops the SQLITE_ prefix, so the check
    looks for ENABLE_FTS5, then confirms a probe table can actually be made.
    """
    with sqlite3.connect(":memory:") as connection:
        options = {row[0] for row in connection.execute("PRAGMA compile_options")}
        if "ENABLE_FTS5" not in options:
            return False
        try:
            connection.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
            return True
        except sqlite3.OperationalError:
            return False
