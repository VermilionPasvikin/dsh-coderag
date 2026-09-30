# M6 跨平台兼容性基线审计（T6-01）

> **任务**：[`PROJECT.md`](../PROJECT.md) §6.5.1 的 `T6-01`｜**里程碑**：M6（v2.1.0）｜**审计日期**：2026-09-30
> **定位**：本文件是 `T6-01` 的唯一交付物。**先取证、后改代码**——本次审计**没有修改任何源文件**，
> 只新增本文件。四件事逐条给出结论，并且**按平台**分开记录：实测过的写「已核实」，
> 没实测的一律写「未验证」。**不用推断代替实测**。
> **谁消费它**：`T6-02`（Python CLI 成为唯一入口）、`T6-03`（Windows 跑通测试套件）、
> `T6-05`（README / 架构文档的平台表述）。§5 与 §6 是给它们的输入，不是本任务要修的东西。

---

## 1. 审计环境

本次全部 Windows 结论来自**同一台机器、同一个解释器**，在 DSH 会话（文件沙箱 `workspace-write`）内执行。

| 项 | 值 |
|---|---|
| 操作系统 | `Microsoft Windows NT 10.0.26100.0`（Windows 10 内核 26100，x64） |
| 目标解释器 | `F:\conda\envs\dsh-coderag\python.exe` |
| 解释器版本 | `3.10.21 \| packaged by Anaconda, Inc. \| (main, Aug 27 2026, 14:35:39) [MSC v.1942 64 bit (AMD64)]` |
| 平台三元组 | `platform.machine() = AMD64`、`platform.platform() = Windows-10-10.0.26100-SP0` → **`win_amd64`** |
| `sqlite3` | 模块 `2.6.0`｜SQLite **`3.53.4`** |
| 控制台代码页 | **936**（GBK） |
| PowerShell | **5.1.26100.5074**（`powershell.exe`）；**`pwsh` 未安装** |
| git | `2.38.0.windows.1` |
| `CODERAG_PYTHON` | 会话环境中**未设置**（因此本次每条命令都显式指定解释器） |
| 安装方式 | 依赖用 `pip install` 装进上述 conda 环境；该环境在审计开始时**只有 `pip` / `setuptools` / `wheel` / `packaging`** |

> **诚实标注一处执行条件**：其中「真实安装 wheel」那一步在 DSH 文件沙箱下被拒（目标目录
> `F:\conda\envs\dsh-coderag` 在工作区之外），是**取得一次完整访问授权后**执行的。沙箱是执行条件，
> 不是平台结论——§6 第 4 条单独说明了它与 Windows 权限机制的交互。

---

## 2. 读数规则

| 标记 | 含义 |
|---|---|
| **已核实** | 本机实际执行了命令，并粘贴其原始输出；或取自 PyPI 的权威文件清单（对「文件是否发布」这一问题，清单就是事实本身） |
| **未验证** | 本机**没有**执行过。可能是平台不可得（没有 Linux / macOS 机器），也可能是本次范围内没测 |

两个容易混淆的边界，本文件始终区分：

- 「**wheel 已发布**」≠「**在这台机器上装成功**」。前者由 PyPI 清单证明，后者要真的装。
- 「**本次已核实**」≠「**仓库既有记录**」。macOS 的结论来自仓库里**别人实跑过**的记录
  （`docs/m4-install-verification.md`、`PROJECT.md` §6.7 的既有证据行），本文件照抄并标明来源，
  不冒充本次实测。

---

## 3. 四项事实逐条结论

### 3.1 事实①：依赖 wheel 在 `win_amd64` 上是否齐备

**用什么查的**：`pyproject.toml` 的四个直接依赖，逐个查 PyPI 的 JSON 文件清单（PyPI 自己发布的
artifact 列表就是权威答案），再在本机**真的装一遍**。

取证脚本（一次性，**不入库**——`T6-01` 的产出只有本文件）：

