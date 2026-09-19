"""Load and validate retrieval evaluation tasks (EVAL.md 2.2 / 2.9).

This module owns the on-disk contract of `eval/tasks.jsonl`: parsing each line
into an `EvalTask` and checking the tasks against a corpus root. It does not
run searches, does not compute metrics and does not read the index.

The checks here are the in-package form of the construction rules. The
standalone `scripts/verify-tasks.py` (T3-02a) keeps its own copy so it can
validate a golden set without importing the package; keep the two in sync when
a rule changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

TASK_CLASSES: tuple[str, ...] = ("exact", "crossfile", "natural")

_ID_RE = re.compile(r"^L-[0-9]{3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_REQUIRED_FIELDS = ("id", "class", "query", "expect_paths", "added")
_OPTIONAL_FIELDS = ("expect_symbols", "must_not_paths", "notes")
_ALLOWED_FIELDS = frozenset(_REQUIRED_FIELDS + _OPTIONAL_FIELDS)


class EvalError(Exception):
    """Base class for eval failures that must reach the caller as an exception."""


class EvalTaskError(EvalError):
    """`eval/tasks.jsonl` cannot be parsed into `EvalTask` objects."""


@dataclass(frozen=True)
class EvalTask:
    """One golden retrieval task.

    expect_paths / must_not_paths are workspace-relative paths using forward
    slashes. `task_class` maps to the JSONL `class` field, which cannot be a
    Python attribute name.
    """

    id: str
    task_class: str
    query: str
    expect_paths: tuple[str, ...]
    added: str
    expect_symbols: tuple[str, ...] = ()
    must_not_paths: tuple[str, ...] = ()
    notes: str | None = None


def load_tasks(path: Path) -> list[EvalTask]:
    """Parse a JSONL golden set into tasks, failing loudly on the first bad line.

    Raises:
        EvalTaskError: If the file is empty, contains a blank line, a line that
            is not a JSON object, or an object that violates the field
            contract (missing/unknown field, wrong type, empty id).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvalTaskError(f"{path}: 无法读取：{exc}") from exc
    tasks: list[EvalTask] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise EvalTaskError(f"{path}:{lineno}: 空行；JSONL 不允许空行")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalTaskError(f"{path}:{lineno}: 非法 JSON：{exc}") from exc
        if not isinstance(payload, dict):
            raise EvalTaskError(f"{path}:{lineno}: 不是 JSON 对象")
        tasks.append(_build_task(payload, path, lineno))
    if not tasks:
        raise EvalTaskError(f"{path}: 未解析到任何任务")
    return tasks


def validate_tasks(tasks: list[EvalTask], corpus_root: Path) -> list[str]:
    """Check tasks against a corpus root and return every problem found.

    An empty list means the set is usable. Checked here: id shape and
    uniqueness, class enum, non-empty query, path format and existence,
    `expect_paths`/`must_not_paths` disjointness, `added` date, and the
    answer-leak rule (a query must not name its own target file or, outside
    the exact bucket, an expected symbol).
    """
    errors: list[str] = []
    base = corpus_root.resolve()
    if not base.is_dir():
        errors.append(f"被评测仓库不存在或不是目录：{base}")
    seen: dict[str, int] = {}
    for index, task in enumerate(tasks, start=1):
        where = f"第 {index} 条（{task.id or '<无 id>'}）"
        if not _ID_RE.match(task.id):
            errors.append(f"{where}: id 不符合 L-NNN 格式")
        elif task.id in seen:
            errors.append(f"{where}: id 与第 {seen[task.id]} 条重复")
        else:
            seen[task.id] = index
        if task.task_class not in TASK_CLASSES:
            errors.append(f"{where}: class {task.task_class!r} 不在 {TASK_CLASSES}")
        if not task.query.strip():
            errors.append(f"{where}: query 为空")
        if not task.expect_paths:
            errors.append(f"{where}: expect_paths 为空")
        if not _is_iso_date(task.added):
            errors.append(f"{where}: added {task.added!r} 不是 YYYY-MM-DD 日期")
        for field, values in (
            ("expect_paths", task.expect_paths),
            ("must_not_paths", task.must_not_paths),
        ):
            if len(set(values)) != len(values):
                errors.append(f"{where}: {field} 含重复项")
            for rel in values:
                reason = path_format_error(rel)
                if reason is not None:
                    errors.append(f"{where}: {field} 项 {rel!r} 不合规：{reason}")
                elif base.is_dir() and not (base / rel).is_file():
                    errors.append(f"{where}: {field} 项 {rel!r} 在 {base} 下不存在")
        overlap = set(task.expect_paths) & set(task.must_not_paths)
        if overlap:
            errors.append(
                f"{where}: 同一条路径同时在 expect_paths 与 must_not_paths：{sorted(overlap)}"
            )
        for rel in task.expect_paths:
            for candidate in leak_candidates(rel):
                if len(candidate) >= 4 and mentions(task.query, candidate):
                    errors.append(f"{where}: query 泄漏目标路径片段 {candidate!r}（来自 {rel}）")
        if task.task_class != "exact":
            for symbol in task.expect_symbols:
                if mentions(task.query, symbol):
                    errors.append(f"{where}: 非 exact 类 query 泄漏 expect_symbols 符号 {symbol!r}")
    return errors


