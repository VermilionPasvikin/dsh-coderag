"""Tests for the dsh-coderag console entry point (including the M6 subcommands).

The `doctor` / `install-deps` subcommands took over the logic that used to live
in `scripts/install.sh` (T6-02), so the interpreter gates that script used to
own - a Python outside `requires-python`, a missing interpreter location, a
failing pip - are asserted here against the CLI instead.

`pip install` itself is never run: the install step goes through the
`run_pip(command, cwd)` seam and is replaced in these tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from dsh_coderag import __main__ as cli
from dsh_coderag import __version__

NO_DEPENDENCIES_PROGRAM = """
import sys

# A real interpreter without the engine's wheels: importing them raises.
sys.modules["tree_sitter"] = None
sys.modules["tree_sitter_language_pack"] = None

import dsh_coderag

print("version", dsh_coderag.__version__)
try:
    dsh_coderag.index_sync
except ImportError:
    print("lazy")
"""


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m dsh_coderag ...` in a fresh interpreter.

    Both directions are pinned to UTF-8: the CLI prints Chinese, and a Windows
    console default (cp936) cannot decode it — the assertions would fail on
    mojibake rather than on the behaviour under test.
    """
    return subprocess.run(
        [sys.executable, "-m", "dsh_coderag", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )


def error_payload(captured: pytest.CaptureFixture[str]) -> dict[str, str]:
    """Parse the single structured error object the CLI writes to stderr."""
    return json.loads(captured.readouterr().err.strip())


def test_module_invocation_reports_version() -> None:
    """python -m dsh_coderag must actually run main(), not import and exit."""
    result = run_module("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == f"dsh-coderag {__version__}"


def test_importing_the_package_needs_only_the_standard_library() -> None:
    """`doctor` has to run before the engine's wheels exist (T6-02)."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(NO_DEPENDENCIES_PROGRAM)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"version {__version__}" in result.stdout
    assert "lazy" in result.stdout, "index_sync must not be imported eagerly"


def test_doctor_reports_the_interpreter_and_a_copyable_assignment() -> None:
    """The printed assignment must be the one this OS's shell can actually run."""
    result = run_module("doctor")

    assert result.returncode == 0, result.stderr
    assert f"{cli.ENV_PYTHON}={sys.executable}" in result.stdout
    if sys.platform == "win32":
        assert f'$env:{cli.ENV_PYTHON} = "{sys.executable}"' in result.stdout
        assert f"export {cli.ENV_PYTHON}=" not in result.stdout
    else:
        assert f'export {cli.ENV_PYTHON}="{sys.executable}"' in result.stdout
        assert f"$env:{cli.ENV_PYTHON}" not in result.stdout


def test_index_explains_a_workspace_with_nothing_indexable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`indexed 0 files` alone cannot be told apart from a broken workspace."""
    for name in ("ship.MXML", "ui.MXML"):
        (tmp_path / name).write_text("<mx:Canvas/>", encoding="utf-8")

    code = cli.main(["index", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK, "a workspace that holds no code is not an error"
    assert "没有可索引的文件" in out
    assert "看到 2 个文件" in out
    assert "2 个的后缀不在白名单内" in out
    assert ".py" in out and ".js" in out, "the notice must name the whitelist"


def test_index_stays_quiet_when_there_is_something_to_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")

    assert cli.main(["index", str(tmp_path)]) == cli.EXIT_OK

    assert "没有可索引的文件" not in capsys.readouterr().out


def test_index_uses_the_extensions_the_user_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CODERAG_EXTRA_EXTENSIONS must reach the index run, not just the parser."""
    (tmp_path / "screen.MXML").write_text("<mx:Canvas/>", encoding="utf-8")
    monkeypatch.setenv("CODERAG_EXTRA_EXTENSIONS", ".mxml")

    code = cli.main(["index", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "indexed 1 files" in out, out
    assert "没有可索引的文件" not in out


def test_empty_index_notice_names_the_effective_whitelist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Telling a user their extension is unsupported right after adding it is worse than silence."""
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("CODERAG_EXTRA_EXTENSIONS", ".mxml")

    assert cli.main(["index", str(tmp_path)]) == cli.EXIT_OK

    out = capsys.readouterr().out
    assert ".mxml" in out, "the notice must list the effective extensions"
    assert "CODERAG_EXTRA_EXTENSIONS" not in out, "no point suggesting what is already set"


def test_doctor_prints_a_ready_to_paste_profile_override() -> None:
    """The override is the only thing that fixes a desktop app's spawn failure."""
    result = run_module("doctor")
    lines = result.stdout.splitlines()
    start = lines.index(f"- id: {cli.MCP_ROW_ID}")
    block = lines[start:]

    assert block == cli.profile_override_block(sys.executable)
    assert any(f"command: '{sys.executable}'" in line for line in block)
    assert any(line.strip().startswith("args:") for line in block), (
        "an id-targeted patch replaces the whole config, so args must be restated"
    )
    assert any("CODERAG_ROOT" in line for line in block)
    assert "追加" in result.stdout and "不要替换整个文件" in result.stdout


def test_index_rejects_a_workspace_that_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mistyped path used to be created and then reported as a successful run."""
    missing = tmp_path / "typo" / "not" / "here"

    code = cli.main(["index", str(missing)])

    payload = error_payload(capsys)
    assert code == cli.EXIT_FAILED
    assert payload["code"] == "WORKSPACE_NOT_FOUND"
    assert str(missing) in payload["message"]
    assert not missing.exists(), "indexing must not create the workspace"


def test_search_reports_a_non_ready_index_without_the_none_placeholder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty workspace has no message; the raw None reached the user's terminal."""
    assert cli.main(["index", str(tmp_path)]) == cli.EXIT_OK

    code = cli.main(["search", "anything", "--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == cli.EXIT_FAILED
    # stderr also carries the indexer's structured log lines; the status is last.
    last_line = captured.err.strip().splitlines()[-1]
    assert last_line.startswith("empty"), captured.err
    assert "None" not in last_line


def test_install_deps_without_a_checkout_points_at_an_editable_install(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The old hint said "run it inside this repository", which is what fails."""
    monkeypatch.setattr(cli, "pip_available", lambda: True)
    monkeypatch.setattr(cli, "source_root", lambda: None)

    code = cli.main(["install-deps"])

    assert code == cli.EXIT_ENV_UNUSABLE
    assert "pip install -e" in error_payload(capsys)["hint"]


@pytest.mark.parametrize("command", ["doctor", "install-deps"])
def test_new_subcommands_print_help_and_exit_zero(command: str) -> None:
    result = run_module(command, "--help")

    assert result.returncode == 0, result.stderr
    assert f"dsh-coderag {command}" in result.stdout


def test_install_deps_help_mentions_the_skip_switch() -> None:
    result = run_module("install-deps", "--help")

    assert result.returncode == 0, result.stderr
    assert "--skip-install" in result.stdout
    assert cli.ENV_SKIP_INSTALL in result.stdout


def test_requires_python_is_read_from_pyproject_not_hardcoded() -> None:
    """RL-07: the range must come from pyproject.toml, not from a literal here."""
    root = cli.source_root()

    assert root is not None, "these tests run from the repository checkout"
    declared = cli.read_project_scalars(root / cli.PYPROJECT)["requires-python"]

    assert cli.requires_python_spec() == declared


@pytest.mark.parametrize(
    ("version", "spec", "expected"),
    [
        ((3, 10, 21), ">=3.10,<3.13", True),
        ((3, 10, 0), ">=3.10", True),
        ((3, 12, 9), "<3.13", True),
        ((3, 9, 0), ">=3.10,<3.13", False),
        ((3, 13, 0), ">=3.10,<3.13", False),
        ((3, 13, 0), "<3.13", False),
        ((3, 10, 21), "==3.10.21", True),
        ((3, 10, 21), "==3.10", False),
        ((3, 11, 0), ">=3.10, <3.13", True),
    ],
)
def test_version_satisfies(
    version: tuple[int, ...], spec: str, expected: bool
) -> None:
    assert cli.version_satisfies(version, spec) is expected


def test_version_satisfies_rejects_an_unsupported_operator() -> None:
    """An operator we cannot evaluate must raise, never be silently dropped."""
    with pytest.raises(cli.CliError) as raised:
        cli.version_satisfies((3, 10, 21), "~=3.10")

    assert raised.value.code == "REQUIRES_PYTHON_UNSUPPORTED_SPEC"


def test_doctor_rejects_a_python_outside_the_required_range(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "requires_python_spec", lambda: ">=3.99")

    code = cli.main(["doctor"])

    assert code == cli.EXIT_ENV_UNUSABLE == 2
    payload = error_payload(capsys)
    assert payload["status"] == "error"
    assert payload["code"] == "PYTHON_VERSION_UNSUPPORTED"
    assert "3.99" in payload["message"]


def test_self_check_covers_fts5_and_every_round_trip() -> None:
    checks = cli.self_check()

    assert [check.name for check in checks] == [
        "FTS5",
        "bigram",
        "中文往返",
        "标识符往返",
        "无关词不命中",
    ]
    assert all(check.ok for check in checks), [check.detail for check in checks]


def test_install_deps_skips_pip_when_asked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CODERAG_SKIP_INSTALL=1 must reach the self-check without touching pip."""
    monkeypatch.delenv(cli.ENV_SKIP_INSTALL, raising=False)

    def explode(command: object, cwd: object) -> int:  # pragma: no cover - guard
        raise AssertionError("pip must not run when the install is skipped")

    monkeypatch.setattr(cli, "run_pip", explode)

    code = cli.main(["install-deps", "--skip-install"])

    assert code == cli.EXIT_OK == 0
    assert "完成：安装与自检通过" in capsys.readouterr().out


def test_pip_failure_is_reported_as_structured_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "pip_available", lambda: True)
    monkeypatch.setattr(cli, "install_target", lambda root: ["."])
    monkeypatch.setattr(cli, "run_pip", lambda command, cwd: 7)

    code = cli.main(["install-deps"])

    assert code == cli.EXIT_FAILED == 1
    payload = error_payload(capsys)
    assert payload["code"] == "PIP_INSTALL_FAILED"
    assert "7" in payload["message"]
    assert "hint" in payload


def test_install_without_a_checkout_is_reported_as_structured_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "pip_available", lambda: True)
    monkeypatch.setattr(cli, "source_root", lambda: None)

    code = cli.main(["install-deps"])

    assert code == cli.EXIT_ENV_UNUSABLE
    assert error_payload(capsys)["code"] == "SOURCE_CHECKOUT_NOT_FOUND"


def test_unexpected_errors_still_leave_the_cli_as_structured_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """RL-09's counterpart: a traceback must never be the CLI's failure mode."""
    monkeypatch.setattr(
        cli, "environment_checks", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    code = cli.main(["doctor"])

    assert code == cli.EXIT_FAILED
    payload = error_payload(capsys)
    assert payload["code"] == "CLI_UNEXPECTED_ERROR"
    assert "boom" in payload["message"]


def test_install_target_keeps_an_editable_checkout_editable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(cli.ENV_EDITABLE, raising=False)
    root = cli.source_root()
    assert root is not None
    monkeypatch.setattr(cli, "editable_location", lambda: str(root))

    assert cli.install_target(root) == ["-e", "."]
    capsys.readouterr()


@pytest.mark.parametrize(("setting", "expected"), [("1", ["-e", "."]), ("0", ["."])])
def test_install_target_honours_the_editable_override(
    monkeypatch: pytest.MonkeyPatch, setting: str, expected: list[str]
) -> None:
    monkeypatch.setenv(cli.ENV_EDITABLE, setting)

    assert cli.install_target(Path(".")) == expected


def test_install_target_rejects_a_malformed_editable_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cli.ENV_EDITABLE, "maybe")

    with pytest.raises(cli.CliError) as raised:
        cli.install_target(Path("."))

    assert raised.value.code == "CODERAG_EDITABLE_INVALID"


def test_pip_extra_args_are_split_on_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cli.ENV_PIP_ARGS, "--index-url https://example.invalid/simple")

    assert cli.pip_extra_args() == ["--index-url", "https://example.invalid/simple"]


def test_index_reports_the_file_limit_with_its_own_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An expected limit must not be dressed up as an unexpected failure (T6-22).

    The report that prompted this had the user guessing which variable to set and
    how to spell it, because the CLI replaced the walker's own code and count with
    CLI_UNEXPECTED_ERROR and a leaked class name.
    """
    for name in ("a.py", "b.py"):
        (tmp_path / name).write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("CODERAG_MAX_FILES", "1")

    code = cli.main(["index", str(tmp_path)])

    error = capsys.readouterr().err
    payload = json.loads(error.strip().splitlines()[-1])
    assert code == cli.EXIT_FAILED
    assert payload["code"] == "INDEX_TOO_MANY_FILES"
    # The structured log on stderr names the exception type on purpose (S-05
    # diagnostics); the user-facing object must not carry it (D-02).
    assert "TooManyFilesError" not in payload["message"]
    assert "2 indexable files" in payload["message"]
    assert "CODERAG_MAX_FILES" in payload["hint"]
    assert "'2'" in payload["hint"], "the hint must show a value that actually works"


def test_search_uses_the_token_budget_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI's search reads CODERAG_MAX_TOKENS, like the MCP path does (T6-22)."""
    for index in range(40):
        (tmp_path / f"f{index:02d}.py").write_text(
            f"def needletoken_{index}():\n    return needletoken\n", encoding="utf-8"
        )
    monkeypatch.delenv("CODERAG_MAX_TOKENS", raising=False)
    assert cli.main(["index", str(tmp_path)]) == cli.EXIT_OK
    capsys.readouterr()

    args = ["search", "needletoken", "--root", str(tmp_path), "--limit", "40"]
    assert cli.main(args) == cli.EXIT_OK
    full = capsys.readouterr().out.splitlines()

    monkeypatch.setenv("CODERAG_MAX_TOKENS", "20")
    assert cli.main(args) == cli.EXIT_OK
    trimmed = capsys.readouterr().out.splitlines()

    assert len(full) > 1, full
    assert 0 < len(trimmed) < len(full), (len(full), len(trimmed))
