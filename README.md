# dsh-coderag

> ## ⚠️ 安全声明（请先读）
>
> **安装本插件等于授予它与本机账号同等的机器权限。**
> DSH 的三档文件权限（`read-only` / `workspace-write` / `danger-full-access`）**不约束插件**
> （依据：DSH `tool-cordis` README 与 `agent-scope-contexts` 笔记，见 `AGENTS.md` E-04）。
> **请只在你信任的仓库与本机上安装和运行。** 本项目默认**不联网**、**不采集遥测**。

dsh-coderag 是一个以 **MCP 服务器**形态提供的代码库检索引擎：让 DeepSeek Harness（DSH）的 Agent
能按语义与结构找到代码，而不是靠猜关键词反复 grep。它只做检索，不改你的代码。

**当前版本 `0.1.0`，尚未发布到 PyPI / npm；安装方式见下文「安装（当前方式）」。**

---

## 装上去以后，找代码会变成什么样

DSH 本来就能 grep、能读文件，所以问题不是"搜不搜得到"，而是每次都要**先把中文问题翻译成代码里可能出现的
英文词，再一轮轮试**。coderag 补的正是中间那一步：给助手一个可以直接问"这段逻辑在哪"的检索工具，
它返回 `文件:行号 [符号]`，助手再按行号去精读。

下面几种情况，是接与不接差别最明显的地方（场景取自 `eval/runs/a-smoke` 与 `b-smoke` 里两组实际回答过的问题）。

### 情况一：你知道"有这么个限制"，但不知道它在代码里叫什么

> 「一条消息里最多能附几张图片？这个上限定义在哪个文件？」

只靠 grep 时，助手得自己猜词：`image`、`attach`、`max`、`limit`……组合成正则一个个试，
再从命中的测试或文档反推定义处。**猜对了照样能答对——成本全压在"猜词"上。**
装了 coderag 之后，助手可以直接把这句话交给 `code_search`，拿回
`packages/attachment/attachment-local/src/index.ts:36` 与符号 `DEFAULT_MAX_IMAGES_PER_MESSAGE`，
然后只读那一个文件的相关几行。仓库里另有 `DEFAULT_MAX_IMAGES_PER_REQUEST` 这种容易张冠李戴的相似常量，
检索给出的**准确位置**能让人少走一段弯路。

### 情况二：中文问句，英文实现，词形毫无重叠

> 「启动子进程时，父进程的环境变量哪些会被过滤掉？这套规则写在哪个文件？」

问句里的"环境变量 / 过滤"，在代码里写作 `scrubbedParentEnv`、`SENSITIVE_ENV_PATTERN`——
**没有一个词能直接 grep 到**。熟悉这个仓库的人知道该猜 `env` 或 `scrub`，不熟悉的人只能一个个试。
这正是 coderag 的用武之地：直接从中文意图命中 `packages/subprocess/subprocess/src/index.ts`。

### 情况三：一个行为散在好几个包里

> 「工具还没真正执行就被取消时用的那个错误码，在哪定义、在哪写进结果、又被哪个检查点策略复用？」

答案横跨 `core/tools`、`agent-loop`、`session-checkpoint-policy` 三个地方。
没有检索时，助手常常是"找到一个、顺着 import 再找下一个"，链条一长就容易漏掉其中一环。
有检索时，至少第一个落点能落在正确的包上，剩下的顺着调用关系补全即可。

### 情况四：它不该让简单的事变复杂

装上检索**不是**要取代 grep：

- **直接给出标识符**（`PRUNE_MARKER` 定义在哪个文件）时，一次 grep 就够了——装了 coderag 也不会让它变慢变差。
- **仓库里根本没有的东西**（"这里用了 Kafka 吗"），必须老实回答"没有"。coderag 在找不到时返回的是
  **带状态的结果**（`empty`，或提示这类查询该改用 grep），而不是一个空列表——空列表会被模型读成
  "代码里不存在"，接着开始编（`AGENTS.md` RL-06）。

