# M6 macOS 复核（`T6-03b`）

> **定位**：这份报告是 M6 的 **macOS 集中复核载体**（2026-09-30 裁决：M6 的 macOS 复核集中做一次，
> `T6-04` 的 macOS 栏与 `T6-05` 的平台表述都引用本文）。它记录**在本机 macOS 上实际跑出来的原始输出**，
> 并与 `T6-03a` 的 Windows 读数并列。
> 观测日期 **2026-09-30**；被复核的提交 `0293398` 加上本任务的两处修复（见 §5）。
>
> **本文不放宽任何既有判据**：`T6-03b` 要求 macOS 全量通过、无 xfail——这一点无条件成立，
> 见 §3；本文同时如实记录一次**先行失败**及其根因（§4）。

---

## 1. 结论

| 检查 | macOS（本文实测） | Windows（`T6-03a` 的读数） |
|---|---|---|
| 全量 `pytest` | **567 passed, 5 skipped**（**0 failed / 0 xfail**） | 568 passed, 2 skipped（0 failed / 0 xfail） |
| `ruff check src tests` | `All checks passed!` | `All checks passed!` |
| `mypy --strict src/` | `Success: no issues found in 26 source files` | 同 |
| `python3 scripts/verify-plan.py .` | `计划完备性：通过 ✅`（28 项检查，退出码 0） | 同 |
| 端到端冒烟（`T6-04` 的 macOS 栏） | **通过**：插件登记成功、`code_search` 命中 `src/auth/token.py` | 通过 |

**macOS 侧结论：同一份代码在 macOS 上零退化**——`T6-03a` 修好的路径规范化与 extra 声明在 macOS 上同样成立，
没有任何一条 Windows 侧的修复以 macOS 为代价。

**两处数字差异都已逐条查清**（不是"差不多就行"，见 §3.2 与 §4），且**没有为对齐数字改过任何断言**。

---

## 2. 环境

| 项 | 值 |
|---|---|
| OS | macOS **26.4** |
| 解释器（测试与 MCP 子进程） | `/opt/anaconda3/envs/forBSH/bin/python`（**Python 3.10.21**） |
| `numpy`（可选 extra `semantic`） | **2.2.6**（已装，满足 `ADR-16` §3.2 的 `numpy>=1.26`） |
| 包装脚本的 `dsh` 后端 | `./scripts/dsh` → 全局 `dsh`，钉 **0.1.5-rc.1** |
| Node / pnpm | `v24.14.0` / `12.4.2` |
| 被复核的提交 | `0293398`（Windows 侧推送的 HEAD）+ 本任务的修复 |
| 冒烟用的全新 `DSH_HOME` | `/tmp/dsh-m6-t603b/dshhome`（**跑之前不存在**） |
| 冒烟用的全新 profile | `m6mac` |
| demo 工作区干净副本 | `/tmp/dsh-m6-t603b/demo-ws`（4 个被跟踪文件，**无 `.coderag/`**） |

> **副本为什么不是 `cp -R`**：`examples/demo-workspace/.coderag/index.sqlite3` 是一份**被 `.gitignore` 排除**
> 的历史索引产物（来自 `T1-15`），`cp -R` 会把它带进"干净副本"。改用
> `git archive HEAD examples/demo-workspace` 导出**被跟踪**的 4 个文件，确保副本里没有索引。

---

## 3. macOS 全量测试

### 3.1 原始输出

```
$ /opt/anaconda3/envs/forBSH/bin/python -m pytest -rs
........................................................................ [ 12%]
........................................................................ [ 25%]
........................................................................ [ 37%]
........................................................................ [ 50%]
........................................................................ [ 62%]
........................................................................ [ 75%]
........................................................................ [ 87%]
........................................................................ [100%]
=========================== short test summary info ===========================
SKIPPED [1] tests/test_cases.py:95: set CODERAG_L2_CORPUS to the prepared DSH copy
SKIPPED [1] tests/test_eval.py:347: set CODERAG_EVAL_CORPUS to an indexed DSH copy to replay the golden set
SKIPPED [3] tests/test_path_filter.py:72: backslash separators only resolve as path separators on Windows
567 passed, 5 skipped in 11.23s
```

其余门禁：

```
$ /opt/anaconda3/envs/forBSH/bin/python -m ruff check src tests
All checks passed!

$ /opt/anaconda3/envs/forBSH/bin/python -m mypy --strict src/
Success: no issues found in 26 source files

$ python3 scripts/verify-plan.py .
计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）
```

