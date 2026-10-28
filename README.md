# dsh-coderag

> ## ⚠️ 安全声明（请先读）
>
> **安装本插件等于授予它与本机账号同等的机器权限。**
> DSH 的三档文件权限（`read-only` / `workspace-write` / `danger-full-access`）**不约束插件**
> （依据：DSH `tool-cordis` README 与 `agent-scope-contexts` 笔记，见 `AGENTS.md` E-04）。
> **请只在你信任的仓库与本机上安装和运行。** 本项目默认**不联网**、**不采集遥测**。

dsh-coderag 是给 DeepSeek Harness（DSH）用的**代码库检索引擎**，以 MCP 服务器形态运行：
让 Agent 能按「行为描述」直接找到代码，而不是靠猜关键词反复 `grep`。**它只读你的代码，不改。**

---

## 项目功能概述

- **4 个 MCP 工具**（固定，不动态增删）：`code_search`（按自然语言或标识符检索，返回**文件路径 + 行号 + 符号名**）、
  `code_outline`（单文件的符号大纲）、`code_index`（建/刷新索引，**立刻返回 taskId**，后台执行）、
  `index_status`（索引状态与跳过统计）。DSH 侧看到的完整名字带 `mcp__coderag__` 前缀。
- **索引**：SQLite **FTS5** + **中文 bigram**，落点 `<工作区>/.coderag/index.sqlite3`；
  用 **tree-sitter** 按函数/类/接口等声明边界分块。**增量索引**——只重算内容哈希变化的文件；
  并发度与批大小按 CPU/内存**自适应推导**，不硬编码；文件数超上限**显式失败并报实际数量**。
- **检索**：BM25 打分。**选按分数、排按源码顺序**（`ADR-05`）——同一批命中按文件与行号输出，
  便于模型按行号去读原文。召回三级递进：**精度（全部词元）→ 仅标识符 → 含 CJK bigram**；
  纯标点/短符号查询不做全表扫描，而是返回结构化提示引导改用 `grep`。
- **状态永远可解释**：索引未就绪、返回为空、后端不可用时都返回**结构化 `status`**（而非空列表），
  模型不会把"没查到"误读成"不存在"从而编造。
- **安全过滤**：三层（内置密钥黑名单 → `.gitignore`/`.coderagignore` → 内容级正则），
  命中的 chunk **不入库**；**过滤结果对模型可见**（`skipped: {count, reasons}`）。
- **异步与预算**：`code_index` 立刻返回、后台执行（避开工具调用 60 秒超时）；
  单次检索有 token 预算，超出部分**显式报告**省略条数而不是静默截断。

---

## 装上之后能带来多少提升（实测）

在一份 DSH 源码副本（**3967 文件 / 63046 chunk**）上，用同一套 **13 个「找代码」任务**各跑 **3 次**
（共 78 个真实模型会话），对比两个**同配置**的 headless DSH 实例：

- **A 组**：纯净 profile（`dsh-base` + `dsh-headless`），只有基础的 `bash` / `grep` / `glob` / `read`。
- **B 组**：**同一个 profile**，只多挂一层本插件的 patch（多出 `code_search` 等 4 个工具）。

| 指标 | A · 不装 | B · 装了 coderag | 差 |
|---|---:|---:|---:|
| **任务成功率**（39 次尝试） | 11/39 = **28.2%** | 32/39 = **82.1%** | **+53.8pp** |
| 95% Wilson 区间 | [0.165, 0.438] | [0.673, 0.910] | **不重叠** |
| 用例级「至少做对一次」 | 4/13 = 30.8% | **13/13 = 100%** | +69pp |
| 「三次全做对」 | 3/13 = 23.1% | **7/13 = 53.8%** | +30.7pp |
| 平均步数 | 5.6 | 5.8 | +0.2 |
| **中位 token / 次** | 80,072 | **72,909** | **−8.9%** |
| 总 token（39 次） | 6,169,545 | 6,697,966 | +8.6% |
| **token / 每个做对的任务** | 560,868 | **209,311** | **−62.7%** |
| 用过 `code_search` 的用例 | 0/13 | 12/13 | +12 |

按问题类型拆开看，提升集中在「**用中文描述、答案在英文代码里**」的那两类：

| 问题类型 | A · 不装 | B · 装了 coderag |
|---|---:|---:|
| `locate`：描述行为，定位常量/文件在哪 | **0/12** | **9/12** |
| `crossfile`：跨文件链路（定义处 → 使用处 → 封锁处） | **0/15** | **12/15** |
| ↳ 其中 `semantic-gap`：中文意图 ↔ 英文代码**零词法重叠** | 0/3 | **3/3** |
| `identifier`：直接给标识符 | 6/6 | 6/6 |
| `regression`：标识符直查，装了不该变慢变差 | 6/6 | 6/6 |
| `negative`：仓库里根本不存在的东西，不该被编造 | 5/6 | 5/6 |

**一句话**：不装插件时，Agent 在这 27 次「用中文问、答案在英文代码里」的定位/跨文件尝试中
**一次都没找对（0/27）**；装上之后 **21/27**。而且**简单直查题、回归题、反臆造题都没有变差**
（`identifier` 与 `regression` 两组满分不变，`negative` 仅一条 3/3 变 2/3）。

**成本上它不亏**：典型一次查询的**中位 token 反而降了 8.9%**（不再反复 `grep`），总量只涨 8.6%
（多出来的就是检索回来的代码片段），**折算到「每个做对的任务」便宜 62.7%**。

> **口径（请一起读）**：这 13 个任务**刻意偏向"需要检索"的那一类**（`locate` + `crossfile` +
> `semantic-gap` 占 10/13），所以 **+53.8pp 不是真实流量上的提升幅度**——真实提问里有大量精确标识符，
> 那些本来就不需要检索（上表 `identifier` 组差值为 0 正是证据）。它回答的是
> **「当问题确实需要检索时，装与不装差多少」**。样本为单一语料、单一模型、13 条题 × 3 次；
> 3 次尝试不独立（同题重跑），真实置信区间比 Wilson 更宽。
> 原始数据：[`eval/runs/clean-a3/report.md`](eval/runs/clean-a3/report.md)（A 组）／
> [`eval/runs/clean-b3/report.md`](eval/runs/clean-b3/report.md)（B 组）。

---

## 安装

