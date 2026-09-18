"""Tests for dsh_coderag.parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsh_coderag.parser import (
    EXTENSION_LANGUAGES,
    detect_language,
    get_language,
    get_parser,
)
from dsh_coderag.walker import CODE_EXTENSIONS

# A minimal snippet per grammar. Parsing it and checking the root node type
# proves the grammar actually loaded, not merely that a name was returned.
SAMPLE_SOURCES: dict[str, bytes] = {
    "python": b"def verify_token(token):\n    return token\n",
    "c": b"int add(int a, int b) { return a + b; }\n",
    "cpp": b"class Pool { public: int size; };\n",
    "typescript": b"function add(a: number): number { return a; }\n",
    "javascript": b"function add(a) { return a; }\n",
}

EXPECTED_ROOT_TYPES: dict[str, str] = {
    "python": "module",
    "c": "translation_unit",
    "cpp": "translation_unit",
    "typescript": "program",
    "javascript": "program",
}

EXTENSION_CASES = [
    ("main.py", "python"),
    ("lib.c", "c"),
    ("lib.h", "c"),
    ("lib.cpp", "cpp"),
    ("lib.hpp", "cpp"),
    ("app.ts", "typescript"),
    ("app.js", "javascript"),
]


def test_every_indexable_extension_has_a_grammar() -> None:
    assert EXTENSION_LANGUAGES.keys() >= CODE_EXTENSIONS


@pytest.mark.parametrize(("filename", "language"), EXTENSION_CASES)
def test_detect_language_maps_extension_to_grammar_name(filename: str, language: str) -> None:
    assert detect_language(filename) == language


def test_detect_language_is_case_insensitive() -> None:
    assert detect_language("MAIN.PY") == "python"


def test_detect_language_accepts_nested_paths() -> None:
    assert detect_language(Path("src/auth/token.py")) == "python"


@pytest.mark.parametrize("filename", ["README.md", "script.rb", "noextension", "archive.tar.gz"])
def test_detect_language_returns_none_for_unknown_extension(filename: str) -> None:
    assert detect_language(filename) is None


def test_detect_language_ignores_dotfiles_without_suffix() -> None:
    assert detect_language(".gitignore") is None


@pytest.mark.parametrize("language", ["python", "c", "cpp", "typescript", "javascript"])
def test_grammar_parses_its_language_without_errors(language: str) -> None:
    tree = get_parser(language).parse(SAMPLE_SOURCES[language])
    assert tree.root_node.type == EXPECTED_ROOT_TYPES[language]
    assert not tree.root_node.has_error


def test_detection_and_grammar_load_agree_for_the_four_target_languages() -> None:
    cases = {
        "src/auth/token.py": "python",
        "src/db/pool.c": "c",
        "src/db/pool.hpp": "cpp",
        "web/app.ts": "typescript",
    }
    for filename, expected in cases.items():
        language = detect_language(filename)
        assert language == expected
        assert get_language(language) is not None
        tree = get_parser(language).parse(SAMPLE_SOURCES[expected])
        assert not tree.root_node.has_error


def test_unknown_language_name_raises_lookup_error() -> None:
    with pytest.raises(LookupError):
        get_language("definitelynotalang")