### 3.2 5 条 skip 逐条归因（**全部与平台约定或 opt-in 语料有关，没有一条是隐藏的失败**）

| skip | 条数 | 原因 | Windows 侧 |
|---|---|---|---|
| `tests/test_path_filter.py:72` | **3** | `skipif(sys.platform != "win32")`——反斜杠只在 Windows 上是路径分隔符 | **不跳过**（这就是 Windows 比 macOS 多跑的 3 条） |
| `tests/test_cases.py:95` | 1 | `CODERAG_L2_CORPUS` 未设（L2 语料 opt-in） | 同样跳过 |
| `tests/test_eval.py:347` | 1 | `CODERAG_EVAL_CORPUS` 未设（金标集回放 opt-in） | 同样跳过 |

**关于"预期 565 passed / 5 skipped"**：本次实测是 **567 passed / 5 skipped**，比预期**多 2 条通过**，
原因已定位——本任务在 `tests/test_dsh_script.py` 新增了 **2 条**用例（见 §4.2），
`tests/test_dsh_script.py` 由 5 条变 **7** 条。`5 skipped` 与预期一致。
**没有为了让数字落回 565 而删测试或改断言**（`T-08`）。

### 3.3 对照实验：把 `bash` 从 `PATH` 里去掉（复现 Windows 的 `PATH` 条件）

`T6-01` 的基线记录 Windows 上 `sh` / `bash` **都不在 `PATH`**，而 `tests/test_dsh_script.py` 与
`tests/test_install_script.py` 都以 `shutil.which("bash")` 为整文件守卫。为确认这些守卫**只**影响可用性、
不影响结论，在 macOS 上做了一次对照：

```
$ env -i PATH=/nonexistent HOME="$HOME" PYTHONPATH="$PWD/src" /opt/anaconda3/envs/forBSH/bin/python -m pytest -rs
SKIPPED [6] tests/test_install_script.py: bash is required to run install.sh
SKIPPED [7] tests/test_dsh_script.py: bash is required to run scripts/dsh
SKIPPED [3] tests/test_path_filter.py:72: backslash separators only resolve as path separators on Windows
SKIPPED [2] 语料 opt-in（test_cases.py / test_eval.py）
552 passed, 20 skipped
```

即：**13 条 shell 包装用例 + 3 条 Windows 专用 + 2 条 opt-in = 18 条**会因环境而跳过，**其余全部通过**。
这说明两个 `*.sh` 包装的用例是"平台可用性门控"，不是平台正确性问题。

---

## 4. 先行失败与根因（**本文最重要的部分**）

首次在 macOS 上跑全量套件时是 **`1 failed, 564 passed, 5 skipped`**，失败的是
`tests/test_dsh_script.py::test_dsh_script_does_not_export_an_unusable_interpreter`。
按 `AGENTS.md` §9 与用户指示（"数字对不上就逐条查清，不要为对齐数字而改断言"），逐项取证如下。

### 4.1 三层根因

**① 测试没有隔离 `CONDA_PREFIX`（测试缺陷）**

`run_dsh` 只清掉了 `CODERAG_*` 前缀的变量，**没有清 `CONDA_PREFIX`**。于是包装脚本走了
`${CONDA_PREFIX}/bin/python` 分支，导出的是**本机真实、可用**的 `/opt/anaconda3/bin/python`（3.13.5），
而用例断言的是 `CODERAG_PYTHON=unset`。

决定性证据（同一份代码，只改环境）：

```
$ /opt/anaconda3/envs/forBSH/bin/python -m pytest tests/test_dsh_script.py::test_dsh_script_does_not_export_an_unusable_interpreter -q
FAILED（导出的值是 /opt/anaconda3/bin/python）

$ env -u CONDA_PREFIX /opt/anaconda3/envs/forBSH/bin/python -m pytest tests/test_dsh_script.py::test_dsh_script_does_not_export_an_unusable_interpreter -q
.                                                                        [100%]
1 passed
```

也就是说：这条用例在 macOS 上是**假红**——它想证"不可用的解释器不许被导出"，实际却因为**本机恰好有可用的
conda 解释器**而失败。它只在"环境里没有可用 conda"时通过，而 Windows 恰好满足那个前提
（`<CONDA_PREFIX>\python.exe`，**没有 `bin/` 这一层**，所以该分支根本不成立）。

**② `scripts/dsh` 的 `CONDA_PREFIX` 分支缺可用性校验（真缺陷）**