**前置**：Python **3.10–3.12**（`requires-python = ">=3.10,<3.13"`）、
[DSH](https://www.npmjs.com/package/@deepseek-ai/dsh)、Git。
**pnpm 不用自己准备**：`dsh` 自带一个（实测：Windows 的 `PATH` 上**没有** pnpm，
`dsh plugin add` 仍用自带的 pnpm 11.7.0 正常完成）。

> **发布方式：只发布在 GitHub**（tag / release），**不发布到 PyPI、也不发布到 npm**。
> 因此安装只能走下面这条「克隆」路径；`pip install dsh-coderag` 与 `npm i dsh-coderag` 都**不可用**。
> **当前版本 `2.1.1` 同样只在 GitHub 上以 tag / release 发布**（`v2.1.1`），PyPI 与 npm 上没有任何版本。

> **平台状态（实测，2026-09-30）**：**macOS 26.4** 与 **Windows 10（26100，`win_amd64`）** 已实测通过——
> 安装、`dsh plugin add`、`--dump-config` 与一次真实 `code_search` 两边都跑通，两边的全量 `pytest` 也通过。
> **Linux 尚未实测，因此本项目不声称支持 Linux。**
> 三份证据：[跨平台基线](docs/m6-crossplatform-baseline.md)（依赖 wheel、FTS5、离线 grammar、MCP 子进程）、
> [macOS 复核](docs/m6-macos-verification.md)、[Windows 冒烟](docs/m6-windows-smoke.md)。
> 计划与判据见 [`PROJECT.md`](PROJECT.md) §6.5.1（`T6-01`–`T6-05`）。

### macOS / Linux（POSIX shell）

```sh
# 1. 克隆（cordis.patch.yml 在仓库里，必须克隆）
#    ⚠️ 克隆会落在你**当前所在目录**下新建的 dsh-coderag/ 里——先 cd 到想放的位置。
cd ~                         # 不 cd 的话就落在你打开终端时的那个目录
git clone https://github.com/VermilionPasvikin/dsh-coderag.git
cd dsh-coderag
# 想自己指定目录名：git clone <url> my-coderag && cd my-coderag

# 2. 装引擎并自检：这个薄包装只做「找到解释器 → 转发给 Python CLI 的 install-deps」
bash scripts/install.sh          # 受限网络：CODERAG_PIP_ARGS="--index-url <镜像>" bash scripts/install.sh

# 3. 验证引擎可用（这一步不涉及 DSH）
"$CODERAG_PYTHON" -m dsh_coderag doctor     # 打印可复制的 CODERAG_PYTHON
"$CODERAG_PYTHON" -m dsh_coderag index /path/to/repo
"$CODERAG_PYTHON" -m dsh_coderag search "用户令牌在哪里校验" --root /path/to/repo

# 4. 挂插件（推荐）：把本仓库注册成 web profile 的一层，然后确认
./scripts/dsh plugin --profile web add .
./scripts/dsh --profile web --dump-config | grep -A2 '== dsh-coderag'
# 期望：先出现 # == dsh-coderag，紧接着 - id: coderag（设置行）与 - id: mcp-coderag（执行器）

# 5. 启动（web 应用来自 profile 自带的 @deepseek-ai/dsh-web-app）
./scripts/dsh --profile web
```

### Windows（PowerShell）

> **先确认两件事，它们决定了后面每条命令怎么写。**

**① 你手上的 `python` 是哪一个。** Windows 上 `python` / `python3` 很可能只是
**Microsoft Store 的占位符**——运行时会打印
`Python was not found; run without arguments to install from the Microsoft Store …`，
那不是你装的那个解释器。所以下面**一律用显式路径变量 `$py`**，不依赖 `PATH`：

```powershell
py -0p                     # 列出本机已注册的解释器（Windows 官方 launcher）
```

**② 你实际在跑的是哪个 DSH profile。** 插件必须注册到**你正在用的那个**，否则装好了也看不到工具：
桌面版跑的是 `desktop`，`dsh web` 用的是 `web`。用 `$env:DSH_PROFILE` 或看
`%USERPROFILE%\.dsh\profiles\` 下有哪些目录来确认；下面用 `$profile` 指代它。

```powershell
# 0. 准备一个 Python 环境（3.10–3.12）。已有 conda / venv 就跳过这步，直接设 $py
& py -m venv "$HOME\dsh-coderag-venv"    # py 会挑一个已注册的解释器；用 py -0p 看它有哪些
$py = "$HOME\dsh-coderag-venv\Scripts\python.exe"
& $py --version                          # 期望：Python 3.10 / 3.11 / 3.12

# 1. 克隆（cordis.patch.yml 在仓库里，必须克隆）
#    ⚠️ 克隆会落在 **PowerShell 当前所在目录**下新建的 dsh-coderag\ 里。
Get-Location                 # 先确认你在哪；常见是 C:\Users\<你>
Set-Location $HOME           # 想放到别处就改这一句
git clone https://github.com/VermilionPasvikin/dsh-coderag.git
Set-Location dsh-coderag
# 不想先 cd，就直接给目录名：git clone <url> C:\src\my-coderag; Set-Location C:\src\my-coderag
# 克隆失败（公司网络 / 代理 / 连接重置）时：在 GitHub 页面下载 ZIP 解压即可，
# 这个仓库不需要 .git 也能装；或在能连通的机器上克隆后把整个目录拷过来。

# 2. 装引擎与依赖：PowerShell 里没有 sh，所以直接用解释器调 pip / CLI
& $py -m pip install .                   # 开发者：& $py -m pip install -e ".[dev,semantic]"
& $py -m dsh_coderag doctor              # 探测解释器 / 版本 / FTS5，并打印可复制的赋值语句

# 3. 验证引擎可用（这一步不涉及 DSH）。$repo 必须换成真实存在的目录
$repo = "C:\path\to\your\repo"           # ← 换成你要索引的目录
& $py -m dsh_coderag index $repo
& $py -m dsh_coderag search "用户令牌在哪里校验" --root $repo

# 4. 把解释器交给 DSH。桌面版是快捷方式启动的、继承不到终端里的变量，
#    所以最可靠的是写进 profile 的 cordis.patch.yml（见「配置」一节的完整示例）。
#    只有「从本窗口启动 dsh」时，下面这一句才够用：
$env:CODERAG_PYTHON = $py

# 5. 先完全退出 DeepSeek Harness 桌面版，再挂插件（见下方说明）
$dsh = "<DeepSeek Harness 安装目录>\resources\runtime\cli\bin\dsh.cmd"   # 或全局 dsh 的路径
& $dsh plugin --profile $profile add .   # $profile 换成你实际在跑的那个（桌面版通常是 desktop）
& $dsh --profile $profile --dump-config | Select-String -Pattern '== dsh-coderag' -Context 0,2
# 期望：先出现 # == dsh-coderag，紧接着 - id: coderag（设置行）与 - id: mcp-coderag（执行器）

# 6. 重新打开桌面版；若你走的是命令行路线则为 & $dsh --profile $profile
```

> **`dsh` 在 Windows 上不一定在 `PATH` 上**（`AGENTS.md` E-07）。可用的写法：
> ① **桌面版自带的 CLI**——`<DeepSeek Harness 安装目录>\resources\runtime\cli\bin\dsh.cmd`
> （本机是 `F:\dsh\...`、版本 `0.2.0-rc.2`，上面第 5 步用的就是它）；
> ② **Git for Windows 的 bash** + 仓库里的薄包装——`bash scripts/dsh --profile $profile`（会回退到钉版本的 npx）。
> 你自己装过全局 `dsh` 的话，`dsh ...` 直接可用。

> **为什么第 5 步要先退出桌面版**：桌面版正在运行时，DSH **拒绝**改动它的 profile——
> `dsh: Error: Open DeepSeek Harness Desktop once to initialize its profile, then fully quit it
> before running dsh plugin --profile desktop.`（本机实测）。改完再打开桌面版即可。
> 注意**不要**把插件注册到一个新起的 profile 名上：那种 profile 只有 `dsh-base` + 本插件、
> **没有 web 应用**，`dsh --profile <新名字>` 起不来界面。

> **为什么第 4 步不能只靠 `$env:`**：`$env:CODERAG_PYTHON` 只对**从同一个窗口启动**的进程有效。
> 桌面版是从快捷方式启动的，读不到你在这个窗口里设的变量——那种情况下 MCP 子进程会去用
> `cordis.patch.yml` 里内置的默认解释器（作者机器的 macOS 路径）而启动失败。
> 所以桌面版用户请把解释器写进 profile 的 `cordis.patch.yml`（见下节）。
> 也可以把它设成**用户级环境变量**再重启桌面版（`[Environment]::SetEnvironmentVariable`
> 的 `User` 作用域；本条未在本机实测）。

> **两条路线的区别（Windows 与 macOS 均实测）**：
> `dsh plugin --profile web add .` 会把**自带的 `web` 模板复制成你的 profile**（`package.json` 里
> `bundles: ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "dsh-coderag"]`）——所以它既能挂上
> 本插件、又保留了 web 应用，`--dump-config` 里会多出 `# == dsh-coderag` 这一层标记。
> 而 `& $dsh --profile web --patch .\cordis.patch.yml` 只是**临时叠加**：dump 里**只有**
> `- id: mcp-coderag`、**没有** `# == dsh-coderag`。**长期使用走 `plugin add`，改 patch 时用 `--patch` 叠加调试。**
> **不要给一个全新的 profile 名（如 `--profile coderag`）当启动目标**——它只拿到 `dsh-base` + 本插件，
> **没有 web 应用**，`dsh --profile coderag` 起不来界面；它只适合拿来 `--dump-config` 验证。

> **为什么 Windows 用 `& $py -m pip install .` 而不是 `install-deps`**：`& $py -m dsh_coderag …`
> 要求包**已经可导入**，而全新 clone 上它还没装。`install-deps` 做的是「装 + 装后自检」，
> 在包可导入之后随时可以重跑它。装了 Git for Windows 的话，也可以直接在 Git Bash 里跑
> `bash scripts/install.sh`（实测可用）。

> **`CODERAG_PYTHON` 不设会怎样**：patch 的兜底是 `python`（Windows）/ `python3`（其它平台），
> 也就是在 `PATH` 上找解释器——**桌面版从快捷方式启动，多半找不到你那个真 Python**
> （Windows 上常见的是 Microsoft Store 占位符），MCP 子进程于是起不来。
> **这个故障是静默的**：插件看起来装好了、`--dump-config` 里也有本插件，但会话里**没有**
> `mcp__coderag__*` 工具。所以第 4 步不是可选项；`& $py -m dsh_coderag doctor` 会打印一段
> **可直接粘贴**的 profile 覆盖块，把它**追加**到你实际在跑的那个 profile 的 `cordis.patch.yml`。

