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
[DSH](https://www.npmjs.com/package/@deepseek-ai/dsh)、Git、pnpm。

> **发布方式：只发布在 GitHub**（tag / release），**不发布到 PyPI、也不发布到 npm**。
> 因此安装只能走下面这条「克隆」路径；`pip install dsh-coderag` 与 `npm i dsh-coderag` 都**不可用**。
> **当前版本 `2.0.0` 同样只在 GitHub 上以 tag / release 发布**（`v2.0.0`），PyPI 与 npm 上没有任何版本。

```sh
# 1. 克隆（cordis.patch.yml 在仓库里，必须克隆）
git clone https://github.com/VermilionPasvikin/dsh-coderag.git
cd dsh-coderag

# 2. 装 Python 包（用你自己环境里的解释器；conda 或 venv 都行）
python -m pip install .          # 开发者用 pip install -e ".[dev]"

# 3. 验证引擎可用（这一步不涉及 DSH）
dsh-coderag --version            # 期望输出：dsh-coderag 2.0.0
dsh-coderag index /path/to/repo  # 期望：indexed N files, M chunks into .../.coderag/index.sqlite3
dsh-coderag search "用户令牌在哪里校验" --root /path/to/repo

# 4. 告诉 DSH 用哪个解释器（重要：patch 里的默认值是作者机器的路径）
export CODERAG_PYTHON="$(command -v python)"

# 5. 把插件挂进 DSH
./scripts/dsh web --patch ./cordis.patch.yml
```

> **`CODERAG_PYTHON` 不设会怎样**：patch 的内置默认值是
> `/opt/anaconda3/envs/forBSH/bin/python`——那是**作者本机**的路径，在你的机器上多半不存在，
> MCP 子进程会启动失败。所以第 4 步不是可选项。

> **`--patch` 的位置**：`--profile` / `--patch` 是**启动器**选项，必须写在 Web 应用自己的选项
> （`--port` / `--no-open` / `--host`）**之前**，否则报 `error: unknown option '--patch'`。
> 正确写法：`./scripts/dsh --profile web --patch ./cordis.patch.yml --port 3099`（实测）。

> **`dsh` 不一定在 PATH 上**，所以本仓库统一用 `./scripts/dsh`（`AGENTS.md` E-07）；
> 若你已有全局 `dsh`，它等价于直接敲 `dsh`。

一键安装脚本（会检查解释器、Python 版本与 FTS5，并验证中文 bigram 往返；可重复运行）：

```sh
bash scripts/install.sh                       # 受限网络：CODERAG_PIP_ARGS="--index-url <镜像>" ...
```

**怎么确认装上了**——`dsh plugin add` 在 pnpm 非零退出时会**静默跳过 bundle 登记**，
插件看起来装上了却永远不会加载（`AGENTS.md` E-05）。务必自查这一条：

```sh
./scripts/dsh --profile <名字> --dump-config | grep -A2 '== dsh-coderag'
# 期望看到：# == dsh-coderag   然后  - id: mcp-coderag
```

| 现象 | 怎么办 |
|---|---|
| `--dump-config` 里没有 `# == dsh-coderag` | bundle 没被登记：回头看 `add` 的 pnpm 报错；若报 `ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED`，把 pnpm 打印的精确 key 写进 `~/.dsh/profiles/<名字>/pnpm-workspace.yaml` 的 `allowBuilds:` 下（`<key>: true`）后重跑 `add` |
| 会话里没有 `mcp__coderag__code_search` | MCP 子进程起不来，最常见是解释器路径：`export CODERAG_PYTHON=<真正装了 dsh_coderag 的解释器>`，用 `"$CODERAG_PYTHON" -m dsh_coderag --version` 确认 |
| `pip install` 报 `externally-managed-environment` | PEP 668：用 conda 或 venv；**不要**用 `--break-system-packages` |
| 中文检索总是空 | 该解释器的 SQLite 没编译 FTS5：`bash scripts/install.sh` 会预检并给指引 |

更完整的安装实录与边界见 [`docs/m4-install-verification.md`](docs/m4-install-verification.md)。

## 配置

**运行时参数只从环境变量读**，唯一入口是 `src/dsh_coderag/config.py`，没有用户配置文件。

stdio 子进程的环境会被清洗：**继承来的**环境里，匹配 `*KEY*` / `*PASSWORD*` / `*SECRET*` / `*TOKEN*`
的变量与**所有** `DSH_*` 变量都会被删除。清洗之后，`cordis.patch.yml` 的 `config.env` 会**合并到最上面**
（已核实：`{...scrubbedParentEnv(), ...extra}`）——所以**写进 patch 的一定到得了子进程，export 的不一定**。

**配置写在哪**（按推荐顺序）：

| 写在哪 | 适合什么 | 会不会入库 |
|---|---|---|
| `$DSH_HOME/profiles/<profile>/cordis.patch.yml` | 本机持久设置，**包括密钥字面值** | ❌ 仓库之外，不会 |
| `$DSH_HOME/cordis.patch.yml` | 同上，且**优先级更高**（对所有 profile 生效） | ❌ 仓库之外，不会 |
| 启动 dsh 的那个 shell 里 `export` | 只对"名字不含 `KEY/PASSWORD/SECRET/TOKEN`"的变量有效 | ❌ 不涉及文件 |
| 仓库里的 `cordis.patch.yml`（`env:` 块） | 非密钥的默认值；**密钥只能用 `!!js` 表达式** | ⚠️ 会（**`RL-02`：绝不能写真实 key**） |

> **哪些变量 export 不生效**：`CODERAG_MAX_TOKENS` 的名字里含 `TOKEN`，会被清洗掉；云端的 API key 同理。
> 这两个**必须**写进上面任一处 patch 的 `env:` 里。`CODERAG_ROOT` 与 `CODERAG_PYTHON` 例外——
> 它们在 `cordis.patch.yml` 里已被 `!!js` 引用，由宿主进程读取你的 shell 环境。

> **覆盖时注意**：DSH 的 patch 是**整体替换**而不是深合并——写 `- id: mcp-coderag` 覆盖时，必须把
> `serverName` / `transport` / `command` / `args` 与**所有想保留的 `env` 项**一并重写，否则它们会消失。

| 变量 | 作用 | 默认 |
|---|---|---|
| `CODERAG_PYTHON` | 运行 MCP 服务器的解释器路径 | 作者机器上的 `forBSH` 路径（**请覆盖**） |
| `CODERAG_ROOT` | 要索引的工作区根 | DSH 进程的工作目录 |
| `CODERAG_MAX_FILES` | 文件数上限，**超限显式失败**并报实际数量（不静默截断） | `20000` |
| `CODERAG_MAX_TOKENS` | 单次检索返回的 token 预算 | `4000` |
| `CODERAG_MAX_FILE_BYTES` | 单文件大小上限，超过则跳过并计入 `skipped.too_large` | `1048576`（1 MiB） |
| `CODERAG_BATCH_SIZE` | 索引写库批大小（不设则自适应推导） | 自适应（1–512） |
| `CODERAG_MAX_WORKERS` | 索引并发度（不设则按 CPU/内存推导） | 自适应（上限 8） |

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
