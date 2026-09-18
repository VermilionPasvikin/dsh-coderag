"""MCP server exposing the four dsh_coderag tools over stdio.

This module is a thin protocol layer: it owns the tool schemas, argument
validation and dispatch into the engine. It contains no retrieval logic.
stdout belongs exclusively to the MCP transport, so nothing here may write
to it (RL-04).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from dsh_coderag import __version__
from dsh_coderag.config import ConfigError, load_config
from dsh_coderag.indexer import index_sync, open_index
from dsh_coderag.render import render_search_result, render_status
from dsh_coderag.searcher import search
from dsh_coderag.taskman import TaskManager, TaskNotFoundError
from dsh_coderag.types import ErrorCode, SearchStatus

SERVER_NAME = "coderag"

TOOLS: list[Tool] = [
    Tool(
        name="code_search",
        description=(
            "Search the workspace codebase for relevant code. Returns ranked code"
            " snippets with exact file paths and line numbers. Prefer this over grep"
            " when you do not know the exact identifier, or when searching for"
            " behaviour across multiple files. When the index is not ready the result"
            " reports a structured status instead of an empty list."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language or identifiers describing what you are"
                        " looking for."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative directory to search within. Defaults to"
                        " the workspace root."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of snippets. Defaults to 5, maximum 50.",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": (
                        "Approximate token budget for the returned snippets."
                        " Defaults to 4000."
                    ),
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="code_outline",
        description=(
            "Return the symbol outline (classes, functions, methods) of one file, with"
            " line numbers. Use this to understand a file's structure before reading"
            " it in full."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Nesting depth to include. Defaults to 2.",
                },
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="code_index",
        description=(
            "Start (or refresh) the code index for a workspace directory. Returns"
            " immediately with a task id; indexing continues in the background. Poll"
            " index_status for progress."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative directory to index. Defaults to the"
                        " workspace root."
                    ),
                },
                "force": {
                    "type": "boolean",
                    "description": (
                        "Rebuild from scratch instead of incrementally. Defaults to"
                        " false."
                    ),
                },
            },
        },
    ),
    Tool(
        name="index_status",
        description=(
            "Report the state and progress of an indexing task, or of the workspace"
            " index when no task id is given."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": (
                        "Task id returned by code_index. Omit to report the current"
                        " workspace index."
                    ),
                },
            },
        },
    ),
]


def build_server(root: Path | None = None) -> Server:
    """Build the MCP server. root defaults to CODERAG_ROOT at call time."""
    server: Server = Server(SERVER_NAME, version=__version__)

    def workspace_root() -> Path:
        if root is not None:
            return root
        return load_config().root

    @server.list_tools()  # type: ignore[untyped-decorator, no-untyped-call]
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return [TextContent(type="text", text=_dispatch(name, arguments, workspace_root))]

    return server


def _dispatch(
    name: str, arguments: dict[str, Any], root_provider: Callable[[], Path]
) -> str:
    """Run one tool, converting every expected failure into structured text."""
    try:
        root = root_provider()
        if name == "code_search":
            return _code_search(arguments, root)
        if name == "code_outline":
            return _code_outline()
        if name == "code_index":
            return _code_index(arguments, root)
        if name == "index_status":
            return _index_status(arguments, root)
    except ConfigError as exc:
        return render_status(
            SearchStatus.ERROR, message=str(exc), code=ErrorCode.INDEX_NOT_FOUND
        )
    except FileNotFoundError as exc:
        return render_status(
            SearchStatus.INDEXING,
            message=str(exc),
            code=ErrorCode.INDEX_NOT_FOUND,
            hint="Call code_index for this workspace, then retry.",
        )
    except TaskNotFoundError as exc:
        return render_status(
            SearchStatus.ERROR, message=str(exc), code=ErrorCode.TASK_NOT_FOUND
        )
    return render_status(
        SearchStatus.ERROR, message=f"unknown tool: {name}", code=ErrorCode.SEARCH_FAILED
    )


def _code_search(arguments: dict[str, Any], root: Path) -> str:
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        return render_status(
            SearchStatus.ERROR,
            message="query is required",
            code=ErrorCode.SEARCH_INVALID_QUERY,
        )
    limit = min(int(arguments.get("limit", 5)), 50)
    result = search(root, query, k=limit)
    if result.status is not SearchStatus.READY:
        return render_status(
            result.status,
            message=result.message or "Search did not return results.",
            code=result.code,
            hint=result.hint,
        )
    return render_search_result(result)


def _code_outline() -> str:
    return render_status(
        SearchStatus.EMPTY,
        message="code_outline is not implemented yet.",
        hint="Use code_search to locate the symbol, then read the file directly.",
    )


def _code_index(arguments: dict[str, Any], root: Path) -> str:
    target = root
    relative = arguments.get("path")
    if isinstance(relative, str) and relative:
        target = (root / relative).resolve()
    db_path = target.resolve() / ".coderag" / "index.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    task_id = TaskManager(db_path).start(target, index_sync)
    return json.dumps(
        {
            "taskId": task_id,
            "state": "pending",
            "hint": "Poll index_status with this taskId.",
        },
        ensure_ascii=False,
    )


def _index_status(arguments: dict[str, Any], root: Path) -> str:
    db_path = root.resolve() / ".coderag" / "index.sqlite3"
    task_id = arguments.get("task_id")
    if isinstance(task_id, str) and task_id:
        if not db_path.exists():
            return render_status(
                SearchStatus.ERROR,
                message="no index for this workspace",
                code=ErrorCode.INDEX_NOT_FOUND,
            )
        run = TaskManager(db_path).status(task_id)
        return json.dumps(
            {
                "taskId": run.task_id,
                "state": run.state,
                "total_files": run.total_files,
                "done_files": run.done_files,
                "total_chunks": run.total_chunks,
                "done_chunks": run.done_chunks,
                "message": run.message,
            },
            ensure_ascii=False,
        )
    if not db_path.exists():
        return render_status(
            SearchStatus.ERROR,
            message="no index for this workspace",
            code=ErrorCode.INDEX_NOT_FOUND,
        )
    connection = open_index(db_path)
    try:
        row = connection.execute(
            "SELECT ready, db_schema FROM workspace_index WHERE root = ?",
            (str(root.resolve()),),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return render_status(
            SearchStatus.ERROR,
            message="no index for this workspace",
            code=ErrorCode.INDEX_NOT_FOUND,
        )
    return json.dumps(
        {"status": "ready" if row[0] else "indexing", "db_schema": row[1]},
        ensure_ascii=False,
    )





async def main() -> None:
    """Run the server over stdio until the client closes the connection."""
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run() -> None:
    """Console entry point for the stdio server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
