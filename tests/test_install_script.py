"""Tests for scripts/install.sh (T4-03).

The acceptance criterion is "idempotent, re-runnable without error", so the
tests run the real script twice in its offline mode (`CODERAG_SKIP_INSTALL=1`)
and assert the two runs are byte-identical. The remaining cases cover the
environment gates the task requires: a missing interpreter and a Python
version outside `requires-python`.

Nothing here touches the network or installs anything.
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

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required to run install.sh")


def install_env(**overrides: str) -> dict[str, str]:
    """Inherit the environment minus any CODERAG_* this shell happens to carry."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("CODERAG_")}
    env.update(overrides)
    return env


def run_install(**overrides: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, str(SCRIPT)],
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


def test_install_script_selfcheck_passes_without_installing() -> None:
    result = run_install(CODERAG_PYTHON=sys.executable, CODERAG_SKIP_INSTALL="1")

    assert result.returncode == 0, result.stderr
    assert "已跳过（CODERAG_SKIP_INSTALL=1）" in result.stdout
    assert "FTS5   ：可用 ✅" in result.stdout
    assert "往返   ：中文查询命中 ✅  标识符命中 ✅  无关词不命中 ✅" in result.stdout
    assert "完成：安装与自检通过 ✅" in result.stdout


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


def test_install_script_rejects_an_unsupported_python_version(tmp_path: Path) -> None:
    fake = tmp_path / "fake-python"
    fake.write_text(
        "#!/bin/sh\n"
        "# Reports 3.9.0 when asked to print its version; fails the range probe.\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        "    *'print('*) printf '3.9.0\\n'; exit 0 ;;\n"
        "    *version_info*) exit 1 ;;\n"
        "  esac\n"
        "done\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    result = run_install(CODERAG_PYTHON=str(fake), CODERAG_SKIP_INSTALL="1")

    assert result.returncode == 2
    assert "Python 版本不符" in result.stderr
    assert "3.9.0" in result.stderr
