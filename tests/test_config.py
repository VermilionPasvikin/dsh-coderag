"""Tests for dsh_coderag.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.config import ConfigError, load_config, load_semantic_config


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


def test_semantic_defaults_keep_the_backend_off() -> None:
    config = load_semantic_config({})
    assert config.enabled is False
    assert config.backend == "ollama"
    assert config.url == "http://127.0.0.1:11434"
    assert config.model == "bge-m3"
    assert config.timeout_s == 30
    assert config.batch == 16
    assert config.max_chunks == 100000
    assert config.api_key is None
    assert config.allow_remote is False
    assert config.switch_invalid is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "ON"])
def test_only_the_exact_word_on_enables_the_backend(value: str) -> None:
    config = load_semantic_config({"CODERAG_SEMANTIC": value})
    assert config.enabled is False
    assert config.switch_value == value
    assert config.switch_invalid is True


def test_enabling_the_backend_requires_the_exact_word_on() -> None:
    assert load_semantic_config({"CODERAG_SEMANTIC": "on"}).enabled is True


def test_blank_values_count_as_unset_so_defaults_survive() -> None:
    config = load_semantic_config(
        {
            "CODERAG_SEMANTIC": "on",
            "CODERAG_SEMANTIC_MODEL": "   ",
            "CODERAG_SEMANTIC_TIMEOUT": "",
            "CODERAG_SEMANTIC_BATCH": "",
        }
    )
    assert config.model == "bge-m3"
    assert config.timeout_s == 30
    assert config.batch == 16
    assert config.enabled is True


def test_semantic_numeric_overrides_are_read() -> None:
    config = load_semantic_config(
        {
            "CODERAG_SEMANTIC_TIMEOUT": "5",
            "CODERAG_SEMANTIC_BATCH": "4",
            "CODERAG_SEMANTIC_MAX_CHUNKS": "77",
        }
    )
    assert (config.timeout_s, config.batch, config.max_chunks) == (5, 4, 77)


def test_malformed_semantic_number_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="CODERAG_SEMANTIC_BATCH"):
        load_semantic_config({"CODERAG_SEMANTIC_BATCH": "lots"})


def test_allow_remote_needs_the_exact_value_one() -> None:
    assert load_semantic_config({"CODERAG_SEMANTIC_ALLOW_REMOTE": "1"}).allow_remote
    for value in ("true", "yes", "0", ""):
        assert not load_semantic_config(
            {"CODERAG_SEMANTIC_ALLOW_REMOTE": value}
        ).allow_remote


def test_cloud_backend_requires_explicit_url_and_model() -> None:
    base = {"CODERAG_SEMANTIC": "on", "CODERAG_SEMANTIC_BACKEND": "openai"}
    with pytest.raises(ConfigError, match="CODERAG_SEMANTIC_URL"):
        load_semantic_config(base)
    with pytest.raises(ConfigError, match="CODERAG_SEMANTIC_MODEL"):
        load_semantic_config({**base, "CODERAG_SEMANTIC_URL": "https://api.example/v1"})
    resolved = load_semantic_config(
        {
            **base,
            "CODERAG_SEMANTIC_URL": "https://api.example/v1",
            "CODERAG_SEMANTIC_MODEL": "text-embedding-3-small",
            "CODERAG_SEMANTIC_ALLOW_REMOTE": "1",
        }
    )
    assert resolved.backend == "openai"
    assert resolved.url == "https://api.example/v1"
    assert resolved.model == "text-embedding-3-small"
    assert resolved.allow_remote is True


def test_cloud_backend_stays_unvalidated_while_disabled() -> None:
    config = load_semantic_config({"CODERAG_SEMANTIC_BACKEND": "openai"})
    assert config.enabled is False
    assert config.url == "http://127.0.0.1:11434"
