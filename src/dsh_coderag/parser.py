"""Tree-sitter language detection and grammar access for dsh_coderag.

This module maps source paths to tree-sitter grammars by file extension and
loads those grammars from tree-sitter-language-pack. It does not walk the
workspace, read file contents, split text into chunks or write to the
database; the chunker owns those steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from tree_sitter import Language, Parser
from tree_sitter_language_pack import SupportedLanguage
from tree_sitter_language_pack import get_language as _pack_get_language
from tree_sitter_language_pack import get_parser as _pack_get_parser

# Extension (lower case, with leading dot) -> tree-sitter grammar name.
# Keys cover every extension in walker.CODE_EXTENSIONS; ".h" is treated as C.
EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".ts": "typescript",
    ".js": "javascript",
}


def detect_language(path: str | Path) -> str | None:
    """Return the tree-sitter grammar name for path, or None if unsupported.

    The match is on the lower-cased file suffix, so both workspace-relative
    and absolute paths are accepted.
    """
    return EXTENSION_LANGUAGES.get(Path(path).suffix.lower())


def get_language(language: str) -> Language:
    """Load the bundled tree-sitter grammar named language.

    Raises LookupError when no grammar is available for that name.
    """
    return _pack_get_language(cast("SupportedLanguage", language))


def get_parser(language: str) -> Parser:
    """Return a tree-sitter parser bound to the grammar named language.

    Raises LookupError when no grammar is available for that name.
    """
    return _pack_get_parser(cast("SupportedLanguage", language))