> **`--patch` 的位置**：`--profile` / `--patch` 是**启动器**选项，必须写在 Web 应用自己的选项
> （`--port` / `--no-open` / `--host`）**之前**，否则报 `error: unknown option '--patch'`。
> 正确写法：`./scripts/dsh --profile web --patch ./cordis.patch.yml --port 3099`（实测）。

> **`dsh` 不一定在 PATH 上**，所以 macOS / Linux 上本仓库统一用 `./scripts/dsh`（`AGENTS.md` E-07）；
> 若你已有全局 `dsh`，它等价于直接敲 `dsh`。**Windows 上没有 `sh`，请直接用全局 `dsh`**
> 或 `npx @deepseek-ai/dsh@<钉的版本>`——`./scripts/dsh` 在 PowerShell 里跑不了。
>
> **两个 shell 脚本的平台范围**：`scripts/install.sh`（`bash`）与 `scripts/dsh`（`sh`）是
> **macOS / Linux 用法**；它们只做「找到解释器 → 转发」，安装与自检逻辑都在跨平台的 Python CLI
> （`dsh-coderag doctor` / `install-deps`）里，所以三个平台走的是**同一条代码路径**，
> 而且那条路径能被 `pytest` 直接覆盖。

**怎么确认装上了**——`dsh plugin add` 在 pnpm 非零退出时会**静默跳过 bundle 登记**，
插件看起来装上了却永远不会加载（`AGENTS.md` E-05）。务必自查这一条：

```sh
# macOS / Linux
./scripts/dsh --profile <名字> --dump-config | grep -A2 '== dsh-coderag'
```

```powershell
# Windows（$dsh 的取法见上面「Windows」一节，它不一定在 PATH 上）
& $dsh --profile <名字> --dump-config | Select-String -Pattern '== dsh-coderag' -Context 0,2
```

期望看到 `# == dsh-coderag`，紧随一行 `- id: mcp-coderag`。

| 现象 | 怎么办 |
|---|---|
| `--dump-config` 里没有 `# == dsh-coderag` | bundle 没被登记：回头看 `add` 的 pnpm 报错；若报 `ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED`，把 pnpm 打印的精确 key 写进 `~/.dsh/profiles/<名字>/pnpm-workspace.yaml` 的 `allowBuilds:` 下（`<key>: true`）后重跑 `add` |
| 会话里没有 `mcp__coderag__code_search` | MCP 子进程起不来，最常见是解释器路径。macOS / Linux：`export CODERAG_PYTHON=<真正装了 dsh_coderag 的解释器>`；Windows：`$env:CODERAG_PYTHON = "<同一个路径>"`。用 `python -m dsh_coderag --version`（或 `"$CODERAG_PYTHON" -m dsh_coderag --version`）确认。**桌面版请改 profile 的 `cordis.patch.yml`**——快捷方式启动读不到终端变量（见「配置」） |
| `pip install` 报 `externally-managed-environment` | PEP 668：用 conda 或 venv；**不要**用 `--break-system-packages` |
| 中文检索总是空 | 该解释器的 SQLite 没编译 FTS5：macOS / Linux 上 `bash scripts/install.sh`、Windows 上 `python -m dsh_coderag install-deps` 都会预检并给指引 |

更完整的安装实录与边界见 [`docs/m4-install-verification.md`](docs/m4-install-verification.md)。

## 配置

**运行时参数只从环境变量读**，唯一入口是 `src/dsh_coderag/config.py`，没有用户配置文件。
**DSH 侧的推荐入口是本插件的原生设置页**（见下一小节「原生设置页」）：它把参数写进 profile 的
`coderag` 行，再由 Host 同步成 MCP 行的 `config.env`。CLI 不读设置页，仍只认当前 shell 的环境变量。

stdio 子进程的环境会被清洗：**继承来的**环境里，匹配 `*KEY*` / `*PASSWORD*` / `*SECRET*` / `*TOKEN*`
的变量与**所有** `DSH_*` 变量都会被删除。清洗之后，`cordis.patch.yml` 的 `config.env` 会**合并到最上面**
（已核实：`{...scrubbedParentEnv(), ...extra}`）——所以**写进 patch 的一定到得了子进程，在 shell 里设的不一定**。

**`$DSH_HOME` 在哪**——上面那些路径里的 `$DSH_HOME` 指的是 **DSH 的"主目录"**，
本机的 profile、会话与凭据都住在它下面：

| 平台 | 默认位置 | 怎么确认 |
|---|---|---|
| Windows | `%USERPROFILE%\.dsh`（例如 `C:\Users\<你>\.dsh`） | `$env:DSH_HOME`；若为空则 `Test-Path "$env:USERPROFILE\.dsh"` |
| macOS / Linux | `$HOME/.dsh` | `echo "${DSH_HOME:-$HOME/.dsh}"` |

- **换位置只有一种办法：设环境变量 `DSH_HOME`。** 依据是 DSH 自己的帮助文本——
  `--profile <name>` 的说明是 *"the profile under `$DSH_HOME/profiles` to boot"*，
  而 `dsh --help` 里**没有** `--home` 之类的选项（所以也不存在 XDG 之类的另一套路径，别去找）。
- **在 DSH 里开出来的终端，`DSH_HOME` 总是有值**：DSH 进程会把它设好再传给子进程
  （本机实测：系统级的 User / Machine 作用域里它是**空的**，值来自 DSH 进程本身）。
- 目录里除了 `profiles/`，还有 `sessions/`、`storages/` 与 **`.credentials.yaml`**（DSH 自己的凭据）
  ——所以这是**本机机密目录**，别把它整个拷进任何仓库或共享目录。
- 与本插件有关的只有两个文件：**该 profile 的** `$DSH_HOME/profiles/<profile>/cordis.patch.yml`
  与 **对所有 profile 生效、优先级更高**的 `$DSH_HOME/cordis.patch.yml`（下一张表）。
- 不确定自己在跑哪个 profile：看 `$env:DSH_PROFILE`，或列 `$DSH_HOME/profiles/` 下的目录名。

**配置写在哪**（按推荐顺序）：

| 写在哪 | Windows 上的路径 | 适合什么 | 会不会入库 |
|---|---|---|---|
| **原生设置页**（设置 → CodeRAG；或 Plugins → dsh-coderag） | 落盘位置：`%USERPROFILE%\.dsh\profiles\<profile>\cordis.patch.yml` 的 `coderag` 行 | **最推荐**：13 个常用参数，保存即热重载 MCP 子进程 | ❌ 仓库之外，不会 |
| profile 的 `cordis.patch.yml` | `%USERPROFILE%\.dsh\profiles\<profile>\cordis.patch.yml` | 本机持久设置，**包括密钥字面值**；设置页不管理的 4 个变量写在这里 | ❌ 仓库之外，不会 |
| `$DSH_HOME/cordis.patch.yml` | `%USERPROFILE%\.dsh\cordis.patch.yml` | 同上，且**优先级更高**（对所有 profile 生效） | ❌ 仓库之外，不会 |
| 启动 dsh 的那个 shell | `export X=...`（macOS / Linux）／`$env:X = "..."`（PowerShell） | 只对"名字不含 `KEY/PASSWORD/SECRET/TOKEN`"的变量有效；**只活到窗口关闭** | ❌ 不涉及文件 |
| 仓库里的 `cordis.patch.yml`（`env:` 块） | 同左 | 非密钥的默认值；**密钥只能用 `!!js` 表达式** | ⚠️ 会（**`RL-02`：绝不能写真实 key**） |

> **哪些变量在 shell 里设不生效**：名字里含 `TOKEN` 的 `CODERAG_MAX_TOKENS` 会被清洗掉；云端的 API key 同理。
> 这两个**必须**写进上面任一处 patch 的 `env:` 里。`CODERAG_ROOT` 与 `CODERAG_PYTHON` 例外——
> 它们在 `cordis.patch.yml` 里已被 `!!js` 引用，由宿主进程读取**启动 dsh 的那个进程**的环境
> （PowerShell 用 `$env:CODERAG_PYTHON = $py`，macOS / Linux 用 `export CODERAG_PYTHON=...`）。
> **桌面版是从快捷方式启动的，读不到你在终端里设的变量**，所以桌面版用户请把解释器写进下面的 `env:`。

### 原生设置页（推荐）