```text
$ python audit_wheels.py win_amd64 --python cp310      # 脚本位于 %TEMP%\dsh-m6-audit\，下同
== T6-01 fact 1: published wheels (platform=win_amd64, python=cp310) ==

-- mcp >=1.28,<2  ==>  1.30.0 --
   published artifacts   : 2
   win_amd64 + cp310 wheels : 0
   pure-python wheels    : 1
   sdists                : 1
     * mcp-1.30.0-py3-none-any.whl
   VERDICT: wheel available

-- tree-sitter >=0.25.2,<0.26  ==>  0.25.2 --
   published artifacts   : 36
   win_amd64 + cp310 wheels : 1
   pure-python wheels    : 0
   sdists                : 1
     * tree_sitter-0.25.2-cp310-cp310-win_amd64.whl
   VERDICT: wheel available

-- tree-sitter-language-pack >=0.13,<0.14  ==>  0.13.0 --
   published artifacts   : 6
   win_amd64 + cp310 wheels : 1
   pure-python wheels    : 0
   sdists                : 1
     * tree_sitter_language_pack-0.13.0-cp310-abi3-win_amd64.whl
   VERDICT: wheel available

-- pathspec >=0.12  ==>  1.1.1 --
   published artifacts   : 2
   win_amd64 + cp310 wheels : 0
   pure-python wheels    : 1
   sdists                : 1
     * pathspec-1.1.1-py3-none-any.whl
   VERDICT: wheel available
```

**更强的证据：真的装了一遍**（不带 `--only-binary`，pip 可以自由选 sdist——结果一个 sdist 都没用）：

```text
$ "F:\conda\envs\dsh-coderag\python.exe" -m pip install --no-cache-dir --disable-pip-version-check \
    "mcp>=1.28,<2" "tree-sitter>=0.25.2,<0.26" "tree-sitter-language-pack>=0.13,<0.14" "pathspec>=0.12"
Collecting tree-sitter<0.26,>=0.25.2
  Downloading tree_sitter-0.25.2-cp310-cp310-win_amd64.whl.metadata (10 kB)
Collecting tree-sitter-language-pack<0.14,>=0.13
  Downloading tree_sitter_language_pack-0.13.0-cp310-abi3-win_amd64.whl.metadata (19 kB)
  Downloading tree_sitter_language_pack-0.13.0-cp310-abi3-win_amd64.whl (16.9 MB)
Collecting pywin32>=310 (from mcp<2,>=1.28)
  Downloading pywin32-312-cp310-cp310-win_amd64.whl.metadata (11 kB)
Collecting pydantic-core==2.46.5 (from pydantic<3.0.0,>=2.11.0->mcp<2,>=1.28)
  Downloading pydantic_core-2.46.5-cp310-cp310-win_amd64.whl.metadata (6.7 kB)
Collecting rpds-py>=0.25.0 (from jsonschema>=4.20.0->mcp<2,>=1.28)
  Downloading rpds_py-0.30.0-cp310-cp310-win_amd64.whl.metadata (4.2 kB)
Collecting cryptography>=3.4.0 (from pyjwt[crypto]>=2.10.1->mcp<2,>=1.28)
  Downloading cryptography-50.0.1-cp39-abi3-win_amd64.whl.metadata (4.3 kB)
Collecting cffi>=2.0.0 (from cryptography>=3.4.0->...)
  Downloading cffi-2.1.1-cp310-cp310-win_amd64.whl.metadata (6.7 kB)
Collecting tree-sitter-c-sharp>=0.23.1 (from tree-sitter-language-pack<0.14,>=0.13)
  Downloading tree_sitter_c_sharp-0.23.5-cp310-abi3-win_amd64.whl.metadata (2.8 kB)
Collecting tree-sitter-embedded-template>=0.25.0 (from tree-sitter-language-pack<0.14,>=0.13)
  Downloading tree_sitter_embedded_template-0.25.0-cp310-abi3-win_amd64.whl.metadata (2.4 kB)
Collecting tree-sitter-yaml>=0.7.2 (from tree-sitter-language-pack<0.14,>=0.13)
  Downloading tree_sitter_yaml-0.7.2-cp310-abi3-win_amd64.whl.metadata (1.8 kB)
Installing collected packages: ..., mcp, ...
Successfully installed annotated-types-0.8.0 anyio-4.15.1 attrs-26.1.0 certifi-2026.7.22 cffi-2.1.1
click-8.5.0 cryptography-50.0.1 exceptiongroup-1.3.1 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1
httpx-sse-0.4.3 idna-3.20 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 mcp-1.30.0
pathspec-1.1.1 pycparser-3.0 pydantic-2.13.5 pydantic-core-2.46.5 pydantic-settings-2.15.0
pyjwt-2.15.1 python-dotenv-1.2.3 python-multipart-0.0.32 pywin32-312 referencing-0.37.0
rpds-py-0.30.0 sse-starlette-3.5.0 starlette-1.7.0 tree-sitter-0.25.2 tree-sitter-c-sharp-0.23.5
tree-sitter-embedded-template-0.25.0 tree-sitter-language-pack-0.13.0 tree-sitter-yaml-0.7.2
typing-extensions-4.16.0 typing-inspection-0.4.4 uvicorn-0.54.0
EXIT=0
```

