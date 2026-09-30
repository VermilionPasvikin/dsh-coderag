"""Tests for the distributed bundle patch `cordis.patch.yml`.

The patch decides which interpreter DSH spawns for the MCP row, and that
decision is invisible at runtime: a `command` that cannot be spawned still
loads the plugin, so the only symptom is "the coderag tools are missing". A
machine-specific default therefore shipped for months without anyone noticing
(T6-15), which is what these assertions exist to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

from dsh_coderag import __main__ as cli

REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH = (REPO_ROOT / "cordis.patch.yml").read_text(encoding="utf-8")


def test_patch_bakes_in_no_absolute_interpreter_path() -> None:
    """A default naming one machine's interpreter breaks every other machine."""
    assert "/opt/anaconda3" not in PATCH
    assert "F:\\\\conda" not in PATCH
    assert not re.search(r"command:.*\.exe'", PATCH), "command must not pin an .exe"


def test_patch_command_defaults_to_a_portable_path_name() -> None:
    """`python` / `python3` respect an activated environment and name Python on failure."""
    command = next(line for line in PATCH.splitlines() if line.strip().startswith("command:"))
    assert "process.env.CODERAG_PYTHON" in command, "the override must come first"
    assert "process.platform" in command, "the fallback must be chosen per platform"
    assert "'python'" in command and "'python3'" in command


def test_patch_command_scalar_cannot_break_yaml() -> None:
    """A plain YAML scalar stops at ": ", which made DSH reject the whole bundle.

    The expression needs a ternary, and `? 'a' : 'b'` inside an unquoted scalar
    parses as a nested mapping — DSH then refuses to load the plugin at all
    ("failed to parse overlay"). Quoting the scalar is the fix, and a quoted
    scalar may contain ": " safely; this asserts it stays quoted.
    """
    line = next(line for line in PATCH.splitlines() if line.strip().startswith("command:"))
    expression = line.split("!!js", 1)[1].strip()
    assert ": " in expression, "this guard only matters while a ternary is here"
    assert expression.startswith('"') and expression.endswith('"'), (
        "unquoted ': ' would break YAML parsing and DSH would reject the bundle"
    )


def test_patch_env_does_not_repeat_coderag_python() -> None:
    """Only `command` picks the executable; the engine never reads this variable."""
    env_block = PATCH.split("env:", 1)[1]
    assert not re.search(r"^\s+CODERAG_PYTHON:", env_block, re.M), (
        "a copy in env made a broken command look correct"
    )


def test_doctor_block_names_the_same_row_as_the_patch() -> None:
    """doctor prints a ready-to-paste override, so its identifiers must match."""
    assert f"id: {cli.MCP_ROW_ID}" in PATCH
    assert cli.MCP_CLIENT_PACKAGE in PATCH


def _without_comments(text: str) -> str:
    """The effective YAML: a full-line comment carries no behaviour."""
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


def test_neither_the_patch_nor_doctor_guesses_the_workspace() -> None:
    """`process.cwd()` there is the HOST's directory, not the user's workspace.

    Measured 2026-09-30: for a desktop app started from a shortcut that value is
    $DSH_HOME/profiles/<profile>, so a root resolved this way indexes DSH's own
    state and reports itself ready while the user's 10.67 GiB index sits
    elsewhere, invisible (T6-25).
    """
    block = "\n".join(cli.profile_override_block("python"))
    effective = _without_comments(PATCH)

    assert "process.cwd()" not in effective
    assert "process.cwd()" not in block
    assert not re.search(r"^\s+CODERAG_ROOT:", effective, re.M), (
        "the shipped bundle must set no root at all rather than guess one"
    )
    assert f"{cli.ENV_ROOT}: " in block, "doctor must show where the root goes"