DSH **0.1.7-rc.1 起**（本仓库在 **0.2.1-rc.3** 上实测）插件可以在原生 UI 里提供自己的设置页。
本插件提供**三个入口**，内容完全一致（13 个字段）：

1. **设置 → CodeRAG**（`settings.section`，主入口）——一点就行，不经过任何 README；
2. **Plugins → dsh-coderag → `coderag` 行 → 配置**（`plugins.row.config`）；
3. **Plugins → dsh-coderag 详情页**里的「CodeRAG 参数设置」表单（`plugins.bundle.config`，附加入口）。

保存会写进当前 profile 的 `cordis.patch.yml`（`coderag` 行），Host 半侧再把它同步成
`mcp-coderag` 行的 `config.env`，MCP 行随即重挂载、**Python 子进程以新环境重启**。
**实测热重载**：在一个真实 DeepForge 实例里改 `root` 后，**1.5 秒**内模型调
`mcp__coderag__index_status` 返回的 `root` 已是新目录；再改回后约 2 秒内恢复。
不需要手工改 YAML，也不需要重启 DSH。

| 表单字段 | 写入的环境变量 | 空值/0 的含义 |
|---|---|---|
| 工作区根 `root` | `CODERAG_ROOT` | 省略；引擎明确报 `WORKSPACE_INVALID`，不猜目录（`T6-26`） |
| 文件数量上限 `maxFiles` | `CODERAG_MAX_FILES` | 省略，用引擎默认 20000 |
| 单文件字节上限 `maxFileBytes` | `CODERAG_MAX_FILE_BYTES` | 省略，用引擎默认 1 MiB |
| 检索 token 预算 `maxTokens` | `CODERAG_MAX_TOKENS` | 0 = 省略，用引擎默认 4000（名字含 `TOKEN`，只能显式投递） |
| 额外文件扩展名 `extraExtensions` | `CODERAG_EXTRA_EXTENSIONS` | 省略；只增不减，密钥黑名单仍生效（`RL-03`） |
| 启用语义检索 `semantic` | `CODERAG_SEMANTIC` | 关闭 = 省略；开启 = `on` |
| 语义后端 `semanticBackend` | `CODERAG_SEMANTIC_BACKEND` | 省略，用引擎默认 `ollama`；云端选 `openai` |
| 语义服务 URL `semanticUrl` | `CODERAG_SEMANTIC_URL` | 省略；本地后端只允许 loopback |
| 语义模型 `semanticModel` | `CODERAG_SEMANTIC_MODEL` | 省略，本地默认 `bge-m3` |
| 语义请求超时 `semanticTimeout` | `CODERAG_SEMANTIC_TIMEOUT` | 0 = 省略，默认 30 秒 |
| 语义批量大小 `semanticBatch` | `CODERAG_SEMANTIC_BATCH` | 0 = 省略，默认 16 |
| 向量化 chunk 上限 `semanticMaxChunks` | `CODERAG_SEMANTIC_MAX_CHUNKS` | 0 = 省略，默认 100000（云端首次索引的计费上限） |
| 允许非 loopback 云端地址 `semanticAllowRemote` | `CODERAG_SEMANTIC_ALLOW_REMOTE` | 关闭 = 省略；开启 = `1`（仅云端 openai + 非 loopback 需要） |

**只有 `CODERAG_SEMANTIC_API_KEY` 不在设置页里**（也不会有、不应该有 API key 字段）：
key 继续写在 patch 的 `env:` 或启动 dsh 的 shell 里（`RL-02`/`S-05`：key 只从环境或本机配置层读，
不入库、不入日志、不进浏览器表单）。表单对「语义检索 + openai + 非 loopback URL」会强制要求打开
`semanticAllowRemote`，与引擎的 `ALLOW_REMOTE=1` 双重开关一致（`ADR-17` §1.3）。

**行为与边界**：

- **保存**把 13 个字段一起写进 `coderag` 行（包括打开页面时显示的环境默认值），所以 bundle 里
  `!!js` 读到的 shell 值不会因为“只改了一项”而在下次启动时丢失。
- **保存即热重载**（本机实测）：保存后 Loader 以 volatile 方式提交设置行，
  Host 同步 MCP 行 env、MCP 行重挂载、Python 子进程重启；**1.5–2 秒**内 `index_status` 已返回新 `root`。
  页面提示为「已保存，MCP 已按新环境热重载」。
- **恢复默认**把表单恢复成 `base`（bundle 层 / 环境变量解析出的值），再点保存才生效。
- **非法值**先在浏览器里逐字段拒绝（非整数、`a.b` 这类扩展名、cloud 缺 URL/模型、本地后端配非 loopback URL、
  云端非 loopback 未开 `semanticAllowRemote`），Host 的 schemastery 再校验一次；失败时会显示错误，
  不会写进 mcp 行。
- **首次保存前**，profile 里已经手写在 `mcp-coderag` 行 `env` 里的旧配置**不会被清掉**：Host 只在
  “设置里至少有一个非空值”时才做启动同步。**第一次保存之后**，这 13 个变量以设置页为唯一来源
  （旧 `env` 里的同名项会被覆盖或删除），只有 `CODERAG_SEMANTIC_API_KEY` 始终原样保留。这是有意的取舍，
  见 [`docs/settings-ui-plan.md`](docs/settings-ui-plan.md) §4.3。
- 启动同步时若设置来自 shell 环境变量，MCP 子进程可能先以旧环境启动一次、随后被设置同步重启一次；
  之后保存都是即时重启。
- 用 CLI（`dsh-coderag index/search`）时**仍然只读当前 shell 的环境变量**，不读这份设置
  （见下文「谁读哪份配置」）。
- DSH 版本不支持这些 slot（`settings.section` / `plugins.row.config` / `plugins.bundle.config`）时页面不会出现；
  此时照旧用下面的 `env:` / shell 变量配置，功能不受影响。

**手工验收（黑盒）**：

1. 重启 DSH → 打开 **设置 → CodeRAG**（或 Plugins → dsh-coderag），第一屏即可见 13 个字段。
2. 填工作区根 → 保存 → 页面显示「已保存，MCP 已按新环境热重载」；profile 的 `cordis.patch.yml`
   出现 `- id: coderag` 且含 `root:`。
3. 让模型调 `mcp__coderag__index_status` → 返回的 `root` 是新目录、状态不再是 `WORKSPACE_INVALID`。
4. 把文件上限改成 `-1` 或把扩展名改成 `a.b` → 页面就地报错，保存被拒绝。
5. 点「恢复默认」→ 表单回到默认值 → 保存 → `coderag` 行的 `config` 被移除，行为回到环境变量/引擎默认。

### 运维面板（云端 Key / 后端连通性 / 向量库）

设置 → CodeRAG 的参数表单下面还有三块运维区（只读状态 + 受控操作）：

1. **云端 API Key**
   - 状态只显示「已配置（不可查看）」/「未配置」，输入框是密码框，**保存后立即清空**；
     删除需要二次确认。
   - 值只写进 DSH 的 **credentials 服务**（reference 固定为 `CODERAG_SEMANTIC_API_KEY`），
     **不写 profile patch、不回读、不显示**；Host 同步 MCP 行和启动 admin 子进程时用
     `credentials.resolve` 取它。key 不会出现在任何 state/错误响应或日志里。
   - 保存/删除后自动调用 Host 的 `refresh` 动作，把新 key 同步进 `mcp-coderag` 的 env。

2. **语义后端**
   - 「检查本地连通性」/「检查云端连通性」分别调用 admin `health`；
     使用已保存的 URL/model/key，云端检查会按 `openai` 后端覆盖。
   - 「一键启动本地后端」会 detached 启动 `ollama serve`，并轮询 `http://127.0.0.1:11434/api/tags`
     ≤15 秒；成功/失败都有状态行，失败弹出可关闭的错误弹窗（显示 admin 的结构化 `message`）。
   - 前提：本机装了 `ollama`（可选后端，默认关闭）。

3. **向量数据库**
   - 状态卡显示：索引/向量库存在性、模型与维度、总 chunk、已向量化、待向量化、过期 chunk、
     检查点数量、生成时间；数据来自 admin CLI（`python -c` 启动器加载 `dsh_coderag.admin`）
  的 `status --root <已保存的 root>`。
   - 「向量化增量」/「开始向量化」启动 admin `vectorize` 子进程；运行中显示进度条与
     `embedded/total` 数字，可「停止」（SIGTERM，检查点保留，下次从检查点恢复）。
   - 完成后自动刷新状态卡；有未保存的参数改动时提示先保存（任务使用已保存的 root）。
   - 依赖 T7-01 的 admin CLI（`src/dsh_coderag/admin.py`）；进程退出码/错误事件会变成
     可关闭的错误弹窗，不会把 key 放进消息。

