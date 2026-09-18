"""Tokenizer semantics: punctuation routing, no stemming, stop words (TESTING 3.11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.indexer import index_sync, open_index
from dsh_coderag.searcher import search
from dsh_coderag.types import SearchStatus

PUNCTUATION_QUERIES = ["(", "::", "->", "[", "#", "{}", "()"]


@pytest.fixture
def indexed_tokenizer(tmp_path: Path) -> Path:
    (tmp_path / "connect_only.py").write_text(
        "def connect():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "connection.py").write_text(
        "def connection():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "auth.py").write_text(
        "def login(self):\n    return self.authenticate()\n", encoding="utf-8"
    )
    (tmp_path / "stopwords.py").write_text(
        "def check(items):\n"
        "    for item in items:\n"
        "        if item and not item:\n"
        "            return item\n"
        "    return None\n",
        encoding="utf-8",
    )
    (tmp_path / "vector.cpp").write_text(
        "#include <vector>\nstd::vector<int> make() { return {}; }\n",
        encoding="utf-8",
    )
    index_sync(tmp_path)
    return tmp_path


# ── 测试 1：标点查询必须被显式路由，而不是静默返回空（ADR-13）──
@pytest.mark.parametrize("query", PUNCTUATION_QUERIES)
def test_punctuation_query_routes_to_grep(indexed_tokenizer: Path, query: str) -> None:
    result = search(indexed_tokenizer, query, k=5)
    assert result.status is SearchStatus.EMPTY
    assert result.hits == []
    assert "grep" in (result.hint or "").lower()


@pytest.mark.parametrize(
    ("query", "expected_path"),
    [("self.authenticate", "auth.py"), ("std::vector", "vector.cpp")],
)
def test_punctuation_with_a_searchable_word_still_searches(
    indexed_tokenizer: Path, query: str, expected_path: str
) -> None:
    result = search(indexed_tokenizer, query, k=5)
    assert result.status is SearchStatus.READY
    assert any(hit.path == expected_path for hit in result.hits)


# ── 测试 2：不做词干化（防 porter）──
def test_no_stemming(indexed_tokenizer: Path) -> None:
    result = search(indexed_tokenizer, "connection", k=5)
    assert any(hit.path == "connection.py" for hit in result.hits)
    assert all(hit.path != "connect_only.py" for hit in result.hits)


def test_tokenizer_is_not_porter(indexed_tokenizer: Path) -> None:
    connection = open_index(indexed_tokenizer / ".coderag" / "index.sqlite3")
    try:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'"
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    schema = str(row[0])
    assert "tokenize = 'unicode61'" in schema
    assert "porter" not in schema


# ── 测试 3：不剥离停用词（代码里 for/if/and 是标识符）──
@pytest.mark.parametrize("word", ["for", "if", "and", "in", "not"])
def test_stopwords_are_searchable(indexed_tokenizer: Path, word: str) -> None:
    result = search(indexed_tokenizer, word, k=5)
    assert result.status is SearchStatus.READY
    assert any(hit.path == "stopwords.py" for hit in result.hits)
