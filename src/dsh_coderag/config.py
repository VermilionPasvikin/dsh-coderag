"""Configuration loading and validation for dsh_coderag.

This module reads runtime settings from environment variables and validates
them. It does not guess values for required settings, does not read index
state, and does not depend on any other dsh_coderag module.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_ROOT = "CODERAG_ROOT"
ENV_MAX_FILES = "CODERAG_MAX_FILES"
ENV_MAX_TOKENS = "CODERAG_MAX_TOKENS"

DEFAULT_MAX_FILES = 20000
DEFAULT_MAX_TOKENS = 4000


class ConfigError(Exception):
    """Raised when a required setting is missing or a value is malformed."""


@dataclass(frozen=True)
class IndexConfig:
    """Validated settings that drive indexing and search."""

    root: Path
    max_files: int = DEFAULT_MAX_FILES
    max_tokens: int = DEFAULT_MAX_TOKENS


def load_config(environ: Mapping[str, str] | None = None) -> IndexConfig:
    """Build an IndexConfig from environment variables.

    Args:
        environ: Mapping to read. Defaults to os.environ; tests pass a
            controlled mapping instead of mutating the process environment.

    Raises:
        ConfigError: If CODERAG_ROOT is missing or empty, or if a numeric
            setting is not a positive integer.
    """
    env = os.environ if environ is None else environ
    root_value = env.get(ENV_ROOT)
    if root_value is None or not root_value.strip():
        raise ConfigError(f"{ENV_ROOT} is required and must be a non-empty path")
    return IndexConfig(
        root=Path(root_value),
        max_files=_read_positive_int(env, ENV_MAX_FILES, DEFAULT_MAX_FILES),
        max_tokens=_read_positive_int(env, ENV_MAX_TOKENS, DEFAULT_MAX_TOKENS),
    )


def _read_positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    """Return the positive integer stored at environ[name] or default."""
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer, got {value}")
    return value