> **⚠️ 云端 embedding 会外发数据**（与「③ 云端 embedding 后端」同一套要点，`D-08`）：
> 外发已入库 chunk 文本**及上下文前缀行（含文件路径与符号名）**；被三层过滤拦下的密钥文件
> 不会外发；按 token 计费，首次索引是**全量支出**；合规自负；key 只从环境 / 仓库之外的
> 本机配置层 / DSH credentials 读，不入库、不入日志或状态；非 loopback 必须同时设
> `CODERAG_SEMANTIC_ALLOW_REMOTE=1` 并建议 `https://`。

**安全性**：三条运维路由（`GET /coderag-admin/state`、`POST /coderag-admin/action`、
`GET /coderag-admin/job`）只在 Web profile 注册，并且每个请求都过 `connection.requestRejection`
（与 GUI 其他 API 同一信任边界）；响应永远是 `{ok,value}` / `{ok:false,error}`，
state 中只有 `config.key_present`，没有 key 值。

**Windows 上写到一个持久位置**——打开 `%USERPROFILE%\.dsh\profiles\<你实际在跑的 profile>\cordis.patch.yml`
（该文件由 `dsh plugin --profile <profile> add .` 生成），把下面这段放进去。**参数本身建议留在设置页**，
这里只覆盖解释器与执行器字段：

```yaml
- id: mcp-coderag
  config:
    serverName: coderag
    transport: stdio
    command: 'C:\Users\<你>\dsh-coderag-venv\Scripts\python.exe'
    args: ['-c', 'import dsh_coderag.server as s; s.run()']
    env: {}
```

> 工作区根与全部 `CODERAG_*` 参数优先在 **设置 → CodeRAG** 里配；如果确实要写死在 `env:` 里，
> 请写完整字段（DSH 的 patch 是整体替换），并把工作区根显式写成绝对路径
> （`CODERAG_ROOT: 'F:\src\my-repo'`）——**不要用 `process.cwd()`**，那是 DSH 自己的目录（`T6-26`）。

> **两种情形写法不同（都实测过）**：
> ① 文件里**只有占位符 `[]`**（全新 profile 的初始内容）→ 用上面这段**替换掉那一行**；
> ② 文件里**已有条目** → **追加**到末尾，**不要替换整个文件**。
> `[]` 后面直接接列表项会变成**非法 YAML**，`--dump-config` 会报错——本机实测。
> 而第 ② 种情形必须用追加，因为这个文件**不是你一个人的**：它是该 profile 的**用户层**，DSH 自己也会往里写
> ——本机实测它里面本来就有 `ui-settings-general`（欢迎提示版本）与 `agent-preset-registry`（agent preset）。
>
> `& $py -m dsh_coderag doctor` 会把上面这段**按本机解释器生成好**并直接打印出来，照抄即可
> （它也会提示这两种情形）。
>
> 改完用 `& $dsh --profile <profile> --dump-config` 确认组合结果里同时还有 `# == dsh-coderag`。

> **覆盖 `mcp-coderag` 时注意：DSH 的 patch 是「整体替换」而不是深合并**——DSH schema 自己的说明就是
> *"A patch config replaces the whole config."*。**实测**：只写 `config.env` 一项去覆盖
> `mcp-coderag` 时，`serverName` / `transport` / `args` 会**从结果里消失**。所以上面那个例子把要保留的
> 字段**全部重写**了一遍；`CODERAG_SEMANTIC_API_KEY`（唯一不由设置页管理的变量）若要写进 `env:`，
> 也必须把其它 env 项抄全。

| 变量 | 作用 | 默认 | **生效情况** |
|---|---|---|---|
| `CODERAG_PYTHON` | 运行 MCP 服务器的解释器路径 | `python` / `python3`（走 `PATH`；**桌面版请覆盖成绝对路径**，见 `doctor` 打印的块） | ✅ 由 DSH 读（patch 里的 `!!js`） |
| `CODERAG_ROOT` | 要索引的工作区根 | **无默认**（未设即 `WORKSPACE_INVALID`，不猜 DSH 自己的目录） | ✅ MCP 服务器读它决定工作区 |
| `CODERAG_MAX_TOKENS` | 单次检索返回的 token 预算 | `4000` | ✅ 作为 `code_search` 的**默认**预算；某一次调用传入 `max_tokens` 参数仍可覆盖它；设置页可改 |
| `CODERAG_MAX_FILES` | 文件数上限，**超限显式失败**并报实际数量（不静默截断） | `20000` | ✅ 建索引时生效；`index_status` 在超限时返回 `INDEX_TOO_MANY_FILES` + 实际数量 |
| `CODERAG_MAX_FILE_BYTES` | 单文件大小上限，超过则跳过并计入 `skipped.too_large` | `1048576`（1 MiB） | ✅ 建索引时生效，且 `index_status` 的 `skipped` 统计与它一致 |
| `CODERAG_BATCH_SIZE` | 索引写库批大小（不设则自适应推导） | 自适应（1–512） | ✅ 建索引时生效 |
| `CODERAG_MAX_WORKERS` | 索引并发度（不设则按 CPU/内存推导） | 自适应（上限 8） | ✅ 建索引时生效 |
| `CODERAG_EXTRA_EXTENSIONS` | **追加**可索引的文件后缀（内置白名单**不可移除**） | 空（只有 `.py` `.c` `.h` `.cpp` `.hpp` `.ts` `.js`） | ✅ 建索引与 `index_status` 都生效；逗号或空格分隔，如 `.mxml,.as`；**密钥过滤不受影响** |

**要收录别的格式**（游戏资产 `.mxml`、模板、`.as` 之类）——设 `CODERAG_EXTRA_EXTENSIONS` 即可，
不用改代码：

```powershell
$env:CODERAG_EXTRA_EXTENSIONS = ".mxml,.as"      # 桌面版请写进 profile 的 cordis.patch.yml
& $py -m dsh_coderag index $repo                 # 空索引时的那条提示会列出**生效的**白名单
```

- **只增不减**：内置的 7 个后缀去不掉；`CODERAG_EXTRA_EXTENSIONS` 写错（含点号的 token、路径分隔符、
  通配符）会**报错**而不是被静默忽略——`Path.suffix` 只取最后一段，`a.d.ts` 这类写法永远匹配不上。
- **没有 grammar 的后缀按固定行数切分**：tree-sitter 只认识有限的语言，`.mxml` 这类会走 L4 规则
  按固定行数切块，`symbol_kind` 为 `None`（渲染出来没有 `[符号名]` 标注）——能检索、能命中，
  但没有声明边界这一层信息。（`Chunk.low_confidence` 字段目前**只存在于内存**：不入库、也不渲染，
  见 [`docs/backlog.md`](docs/backlog.md)。）
- **不会绕过密钥过滤**：扩展名闸门在第 1 层黑名单**之前**，所以 `.env.local` / `*.pem` /
  `credentials*` 即使把后缀加进白名单**也仍然不入库**（`RL-03`，有测试钉住）。

> **这些变量曾经在 MCP 路径上全部不生效**（`config.py` 读了，但 `server.py` 建索引时没把配置传下去、
> 检索预算还硬编码 4000），`v2.1.0` 发布时如实标注为 ⚠️。**已在 `T6-07` 修好接线并补了 3 条测试**——
> 这 3 条测试在修复前会红（`assert 2 == 1`、命中数未被裁剪），因此这条路径不会再次静默失效。
> `T6-17` 又把同一条配置通路接进了 **CLI**（此前 `dsh-coderag index` 完全不读这些变量）。

#### 子进程的工作区根是谁定的（**GUI 里打开哪个文件夹不算**）

`CODERAG_ROOT` 决定 MCP 子进程去哪个目录找 `.coderag/index.sqlite3`。它按这个顺序取值：

1. `CODERAG_ROOT`（环境里或 profile 的 `cordis.patch.yml` 里）→ 用它。**桌面版必须显式钉死**，见下；
2. **不设就是错误**：引擎不会猜一个默认值——唯一能当默认值的只有「本进程的工作目录」，
   而**实测（2026-09-30，`T6-26`）桌面版给 MCP 子进程的正是 `%USERPROFILE%\.dsh\profiles\<profile>`**，
   也就是 DSH 自己的状态目录，**不是**你在 GUI 里打开的那个文件夹（那个实验的结论就是「不能用它」）。
   未设时返回 `WORKSPACE_INVALID`，并说明「唯一候选是引擎自己的工作目录（…），它落在 DSH 的 home 之内」；
   若工作目录不在 DSH home 内，则是简洁的「`CODERAG_ROOT` is required」；
