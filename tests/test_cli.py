"""Tests for the dsh-coderag console entry point."""

from __future__ import annotations

import subprocess
import sys

from dsh_coderag import __version__


def test_module_invocation_reports_version() -> None:
    """python -m dsh_coderag must actually run main(), not import and exit."""
    result = subprocess.run(
        [sys.executable, "-m", "dsh_coderag", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"dsh-coderag {__version__}"
