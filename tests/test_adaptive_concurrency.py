"""Tests for adaptive concurrency and batch sizing (PROJECT.md 5.2)."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.config import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    IndexConfig,
    adaptive_workers,
    load_config,
    next_batch_size,
)
from dsh_coderag.indexer import index_sync


def test_adaptive_concurrency_derives_workers_from_cpu_count() -> None:
    assert adaptive_workers(cpu_count=16) == 8
    assert adaptive_workers(cpu_count=4) == 3
    assert adaptive_workers(cpu_count=1) == 1


def test_adaptive_concurrency_caps_workers_by_available_memory() -> None:
    assert adaptive_workers(cpu_count=16, available_bytes=128 * 1024 * 1024) == 2
    assert adaptive_workers(cpu_count=16, available_bytes=1) == 1


def test_adaptive_concurrency_halves_the_batch_when_a_batch_is_slow() -> None:
    assert next_batch_size(64, 3.0) == 32
    assert next_batch_size(1, 3.0) == 1


def test_adaptive_concurrency_doubles_the_batch_when_a_batch_is_fast() -> None:
    assert next_batch_size(64, 0.1) == 128
    assert next_batch_size(MAX_BATCH_SIZE, 0.1) == MAX_BATCH_SIZE


def test_adaptive_concurrency_keeps_the_batch_in_the_middle() -> None:
    assert next_batch_size(64, 1.0) == 64


def test_adaptive_concurrency_uses_the_config_override(tmp_path: Path) -> None:
    config = IndexConfig(root=tmp_path, batch_size=7, max_workers=2)
    assert config.start_batch_size == 7
    assert config.workers == 2


def test_adaptive_concurrency_derives_when_config_does_not_override(tmp_path: Path) -> None:
    config = IndexConfig(root=tmp_path)
    assert config.start_batch_size == DEFAULT_BATCH_SIZE
    assert config.workers == adaptive_workers()


def test_adaptive_concurrency_reads_optional_environment_overrides(tmp_path: Path) -> None:
    config = load_config(
        {
            "CODERAG_ROOT": str(tmp_path),
            "CODERAG_BATCH_SIZE": "16",
            "CODERAG_MAX_WORKERS": "3",
        }
    )
    assert config.start_batch_size == 16
    assert config.workers == 3


def test_adaptive_concurrency_indexes_with_an_overridden_config(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    summary = index_sync(tmp_path, IndexConfig(root=tmp_path, batch_size=1, max_workers=1))
    assert summary.files == 1
    assert summary.chunks == 1
