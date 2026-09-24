#!/usr/bin/env python3
# ruff: noqa: T201
"""校验检索评测集 `eval/tasks.jsonl`（T3-02a 产出，T3-02b 复用）。

用法:
    python3 scripts/verify-tasks.py eval/tasks.jsonl <被评测仓库根目录>

校验项（任一项失败即退出码 1）:

    [V1]  读取与解析   文件非空、每行合法 JSON 对象、不允许空行
    [V2]  schema       逐条通过 `eval/schema.json`（JSON Schema Draft 2020-12）
    [V3]  唯一 ID      `L-NNN` 不重复
    [V4]  路径格式     工作区相对路径：`/` 分隔、无前导 `/`、无 `.`/`..` 段、无反斜杠
    [V5]  路径存在     `expect_paths` / `must_not_paths` 在仓库下真实存在且是文件
    [V6]  无答案泄漏   query 不含 `expect_paths` 的文件名/stem/规范化路径；
                       非 exact 类还不含 `expect_symbols`（EVAL.md §2.9 陷阱 1）
    [V7]  exact 真标识符  exact 类 query 至少含一个 ASCII 标识符，且至少一个
                       真实出现在目标文件里（EVAL.md §2.4 构造流程 Step 3 的机器化）
    [V8]  natural 无标识符  natural 类 query 的 ASCII 标识符不得出现在目标文件中
                       （否则是把 exact 题伪装成 natural 桶）
    [V9]  class 配比   与 EVAL.md §2.3 的 12:11:7 目标比例一致（±1 容忍 A 批舍入）
    [V10] 任务数下限   < 10 条即失败——A 批下限，低于它就是解析失败或批次不足

为什么 exact 类允许 query 含标识符：那正是 exact 桶的定义（EVAL.md §2.3）。
V6 因此只对非 exact 类检查 `expect_symbols`；对所有类都检查路径片段。

设计原则（沿用 `scripts/verify-plan.py`）:
  * **不静默通过** —— 解析到 0 条、任何检查为 0 都失败或显式报警
  * **不静默跳过** —— 每项检查都打印"实际检查了多少条"
  * **失败可定位** —— 每条失败都带任务 ID 与原因

依赖：`jsonschema`（T3-01 的 schema 自检已使用同一依赖）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# ── 阈值与目标比例（EVAL.md §2.3 / §2.4）────────────────────────────────
MIN_TASKS = 10
RATIO = {"exact": 12, "crossfile": 11, "natural": 20}
# 2026-09-25: natural 由 7 扩到 20（T3-11 后续扩桶）。V1 是 natural 专属判据，
# 7 条时单条翻转 = 14.3pp，样本量不足以支撑判定；见 EVAL.md §2.3 的后续更新。
RATIO_SUM = sum(RATIO.values())
RATIO_TOLERANCE = 1
VALID_CLASSES = ("exact", "crossfile", "natural")

# 标识符：ASCII 字母/下划线开头、长度 ≥3（排除 `if`/`to` 这类短词噪声）
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

FAILS: list[str] = []
WARNINGS: list[str] = []
CHECKS: list[tuple[str, str, bool, str]] = []


def fail(code: str, msg: str) -> None:
    """登记一条失败（打印在前缀 `[Vn]`）。"""
    FAILS.append(f"[{code}] {msg}")


def warn(msg: str) -> None:
    """登记一条不致命但必须可见的警告。"""
    WARNINGS.append(msg)


def tid_of(obj: dict[str, Any]) -> str:
    """取任务 ID；缺失时回退到行号，保证失败信息仍可定位。"""
    tid = obj.get("id")
    if isinstance(tid, str) and tid:
        return tid
    return f"<第{obj.get('__line__', '?')}行>"


def read_text(path: Path) -> str:
    """读文件文本；读不到返回空串（存在性由 V5 单独报告）。"""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ── V1 读取与解析 ──────────────────────────────────────────────────────
def load_tasks(path: Path) -> list[dict[str, Any]]:
    """按 JSONL 逐行解析；空行与非法 JSON 都显式失败，不被跳过。"""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        fail("V1", f"{path} 是空文件")
        return []
    lines = text.splitlines()
    tasks: list[dict[str, Any]] = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            fail("V1", f"第 {lineno} 行为空；JSONL 不允许空行")
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            fail("V1", f"第 {lineno} 行不是合法 JSON：{exc}")
            continue
        if not isinstance(obj, dict):
            fail("V1", f"第 {lineno} 行不是 JSON 对象（实际 {type(obj).__name__}）")
            continue
        obj["__line__"] = lineno
        tasks.append(obj)
    return tasks


# ── V2 schema ──────────────────────────────────────────────────────────
def check_schema(tasks: list[dict[str, Any]], schema_path: Path) -> str:
    """用 eval/schema.json 逐条校验；缺 jsonschema 时显式失败而非跳过。"""
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        fail("V2", "缺少 jsonschema 依赖，无法校验 schema（pip install jsonschema）")
        return "未执行"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.exceptions.SchemaError) as exc:
        fail("V2", f"schema 本身不可用（{schema_path}）：{exc}")
        return "未执行"
    validator = jsonschema.Draft202012Validator(schema)
    passed = 0
    for obj in tasks:
        payload = {k: v for k, v in obj.items() if k != "__line__"}
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        if not errors:
            passed += 1
            continue
        for err in errors:
            loc = "/".join(str(p) for p in err.path) or "<root>"
            fail("V2", f"{tid_of(obj)} 第 {obj['__line__']} 行 schema 违规 {loc}：{err.message}")
    return f"{passed}/{len(tasks)} 条通过 {schema_path.name}"


# ── V3 唯一 ID ─────────────────────────────────────────────────────────
def check_unique_ids(tasks: list[dict[str, Any]]) -> str:
    """重复 ID 会让逐 query diff 与归因无法对齐。"""
    seen: dict[str, int] = {}
    for obj in tasks:
        tid = obj.get("id")
        if not isinstance(tid, str):
            continue
        if tid in seen:
            fail("V3", f"重复 ID {tid}（第 {seen[tid]} 行与第 {obj['__line__']} 行）")
        else:
            seen[tid] = obj["__line__"]
    return f"{len(seen)} 个唯一 ID / {len(tasks)} 条"


# ── V4/V5 路径格式与存在性 ──────────────────────────────────────────────
def path_format_error(rel: str) -> str | None:
    """返回不符合工作区相对路径约定的原因；合规返回 None。"""
    if rel.startswith("/"):
        return "以 / 开头（绝对路径，不是工作区相对路径）"
    if rel.startswith("\\"):
        return "以 \\ 开头（绝对路径）"
    if "\\" in rel:
        return "包含反斜杠（必须用 / 分隔）"
    if re.match(r"^[A-Za-z]:", rel):
        return "包含 Windows 盘符"
    parts = rel.split("/")
    if any(p in (".", "..") for p in parts):
        return "包含 . 或 .. 路径段"
    if "" in parts:
        return "包含空路径段（前导/结尾 / 或 //）"
    return None


def iter_declared_paths(tasks: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str, str]]:
    """展开所有 (任务, 字段名, 路径) 三元组。"""
    out: list[tuple[dict[str, Any], str, str]] = []
    for obj in tasks:
        for field in ("expect_paths", "must_not_paths"):
            values = obj.get(field)
            if not isinstance(values, list):
                continue
            for rel in values:
                if isinstance(rel, str):
                    out.append((obj, field, rel))
    return out


def check_path_format(tasks: list[dict[str, Any]]) -> str:
    declared = iter_declared_paths(tasks)
    for obj, field, rel in declared:
        reason = path_format_error(rel)
        if reason is not None:
            fail("V4", f"{tid_of(obj)} 的 {field} 项 {rel!r} 不合规：{reason}")
    return f"{len(declared)} 条路径"


def check_path_exists(tasks: list[dict[str, Any]], corpus: Path) -> str:
    declared = iter_declared_paths(tasks)
    existing = 0
    for obj, field, rel in declared:
        target = corpus / rel
        if target.is_file():
            existing += 1
        else:
            fail("V5", f"{tid_of(obj)} 的 {field} 项 {rel!r} 在 {corpus} 下不存在或不是文件")
    return f"{existing}/{len(declared)} 条路径存在"


# ── V6 无答案泄漏 ──────────────────────────────────────────────────────
def leak_candidates(rel: str) -> list[str]:
    """query 里若出现这些片段就说明答案泄漏（长片段优先报告）。"""
    path = rel.lstrip("/")
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return sorted({path, name, stem}, key=len, reverse=True)


def mentions(query: str, cand: str) -> bool:
    """query 是否以完整 token 形式出现 cand（大小写不敏感）。

    必须带标识符边界：`delegationDepthOf` 里的 `depth` 不是路径泄漏，
    而 `depth 的定义` / `depth.ts` 是。边界定义为 `[A-Za-z0-9_]`。
    """
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(cand) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, query, re.IGNORECASE) is not None


def check_no_leak(tasks: list[dict[str, Any]]) -> str:
    """EVAL.md §2.9 陷阱 1：query 不能抄目标路径或（非 exact 的）符号名。"""
    checked = 0
    for obj in tasks:
        checked += 1
        query = obj["query"]
        for rel in obj.get("expect_paths", []) or []:
            if not isinstance(rel, str):
                continue
            for cand in leak_candidates(rel):
                if len(cand) >= 4 and mentions(query, cand):
                    fail("V6", f"{tid_of(obj)} query 泄漏目标路径片段 {cand!r}（来自 {rel}）")
        if obj.get("class") != "exact":
            for sym in obj.get("expect_symbols", []) or []:
                if isinstance(sym, str) and mentions(query, sym):
                    fail("V6", f"{tid_of(obj)} 非 exact 类 query 泄漏 expect_symbols 符号 {sym!r}")
    return f"{checked} 条 query"


# ── V7/V8 分桶词法检查 ─────────────────────────────────────────────────
def target_texts(obj: dict[str, Any], corpus: Path) -> list[str]:
    return [read_text(corpus / rel) for rel in obj.get("expect_paths", []) or []
            if isinstance(rel, str)]


def check_exact_identifiers(tasks: list[dict[str, Any]], corpus: Path) -> str:
    """exact 桶的标识符必须来自真实代码，否则这道题无法用词法命中。"""
    checked = 0
    for obj in tasks:
        if obj.get("class") != "exact":
            continue
        checked += 1
        tokens = sorted(set(IDENT_RE.findall(obj["query"])))
        if not tokens:
            fail("V7", f"{tid_of(obj)} 是 exact 类但 query 不含任何 ASCII 标识符")
            continue
        texts = target_texts(obj, corpus)
        matched = [t for t in tokens if any(t in txt for txt in texts)]
        if not matched:
            fail("V7", f"{tid_of(obj)} query 标识符 {tokens} 均未出现在 expect_paths 目标文件中")
    return f"{checked} 条 exact"


def check_natural_identifiers(tasks: list[dict[str, Any]], corpus: Path) -> str:
    """natural 桶必须与目标代码零标识符重叠，否则它测的不是自然语言检索。"""
    checked = 0
    for obj in tasks:
        if obj.get("class") != "natural":
            continue
        checked += 1
        tokens = sorted(set(IDENT_RE.findall(obj["query"])))
        if not tokens:
            continue
        texts = target_texts(obj, corpus)
        leaked = [t for t in tokens if any(t in txt for txt in texts)]
        if leaked:
            fail("V8", f"{tid_of(obj)} 是 natural 类但 query 含目标代码中的标识符 {leaked}")
        else:
            warn(f"{tid_of(obj)} natural query 含 ASCII 标识符 {tokens}，但均未出现在目标代码中")
    return f"{checked} 条 natural"


# ── V9/V10 配比与下限 ──────────────────────────────────────────────────
def check_ratio(tasks: list[dict[str, Any]]) -> str:
    ratio_label = ":".join(str(RATIO[c]) for c in VALID_CLASSES)
    total = len(tasks)
    actual = {c: sum(1 for o in tasks if o.get("class") == c) for c in VALID_CLASSES}
    for cls in VALID_CLASSES:
        expected = total * RATIO[cls] / RATIO_SUM
        if abs(actual[cls] - expected) > RATIO_TOLERANCE:
            fail("V9", f"{cls} 实际 {actual[cls]} 条，目标比例 {ratio_label} 下应为 "
                       f"{expected:.2f}±{RATIO_TOLERANCE}")
    return (f"exact/crossfile/natural = {actual['exact']}/{actual['crossfile']}/"
            f"{actual['natural']}，目标比例 {ratio_label}（±{RATIO_TOLERANCE}）")


def check_min_tasks(tasks: list[dict[str, Any]]) -> str:
    if len(tasks) < MIN_TASKS:
        fail("V10", f"只解析到 {len(tasks)} 条任务，低于 A 批下限 {MIN_TASKS} 条")
    return f"{len(tasks)} ≥ {MIN_TASKS}"


def run_check(code: str, label: str, fn: Any, *args: Any) -> None:
    """执行一项检查并记录其通过/失败状态（失败由 fail() 内部登记）。"""
    before = len(FAILS)
    detail = fn(*args)
    CHECKS.append((code, label, len(FAILS) == before, detail))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("用法: python3 scripts/verify-tasks.py <tasks.jsonl> <被评测仓库根目录>")
        return 2
    tasks_path = Path(argv[1])
    corpus = Path(argv[2]).resolve()
    schema_path = tasks_path.resolve().parent / "schema.json"

    print("== verify-tasks ==")
    print(f"tasks : {tasks_path}")
    print(f"corpus: {corpus}")
    if not tasks_path.is_file():
        print(f"FAIL: 任务文件不存在：{tasks_path}")
        return 1
    if not corpus.is_dir():
        print(f"FAIL: 被评测仓库不存在或不是目录：{corpus}")
        return 1

    before_load = len(FAILS)
    tasks = load_tasks(tasks_path)
    CHECKS.append(("V1", "读取与解析", len(FAILS) == before_load, f"{len(tasks)} 条有效任务"))
    if not tasks:
        for item in FAILS:
            print(item)
        print("FAIL: 未解析到任何任务")
        return 1
    counts = {c: sum(1 for o in tasks if o.get("class") == c) for c in VALID_CLASSES}
    print(f"解析到 {len(tasks)} 条任务"
          f"（exact {counts['exact']} / crossfile {counts['crossfile']} / "
          f"natural {counts['natural']}）")
    print()

    if schema_path.is_file():
        run_check("V2", "schema", check_schema, tasks, schema_path)
    else:
        fail("V2", f"缺少 schema 文件：{schema_path}")
        run_check("V2", "schema", lambda: "未执行")
    run_check("V3", "唯一 ID", check_unique_ids, tasks)
    run_check("V4", "路径格式", check_path_format, tasks)
    run_check("V5", "路径存在", check_path_exists, tasks, corpus)
    run_check("V6", "无答案泄漏", check_no_leak, tasks)
    run_check("V7", "exact 标识符存在", check_exact_identifiers, tasks, corpus)
    run_check("V8", "natural 无标识符", check_natural_identifiers, tasks, corpus)
    run_check("V9", "class 配比", check_ratio, tasks)
    run_check("V10", "任务数下限", check_min_tasks, tasks)

    for code, label, ok, detail in CHECKS:
        print(f"[{code:<3}] {label:<16} {'PASS' if ok else 'FAIL'}  {detail}")
    for msg in WARNINGS:
        print(f"WARN  {msg}")
    print()
    if FAILS:
        for item in FAILS:
            print(item)
        print(f"\nFAIL: {len(FAILS)} 项检查失败（{len(tasks)} 条任务）")
        return 1
    print(f"PASS: {len(tasks)} 条任务全部通过 {len(CHECKS)} 项检查")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