### 一句话

coderag 给 DSH 加的不是"更强的搜索"，而是**一个"先检索、再精读"的一等公民动作**：把
"用中文描述 → 文件与行号"这一步，从"靠模型猜英文关键字"变成"问一次、拿到位置、再去读"。

它目前的不足也摆在台面上：**纯中文自然语言的检索质量还没达标**；端到端的量化与短板见下文「实测评测数据」。

---

## 当前状态

| 里程碑 | 状态 |
|---|---|
| **M1** 走通闭环 | ✅ 已完成（DSH → MCP → Python → SQLite → 结果） |
| **M2** 检索质量 | ✅ 已完成（tree-sitter 声明感知分块、三层安全过滤、增量索引、任务取消、顺序保持） |
| **M3** 评测与决策 | ✅ **决策与应用层已闭合**：L1/L2 评测、逐 query diff（`T3-04c`）、`golden_version` 校验（`T3-04d`）、一键门禁（`T3-12`）全部完成，决策门 `T3-07` 已裁定。**向量检索（`T3-08`–`T3-11`）按 [`ADR-15`](docs/adr/ADR-15-defer-semantic-retrieval.md) 暂缓**——v1.0 不含，后续版本以**可选后端**引入（默认关闭、未配置退回纯 BM25） |
| **M4** 打包分发 | 🟡 进行中：bundle 清单（`T4-01`）与**可分发的 bundle 层**（`T4-02`：`dsh plugin add .` 实测装载，见 [`docs/m4-bundle.md`](docs/m4-bundle.md)）已落地；安装脚本 / 干净环境验证 / CHANGELOG 等待做 |

**评测结论**：端到端**有用**（S3 成立，+59.0pp），但**检索本身还没达标**（S1/S2 未达标）——
详见下文「实测评测数据」。这不是一个"检索很准"的项目，而是一个"接进去能提升任务成功率、
且对自己的短板有量化"的项目。

## 它是怎么工作的

- 引擎是 Python 包 `dsh_coderag`，以 **MCP stdio 服务器**运行。
- DSH 通过内置包 `@deepseek-ai/dsh-mcp-client` 在本机**拉起一个子进程**
  （`dsh_coderag.server` 的 stdio 入口，见 `cordis.patch.yml`），
  两者用 stdin/stdout 上的 JSON-RPC 通信，**不经过网络、不监听端口**。
- 索引存放在 `<工作区>/.coderag/index.sqlite3`（SQLite **FTS5** + 中文 bigram），
  **不写到工作区之外**（`AGENTS.md` S-03/S-04）。
- 分块用 **tree-sitter** 按函数/类/接口等声明边界切分；检索用 **BM25**，
  选按分数、**排按源码顺序**（ADR-05）。
- 仓库根的 `cordis.patch.yml` 同时充当本地开发 overlay 与**可分发的 bundle patch**：`dsh plugin add .`
  之后 DSH 的组合配置里会出现 `# == dsh-coderag` 层（`T4-02` 实测，见 [`docs/m4-bundle.md`](docs/m4-bundle.md)）。

## 安装（当前方式）

> **注意**：bundle 清单（`package.json`，`T4-01`）与**层的装载**（`T4-02`）**已就绪并实测**——
> `dsh.bundle.patch` 指向 `./cordis.patch.yml`、`files` 只放行该文件、**不含任何 JS 入口**；
> `dsh plugin --profile <名字> add .` 之后 `--dump-config` 会出现 `# == dsh-coderag` 层与
> `mcp-coderag` 行（复现步骤见 [`docs/m4-bundle.md`](docs/m4-bundle.md)）。但**尚未发布到
> PyPI / npm**，安装脚本（`T4-03`）与**干净 profile 的端到端验证**（`T4-08`）也还没做。
> 因此当前可靠的方式仍是「克隆 + `pip install` + `--patch`」。
> 下面每一条都在本机实测过（见文末「安装验证」）。