**Linux 侧的对应结论**（同一脚本，`manylinux` + `cp310`）：

```text
$ python audit_wheels.py manylinux --python cp310
-- mcp >=1.28,<2  ==>  1.30.0 --
   pure-python wheels    : 1
     * mcp-1.30.0-py3-none-any.whl
   VERDICT: wheel available
-- tree-sitter >=0.25.2,<0.26  ==>  0.25.2 --
   manylinux + cp310 wheels : 2
     * tree_sitter-0.25.2-cp310-cp310-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl
     * tree_sitter-0.25.2-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
   VERDICT: wheel available
-- tree-sitter-language-pack >=0.13,<0.14  ==>  0.13.0 --
   manylinux + cp310 wheels : 2
     * tree_sitter_language_pack-0.13.0-cp310-abi3-manylinux2014_aarch64.whl
     * tree_sitter_language_pack-0.13.0-cp310-abi3-manylinux2014_x86_64.whl
   VERDICT: wheel available
-- pathspec >=0.12  ==>  1.1.1 --
   pure-python wheels    : 1
     * pathspec-1.1.1-py3-none-any.whl
   VERDICT: wheel available
```

**结论**

| 平台 | 结论 | 定级 |
|---|---|---|
| **Windows（`win_amd64`, cp310）** | 四个直接依赖 + **完整传递闭包**（含 `pywin32`、`pydantic-core`、`rpds-py`、`cffi`、`cryptography`、三个 `tree-sitter-*` 附属包）全部有 wheel，**零源码编译**；本机安装退出码 `0` | **已核实** |
| **Linux（`manylinux_2_17/2_28`, `x86_64` + `aarch64`, cp310）** | 两个含原生扩展的依赖都有 manylinux wheel（x86_64 与 aarch64 各一），另两个是纯 Python | **已核实**（发布清单）｜**未验证**（未在 Linux 上实际安装） |
| **macOS** | 本次**未查、未装** | **未验证**（仓库既有记录：`docs/m4-install-verification.md` 记 macOS + forBSH 装成过） |

> 这一条推翻了 `PROJECT.md` §6.5.1「已知阻碍」里的第一句猜测——原文写
> 「`tree-sitter` / `tree-sitter-language-pack` 的 Windows wheel 是否齐备**未经核实**」。
> **现已核实：齐备。** 该阻碍可以划掉（改写属 `T6-05`，本任务只给结论）。

### 3.2 事实②：目标解释器的 `sqlite3` 是否带 FTS5

```text
$ "F:\conda\envs\dsh-coderag\python.exe" -c "import sqlite3; ..."
sqlite_version: 3.53.4
fts5: available
compile_options:
   ...
   ENABLE_FTS5
   ENABLE_GEOPOLY
   ENABLE_RTREE
   ...
```

其中 `fts5: available` 来自**真的建了一张 FTS5 虚表**（`CREATE VIRTUAL TABLE t USING fts5(x)` 未抛异常），
不是只读 `PRAGMA compile_options`。

**结论**

| 平台 | 结论 | 定级 |
|---|---|---|
| **Windows（conda `dsh-coderag`）** | SQLite `3.53.4`，`compile_options` 含 `ENABLE_FTS5`，FTS5 虚表创建成功 | **已核实** |
| **macOS（forBSH，既有记录）** | `PROJECT.md` §6.7 的 `T1-06` 证据记 `chunks_fts` 建成且分词器为 `unicode61`；`T2-22` 证据记「本机 `fts5_available()` 为 True」——建 FTS5 虚表本身就要求 FTS5 可用 | **已核实**（仓库既有记录，非本次实测） |
| **Linux** | 本次无 Linux 机器 | **未验证** |

### 3.3 事实③：`tree-sitter-language-pack` 能否在无网络下给出已编译 grammar

**判据**：把 `socket.getaddrinfo` / `socket.create_connection` / `socket.socket.connect` 全部替换为抛异常，
然后走**项目自己的 `dsh_coderag.parser`**（不是复述一份实现）为 7 个扩展名各取一次 grammar 并真解析。

