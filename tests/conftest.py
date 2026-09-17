"""Shared pytest fixtures for the dsh_coderag test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """Copy the tiny fixture into tmp_path so tests never write repo files."""
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURES / "tiny", dst)
    return dst
