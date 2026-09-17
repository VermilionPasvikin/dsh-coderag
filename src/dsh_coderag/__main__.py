"""Console entry point for the dsh-coderag command.

This module parses the command line and dispatches debug commands. It does
not start the MCP server; that entry point lives in dsh_coderag.server.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dsh_coderag import __version__
from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search
from dsh_coderag.types import SearchStatus


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the dsh-coderag command."""
    parser = argparse.ArgumentParser(
        prog="dsh-coderag",
        description="Codebase retrieval engine for DeepSeek Harness.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"dsh-coderag {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")
    index_parser = subparsers.add_parser(
        "index",
        help="Build or refresh the index for a workspace directory.",
    )
    index_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Workspace directory to index (default: current directory).",
    )
    search_parser = subparsers.add_parser(
        "search",
        help="Search the workspace index.",
    )
    search_parser.add_argument("query", help="Keyword or natural-language query.")
    search_parser.add_argument(
        "--root",
        default=".",
        help="Workspace root to search (default: current directory).",
    )
    search_parser.add_argument(
        "-k",
        "--limit",
        type=int,
        default=5,
        help="Maximum number of hits (default: 5).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "index":
        summary = index_sync(Path(args.path))
        sys.stdout.write(
            f"indexed {summary.files} files, {summary.chunks} chunks "
            f"into {summary.root}/.coderag/index.sqlite3\n"
        )
        return 0
    if args.command == "search":
        result = search(Path(args.root), args.query, k=args.limit)
        if result.status is not SearchStatus.READY:
            sys.stderr.write(f"{result.status.value}: {result.message}\n")
            return 1
        for hit in result.hits:
            sys.stdout.write(f"{hit.path}:{hit.start_line}-{hit.end_line}\n")
        return 0
    parser.print_help()
    return 0
