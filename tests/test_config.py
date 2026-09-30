"""Tests for dsh_coderag.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.config import ConfigError, load_config, load_config_for, load_semantic_config


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


def test_a_missing_root_uses_the_process_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T6-26: DSH carries the session workspace as the child's working directory.

    Measured on this machine: the host gives its children the folder the
    conversation is on, while a patch expression would only see the host's own
    directory - which is DSH's profile folder (T6-25).
    """
    monkeypatch.chdir(tmp_path)

    config = load_config({"DSH_HOME": str(tmp_path / "elsewhere")})

    assert config.root == tmp_path


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_root_counts_as_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Empty counts as unset here, exactly as it does for every other variable."""
    monkeypatch.chdir(tmp_path)

    config = load_config({"CODERAG_ROOT": value, "DSH_HOME": str(tmp_path / "elsewhere")})

    assert config.root == tmp_path


def test_the_fallback_is_refused_inside_dsh_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The desktop app's inherited directory is DSH's own state, not a workspace.

    With no root set, refusing here is what keeps the fallback from silently
    indexing DSH's own files - the failure this experiment must not reintroduce.
    The message says the value came from the engine's own directory, which is the
    measurement the experiment is after.
    """
    home = tmp_path / ".dsh"
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True)
    monkeypatch.chdir(profile)

    with pytest.raises(ConfigError, match="is unset, so the engine used its own"):
        load_config({"DSH_HOME": str(home)})


def test_an_explicit_root_inside_dsh_home_says_it_was_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A value from the patch is the HOST's directory, not the engine's - say so.

    Measured 2026-09-30: the profile patch still carried
    `process.env.CODERAG_ROOT ?? process.cwd()`, so the first live reading could
    not tell the two sources apart.
    """
    home = tmp_path / ".dsh"
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError, match="is set to"):
        load_config({"CODERAG_ROOT": str(profile), "DSH_HOME": str(home)})


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


def test_extra_extensions_are_normalised(tmp_path: Path) -> None:
    """Users type `.MXML`, `mxml` and ` .mxml ` for the same thing (T6-17)."""
    config = load_config(
        {"CODERAG_ROOT": str(tmp_path), "CODERAG_EXTRA_EXTENSIONS": " .MXML, as ,mxml"}
    )
    assert config.extra_extensions == frozenset({".mxml", ".as"})


@pytest.mark.parametrize("raw", ["", "   ", ",", ", ,"])
def test_blank_extra_extensions_mean_none(tmp_path: Path, raw: str) -> None:
    """The patch ships an empty default, so empty must not be an error."""
    config = load_config({"CODERAG_ROOT": str(tmp_path), "CODERAG_EXTRA_EXTENSIONS": raw})
    assert config.extra_extensions == frozenset()


@pytest.mark.parametrize("raw", ["a.b", ".d.ts", "..\\evil", "sub/dir", "*", "-"])
def test_extra_extensions_reject_entries_that_could_never_match(
    tmp_path: Path, raw: str
) -> None:
    """A dotted token or a glob would silently match nothing (`Path.suffix`)."""
    with pytest.raises(ConfigError, match="CODERAG_EXTRA_EXTENSIONS"):
        load_config({"CODERAG_ROOT": str(tmp_path), "CODERAG_EXTRA_EXTENSIONS": raw})


def test_load_config_for_supplies_the_root_the_caller_already_has(tmp_path: Path) -> None:
    """The CLI and `build_server(root=...)` know the root but still need config."""
    config = load_config_for(tmp_path, {"CODERAG_EXTRA_EXTENSIONS": ".mxml"})
    assert config.root == tmp_path
    assert config.extra_extensions == frozenset({".mxml"})


def test_load_config_for_lets_an_explicit_root_win(tmp_path: Path) -> None:
    other = tmp_path / "other"
    config = load_config_for(tmp_path, {"CODERAG_ROOT": str(other)})
    assert config.root == other


def test_a_root_inside_dsh_home_is_refused(tmp_path: Path) -> None:
    """T6-25: the desktop app inherits its profile directory as the root.

    That directory is DSH's own state, never the user's workspace, and indexing it
    used to succeed silently.
    """
    dsh_home = tmp_path / ".dsh"
    profile = dsh_home / "profiles" / "desktop"
    profile.mkdir(parents=True)

    with pytest.raises(ConfigError, match="DSH"):
        load_config({"CODERAG_ROOT": str(profile), "DSH_HOME": str(dsh_home)})


def test_the_dsh_home_itself_is_refused(tmp_path: Path) -> None:
    dsh_home = tmp_path / ".dsh"
    dsh_home.mkdir()

    with pytest.raises(ConfigError, match="DSH"):
        load_config({"CODERAG_ROOT": str(dsh_home), "DSH_HOME": str(dsh_home)})


def test_a_workspace_beside_dsh_home_is_accepted(tmp_path: Path) -> None:
    dsh_home = tmp_path / ".dsh"
    dsh_home.mkdir()
    workspace = tmp_path / "repo"
    workspace.mkdir()

    config = load_config({"CODERAG_ROOT": str(workspace), "DSH_HOME": str(dsh_home)})

    assert config.root == workspace