```text
$ python probe_grammars_offline.py
== T6-01 fact 3: offline compiled grammars ==
interpreter            : F:\conda\envs\dsh-coderag\python.exe
tree-sitter-language-pack: 0.13.0
tree-sitter              : 0.25.2
bindings dir             : F:\conda\envs\dsh-coderag\lib\site-packages\tree_sitter_language_pack\bindings
compiled .pyd grammars   : 170
  sample: actionscript.pyd, ada.pyd, agda.pyd, apex.pyd, arduino.pyd, asm.pyd ...

-- production path: parser.get_parser() per extension --
  .c    -> c           root='translation_unit' has_error=False
  .cpp  -> cpp         root='translation_unit' has_error=False
  .h    -> c           root='translation_unit' has_error=False
  .hpp  -> cpp         root='translation_unit' has_error=False
  .js   -> javascript  root='program' has_error=False
  .py   -> python      root='module' has_error=False
  .ts   -> typescript  root='program' has_error=False

VERDICT: compiled grammars are available with sockets blocked
```

**结论**

| 平台 | 结论 | 定级 |
|---|---|---|
| **Windows** | `tree-sitter-language-pack==0.13.0` 的 wheel 里直接带着 **170 个已编译 `.pyd`** grammar；7 个扩展名全部解析成功且 `has_error=False`；**socket 全封**，没有发生任何一次联网 | **已核实** |
| **macOS（既有记录）** | `PROJECT.md` §6.7 的 `T2-01` 记下过反面案例（未钉版本装到 `1.20.0` 时 `available_languages()==0`、`get_language('python')` 报 `DownloadError`，即**要联网**），并因此把 `tree-sitter-language-pack` 钉到 `>=0.13,<0.14`；`T2-02`/`T2-05` 的证据显示钉住后分块与上下文前缀测试全绿——离线可用 | **已核实**（仓库既有记录，非本次实测） |
| **Linux** | 本次无 Linux 机器 | **未验证** |

> **`pyd` vs `so` 不构成差异**：Linux 的 wheel 里对应的是一批 `.so`。两者都随 wheel 分发、都不需要
> 运行时下载；「Linux 上也离线可用」不作为实测结论，故仍列**未验证**。

### 3.4 事实④：MCP 子进程能否被拉起

**判据**：把 `cordis.patch.yml` 里的 `command` / `args` **原样读出来**（探针不另写一份，避免漂移），
用 Windows 形态的解释器路径当 `CODERAG_PYTHON`，以 piped stdio 拉起子进程，发真实的
`initialize` + `notifications/initialized` + `tools/list`。

```text
$ python probe_mcp_child.py
== T6-01 fact 4: MCP child launch on Windows ==
patch command : command: !!js process.env.CODERAG_PYTHON ?? '/opt/anaconda3/envs/forBSH/bin/python'
patch args    : args: ['-c', 'import dsh_coderag.server as s; s.run()']
parsed argv   : ['-c', 'import dsh_coderag.server as s; s.run()']
CODERAG_PYTHON: F:\conda\envs\dsh-coderag\python.exe
initialize   : {'name': 'coderag', 'version': '2.0.0'}
tools/list   : ['code_search', 'code_outline', 'code_index', 'index_status']
child exit   : 0
stderr bytes : 0
child launched and completed the MCP handshake on Windows
```

**结论**

| 平台 | 结论 | 定级 |
|---|---|---|
| **Windows** | 子进程被拉起，完成 MCP 握手，`serverInfo` 为 `coderag 2.0.0`，工具集恰为**固定的 4 个**，子进程退出码 `0`、**stderr 0 字节**（stdout 干净） | **已核实** |
| **macOS（既有记录）** | `PROJECT.md` §6.7 的 `T1-14`（`--dump-config` 打出 `mcp-coderag` 行）+ `T1-15`（DSH Web 里 `mcp__coderag__code_search` 真的被调用）；`docs/m4-install-verification.md` 第 137 行记的启动命令与之同形 | **已核实**（仓库既有记录，非本次实测） |
| **Linux** | 本次无 Linux 机器 | **未验证** |

**这一环为什么天然跨平台**（与任务描述一致，已由上面输出印证）：

- `command` 是**一个解释器路径**，`args` 是 `['-c', '<一行 Python>']`——都是字符串参数，**不经任何 shell**，
  因此没有 `sh` / `bash`、没有引号规则、没有 `PATH` 查找、没有可执行位，也没有 POSIX 路径拼接。
