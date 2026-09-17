"""Console entry point for the dsh-coderag command.

This module parses the command line and reports package metadata. It does
not start the MCP server; that entry point lives in dsh_coderag.server.
"""

from __future__ import annotations

import argparse
import sys

from dsh_coderag import __version__


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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
