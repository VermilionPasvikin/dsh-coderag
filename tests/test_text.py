"""Tests for dsh_coderag.text."""

from __future__ import annotations

import pytest

from dsh_coderag.text import to_bigrams


def test_bigrams_are_symmetric_between_index_and_query() -> None:
    """M2: index side and query side must use the same conversion."""
    assert to_bigrams("校验用户令牌的有效性") == "校验 验用 用户 户令 令牌 牌的 的有 有效 效性"


def test_latin_identifier_is_not_bigrammed() -> None:
    assert "verify_token" in to_bigrams("def verify_token(raw): pass")


def test_latin_only_text_is_unchanged() -> None:
    text = "def verify_token(raw):\n    return raw\n"
    assert to_bigrams(text) == text


def test_single_cjk_character_is_kept() -> None:
    assert to_bigrams("器") == "器"


@pytest.mark.parametrize(
    "text",
    [
        "校验用户令牌",
        "校验用户令牌的有效性",
        "def verify_token(raw): pass",
        "abc 中文 def",
        "中文abc",
        "hello  world",
        "用户 token 校验",
    ],
)
def test_to_bigrams_is_idempotent(text: str) -> None:
    once = to_bigrams(text)
    assert to_bigrams(once) == once


@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("用户令牌是在哪里校验的", "令牌"),
        ("如何校验用户令牌", "用户令牌"),
        ("连接池的初始化逻辑", "连接池"),
    ],
)
def test_query_bigrams_match_inside_text_bigrams(text: str, query: str) -> None:
    """M2 round-trip: a query's bigrams appear as a run in the text's bigrams."""
    text_tokens = to_bigrams(text).split()
    query_tokens = to_bigrams(query).split()
    assert query_tokens
    starts = range(len(text_tokens) - len(query_tokens) + 1)
    assert any(text_tokens[index : index + len(query_tokens)] == query_tokens for index in starts)
