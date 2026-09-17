#!/usr/bin/env python3
"""`verify-plan.py` 的**变异测试**——证明每项检查在坏数据上真的会失败。

一个只会说"通过"的校验器毫无价值。本脚本把四份文档复制到临时目录，
逐个施加"人为破坏"，然后断言 `verify-plan.py` **必须返回非零**。

用法:
    python3 scripts/test-verify-plan.py .

退出码 0 表示全部变异都被检出；非 0 表示有检查是"纸老虎"。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DOCS = ("PROJECT.md", "AGENTS.md", "EVAL.md", "TESTING.md")
HERE = Path(__file__).resolve().parent


def run(root: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(HERE / "verify-plan.py"), str(root)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def mutate_drop_matrix_row(key: str):
    """删除覆盖矩阵中某个键所在的行。"""
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        out = [l for l in lines if not re.match(rf"^\|\s*`?{re.escape(key)}`?\s*\|", l)]
        assert len(out) < len(lines), f"没找到矩阵行 {key}"
        files["PROJECT.md"] = "".join(out)
        return files
    return f


def mutate_duplicate_task(tid: str = "T2-05"):
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(rf"^\|\s*{re.escape(tid)}\s*\|", l) and "未开始" not in l:
                lines.insert(i + 1, l)
                break
        else:
            raise AssertionError("没找到任务行")
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_self_dep(tid: str = "T2-09"):
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(rf"^\|\s*{re.escape(tid)}\s*\|", l) and "未开始" not in l:
                cells = l.rstrip("\n").split("|")
                cells[6] = f" {tid} "          # 依赖列 → 指向自己
                lines[i] = "|".join(cells) + "\n"
                break
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_orphan_t1(tid: str = "T1-06"):
    """把某个 T1 任务的依赖清空，使它成为孤岛（追不到 T1-01）。"""
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(rf"^\|\s*{re.escape(tid)}\s*\|", l) and "未开始" not in l:
                cells = l.rstrip("\n").split("|")
                cells[6] = " — "
                lines[i] = "|".join(cells) + "\n"
                break
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_eval_ghost(tid: str = "T9-99"):
    def f(files: dict[str, str]) -> dict[str, str]:
        files["EVAL.md"] = files["EVAL.md"].replace(
            "| **评测集构造拆成", f"| **新增 `{tid}`** 什么的 | 占位 |\n| **评测集构造拆成", 1)
        return files
    return f


def mutate_testing_mapping(item: str = "M5", ghost: str = "T9-88"):
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["TESTING.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(rf"^\|\s*\*\*{item}\*\*\s*\|", l):
                lines[i] = re.sub(r"T[0-9]-[0-9]+[a-z]?", ghost, l)
                break
        files["TESTING.md"] = "".join(lines)
        return files
    return f


def mutate_dup_matrix_key():
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(r"^\|\s*`?ADR-07`?\s*\|", l):
                lines.insert(i + 1, l)
                break
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_fake_matrix_key():
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(r"^\|\s*`?ADR-07`?\s*\|", l):
                lines.insert(i + 1, "| ADR-99 | T1-01 | 虚构定义 |\n")
                break
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_empty_matrix():
    def f(files: dict[str, str]) -> dict[str, str]:
        files["PROJECT.md"] = files["PROJECT.md"].replace("### 6.7 覆盖矩阵", "### 6.7x 覆盖矩阵", 1)
        return files
    return f


def mutate_dash_without_note():
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        n = 0
        for i, l in enumerate(lines):
            if re.match(r"^\|\s*`?C3`?\s*\|\s*\*?全局\*?\s*\|", l):
                lines[i] = "| C3 | — |  |\n"
                n += 1
        assert n, "没找到 C3 行"
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_bad_force_token():
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(r"^\|\s*`?ADR-07`?\s*\|", l):
                lines[i] = "| ADR-07 | 随便什么文字 | x |\n"
                break
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_graph_drift():
    def f(files: dict[str, str]) -> dict[str, str]:
        files["PROJECT.md"] = files["PROJECT.md"].replace(
            "T1-02  ← T1-01", "T1-02  ← T9-99", 1)
        return files
    return f


def mutate_cycle():
    """让 T1-02 反向依赖 T1-03，与 T1-03 ← T1-01 形成环。"""
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        for i, l in enumerate(lines):
            if re.match(r"^\|\s*T1-02\s*\|", l) and "未开始" not in l:
                cells = l.rstrip("\n").split("|")
                cells[6] = " T1-04 "
                lines[i] = "|".join(cells) + "\n"
            if re.match(r"^\|\s*T1-04\s*\|", l) and "未开始" not in l:
                cells = l.rstrip("\n").split("|")
                cells[6] = " T1-02 "
                lines[i] = "|".join(cells) + "\n"
        files["PROJECT.md"] = "".join(lines)
        return files
    return f


def mutate_zero_definitions():
    def f(files: dict[str, str]) -> dict[str, str]:
        # 把所有 ADR 定义行的加粗去掉，模拟"格式变化导致解析为 0"
        files["PROJECT.md"] = re.sub(r"^\| \*\*(ADR-[0-9]+)\*\*", r"| \1", files["PROJECT.md"], flags=re.M)
        return files
    return f


def mutate_drop_whole_matrix_section():
    def f(files: dict[str, str]) -> dict[str, str]:
        lines = files["PROJECT.md"].splitlines(keepends=True)
        s = next(i for i, l in enumerate(lines) if l.startswith("### 6.7"))
        e = next(i for i, l in enumerate(lines) if l.startswith("## 7.") and i > s)
        files["PROJECT.md"] = "".join(lines[:s] + lines[e:])
        return files
    return f


CASES: list[tuple[str, str, callable]] = [
    ("B1", "删掉矩阵里的 S2 行", mutate_drop_matrix_row("S2")),
    ("B1", "删掉矩阵里的 S4 行", mutate_drop_matrix_row("S4")),
    ("B2", "删掉矩阵里的 D3 行", mutate_drop_matrix_row("D3")),
    ("B1", "删掉矩阵里的 RL-08 行", mutate_drop_matrix_row("RL-08")),
    ("B1", "删掉矩阵里的 C7 行", mutate_drop_matrix_row("C7")),
    ("B1", "删掉矩阵里的 ADR-05 行", mutate_drop_matrix_row("ADR-05")),
    ("B3", "把所有 ADR 定义去掉加粗（解析为 0）", mutate_zero_definitions()),
    ("B3", "整段删除 §6.7 覆盖矩阵", mutate_drop_whole_matrix_section()),
    ("B4", "往矩阵塞一个虚构键 ADR-99", mutate_fake_matrix_key()),
    ("B5", "把矩阵里 ADR-07 行复制一份（重复键）", mutate_dup_matrix_key()),
    ("B6", "把 C3 行改成「—」且说明留空", mutate_dash_without_note()),
    ("B7", "把 ADR-07 的强制点改成任意文字", mutate_bad_force_token()),
    ("C1", "把任务 T2-05 复制一份（重复 ID）", mutate_duplicate_task()),
    ("C3", "让 T2-09 依赖自身", mutate_self_dep()),
    ("C5", "把 §6.5 里的一条边改错（图漂移）", mutate_graph_drift()),
    ("C-CYCLE", "制造环 T1-02 ⇄ T1-04", mutate_cycle()),
    ("D1", "清空 T1-06 的依赖（孤立 T1 任务）", mutate_orphan_t1()),
    ("A5", "在 EVAL.md §6 塞一个不存在的任务 ID", mutate_eval_ghost()),
    ("E3", "把 TESTING.md M5 的任务映射改成不存在的 ID", mutate_testing_mapping()),
]


def main() -> int:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    src = {d: (base / d).read_text(encoding="utf-8") for d in DOCS}

    code, _ = run(base)
    print(f"[基线] 未变异时必须通过 … {'✅ 通过' if code == 0 else '❌ 基线就失败了'}")
    if code != 0:
        return 1

    failures: list[str] = []
    print(f"\n[变异测试] 共 {len(CASES)} 个用例，每个都必须让校验器返回非零\n")
    for item, desc, fn in CASES:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = fn(dict(src))
            for name, content in files.items():
                (root / name).write_text(content, encoding="utf-8")
            code, output = run(root)
            caught = code != 0
            mark = "✅ 已检出" if caught else "❌ 漏检"
            print(f"  {mark}  [{item}] {desc}")
            if not caught:
                failures.append(f"[{item}] {desc}")
            elif item not in output:
                # 检出了，但要确认是**预期的那项检查**报的
                print(f"        ⚠️  失败原因里未见 [{item}] 标记，实际输出首行："
                      f"{next((l for l in output.splitlines() if l.startswith('  ✗')), '(无)')}")

    print("\n" + "=" * 66)
    if failures:
        print(f"漏检 {len(failures)} 项 —— 这些检查是纸老虎：")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print(f"全部 {len(CASES)} 个变异均被检出 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