包装脚本对 `PATH` 候选做了可用性校验（`"$candidate" -c ''`，注释写明是为 Windows 的
Microsoft Store 占位符），但 `${CONDA_PREFIX}/bin/python` 分支**只测 `-x`**。把 `CONDA_PREFIX`
指向一个 `exit 1` 的假解释器即可证明它会被导出：

```
$ env -i PATH="$BINDIR" HOME="$HOME" CONDA_PREFIX=/tmp/.../broken-conda /bin/sh scripts/dsh --version
fake-dsh CODERAG_PYTHON=/tmp/dsh-m6-t603b/broken-conda/bin/python args=--version
```

**后果是真的**：`CODERAG_PYTHON` 是 MCP 子进程的解释器（`E-06`），导出不可用的解释器会让
`mcp__coderag__code_search` 直接不可用。Windows 之所以没暴露它，纯粹是因为那个分支在 Windows 上不成立
——**缺陷一直在，只是被平台掩盖**。

**③ `scripts/install.sh` 有同一个缺口（同源，一并修）**

`install.sh` 第 28–29 行是同一段逻辑的复制：`-x` 就采信。既然 `T6-02` 的设计是"逻辑单点、两份脚本只做转发"，
就不能只修一半。

### 4.2 修复（**断言一字未改**）

| 文件 | 改动 |
|---|---|
| `scripts/dsh` | 把 `CONDA_PREFIX` 与 `PATH` 候选合成**一个循环**，**每个候选都过 `-c ''` 可用性校验**；文件 34 → **31 行** |
| `scripts/install.sh` | 同一循环；并**恢复**显式 `CODERAG_PYTHON` 的校验，且由 `-x` 加强为「可执行**且**能跑」，错误消息与退出码契约不变；文件 38 行（未变） |
| `tests/test_dsh_script.py` | `run_dsh` **隔离 `CONDA_PREFIX`**（`env.pop`）；新增 `fake_conda()` 夹具（可用 / 不可用两种）；原有那条用例改用"坏 conda + 坏 PATH"；**新增 2 条**：`test_dsh_script_does_not_export_an_unusable_conda_interpreter`（坏 conda 必须被拒）与 `test_dsh_script_prefers_a_usable_conda_interpreter`（好 conda 必须被采用） |

修完 `tests/test_dsh_script.py` **7 / 7 通过**，全量 **567 passed, 5 skipped**，两个包装脚本都在
`T6-02` 的 `≤ 40 行` 判据内（31 / 38）。

> **修复过程中我自己引入并立刻修掉的一个回归**：第一版把 `install.sh` 的 `[ -x "$PY" ]` 检查**删掉**了，
> `tests/test_install_script.py::test_install_script_rejects_a_missing_interpreter` 立刻抓到
> （`assert 126 == 2`——缺可执行位导致 shell 自己报 126，而不是脚本约定的 2）。已恢复并加强为可用性校验。
> 这正是"一个候选都要真的能跑"这条规则在**显式指定**路径上的同类漏洞。

---

## 5. `T6-04` 的 macOS 栏（端到端冒烟）

按 2026-09-30 裁决，`T6-04` 的 macOS 栏并入本文。

### 5.1 全新 `DSH_HOME` + 全新 profile：`plugin add`

```
$ DSH_HOME=/tmp/dsh-m6-t603b/dshhome ./scripts/dsh plugin --profile m6mac add .
dsh: initialized profile m6mac at /tmp/dsh-m6-t603b/dshhome/profiles/m6mac
dependencies:
+ dsh-coderag link:../../../..<repo>
Done in 2s using pnpm v12.4.2
（EXIT=0）
```

全新 `DSH_HOME` 下新建了 `profiles/m6mac/`（`cordis.patch.yml` / `package.json` / `pnpm-lock.yaml` /
`pnpm-workspace.yaml`）——即**确实是从零开始的 profile**，没有复用既有配置。

### 5.2 `--dump-config`：插件层确实被登记

```
$ DSH_HOME=/tmp/dsh-m6-t603b/dshhome ./scripts/dsh --profile m6mac --dump-config > dump-config.txt
（EXIT=0；354 行）

$ grep -n '# == dsh-coderag' dump-config.txt
333:# == dsh-coderag
$ grep -A6 '# == dsh-coderag' dump-config.txt
# == dsh-coderag
- id: mcp-coderag
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: coderag
    transport: stdio
    command: !!js process.env.CODERAG_PYTHON ?? '/opt/anaconda3/envs/forBSH/bin/python'
```

对整个 dump 扫描 `ERR_PNPM` / `error` / `skipped`：**0 / 0 / 0 命中**（无静默跳过，`E-05`）；
stderr 为空。

