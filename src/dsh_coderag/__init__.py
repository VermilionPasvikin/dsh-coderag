"""dsh_coderag: codebase retrieval engine exposed over MCP.

This package owns the retrieval engine only. It does not own the MCP
transport lifecycle, does not choose an embedding provider, and never
modifies the DeepSeek Harness host.

Importing the package costs only the standard library. `index_sync` and
`search` pull in third-party wheels (tree-sitter), and the M6 entry point has
to run on a machine where those are not installed yet - `python -m
dsh_coderag doctor` and `install-deps` exist precisely to get that machine
ready (PROJECT.md 6.5.1, T6-02). They are therefore resolved on first use
through the module `__getattr__` below (PEP 562).
"""

from __future__ import annotations

import os
import sys


def _drop_working_directory_from_sys_path() -> None:
    """Remove the process working directory from `sys.path`.

    The harness launches the engine as `python -m dsh_coderag.server` with the
    working directory set to the workspace being indexed (the patch derives
    `CODERAG_ROOT` from `process.cwd()`), and `-m` puts that directory first on
    `sys.path`. A workspace file named after a stdlib module (`token.py`,
    `types.py`, `parser.py`, `logging.py`, ...) then shadows it and aborts the
    server during this very import, before it can serve a single request.

    The engine reads user files as text and never imports them, so dropping the
    working directory here is safe. The package itself is located through
    site-packages or its own `__path__`, not through the working directory.

    This must stay the first executable statement in the module, ahead of every
    import that is not already loaded at interpreter startup: `typing` pulls in
    `functools` and therefore `types`, so importing it first lets a workspace
    `types.py` fail the import (tests/test_cwd_shadowing.py).
    """
    working_directory = os.path.realpath(os.getcwd())
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry not in ("", ".") and os.path.realpath(entry) != working_directory
    ]


_drop_working_directory_from_sys_path()

from importlib import import_module  # noqa: E402
from typing import TYPE_CHECKING, Any  # noqa: E402

if TYPE_CHECKING:
    from dsh_coderag.types import SearchStatus

__all__ = ["SearchStatus", "__version__", "index_sync", "search"]

__version__ = "2.0.0"

_LAZY_ATTRIBUTES: dict[str, str] = {
    "index_sync": "dsh_coderag.indexer",
    "search": "dsh_coderag.searcher",
    "SearchStatus": "dsh_coderag.types",
}
"""Public name to defining module. Resolved on first attribute access."""


def __getattr__(name: str) -> Any:
    """Resolve a public name on first use (PEP 562).

    Kept deliberately narrow: only the names in `_LAZY_ATTRIBUTES` are
    resolved, so a typo still raises AttributeError instead of importing
    something unexpected. Submodule access keeps working because the import
    system falls back to importing `dsh_coderag.<name>` itself.
    """
    module_name = _LAZY_ATTRIBUTES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
