# M6 Windows 端到端冒烟（T6-04）

> **任务**：[`PROJECT.md`](../PROJECT.md) §6.5.1 的 `T6-04`｜**里程碑**：M6（v2.1.0）｜**执行日期**：2026-09-30
> **定位**：这是 **Windows 侧**的端到端冒烟记录。首次执行时**本机没有 macOS**，所以
> 「两平台结论并列」里的 **macOS 栏未执行**——它已按 2026-09-30 裁决拆给 **`T6-03b`**
> （M6 的 macOS 集中复核），本文件在那一栏如实标注「未执行」。
> **边界**：按任务行要求，冒烟过程**没有修改任何已有文件**；本文件是唯一新增物，
> 所有工作区、解释器、`DSH_HOME` 都在仓库之外的一次性目录里。

---

## 1. 冒烟环境

| 项 | 值 |
|---|---|
| 操作系统 | `Microsoft Windows NT 10.0.26100.0`（x64） |
| 全新解释器 | `C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\fresh-python\Scripts\python.exe`，Python `3.10.21` |
| 全新解释器（第二种路径） | `…\dsh-m6-t604\bare-python\Scripts\python.exe`，同样 `3.10.21`，**装之前只有 `pip` + `setuptools`** |
| 全新 `DSH_HOME` | `C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\dshhome`（由 `dsh` 现场初始化） |
| 全新 profile | `m6smoke`（`dsh: initialized profile m6smoke at …\dshhome\profiles\m6smoke`） |
| `dsh` 启动器 | `F:\dsh\resources\runtime\cli\bin\dsh.cmd` |
| **DSH 版本** | **`0.2.0-rc.2`**（随本机 DeepSeek Harness 安装自带） |
| DSH 自带 pnpm | **`pnpm v11.7.0`**（`F:\dsh\resources\runtime\pnpm`，不在 `PATH` 上，由 `dsh` 自己调用） |
| PowerShell | **只有 `powershell.exe` 5.1.26100.5074（Desktop）**；**`pwsh` 未安装** |
| 演示工作区 | `…\dsh-m6-t604\demo-ws`（`examples/demo-workspace` 的**干净副本**，仓库外） |

> **一处与项目既有记录的偏差，必须并列声明**：`dsh` 的版本是 **`0.2.0-rc.2`**，而
> `scripts/dsh` 钉的是 `0.1.5-rc.1`（`PROJECT.md` §4.1），`docs/architecture.md` 记的验证环境也是
> `0.1.5-rc.1`。本机**没有** `0.1.5-rc.1`（全局 npm 无 `@deepseek-ai/dsh`、npx 缓存为空），
> 而随桌面版自带的运行时是 `0.2.0-rc.2`。本次冒烟用的是**用户在这台机器上实际会拿到的那一个**，
> 因此它证明的是「在 DSH `0.2.0-rc.2` + pnpm `11.7.0` 下，本 bundle 能装上并被 `--dump-config` 收录」；
> **不是**「在 `0.1.5-rc.1` 下」的结论。

---

## 2. (a) 用 T6-02 的 CLI 装好引擎，并确认默认路径零向量依赖

**装法**：一次性全新解释器，走 `doctor` + `install-deps` 的默认路径（**不装任何 extra**）。

```text
$ "F:\conda\envs\dsh-coderag\python.exe" -m venv …\dsh-m6-t604\fresh-python
$ …\fresh-python\Scripts\python.exe -m pip list --format=freeze
pip==23.0.1
setuptools==79.0.1
```

引擎还没装进这个解释器，所以第一次先把包目录放进 `PYTHONPATH`（这正是 `scripts/install.sh`
这条薄包装做的事）：

```text
$ $env:PYTHONPATH = "<repo>\src"; …\fresh-python\Scripts\python.exe -m dsh_coderag doctor
== dsh-coderag doctor 2.0.0 ==
[ok] 解释器：C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\fresh-python\Scripts\python.exe
[ok] 版本：3.10.21（要求 >=3.10,<3.13）
[ok] FTS5：可用

CODERAG_PYTHON=C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\fresh-python\Scripts\python.exe
export CODERAG_PYTHON="C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\fresh-python\Scripts\python.exe"
把上面的值写进 cordis.patch.yml 的 config.env，
或在启动 dsh 的 shell 里 export（E-02/E-06）。
EXIT=0
```

