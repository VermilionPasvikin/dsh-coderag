"""Line-ending guarantee for the shell scripts (T6-11).

`scripts/dsh`, `scripts/install.sh` and `scripts/eval-gate.sh` are executed by
sh/bash, where a CRLF shebang line does not resolve. `.gitattributes` pins them
to LF, so the guarantee belongs to the repository rather than to whoever wrote
the file last: a checkout with `core.autocrlf=true` (the Git for Windows
default) would otherwise materialise CRLF.

The working-tree bytes are the property a user actually hits, so that is what
this test asserts. Note the limit of the check: on a POSIX checkout the files
are LF whether or not the pin exists, so `git check-attr eol` (run in T6-11's
acceptance) is what proves the pin itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_SCRIPTS = ("scripts/dsh", "scripts/install.sh", "scripts/eval-gate.sh")


@pytest.mark.parametrize("relative", SHELL_SCRIPTS)
def test_shell_script_is_checked_out_with_lf(relative: str) -> None:
    raw = (REPO_ROOT / relative).read_bytes()
    assert raw, f"{relative} is empty"
    assert b"\r" not in raw, (
        f"{relative} contains a carriage return; it must be checked out with LF "
        f"(the rule lives in .gitattributes)"
    )
    first_line = raw.split(b"\n", 1)[0]
    assert raw.startswith(b"#!") and first_line.endswith(b"sh"), (
        f"{relative} should begin with a sh shebang"
    )
