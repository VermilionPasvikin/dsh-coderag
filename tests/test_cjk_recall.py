"""Chinese recall and the precision -> recall fallback (TESTING.md 3.7, M2).

The A1 finding of T3-03/T3-04b was that `_build_match` ANDs every token,
including CJK bigrams that the target code never contains, so a mixed
`identifier + 中文` query returned nothing. PROJECT.md 5.3.1 already specified
the fix: try precision first, and only when it yields nothing fall back to a
recall (OR) match. These tests pin that behaviour, including the M2 case where
precision must still behave like an exact substring match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.indexer import index_sync
from dsh_coderag.searcher import search
from dsh_coderag.types import SearchStatus


@pytest.fixture
def cjk_corpus(tmp_path: Path) -> Path:
    """A tiny indexed corpus with overlapping and non-overlapping CJK runs."""
    root = tmp_path / "cjk"
    (root / "src" / "auth").mkdir(parents=True)
    (root / "src" / "auth" / "token.py").write_text(
        "# 校验用户令牌的有效性\ndef verify_token(raw):\n    return raw\n",
        encoding="utf-8",
    )
    # Has 用户 and 令牌 but not the overlapping bigram 户令: precision must reject it.
    (root / "src" / "auth" / "separate.py").write_text(
        "# 用户表与令牌表\n", encoding="utf-8"
    )
    (root / "src" / "auth" / "session.py").write_text("# 认证流程\n", encoding="utf-8")
    index_sync(root)
    return root


def test_two_char_cjk_word_is_retrievable(cjk_corpus: Path) -> None:
    """M2: a 2-character word must hit — this is why trigram was rejected."""
    result = search(cjk_corpus, "令牌", k=5)
    assert result.status is SearchStatus.READY
    assert "src/auth/token.py" in [hit.path for hit in result.hits]


def test_precision_mode_matches_exact_substring(cjk_corpus: Path) -> None:
    """M2: overlapping bigrams make precision mode an exact substring match."""
    result = search(cjk_corpus, "用户令牌", k=5)
    assert [hit.path for hit in result.hits] == ["src/auth/token.py"]


def test_recall_mode_rescues_a_query_with_an_unmatchable_token(
    cjk_corpus: Path,
) -> None:
    """M2: precision returning nothing must fall back to recall, not empty."""
    result = search(cjk_corpus, "令牌未定义词", k=5)
    assert result.status is SearchStatus.READY
    assert "src/auth/token.py" in [hit.path for hit in result.hits]


def test_mixed_identifier_and_cjk_query_hits(cjk_corpus: Path) -> None:
    """The A1 regression: `verify_token + 未定义词` used to return empty."""
    result = search(cjk_corpus, "verify_token未定义词", k=5)
    assert result.status is SearchStatus.READY
    assert "src/auth/token.py" in [hit.path for hit in result.hits]


def test_both_modes_empty_keeps_the_structured_empty_status(cjk_corpus: Path) -> None:
    """RL-06: the fallback must not fabricate hits, and must stay structured."""
    result = search(cjk_corpus, "zzz_nonexistent_concept", k=5)
    assert result.status is SearchStatus.EMPTY
    assert result.hits == []
    assert result.hint


def test_punctuation_routing_still_precedes_the_fallback(cjk_corpus: Path) -> None:
    """ADR-13: punctuation queries route to grep and never reach recall mode."""
    result = search(cjk_corpus, "::", k=5)
    assert result.status is SearchStatus.EMPTY
    assert result.hits == []
    assert result.hint is not None and "grep" in result.hint.lower()
