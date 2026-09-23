"""Regression: workspace modules must not shadow the engine's own imports.

The harness launches the engine with the working directory set to the workspace
being indexed, and both `python -m` and `python -c` put that directory first on
`sys.path`. A workspace file named after a stdlib module therefore used to abort
the server before it could serve anything.

`-m` cannot be rescued from inside the package: it imports `runpy` before any of
our code runs, so a workspace `types.py` kills the interpreter during startup.
The shipped launcher therefore uses `-c`, and `dsh_coderag/__init__.py` drops the
working directory from `sys.path` before its first shadowable import. These
tests spawn the real interpreter, so they cover that launcher path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dsh_coderag import __version__

SHADOWING_MODULES = ("token.py", "types.py", "parser.py", "logging.py", "config.py")
"""Stdlib names a workspace can plausibly contain at its root."""

LAUNCHER_PROGRAM = "import dsh_coderag.server as s; s.run()"
"""Must stay identical to the `args` of `mcp-coderag` in cordis.patch.yml."""

PATCH_FILE = Path(__file__).resolve().parents[1] / "cordis.patch.yml"

TIMEOUT_S = 20
"""Below the pytest per-test timeout so a hang fails with a clear message."""


def _shadowing_workspace(tmp_path: Path) -> Path:
    """Create a workspace whose root shadows several stdlib modules."""
    for name in SHADOWING_MODULES:
        (tmp_path / name).write_text("VALUE_FROM_WORKSPACE = 1\n", encoding="utf-8")
    return tmp_path


def test_patch_launcher_and_test_agree() -> None:
    """The shipped patch must use the `-c` launcher this file exercises."""
    assert LAUNCHER_PROGRAM in PATCH_FILE.read_text(encoding="utf-8")


def test_import_survives_workspace_modules_shadowing_stdlib(tmp_path: Path) -> None:
    workspace = _shadowing_workspace(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-c", "import dsh_coderag; print(dsh_coderag.__version__)"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    # Compare against the installed version, not a literal: this test is about
    # the import surviving, and a hardcoded string breaks on every version bump.
    assert completed.stdout.strip() == __version__


def test_launcher_serves_mcp_with_shadowing_modules_in_cwd(tmp_path: Path) -> None:
    """The exact argv from cordis.patch.yml must complete an MCP handshake."""
    workspace = _shadowing_workspace(tmp_path)
    process = subprocess.Popen(
        [sys.executable, "-c", LAUNCHER_PROGRAM],
        cwd=workspace,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None
        assert process.stdout is not None
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "regression", "version": "0"},
            },
        }
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            # The server is already gone, so stderr is at EOF and safe to drain.
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise AssertionError(f"服务器没有响应；stderr={stderr!r}")
        assert json.loads(line)["result"]["serverInfo"]["name"] == "coderag"
    finally:
        process.kill()
        process.wait(timeout=TIMEOUT_S)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
