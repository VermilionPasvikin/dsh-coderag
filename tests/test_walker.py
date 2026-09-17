"""Tests for dsh_coderag.walker."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.walker import CODE_EXTENSIONS, walk


def _relative_paths(entries: list[tuple[Path, int, int]], base: Path) -> list[str]:
    return sorted(str(path.relative_to(base)) for path, _, _ in entries)


def test_walk_returns_whitelisted_files_in_stable_order(tiny_repo: Path) -> None:
    entries = walk(tiny_repo)
    assert _relative_paths(entries, tiny_repo) == ["app.ts", "lib.c", "main.py"]
    assert all(size > 0 for _, size, _ in entries)
    assert all(mtime_ns > 0 for _, _, mtime_ns in entries)


def test_walk_skips_files_with_unlisted_extensions(tiny_repo: Path) -> None:
    (tiny_repo / "notes.md").write_text("not code\n", encoding="utf-8")
    (tiny_repo / "data.json").write_text("{}\n", encoding="utf-8")
    assert _relative_paths(walk(tiny_repo), tiny_repo) == ["app.ts", "lib.c", "main.py"]


def test_walk_recurses_into_subdirectories(tiny_repo: Path) -> None:
    nested = tiny_repo / "pkg" / "sub"
    nested.mkdir(parents=True)
    (nested / "util.js").write_text("export const x = 1;\n", encoding="utf-8")
    assert "pkg/sub/util.js" in _relative_paths(walk(tiny_repo), tiny_repo)


def test_walk_returns_absolute_paths(tiny_repo: Path) -> None:
    assert all(path.is_absolute() for path, _, _ in walk(tiny_repo))


def test_code_extensions_cover_the_documented_whitelist() -> None:
    assert {".py", ".c", ".h", ".cpp", ".hpp", ".ts", ".js"} == CODE_EXTENSIONS