### 5.3 demo 工作区干净副本上的真实 `code_search`

用 patch 里的 `command` / `args`（`python -c 'import dsh_coderag.server as s; s.run()'`）拉起真实
MCP stdio 子进程，`CODERAG_ROOT` 指向干净副本：

```
initialize: {"name": "coderag", "version": "2.0.0"}
tools: ['code_search', 'code_outline', 'code_index', 'index_status']
code_index: {"taskId": "idx-20260930-e6ff", "state": "pending", "hint": "Poll index_status with this taskId."}
final index_status: {"state": "ready", "total_files": 3, "total_chunks": 7}
--- workspace index_status 原文 ---
{"status": "ready", "db_schema": 1, "skipped": {"count": 0, "reasons": {}}}
isError: False
--- code_search 原文 ---
status: ready
query: "用户令牌在哪里校验"
scanned: 3 files / 7 chunks
hits: 1 (sorted by source order)
skipped: 0

── src/auth/token.py:1-6  [module]  (chunk 0)
"""Token verification for the demo workspace.

用户令牌在哪里校验？答案就在本模块的 verify_token。
"""

from __future__ import annotations
--- 命中判定 ---
hit target file: True
status ready: True
```

- **命中 `src/auth/token.py` ✅**，`status: ready` ✅，`isError: False` ✅（`RL-06`/`RL-09`：有结果就不空返回）。
- 子进程 stderr 上是正常的 JSON-Lines 审计（`index_start` / `index_done`，`files: 3, chunks: 7`），**stdout 上只有 JSON-RPC**（`RL-04`）。
- 索引只落在**副本**：`/tmp/dsh-m6-t603b/demo-ws/.coderag/`（`index.sqlite3` 65536 B + `last-index.json`）。
  **原仓库未被污染**：冒烟后 `git status --short` 只有本任务预期的三处改动，且
  `examples/demo-workspace` 下没有新增索引（`S-03`/`S-04`）。

### 5.4 与 Windows 读数并列

| 检查 | macOS（本文） | Windows（`docs/m6-windows-smoke.md`） |
|---|---|---|
| 安装入口 | `pip install .`（forBSH，本机既有环境） | 全新解释器 + `dsh_coderag install-deps` |
| 默认路径无 numpy | 本机**已装** numpy 2.2.6，故本文**不**声称这一点 | `import numpy` → `ModuleNotFoundError`（过渡式断言） |
| `plugin add` | 退出码 0，无 `ERR_PNPM` | 退出码 0，无 `ERR_PNPM`，`Done in 366ms` |
| `--dump-config` | 第 333 行 `# == dsh-coderag`，负面扫描 0 命中 | 同样命中，负面扫描 0 命中 |
| `code_search` | `status: ready`，命中 `src/auth/token.py:1-6`，3 files / 7 chunks | `status: ready`，命中 `src/auth/token.py:1-6`，3 files / 7 chunks |
| 索引落点 | 只在副本的 `.coderag/` | 只在副本的 `.coderag/` |

> **一处必须诚实标注的边界**：macOS 侧**没有**复跑"一次性全新解释器 + 默认安装"那一段
> （`RL-10` 的过渡式断言）。forBSH 里装着 numpy 2.2.6——那是**运行向量测试套件的前提**
> （`pyproject.toml` 的 `semantic` extra），不是一个"全新默认安装"的样本。因此
> **`RL-10` 的默认安装零向量依赖，本文不提供 macOS 证据**，它由 Windows 侧那次冒烟提供；
> macOS 侧能证明的是"装了 numpy 的解释器上默认路径仍逐条走 BM25"（`S6`，见 L1 门禁）。

---

## 6. 未改动与明确的越界项

- **`docs/architecture.md` 第 8 行的「实测平台」未动**（按用户指示留给 `T6-05`）。本报告只是它的证据来源。
- **未改任何断言**：`tests/` 的改动只有 `run_dsh` 的环境隔离与新增用例；`tests/test_path_filter.py`、
  `tests/test_walker.py`、`src/` 一行未动。
- **未放宽任何判据**：`S1`–`S6`、`RL-10` 与 M6 的出口判据都不因本文改变。
- 冒烟用的临时目录（`/tmp/dsh-m6-t603b/`：`dshhome`、`demo-ws`、`dump-config.txt`、`mcp_smoke.py`、
  `broken-conda`、`fakebin`）**保留**以便复查，不属仓库内容。`mcp_smoke.py` 是一次性驱动脚本，
  按 `T5-14` 的先例**不进 `src/` / `scripts/`**。