```text
$ …\fresh-python\Scripts\python.exe -m dsh_coderag install-deps
安装   ：C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\fresh-python\Scripts\python.exe -m pip install .

== 自检：FTS5 可用 + 中文 bigram 往返 ==
[ok] FTS5：可用
[ok] bigram：幂等；'用户令牌' -> '用户 户令 令牌'
[ok] 中文往返：'用户令牌' -> ['token.py']
[ok] 标识符往返：'verify_token' -> ['token.py']
[ok] 无关词不命中：'连接池' -> []
包版本 ：dsh_coderag 2.0.0
完成：安装与自检通过
EXIT=0
```

pip 自己装掉 37 个包（`Successfully installed annotated-types-0.8.0 … uvicorn-0.54.0`），
其中含 `tree-sitter-0.25.2`、`tree-sitter-language-pack-0.13.0`、`mcp-1.30.0`、`pathspec-1.1.1`。

### 默认安装路径**没有**引入 numpy（`RL-10`）

按 2026-09-30 裁决，判据是**过渡式**的：不是「这台机器上有没有 numpy」，而是
「**走默认安装路径之后，这个全新解释器里有没有 numpy**」。

```text
$ …\fresh-python\Scripts\python.exe -c "import numpy"
ModuleNotFoundError: No module named 'numpy'
import numpy EXIT=1

$ …\fresh-python\Scripts\python.exe -c "import importlib.util as u; print('numpy spec:', u.find_spec('numpy'))"
numpy spec: None

$ …\fresh-python\Scripts\python.exe -m pip show dsh-coderag
Name: dsh-coderag
Version: 2.0.0
Location: c:\users\15349\appdata\local\temp\dsh-m6-t604\fresh-python\lib\site-packages
Requires: mcp, pathspec, tree-sitter, tree-sitter-language-pack

$ …\fresh-python\Scripts\python.exe -m pip list --format=freeze | Select-String 'numpy|tree-sitter|mcp|pathspec'
mcp==1.30.0
pathspec==1.1.1
tree-sitter==0.25.2
tree-sitter-c-sharp==0.23.5
tree-sitter-embedded-template==0.25.0
tree-sitter-language-pack==0.13.0
tree-sitter-yaml==0.7.2
```

**结论**：`Requires` 里没有 numpy，装完也没有 numpy，`import numpy` 失败。默认路径**零向量依赖**。
（对照：`numpy` 只在 `[project.optional-dependencies]` 的 `semantic` 里，是显式 opt-in 的。）

---

## 3. (b) 全新 `DSH_HOME` + 全新 profile：`dsh plugin add .`

```text
$ $env:DSH_HOME = "…\dsh-m6-t604\dshhome"
$ (cd <repo>) ; F:\dsh\resources\runtime\cli\bin\dsh.cmd plugin --profile m6smoke add .
dsh: initialized profile m6smoke at C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\dshhome\profiles\m6smoke

dependencies:
+ dsh-coderag link:F:/PersonalProjects/python/dsh-coderag/dsh-coderag

✓ Lockfile passes supply-chain policies (verified 2m ago)
Already up to date
Done in 366ms using pnpm v11.7.0
PLUGIN_ADD_EXIT=0
```

**没有出现 `ERR_PNPM_...`，也没有出现任何静默跳过**：退出码 `0`，依赖行明确写出
`+ dsh-coderag link:…`，pnpm 正常收尾。这正是 `E-05`／`T3-00` 记录的失败模式所关心的那一点——
`T3-00` 那次是 `ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED`（git-hosted 的 `prepare` 被 pnpm 10+ 拦下）；
本 bundle 是**零 install script、零构建步骤**的本地目录，所以不受该限制。

### `--dump-config` 里出现 bundle 标记

```text
$ F:\dsh\resources\runtime\cli\bin\dsh.cmd --profile m6smoke --dump-config
exit=0   lines=383
# == dsh-coderag
```

并且它插进来的那一行确实是 MCP 客户端：

```text
- id: mcp-coderag
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: coderag
    transport: stdio
    command: !!js process.env.CODERAG_PYTHON ?? '/opt/anaconda3/envs/forBSH/bin/python'
    args:
      - '-c'
      - import dsh_coderag.server as s; s.run()
```

对整个 dump 扫 `ERR_PNPM|error|skipped`：**无命中**。

> **一处必须说清的限制**：`--dump-config` 把 `command` 渲染成**未求值的 `!!js` 表达式**——
> 它显示的是 `process.env.CODERAG_PYTHON ?? '<macOS 默认值>'` 这段源码，不是求值结果。
> 因此**这份输出不能用来证明覆盖是否生效**；它只能证明「patch 被收录、且默认值确实是作者机器的
> macOS 路径」（`E-06`）。`dsh` 这版没有「调用某个 MCP 工具」的命令（只有 `plugin` 与启动 profile，
> 而 `headless` 需要 model key），所以**「DSH 在 `CODERAG_PYTHON` 下真的用这个解释器拉起子进程」
> 这一环本次未直接测**——下一节用「同一份 `command`/`args` 直连」测了它的下游半边。