def path_format_error(rel: str) -> str | None:
    """Return why `rel` is not a workspace-relative path, or None if it is."""
    if rel.startswith("/"):
        return "以 / 开头（绝对路径）"
    if rel.startswith("\\") or "\\" in rel:
        return "包含反斜杠（必须用 / 分隔）"
    if re.match(r"^[A-Za-z]:", rel):
        return "包含 Windows 盘符"
    parts = rel.split("/")
    if any(part in (".", "..") for part in parts):
        return "包含 . 或 .. 路径段"
    if "" in parts:
        return "包含空路径段"
    return None


def leak_candidates(rel: str) -> list[str]:
    """Fragments of `rel` that must not appear in the query (longest first)."""
    path = rel.lstrip("/")
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return sorted({path, name, stem}, key=len, reverse=True)


def mentions(query: str, candidate: str) -> bool:
    """Whether `candidate` appears in `query` as a whole identifier.

    Boundaries are `[A-Za-z0-9_]` so `depth` does not match inside
    `delegationDepthOf`, while `depth 的定义` and `depth.ts` do match.
    """
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(candidate) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, query, re.IGNORECASE) is not None


def _is_iso_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _build_task(payload: dict[str, Any], path: Path, lineno: int) -> EvalTask:
    where = f"{path}:{lineno}"
    missing = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing:
        raise EvalTaskError(f"{where}: 缺少必填字段 {missing}")
    unknown = sorted(set(payload) - _ALLOWED_FIELDS)
    if unknown:
        raise EvalTaskError(f"{where}: 未知字段 {unknown}")
    task_id = payload["id"]
    task_class = payload["class"]
    query = payload["query"]
    added = payload["added"]
    if not isinstance(task_id, str) or not task_id:
        raise EvalTaskError(f"{where}: id 必须是非空字符串")
    if not isinstance(task_class, str):
        raise EvalTaskError(f"{where}: class 必须是字符串")
    if not isinstance(query, str):
        raise EvalTaskError(f"{where}: query 必须是字符串")
    if not isinstance(added, str):
        raise EvalTaskError(f"{where}: added 必须是字符串")
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise EvalTaskError(f"{where}: notes 必须是字符串")
    return EvalTask(
        id=task_id,
        task_class=task_class,
        query=query,
        expect_paths=_string_tuple(payload, "expect_paths", where),
        added=added,
        expect_symbols=_string_tuple(payload, "expect_symbols", where),
        must_not_paths=_string_tuple(payload, "must_not_paths", where),
        notes=notes,
    )


def _string_tuple(payload: dict[str, Any], field: str, where: str) -> tuple[str, ...]:
    values = payload.get(field, [])
    if not isinstance(values, list):
        raise EvalTaskError(f"{where}: {field} 必须是数组")
    out: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item:
            raise EvalTaskError(f"{where}: {field} 的每一项必须是非空字符串")
        out.append(item)
    return tuple(out)
