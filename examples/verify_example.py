#!/usr/bin/env python3
"""校验评测集文件——这是 `EVAL.md` §2.4 Step 5「机器校验」的参考实现。

用法:
    python examples/verify_example.py examples/eval-tasks.EXAMPLE.jsonl <被评测仓库根目录>

它会检查四件事，任何一条不通过都会让退出码非零：
  1. schema：必填字段、类型、id 唯一、class 取值合法
  2. 路径存在性：每个 expect_paths 里的路径在目标仓库里真实存在
  3. 答案泄漏：crossfile / natural 类的 query 不得包含 expect_paths 的路径片段或符号名
  4. 配比：三类任务的分布（仅提示，不作为失败条件）
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REQUIRED = {"id", "class", "query", "expect_paths", "added"}
CLASSES = {"exact", "crossfile", "natural"}
# 期望配比（EVAL.md §2.3）：12 / 11 / 7，按比例换算成占比
EXPECTED_RATIO = {"exact": 0.40, "crossfile": 0.37, "natural": 0.23}


def load(path: Path) -> list[dict]:
    tasks = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            tasks.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            fail(f"{path.name}:{lineno} 不是合法 JSON：{exc}")
    return tasks


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")
    FAILURES.append(msg)


FAILURES: list[str] = []


def check_schema(tasks: list[dict], seen_ids: set[str]) -> None:
    print("\n[1/4] schema 校验")
    for i, t in enumerate(tasks, 1):
        missing = REQUIRED - t.keys()
        if missing:
            fail(f"第 {i} 条缺字段 {sorted(missing)}")
            continue
        if t["class"] not in CLASSES:
            fail(f"{t['id']} 的 class={t['class']!r} 非法，应为 {sorted(CLASSES)}")
        if t["id"] in seen_ids:
            fail(f"{t['id']} 重复")
        seen_ids.add(t["id"])
        if not t["expect_paths"]:
            fail(f"{t['id']} 的 expect_paths 为空")
    print(f"  共 {len(tasks)} 条，id 唯一：{len(seen_ids) == len(tasks)}")


def check_paths(tasks: list[dict], repo: Path) -> None:
    print(f"\n[2/4] 路径存在性（目标仓库：{repo}）")
    for t in tasks:
        for rel in t["expect_paths"]:
            if not (repo / rel).exists():
                fail(f"{t['id']} 的 expect_paths 不存在：{rel}")
    print(f"  已检查 {sum(len(t['expect_paths']) for t in tasks)} 条路径")


def check_leakage(tasks: list[dict]) -> None:
    """crossfile / natural 的 query 不得含答案的路径片段或符号名。

    exact 类**故意**包含标识符，因此豁免。
    """
    print("\n[3/4] 答案泄漏检查（crossfile / natural 豁免 exact）")
    for t in tasks:
        if t["class"] == "exact":
            continue
        q = t["query"]
        for rel in t["expect_paths"]:
            # 路径的最后一段（文件名，去扩展名）不得出现在 query 里
            stem = Path(rel).stem
            if stem and stem.lower() in q.lower():
                fail(f"{t['id']} 的 query 出现了答案文件名 {stem!r}")
            # 完整路径片段（2 段以上）不得出现
            parts = Path(rel).parts
            for n in range(2, len(parts) + 1):
                frag = "/".join(parts[:n])
                if frag.lower() in q.lower():
                    fail(f"{t['id']} 的 query 出现了路径片段 {frag!r}")
        for sym in t.get("expect_symbols", []):
            if sym and sym.lower() in q.lower():
                fail(f"{t['id']} 的 query 出现了符号名 {sym!r}")
    print("  完成")


def check_ratio(tasks: list[dict]) -> None:
    print("\n[4/4] 配比（仅提示，不判失败）")
    c = Counter(t["class"] for t in tasks)
    n = len(tasks)
    for cls in ("exact", "crossfile", "natural"):
        actual = c[cls] / n if n else 0
        want = EXPECTED_RATIO[cls]
        flag = "✅" if abs(actual - want) <= 0.12 else "⚠️ "
        print(f"  {flag} {cls:<10} {c[cls]:>2}/{n} = {actual:.0%}  （目标 {want:.0%}）")
    if n < 25:
        print(f"  ⚠️  只有 {n} 条 —— 够跑通链路，但不够支撑统计结论（EVAL.md §2.6 建议 25–50）")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    tasks_path, repo = Path(sys.argv[1]), Path(sys.argv[2])
    if not tasks_path.is_file():
        print(f"找不到评测集文件：{tasks_path}")
        return 2
    if not repo.is_dir():
        print(f"找不到目标仓库目录：{repo}")
        return 2

    print(f"评测集：{tasks_path}")
    tasks = load(tasks_path)
    check_schema(tasks, set())
    check_paths(tasks, repo)
    check_leakage(tasks)
    check_ratio(tasks)

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("全部检查通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
