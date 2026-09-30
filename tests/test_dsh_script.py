"""Tests for the thin `scripts/dsh` wrapper (T6-02).

The wrapper does two things: export the interpreter the MCP child must use
(E-06), and forward to the pinned dsh launcher (E-07). Both are asserted here
without touching the network - a recording fake `dsh` earlier on PATH captures
what the wrapper handed it, so the `npx` fallback is never reached.

Skipped where no `bash` is on PATH; this is a POSIX-shell wrapper.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dsh"
BASH = shutil.which("bash")

MAX_WRAPPER_LINES = 40
"""T6-02's acceptance criterion: each wrapper is at most 40 lines."""

FAKE_DSH = '#!/bin/sh\necho "fake-dsh CODERAG_PYTHON=${CODERAG_PYTHON:-unset} args=$*"\n'

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required to run scripts/dsh")


def make_bin(tmp_path: Path, *, with_broken_python: bool = False) -> Path:
    """Build a PATH directory holding the recording `dsh` (and optional broken pythons)."""
    directory = tmp_path / "bin"
    directory.mkdir()
    dsh = directory / "dsh"
    dsh.write_text(FAKE_DSH, encoding="utf-8")
    dsh.chmod(0o755)
    if with_broken_python:
        for name in ("python3", "python"):
            stub = directory / name
            stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            stub.chmod(0o755)
    return directory


def run_dsh(
    directory: Path, *args: str, restrict_path: bool = False, **overrides: str
) -> subprocess.CompletedProcess[str]:
    """Run scripts/dsh with the fake bin directory ahead of PATH."""
    assert BASH is not None
    env = {key: value for key, value in os.environ.items() if not key.startswith("CODERAG_")}
    inherited = [] if restrict_path else env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join([str(directory), *inherited])
    env.update(overrides)
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_dsh_script_is_syntactically_valid_bash() -> None:
    assert BASH is not None
    result = subprocess.run(
        [BASH, "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_dsh_script_is_a_thin_wrapper() -> None:
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()

    assert len(lines) <= MAX_WRAPPER_LINES, f"{len(lines)} lines exceeds {MAX_WRAPPER_LINES}"


def test_dsh_script_forwards_arguments_and_the_interpreter(tmp_path: Path) -> None:
    result = run_dsh(make_bin(tmp_path), "alpha", "beta", CODERAG_PYTHON=sys.executable)

    assert result.returncode == 0, result.stderr
    assert f"CODERAG_PYTHON={sys.executable}" in result.stdout
    assert "args=alpha beta" in result.stdout


def test_dsh_script_keeps_an_interpreter_the_caller_already_set(tmp_path: Path) -> None:
    preset = str(tmp_path / "preset-python")

    result = run_dsh(make_bin(tmp_path), CODERAG_PYTHON=preset)

    assert f"CODERAG_PYTHON={preset}" in result.stdout


def test_dsh_script_does_not_export_an_unusable_interpreter(tmp_path: Path) -> None:
    """A PATH-only `python3` that cannot run must not become CODERAG_PYTHON.

    Windows ships a Microsoft Store placeholder under exactly that name, and
    exporting it would hand the MCP child an interpreter that cannot import
    the engine (see docs/m6-crossplatform-baseline.md).
    """
    directory = make_bin(tmp_path, with_broken_python=True)

    result = run_dsh(directory, restrict_path=True)

    assert result.returncode == 0, result.stderr
    assert "CODERAG_PYTHON=unset" in result.stdout
