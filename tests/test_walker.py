"""Tests for dsh_coderag.walker."""

from __future__ import annotations

from pathlib import Path

from dsh_coderag.walker import CODE_EXTENSIONS, walk, walk_with_report


def _relative_paths(entries: list[tuple[Path, int, int]], base: Path) -> list[str]:
    # as_posix, not str: the workspace-relative path form the engine stores is
    # always forward-slashed (C-07), so the expectation reads the same on
    # Windows as on macOS/Linux.
    return sorted(path.relative_to(base).as_posix() for path, _, _ in entries)


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


def test_walk_counts_files_whose_extension_is_not_code(tmp_path: Path) -> None:
    """A workspace of game assets is a legitimate zero, not a silent failure.

    `files == 0` and `reasons == {}` are both correct there — an unlisted
    extension is not a skip (4.2) — so the walk reports what it saw separately
    (T6-16), otherwise an empty index is indistinguishable from a broken one.
    """
    for name in ("ship.MXML", "ui.MXML", "readme.txt"):
        (tmp_path / name).write_text("<mx:Canvas/>", encoding="utf-8")
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")

    report = walk_with_report(tmp_path)

    assert [path.name for path, _, _ in report.files] == ["mod.py"]
    assert report.reasons == {}, "an unlisted extension is not a skip"
    assert report.seen_files == 4
    assert report.other_extensions == 3
