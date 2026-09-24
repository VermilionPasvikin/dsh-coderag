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

# Optional embedding backend (ADR-16 4, ADR-17 4). Every name below is frozen:
# the bundle patch ships them as empty strings, so "unset" and "blank" must be
# the same thing and the documented default must survive.
ENV_SEMANTIC = "CODERAG_SEMANTIC"
ENV_SEMANTIC_BACKEND = "CODERAG_SEMANTIC_BACKEND"
ENV_SEMANTIC_URL = "CODERAG_SEMANTIC_URL"
ENV_SEMANTIC_MODEL = "CODERAG_SEMANTIC_MODEL"
ENV_SEMANTIC_TIMEOUT = "CODERAG_SEMANTIC_TIMEOUT"
ENV_SEMANTIC_BATCH = "CODERAG_SEMANTIC_BATCH"
ENV_SEMANTIC_MAX_CHUNKS = "CODERAG_SEMANTIC_MAX_CHUNKS"
ENV_SEMANTIC_API_KEY = "CODERAG_SEMANTIC_API_KEY"
ENV_SEMANTIC_ALLOW_REMOTE = "CODERAG_SEMANTIC_ALLOW_REMOTE"

SEMANTIC_ENABLED_VALUE = "on"
SEMANTIC_ALLOW_REMOTE_VALUE = "1"
SEMANTIC_BACKEND_OLLAMA = "ollama"
SEMANTIC_BACKEND_OPENAI = "openai"

DEFAULT_SEMANTIC_BACKEND = SEMANTIC_BACKEND_OLLAMA
DEFAULT_SEMANTIC_URL = "http://127.0.0.1:11434"
DEFAULT_SEMANTIC_MODEL = "bge-m3"
DEFAULT_SEMANTIC_TIMEOUT = 30
DEFAULT_SEMANTIC_BATCH = 16
DEFAULT_SEMANTIC_MAX_CHUNKS = 100000


class ConfigError(Exception):
    """Raised when a required setting is missing or a value is malformed."""


@dataclass(frozen=True)
class SemanticConfig:
    """Settings for the optional embedding backend (ADR-16 4 / ADR-17 4).

    Off by default: `enabled` is True only when CODERAG_SEMANTIC is exactly
    `on`. Any other value keeps the backend off and is preserved in
    `switch_value` so the structured status can name the invalid value instead
    of guessing (ADR-16 4). Required settings that are missing raise
    ConfigError rather than falling back to a guessed value.

    SECURITY WARNING - enabling the cloud (`openai`) backend sends part of
    your source text off this machine:

    * What leaves: the text of already-indexed chunks, **including each chunk's
      context prefix line** (`// file: <workspace-relative path> | symbol: ...`),
      so file paths and symbol names are sent as well.
    * What does not: files stopped by the three-layer filter (`.env`, `*.pem`,
      `id_rsa*`, ...) never become chunks, so they can never be sent.
    * Cost: cloud embedding is billed per token, and the first index embeds
      every chunk, so the first run is the full spend.
    * Compliance: the code may be company property or third-party licensed.
      Confirm you are allowed to send it to that provider.
    * API key: read from the environment only. Never write it into the
      repository, a config literal, logs, structured status or error text.
    * Transport: a non-loopback URL additionally requires
      `CODERAG_SEMANTIC_ALLOW_REMOTE=1`; use `https://`.
    """

    enabled: bool
    backend: str = DEFAULT_SEMANTIC_BACKEND
    url: str = DEFAULT_SEMANTIC_URL
    model: str = DEFAULT_SEMANTIC_MODEL
    timeout_s: int = DEFAULT_SEMANTIC_TIMEOUT
    batch: int = DEFAULT_SEMANTIC_BATCH
    max_chunks: int = DEFAULT_SEMANTIC_MAX_CHUNKS
    api_key: str | None = None
    allow_remote: bool = False
    switch_value: str | None = None

    @property
    def switch_invalid(self) -> bool:
        """Whether CODERAG_SEMANTIC was set to something other than `on`."""
        return self.switch_value is not None and not self.enabled


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


def load_semantic_config(environ: Mapping[str, str] | None = None) -> SemanticConfig:
    """Build a SemanticConfig from environment variables (ADR-16/17 4).

    Empty and whitespace-only values count as unset so the documented default
    keeps working. Never use `os.environ.get(name, default)` here: that would
    let the patch's `MODEL=""` erase the `bge-m3` default.

    Args:
        environ: Mapping to read. Defaults to os.environ; tests pass a
            controlled mapping instead of mutating the process environment.

    Raises:
        ConfigError: If a numeric setting is malformed, or if the cloud backend
            is explicitly enabled without its required URL or model. Nothing is
            validated while the backend is off, so a default install can never
            be blocked by this function.
    """
    env = os.environ if environ is None else environ
    switch_value = _read_optional_str(env, ENV_SEMANTIC)
    enabled = switch_value == SEMANTIC_ENABLED_VALUE
    backend = _read_optional_str(env, ENV_SEMANTIC_BACKEND) or DEFAULT_SEMANTIC_BACKEND
    url = _read_optional_str(env, ENV_SEMANTIC_URL)
    model = _read_optional_str(env, ENV_SEMANTIC_MODEL)
    if enabled and backend == SEMANTIC_BACKEND_OPENAI:
        _require_explicit(url, ENV_SEMANTIC_URL, backend)
        _require_explicit(model, ENV_SEMANTIC_MODEL, backend)
    return SemanticConfig(
        enabled=enabled,
        backend=backend,
        url=url if url is not None else DEFAULT_SEMANTIC_URL,
        model=model if model is not None else DEFAULT_SEMANTIC_MODEL,
        timeout_s=_read_positive_int(env, ENV_SEMANTIC_TIMEOUT, DEFAULT_SEMANTIC_TIMEOUT),
        batch=_read_positive_int(env, ENV_SEMANTIC_BATCH, DEFAULT_SEMANTIC_BATCH),
        max_chunks=_read_positive_int(
            env, ENV_SEMANTIC_MAX_CHUNKS, DEFAULT_SEMANTIC_MAX_CHUNKS
        ),
        api_key=_read_optional_str(env, ENV_SEMANTIC_API_KEY),
        allow_remote=_read_optional_str(env, ENV_SEMANTIC_ALLOW_REMOTE)
        == SEMANTIC_ALLOW_REMOTE_VALUE,
        switch_value=switch_value,
    )


def _require_explicit(value: str | None, name: str, backend: str) -> None:
    """Raise ConfigError when the enabled cloud backend lacks a required value."""
    if value is None:
        raise ConfigError(
            f"{name} is required when {ENV_SEMANTIC_BACKEND}={backend!r}: the cloud backend "
            "has no default endpoint or model, so it can never be reached by accident"
        )


def _read_optional_str(environ: Mapping[str, str], name: str) -> str | None:
    """Return the stripped value at environ[name], or None when unset or blank."""
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip()