3. 设了但落在 DSH 自己的 home 之内 → 同样 `WORKSPACE_INVALID`（消息写作 `is set to …`），
   状态里给出实际解析到的根。

**实测（2026-09-30，正是这次去掉兜底的原因）**：发行 patch 曾写 `CODERAG_ROOT: !!js process.env.CODERAG_ROOT ?? process.cwd()`，
而这个 `process.cwd()` 由**宿主**求值——桌面版从快捷方式启动时它是
`%USERPROFILE%\.dsh\profiles\<profile>`（**DSH 自己的 profile 目录**），既不是你的仓库，也不是你在 GUI 里打开的文件夹。
证据：该目录按同一白名单走出来正好 `seen=11 / indexable=2 / other=9`，与当时子进程返回的 `files` 块**逐字一致**，
而且**它真的在那个 profile 目录里建了一份 0.1 MB 的索引**；与此同时用户在同一台机器上跑完的
**10.67 GiB** 游戏索引对子进程**完全不可见**，`code_search` 于是返回「没有建立索引」。
现在这条路径的两种结局都不再是静默的：设了根就按你指的工作区工作；没设就明确报错。

**所以桌面版必须显式钉死根**（`env` 里写**字面值**）：

```yaml
    env:
      CODERAG_ROOT: 'F:\你的\工作区\绝对路径'
      CODERAG_EXTRA_EXTENSIONS: '.mxml'
      CODERAG_MAX_FILES: '200000'      # 可索引文件超过 20000 时**必须**给，否则子进程自己建索引会报 INDEX_TOO_MANY_FILES
```

三点必须知道：

- **一个 profile 一个根**：`CODERAG_ROOT` 只在**拉起子进程时**求值一次，换工作区得改这一行并**重启桌面版**；
  在 GUI 里换打开的文件夹**不会**改变它。
- **CLI 不吃这一套**：`python -m dsh_coderag index` / `search` 只认**参数**（`index <路径>` / `search --root <路径>`），
  与 patch 无关——所以「CLI 建好的索引」与「子进程要找的目录」是不是同一个，要你自己对齐
  （见上一小节「谁读哪份配置」）。
- **改完要重启**：`--dump-config` 只能验证结构，`!!js` 表达式在 dump 里**不求值**（写成字面值就看得见）。

#### 谁读哪份配置——**CLI 与 DSH 读的不是同一份**

这条决定「你在哪设的变量，谁看得见」，也是最容易踩的一处：

| 谁在跑 | 从哪里读变量 | 看得见 profile 的 `cordis.patch.yml` 吗 |
|---|---|---|
| **MCP 子进程**（DSH 会话里的 `mcp__coderag__*` 工具） | DSH 拉起子进程时注入的环境，**以 patch 的 `config.env` 为准** | ✅ **只有它读得到** |
| **CLI**（你自己敲的 `& $py -m dsh_coderag index` / `search`） | **你当前 shell 的环境** | ❌ **完全不读** |

推论（都是实测过的）：

- 在 shell 里设 `CODERAG_EXTRA_EXTENSIONS`，**CLI 的 `index` 认，DSH 会话不认**；写进 patch 则**反过来**。
  所以**不要把「命令行跑通了」当成「DSH 里也配好了」**。
- 两者写的是**同一个** `<工作区>/.coderag/index.sqlite3`——**谁最后跑 `index`，索引内容就是谁那套配置的
  结果**。只用 shell 变量建好的索引，会被下一次 MCP 侧 `code_index` 按 patch 的配置重建成「不含那些后缀」的版本。
- 想让**两边一致**：把共享设置写进**两处**，或者用**用户级持久环境变量**
  （`[Environment]::SetEnvironmentVariable('X','v','User')`）——CLI 直接继承，桌面版**重启后**继承、
  再由 patch 里的 `!!js process.env.X` 转发给子进程。（这条是机制推论，未在你的桌面上实测。）
- **`CODERAG_PYTHON` 只对 DSH 有意义**：它在 patch 里由宿主侧求值、决定拉起哪个解释器；
  CLI 用哪个解释器由**你敲的命令**决定（`& $py …`）。
- **`CODERAG_ROOT`**：CLI 的根来自**参数**（`index <路径>` / `search --root <路径>`），不设它也照常工作；
  DSH 侧的根来自设置页（`coderag` 行的 `root`）或 patch/env 的 `CODERAG_ROOT`——**没有默认值**，
  未设时引擎返回 `WORKSPACE_INVALID`（`T6-26`），不会拿 DSH 自己的目录猜一个根。
- ⚠️ **一处已知缺口**：CLI 的 `search` **不读** `CODERAG_MAX_TOKENS`——实测 `CODERAG_MAX_TOKENS=5`
  与不设该变量时输出**逐字相同**，它只认 `--limit`，token 预算恒为默认 4000。已登记 `docs/backlog.md`。

### 三类常见配置，照抄即可

每一类都给 **PowerShell** 与 **POSIX** 两种写法。先记住上面那张表的区别：
**在终端里设，只对「从这个终端启动的 dsh」有效；桌面版是从快捷方式启动的，读不到终端变量，
必须写进 profile 的 `cordis.patch.yml`。** 桌面版最省事：`& $py -m dsh_coderag doctor` 会打印一段
可直接粘贴的覆盖块，把下面这些变量加进它的 `env:` 即可。

#### ① 让引擎收录别的文件类型（扩展白名单）

内置白名单固定为 `.py` `.c` `.h` `.cpp` `.hpp` `.ts` `.js`；`CODERAG_EXTRA_EXTENSIONS` 在这之上
**只追加**（去不掉内置项）。**要加多个类型，下面三种写法实测完全等价**（逗号 / 空格 / 大小写 / 点号随意）：

| 写法 | 结果 |
|---|---|
| `$env:CODERAG_EXTRA_EXTENSIONS = ".mxml,.as,.glsl"` | 三个都收 |
| `$env:CODERAG_EXTRA_EXTENSIONS = ".mxml .as .glsl"` | 同上 |
| `$env:CODERAG_EXTRA_EXTENSIONS = " .MXML, AS ,glsl "` | 同上 |

空项会被忽略（`".mxml,,.as"` 等价于 `".mxml,.as"`）；写成数组（`= ".mxml", ".as"`）
会被 PowerShell 折成空格分隔的字符串、能用，但不如直接写一整串带引号的清楚。

```powershell
$env:CODERAG_EXTRA_EXTENSIONS = ".mxml,.as,.glsl"
& $py -m dsh_coderag index $repo          # 改完要重新索引一次才生效
```

```sh
export CODERAG_EXTRA_EXTENSIONS=".mxml,.as,.glsl"
"$CODERAG_PYTHON" -m dsh_coderag index /path/to/repo
```

```yaml
# 桌面版：写进 profile 覆盖块的 env
    env:
      CODERAG_ROOT: !!js process.env.CODERAG_ROOT ?? process.cwd()
      CODERAG_EXTRA_EXTENSIONS: '.mxml,.as,.glsl'
```

**不要**用 `*`、`*.mxml` 或 `a.d.ts` 这类写法——含通配符、路径分隔符或点号的 token 会**报错**
（退出码 2）而不是被忽略：匹配用的是 `Path.suffix`，它只取最后一段。

> **限制**：**没有扩展名的文件收不进来**（`Dockerfile`、`Makefile` 这类）——`Path.suffix` 对它们是
> 空字符串，而每个 token 都必须以字母或数字开头，所以没法用「空扩展名」表达。需要它们的话目前
> 只能靠 `grep` 之类的方式。已登记在 [`docs/backlog.md`](docs/backlog.md)。

没有 grammar 的后缀按固定行数切分（`symbol_kind` 为 `None`）。

#### ② 本地 embedding 后端（**代码不出机器**）

先装 `semantic` extra——它只含 `numpy`，**默认安装不带它**（`RL-10`）：

```powershell
& $py -m pip install ".[semantic]"        # 开发检出用 & $py -m pip install -e ".[dev,semantic]"
```

```sh
"$CODERAG_PYTHON" -m pip install ".[semantic]"
```

再开开关（**默认关闭；只有 `on` 才算开启**）：