---

## 4. (c) 在演示工作区的干净副本上跑一次真实 `code_search`

**做法**：把 `examples/demo-workspace` 复制到仓库之外（`…\dsh-m6-t604\demo-ws`），
按 `cordis.patch.yml` **原样的 `command` / `args`** 拉起 MCP 子进程（`command` 换成全新解释器、
`CODERAG_ROOT` 指向副本），然后走文档化的三调用循环：`code_index` → `index_status` → `code_search`。

```text
workspace : C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\demo-ws
launcher  : …\fresh-python\Scripts\python.exe -c 'import dsh_coderag.server as s; s.run()'
initialize: {'name': 'coderag', 'version': '2.0.0'}
code_index: {'taskId': 'idx-20260930-e2e0', 'state': 'pending', 'hint': 'Poll index_status with this taskId.'}
final index_status: {'taskId': 'idx-20260930-e2e0', 'state': 'ready', 'total_files': 3, 'done_files': 3,
                     'total_chunks': 7, 'done_chunks': 7, 'message': None}
---- code_search output ----
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

---- end ----
hit target file: True
child exit: 0
```

**逐条对齐期望结果**：`code_search` 返回 `status: ready` ✅；含**目标文件与行号**
（`src/auth/token.py:1-6`）✅；子进程退出码 `0` ✅；`index_status` 到达 `ready` ✅
（`E-01` 要求的「`code_index` 立刻返回 taskId、后台索引」这条链路也一并走通了）。

**索引落点**（`S-03`：不得写出工作区之外）：

```text
$ Get-ChildItem …\dsh-m6-t604\demo-ws\.coderag
index.sqlite3    65536
last-index.json    381
```

即在**副本自己**的 `.coderag/` 下。原仓库的 `examples/demo-workspace` **没有**被建索引
（`Test-Path <repo>\examples\demo-workspace\.coderag` → `False`），冒烟结束后
`git status --short` 为空。

> **未覆盖的一环**：`T1-15` 的「模型在 DSH 会话里被问到问题 → 真的调用
> `mcp__coderag__code_search`」需要一次带模型的任务（`dsh headless` 要 model key）。
> 本次冒烟覆盖的是「patch 的启动串 → 子进程 → SQLite FTS5 → 渲染结果」这一段，
> **不含模型侧的工具采纳**。

---

## 5. (d) 两代终端与 `doctor` 打印的 `CODERAG_PYTHON`

```text
$ (Get-Command powershell).Source
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
$ (Get-Command pwsh -ErrorAction SilentlyContinue)
NOT INSTALLED
$ $PSVersionTable.PSVersion ; $PSVersionTable.PSEdition
5.1.26100.5074  Desktop
```

**基线结论**：这台机器上**只有 Windows PowerShell 5.1，没有 `pwsh`**，因此「两代终端的差异」
在**本机无法对照**——只能记录「`pwsh` 缺席」这一事实本身。这与 `T6-01` 的
`docs/m6-crossplatform-baseline.md` §6 第 3 条一致（那里已用同一命令登记过一次）。

同一节还发现过一条与终端有关的取证陷阱：**PowerShell 5.1 的 `Invoke-WebRequest` 访问
`https://pypi.org/...` 会失败**（「基础连接已经关闭」），而同一个解释器的 `urllib` 正常返回
`HTTP 200`——即 **PS 5.1 不适合用来做网络取证**。

`doctor` 打印的、可直接复制的值：

```text
CODERAG_PYTHON=C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\fresh-python\Scripts\python.exe
export CODERAG_PYTHON="C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\fresh-python\Scripts\python.exe"
```

---

## 6. 两平台并列

| 项 | **Windows**（本次实测） | **macOS** |
|---|---|---|
| (a) 默认安装路径零向量依赖 | **已核实**：全新解释器装完 `import numpy` 失败、`Requires` 无 numpy | **未执行**（本机无 macOS，归 `T6-03b`） |
| (b) `plugin add` 无静默跳过 | **已核实**：exit 0、`+ dsh-coderag link:…`、pnpm v11.7.0、无 `ERR_PNPM` | **未执行**（归 `T6-03b`） |
| (b) `--dump-config` 含 bundle 标记 | **已核实**：`# == dsh-coderag` | **未执行**（归 `T6-03b`） |
| (c) `code_search` 命中目标文件 | **已核实**：`status: ready`、`src/auth/token.py:1-6` | **未执行**（归 `T6-03b`） |
| (d) 终端形态 | 只有 PowerShell 5.1，`pwsh` 缺席 | **未执行**（归 `T6-03b`） |
| DSH 版本 | `0.2.0-rc.2`（本机自带；项目钉的是 `0.1.5-rc.1`） | **未执行** |