- 唯一的平台相关部分是 **`command` 的默认值**：`'/opt/anaconda3/envs/forBSH/bin/python'` 是作者机器的
  **macOS 路径**。在 Windows 上它必须被 `CODERAG_PYTHON` 覆盖成 `F:\conda\envs\dsh-coderag\python.exe`
  （本探针就是这么做的）。这是**数据**，不是启动逻辑里的 POSIX 假设——`T6-02` 的 `doctor` 子命令
  要打印的正是这个可直接复制的值。
- **一处必须说明的替代**：本次 `PYTHONPATH` 指向了仓库的 `src/`，因为**项目本身还没有装进这个解释器**。
  「把包装进去」是 `T6-02` 的 `install-deps` 与 `T6-04` 的端到端冒烟，不在本任务范围内。
  换句话说：**子进程能否被拉起已核实；「装好之后能否被拉起」未验证**（归 `T6-04`）。

---

## 4. 按平台汇总：已核实 / 未验证

> **本节是 `T6-01` 当时的快照，读数不改写**——基线文件的价值就在于是那时的事实。
> 表里的「未验证」项此后已由 `T6-03a` / `T6-03b` / `T6-04` / `T6-08` 逐条处置；
> **M6 收尾时的当前状态见 [`m6-summary.md`](m6-summary.md)**（含最终平台矩阵与仍然成立的边界）。

**已核实**（本机实跑，含上面的实际输出；标「既有记录」的来自仓库里此前真实跑过的证据行）

| 平台 | 事实① wheel | 事实② FTS5 | 事实③ 离线 grammar | 事实④ MCP 子进程 |
|---|---|---|---|---|
| **Windows** | 齐备，含传递闭包，零编译 | `3.53.4` + `ENABLE_FTS5`，虚表建成 | 170 个 `.pyd`，socket 全封可用 | 拉起成功，握手 + 4 工具，exit 0 |
| **macOS** | 既有记录（`docs/m4-install-verification.md`） | 既有记录（`T1-06` / `T2-22`） | 既有记录（`T2-01` / `T2-02`） | 既有记录（`T1-14` / `T1-15` / `m4`） |
| **Linux** | 发布清单已核实（manylinux x86_64 + aarch64） | — | — | — |

**未验证**（本机没有执行过，因此**不得**被下游任务或文档当作「支持」）

| 平台 | 未验证的内容 | 归谁 |
|---|---|---|
| **Linux** | ① 实际安装；② FTS5；③ 离线 grammar；④ MCP 子进程拉起——**四项全部未验证**（无 Linux 机器） | 未被任何 M6 任务覆盖，**保持未验证** |
| **macOS** | **本轮复跑**：本次没有 macOS 机器，上述 macOS 结论**全部来自既有记录**，未在 2.0.0 的当前 HEAD 上重跑 | `T6-03` / `T6-04`（它们要求同一提交内在 macOS 上复跑） |
| **Windows** | ① 项目自身安装后的 MCP 拉起（本次用 `PYTHONPATH=src` 代替）；② 全量 `pytest`；③ 端到端冒烟（`dsh plugin add` + `--dump-config` + 真实 `code_search`）；④ `scripts/install.sh` / `scripts/dsh` 在 Windows 上的可执行性（见 §5） | `T6-02` / `T6-03` / `T6-04` |

> **对 `docs/architecture.md` 第 8 行的直接后果**：那一行现在写「**实测平台：仅 macOS**」。
> 本次审计把 Windows 的**四项基线**变成已核实，但**没有**验证 Windows 上的安装与端到端链路，
> 所以该行**现在仍不应改写**——改写要等 `T6-04`，且只能写它实际测过的平台（`T6-05`）。

---

## 5. 两个外壳脚本的 POSIX 依赖（**只登记，不修**）

`T6-01` 的边界：这里只记录事实与行号，**修法是 `T6-02`**。

**本机环境事实**

