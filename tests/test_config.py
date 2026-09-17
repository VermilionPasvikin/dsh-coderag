"""Tests for dsh_coderag.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.config import ConfigError, load_config


def test_load_config_reads_root_and_numeric_overrides(tmp_path: Path) -> None:
    config = load_config(
        {
            "CODERAG_ROOT": str(tmp_path),
            "CODERAG_MAX_FILES": "123",
            "CODERAG_MAX_TOKENS": "456",
        }
    )
    assert config.root == tmp_path
    assert config.max_files == 123
    assert config.max_tokens == 456


def test_load_config_raises_when_required_root_is_missing() -> None:
    with pytest.raises(ConfigError, match="CODERAG_ROOT"):
        load_config({"CODERAG_MAX_FILES": "123"})


def test_load_config_raises_when_numeric_value_is_not_an_integer() -> None:
    with pytest.raises(ConfigError, match="CODERAG_MAX_FILES"):
        load_config({"CODERAG_ROOT": "/workspace", "CODERAG_MAX_FILES": "many"})