**前置**：Python **3.10–3.12**（`requires-python = ">=3.10,<3.13"`）、
[DSH](https://www.npmjs.com/package/@deepseek-ai/dsh)、Git。

```sh
# 1. 克隆（cordis.patch.yml 在仓库里，必须克隆）
git clone https://github.com/VermilionPasvikin/dsh-coderag.git
cd dsh-coderag

# 2. 装 Python 包（用你自己环境里的解释器；conda 或 venv 都行）
python -m pip install .          # 开发者用 pip install -e ".[dev]"

# 3. 验证引擎可用（这一步不涉及 DSH）
dsh-coderag --version            # 期望输出：dsh-coderag 0.1.0
dsh-coderag index /path/to/repo  # 期望：indexed N files, M chunks into .../.coderag/index.sqlite3
dsh-coderag search "用户令牌在哪里校验" --root /path/to/repo

# 4. 告诉 DSH 用哪个解释器（重要：patch 里的默认值是作者机器的路径）
export CODERAG_PYTHON="$(command -v python)"

# 5. 把插件挂进 DSH
./scripts/dsh web --patch ./cordis.patch.yml
```

> **顺序有讲究**：`--profile` / `--patch` 是**启动器**选项，必须写在 Web 应用自己的选项
> （`--port` / `--no-open` / `--host`）**之前**。写成
> `./scripts/dsh web --port 3099 --patch ./cordis.patch.yml` 会被应用解析器拒绝，报
> `error: unknown option '--patch'`。正确的写法是
> `./scripts/dsh --profile web --patch ./cordis.patch.yml --port 3099`（实测）。

第 5 步之后，DSH 会话里就会出现 `mcp__coderag__code_search` 等 4 个工具。
**`dsh` 不一定在 PATH 上**，所以本仓库统一用 `./scripts/dsh`（见 `PROJECT.md` §4.3.1 / `AGENTS.md` E-07）；
若你已有全局 `dsh`，它等价于直接敲 `dsh`。

> **`CODERAG_PYTHON` 不设会怎样**：patch 的内置默认值是
> `/opt/anaconda3/envs/forBSH/bin/python`——那是**作者本机**的路径，在你的机器上多半不存在，
> MCP 子进程会启动失败。所以第 4 步不是可选项。

### 安装验证

本机实测（macOS，Python 3.10.21，DSH 0.1.5-rc.1），**在一个全新的 venv 与新的 DSH 实例上**：

1. **干净环境 `pip install .` 成功**（依赖全部从 PyPI 解析：`mcp` / `tree-sitter` /
   `tree-sitter-language-pack` / `pathspec`），无 install script 参与。
2. `dsh-coderag --version` → `dsh-coderag 0.1.0`；
   对一个 2 chunk 的小仓库 `index` → `indexed 1 files, 2 chunks`，
   `search "verify_token"` → `token.py:1-3`。
3. **MCP 握手**（用的就是 patch 里的那条命令，解释器设为该 venv）：
   `serverInfo {'name': 'coderag', 'version': '0.1.0'}`、
   `tools ['code_search', 'code_outline', 'code_index', 'index_status']`、
   `code_search` 返回结构化结果且 `isError: False`。
4. **新 DSH Web 实例**（`:3099`）用 `./scripts/dsh --profile web --patch ./cordis.patch.yml --port 3099`
   启动成功，UI 正常返回（HTTP 200 + `__DSH_BOOT__`）。
5. **端到端功能**：让一个 headless DSH 进程带着同一份 patch 与 `CODERAG_PYTHON` 提问，
   其会话日志显示 `mcp__coderag__code_search` 被调用 5 次、`code_outline` / `index_status` 各 1 次，
   检索返回 `status: ready` / `scanned: 3967 files / 63046 chunks`，并给出了正确答案。

## 配置

stdio 子进程的环境会被清洗（匹配 `*KEY*` / `*PASSWORD*` / `*SECRET*` / `*TOKEN*` 的环境变量
与**所有** `DSH_*` 变量都会被删除），所以需要传给 Python 进程的配置要么通过 `cordis.patch.yml`
的 `config.env`，要么在**启动 dsh 的那个 shell** 里 export（后者对 `CODERAG_PYTHON` 有效，
因为它在 DSH 进程内求值）。

| 变量 | 作用 | 默认 |
|---|---|---|
| `CODERAG_PYTHON` | 运行 MCP 服务器的解释器路径 | 作者机器上的 `forBSH` 路径（**请覆盖**） |
| `CODERAG_ROOT` | 要索引的工作区根 | DSH 进程的工作目录 |
| `CODERAG_MAX_FILES` | 文件数上限，**超限显式失败**并报实际数量（不静默截断） | `20000` |
| `CODERAG_MAX_TOKENS` | 单次检索返回的 token 预算 | `4000` |
| `CODERAG_MAX_FILE_BYTES` | 单文件大小上限，超过则跳过并计入 `skipped.too_large` | `1048576`（1 MiB） |
| `CODERAG_BATCH_SIZE` | 索引写库批大小（不设则自适应推导） | 自适应（1–512） |
| `CODERAG_MAX_WORKERS` | 索引并发度（不设则按 CPU/内存推导） | 自适应（上限 8） |

## 工具（固定 4 个，不动态增删）

DSH 侧看到的工具名前缀为 `mcp__coderag__`，例如 `mcp__coderag__code_search`。

| 工具 | 参数 | 作用 |
|---|---|---|
| `code_search` | `query`（必填）、`path`、`limit`（默认 5，上限 50）、`max_tokens`（默认 4000） | 按自然语言或标识符检索，返回**文件路径 + 行号 + 符号名**；索引未就绪时返回结构化 `status` 而**不是空列表** |
| `code_outline` | `path`（必填）、`max_depth`（默认 2） | 返回单个文件的符号大纲（类/函数/方法）与行号 |
| `code_index` | `path`、`force` | 建立/刷新索引，**立刻返回 taskId**，后台执行 |
| `index_status` | `task_id`（可省） | 查询索引任务或当前工作区索引状态；含 `skipped` 计数与原因分类 |

`code_search` 的返回形如：

```jsonc
status: ready
query: "..."
scanned: 3967 files / 63046 chunks
hits: 10 (sorted by source order)
skipped: 3 (secret_file: 3)
```

## CLI

```sh
dsh-coderag index [路径]                 # 建/刷新索引（默认当前目录）
dsh-coderag search "查询" [--root 路径] [--limit N]
dsh-coderag --version
```

## 实测评测数据

**一次性说明**：两套评测都跑在 **DSH 仓库的一份副本**上（遵守 `AGENTS.md` RL-01/S-03，
用 rsync 复制而非原地索引）：**3967 个文件 / 63046 个 chunk**，全量索引**约 4.0 秒**（本机）。

### 成功标准（`PROJECT.md` §1.4）

| # | 标准 | 阈值 | 实测 | 达标 |
|---|---|---|---|---|
| **S1** | 检索本身有效：`Success@5` | ≥ 0.80 | **0.433**（30 条，95% CI `[0.274, 0.608]`） | ❌ |
| **S2** | 排序质量：`MRR` | ≥ 0.60 | **0.313** | ❌ |
| **S3** | 端到端有提升（有检索 vs 无检索） | ≥ +10pp | **+59.0pp**（0.308 → 0.897） | ✅ |
| **S4** | 成本：单次返回 token 中位数 | ≤ 4000 | **2492** | ✅ |

### L1 检索质量（30 条 golden 集，k=5）

| 桶 | n | Success@1 | Success@3 | Success@5 | MRR | token 中位数 |
|---|---:|---:|---:|---:|---:|---:|
| **overall** | 30 | 0.267 | 0.367 | **0.433** | **0.313** | 2492 |
| exact（裸标识符） | 12 | 0.583 | 0.833 | **1.000** | 0.700 | 1318 |
| crossfile（跨文件） | 11 | 0.091 | 0.091 | **0.091** | 0.091 | 3083 |
| natural（纯中文自然语言） | 7 | 0.000 | 0.000 | **0.000** | 0.000 | 3354 |

失败归因（`EVAL.md` §2.8 的 A1–A7）：`overall {"A5": 16, "A1": 1}`；
**`natural` 桶 7 条失败全部是 `A5`（零词法重叠）**，占 100%。

**读法**：`exact`（已知标识符）已经很好（S@5 = 1.000）；**纯中文自然语言是短板**
（S@5 = 0.000，因为查询词与代码文本没有共同词元，BM25 无从下手）。

### L2 端到端 A/B（13 条用例 × 3 trials）

| 组 | 检索工具 | taskSuccess |
|---|---|---:|
| A · 基线 | 无（bash / grep / glob / read） | 12/39 = **0.308** |
| B · 词法 | `code_search` / `code_outline` / `code_index` / `index_status` | 35/39 = **0.897** |

> 同题的**冒烟**运行（13 条 × 1 次，[`gate-smoke.md`](eval/runs/gate-smoke.md)）：A 4/13 → B 10/13（+46.2pp）；
> 仅 1 次取样，只作冒烟。两组的**机制**差别（先检索再精读 vs 猜英文词反复 grep）见上文场景说明。

> B 组的两次测量：`T3-06` 时是 22/39（0.564）；**`R5` 修复工具描述后升到 35/39（0.897）**。
> 采纳率（调用过 `code_search` 的 attempt）从 33.3% 升到 79.5%。

门禁 **0 回归**，**S3 成立**。
完整分层、逐条 diff 与失败归因见 **[`docs/eval-report-m3.md`](docs/eval-report-m3.md)**。

> **注意**：修好采纳后，**调用了工具的 31 个 attempt 里只失败 1 个**；残余 4 条失败是
> 3 条没调用 + 1 条步数超限，**没有一条是"检索返回了错误文件"**。也就是说这个 +59.0pp 主要来自
> "工具被用上的用例变多"，而不是"排序变准"——排序质量看上面的 L1。

## 已知限制

- **S1 / S2 未达标**：`Success@5 = 0.433`（阈值 0.80）、`MRR = 0.313`（阈值 0.60）。
- **纯中文自然语言检索基本不可用（已知且已决定暂缓）**：`natural` 桶 `Success@5 = 0.000`，
  失败 100% 归因 `A5`（查询与代码零词法重叠）。`ADR-14` 据此裁定 R2 命中，但
  **[`ADR-15`](docs/adr/ADR-15-defer-semantic-retrieval.md) 决定 v1.0 暂缓向量**：当前
  **没有任何 embedding / 向量库依赖**，安装也**不需要**任何本地模型。向量计划在后续版本以
  **可选后端**引入（默认关闭、未配置时退回纯 BM25）。**这条限制不会因为发版而消失**——
  如果你的使用场景以中文自然语言提问为主，v1.0 帮不上你。
- **工具采纳曾不稳定（R5，已改善）**：修 `code_search` 的描述前，只有 33.3% 的 attempt 会调用它；
  改后为 79.5%，端到端任务成功率 0.564 → 0.897。
- **工作区里与标准库同名的模块：已处理，保留一个残余边界**。DSH 以工作区为 cwd 启动引擎，
  而 `python -m` / `-c` 会把 cwd 放到 `sys.path` 最前，工作区根目录的 `token.py`、`types.py`、
  `logging.py` 等会遮蔽标准库，导致 MCP 服务器起不来。现在由两层防护解决：
  `cordis.patch.yml` 改用 **`-c`** 启动（绕开 `runpy`），
  `dsh_coderag/__init__.py` 在**任何可被遮蔽的导入之前**把 cwd 从 `sys.path` 移除。
  实测在同时含 `token.py` / `types.py` / `parser.py` / `logging.py` / `config.py` 的工作区里，
  DSH 会话中的 `code_search` 正常返回 `status: ready`。
  **残余边界**：手工执行 `python -m dsh_coderag.server`（不经 `-c`）且工作区含 `types.py`
  这类 **`runpy` 自身依赖**的同名文件时，解释器启动阶段仍会失败——这发生在我们的代码运行之前，
  无法从包内修复；请使用 `cordis.patch.yml` 的启动方式。
- **gap chunk 没有行数上限**：`export const X = {...}` 这类不被识别为声明的区域会合成一个
  大块，DSH 语料上实测最大 **3080 行**（`docs/backlog.md`）。
- **TS 的 `type` 别名与 `const`/箭头函数未纳入声明**：在 DSH 语料上 **69.6% 的 chunk 是 gap**
  （`docs/backlog.md`）。
- **每次检索会为填 `skipped` 重新遍历仓库**（约 180 ms），尚未随索引持久化。
- **单字中文查询**未实现 `§5.3.1` 规定的 `LIKE + low_confidence` 退化路径。
- **固定 4 个工具**，不动态增删（`AGENTS.md` RL-05）。
- **尚未发布**：无 PyPI 包、无 npm registry 包、无 `scripts/install.sh`、无 `CHANGELOG.md`；
  bundle 目前只能从**本仓库路径**安装（`dsh plugin add .` 已验证层可装载，`T4-02`），
  **干净 profile 的端到端（`T4-08`）与 registry 安装均未验证**。
- 未做 Windows 实测；开发与评测均在 macOS 上完成。

## 安全与隐私

- **三层过滤**（`AGENTS.md` §4.1，按顺序、缺一不可）：
  ① 内置密钥黑名单（`.env*`、`*.pem`、`*.key`、`id_rsa*`、`.npmrc`、`.ssh/`、`.aws/` …）；
  ② 项目的 `.gitignore` → `.coderagignore`（用 `pathspec`，不自造 gitignore 语义）；
  ③ **内容级正则**（私钥头、`AKIA…`、`sk-…`、`ghp_…`、`xox…`）——命中的 chunk **不入库**，
  且**只记路径与模式名，绝不记录匹配到的内容**。
- **过滤结果对模型可见**：`code_search` / `index_status` 会报告 `skipped: {count, reasons}`，
  避免模型把"被过滤"误读成"不存在"从而编造。
- **不联网、不采集遥测、不外发任何数据**（`AGENTS.md` S-01/S-02）。
- **索引只写在工作区内**：`<工作区>/.coderag/index.sqlite3`，且被本仓库的 `.gitignore` 排除。

## 开发

```sh
python -m pip install -e ".[dev]"
python -m pytest                    # 全量（离线，不需要 API key）
python -m ruff check src tests
python -m mypy --strict src/
```

L2 A/B 评测（**需要模型 API key**）见 `EVAL.md` §3.6 与 `docs/eval-report-m3.md`。

## 文档

| 文件 | 内容 |
|---|---|
| `PROJECT.md` | 项目概况、架构、ADR、任务表与进度 |
| `AGENTS.md` | 强制性约束：红线、DSH 环境坑、安全、提交规范 |
| `EVAL.md` / `TESTING.md` | 评测方案 / 测试方案 |
| `docs/eval-report-m3.md` | M3 的 L1/L2 评测报告（分层 + 逐条 + 归因） |
| `docs/adr/ADR-14-semantic-retrieval.md` | 决策门 `T3-07` 的裁决与证据 |
| `docs/adr/ADR-15-defer-semantic-retrieval.md` | 执行推迟：v1 不含向量，后续以可选后端引入（默认关闭） |
| `docs/m4-bundle.md` | 可分发的 DSH bundle：装载实测、自检清单与复现步骤 |
| `docs/backlog.md` | 已知但未修的缺陷 |
| `cordis.patch.yml` | DSH 接入配置 |

## 许可

MIT，见 [`LICENSE`](LICENSE)。