| 探测 | 结果 |
|---|---|
| `Get-Command sh` / `bash` / `grep` / `sed` / `awk` / `env` | **全部 NOT FOUND**（都不在 `PATH` 上） |
| Git for Windows 自带的 POSIX 工具 | `C:\Program Files\Git\usr\bin\bash.exe`、`bin\sh.exe`、`usr\bin\grep.exe`、`usr\bin\sed.exe` **存在于磁盘**，但**不在 `PATH`** |
| 实际执行 `bash scripts/install.sh` | 失败：`bash.exe: *** fatal error - couldn't create signal pipe, Win32 error 5`（DSH 沙箱不允许命名管道——**这是沙箱边界，不作为 Windows 平台结论**） |
| Windows conda 的解释器位置 | `F:\conda\envs\dsh-coderag\python.exe`（即 `<CONDA_PREFIX>\python.exe`，**没有 `bin/` 这一层**） |

**`scripts/dsh`（34 行，`#!/bin/sh`）**

| 行 | POSIX 依赖 |
|---|---|
| 1 | `#!/bin/sh` shebang——Windows 没有原生外壳认它 |
| 28 | `DSH_VERSION="${DSH_VERSION:-0.1.5-rc.1}"` 参数展开 |
| 30 | `command -v dsh`（POSIX 内建，`/dev/null` 也是 POSIX 路径）、`[ ... ]` 测试 |
| 31, 34 | `exec` |

**`scripts/install.sh`（239 行，`#!/usr/bin/env bash`）**

| 行 | POSIX 依赖 |
|---|---|
| 1 | `#!/usr/bin/env bash` |
| 30 | `set -u` |
| 32 | `cd "$(dirname "$0")/.."` |
| 34–36 | `printf` |
| 44, 47 | `CODERAG_PYTHON` / `CONDA_PREFIX` / `CONDA_DEFAULT_ENV` 变量展开；**`${CONDA_PREFIX}/bin/python` 在 Windows 上是错的路径**（真实布局是 `<CONDA_PREFIX>\python.exe`） |
| 51–55, 76, 234–236 | `command -v` |
| 66 | `[ ! -x "${PY}" ]`——**可执行位语义**（Windows 由扩展名决定，不靠 mode bit） |
| 84–87, 96–98, 117, 144 | 以 `"${PY}" -c '...'` / heredoc 形式跑内联 Python（这部分本身跨平台） |
| 118 | `sed -n 's/^Editable project location: //p'` |
| 123 | `pwd -P` |
| 144–212 | `<<'PYCODE'` heredoc |
| 13–17 | 退出码约定 `0` / `1` / `2`——**这段契约是要平移进 Python CLI 的东西**，不是要丢的东西 |

**登记结论**：两个脚本都**没有 Windows 原生外壳**可直接执行；它们的逻辑（解释器探测、版本区间校验、
FTS5 预检、`pip install`、自检）在 Windows 上只能靠 Git for Windows 额外提供 `bash`——而那个 `bash`
**不在 `PATH` 上**，用户不可能知道要去 `C:\Program Files\Git\usr\bin` 里找。这正是 M6 已裁定
「**Python CLI 是唯一跨平台入口**」、并把 `install.ps1` / `dsh.ps1` 列为**被否决方案**的实证依据。
本仓库中**不存在** `scripts/dsh.ps1` 或 `scripts/install.ps1`（已核实：全仓库 `*.ps1` 零命中）。

---

## 6. 顺带记录的 Windows 环境发现（**登记，不修**）

审计过程中撞到的、会直接影响 M6 后续任务与**验收命令本身**的 Windows 事实。修法归属逐条写明。

1. **`python3` / `python` 在 Windows 上是商店占位符，计划里的验收命令不能照抄。**
   `Get-Command python3` → `C:\Users\...\AppData\Local\Microsoft\WindowsApps\python3.exe`，执行结果是：

   ```text
   $ python3 --version
   python3.exe : Python was not found; run without arguments to install from the Microsoft Store,
   or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.
   ```

   `PROJECT.md` §6.5.1 里 `T6-01`–`T6-05` 的验收命令大量以 `python3 ...` 开头（`T6-01` 自己就有
   `python3 scripts/verify-plan.py .`）。**在 Windows 上必须写成 `"$CODERAG_PYTHON" ...`**，
   否则跑起来是商店占位符。→ 归 `T6-02`（`doctor` 打印可复制的解释器路径）/ `T6-05`（文档写法）。

