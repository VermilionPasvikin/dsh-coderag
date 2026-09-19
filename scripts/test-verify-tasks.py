#!/usr/bin/env python3
# ruff: noqa: T201
"""`verify-tasks.py` 的**变异测试**——证明每项检查在坏数据上真的会失败。

一个只会说"通过"的校验器毫无价值。本脚本把当前 golden 集复制到临时目录，
逐个施加"人为破坏"，然后断言 `verify-tasks.py` **必须返回非零**，
且失败信息里出现**预期的那项检查编号**（不是随便什么错误都算数）。

用法:
    python3 scripts/test-verify-tasks.py [被评测仓库根目录]

`被评测仓库根目录` 默认 /Users/vermi/projects/dsh（T3-02a 的被评测仓库）。
退出码 0 表示全部变异都被检出；非 0 表示有检查是"纸老虎"。

其中 M07 / M09 直接复现了 T3-02a 实际发现并修正的两个缺陷
（前导 `/` 与 `types.t` 扩展名截断）。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
GOLDEN = REPO / "eval" / "tasks.jsonl"
SCHEMA = REPO / "eval" / "schema.json"
DEFAULT_CORPUS = Path("/Users/vermi/projects/dsh")

Task = dict[str, object]
Mutator = Callable[[list[Task]], str]


def load_tasks() -> list[Task]:
    """每个变异都从干净的 golden 集重新加载，避免变异之间互相污染。"""
    return [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def render(tasks: list[Task]) -> str:
    return "\n".join(json.dumps(t, ensure_ascii=False) for t in tasks) + "\n"


# ── 变异函数：每个返回要写盘的 tasks.jsonl 文本 ──────────────────────────
def m_drop_task(tasks: list[Task]) -> str:
    return render(tasks[:-1])


def m_empty_file(tasks: list[Task]) -> str:
    return ""


def m_break_json(tasks: list[Task]) -> str:
    lines = render(tasks).splitlines()
    lines[0] = lines[0] + " {"
    return "\n".join(lines) + "\n"


def m_blank_line(tasks: list[Task]) -> str:
    lines = render(tasks).splitlines()
    lines.insert(3, "")
    return "\n".join(lines) + "\n"


def m_bad_class(tasks: list[Task]) -> str:
    tasks[2]["class"] = "exactt"
    return render(tasks)


def m_duplicate_id(tasks: list[Task]) -> str:
    tasks[1]["id"] = tasks[0]["id"]
    return render(tasks)


def m_leading_slash(tasks: list[Task]) -> str:
    """T3-02a 实际缺陷 1：expect_paths 写成绝对路径。"""
    paths = tasks[1]["expect_paths"]
    assert isinstance(paths, list)
    paths[0] = "/" + str(paths[0])
    return render(tasks)


def m_missing_file(tasks: list[Task]) -> str:
    tasks[0]["expect_paths"] = ["packages/does/not/exist.ts"]
    return render(tasks)


def m_truncated_extension(tasks: list[Task]) -> str:
    """T3-02a 实际缺陷 2：`types.ts` 被截断成 `types.t`。"""
    tasks[6]["expect_paths"] = ["packages/core/session/src/types.t"]
    return render(tasks)


def m_leak_path_in_query(tasks: list[Task]) -> str:
    tasks[1]["query"] = "error.ts 定义在哪？"
    return render(tasks)


def m_fake_exact_identifier(tasks: list[Task]) -> str:
    tasks[0]["query"] = "NOT_A_REAL_SYMBOL_ANYWHERE"
    return render(tasks)


def m_natural_with_identifier(tasks: list[Task]) -> str:
    """把 natural 题写成含目标代码标识符的 exact 题。"""
    tasks[8]["query"] = "DEFAULT_MAX_RETRIES 是什么"
    return render(tasks)


def m_wrong_ratio(tasks: list[Task]) -> str:
    for task in tasks[4:8]:
        task["class"] = "exact"
    return render(tasks)


MUTATIONS: list[tuple[str, str, Mutator]] = [
    ("M01", "V10", m_drop_task),
    ("M02", "V1", m_empty_file),
    ("M03", "V1", m_break_json),
    ("M04", "V1", m_blank_line),
    ("M05", "V2", m_bad_class),
    ("M06", "V3", m_duplicate_id),
    ("M07", "V4", m_leading_slash),
    ("M08", "V5", m_missing_file),
    ("M09", "V5", m_truncated_extension),
    ("M10", "V6", m_leak_path_in_query),
    ("M11", "V7", m_fake_exact_identifier),
    ("M12", "V8", m_natural_with_identifier),
    ("M13", "V9", m_wrong_ratio),
]


def run_verifier(tasks_text: str, corpus: Path) -> tuple[int, str]:
    """在临时目录里写一份 tasks.jsonl + schema.json，跑一次校验器。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "tasks.jsonl").write_text(tasks_text, encoding="utf-8")
        shutil.copyfile(SCHEMA, tmp_path / "schema.json")
        proc = subprocess.run(
            [sys.executable, str(HERE / "verify-tasks.py"),
             str(tmp_path / "tasks.jsonl"), str(corpus)],
            capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr


def main(argv: list[str]) -> int:
    corpus = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_CORPUS
    print("== test-verify-tasks ==")
    print(f"corpus: {corpus}")
    if not corpus.is_dir():
        print(f"FAIL: 被评测仓库不存在：{corpus}")
        return 1
    if not GOLDEN.is_file() or not SCHEMA.is_file():
        print("FAIL: 缺少 eval/tasks.jsonl 或 eval/schema.json")
        return 1

    failures = 0
    code, out = run_verifier(GOLDEN.read_text(encoding="utf-8"), corpus)
    baseline_ok = code == 0 and "PASS:" in out
    print(f"[BASE] 未变异的 golden 集必须通过 ................ "
          f"{'PASS' if baseline_ok else 'FAIL'}")
    if not baseline_ok:
        failures += 1
        print(out)

    for name, expected, mutator in MUTATIONS:
        tasks = load_tasks()
        try:
            text = mutator(tasks)
        except (KeyError, IndexError, AssertionError) as exc:
            print(f"[{name}] 变异本身构造失败：{exc!r}")
            failures += 1
            continue
        code, out = run_verifier(text, corpus)
        detected = code != 0 and f"[{expected}]" in out
        status = "PASS" if detected else "FAIL"
        print(f"[{name}] 期望检出 {expected:<3} ......................... {status}")
        if not detected:
            failures += 1
            print(f"  rc={code}")
            print("  " + out.replace("\n", "\n  "))

    print()
    if failures:
        print(f"FAIL: {failures} 个变异未被正确检出")
        return 1
    print(f"PASS: 基线通过，{len(MUTATIONS)} 个变异全部被预期检查检出")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
