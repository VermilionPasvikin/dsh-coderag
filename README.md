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
# 期望：先出现 # == dsh-coderag，紧接着 - id: mcp-coderag

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
# 期望：先出现 # == dsh-coderag，紧接着 - id: mcp-coderag

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
| profile 的 `cordis.patch.yml` | `%USERPROFILE%\.dsh\profiles\<profile>\cordis.patch.yml` | 本机持久设置，**包括密钥字面值** | ❌ 仓库之外，不会 |
| `$DSH_HOME/cordis.patch.yml` | `%USERPROFILE%\.dsh\cordis.patch.yml` | 同上，且**优先级更高**（对所有 profile 生效） | ❌ 仓库之外，不会 |
| 启动 dsh 的那个 shell | `export X=...`（macOS / Linux）／`$env:X = "..."`（PowerShell） | 只对"名字不含 `KEY/PASSWORD/SECRET/TOKEN`"的变量有效；**只活到窗口关闭** | ❌ 不涉及文件 |
| 仓库里的 `cordis.patch.yml`（`env:` 块） | 同左 | 非密钥的默认值；**密钥只能用 `!!js` 表达式** | ⚠️ 会（**`RL-02`：绝不能写真实 key**） |

> **哪些变量在 shell 里设不生效**：名字里含 `TOKEN` 的 `CODERAG_MAX_TOKENS` 会被清洗掉；云端的 API key 同理。
> 这两个**必须**写进上面任一处 patch 的 `env:` 里。`CODERAG_ROOT` 与 `CODERAG_PYTHON` 例外——
> 它们在 `cordis.patch.yml` 里已被 `!!js` 引用，由宿主进程读取**启动 dsh 的那个进程**的环境
> （PowerShell 用 `$env:CODERAG_PYTHON = $py`，macOS / Linux 用 `export CODERAG_PYTHON=...`）。
> **桌面版是从快捷方式启动的，读不到你在终端里设的变量**，所以桌面版用户请把解释器写进下面的 `env:`。

**Windows 上写到一个持久位置**——打开 `%USERPROFILE%\.dsh\profiles\<你实际在跑的 profile>\cordis.patch.yml`
（该文件由 `dsh plugin --profile <profile> add .` 生成），把下面这段放进去：

```yaml
- id: mcp-coderag
  config:
    serverName: coderag
    transport: stdio
    command: 'C:\Users\<你>\dsh-coderag-venv\Scripts\python.exe'
    args: ['-c', 'import dsh_coderag.server as s; s.run()']
    env:
      CODERAG_ROOT: !!js process.env.CODERAG_ROOT ?? process.cwd()
```

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
> 字段**全部重写**了一遍；仓库根 `cordis.patch.yml` 里那条 `env` 的其它项（如 `CODERAG_MAX_TOKENS`）
> 若你也想要，同样要抄进来。

| 变量 | 作用 | 默认 | **生效情况** |
|---|---|---|---|
| `CODERAG_PYTHON` | 运行 MCP 服务器的解释器路径 | `python` / `python3`（走 `PATH`；**桌面版请覆盖成绝对路径**，见 `doctor` 打印的块） | ✅ 由 DSH 读（patch 里的 `!!js`） |
| `CODERAG_ROOT` | 要索引的工作区根 | DSH 进程的工作目录 | ✅ MCP 服务器读它决定工作区 |
| `CODERAG_MAX_TOKENS` | 单次检索返回的 token 预算 | `4000` | ✅ 作为 `code_search` 的**默认**预算；某一次调用传入 `max_tokens` 参数仍可覆盖它 |
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

1. 环境里有 `CODERAG_ROOT` → 用它（**推荐显式钉死**，见下）；
2. 否则用 **DSH 宿主进程的 `process.cwd()`**——桌面版从快捷方式启动时，这个值是
   `%USERPROFILE%\.dsh\profiles\<profile>`（**profile 目录本身**），既不是你的仓库，也不是你在 GUI 里打开的文件夹。

**实测（2026-09-30）**：把根留成 `process.cwd()` 时，子进程报出的工作区是
`C:\Users\15349\.dsh\profiles\desktop`——同一目录按同一白名单走出来正好 `seen=11 / indexable=2 / other=9`，
与子进程返回的 `files` 块**逐字一致**，而且**它真的在那个 profile 目录里建了一份 0.1 MB 的索引**；
与此同时，用户在同一台机器上跑完的 **10.67 GiB** 游戏索引对子进程**完全不可见**，
`code_search` 于是返回「没有建立索引」。

**所以桌面版必须显式钉死根**（`env` 里写**字面值**，不要留 `process.cwd()`）：

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
  DSH 侧的根来自 patch 的 `CODERAG_ROOT`，默认 `process.cwd()`（DSH 启动时的工作目录）。
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
> - **key**：只从环境或**仓库之外**的本机配置层读，**绝不**入库、不入日志、不入结构化状态。
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
| **MCP 子进程的工作区根在启动时就定死** | GUI 里打开别的文件夹**不会**改变它；一个 profile 只有一个根，换工作区要改 patch 并重启 | 上一小节 |
| **CLI 与 DSH 读不同的配置来源** | shell 里设的变量 CLI 认、DSH 会话不认；写进 patch 则反过来。两者写同一个索引文件，**谁最后跑 `index` 谁的内容生效** | 「谁读哪份配置」 |
| **CLI 路径没有运行历史** | 中断后 `index_status` 只说「未就绪」，说不出「被中断、跑到多少」 | backlog |
| **`searcher` 不读 `ready`** | 被中断的索引**仍可被搜到**（保留可用性的取舍）：命中可能来自不完整的数据，判断要靠 `index_status` | backlog |
| **大文件默认跳过** | 超过 `CODERAG_MAX_FILE_BYTES`（1 MiB）的文件不入库，只在 `skipped.too_large` 里计数 | 配置章节 |
| **可选向量后端默认关闭，且不声称检索质量** | 本地后端只允许 loopback；按 `ADR-14` §10.4 的 `V4`，`natural` 桶 `S@5 = 0.300 < 0.40` | 「② 本地 embedding 后端」 |

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
| [`docs/backlog.md`](docs/backlog.md) | 已知但未修的缺陷与欠账 |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本变更记录（Keep a Changelog） |
| `cordis.patch.yml` | DSH 接入配置（dev overlay 兼 bundle patch） |

---

MIT，见 [`LICENSE`](LICENSE)。