2. **`scripts/verify-plan.py` 在 cp936 控制台下会崩，且不是逻辑错。**
   不加任何设置、在代码页 936 的终端里：

   ```text
   $ chcp
   Active code page: 936
   $ "F:\conda\envs\dsh-coderag\python.exe" scripts/verify-plan.py .
   ... （前 3 行正常打印）
   UnicodeEncodeError: 'gbk' codec can't encode character '\u2705' in position 2: illegal multibyte sequence
   EXIT=1
   ```

   崩溃点是脚本第 434 行打印 `✅` / `❌` 的那一行。加 `PYTHONIOENCODING=utf-8` 后 **28 项检查全绿**
   （输出见 §7 的验收证据）。**这意味着 Windows 上任何以 `python3 scripts/verify-plan.py .` 收尾的
   验收命令都会被这道编码墙挡住。** → 归 `T6-03`（或直接把标记改成 ASCII），本任务只登记。

3. **本机 PowerShell 只有 5.1，没有 `pwsh`。** `$PSVersionTable.PSVersion` = `5.1.26100.5074`，
   `Get-Command pwsh` = NOT FOUND。`T6-04`(d) 要求记录「PowerShell 与 `pwsh` 两代终端的差异」——
   **基线在此：这台机器上 `pwsh` 不存在，两代差异在本机无法对照**。
   附带一条与项目无关但影响取证方式的观察：PowerShell 5.1 的 `Invoke-WebRequest` 访问
   `https://pypi.org/...` 报「基础连接已经关闭」，而同一个解释器的 `urllib` 正常返回 `HTTP 200`——
   **网络取证不要放在 PS 5.1 里做**。

4. **环境注记（DSH 沙箱 × Windows 权限，不记为平台缺陷）。**
   在受限令牌下，用 `os.mkdir(path, 0o700)` 创建的目录**丢掉继承来的权限项**，之后往里写文件被拒：

   ```text
   os.mkdir mode 700 -> child write DENIED (PermissionError)
   os.mkdir mode 777 -> child write OK
   ```

   `tempfile.mkdtemp()` 用的正是 `0o700`，所以 **`pip` 在沙箱内必然失败**
   （`pip-unpack-*/*.whl.metadata` → `[Errno 13] Permission denied`），而且它在工作区外写
   `site-packages` 也会被拒。取得完整访问后同一条 `pip install` 一次成功（见 §3.1）。
   **结论**：这是「受限令牌 + Windows 显式 DACL」的交互，不是 Windows 上的正常失败路径；
   但它对**自动化安装步骤**（`T6-02` 的 `install-deps`）有直接影响——在受限环境下要靠
   可继承权限的临时目录，或干脆别让它自己造临时目录。

---

## 7. 本任务的验收证据

`T6-01` 的验收命令（`AGENTS.md` §0.2 步骤 5；**在 Windows 上按 §6 第 1 条改用显式解释器**）：

```text
$ test -f docs/m6-crossplatform-baseline.md && echo "文件存在 ✅"
$ grep -c -e "已核实" -e "未验证" docs/m6-crossplatform-baseline.md
$ "$CODERAG_PYTHON" scripts/verify-plan.py .
```

三条的实际输出粘贴在 `PROJECT.md` §6.7 的 `T6-01` 行（`AGENTS.md` §5.1 第 4 条）——本文件不复制它们，
一个事实一个家。

---

## 8. 对下游任务的交接

| 任务 | 本文件交给它的东西 |
|---|---|
| `T6-02`（Python CLI 唯一入口） | §3.1 的 wheel 齐备结论（不必再为 Windows 设计 fallback）；§3.4 里 `command` 默认值需被 `doctor` 打印成可复制形态；§5 的 POSIX 依赖清单（要平移的正是那 239 行里的逻辑与退出码契约）；§6 第 1、4 条 |
| `T6-03`（Windows 跑通测试套件） | §3.2 的 FTS5 已核实（不必再探）；§3.3 的离线 grammar 已核实；§6 第 2 条的编码墙（否则验收命令自己就跑不过）；§4 的「未验证」清单 |
| `T6-04`（Windows 端到端冒烟） | §4 里 Windows 的 4 项「未验证」正是它的范围；§6 第 3 条的 `pwsh` 缺失是它要记录的(d)项基线 |
| `T6-05`（文档平台对齐） | §3.1 推翻了「Windows wheel 未经核实」这一阻碍；§4 的结论要求 `docs/architecture.md` 第 8 行**暂时不动**，只写 `T6-04` 实测过的平台 |

**本任务明确没做的事**：不修改任何源文件、不动两个 shell 脚本、不改 `README.md` / `architecture.md`、
不跑全量测试、不做端到端冒烟。它们分别是 `T6-02`–`T6-05`。
