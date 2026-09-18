"""Secret detection for the indexing filter (PROJECT.md 5.5, AGENTS.md 4).

This module implements layer 1 (the built-in secret filename and path
blacklist) and layer 3 (content-level regex scanning) of the indexing filter.
It does not walk the workspace, read files or write the database. It never
returns or logs the matched secret text: callers get a pattern name only.

Layer 2 (the project ignore rules) lives in dsh_coderag.walker.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# Built-in file name blacklist. This cannot be disabled by configuration.
SECRET_FILENAME_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    "credentials*",
    "*_rsa",
    "*_ed25519",
)

# Path fragments are matched against the POSIX path with a leading slash, so
# relative and absolute paths behave the same.
SECRET_PATH_FRAGMENTS: tuple[str, ...] = (
    "/.ssh/",
    "/.aws/",
    "/.gnupg/",
    "/.kube/",
    "/.docker/config.json",
)

# Content-level patterns. The name is safe to log; the matched text is not.
CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]+")),
)


def is_secret_path(path: Path) -> bool:
    """Return True when path matches the built-in secret blacklist.

    The file name is matched with fnmatch globs; path fragments are matched
    against the POSIX path with a leading slash.
    """
    if any(fnmatch.fnmatchcase(path.name, pattern) for pattern in SECRET_FILENAME_PATTERNS):
        return True
    posix = "/" + path.as_posix().lstrip("/")
    return any(fragment in posix for fragment in SECRET_PATH_FRAGMENTS)


def scan_secret(text: str) -> str | None:
    """Return the name of the first content pattern matching text, or None.

    The matched text is never returned or logged (PROJECT.md 5.5).
    """
    for name, pattern in CONTENT_PATTERNS:
        if pattern.search(text):
            return name
    return None
