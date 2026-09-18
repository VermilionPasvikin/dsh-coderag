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
ENV_BATCH_SIZE = "CODERAG_BATCH_SIZE"
ENV_MAX_WORKERS = "CODERAG_MAX_WORKERS"
ENV_MAX_FILE_BYTES = "CODERAG_MAX_FILE_BYTES"

DEFAULT_MAX_FILES = 20000
DEFAULT_MAX_TOKENS = 4000
DEFAULT_MAX_FILE_BYTES = 1024 * 1024

# Adaptive concurrency and batching (PROJECT.md 5.2, constraints C8 / RL-07).
DEFAULT_BATCH_SIZE = 64
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 512
FAST_BATCH_SECONDS = 0.2
SLOW_BATCH_SECONDS = 2.0
MAX_WORKERS = 8
WORKER_MEMORY_BYTES = 64 * 1024 * 1024


class ConfigError(Exception):
    """Raised when a required setting is missing or a value is malformed."""


@dataclass(frozen=True)
class IndexConfig:
    """Validated settings that drive indexing and search."""

    root: Path
    max_files: int = DEFAULT_MAX_FILES
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    batch_size: int | None = None
    max_workers: int | None = None

    @property
    def workers(self) -> int:
        """Worker count: the override, else derived from CPU count and memory."""
        if self.max_workers is not None:
            return self.max_workers
        return adaptive_workers()

    @property
    def start_batch_size(self) -> int:
        """First chunk batch: the override, else the default adaptive start."""
        return self.batch_size if self.batch_size is not None else DEFAULT_BATCH_SIZE


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
        max_file_bytes=_read_positive_int(env, ENV_MAX_FILE_BYTES, DEFAULT_MAX_FILE_BYTES),
        batch_size=_read_optional_positive_int(env, ENV_BATCH_SIZE),
        max_workers=_read_optional_positive_int(env, ENV_MAX_WORKERS),
    )


def adaptive_workers(
    cpu_count: int | None = None, available_bytes: int | None = None
) -> int:
    """Derive the worker count from the CPU count and available memory (C8).

    cpu_count defaults to os.cpu_count(); available_bytes, when given, caps
    workers at one per WORKER_MEMORY_BYTES so a small machine is not overrun.
    """
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
    workers = max(1, min(cpus - 1, MAX_WORKERS))
    if available_bytes is not None:
        workers = min(workers, max(1, available_bytes // WORKER_MEMORY_BYTES))
    return workers


def next_batch_size(current: int, elapsed_seconds: float) -> int:
    """Return the next batch size from the last batch's duration (5.2)."""
    if elapsed_seconds > SLOW_BATCH_SECONDS:
        return max(MIN_BATCH_SIZE, current // 2)
    if elapsed_seconds < FAST_BATCH_SECONDS:
        return min(MAX_BATCH_SIZE, current * 2)
    return current


def _read_optional_positive_int(environ: Mapping[str, str], name: str) -> int | None:
    """Return the positive integer stored at environ[name], or None if unset."""
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer, got {value}")
    return value


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
