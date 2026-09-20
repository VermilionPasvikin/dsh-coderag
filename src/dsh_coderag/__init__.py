"""dsh_coderag: codebase retrieval engine exposed over MCP.

This package owns the retrieval engine only. It does not own the MCP
transport lifecycle, does not choose an embedding provider, and never
modifies the DeepSeek Harness host.
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
    """
    working_directory = os.path.realpath(os.getcwd())
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry not in ("", ".") and os.path.realpath(entry) != working_directory
    ]


_drop_working_directory_from_sys_path()

from dsh_coderag.indexer import index_sync  # noqa: E402
from dsh_coderag.searcher import search  # noqa: E402
from dsh_coderag.types import SearchStatus  # noqa: E402

__all__ = ["SearchStatus", "__version__", "index_sync", "search"]

__version__ = "0.1.0"
