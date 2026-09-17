#!/usr/bin/env python3
"""校验 dsh-coderag 计划完备性（v2 —— 按《工程完备性检查缺陷清单》逐项实现）。

用法:
    python3 scripts/verify-plan.py .                # 全量校验
    python3 scripts/verify-plan.py . --emit-graph   # 只输出 §6.5 依赖图正文（用于重新生成）

设计原则（对应清单 F 组）：
  * **不静默通过**：关键解析结果为 0 或低于下限 → 失败，而不是打印 "0 条 ✅"
  * **不静默覆盖**：重复定义 → 失败并报行号，而不是被字典覆盖
  * **不静默跳过**：文档声明的每一组（S*/D* 等）都必须被校验
  * **报告实际数量**：每项检查打印"解析到 N 个 X"，让"未执行"无法伪装成"通过"

每项检查前的 [A1] 等编号对应缺陷清单的条目。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── 下限阈值（F4）：低于此值说明**解析失败**，不是"文档恰好很少" ────────────
MIN_TASKS = 50
MIN_ADR = 13
MIN_C = 12
MIN_RL = 11
MIN_S = 4
MIN_D = 5
MIN_MATRIX = 45
MIN_TEST_ITEMS = 10
MIN_TEST_REQS = 8

ROOT_TASK = "T1-01"

TASK_ROW = re.compile(r"^\|\s*[`*]*\s*(T[0-9]-[0-9]+[a-z]?)\s*[`*]*\s*\|")
ANY_TASK_ID = re.compile(r"\bT[0-9]-[0-9]+[a-z]?\b")
ADR_DEF = re.compile(r"^\|\s*\*\*(ADR-[0-9]+)\*\*")
C_DEF = re.compile(r"^\|\s*(C[0-9]+)\s*\|")
RL_DEF = re.compile(r"^\|\s*\*\*(RL-[0-9]+)\*\*")
S_DEF = re.compile(r"^\|\s*\*\*(S[0-9])\*\*")
D_DEF = re.compile(r"^\|\s*\*\*(D[0-9])\*\*")
MATRIX_ROW = re.compile(r"^\|\s*`?([A-Za-z][A-Za-z0-9-]*)`?\s*\|([^|]*)\|([^|]*)\|")
MUSTTEST_ROW = re.compile(r"^\|\s*\*\*(M[0-9]+)\*\*\s*\|")
TESTREQ_ROW = re.compile(r"^\|\s*\*\*(T-[0-9]+)\*\*")

FAIL: list[str] = []
CHECKS: list[tuple[str, str, str]] = []


def fail(item: str, msg: str) -> None:
    FAIL.append(f"[{item}] {msg}")


def ok(item: str, msg: str) -> None:
    CHECKS.append((item, "PASS", msg))


def bad(item: str, msg: str) -> None:
    CHECKS.append((item, "FAIL", msg))


def section(lines: list[str], start: str, ends: tuple[str, ...]) -> list[str]:
    out, on = [], False
    for line in lines:
        if not on:
            if start in line:
                on = True
            continue
        if any(e in line for e in ends):
            break
        out.append(line)
    return out


# ══ A. EVAL.md 漂移 ═══════════════════════════════════════════════════
def check_eval_drift(ev_lines: list[str], tasks: dict[str, dict]) -> set[str]:
    body = section(ev_lines, "## 6. 修订记录", ("## 7.", "## 8."))
    if not body:
        fail("A1", "EVAL.md §6 截取失败（期望标题以 `## 6. 修订记录` 开头）")
        bad("A1", "§6 未截取到正文")
        return set()
    ok("A1", f"§6 正文截取到 {len(body)} 行")

    text = "\n".join(body)
    ids = set(ANY_TASK_ID.findall(text))
    ok("A2", f"从 §6 描述性文本中提取到 {len(ids)} 个任务 ID")

    if ANY_TASK_ID.search(text) and not ids:
        fail("A3", "§6 出现了任务 ID 文本但解析为 0 —— 格式不匹配")
        bad("A3", "解析失败被当成空集")
    else:
        ok("A3", "解析结果与正文是否含 ID 一致（未把解析失败当空集）")

    if "不定义任务" not in text and "唯一地定义在" not in text:
        fail("A4", "§6 未声明「不定义任务 / 唯一地定义在 PROJECT.md」")
        bad("A4", "权威版本声明缺失")
    else:
        ok("A4", "§6 已声明不定义任务（权威版本 = PROJECT.md §6.3）")

    ghost = sorted(i for i in ids if i not in tasks)
    if ghost:
        fail("A5", f"§6 引用了 PROJECT.md 中不存在的任务：{ghost}")
        bad("A5", f"{len(ghost)} 个孤立 ID")
    else:
        ok("A5", f"{len(ids)} 个被引用 ID 全部存在")

    declared_new = {"T3-00", "T3-02a", "T3-02b", "T3-04b", "T3-04c", "T3-04d"}
    if declared_new & ids:
        missing = sorted(n for n in declared_new if n not in tasks)
        if missing:
            fail("A6", f"§6 声明新增但任务表里没有：{missing}")
            bad("A6", f"合并声明与实际不符：{missing}")
        else:
            ok("A6", f"§6 声明的 {len(declared_new)} 个新增任务全部已在任务表")
    else:
        ok("A6", "§6 未声明新增任务，跳过合并校验")
    return ids


# ══ B. 覆盖矩阵 ═══════════════════════════════════════════════════════
def parse_matrix(proj_lines: list[str]) -> dict[str, tuple[str, str, int]]:
    start = next((i for i, l in enumerate(proj_lines) if l.startswith("### 6.7")), None)
    if start is None:
        return {}
    matrix: dict[str, tuple[str, str, int]] = {}
    for i in range(start + 1, len(proj_lines)):
        line = proj_lines[i]
        if line.startswith("### 6.8") or line.startswith("## 7."):
            break
        m = MATRIX_ROW.match(line)
        if not m:
            continue
        key, force, note = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        if key == "定义" or set(key) <= set("- "):
            continue
        lineno = i + 1
        if key in matrix:
            fail("B5", f"矩阵重复键 {key}（行 {matrix[key][2]} 与行 {lineno}）")
        matrix[key] = (force, note, lineno)
    return matrix


def check_matrix(proj_lines: list[str], agents_lines: list[str], tasks: dict[str, dict],
                 matrix: dict[str, tuple[str, str, int]]) -> None:
    if not matrix:
        fail("B3", "§6.7 覆盖矩阵解析为空（标题应为 `### 6.7`）")
        bad("B3", "矩阵为空")
        return
    if len(matrix) < MIN_MATRIX:
        fail("F4", f"矩阵只有 {len(matrix)} 行，低于下限 {MIN_MATRIX}")
        bad("F4", f"矩阵 {len(matrix)} < {MIN_MATRIX}")
    else:
        ok("F4", f"矩阵 {len(matrix)} 行 ≥ 下限 {MIN_MATRIX}")

    proj_c = section(proj_lines, "## 2. 技术选型依据", ("## 3. 架构设计",))
    src = {
        "ADR": [m.group(1) for m in (ADR_DEF.match(l) for l in proj_lines) if m],
        "C": [m.group(1) for m in (C_DEF.match(l) for l in proj_c) if m],
        "RL": [m.group(1) for m in (RL_DEF.match(l) for l in agents_lines) if m],
        "S": [m.group(1) for m in (S_DEF.match(l) for l in proj_lines) if m],
        "D": [m.group(1) for m in (D_DEF.match(l) for l in proj_lines) if m],
    }
    mins = {"ADR": MIN_ADR, "C": MIN_C, "RL": MIN_RL, "S": MIN_S, "D": MIN_D}
    for kind, ids in src.items():
        if len(ids) < mins[kind]:
            fail("B3", f"{kind} 只解析到 {len(ids)} 条，低于下限 {mins[kind]} —— 解析失败或文档缺定义")
            bad("B3", f"{kind} 数量异常({len(ids)})")
        elif len(ids) != len(set(ids)):
            dup = sorted({x for x in ids if ids.count(x) > 1})
            fail("B3", f"{kind} 定义自身重复：{dup}")

    for item, kind, label in (("B1", "ADR", "ADR"), ("B1", "C", "约束 C*"), ("B1", "RL", "红线 RL-*"),
                              ("B1", "S", "成功标准 S*"), ("B2", "D", "交付物 D*")):
        missing = [i for i in src[kind] if i not in matrix]
        if missing:
            fail(item, f"{label} 有 {len(missing)} 条不在覆盖矩阵里：{missing}")
            bad(item, f"{label} 缺 {len(missing)} 条")
        else:
            ok(item, f"{label}: {len(src[kind])} 条全部在矩阵里")

    valid = {i for ids in src.values() for i in ids}
    ghosts = sorted(k for k in matrix if k not in valid)
    if ghosts:
        fail("B4", f"矩阵有 {len(ghosts)} 个键不对应真实定义：{ghosts}")
        bad("B4", f"{len(ghosts)} 个虚构键")
    else:
        ok("B4", f"{len(matrix)} 个矩阵键全部对应真实定义")

    tid_re = re.compile(r"\bT[0-9]-[0-9]+[a-z]?\b")
    for key, (force, note, lineno) in sorted(matrix.items()):
        f = force.strip().strip("`*").strip()
        if f in ("—", "-", ""):
            if len(note) < 8:
                fail("B6", f"{key}（行 {lineno}）标为「—」但说明过短/为空：{note!r}")
            continue
        if "全局" in f:
            for tid in tid_re.findall(force):
                if tid not in tasks:
                    fail("B8", f"{key}（行 {lineno}）标为全局但引用了不存在的任务 {tid}")
            continue
        toks = [t for t in re.split(r"[,\s、]+", f) if t]
        if not toks:
            fail("B7", f"{key}（行 {lineno}）强制点为空")
            continue
        for t in toks:
            if not re.fullmatch(r"T[0-9]-[0-9]+[a-z]?", t):
                fail("B7", f"{key}（行 {lineno}）强制点含非法记号 {t!r}；只允许任务 ID / *全局* / —")
            elif t not in tasks:
                fail("C-DEP", f"{key}（行 {lineno}）引用了不存在的任务 {t}")
    ok("B6", "「—」行的说明长度已校验")
    ok("B7", "强制点单元格格式已校验（任务 ID / *全局* / —）")
    ok("B8", "「全局」行未混入非法任务 ID")


# ══ C. 任务 ID 与依赖 ═════════════════════════════════════════════════
def parse_tasks(proj_lines: list[str]) -> dict[str, dict]:
    body = section(proj_lines, "## 6. 工作计划", ("### 6.5", "### 6.6", "## 7."))
    tasks: dict[str, dict] = {}
    lineno_of: dict[int, int] = {}
    for i, l in enumerate(proj_lines):
        lineno_of[id(l)] = i + 1
    for raw in body:
        m = TASK_ROW.match(raw)
        if not m:
            continue
        tid = m.group(1)
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        cell = cells[5] if len(cells) >= 6 else ""
        lineno = lineno_of.get(id(raw), -1)
        if tid in tasks:
            fail("C1", f"任务 {tid} 重复定义（行 {tasks[tid]['line']} 与行 {lineno}）—— 覆盖会隐藏错误依赖")
            bad("C1", f"{tid} 重复")
            continue          # C2：保留**首次**定义，不用后出现的覆盖它
        raw_deps = ANY_TASK_ID.findall(cell)
        if tid in raw_deps:
            fail("C3", f"任务 {tid}（行 {lineno}）依赖自身")
            bad("C3", f"{tid} 自依赖")
        if not raw_deps and cell and not re.fullmatch(r"[\s—\-|]*", cell):
            fail("C4", f"任务 {tid}（行 {lineno}）的依赖单元格无法解析：{cell!r}")
            bad("C4", f"{tid} 依赖格式异常")
        tasks[tid] = {"deps": [d for d in raw_deps if d != tid], "line": lineno, "raw": raw}
    return tasks


def check_task_graph(tasks: dict[str, dict]) -> None:
    if len(tasks) < MIN_TASKS:
        fail("F4", f"只解析到 {len(tasks)} 个任务，低于下限 {MIN_TASKS} —— 疑似解析失败")
        bad("F4", f"任务数 {len(tasks)} < {MIN_TASKS}")
    else:
        ok("F4", f"任务数 {len(tasks)} ≥ 下限 {MIN_TASKS}")

    dangling = [(t, d) for t, v in tasks.items() for d in v["deps"] if d not in tasks]
    for t, d in dangling:
        fail("C-DEP", f"{t} 依赖的 {d} 不存在")
    if dangling:
        bad("C-DEP", f"{len(dangling)} 条悬空依赖")
    else:
        ok("C-DEP", f"{len(tasks)} 个任务 / {sum(len(v['deps']) for v in tasks.values())} 条依赖边，引用全部有效")

    color = dict.fromkeys(tasks, 0)
    path: list[str] = []

    def dfs(n: str) -> bool:
        color[n] = 1
        path.append(n)
        for d in tasks[n]["deps"]:
            if d not in color:
                continue
            if color[d] == 1:
                fail("C-CYCLE", f"依赖环：{' -> '.join(path[path.index(d):] + [d])}")
                return True
            if color[d] == 0 and dfs(d):
                return True
        path.pop()
        color[n] = 2
        return False

    if any(dfs(t) for t in sorted(tasks) if color[t] == 0):
        bad("C-CYCLE", "存在依赖环")
    else:
        ok("C-CYCLE", "依赖图无环")


# ══ D. 图根 ═══════════════════════════════════════════════════════════
def check_root(tasks: dict[str, dict]) -> None:
    if ROOT_TASK not in tasks:
        fail("D3", f"根任务 {ROOT_TASK} 不存在")
        bad("D3", "无根")
        return
    if tasks[ROOT_TASK]["deps"]:
        fail("D3", f"根任务 {ROOT_TASK} 不应有依赖，实际为 {tasks[ROOT_TASK]['deps']}")

    def reaches_root(n: str, seen: set[str]) -> bool:
        if n == ROOT_TASK:
            return True
        if n in seen:
            return False
        seen.add(n)
        return any(reaches_root(d, seen) for d in tasks[n]["deps"] if d in tasks)

    unreachable = [t for t in sorted(tasks) if not reaches_root(t, set())]
    if unreachable:
        for t in unreachable:
            fail("D1", f"{t} 无法沿依赖边追溯到根 {ROOT_TASK}（悬空孤岛）")
        bad("D2", f"{len(unreachable)} 个任务到不了根")
    else:
        ok("D3", f"根 = {ROOT_TASK}（无依赖）；{len(tasks)}/{len(tasks)} 个任务可达根")
        ok("D1", "连通性以 T1-01 为唯一根（不再把任意 T1-* 当根）")
        ok("D2", "孤立 T1 任务会被检出")


def emit_graph(tasks: dict[str, dict]) -> str:
    def sortkey(x: str) -> tuple:
        mm = re.match(r"T([0-9])-([0-9]+)([a-z]?)", x)
        return (int(mm.group(1)), int(mm.group(2)), mm.group(3))

    out = ["# 由 scripts/verify-plan.py --emit-graph 从任务表「依赖」列生成。请勿手改。", ""]
    for tid in sorted(tasks, key=sortkey):
        deps = tasks[tid]["deps"]
        if tid == ROOT_TASK:
            out.append(f"{tid}  (根，无依赖)")
        elif deps:
            out.append(f"{tid}  ← {', '.join(sorted(deps, key=sortkey))}")
        else:
            out.append(f"{tid}  ← (无硬阻塞)")
    return "\n".join(out)


def check_graph_sync(proj_lines: list[str], tasks: dict[str, dict]) -> None:
    body = section(proj_lines, "### 6.5", ("### 6.6",))
    if not body:
        fail("C5", "§6.5 任务依赖图未找到")
        bad("C5", "§6.5 缺失")
        return
    actual_lines = [l.rstrip() for l in body
                    if (l.startswith("T") or l.startswith("# 由 scripts/")) and l.strip()]
    actual = "\n".join(actual_lines).strip()
    expected = "\n".join(l for l in emit_graph(tasks).splitlines() if l.strip()).strip()
    if actual != expected:
        bad("C5", "§6.5 与任务表不一致")
        fail("C5", "§6.5 依赖图已过期 —— 运行 `python3 scripts/verify-plan.py . --emit-graph` 覆盖")
        for a, e in zip(actual.splitlines(), expected.splitlines()):
            if a != e:
                fail("C5", f"  首个差异：图 `{a}`  vs  表 `{e}`")
                break
    else:
        ok("C5", f"§6.5 与任务表逐行一致（{len(tasks)} 行）")


# ══ E. TESTING.md ═════════════════════════════════════════════════════
def check_testing(test_lines: list[str], agents_lines: list[str], tasks: dict[str, dict]) -> None:
    if not test_lines:
        fail("E1", "TESTING.md 读取失败或为空")
        bad("E1", "TESTING.md 未读取")
        return
    ok("E1", f"TESTING.md 读取到 {len(test_lines)} 行")

    body = section(test_lines, "## 2. 必测清单", ("## 3.",))
    rows: dict[str, list[str]] = {}
    for line in body:
        m = MUSTTEST_ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows[m.group(1)] = ANY_TASK_ID.findall(cells[-1]) if cells else []
    if len(rows) < MIN_TEST_ITEMS:
        fail("E2", f"必测清单只解析到 {len(rows)} 项，低于下限 {MIN_TEST_ITEMS}")
        bad("E2", f"必测项 {len(rows)} < {MIN_TEST_ITEMS}")
    else:
        ok("E2", f"必测清单 {len(rows)} 项：{', '.join(sorted(rows, key=lambda s: int(s[1:])))}")

    no_ref = sorted(k for k, v in rows.items() if not v)
    if no_ref:
        fail("E2", f"这些必测项没有「对应任务」：{no_ref}")
    used = {t for v in rows.values() for t in v}
    ghost = sorted(t for t in used if t not in tasks)
    if ghost:
        fail("E3", f"必测清单引用了不存在的任务：{ghost}")
        bad("E3", f"{len(ghost)} 个孤立引用")
    else:
        ok("E3", f"必测清单引用的 {len(used)} 个任务全部存在")

    body2 = section(agents_lines, "### 5.2 测试要求", ("### 5.3", "## 6."))
    reqs = [m.group(1) for m in (TESTREQ_ROW.match(l) for l in body2) if m]
    if len(reqs) < MIN_TEST_REQS:
        fail("E4", f"AGENTS.md §5.2 只解析到 {len(reqs)} 条测试要求，期望 ≥ {MIN_TEST_REQS}")
        bad("E4", f"测试要求 {len(reqs)}")
    else:
        ok("E4", f"AGENTS.md §5.2 测试要求 {len(reqs)} 条：{', '.join(reqs)}")
    if not any("L3" in l for l in body):
        fail("E4", "必测清单没有 L3（端到端）项")
    else:
        ok("E4", "必测清单覆盖 L3 端到端层")


# ══ main ══════════════════════════════════════════════════════════════
def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    root = Path(args[0] if args else ".")
    P = {k: root / v for k, v in (("proj", "PROJECT.md"), ("agents", "AGENTS.md"),
                                  ("ev", "EVAL.md"), ("test", "TESTING.md"))}
    for p in P.values():
        if not p.is_file():
            print(f"找不到 {p}")
            return 2

    proj_lines = P["proj"].read_text(encoding="utf-8").splitlines()
    agents_lines = P["agents"].read_text(encoding="utf-8").splitlines()
    ev_lines = P["ev"].read_text(encoding="utf-8").splitlines()
    test_lines = P["test"].read_text(encoding="utf-8").splitlines()

    tasks = parse_tasks(proj_lines)
    if "--emit-graph" in flags:
        print(emit_graph(tasks))
        return 0

    print(f"校验计划完备性：{root.resolve()}")
    print(f"  读取行数  PROJECT.md={len(proj_lines)}  AGENTS.md={len(agents_lines)}  "
          f"EVAL.md={len(ev_lines)}  TESTING.md={len(test_lines)}")
    print(f"  解析结果  任务={len(tasks)}")

    check_eval_drift(ev_lines, tasks)
    check_task_graph(tasks)
    check_root(tasks)
    check_graph_sync(proj_lines, tasks)
    matrix = parse_matrix(proj_lines)
    check_matrix(proj_lines, agents_lines, tasks, matrix)
    check_testing(test_lines, agents_lines, tasks)

    print("\n" + "─" * 70)
    for item, status, msg in CHECKS:
        print(f"  {'✅' if status == 'PASS' else '❌'} [{item}] {msg}")
    print("─" * 70)

    if FAIL:
        print(f"\n失败 {len(FAIL)} 项：")
        for f in FAIL:
            print(f"  ✗ {f}")
        return 1
    n_pass = sum(1 for _, s, _ in CHECKS if s == "PASS")
    print(f"\n计划完备性：通过 ✅   （{n_pass} 项检查全部实际执行，无空过）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
