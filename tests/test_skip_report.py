"""Tests for reporting skipped files (PROJECT.md 4.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag.indexer import index_sync
from dsh_coderag.render import render_search_result, render_status
from dsh_coderag.searcher import search
from dsh_coderag.server import build_server
from dsh_coderag.types import SearchResult, SearchStatus, SkipReport
from dsh_coderag.walker import walk_with_report


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_skip_report_classifies_secret_and_ignored_files(secrets_repo: Path) -> None:
    report = walk_with_report(secrets_repo)
    assert report.reasons == {"gitignored": 1, "secret_file": 2}
    names = {path.name for path, _, _ in report.files}
    assert names == {"config.py", "env_reader.py", "normal.py"}


def test_skip_report_is_attached_by_search(secrets_repo: Path) -> None:
    index_sync(secrets_repo)
    result = search(secrets_repo, "add", k=5)
    assert result.status is SearchStatus.READY
    assert result.skipped.reasons == {"gitignored": 1, "secret_file": 2}


def test_skip_report_is_rendered_in_the_search_header(secrets_repo: Path) -> None:
    index_sync(secrets_repo)
    out = render_search_result(search(secrets_repo, "add", k=5))
    assert "skipped: 3 (gitignored: 1, secret_file: 2)" in out


def test_skip_report_is_rendered_for_zero_skips() -> None:
    out = render_search_result(SearchResult(status=SearchStatus.READY, query="x"))
    assert "skipped: 0\n" in out


def test_skip_report_is_rendered_by_status() -> None:
    out = render_status(
        SearchStatus.EMPTY,
        message="No matches.",
        skipped=SkipReport(reasons={"gitignored": 2}),
    )
    assert "skipped: 2 (gitignored: 2)" in out


@pytest.mark.anyio
async def test_skip_report_is_reported_by_index_status(secrets_repo: Path) -> None:
    index_sync(secrets_repo)
    server = build_server(root=secrets_repo)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("index_status", {})
    payload = json.loads(result.content[0].text)
    assert payload["skipped"] == {
        "count": 3,
        "reasons": {"gitignored": 1, "secret_file": 2},
    }