**macOS 那一栏整体未执行**，因此本文件**不构成**「Windows 与 macOS 并列可查」的完成证据——
那一栏要等 `T6-03b` 的集中 macOS 复核补齐。这是 2026-09-30 裁决时的既定安排，不是遗漏。

---

## 7. 冒烟过程中顺带实测到的三件事

这三条都是**观察**，本任务不改任何文件，故只记录：

1. **两个薄包装在 Windows 上确实可用——但依赖的是 MSYS2 的路径转换，不是 POSIX 语义。**
   在一个**全新空**解释器上（只有 `pip`/`setuptools`）执行
   `CODERAG_PYTHON=<bare> bash scripts/install.sh`（Git for Windows 的 bash），
   它成功走到 `pip install .` 并跑完装后自检：

   ```text
   安装   ：C:\Users\15349\AppData\Local\Temp\dsh-m6-t604\bare-python\Scripts\python.exe -m pip install .

   == 自检：FTS5 可用 + 中文 bigram 往返 ==
   [ok] FTS5：可用
   [ok] 中文往返：'用户令牌' -> ['token.py']
   包版本 ：dsh_coderag 2.0.0
   完成：安装与自检通过
   WRAPPER_EXIT=0
   ```

   包装脚本里 `PYTHONPATH="${repo}/src"` 是 **POSIX 形式**（`/f/PersonalProjects/…`），
   而**原生 Windows Python 认不出它**——之所以还能跑起来，是 MSYS2/Git for Windows 在把
   环境交给原生子进程时把 `PYTHONPATH` 转成了 Windows 形式。
   **因此**：Windows 上的**推荐形态**仍是直接调用 CLI
   （`"$CODERAG_PYTHON" -m dsh_coderag install-deps`，本文件 §2 用的就是它）；包装脚本
   只在「装了 Git for Windows 的 bash」这一前提下可用。这条措辞归 `T6-05`。

2. **`--dump-config` 不求值 `!!js`。** 见 §3 末尾：它渲染的是表达式源码。任何拿
   `dump-config` 当「覆盖已生效」证据的验收写法都是**代理指标**（`AGENTS.md` §8 那一类）。

3. **`install-deps` 的输出顺序在重定向时会被缓冲打乱。** `pip install` 是子进程、直写 fd，
   而 CLI 自己的 `_emit` 走的是 Python 的 **块缓冲** stdout；于是把输出重定向到文件后，
   pip 的日志会**排在** CLI 的进度行之前。交互式终端下不出现。属观感问题、不影响退出码与结果，
   但会让脚本化的安装日志读起来像是「先安装、后报告」。**本任务不改文件**，如需修（给
   CLI 的写操作加 `flush=True`）应另立条目。

---

## 8. 结论与仍未验证的事项

**本次已核实的（Windows）**：默认安装路径零向量依赖（过渡式断言）、`dsh plugin add .` 无静默跳过、
`--dump-config` 收录 `# == dsh-coderag`、演示工作区副本上 `code_search` 返回 `status: ready`
且命中 `src/auth/token.py:1-6`、索引只落在工作区内、仓库与原始演示工作区全程未被改动。

**仍未验证的**：

| 项 | 原因 | 归属 |
|---|---|---|
| macOS 侧的全部五项 | 本机无 macOS 机器 | **`T6-03b`**（M6 的集中 macOS 复核） |
| 「DSH 在 `CODERAG_PYTHON` 下真的用该解释器拉起 MCP 子进程」 | `--dump-config` 不求值 `!!js`；`dsh` 无「调用 MCP 工具」的命令 | 需一次带 model key 的会话，或 `T6-05` 如实措辞 |
| 模型侧的工具采纳（`T1-15` 那一环） | 需要 model key | 不属于 M6 |
| 在 **DSH `0.1.5-rc.1`**（项目钉的版本）下的同样结论 | 本机只有 `0.2.0-rc.2` | 如需，须在有该版本缓存的机器上复跑 |
| `pwsh` 与 PowerShell 5.1 的行为差异 | 本机无 `pwsh` | 无法在有 `pwsh` 的机器之外补 |
