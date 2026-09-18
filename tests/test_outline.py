"""Tests for code_outline (T2-13)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag.searcher import OutlineSymbol, outline
from dsh_coderag.server import build_server


def test_outline_returns_the_symbol_tree(decl_repo: Path) -> None:
    symbols = outline(decl_repo, "sample.py")
    assert symbols == [
        OutlineSymbol("function", "add", 4, 5),
        OutlineSymbol("function", "decorator", 8, 9),
        OutlineSymbol("function", "run", 12, 14),
        OutlineSymbol(
            "class",
            "Pool",
            17,
            19,
            (OutlineSymbol("method", "acquire", 18, 19),),
        ),
    ]


def test_outline_respects_max_depth(decl_repo: Path) -> None:
    symbols = outline(decl_repo, "sample.py", max_depth=1)
    assert symbols[-1] == OutlineSymbol("class", "Pool", 17, 19)


def test_outline_returns_empty_for_an_unknown_language(decl_repo: Path) -> None:
    (decl_repo / "notes.txt").write_text("hello\n", encoding="utf-8")
    assert outline(decl_repo, "notes.txt") == []


def test_outline_rejects_a_path_outside_the_workspace(decl_repo: Path) -> None:
    with pytest.raises(ValueError):
        outline(decl_repo, "../outside.py")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_code_outline_returns_the_rendered_tree(decl_repo: Path) -> None:
    server = build_server(root=decl_repo)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("code_outline", {"path": "sample.py"})
    assert result.content[0].text == (
        "status: ready\n"
        "path: sample.py\n"
        "symbols: 5\n"
        "\n"
        "function add  lines 4-5\n"
        "function decorator  lines 8-9\n"
        "function run  lines 12-14\n"
        "class Pool  lines 17-19\n"
        "  method acquire  lines 18-19\n"
    )


@pytest.mark.anyio
async def test_code_outline_reports_a_missing_file(decl_repo: Path) -> None:
    server = build_server(root=decl_repo)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("code_outline", {"path": "nope.py"})
    assert result.content[0].text.startswith("status: empty")
