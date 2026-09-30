"""Tests for the thin `scripts/install.sh` wrapper (T6-02).

After T6-02 that script no longer holds install logic: it locates an
interpreter and forwards to `dsh_coderag install-deps`. What is left to assert
is the wrapper's own contract - valid shell, bounded size, no dependency list
of its own, and argument pass-through. The interpreter gates the script used to
own (Python version range, FTS5, pip) are asserted against the CLI in
`tests/test_cli.py`, because that is where they live now.

These tests are skipped where no `bash` is on PATH; they are POSIX-shell
wrappers, and the Windows path is the Python CLI itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "install.sh"
BASH = shutil.which("bash")

MAX_WRAPPER_LINES = 40
"""T6-02's acceptance criterion: each wrapper is at most 40 lines."""

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required to run install.sh")


def install_env(**overrides: str) -> dict[str, str]:
    """Inherit the environment minus any CODERAG_* this shell happens to carry."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("CODERAG_")}
    env.update(overrides)
    return env


def run_install(*args: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=install_env(**overrides),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_install_script_is_syntactically_valid_bash() -> None:
    assert BASH is not None
    result = subprocess.run(
        [BASH, "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_install_script_is_a_thin_wrapper() -> None:
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()

    assert len(lines) <= MAX_WRAPPER_LINES, f"{len(lines)} lines exceeds {MAX_WRAPPER_LINES}"


def test_install_script_carries_no_dependency_list_of_its_own() -> None:
    """The dependency list must exist in pyproject.toml and nowhere else.

    The guard is on an actual pip invocation (`-m pip`) and on the dependency
    names, not on the words "pip install" in prose: the wrapper is allowed to
    explain that the install step moved to the CLI.
    """
    text = SCRIPT.read_text(encoding="utf-8")

    assert "-m pip" not in text
    for dependency in ("tree-sitter", "tree-sitter-language-pack", "pathspec", "mcp>="):
        assert dependency not in text, dependency
    assert "-m dsh_coderag install-deps" in text


def test_install_script_locates_the_interpreter_from_coderag_python() -> None:
    assert "CODERAG_PYTHON" in SCRIPT.read_text(encoding="utf-8")


def test_install_script_forwards_to_the_python_cli() -> None:
    result = run_install(CODERAG_PYTHON=sys.executable, CODERAG_SKIP_INSTALL="1")

    assert result.returncode == 0, result.stderr
    assert "== dsh-coderag install-deps" in result.stdout
    assert "完成：安装与自检通过" in result.stdout


def test_install_script_passes_arguments_through_to_the_cli() -> None:
    """`"$@"` must survive: the wrapper adds no options of its own."""
    result = run_install("--skip-install", CODERAG_PYTHON=sys.executable)

    assert result.returncode == 0, result.stderr
    assert "已跳过" in result.stdout


def test_install_script_is_idempotent() -> None:
    first = run_install(CODERAG_PYTHON=sys.executable, CODERAG_SKIP_INSTALL="1")
    second = run_install(CODERAG_PYTHON=sys.executable, CODERAG_SKIP_INSTALL="1")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout, "重复运行必须得到完全相同的结果（幂等）"


def test_install_script_rejects_a_missing_interpreter(tmp_path: Path) -> None:
    missing = tmp_path / "not-a-python"

    result = run_install(CODERAG_PYTHON=str(missing), CODERAG_SKIP_INSTALL="1")

    assert result.returncode == 2
    assert "解释器不可执行或不存在" in result.stderr
