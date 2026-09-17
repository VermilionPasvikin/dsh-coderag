"""dsh_coderag: codebase retrieval engine exposed over MCP.

This package owns the retrieval engine only. It does not own the MCP
transport lifecycle, does not choose an embedding provider, and never
modifies the DeepSeek Harness host.
"""

from __future__ import annotations

from dsh_coderag.indexer import index_sync

__all__ = ["__version__", "index_sync"]

__version__ = "0.1.0"