```powershell
$env:CODERAG_SEMANTIC        = "on"                       # 必须正好是 on
$env:CODERAG_SEMANTIC_BACKEND = "ollama"                  # 默认就是 ollama
$env:CODERAG_SEMANTIC_URL    = "http://127.0.0.1:11434"   # 本地后端只允许 loopback
$env:CODERAG_SEMANTIC_MODEL  = "bge-m3"
& $py -m dsh_coderag index $repo                          # 重新索引：这一步才会生成向量
```

```sh
export CODERAG_SEMANTIC=on CODERAG_SEMANTIC_MODEL=bge-m3
"$CODERAG_PYTHON" -m dsh_coderag index /path/to/repo
```

- `_URL` **只允许** `127.0.0.1` / `::1` / `localhost`——指向别处会被**拒绝**（`embed.py` 里最后一道闸）。
  本地后端的全部意义就是"代码不出机器"，所以这条不做成可选项。
- 其它可调项：`_TIMEOUT`（秒，默认 `30`）、`_BATCH`（默认 `16`）、`_MAX_CHUNKS`（默认 `100000`）。
- 本机要先有 Ollama 并拉好模型：`ollama pull bge-m3`。
- ⚠️ **模型上下文决定你能嵌多长的 chunk**：Ollama 会把超长输入**静默截断**到模型的上下文
  （实测 `nomic-embed-text` 为 2,048 token：8,000 / 20,000 / 80,000 字符的输入一律只处理 2,048）。
  引擎现在**自己**按「上下文 × 2 字符」截断并在日志里报数（`semantic_chunk_shortened` /
  `semantic_shortened_summary`），因此损失可见、可决策。选模型时优先看上下文：
  `bge-m3` = 8,192（约 16,384 字符，覆盖常见文件）；`nomic-embed-text` = 2,048（约 4,096 字符，快但会截）。
- **长跑可中断**（`T6-31`）：向量构建每完成一批就把向量**追加**到
  `<root>/.coderag/vectors/cache/<模型>/embed-cache.bin` 并在批末 `fsync`，因此**中断后重跑只补缺失的部分**，
  不再从头再来。检查点按模型分目录、以文本 sha256 为键；换模型不会混用旧向量；被写坏的最后一条记录会被丢弃并把文件截断。
  代价是磁盘上多一份与 `embeddings.npy` 等量的数据（1024 维、41.6 万 chunk 约 1.6 GiB）——不需要时可整目录删除，
  下次构建会重新生成。
- **不声称检索质量**：按 `ADR-14` §10.4 的 `V4`，`natural` 桶 `S@5 = 0.300 < 0.40`，所以这条路径
  默认关闭、也没有随任何版本对外发布。

#### ③ 云端 embedding 后端（**会把代码发出去**）

