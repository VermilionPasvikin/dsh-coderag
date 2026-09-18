"""Tests for the three-layer secret filtering (PROJECT.md 5.5, M1 gate)."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.indexer import index_sync, open_index
from dsh_coderag.sanitize import scan_secret
from dsh_coderag.walker import walk


def _indexed_paths(repo: Path) -> set[str]:
    """Return the workspace-relative paths that have at least one chunk."""
    connection = open_index(repo / ".coderag" / "index.sqlite3")
    try:
        rows = connection.execute(
            "SELECT DISTINCT f.path FROM chunks c JOIN files f ON f.id = c.file_id"
        )
        return {row[0] for row in rows}
    finally:
        connection.close()


def test_secret_files_never_enter_the_index(secrets_repo: Path) -> None:
    index_sync(secrets_repo)
    paths = _indexed_paths(secrets_repo)
    assert not any(path.endswith(".env") for path in paths)
    assert not any("id_rsa" in path for path in paths)
    assert not any("credentials" in path for path in paths)
    assert "config.py" not in paths
    assert not any(path.startswith(".gnupg/") for path in paths)


def test_normal_files_still_enter_the_index(secrets_repo: Path) -> None:
    index_sync(secrets_repo)
    paths = _indexed_paths(secrets_repo)
    assert "normal.py" in paths
    assert "env_reader.py" in paths


def test_project_ignore_rules_keep_ignored_directories_out(secrets_repo: Path) -> None:
    index_sync(secrets_repo)
    paths = _indexed_paths(secrets_repo)
    assert not any(path.startswith("ignored_dir/") for path in paths)


def test_gitignore_is_honoured(tmp_path: Path) -> None:
    (tmp_path / "kept.py").write_text("VALUE = 1\n", encoding="utf-8")
    ignored = tmp_path / "gitignored"
    ignored.mkdir()
    (ignored / "hidden.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("gitignored/\n", encoding="utf-8")
    index_sync(tmp_path)
    paths = _indexed_paths(tmp_path)
    assert "kept.py" in paths
    assert not any(path.startswith("gitignored/") for path in paths)


def test_content_level_scan_redacts_an_inline_secret(tmp_path: Path) -> None:
    (tmp_path / "leak.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    index_sync(tmp_path)
    assert _indexed_paths(tmp_path) == set()


def test_walker_blocks_secret_names_with_code_extensions(secrets_repo: Path) -> None:
    names = {path.name for path, _, _ in walk(secrets_repo)}
    assert "credentials.py" not in names
    assert "config.py" in names
    assert "normal.py" in names


def test_walker_blocks_secret_path_fragments(secrets_repo: Path) -> None:
    relatives = {path.relative_to(secrets_repo).as_posix() for path, _, _ in walk(secrets_repo)}
    assert ".gnupg/settings.py" not in relatives


def test_scan_secret_reports_the_pattern_name() -> None:
    assert scan_secret('KEY = "AKIAIOSFODNN7EXAMPLE"') == "aws_access_key"
    assert scan_secret("-----BEGIN OPENSSH PRIVATE KEY-----") == "private_key"
    assert scan_secret("token = ghp_" + "a" * 36) == "github_token"
    assert scan_secret("key = sk-" + "a" * 30) == "openai_key"
    assert scan_secret("value = xoxb-" + "1" * 20) == "slack_token"
    assert scan_secret("def normal():\n    return 1\n") is None