> **⚠️ 启用前请读完这一段。** 下面这些要点与 [安全与隐私警告](#安全与隐私警告) 里的是同一套
> （`AGENTS.md` `D-08` 要求它随每一处配置出现）：
>
> - **外发内容**：已入库 chunk 的文本，**包括上下文前缀行**（形如
>   `// file: <工作区相对路径> | symbol: <种类 名字> | lines <起>-<止>`）——
>   也就是说**文件路径与符号名也会一并外发**。
> - **不外发的**：三层过滤在入库前执行，被拦下的密钥文件（`.env*`、`*.pem`、`id_rsa*` 等）
>   **从来没有 chunk**，不可能被外发。
> - **不再成立**：本地后端的"代码不出机器"在云端下**不成立**。
> - **费用**：按 token 计费；首次索引对**全量 chunk** 做 embedding，是一次性真实支出。
> - **合规自负**：代码可能是公司资产或含第三方许可限制，**外发前请确认你有权发给该服务商**。
> - **key**：只从环境、**仓库之外**的本机配置层或 **DSH credentials 服务**（同样在本机）读，
>   **绝不**入库、不入日志、不入结构化状态。
> - **传输**：非 loopback 地址必须**同时**设 `CODERAG_SEMANTIC_ALLOW_REMOTE=1`（第二把钥匙），
>   并请使用 `https://`。

```powershell
$env:CODERAG_SEMANTIC              = "on"
$env:CODERAG_SEMANTIC_BACKEND      = "openai"
$env:CODERAG_SEMANTIC_URL          = "https://api.openai.com/v1"   # 必须显式给出
$env:CODERAG_SEMANTIC_MODEL        = "text-embedding-3-small"      # 必须显式给出
$env:CODERAG_SEMANTIC_ALLOW_REMOTE = "1"                           # 非 loopback 的第二把钥匙
$env:CODERAG_SEMANTIC_API_KEY      = "<你的 API key>"
& $py -m dsh_coderag index $repo
```

桌面版（读不到终端变量）写进 profile 的 `cordis.patch.yml`——**该文件在仓库之外**，
所以 key 写成字面值是受支持的（`ADR-17` §4、`RL-02`）；`_URL` / `_MODEL` 在云端后端下**必须显式给出**：

```yaml
    env:
      CODERAG_SEMANTIC: 'on'
      CODERAG_SEMANTIC_BACKEND: 'openai'
      CODERAG_SEMANTIC_URL: 'https://api.openai.com/v1'
      CODERAG_SEMANTIC_MODEL: 'text-embedding-3-small'
      CODERAG_SEMANTIC_ALLOW_REMOTE: '1'
      # 只写在这里；不要贴进任何会被 git 跟踪的文件（RL-02）
      CODERAG_SEMANTIC_API_KEY: '<你的 API key>'
```

后端关闭时（未设 `CODERAG_SEMANTIC=on`）这些值**一概不校验**，所以默认安装永远不会因此起不来。

## 它是怎么工作的

- 引擎是 Python 包 `dsh_coderag`，以 **MCP stdio 服务器**运行。
- DSH 通过内置包 `@deepseek-ai/dsh-mcp-client` 在本机**拉起一个子进程**
  （`dsh_coderag.server` 的 stdio 入口，见 `cordis.patch.yml`），两者用 stdin/stdout 上的
  JSON-RPC 通信，**不经过网络、不监听端口**。
- 索引存放在 `<工作区>/.coderag/index.sqlite3`（SQLite FTS5 + 中文 bigram），
  **不写到工作区之外**（`AGENTS.md` S-03/S-04），并被 `.gitignore` 排除。
- 分块用 **tree-sitter** 按函数/类/接口等声明边界切分；检索用 **BM25**，
  **选按分数、排按源码顺序**（`ADR-05`）。
- 大文件重排/超限保护：文件数超 `CODERAG_MAX_FILES`、单文件超 `CODERAG_MAX_FILE_BYTES`
  都会**显式报告**（进 `skipped` 或直接失败），不静默丢弃。
- 仓库根的 `cordis.patch.yml` 同时充当本地开发 overlay 与**可分发的 bundle patch**：
  `dsh plugin add .` 之后 DSH 的组合配置里会出现 `# == dsh-coderag` 层（实测，见
  [`docs/m4-bundle.md`](docs/m4-bundle.md)）。
- 关于 `dsh plugin add` 的一个坑：pnpm 10+ 遇到依赖带 install/build script 时会拒绝执行，
  并让 `add` **静默跳过 bundle 登记**（插件看起来装了却永不加载）。**本项目不含任何
  install script**，首次 `add` 不会触发它（干净 profile 实测，见
  [`docs/m4-install-verification.md`](docs/m4-install-verification.md)）。

---

## 安全与隐私警告

- **三层过滤**（`AGENTS.md` §4.1，按顺序、缺一不可）：
  ① 内置密钥黑名单（`.env*`、`*.pem`、`*.key`、`id_rsa*`、`.npmrc`、`.ssh/`、`.aws/` …）；
  ② 项目的 `.gitignore` → `.coderagignore`（用 `pathspec`，不自造 gitignore 语义）；
  ③ **内容级正则**（私钥头、`AKIA…`、`sk-…`、`ghp_…`、`xox…`）——命中的 chunk **不入库**，
  且**只记路径与模式名，绝不记录匹配到的内容**。
- **过滤结果对模型可见**：`code_search` / `index_status` 会报告 `skipped: {count, reasons}`，
  避免模型把"被过滤"误读成"不存在"从而编造。
- **默认不联网、不采集遥测、不外发任何数据**（`AGENTS.md` S-01/S-02）。
- **索引只写在工作区内**：`<工作区>/.coderag/index.sqlite3`，且被本仓库的 `.gitignore` 排除。

> ## ⚠️ 云端 embedding 后端的外发风险
>
> 本项目**默认不联网**。仅当你**显式启用**可选的云端 embedding 后端
> （`CODERAG_SEMANTIC=on` **且** `CODERAG_SEMANTIC_BACKEND=openai` **且**
> 非 loopback 地址时还要 `CODERAG_SEMANTIC_ALLOW_REMOTE=1`，条文见
> [`docs/adr/ADR-17-optional-cloud-embedding.md`](docs/adr/ADR-17-optional-cloud-embedding.md)）
> 时，才有下列外发行为：
>
> - **外发内容**：已入库 chunk 的文本，**包括每个 chunk 的上下文前缀行**
>   （形如 `// file: <工作区相对路径> | symbol: <种类 名字> | lines <起>-<止>`）。
>   也就是说**文件路径与符号名也会一并外发**。
> - **仍然受保护的部分**：三层过滤在入库前执行，被拦下的密钥文件（`.env*`、`*.pem`、`id_rsa*` 等）
>   **从来没有 chunk**，不可能被外发。
> - **不再成立的部分**：本地后端承诺的"代码不出机器"在云端后端下**不成立**。
> - **费用**：云端按 token 计费；首次索引会对**全量 chunk** 做 embedding，是一次性真实支出。
> - **合规**：代码可能是公司资产或含第三方许可限制。**外发前请自行确认你有权发给该服务商。**
> - **API key**：只从环境读，**绝不**写进仓库、配置文件字面值、README 示例、测试或日志。
> - **传输**：非 loopback 地址必须显式设 `CODERAG_SEMANTIC_ALLOW_REMOTE=1`，**请使用 `https://`**。

## 已知限制

按 `AGENTS.md` `D-03`/`D-05` 集中列出。每条都指向正文或 [`docs/backlog.md`](docs/backlog.md) 的详情。

| 限制 | 表现 | 详情 |
|---|---|---|
| **只认白名单里的后缀** | 其余文件**根本不参与遍历结果**（不算 skip）；`Dockerfile` / `Makefile` 这类**没有扩展名**的文件任何配置都收不进来 | [① 扩展白名单](#-让引擎收录别的文件类型扩展白名单)、backlog |
| **没有 grammar 的后缀是低置信度分块** | 按固定行数切块，`symbol_kind` 为 `None`；且 `Chunk.low_confidence` **只存在于内存**，不入库、不渲染，模型看不到 | backlog |
| **MCP 子进程的工作区根在启动时确定** | 设置页保存会让 MCP 行重启、以新 env 生效；但一个 profile 同一时刻只有一个根，且 GUI 里打开别的文件夹**不会**自动切换 | 「原生设置页」、上一小节 |
| **`CODERAG_ROOT` 是必填项，且不能靠「会话工作区」自动推导** | 实测桌面版给 MCP 子进程的工作目录是 `%USERPROFILE%\.dsh\profiles\<profile>`，**不是**你打开的那个文件夹；未设或落在 DSH 自己的 home 之内都会返回 `WORKSPACE_INVALID`（状态里带**实际使用的** `root` 绝对路径） | 上一小节 |
| **CLI 与 DSH 读不同的配置来源** | shell 里设的变量 CLI 认、DSH 会话不认；写进 patch 则反过来。两者写同一个索引文件，**谁最后跑 `index` 谁的内容生效** | 「谁读哪份配置」 |
| **CLI 路径没有运行历史** | 中断后 `index_status` 只说「未就绪」，说不出「被中断、跑到多少」 | backlog |
| **`searcher` 不读 `ready`** | 被中断的索引**仍可被搜到**（保留可用性的取舍）：命中可能来自不完整的数据，判断要靠 `index_status` | backlog |
| **大文件默认跳过** | 超过 `CODERAG_MAX_FILE_BYTES`（1 MiB）的文件不入库，只在 `skipped.too_large` 里计数 | 配置章节 |
| **云端后端对超长 chunk 无能为力** | 代码原样发送 chunk 文本、**不截断**；实测一份含几何数据的 89.5 万 chunk 索引里有 **8,270 个超过 3.2 万字符**（≈8k token，多数模型的上限），这些会被服务商拒绝。云端向量化前需先把这类大块从索引里排除 | 配置章节 ③ |
| **可选向量后端默认关闭，且不声称检索质量** | 本地后端只允许 loopback；按 `ADR-14` §10.4 的 `V4`，`natural` 桶 `S@5 = 0.300 < 0.40` | 「② 本地 embedding 后端」 |
| **设置页需要 DSH 支持 `settings.section` / `plugins.row.config` / `plugins.bundle.config`** | 0.1.7-rc.1 起提供（本仓库在 0.2.1-rc.3 实测）；旧版 DSH 里没有这些入口，但 env / patch 配置仍照旧生效 | README「原生设置页」、`docs/settings-ui-plan.md` |
| **首次保存后，设置页接管 13 个变量** | 旧 `mcp-coderag` 行 `env` 里的同名项会被覆盖/删除；只有 `CODERAG_SEMANTIC_API_KEY` 始终原样保留 | `docs/settings-ui-plan.md` §4.3 |
| **设置页把 API key 存在 DSH credentials，而不是设置/patch** | 页面只显示「已配置/未配置」；值由 Host 在同步 MCP 行与 admin 子进程时读取，永不出现在 state/错误/日志里（`RL-02`/`S-05`） | 「运维面板」 |
| **运维路由只在 Web profile 注册** | 需要 `webServer` + `connection` 服务，并用 `connection.requestRejection` 鉴权；headless 只有 env/patch 配置，没有运维面板 | 「运维面板」 |
| **向量化 job 状态只存在于 Host 内存** | DSH 重启会丢失进度视图，但检查点（`.coderag/vectors/`）保留，重跑会从检查点恢复；停止不会删除检查点 | 「运维面板」 |
| **一键启动只支持本机 `ollama serve`** | 只自动拉起 Ollama；其它本地服务或云端需要用户先启动/配置 | 「运维面板」 |
| **运维面板依赖 admin CLI** | 需要 `dsh_coderag.admin`（T7-01）在 MCP 同一解释器里可用；Host 用私有 cwd + `-c` 启动器调用（防 cwd 注入），缺失/失败时面板显示可关闭的结构化错误 | 「运维面板」 |
| **带环境默认值启动时 MCP 子进程可能启动两次** | 先按启动环境起一次，设置同步后再以同一/新环境重启一次；之后的保存都是即时热重载（实测 1.5–2 秒） | `docs/settings-ui-plan.md` §4.3 |

## 文档

| 文件 | 内容 |
|---|---|
| `PROJECT.md` | 项目概况、架构、ADR 表、任务表与进度追踪 |
| `AGENTS.md` | 强制性约束：红线、DSH 环境坑、安全规范、提交规范 |
| `EVAL.md` / `TESTING.md` | 评测方案 / 测试方案 |
| [`docs/architecture.md`](docs/architecture.md) | **已实现**的架构：模块与依赖方向、索引/检索数据流、数据模型、工具契约 |
| [`docs/eval-report-m3.md`](docs/eval-report-m3.md) | M3 的 L1/L2 评测报告（分层指标 + 逐条 diff + 失败归因） |
| [`docs/eval-report-m3c.md`](docs/eval-report-m3c.md) | C 组（混合检索）评测报告与 `V1`–`V4` 判定 |
| [`eval/runs/clean-a3/report.md`](eval/runs/clean-a3/report.md) / [`clean-b3`](eval/runs/clean-b3/report.md) | 本文「装上之后能带来多少提升」的原始数据（洁净组 / 装插件组） |
| [`docs/adr/`](docs/adr/) | 决策记录：`ADR-14`（是否引入向量）、`ADR-15`（执行时机）、`ADR-16`（可选后端形态）、`ADR-17`（云端后端） |
| [`docs/m4-bundle.md`](docs/m4-bundle.md) / [`docs/m4-install-verification.md`](docs/m4-install-verification.md) | 可分发的 DSH bundle 装载实测 / 安装验证实录 |
| [`docs/settings-ui-plan.md`](docs/settings-ui-plan.md) | 原生设置页的方案、Loader/volatile 接口实测结论与 T5 证据 |
| [`docs/pr-settings-ui.md`](docs/pr-settings-ui.md) | 本次改动的 PR 描述草稿 |
| [`docs/backlog.md`](docs/backlog.md) | 已知但未修的缺陷与欠账 |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本变更记录（Keep a Changelog） |
| `cordis.patch.yml` | DSH 接入配置（dev overlay 兼 bundle patch） |

---

MIT，见 [`LICENSE`](LICENSE)。
