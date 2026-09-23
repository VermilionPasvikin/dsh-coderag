# dsh-coderag — 项目文档

> **文档版本**：1.0 ｜ **撰写日期**：2026-09-17 ｜ **状态**：待开工
> **配套文档**：[`AGENTS.md`](./AGENTS.md)（AI 自动化开发规范与约束）——**两份必须一起读**。
>
> 本文档的每个设计决策都标注了**调研依据**。依据来自 2026-09-17 完成的四类线上调研（编码 Agent、IDE 编程助手、Agent 框架、RAG 技术栈）与本机 DSH 源码的一手核实，来源集中列在第 8 章。
>
> **项目名已定：`dsh-coderag`**（2026-09-17 确定，不再是占位符）。命名如下表，**全项目一律照此书写**，不得出现其他变体：

| 用途 | 定名 | 出现位置 |
|---|---|---|
| 仓库 / 项目名 / 目录 | `dsh-coderag` | GitHub 仓库、本地目录、`package.json` 的 `name` |
| Python 发行包与模块 | `dsh_coderag` | `pyproject.toml`、`import dsh_coderag`、`python -m dsh_coderag.server` |
| MCP `serverName` | `coderag` | `cordis.patch.yml` 的 `config.serverName`；工具在模型侧的名字是 **`mcp__coderag__code_search`** |
| 索引数据目录 | `.coderag/` | `<工作区根>/.coderag/index.sqlite3` |
| 项目忽略文件 | `.coderagignore` | 工作区根 |
| 环境变量 | `CODERAG_*` | `CODERAG_ROOT` / `CODERAG_MAX_FILES` / `CODERAG_MAX_TOKENS` / `CODERAG_PYTHON`；可选向量后端另用 `CODERAG_SEMANTIC`（开关，默认未设=关闭）/ `_BACKEND` / `_URL` / `_MODEL` / `_TIMEOUT` / `_BATCH` / `_MAX_CHUNKS`（冻结于 `ADR-16` §4），**云端后端**再加 `_API_KEY`（只从环境读）与 `_ALLOW_REMOTE`（非 loopback 的第二把钥匙，冻结于 `ADR-17` §4），安装侧开关为 `CODERAG_WITH_SEMANTIC` |
| 开发用 DSH profile | `coderag-dev` | 本地开发，**不要用 `web`** |
| 评测用 DSH profile | `eval-coderag` / `eval-baseline` | A/B 对照 |

> ⚠️ 以下两个名字**看起来像但必须保持不变**，改了就错：
> - **`CodeRAG-Bench`** —— 学术基准名（arXiv 2406.14497），第 2、8 章引用它
> - **`forBSH`** —— 你本机的 conda 环境名，环境搭建命令里引用它

---

## 0. 阅读指南

### 0.1 四份文档的分工

| 文档 | 内容 | 什么时候读 |
|---|---|---|
| **`AGENTS.md`** | **强制性约束**：10 条红线、6 条 DSH 环境约束、代码/安全/测试/文档/提交规范、反模式清单 | **写任何代码之前必读**，并在每个任务开始前复查 §1、§2 |
| **`PROJECT.md`**（本文） | 项目概况、调研依据、架构、环境、实现方案、56 个原子任务、风险 | 开工前通读；每个任务查 §6 |
| **[`EVAL.md`](./EVAL.md)** | 评测方案：三层评测、24 条评测集构造流程、失败归因表、A/B 配置、现成工具 | **做 M3 时通读**；平时遇到"检索不准"查 §2.8 |
| **[`TESTING.md`](./TESTING.md)** | 测试方案：10 类必测、MCP 内存传输用法、确定性/属性/快照测试、CI | **写第一个测试之前通读** |

**冲突时的优先级**：`AGENTS.md`（约束） > `EVAL.md` / `TESTING.md`（专项方案） > `PROJECT.md`（其余）。**`EVAL.md` 已取代本文 §5.8 与 §6.3 中关于评测的原始描述；`TESTING.md` 是 `AGENTS.md` §5 的展开。**

### 0.2 按角色选路径

| 你是谁 | 先读 | 再读 |
|---|---|---|
| 人类项目负责人 | 第 1 章（要做什么）、第 6 章（什么时候做完） | 第 7 章（风险）、《EVAL.md》§2.4（你要亲自做的 3 小时） |
| AI 编码助手 | **先读 `AGENTS.md`** | 第 3 章（架构）、第 5 章（实现）、第 6 章（任务）、《TESTING.md》 |
| 只想快速上手 | 第 4.3 节（环境搭建命令） | 第 6.1 节（M1 任务） |

**术语约定**：非显而易见的术语在首次出现处附一句话解释。若某个术语在本项目中含义有歧义，以第 3.7 节「关键设计决策记录」为准。

---

## 1. 项目概况

### 1.1 一句话定义

**`dsh-coderag` 是一个以 MCP（Model Context Protocol，模型上下文协议）服务形态提供的代码库检索引擎，让 DeepSeek Harness 的 Agent 能"按语义和结构"找到代码，而不是靠猜关键词去 grep。**

### 1.2 要解决的问题

DeepSeek Harness（下称 DSH）是一个"一切皆插件"的 Agent 框架，但它**刻意没有内置任何语义检索能力**。以下是在本机 DSH 源码中逐条核实的事实：

| 事实 | 源码位置 |
|---|---|
| 文件检索只有 `glob` 和 `grep`，底层是打包的 ripgrep，纯关键词匹配 | `packages/fs/tool-fs-search/README.md` |
| 会话检索用 SQLite FTS5，但其 README 自述限制为 *"Token recall, not arbitrary substrings"* | `packages/session-query/session-query-sqlite/README.md` |
| LSP 提供精确定位（跳定义/找引用），但需自行配置语言服务器，且是可选插件 | `packages/lsp/README.md` |
| **全仓库没有 tree-sitter、没有 embedding、没有向量库、没有 rerank** | 全仓库 grep 零命中 |
| LLM 适配器接口只有 chat，**没有 embeddings** | `packages/llm/llm/src/` |
| 官方明说记忆不是 DSH 的职责，"DSH **不负责**选择模型或 embedding 提供方" | `docs/user/guide/mcp-memory.zh.md` |
| 官方扩展手册把"记忆"列为"section 提供方 + 工具"，**但仓库里没有这个包** | `docs/cookbook/extension-cookbook.zh.md` |

**后果**：Agent 理解一个大仓库时，只能靠自己猜关键词去 grep。改一个跨 5 个文件的重构时，它猜不到另外 3 个文件的存在——这正是本项目要解决的问题。

### 1.3 目标与非目标

**目标（必须做到）**

1. 让 DSH 的 Agent 通过一个工具调用，就能拿到**相关的代码片段 + 精确的文件名与行号**。
2. **不修改 DSH 的任何核心代码**（`packages/` 目录在整个开发过程中保持只读）。
3. 结果可被**机械验证**：有一套可重复运行的评测集，能量化"有检索 vs 无检索"的差异。
4. 可分发给他人使用：一条 `dsh plugin add` 命令完成安装。
5. 同一个检索引擎可**被其他 Agent 宿主复用**（Claude Code / Cursor / Codex 等任何支持 MCP 的客户端）。

**非目标（明确不做，避免范围蔓延）**

| 不做 | 理由 |
|---|---|
| 通用文档 RAG（PDF/Word/网页） | 本项目只做**代码库**检索。文档 RAG 是另一套分块与解析问题 |
| Web GUI 管理面板 | 第一期不做。DSH 已提供 Web UI，面板是锦上添花 |
| 多用户 / 服务端部署 / 权限体系 | 单机本地工具，不做多租户 |
| 替换 DSH 的 agent loop | DSH 的 loop 是它的核心资产，重造没有收益 |
| 跨会话长期记忆 | 这是另一个产品（记忆），本项目只做**代码检索** |
| 自动修改代码 | 本项目只提供**只读检索**。写文件由 DSH 自己的工具负责 |

### 1.4 成功标准（可量化）

项目成功的判据**不是"功能做完了"，而是下面这些标准同时成立**（`S1`–`S4` 是 v1.0 的判据；`S5`/`S6` 是 v2.0.0 为可选向量后端追加的两条）：

| # | 标准 | 度量方式 | 阈值 |
|---|---|---|---|
| **S1** | **检索本身有效** | 在自建评测集上，`code_search` 的 **Success@5** | ≥ 0.80 |
| **S2** | **排序质量合格** | 正确文件在结果中的平均排名 **MRR** | ≥ 0.60 |
| **S3** | **端到端有提升** | 评测集任务通过率：有检索 vs 无检索 | 相对提升 ≥ 10 个百分点 |
| **S4** | **成本可接受** | 单次 `code_search` 返回的 token 数 | 中位数 ≤ 4000 |

> `S1`–`S4` 是本项目的稳定标识——`§6.8 覆盖矩阵` 与 `EVAL.md` 都按这些 ID 引用它们，**不要改名**；`S5`/`S6`（v2.0.0 追加）同样是稳定标识。

> **为什么把 S3 设成必要条件**：调研中有一条关键实证——Repoformer 的测量显示**最多 80% 的检索结果并不提升下游任务性能**，只有约 20% 的实例真正受益。如果 S3 不成立，说明检索在做无用功，**此时砍掉它是正确的工程决策，而不是项目失败**（依据：CodeRAG-Bench / Repoformer，见第 8 章）。

**v2.0.0 追加两条**（可选向量后端；`ADR-16` §7.1）：

| # | 标准 | 度量方式 | 阈值 |
|---|---|---|---|
| **S5** | **可选后端补齐自然语言短板** | 开启后端（`CODERAG_SEMANTIC=on`）后，**`natural` 桶**的 `Success@5`（其余口径与 L1 相同：30 条、宏平均、`k=5`） | ≥ **0.40**（沿用 `EVAL.md` §2.7 的 `natural` 桶阈值；7 条里至少 3 条命中） |
| **S6** | **默认路径零回归** | **未配置** `CODERAG_SEMANTIC` 时，30 条 query 的结果与 `1.0.0` 基线**逐条一致**（逐 query diff 的回归条数，由 `T3-12` 门禁给出） | 回归条数 **= 0**，且 `exact` 桶 `S@5` 保持 **1.000** |

> **S5 的适用范围**：它只约束**已发布的**向量路径。若 `T5-14` 的天花板探针给出 no-go，或 `T3-11` 按 `ADR-14` §10.4 的 **V4** 判定"C 组不能显著优于 B 组"，则**该路径不发布**，`S5` 不参与判定（`ADR-16` §1.7/§7.3）。
> **S6 是 2.0.0 的硬门禁，无条件适用**：不满足 `S6` 就不算发布成功——默认安装必须与 `1.0.0` 行为一致（`RL-10` 的可验收形式）。


### 1.5 交付形态

| ID | 交付物 | 落点 | 判据 |
|---|---|---|---|
| **D1** | Python 包 `dsh_coderag` | `src/dsh_coderag/` + `pyproject.toml` | `pip install .` 可安装；`dsh-coderag --version` 可用 |
| **D2** | MCP 服务（stdio 传输） | `src/dsh_coderag/server.py` | 4 个工具可被任何 MCP 宿主发现并调用 |
| **D3** | DSH bundle（npm 包） | 仓库根 `package.json` + `cordis.patch.yml` | `dsh plugin add` 一条命令安装 |
| **D4** | 评测集与评测脚本 | `eval/tasks.jsonl` + `src/dsh_coderag/eval/` | 可重复跑出 S1–S4 的数字 |
| **D5** | README（含安全声明与限制） | `README.md` | 顶部披露插件权限范围；含实测数据与已知限制 |

> `D1`–`D5` 是稳定标识，被 `§6.8 覆盖矩阵` 引用，**不要改名**。

**2.0.0 的交付形态：两段式安装（默认段不变 + 可选段显式）**（`ADR-16` §7.1）

| 段 | 装什么 | 命令 | 谁需要 |
|---|---|---|---|
| **默认段（不变）** | 只有 `mcp` / `tree-sitter` / `tree-sitter-language-pack` / `pathspec`；bundle tarball 与 `scripts/install.sh` 的**默认路径零向量依赖** | `pip install .`（或 `pip install dsh-coderag`）+ `dsh plugin add .` | **所有人**。与 `1.0.0` 完全相同的安装步骤 |
| **可选段（opt-in）** | extra **`semantic`**（内容只有 `numpy`），以及用户自己装的 **Ollama + `bge-m3`** | `pip install -e ".[semantic]"` 或 `CODERAG_WITH_SEMANTIC=1 bash scripts/install.sh`，再设 `CODERAG_SEMANTIC=on` | 只有想要语义检索的人 |

> **两段都不做的人也永远不会碰到向量**：不装 extra 就没有 `numpy`，不设 `CODERAG_SEMANTIC` 就不联网、行为与 `1.0.0` 逐条一致（`S6`）。**这是 `RL-10` 的可验收形式。**

---

### 1.6 分发方式与许可（**已决定，不再讨论**）

#### 1.6.1 仓库布局：**仓库根同时是 npm bundle 和 Python 项目**

```
dsh-coderag/                      ← 仓库根
├── package.json                  ← npm bundle 清单（dsh.bundle → ./cordis.patch.yml）
├── cordis.patch.yml              ← DSH 补丁层：既是 dev overlay，也是分发内容
├── pyproject.toml                ← Python 包配置
├── src/dsh_coderag/              ← Python 引擎
├── tests/  eval/  scripts/  docs/
├── AGENTS.md  PROJECT.md         ← 约束与项目文档
├── EVAL.md  TESTING.md           ← 评测方案与测试方案
├── README.md  LICENSE  CHANGELOG.md
└── .gitignore
```

**为什么这样放**：让**两条安装路径同时成立**——

| 安装路径 | 命令 | 为什么可行 |
|---|---|---|
| 本地开发 / tarball | `dsh plugin --profile <p> add .` 或 `add ./dsh-coderag-1.0.0.tgz` | bundle 清单在仓库根 |
| 从 GitHub 直装（最终目标） | `dsh plugin --profile <p> add github:<你>/dsh-coderag` | npm 包必须在仓库根，pnpm 才能识别 |
| Python 引擎 | `pip install .` 或 `pip install dsh-coderag` | `pyproject.toml` 在仓库根 |

**bundle 里没有任何 JavaScript**：`cordis.patch.yml` 插入的行引用的是 DSH **内置**包 `@deepseek-ai/dsh-mcp-client`，内置包名始终从 dsh 安装目录解析。仓库自己的示例（`apps/cli/config/examples/schedule/cordis.yml`）就是这么做的。

**这顺带彻底绕开了约束 C11（pnpm 拒绝 install script）**——没有 JS 就没有构建脚本，没有 `allowBuilds` 问题。

#### 1.6.2 分发路线：**三阶段，先跑通再上架**

| 阶段 | 时机 | 做什么 | 需要账号吗 |
|---|---|---|---|
| **阶段 1** | M4 出口 | GitHub 仓库 + `scripts/install.sh` + GitHub Release 附 `pnpm pack` 出的 tarball | ❌ 不需要 |
| **阶段 2** | 项目稳定、有评测数据后 | 发布 **PyPI**（`dsh-coderag`）→ `pip install dsh-coderag` | 需要 PyPI 账号 |
| **阶段 3** | 有人真的在用之后 | 发布 **npm**（`dsh-coderag`）→ `dsh plugin add dsh-coderag` 一条命令 | 需要 npm 账号 |

**理由**：阶段 1 零门槛，能立刻验证「别人装得上吗」这个最难的问题；registry 发布是可选的锦上添花，不应该阻塞主线。两个 registry 同名（npm 与 PyPI 是独立命名空间），版本号保持一致。

**不要做的事**：不要用 npm 的 `postinstall` 去 `pip install`（约束 E-05）。Python 依赖由 `scripts/install.sh` 显式安装，README 写清步骤。

#### 1.6.3 许可：**MIT**

| 依赖 | 许可 | 是否兼容 MIT 分发 |
|---|---|---|
| `mcp`（官方 MCP Python SDK） | MIT | ✅ |
| `tree-sitter`（py-tree-sitter） | MIT | ✅ |
| `tree-sitter-language-pack` | MIT | ✅ |
| `pathspec` | MPL-2.0（文件级 copyleft） | ✅ 只要不修改 pathspec 自身的文件 |
| DSH 本身 | MIT | ✅ |

**选 MIT 的理由**：
1. **零障碍**——这是本项目最需要的。你希望别人能一条命令装上，任何额外的许可条款都会降低安装率。
2. **与生态一致**——DSH 本身是 MIT，绝大多数 DSH 插件也是 MIT。
3. **依赖全部兼容**——不需要处理任何 copyleft 传染问题。

**被否决的方案**：
- **AGPL-3.0**（`dsh-knowledge` 的选择）：能防止别人拿去做闭源 SaaS，但对一个本地工具没有任何意义（用户在自己机器上跑，不构成网络服务分发），**只会白白劝退使用者**。

#### 1.6.4 可选依赖：2.0.0 的 extra（**不进默认安装**）

| 项 | 冻结内容 | 依据 |
|---|---|---|
| extra 名 | **`semantic`** | `ADR-16` §3.2 |
| extra 内容 | **只有 `numpy`**（HTTP 走标准库 `urllib.request`，因此不引入 `httpx`；不引入任何向量数据库） | `ADR-16` §3.1/§3.2 |
| 是否进 tarball | **否**。bundle 仍未含任何 JS，也仍未含任何 Python 依赖——tarball 依旧只有 `package.json` / `cordis.patch.yml` / `LICENSE` / `README.md` | `ADR-16` §7.1 |
| 是否进 `install.sh` 默认路径 | **否**。`CODERAG_WITH_SEMANTIC` 未设时脚本**不装任何向量依赖** | `ADR-16` §3.2 |
| 用户侧的另一半 | **Ollama + `bge-m3`**：由用户自己安装的系统服务，**不是**本项目的 Python 依赖，也**不是**安装前置 | `ADR-16` §3.1 |
| **可选后端之二：云端**（`CODERAG_SEMANTIC_BACKEND=openai`） | 任何兼容 **OpenAI `/v1/embeddings`** 的线上服务；**不需任何额外 Python 依赖**（HTTP 走标准库 `urllib`）。需 `CODERAG_SEMANTIC_ALLOW_REMOTE=1` 才允许非 loopback 地址，key 只从环境读（`RL-02`） | `ADR-17` §1/§2/§4 |

> ⚠️ **云端后端的安全风险（`ADR-17` §5，逐字同源）**：**开启它 = 你的部分源码文本会离开这台机器。**外发内容是已入库 chunk 的文本**及其上下文前缀行——因此包含工作区相对路径与符号名**；被三层过滤拦下的密钥文件从来没有 chunk，不会被外发；云端按 token **计费**，首次索引是全量支出（`CODERAG_SEMANTIC_MAX_CHUNKS` 是硬闸，超限显式失败）；代码可能是公司资产，**外发前请自行确认授权**；API key 只从环境读、**绝不写入仓库/日志/状态**；远端地址需 `ALLOW_REMOTE=1` 且**请使用 `https://`**。**默认安装与此无关**——两条后端都默认关闭（`RL-10`）。

> **为什么不把 `numpy` 放进 `dependencies`**：默认安装的承诺是"clone + `pip install .` + 一个 YAML、零 install script"。多一个依赖就多一份装不上的概率，而**大多数用户用不到语义检索**。`RL-10` 把这条写成了红线。
- **Apache-2.0**：多了明确的专利授权，对企业用户更友好。**如果你将来发现有大公司要用，可以再换成 Apache-2.0**——两者兼容，迁移只需改 `LICENSE` 与 `package.json`/`pyproject.toml` 的 `license` 字段。

**落地动作**：`T4-07` 产出 `LICENSE` 时用 **MIT 全文**，年份 2026，版权人填你的名字或 ID。

---

## 2. 技术选型依据（调研结论 → 设计决策）

本章说明**为什么是这套方案**。每一条都对应一个已核实的调研发现。

### 2.1 同类公开项目是怎么做的

**编码 Agent 类（独立进程形态）**

| 项目 | 语言 | 代码理解方案 | 对本项目的启示 |
|---|---|---|---|
| **Aider** | Python | **tree-sitter 符号图 + 图排序**（PageRank 选最重要的片段），**明确不用 embedding** | ✅ 直接采用：tree-sitter + 图/符号排序 |
| **Cline** | TS | **完全不做索引**，官方原话 *"No RAG. No embeddings. No vector databases."*，纯 ripgrep + 符号列表 + 子代理 | ⚠️ 警示：不做索引也能用，说明检索是增强而非必需 |
| **Roo Code** | TS | tree-sitter 语义分块（1000/50 字符，无 overlap）+ Qdrant 纯向量 | ⚠️ 该项目已停服；其分块思路可借鉴，纯向量不可取 |
| **Kilo Code** | TS | 同源分块 + LanceDB/Qdrant | ⚠️ **2026-04 新版扩展一度摘掉了代码索引**（官方 issue #6144） |
| **Continue** | TS | 三套 artifact：FTS5 trigram+BM25 / tree-sitter 符号 / LanceDB 向量；内容寻址 + 分支缓存 | ✅ 最佳范本：**混合检索**与增量设计直接对标 |
| **OpenHands** | TS壳+Py核 | file search，grep 三级降级 | ✅ 采用：**永不报错，逐级降级** |
| **SWE-agent** | Python | Agent-Computer Interface | 参考其工具设计 |

**关键裁决数据（代码检索）**

| 发现 | 数字 | 来源 |
|---|---|---|
| **BM25 在代码上打败纯向量** | RepoEval NDCG@10：**BM25 93.2 vs BGE-large 80.4** | CodeRAG-Bench (arXiv 2406.14497) |
| **代码专用 embedding 在真实任务上输给 BM25** | SWE-bench-Lite：voyage-code **29.1** vs BM25 **43.0** | 同上 |
| **检索经常没用** | **最多 80% 的检索不提升性能**，仅约 20% 实例受益 | Repoformer (arXiv 2403.10059) |
| **混合检索 + 重排的收益（文档域）** | 失败率 5.7% → Contextual Embedding **3.7%**(-35%) → +BM25 **2.9%**(-49%) → +rerank **1.9%**(-67%) | Anthropic Contextual Retrieval |

> **→ 设计决策**：**第一版只做 BM25（FTS5）+ 符号结构，不做向量。** 等评测集证明 BM25 不够用，再考虑上向量。

### 2.2 为什么选「Python + MCP」而不是「原生 TypeScript 插件」

| 维度 | Windows 权重 | Python + MCP（本项目） | 原生 TS 插件 |
|---|---|---|---|
| 复用你已有的技能 | 高 | ✅ 你会 Python | ❌ 要从零学 TypeScript + Cordis |
| 不修改 DSH 源码 | 高 | ✅ 完全不动 | ✅ 不动（但要学它的插件 API） |
| 上游升级影响 | 中 | ✅ 零影响 | ⚠️ 小（插件 API 可能变） |
| 拿得到 DSH 内部能力 | 中 | ❌ 不能注入 system prompt、不能进审批链 | ✅ 全都能 |
| 用户安装难度 | 中 | ⚠️ 需要 Python | ✅ 只要 Node |
| 跨宿主复用 | 高 | ✅ Claude Code / Cursor / Codex 都能用 | ❌ 只能 DSH |
| 出第一版的时间 | 高 | ✅ 1–2 天 | ❌ 1–3 周 |

**并且已有一手先例**：社区的 `dsh-kb-rag`、`code-rag-mcp`、`dsh-memtrace` 都采用"引擎在外部、DSH 侧零代码"的范式。

> **→ 设计决策**：采用范式 C（MCP 桥接）。若将来确认需要深度集成（自动上下文注入、审批链、settings 面板），再升级为范式 A（原生插件）——**届时业务逻辑（分块、索引、检索）可整块搬移，只换外壳**。

### 2.3 为什么第一版不做向量检索（最重要的一个决定）

三条独立证据指向同一结论：

1. **BM25 在代码检索上本来就赢**（93.2 vs 80.4）。
2. **向量检索经常白做**（80% 的检索不提升性能）。
3. **一个已商业化的产品直接把它删了**：Kilo Code 在 2026-04 重建扩展时移除了代码索引。

> **→ 设计决策**：把"上不上向量"设为一个**由数据决定的决策门**（见第 6.3 节 M3-DECIDE），而不是默认架构。**M3 之前禁止引入任何 embedding 依赖。**

**v2.0.0 的范围（决策门之后的实际结果）**：决策门 `T3-07` 已裁定——R2 命中（`ADR-14`），但端到端目标已由纯词法达成，所以向量**先暂缓**（`ADR-15`），再于 2.0.0 以**可选后端**重启（`ADR-16`）。因此本节的三条证据**至今没有被推翻**，它们现在约束的是**默认路径**：

- **默认路径仍是纯 BM25**，`ADR-16` 的形态是"补齐、不替换"（RRF k=60，`exact` 桶必须保持 1.000）；
- 上面第 1 条（BM25 赢纯向量）与第 2 条（80% 检索不提升）正是**为什么向量只做可选**的理由——它没有强到值得成为默认；
- 是否发布这条路径，**由 `T5-14` 的天花板探针先给 go/no-go**，再服从 `ADR-14` §10.4 的 V1–V4（V4：C 组不显著优于 B 组就不发布，`ADR-16` §7.2）。

> 换句话说：本节回答"**为什么第一版不做**"，`ADR-16` 回答"**第二版怎么做成可选的**"；两者不冲突。**"不做"从不等于"永远不做"**，而是"不默认做"。

### 2.4 从真实 issue 学到的硬约束（全部已核实）

这些不是"最佳实践建议"，**是会导致项目失败的硬约束**：

| # | 约束 | 证据 |
|---|---|---|
| C1 | **MCP 工具调用默认 60 秒超时** → 索引必须异步（立即返回 taskId） | `packages/mcp/mcp-client/README.md`：`toolCallTimeoutMs` 默认 `60,000` |
| C2 | **stdio 子进程环境被清洗**：匹配 `/KEY\|PASSWORD\|SECRET\|TOKEN/i` 的变量与所有 `DSH_*` 都被删除 | 同上，"Environment scrubbing (stdio)" |
| C3 | **不要在 `complete: true` 的 preset 上依赖 system-prompt 注入**：会被**静默丢弃且不报错** | `packages/preset/persona/README.md` 第 49 行 |
| C4 | **MCP 工具集必须固定**：`list_changed` 重同步可能撞 namespace 抢占导致工具集清空 | DSH discussion #618 |
| C5 | **中文检索必须专门处理**：`unicode61` 匹配不了中文子串；`trigram` 分词器可以，但**最小匹配单位是 3 字**，2 字中文词（"认证"、"令牌"、"重试"）全部召回失败 | `session-query-sqlite/README.md` 自述 + **本机 PoC 实测**（见 §5.3.1） |
| C6 | **索引未就绪必须返回结构化状态，绝不返回空结果** | RGB 基准（arXiv 2309.01431）：文档全不含答案时模型仍作答，最好拒答率仅中文 43.33% |
| C7 | **忽略规则是安全边界，不是体验优化** | Kilo issue #11637：`.kilocodeignore` 未能阻止 `read` 返回 `.env.local` |
| C8 | **批处理参数必须自适应，不能硬编码** | Roo issue #8875：硬编码 `BATCH_SEGMENT_THRESHOLD` / `BATCH_PROCESSING_CONCURRENCY` 在 4 核 i5 上卡死 VS Code |
| C9 | **文件数上限必须显式报错，不能静默截断** | Roo/Kilo 源码硬编码 `MAX_LIST_FILES_LIMIT_CODE_INDEX = 50_000`；Kilo issue #4080 的仓库有 80,138 文件，被静默截断 |
| C10 | **索引状态必须跨重启持久化** | Roo issue #5656：清空索引后忽略规则丢失，直到重启才恢复 |
| C11 | **pnpm 10+ 拒绝运行 install script，会导致插件"装了但永不加载"** | dsh-zvec-grep README + DSH discussion #656 |
| C12 | **DSH 的三档权限不约束插件，插件 = 完整机器权限** | `packages/extensions/tool-cordis/README.md` 第 182 行；`.agents/notes/implemented/architecture/2026-07-08-agent-scope-contexts.zh.md` 第 145 行「安全与权限是非目标」 |

### 2.5 检索结果排序的一条实证

NVIDIA 论文（arXiv 2409.01666）在 ∞Bench 上的实测：

| 排序方式 | EN.QA F1 |
|---|---|
| 按相关度降序（vanilla RAG） | 38.40 |
| **按原文顺序（order-preserving）** | **44.43** |

同一篇论文还给出：**检索 16K token 的 F1（44.43）超过塞满 117K 上下文的 Llama3.1-70B（34.26）和 196K 的 Gemini-1.5-Pro（43.08）**；且存在**倒 U 形**——检索块数过多反而变差（8B 模型峰值在 16K，70B 在 48K）。

> **→ 设计决策**：检索时**按分数选 top-k，但输出时按（文件路径, 起始行号）重新排序**。默认返回的 token 预算控制在 4000 以内（对应 S4）。

---

## 3. 架构设计

### 3.1 分层

```
┌─────────────────────────────────────────────────────────────────────┐
│ 第 4 层 · 分发层                                                      │
│   npm 包 dsh-coderag-dsh                                             │
│   package.json 声明 dsh.bundle → cordis.patch.yml                    │
│   用户执行：dsh plugin --profile web add github:<你>/dsh-coderag      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ 装载一行 MCP client 配置
┌──────────────────────────────▼──────────────────────────────────────┐
│ 第 3 层 · 桥接层（DSH 官方，本项目零代码）                              │
│   @deepseek-ai/dsh-mcp-client                                        │
│   · stdio 启动子进程、清洗环境变量、发现工具、注册到 ctx.tools          │
│   · 工具在模型侧的名字：mcp__coderag__code_search                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ JSON-RPC over stdio（MCP 协议）
┌──────────────────────────────▼──────────────────────────────────────┐
│ 第 2 层 · 协议层                                                      │
│   4 个 MCP 工具（见 3.5）                                             │
│   工具集固定不变（约束 C4）                                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ 进程内函数调用
┌──────────────────────────────▼──────────────────────────────────────┐
│ 第 1 层 · 引擎层（Python 包 dsh_coderag）                              │
│                                                                      │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│   │ walker   │→ │ chunker  │→ │ indexer  │→ │ searcher │           │
│   │ 文件遍历  │  │ 分块     │  │ 索引     │  │ 检索     │           │
│   │ + 安全   │  │ tree-    │  │ SQLite   │  │ FTS5 BM25│           │
│   │   过滤   │  │ sitter   │  │ FTS5     │  │ + 顺序   │           │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│        │              │             │              │                │
│        └──────────────┴─────────────┴──────────────┘                │
│                          │                                           │
│                   ┌──────▼──────┐   ┌──────────┐  ┌──────────┐     │
│                   │ taskman     │   │ server   │  │ eval     │     │
│                   │ 异步任务管理 │   │ MCP 入口 │  │ 评测     │     │
│                   └─────────────┘   └──────────┘  └──────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 索引数据流

```
用户/模型调用 code_index(root)
   │
   ├─► taskman.create()  ──► 立刻返回 {taskId, state:"pending"}     ← 约束 C1
   │
   └─► （后台线程/进程）
         │
         ├─ 1. walker.walk(root)
         │      ├─ 读 .gitignore + .coderagignore + 内置密钥黑名单   ← 约束 C7
         │      ├─ 跳过二进制/超长行/超大文件
         │      └─ 产出 [(abs_path, size, mtime_ns)]
         │      │
         │      └─► 文件总数 > maxFiles ? → 立刻 fail 并报告实际数量  ← 约束 C9
         │
         ├─ 2. 增量判定：与 files 表比对 content_hash
         │      └─ 只处理 新增/修改/删除 三类                          ← 约束 C10
         │
         ├─ 3. chunker.chunk(path)   （逐文件，可并发但受自适应限流）
         │      ├─ tree-sitter 解析 → 按声明边界切分
         │      ├─ 产出 Chunk{seq, start_line, end_line, symbol, text}
         │      └─ 净化：剔除密钥内容                                 ← 约束 C7
         │
         ├─ 4. indexer.upsert(chunks)
         │      ├─ 事务写入 chunks / chunks_fts
         │      └─ 每批更新 done_chunks 进度
         │
         └─ 5. taskman.finish(taskId, {total, done, state:"ready"})
```

### 3.3 检索数据流

```
code_search(query, path, limit, mode)
   │
   ├─ 0. 预检：任务状态
   │      └─ 索引未就绪 → 返回 {status:"indexing", progress:0.42}     ← 约束 C6
   │                     （绝不返回 [] 让模型误以为"代码里没有"）
   │
   ├─ 1. 查询预处理
   │      ├─ 提取标识符/路径/扩展名等结构化线索
   │      └─ to_bigrams() 转换 + 精度/召回双模式（见 §5.3.1）
   │
   ├─ 2. FTS5 BM25 检索
   │      └─ SELECT ... FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(...) LIMIT k
   │
   ├─ 3. 结构化加分（可选的符号图信号）
   │      ├─ 命中 symbol_name 完全匹配 → 加权
   │      └─ 同文件多命中 → 轻微加权（局部性）
   │
   ├─ 4. 截断到 limit
   │
   ├─ 5. 【顺序保持】按 (path, start_line) 重新排序                    ← 第 2.5 节依据
   │
   ├─ 6. 预算裁剪：累加 token 估算，超过 maxTokens 就停
   │
   └─ 7. 渲染为模型可见文本（含文件名 + 行号 + 符号名 + chunk 序号）
```

### 3.4 模块划分

| 模块 | 文件 | 职责 | 不负责 |
|---|---|---|---|
| `config` | `src/dsh_coderag/config.py` | 配置读取与校验（环境变量）、自适应并发/批大小推导 | 不做默认值猜测（缺失必填项要报错） |
| `types` | `src/dsh_coderag/types.py` | 跨模块数据类与错误码枚举 | 不含行为 |
| `parser` | `src/dsh_coderag/parser.py` | 按扩展名探测语言、提供 tree-sitter grammar/parser | 不解析语法树、不遍历工作区 |
| `text` | `src/dsh_coderag/text.py` | 中文 bigram 预转换（索引与查询两侧共用） | 不做分词决策 |
| `sanitize` | `src/dsh_coderag/sanitize.py` | 密钥文件名/路径黑名单与内容正则扫描 | 不遍历、不读文件、不写库 |
| `sqlite_caps` | `src/dsh_coderag/sqlite_caps.py` | FTS5 能力探测 | 不打开索引数据库 |
| `walker` | `src/dsh_coderag/walker.py` | 遍历工作区、应用忽略规则与密钥黑名单、上报 skip 原因与文件数上限 | 不读文件内容 |
| `chunker` | `src/dsh_coderag/chunker.py` | tree-sitter 声明感知分块、超大符号拆分、module 头、无 grammar 降级、上下文前缀 | 不写数据库 |
| `indexer` | `src/dsh_coderag/indexer.py` | SQLite schema、增量写入、幂等、三类变更、批量写库、内容级 redact、审计转储 | 不做检索 |
| `searcher` | `src/dsh_coderag/searcher.py` | FTS5 查询、打分、顺序保持、预算裁剪、标点路由、path 过滤、`code_outline` 符号树 | 不做索引 |
| `taskman` | `src/dsh_coderag/taskman.py` | 异步任务创建/进度/取消/持久化 | 不执行具体索引逻辑 |
| `render` | `src/dsh_coderag/render.py` | 把 search/status 结果渲染成模型可见文本 | 不做检索决策 |
| `log` | `src/dsh_coderag/log.py` | JSON-Lines 日志（stderr）与 `last-index.json` 审计 | 不写 stdout、不索引/检索 |
| `server` | `src/dsh_coderag/server.py` | MCP 协议实现、4 个工具注册、outline 文本渲染 | 不含业务逻辑（薄层） |
| `eval` | `src/dsh_coderag/eval/` | 评测集加载与校验、L1 运行/指标/归因/报告、L2 A/B runner、门禁 CLI（`tasks.py` / `runner.py` / `metrics.py` / `attribute.py` / `report.py` / `ab.py`） | 不参与生产检索路径；除 `ab.py` 拉起 headless DSH 外不调模型 |
| `cli` | `src/dsh_coderag/__main__.py` | 命令行入口（`index` / `search`） | 供人调试用，非模型接口 |

**模块依赖方向（禁止反向依赖）**：

```
server ──► {taskman, searcher, indexer, render, walker, sqlite_caps, config, types}
cli ─────► {indexer, searcher, types}
taskman ─► {indexer, types}
searcher ► {indexer, walker, chunker, parser, text, sqlite_caps, config, types}
indexer ─► {walker, chunker, sanitize, text, log, sqlite_caps, config, types}
walker ──► {sanitize, config, types}
chunker ─► {parser, types}
render ──► types
eval ────► {searcher, indexer, walker, text, config, types}（`runner` 复用生产检索；`attribute` 读 walker/indexer/text 做归因；markdown 渲染是 eval 自己的）

config / types / parser / text / sanitize / log / sqlite_caps：叶子模块，不依赖其它 dsh_coderag 模块；
config 与 types 被所有模块只读引用。render 只被 server 调用（eval 有自己的 markdown 渲染器）。
```

### 3.5 MCP 工具契约

> **设计原则**：工具集**固定为 4 个**，不动态增删（约束 C4）。所有变化通过参数表达，不通过新增工具。
>
> **命名原则**：工具名描述**模型要达成的目标**，不描述实现机制。不用 `fts5_query`、`bm25_search` 这类实现词汇。

#### 工具 1：`code_search`

```jsonc
{
  "name": "code_search",
  "description": "Search the workspace codebase for relevant code. Returns ranked code snippets with exact file paths and line numbers. Prefer this over grep when you do not know the exact identifier, or when searching for behaviour across multiple files. When the index is not ready the result reports a structured status instead of an empty list.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query":    { "type": "string",  "description": "Natural language or identifiers describing what you are looking for." },
      "path":     { "type": "string",  "description": "Workspace-relative directory to search within. Defaults to the workspace root." },
      "limit":    { "type": "integer", "description": "Maximum number of snippets. Defaults to 5, maximum 50." },
      "max_tokens": { "type": "integer", "description": "Approximate token budget for the returned snippets. Defaults to 4000." }
    },
    "required": ["query"]
  }
}
```

**返回格式（模型可见，逐字符稳定，改动必须更新快照）**：

```
status: ready
query: "如何校验用户令牌"
scanned: 1284 files / 9632 chunks
hits: 5 (sorted by source order)
skipped: 42 (gitignored: 28, secret_file: 12, too_large: 2)

── src/auth/token.py:42-67  [function verify_token]  (chunk 7)
def verify_token(raw: str) -> Claims:
    ...

── src/auth/middleware.py:15-33  [function require_auth]  (chunk 3)
...

[1 more hit omitted by token budget; raise max_tokens to see it]
```

**未就绪时的返回（关键，约束 C6）**：

```
status: indexing
message: The code index for this workspace is still being built.
progress: 42% (540/1284 files, 3900/9632 chunks)
hint: Results would be incomplete. Retry shortly, or use grep for exact identifiers now.
```

**失败时**：

```
status: error
code: INDEX_READ_FAILED
message: ...
```

#### 工具 2：`code_outline`

```jsonc
{
  "name": "code_outline",
  "description": "Return the symbol outline (classes, functions, methods) of one file, with line numbers. Use this to understand a file's structure before reading it in full.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path":      { "type": "string",  "description": "Workspace-relative file path." },
      "max_depth": { "type": "integer", "description": "Nesting depth to include. Defaults to 2." }
    },
    "required": ["path"]
  }
}
```

**返回格式（模型可见）**：

```
status: ready
path: src/auth/token.py
symbols: 3

class TokenService  lines 10-40
  method verify_token  lines 12-20
  method issue_token  lines 22-30
function helper  lines 42-44
```

#### 工具 3：`code_index`

```jsonc
{
  "name": "code_index",
  "description": "Start (or refresh) the code index for a workspace directory. Returns immediately with a task id; indexing continues in the background. Poll index_status for progress.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path":  { "type": "string",  "description": "Workspace-relative directory to index. Defaults to the workspace root." },
      "force": { "type": "boolean", "description": "Rebuild from scratch instead of incrementally. Defaults to false." }
    }
  }
}
```

**返回**：`{"taskId": "idx-20260917-8f3a", "state": "pending", "hint": "Poll index_status with this taskId."}`

#### 工具 4：`index_status`

```jsonc
{
  "name": "index_status",
  "description": "Report the state and progress of an indexing task, or of the workspace index when no task id is given.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "task_id": { "type": "string", "description": "Task id returned by code_index. Omit to report the current workspace index." }
    }
  }
}
```

**状态机**：`pending → running → ready | failed | cancelled`

### 3.6 SQLite 数据模型

**验证记录**：本机 `forBSH` 环境实测为 **Python 3.10.21 + SQLite 3.53.4**，`fts5` **已确认可用**。⚠️ **但中文必须走 bigram 预处理**——`trigram` 分词器对本项目不可用，原因见 §5.3.1 的实测。

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 索引运行记录（约束 C10：跨重启持久化）
CREATE TABLE IF NOT EXISTS index_runs (
  task_id       TEXT PRIMARY KEY,
  root          TEXT    NOT NULL,
  state         TEXT    NOT NULL,   -- pending|running|ready|failed|cancelled
  total_files   INTEGER NOT NULL DEFAULT 0,
  done_files    INTEGER NOT NULL DEFAULT 0,
  total_chunks  INTEGER NOT NULL DEFAULT 0,
  done_chunks   INTEGER NOT NULL DEFAULT 0,
  message       TEXT,
  started_at    INTEGER NOT NULL,
  finished_at   INTEGER
);

-- 文件层（增量判定的依据）
CREATE TABLE IF NOT EXISTS files (
  id            INTEGER PRIMARY KEY,
  path          TEXT    NOT NULL UNIQUE,   -- 工作区相对路径，正斜杠
  size          INTEGER NOT NULL,
  mtime_ns      INTEGER NOT NULL,
  content_hash  TEXT    NOT NULL,          -- sha256，用于幂等
  lang          TEXT,                      -- tree-sitter 语言名
  indexed_at    INTEGER NOT NULL
);

-- 分块层
CREATE TABLE IF NOT EXISTS chunks (
  id            INTEGER PRIMARY KEY,
  file_id       INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,          -- 文件内序号，用于"原文顺序"
  start_line    INTEGER NOT NULL,          -- 1-based，闭区间
  end_line      INTEGER NOT NULL,          -- 1-based，闭区间
  symbol_kind   TEXT,                      -- function|method|class|struct|union|enum|namespace|interface|module
  symbol_name   TEXT,
  text          TEXT    NOT NULL,
  content_hash  TEXT    NOT NULL,
  UNIQUE (file_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_chunks_order ON chunks (file_id, seq);
CREATE INDEX IF NOT EXISTS idx_chunks_symbol ON chunks (symbol_name);

-- 全文索引：中文走 bigram 预转换 + unicode61（约束 C5，见 §5.3.1 的实测依据）。
-- 不用 content= 外部内容表：写入前需要对中文做 to_bigrams() 转换，
-- 转换后的文本必须真实存在索引里。用 UNINDEXED 列承载删除所需的外键。
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5 (
  text_bigram,            -- to_bigrams(chunk.text)，中文已切成 bigram
  symbol,                 -- 原始符号名（拉丁标识符，无需转换）
  path,                   -- 原始路径
  chunk_id UNINDEXED,
  file_id  UNINDEXED,
  tokenize = 'unicode61'
);

-- 工作区索引代（用于检索时判断是否 stale）
CREATE TABLE IF NOT EXISTS workspace_index (
  root          TEXT PRIMARY KEY,
  db_schema     INTEGER NOT NULL,
  ready         INTEGER NOT NULL DEFAULT 0,
  last_task_id  TEXT,
  updated_at    INTEGER NOT NULL
);
```

**存储位置**：`<root>/.coderag/index.sqlite3`（与工作区同目录，便于随项目迁移；必须在 `.gitignore` 中排除）。

**向量索引的落点（2.0.0 的可选后端，**默认关闭**、默认不创建）**（`ADR-16` §5）

向量**不进 `index.sqlite3`**，而是与它并列放在 `.coderag/` 下——暴力余弦要的是"一整块 float32 矩阵 + 一次向量化点积"，把 BLOB 逐行取出再拼矩阵反而更慢：

```text
<root>/.coderag/
├── index.sqlite3          # BM25 索引（上面那张表）
└── vectors/               # 仅当 CODERAG_SEMANTIC=on 时才创建
    ├── embeddings.npy     # float32，行序 = chunk_id 升序
    └── manifest.json      # model / dim / chunk 数 / 逐 chunk 内容哈希 / 生成时间 / 格式版本
```

**被否决的方案**：在 `index.sqlite3` 里建 `embeddings(chunk_id, model, dim, vector BLOB)` 表（本文件 1.0 版的预留设计）。理由：① 逐行读 BLOB 再拼矩阵抵消了 `numpy` 的向量化收益；② 与 BM25 共用一个库会让"只重建向量"变成对同一文件的写放大；③ 独立文件可以整体丢弃/重建，而 `manifest.json` 里的模型与维度正是判断"旧向量还能不能用"的依据（`ADR-16` §5.4）。**两种落点都在 `<root>/.coderag/` 之内**（`S-03`/`S-04`），2.0.0 采用文件形式。

### 3.7 关键设计决策记录（ADR）

| ID | 决策 | 理由 | 被否决的方案 |
|---|---|---|---|
| **ADR-01** | 引擎用 Python，通过 MCP 接入 | 复用已有技能；不动 DSH 源码；可跨宿主复用 | 原生 TS 插件（学习成本高、周期长） |
| **ADR-02** | 第一版只做 FTS5 BM25，不做向量 | BM25 在代码检索上实测赢纯向量（93.2 vs 80.4）；80% 检索不提升性能；Kilo 已删除索引功能 | 直接上向量（成本高、收益未验证） |
| **ADR-03** | 工具集固定为 4 个，不动态增删 | MCP `list_changed` 重同步可能撞 namespace 抢占清空工具集（约束 C4） | 按语言/按目录动态注册工具 |
| **ADR-04** | 索引异步化，立刻返回 taskId | MCP 工具调用默认 60 秒超时（约束 C1） | 同步索引（大仓库必然超时） |
| **ADR-05** | 检索结果按源码顺序输出，而非按分数降序 | NVIDIA 实测：128 块场景 F1 从 38.40 → 44.43（第 2.5 节） | 按相关度降序（vanilla RAG） |
| **ADR-06** | 索引未就绪返回结构化状态，不返回空列表 | RGB 实测拒答率仅 43.33%，空结果会让模型编造（约束 C6） | 返回 `[]` + 提示词里写"没找到就说没有" |
| **ADR-07** | **中文走 bigram 预转换 + FTS5 `unicode61`**（不用 `trigram` 分词器） | 本机 PoC 实测：`trigram` 在 7 条查询上只命中 3 条——**所有 2 字中文词全部失败**（trigram 最小匹配单位是 3 字）；改成 bigram 后 **7/7 全中**。详见 §5.3.1 | `trigram` 分词器（2 字词不可用）；`unicode61` 裸用（中文整段被当一个 token） |
| **ADR-08** | 忽略规则 + 密钥黑名单是**索引入口的硬过滤**，不是可配置的优化项 | Kilo #11637 真实泄露 `.env.local`（约束 C7） | 靠提示词提醒模型"别看密钥" |
| **ADR-09** | 索引状态与忽略规则**一并持久化**到数据库 | Roo #5656：清空索引后忽略规则丢失直到重启（约束 C10） | 忽略规则只在内存中 |
| **ADR-10** | 超过文件数上限时**显式失败并报告实际数量** | Roo/Kilo 硬编码 50000 上限导致静默截断（约束 C9） | 静默截断（用户以为索引完整） |
| **ADR-11** | 并发度自适应，由 CPU 核数与内存推导，不硬编码 | Roo #8875 硬编码参数卡死低配机器（约束 C8） | 固定线程池大小 |
| **ADR-12** | 指标用 **`Success@k`**（top-k 至少命中一个目标文件），不用 nDCG | 0/1 伯努利试验，Wilson 区间直接适用；nDCG 需分级相关性表，人工分级一致率仅 fair | nDCG（分级一致性差）；`Recall@k`（我们无法声称知道全部相关文件，算不出分母） |
| **ADR-13** | **标点/短符号查询不做 FTS，显式路由到 `grep`**，并返回结构化提示 | 本机实测：`(`、`::`、`->` 在 `unicode61`/`trigram`/`porter` 三档下**全部无法 MATCH**；换 tokenizer 解决不了。而 DSH 已提供 ripgrep 后端的 `grep` | 换 trigram tokenizer（实测无效）；自建全表 `LIKE` 扫描（比 grep 慢，负收益） |
| **ADR-14** | **R2 命中：引入向量检索**——词法为底，本地 `bge-m3` embedding + RRF（k=60）**只做补齐、不替换** | 30 条 L1 实测：exact `S@5 = 1.000`（词法对标识符已满分），crossfile `0.091`、natural `0.000`；17 条失败中 **16 条是 `A5`（零词法重叠）**。`S@5 = 0.433 < 0.80` 且 `natural` 的 A5 占比 `1.0 ≥ 50%`，R2 两项条件同时成立；且此前已按 §2.8 的但书修完 A1（T3-13）与 A4（T3-14）。完整证据与限制见 `docs/adr/ADR-14-semantic-retrieval.md` | 全面替换为向量（exact 已满分，替换只会回退）；在修完 A1/A4 前就上向量（`EVAL.md` §2.9 陷阱 8） |
| **ADR-15** | **暂缓语义检索**：v1 不含向量，`T3-08`–`T3-11` **暂缓**；后续版本以**可选后端**引入（**默认关闭**、未配置时退回纯 BM25） | 端到端 S3 已由纯词法 + 采纳率修复达成（0.308 → 0.897，**+59.0pp**），且**调用了工具的 31 个 attempt 里只失败 1 个**、残余失败无一条归因排序；分块修复实验 S1/S2 **逐条零变化**（失败全在 `A5` 词表）；而向量要求用户装 Ollama + 1.2 GB 模型 + 首次索引几十分钟，与 v1"一条命令安装"冲突。完整依据与**重启条件**见 `docs/adr/ADR-15-defer-semantic-retrieval.md` | 以 S1/S2 未达标为由在 v1 就引入向量（部署门槛与发布目标冲突）；把"暂缓"读成"撤销 R2 结论"（R2 事实判断仍成立） |
| **ADR-16** | **向量作为可选后端（2.0.0）**：默认关闭 + opt-in、未配置时**输出与 1.0.0 逐字节一致**、RRF(k=60) 只补齐不替换、后端为**本地 Ollama + `bge-m3`**、依赖冻结为 extra **`semantic`（只有 numpy，用 stdlib `urllib` 不引入 httpx、不引入向量库）**、向量索引落在 **`<root>/.coderag/vectors/`**（`S-03`）、失败一律结构化状态并回退 BM25（不 `isError`、不空列表）、发布服从 `ADR-14` §10.4 的 V1–V4（V3 用 **α = 0.025**，V4：C 不显著优于 B 就不发布），且**探针 `T5-14` 先行、由数据给 go/no-go** | `ADR-15` §3 的重启条件逐条兑现；本地后端是为了满足 `S-01`（默认不联网）与 `S-02`（不外发数据）——云端 embedding 需要 key 且会把代码发出机器；`numpy` 只进 extra 是为了 `RL-10`（改写后）的"不得进入必需依赖"；探针先行是因为在没有上限数据前全量实施是过早优化。完整条文见 `docs/adr/ADR-16-optional-vector-backend.md` | 默认开启或默认安装向量依赖（把"可选"做成"必需"）；云端 embedding；引入向量数据库（≤10 万 chunk 用暴力余弦足够）；把向量做成**替换**而非补齐（exact 已满分，替换只会回退）；跳过探针直接全量实施 |
| **ADR-17** | **云端的向量后端也是可选的**：新增与 `ollama` 平级的 `openai` 后端（兼容 OpenAI `/v1/embeddings`），**双重开关**（`CODERAG_SEMANTIC=on` **且** `CODERAG_SEMANTIC_ALLOW_REMOTE=1` 才允许非 loopback 地址），key 只从环境读，形态与本地后端完全对称（默认关闭 + 干净回退 + RRF + V1–V4） | 用户需求变更（2026-09-23）要求可选的线上模型 API；选兼容协议是为了**一份实现覆盖多家**（改 URL + model 就能换供应商/换模型），且继续用标准库 `urllib`、**不引入任何厂商 SDK**（`RL-10`）。代价是**代码文本会离开本机**，故必须：默认关闭、双重开关、风险声明随每一处配置出现（`D-08`）。完整条文见 `docs/adr/ADR-17-optional-cloud-embedding.md` | 各厂商官方 SDK（依赖树随支持家数膨胀，且与"HTTP 走标准库"的冻结条文冲突）；把云端做成默认或必需依赖（`RL-10`）；**不加第二把钥匙就让远端地址生效**（那样改一个 URL 就能把代码发出去） |

---

## 4. 环境依赖

### 4.1 本机现状（2026-09-17 实测）

| 项 | 状态 | 说明 |
|---|---|---|
| 芯片 / 内存 | Apple M4 / 24 GB | 本地跑 embedding 与 rerank 完全够 |
| 磁盘可用 | 128 GB | 向量索引仅需几十 MB |
| Node.js | **v24.14.0** | 满足 DSH 的 `^22.19 \|\| >=24` |
| npm | 11.9.0 | |
| pnpm | 已安装 | 装插件与从源码开发都需要 |
| conda | `/opt/anaconda3` | |
| 环境 `forBSH` | **Python 3.10.21** | 满足 MCP SDK 的 `>=3.10` |
| SQLite（forBSH 内） | **3.53.4**，FTS5 已验证；中文需 bigram 预处理（§5.3.1） | ADR-07 的前提 |
| Ollama | 未安装 | **仅可选后端需要**，默认关闭（`ADR-16` §3.1）；未启用时与 `1.0.0` 行为一致 |
| gh CLI | 已安装但**未登录** | 发布阶段才需要 |
| dsh（运行时） | **`0.1.5-rc.1`** | 经 `./scripts/dsh` 调用（§4.3.1）。**这是本项目的开发基线**——它决定实际行为 |
| dsh（参考源码） | **`0.1.6-alpha.1`**（commit `0d1f50007f`） | 见 §4.1.1；它决定文档里的源码路径 |

#### 4.1.1 dsh 运行时与参考源码

本项目同时跟踪两个 dsh 版本，用途不同：

- **运行时 = `0.1.5-rc.1`**：经 `./scripts/dsh` 调用（§4.3.1），它决定**实际行为**——工具契约、60s 调用超时、stdio 环境清洗等。
- **参考源码 = `0.1.6-alpha.1`（commit `0d1f50007f`）**：只用于核实**源码路径与实现细节**；文档里的 `packages/...` 路径、README 行号等以它为准。

两者暂时不同步是刻意的：运行时钉一个已验证版本保证可复现，参考源码取较新的树以便引用尚在演进的源码结构。升级运行时时一并更新参考源码（§4.1.2）。**本项目不修改参考源码中任何被 git 跟踪的文件**（RL-01）。

#### 4.1.2 升级 dsh 的三步清单

1. 改 `scripts/dsh` 的 `DSH_VERSION`（或临时设环境变量 `DSH_VERSION=...`）。
2. 同步更新 §4.1 的版本号与 §4.3.1 的说明。
3. 重跑 §4.5 环境验证清单；M3 之后还要跑 `scripts/eval-gate.sh`。

**为什么钉版本而不是追 `latest`**：本机 npx 缓存里已有 `0.1.5-rc.1`，走 npx 时无需重新下载约 190 个包；且 npm 的 `latest` 在本会话期间就从 `0.1.5-rc.1` 漂到了 `0.1.5-rc.2`。钉住一个验证过的版本，比追 `latest` 可复现。

### 4.2 依赖清单

**必需（M1 起声明依赖，M2 起使用）**

| 依赖 | 版本约束 | 用途 | 备注 |
|---|---|---|---|
| Python | `>=3.10,<3.13` | 运行时 | `forBSH` 已满足 |
| `mcp` | `>=1.28,<2` | MCP 服务端 SDK | **必须加 `<2` 上界**：v2 是破坏性重构 |
| `tree-sitter` | `>=0.25.2,<0.26` | 解析器运行时 | 必须与 `tree-sitter-language-pack` 0.13 的构建线一致（0.25.x）：本机实测 0.26.0 在释放大 Tree 时段错误，0.25.2 正常 |
| `tree-sitter-language-pack` | `>=0.13,<0.14` | C / C++ / Python / TS / JS / Rust / Go 等 | 第一版只需 C/C++/Python/TS。**必须钉 `<1`**：1.x 是 Rust 重写，wheel 不含 grammar，运行时从 GitHub Release 下载（离线不可用、违反 `TESTING.md` T-02）；0.13 是最后一个打包 grammar 的 abi3 wheel |
| `pathspec` | `>=0.12` | `.gitignore` 语法解析 | 不要自己实现 gitignore 匹配 |

> 这些依赖自 T1-01 起就写进 `pyproject.toml`；实际使用时间：`mcp` 从 T1-11、`tree-sitter` 从 T2-01、`pathspec` 从 T2-06。

**可选：2.0.0 的 extra `semantic`（**默认关闭**、默认不装）**（`ADR-16` §3.2）

| 依赖 | 用途 | 备注 |
|---|---|---|
| `numpy` | 暴力余弦相似度 | **extra `semantic` 的内容，仅此一项**。安装：`pip install -e ".[semantic]"`，或 `CODERAG_WITH_SEMANTIC=1 bash scripts/install.sh` |
| `ollama`（外部服务）+ `bge-m3` 模型 | 本地 embedding 后端 | 约 1.2 GB，免费、中文强。**由用户自己安装的系统服务，不是本项目的 Python 依赖，也不是安装前置**；本项目用 HTTP 调用它，客户端走标准库 `urllib.request` |

> **不装这个 extra 时，默认安装的依赖仍只有上面那四项**（`RL-10`、`ADR-16` §7.1）。**`httpx` 与云端 embedding 都不在 2.0.0 的范围内**——`ADR-16` §3.1 已否决云端后端（需 API key、会把代码文本发出机器，违反 `S-01`/`S-02`），HTTP 客户端因此退回标准库。

**明确不引入（第一版）**

| 不引入 | 理由 |
|---|---|
| LangChain / LlamaIndex | 已在 DSH 之上，再套一层编排是重复抽象；且带来版本破坏性风险 |
| ChromaDB / Qdrant / Milvus / faiss | **默认路径与可选路径都不引入**：`ADR-16` §3.1 已定——≤10 万 chunk 用 `numpy` 暴力余弦足够，引入向量库是过早优化（`AGENTS.md` §8） |
| `sqlite-vec` | 有已知问题：部分平台的 `node:sqlite`/扩展加载受限；纯 numpy 在 10 万量级足够快 |

### 4.3 环境搭建步骤

```sh
# ── 步骤 1：Node 侧（用于安装 DSH 与加载 bundle）
npm install -g pnpm

# ── 步骤 2：Python 侧
conda activate forBSH
pip install "mcp>=1.28,<2" "tree-sitter>=0.23" tree-sitter-language-pack pathspec

# ── 步骤 3：验证关键假设（必须全部通过）
python -c "import mcp, tree_sitter, pathspec, sqlite3, sys; \
print('python', sys.version.split()[0]); \
print('sqlite', sqlite3.sqlite_version); \
c=sqlite3.connect(':memory:'); \
c.execute('CREATE VIRTUAL TABLE t USING fts5(x, tokenize=unicode61)'); \
print('FTS5 OK'); \
from dsh_coderag.text import to_bigrams; \
assert to_bigrams('校验用户令牌') == '校验 验用 用户 户令 令牌', to_bigrams('校验用户令牌'); \
print('bigram OK')"

# ── 步骤 4：启动 DSH Web（感受"没有 RAG 时模型在哪卡住"）
./scripts/dsh web
```

#### 4.3.1 统一入口：`./scripts/dsh`

**问题**：`dsh` 不一定在 PATH 上。它只在两种情况下可见：① 全局安装过；② 正处在某个 dsh 会话内——会话会把 npx 缓存的 `.bin` 临时注入 PATH。干净终端里实测 `env -i … zsh -lic 'which dsh'` 返回 not found。

**方案**：`scripts/dsh` 包装脚本——若全局有 `dsh` 且未设 `DSH_FORCE_NPX=1`，直接 `exec dsh "$@"`；否则回退到**钉版本**的 `npx --yes @deepseek-ai/dsh@${DSH_VERSION}`。

**约定**：本项目所有文档里的 `dsh X` 都读作 `./scripts/dsh X`（`AGENTS.md` E-07）。

**为什么危险**：在 dsh 会话内直接敲 `dsh X` 看起来完全能用，一离开会话就 `command not found`——属于「测的时候通过、别人跑就失败」。

### 4.4 受限网络下的配置

| 场景 | 配置 |
|---|---|
| pip 慢 | `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ...` |
| HuggingFace 下载慢（M3 之后） | `export HF_ENDPOINT=https://hf-mirror.com` |
| npm 慢 | `npm config set registry https://registry.npmmirror.com` |

### 4.5 环境验证清单

开工前必须逐条确认，任何一条不通过都**不要进入 M1**：

- [ ] `pnpm --version` 有输出
- [ ] `conda activate forBSH && python --version` 显示 3.10.x
- [ ] 步骤 3 的验证脚本打印 `FTS5 OK` 与 `bigram OK`
- [ ] `npx @deepseek-ai/dsh web` 能在 `http://127.0.0.1:3080` 打开
- [ ] 在 DSH 设置里填好模型 API key，能完成一次对话

---

## 5. 实现方案

### 5.1 分块策略

**核心原则：代码绝不按字符数切分。**

| 层级 | 规则 |
|---|---|
| **L1 声明边界** | 用 tree-sitter 解析，按 `function_definition` / `class_specifier` / `method_definition` / `struct_specifier` 等节点边界切分。这是**主路径**。 |
| **L2 超大符号降级** | 单个声明超过 `maxChunkLines`（默认 200 行）时，按内部逻辑块（`compound_statement` 的直接子语句、注释块边界）二次切分，每片补齐 `symbol_name` 与 `#part/N` 后缀。 |
| **L3 文件头** | 文件开头、首个声明**之前**的非声明区块标记为 `symbol_kind="module"` 的头部块，上界 40 行（取该区间内最后一个非空行），内含 license/import/宏定义，便于回答"这个模块是干什么的"。**文件以声明开头时没有独立头部块**。 |
| **L4 无解析器降级** | 语言没有 grammar 时，按空行分隔的段落切分，**并在结果中标注 `low_confidence: true`**，让模型知道这块质量低。 |

**每个 chunk 必须携带的元数据**（依据 arXiv 2401.05856 的教训：*"Adding the file name and chunk number into the retrieved context helped the reader extract the required information"*）：

- `path`（工作区相对路径）
- `start_line` / `end_line`（1-based 闭区间）
- `symbol_kind` / `symbol_name`
- `seq`（文件内序号）
- `lang`

**chunk 文本必须带上下文前缀**（依据 Anthropic Contextual Retrieval，可降低检索失败率 35%）：

```
// file: src/auth/token.py  |  symbol: function verify_token  |  lines 42-67
<原始代码>
```

> 注意：前缀在**索引时**拼接（参与 FTS 索引），在**渲染时**单独成行输出。这样既提升召回，又不污染代码正文。

### 5.2 索引策略

| 项 | 方案 |
|---|---|
| **幂等** | 以 `files.content_hash`（sha256）为判据。hash 未变则整文件跳过，不重复分块 |
| **增量** | 三类变更：新增（插入）、修改（删除旧 chunk 再插入）、删除（级联删除）。每类都必须在**一个事务**内完成 |
| **并发** | `workers = max(1, min(cpu_count - 1, 8))`，且受内存上限约束（约束 C8）。**禁止硬编码** |
| **批大小** | 起始 64 个 chunk 一批，根据单批耗时动态调整（>2s 减半，<200ms 翻倍），上限 512 |
| **上限** | `maxFiles` 默认 20000。超过时**立刻失败**并报告 `actual_count`（约束 C9） |
| **单文件上限** | `maxFileBytes` 默认 1 MiB，超过则跳过并记入 `skipped` 列表 |
| **状态持久化** | 任务路径由 `TaskManager` 写 `index_runs`；索引完成写 `workspace_index.ready`（约束 C10）。直接 `index_sync`（CLI）不写 `index_runs` |
| **取消** | `taskman.cancel(taskId)` 设置取消标志，工作线程在每个文件边界检查一次 |

### 5.3 检索策略

**第 1 阶段（M1–M2）：纯词法**

```
FTS5 MATCH 查询 → bm25() 排序 → 结构化加分 → 截断 → 顺序保持 → 预算裁剪
```

#### 5.3.1 中文查询构造（本机 PoC 实测，**照抄这段**）

> **背景**：这是一个**实测发现**，不是理论推导。开工前我用 `forBSH` 环境跑了一轮最小 PoC，结果推翻了原设计。

**PoC 结果**（同一批 7 条查询，两种分词方案）：

| 查询 | `trigram` 分词器 | **bigram + unicode61** |
|---|---|---|
| `用户令牌是在哪里校验的` | ❌ 无结果 | ✅ 命中 |
| `认证 令牌`（2 字词） | ❌ 无结果 | ✅ 命中 |
| `重试 退避`（2 字词） | ❌ 无结果 | ✅ 命中 |
| `连接池 初始化` | ✅ 命中 | ✅ 命中 |
| `verify_token` | ✅ 命中 | ✅ 命中 |
| `拦截 未认证` | — | ✅ 命中 |
| `怎么处理上游服务失败` | ❌ 无结果 | ✅ 命中 |
| **合计** | **3/7** | **7/7** |

**根因**：FTS5 的 `trigram` 分词器把文本切成 3 字符滑窗，**查询词短于 3 字就无法匹配**。中文里 2 字词占比极高（"认证"、"令牌"、"重试"、"退避"、"拦截"），所以 `trigram` 对中文基本不可用。

**采用的方案**：索引与查询**两侧都做 bigram 预转换**，然后交给普通的 `unicode61` 分词。

```python
CJK = re.compile(r"[\u4e00-\u9fff]+")


def to_bigrams(text: str) -> str:
    """把 CJK 连续段切成 bigram；拉丁词与代码原样保留。

    unicode61 会按空格切词，因此 bigram 成为独立 token，且相邻 bigram 保持位置关系。
    纯 CJK 不产生首尾空格，整体幂等，纯拉丁文本原样返回。
    """
    pieces: list[str] = []
    pos = 0
    for match in CJK.finditer(text):
        pieces.append(text[pos : match.start()])
        pieces.append(_bigram_run(match.group()))
        pos = match.end()
    pieces.append(text[pos:])
    return _join_pieces(pieces)


def _bigram_run(run: str) -> str:
    """把一个 CJK 连续段展开为 bigram；单字原样保留。"""
    if len(run) == 1:
        return run
    return " ".join(run[index : index + 2] for index in range(len(run) - 1))


def _join_pieces(pieces: list[str]) -> str:
    """拼接各段，只在两段会贴在一起时补一个空格。"""
    result = ""
    for piece in pieces:
        if not piece:
            continue
        if result and not result[-1].isspace() and not piece[0].isspace():
            result += " "
        result += piece
    return result
```

该实现保证：纯拉丁文本原样返回；纯 CJK 不产生首尾空格；整体幂等（`to_bigrams(to_bigrams(x)) == to_bigrams(x)`）。

**两种查询模式（实测行为已验证）**：

| 模式 | 构造方式 | 语义 | 实测 |
|---|---|---|---|
| **精度模式**（默认） | 连续 bigram 作**短语** `"用户 户令 令牌"` | 等价于**精确子串匹配** | `用户令牌` → 只命中真正含该子串的文档 |
| **召回模式**（降级） | bigram 全部 OR `"用户" OR "户令" OR ...` | 模糊匹配，带回噪声 | `用户令牌` → 命中 3 个文档（含仅共享片段的） |

**检索流程**：
1. 先用**精度模式**（标识符整体作短语 + CJK 连续 bigram 作短语）
2. 若精度模式返回 0 条，**降级到召回模式**
3. 两种模式都返回 0 条，才返回 `status: empty`

**查询构造要点**：
- 标识符（`[A-Za-z_][A-Za-z0-9_]*`）**整体成词**，用引号短语匹配
- 中文走 `to_bigrams()`，不要原样放进 `MATCH`
- **绝不对 query 做会丢失信息的重写**（不改写、不同义替换）
- 单字中文查询（如"器"）：bigram 无法生成，退化为 `LIKE '%器%'` 扫描，并在结果中标注 `low_confidence: true`

**索引侧要求**：`to_bigrams()` 必须**同时**应用于入库文本与查询文本。两者不一致是本设计最容易犯的错误——**T1-06 必须有一条断言覆盖这个对称性**。

**代价**：中文文本的索引体积约翻倍（bigram 数量 ≈ 字符数）。这是可接受的代价——一个 10 万 chunk 的仓库 FTS 索引仍在几十 MB 量级。

#### 5.3.2 标点与代码符号：**FTS5 搜不到，必须显式路由**（本机实测）

**这是一条必须先讲清楚的限制**，否则你会以为"搜 `fn(` 没结果"是自己的 bug。

GitHub 官方博客《The technology behind GitHub's new code search》原文（经其 WordPress REST API 取得全文）：

> Searching code also has unique requirements: **we want to search for punctuation (for example, a period or open parenthesis); we don't want stemming; we don't want stop words to be stripped from queries**; and, we want to search with regular expressions.

**本机实测（`forBSH` 环境，SQLite 3.53.4）**——三档 tokenizer 全部失败：

| 查询 | `unicode61` | `trigram` | `porter` |
|---|---|---|---|
| `"("` | ❌ 0 | ❌ 0 | ❌ 0 |
| `"."` | ❌ 0 | ❌ 0 | ❌ 0 |
| `"::"` | ❌ 0 | ❌ 0 | ❌ 0 |
| `"->"` | ❌ 0 | ❌ 0 | ❌ 0 |
| `"self."` | ✅ 1 | ✅ 1 | ✅ 1 |
| `"std::vector"` | ✅ 1 | ✅ 1 | ✅ 1 |
| `LIKE '%(%'` | ✅ 1 | ✅ 1 | — |

**结论（三条，都有实测支撑）**：

1. **FTS5 无法检索短于 3 个字符的标点序列**，**三种 tokenizer 一样**（`trigram` 的最小匹配单位也是 3 字符）。**换 tokenizer 解决不了这个问题。**
2. **`trigram` 只在查询包含 ≥3 个连续字符时才有优势**（如 `self.`、`std::vector`）。所以**它不能替代 bigram 方案**——ADR-07 保持不变。
3. **只有 `LIKE` / `GLOB` 能匹配任意标点**。⚠️ 但**不要假设换 trigram 就能让 `LIKE` 走索引**：本机 `EXPLAIN QUERY PLAN` 在两种 tokenizer 下都得到 `SCAN t VIRTUAL TABLE INDEX 0:` / `0:L0`，**没有出现 `L1` 优化计划**。这条外部说法**未获证实**，采用前必须自己测。

**因此新增 ADR-13（见 §3.7）**，`code_search` 的行为规定为：

| 查询特征 | 行为 |
|---|---|
| 含短标点序列（`(`、`::`、`->`、`[`、`#` 等）且**去掉标点后没有可检索的词** | **不做全表扫描**。返回 `status: empty` + **结构化提示**：`hint: "This looks like an exact code search. Use the grep tool instead — it matches punctuation."` |
| 含标点但**也有可检索的词**（如 `self.authenticate`） | 正常检索——标点被分词器丢弃，剩下的词仍能命中 |
| 模型显式要求精确匹配 | 直接建议 `grep` |

**为什么不自己实现全表 `LIKE` 扫描**：DSH **已经提供了 `grep`**（ripgrep 后端，快得多），而"已知精确符号用 grep"这一点我在调研里反复见到（`dsh-zvec-grep` 的作者明确建议如此）。**重复造一个更慢的 grep 是负收益。**

**明确不要做的事**：
- ❌ **不要用 `porter` tokenizer**——它会做词干化，违反代码检索"不做 stemming"的要求，且对中文无意义
- ❌ **不要为了支持标点去改 ADR-07**——实测证明换 tokenizer 没用
- ❌ **不要在 `code_search` 里偷偷做全表 `LIKE`**——用户会以为它很快

结构化加分（在 SQL 排序后的结果上二次打分，权重可配置但必须有默认值）：

| 信号 | 加分 |
|---|---|
| `symbol_name` 与 query 中的标识符完全一致 | +0.30 |
| `symbol_name` 包含该标识符 | +0.15 |
| 同一文件已有其他命中（局部性） | +0.05 |

**第 2 阶段：可选后端路径（`ADR-16`；**默认关闭**）**

> ⚠️ **这一段不是默认路径。** 它只在 `CODERAG_SEMANTIC=on` 且本机 Ollama 可用时才走；**未配置时引擎只跑上面的第 1 阶段（纯 BM25），输出与 `1.0.0` 逐条一致**（成功标准 `S6`）。后端不可用、URL 非 loopback、模型缺失等情况一律**干净回退纯 BM25**并给结构化状态，不报 `isError`、不返回空列表（`ADR-16` §2/§6、`RL-06`/`RL-09`）。

```
BM25 排名 ─┐
            ├─► RRF 融合（k=60）─► 截断 ─► 顺序保持 ─► 预算裁剪
向量排名 ─┘   （仅当可选后端已启用且可用）
```

RRF 公式：`score(d) = Σ_r 1 / (k + rank_r(d))`，`k = 60`（Elasticsearch / Azure / Weaviate 的默认值）。

> **为什么用 RRF 而不是加权分数**：BM25 分数与余弦相似度**量纲不可比**（前者是无界负数、量级由 IDF 决定，后者在 `[-1, 1]`），加权就需要先归一化，而归一化要引入两套参数并随语料漂移；RRF 只用**排名**，因此免调参、也对分数尺度不敏感。这是 `ADR-14` 选它的理由。
>
> **"补齐而非替换"**：融合后 `exact` 桶必须保持 `S@5 = 1.000`（`ADR-14` §10.4 的 V2、`ADR-16` §7.2）——词法在精确标识符上本来满分，向量只负责把 `natural`/`crossfile` 抬起来。

> ⚠️ **不要把 `k` 设成 2**：Qdrant 的默认值是 2，与主流不同。跨库迁移时这是个经典陷阱。

### 5.4 顺序保持与预算裁剪

**顺序保持（ADR-05）**：检索完成后，把命中的 chunk 按其**在源码中的原始顺序**重新排列输出——即按 `(path, start_line)` 升序。选谁（按分数）与怎么排（按位置）是两个独立决策。

**预算裁剪**：按输出顺序累加 token 估算（`len(text) / 3.5` 作为中英混合的粗估），超过 `max_tokens` 即停止，并在末尾追加一行说明被省略的数量。

### 5.5 安全过滤（最高优先级）

> **这一节不是"最佳实践"，是硬性安全边界。** 依据：Kilo issue #11637 的真实信息泄露事件。

**索引入口的三层过滤，按顺序执行**：

1. **内置密钥黑名单（不可配置关闭）**
   文件名匹配：`.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `.npmrc`, `.pypirc`, `credentials*`, `*_rsa`, `*_ed25519`, `.netrc`, `.git-credentials`
   路径包含：`/.ssh/`, `/.aws/`, `/.gnupg/`, `/.kube/`, `/.docker/config.json`

2. **项目忽略规则**
   依次读取 `.gitignore`、`.coderagignore`（若存在）。使用 `pathspec` 库，不自行实现匹配语义。

3. **内容级二次扫描（对将要入库的 chunk 文本）**
   正则匹配高危模式（`-----BEGIN .* PRIVATE KEY-----`、`AKIA[0-9A-Z]{16}`、`sk-[A-Za-z0-9]{20,}`、`ghp_[A-Za-z0-9]{36}` 等）。命中则该 chunk **不入库**，并记入 `redacted` 列表（只记路径，不记内容）。

**过滤结果必须对模型可见**：`index_status` 与 `code_search` 的返回中要报告 `skipped` / `redacted` 的数量与原因分类。**静默过滤会让模型以为"这段代码不存在"。**

### 5.6 状态与错误

**状态枚举（模型可见，改动必须更新测试快照）**：

| status | 含义 | 模型应该怎么做 |
|---|---|---|
| `ready` | 索引就绪，结果完整 | 正常使用结果 |
| `indexing` | 正在建索引 | 稍后重试，或用 grep 找精确标识符 |
| `empty` | 索引就绪但匹配数为 0 | 换关键词，或用 grep |
| `stale` | 索引存在但工作区已有变更 | 可先用结果，并建议调用 `code_index` |
| `error` | 出错了 | 看 `code` 与 `message` |

**错误码（稳定契约，不得随意改名）**：

| code | 触发条件 |
|---|---|
| `INDEX_NOT_FOUND` | 工作区还没有索引 |
| `FTS5_UNAVAILABLE` | 本机 SQLite 未编译 FTS5（**必须给出可操作提示**，见 `TESTING.md` §4.2） |
| `INDEX_RUNNING` | 已有索引任务在跑 |
| `INDEX_TOO_MANY_FILES` | 超过 `maxFiles`（**必须带上实际数量**） |
| `INDEX_READ_FAILED` | 读取文件失败 |
| `INDEX_WRITE_FAILED` | 写数据库失败 |
| `SEARCH_INVALID_QUERY` | 查询无法解析 |
| `SEARCH_FAILED` | 检索内部错误 |
| `TASK_NOT_FOUND` | taskId 不存在 |
| `CANCELLED` | 任务被取消 |

> **当前发出状态**（2026-09-17，T2 收口）：已实际发出的 code 是 `INDEX_NOT_FOUND`、`SEARCH_INVALID_QUERY`、`TASK_NOT_FOUND`、`SEARCH_FAILED`（含 `_dispatch` 异常兜底）、`INDEX_READ_FAILED`、`FTS5_UNAVAILABLE`（FTS5 缺失时由 `code_search`/`code_index`/`index_status` 返回）；`INDEX_TOO_MANY_FILES` 目前只作为 `TooManyFilesError.code` 经任务 `message` 暴露，尚未以 `code:` 字段返回；`INDEX_RUNNING`、`INDEX_WRITE_FAILED`、`CANCELLED` 尚无发出路径。这是**契约先行**，不是已实现清单。

**铁律**：任何内部异常都**不得**向上冒泡成 MCP 的 `isError` 而丢失结构。必须转成带 `status` 与 `code` 的**正常返回值**，让模型能据此决策。

### 5.7 可观测性

- **结构化日志**：JSON Lines 输出到 `stderr`（**绝不能写 stdout**，stdout 是 MCP 协议通道）。
- 每条日志含：`ts`, `level`, `event`, `task_id`, `duration_ms`, 及事件相关字段。**当前 `index_sync` 不接收 taskman 的 taskId，直接/CLI 索引时该字段为 `null`；经 `code_index` 触发的任务应由 taskman 注入（待补，见 `docs/backlog.md`）。**
- **审计转储**：每次索引结束写一份 `<root>/.coderag/last-index.json`，含文件数、chunk 数、跳过数、被净化数、耗时分解。这是你调试索引质量的主要依据。
- **不采集任何遥测**，不外发任何数据。

### 5.8 评测方法

**评测集设计（M3 的核心工作）**

- 规模：**20–30 个任务**。
- 每个任务由人工从**真实仓库**中挑选，格式：

```jsonc
{
  "id": "E01",
  "kind": "locate",                       // locate | crossfile | behaviour
  "query": "用户令牌是在哪里校验的",
  "expect_paths": ["src/auth/token.py"],  // 必须命中的文件
  "expected_symbols": ["verify_token"],     // 可选，必须命中的符号
  "notes": "故意用自然语言，不含标识符"
}
```

- 三类任务的比例建议：`locate`（含精确标识符）40%、`crossfile`（跨文件）40%、`behaviour`（纯自然语言描述）20%。

**指标计算**

| 指标 | 定义 |
|---|---|
| **Success@k**（主指标） | `expect_paths` 中**至少一个**出现在前 k 条结果里的比例。**注：标准名是 `Success@k` 而非 `Recall@k`**——我们无法声称知道全部相关文件，算不出 Recall 的分母。详见 `EVAL.md` §2.5 |
| MRR | 第一个命中的 `expect_path` 出现位置的倒数 |
| Token 中位数 | 单次返回的 token 估算中位数 |

**对照实验（这是证明价值的唯一方式）**

| 组 | 配置 |
|---|---|
| A · 基线 | 禁用 `code_search`，模型只能用 `grep`/`glob`/`read` |
| B · 词法 | 本项目的 BM25 检索 |
| C · 混合 | **可选后端路径**（`ADR-16`）：B 组 + 向量 + RRF。**默认关闭**，只在 `T3-11` 的 C 组实验里以 `CODERAG_SEMANTIC=on` 开启 |

同一批任务、同一模型、同一随机种子，各跑 1 次（时间允许则 3 次取均值）。

---

## 6. 工作计划

### 6.0 里程碑总览与读法

| 里程碑 | 时间 | 目标 | 出口判据 |
|---|---|---|---|
| **M0** | 开工前 | 环境就绪 | 第 4.5 节清单全部打勾 |
| **M1** | Day 1–2 | **走通闭环**：DSH 里能调用 `code_search` 并拿到有用结果 | 在 DSH 中问一个跨文件问题，工具被正确调用，返回含正确文件与行号 |
| **M2** | Day 3–4 | **检索质量**：tree-sitter 分块、安全过滤、增量索引、outline | 分块抽检 20 个无"半个函数"；`.env` 未被索引；二次索引耗时 < 首次的 20% |
| **M3** | Day 5–6 | **评测与决策**：证明价值，决定是否上向量 | S1/S2/S4 达标；S3 有结论；决策门有明确裁决 |
| **M4** | Day 7 | **可分发**：一条命令安装 | 在干净环境 `dsh plugin add` 成功并可用 |
| **M5** | v2.0.0 | **向量可选后端**：默认关闭的 opt-in 语义检索，补齐 `natural` 桶 | `T5-17`：2.0.0 已发布；**默认路径与 1.0.0 逐条一致**；可选后端开启时 `natural` 桶达标（判据见 `ADR-16`） |

**任务编号规则**：`T<里程碑>-<序号>`，例如 `T1-03`。每个任务必须独立可验收。**带字母后缀的（如 `T3-02a`）是同一任务的批次拆分**，各自独立提交。

> **M5 的两批划分**：`T5-01`–`T5-13` 是**实现前必须完成的文档前置**（决定来源是 `T5-05` 的 `ADR-16`）；`T5-14`–`T5-17` 是探针、安装收尾、冒烟与发布。核心实现复用**已重启**的 `T3-08`–`T3-11`。

---

#### 6.0.1 任务表的读法与依赖约定

**列的含义**：

| 列 | 含义 | 执行要求 |
|---|---|---|
| **ID** | 任务编号 | 一个任务一个提交（`AGENTS.md` §7.0）。**带字母后缀的（如 `T3-02a`）是同一任务的批次拆分**，仍各自独立提交 |
| **任务** | 要做什么 | 一句话，无歧义。括号里的"（条件）"表示仅在决策门命中时执行 |
| **产出文件** | 只允许改这些文件 | 超出范围即为越界，见 `AGENTS.md` §9 |
| **验收命令** | 必须实际执行 | 输出要贴进 §6.7 |
| **期望结果** | 命令输出应满足的条件 | 不满足即未完成 |
| **依赖** | **硬阻塞**：必须先完成的任务 | 见下方约定 |
| **估时** | 参考工时 | 超过 3 倍请停下来报告（`AGENTS.md` §9） |

> **单元格里禁止出现竖线**——包括转义写法 `\|`。`scripts/verify-plan.py` 解析任务表时按朴素的
> `split("|")` 切分、**不认转义**，任何多余竖线都会把行拆错，让「依赖」列读到隔壁单元格的内容
> （`C4`/`D1` 会立刻报错）。验收命令里要表达"或"就用 `grep -e A -e B`；要匹配表格行时，改用
> `scripts/verify-plan.py` 自己的检查结论（它会把计数打进输出），不要用 `grep` 去匹配竖线。
> **例外**：进度表（§6.7）与覆盖矩阵（§6.8）不在 `parse_tasks` 的扫描范围内，那两张表在必须
> 贴表格行时照旧用 `\|`（见 `T4-05` 的证据写法）。

**依赖列的约定（重要）**：

> **依赖列只列「硬阻塞」**——跨里程碑的，或里程碑内顺序敏感的。
> **同里程碑内其余部分按 ID 升序执行即可**，不要求把全部前置关系都写成边。

这条约定的后果是：**很多任务是"叶子"**（没有任何任务依赖它），例如 `T1-02`（`config.py`）、`T1-09`（`render.py`）、`T4-07`（`LICENSE`）。**这是正常的，不是漏边。**

但有一条**必须成立**的约束：**除 `T1-01`（仓库骨架，整棵依赖图的唯一根）外，每个任务都必须能沿依赖边传递追溯到 `T1-01`。** 违反它意味着出现了一个"建在空气上"的孤岛任务——通常是漏了依赖边。

> ⚠️ 判据的精确形式是"**追溯到 `T1-01`**"，不是"追溯到任意 `T1-*`"。后者会让所有 M1 任务自动通过，等于没检查。

这条约束（以及本节的其余约定）由 `scripts/verify-plan.py` 机械校验，见 §6.8。

**执行顺序**：严格按 `T1-01 → T1-02 → … → T4-10` 的 ID 升序，**遇到未完成的依赖就停下**（不要跳过，也不要"先做后面的"）。

### 6.1 M1 — 走通闭环（Day 1–2）

**目标**：用最朴素的实现打通"D​​SH → MCP → Python → SQLite → 返回结果"这条链路。**刻意不做 tree-sitter、不做增量、不做安全过滤的完整版**。

| ID | 任务 | 产出文件 | 验收命令 | 期望结果 | 依赖 | 估时 |
|---|---|---|---|---|---|---|
| T1-01 | 创建仓库骨架与 `pyproject.toml`，包名 `dsh_coderag`，入口 `dsh-coderag` | `pyproject.toml`, `src/dsh_coderag/__init__.py`, `__main__.py` | `pip install -e . && dsh-coderag --version` | 打印版本号，退出码 0 | — | 0.5h |
| T1-02 | 实现 `config.py`：从环境变量读取 `CODERAG_ROOT` / `CODERAG_MAX_FILES` / `CODERAG_MAX_TOKENS`，**必填项缺失时报错而非猜测** | `src/dsh_coderag/config.py` | `python -m pytest tests/test_config.py -q` | 3 个用例通过：正常、缺必填、类型错误 | T1-01 | 0.5h |
| T1-03 | 定义全部数据类与错误码枚举（`Chunk`, `Hit`, `IndexRun`, `SearchStatus`, `ErrorCode`） | `src/dsh_coderag/types.py` | `python -c "from dsh_coderag.types import ErrorCode; print(len(ErrorCode))"` | 打印 ≥ 9（对应 5.6 节的 9 个错误码） | T1-01 | 0.5h |
| T1-04 | 实现朴素遍历器：只按扩展名白名单（`.py .c .h .cpp .hpp .ts .js`）收集文件，**先不做 gitignore** | `src/dsh_coderag/walker.py` | `python -m pytest tests/test_walker.py -q` | 在 fixture 目录上返回预期文件列表 | T1-03 | 1h |
| T1-05 | 实现朴素分块器：按固定 80 行 / 20 行重叠切分（**临时的，M2 会替换成 tree-sitter**），标注 `symbol_kind=None` | `src/dsh_coderag/chunker.py` | `python -m pytest tests/test_chunker.py -q` | 切出的 chunk 覆盖全文且无空洞 | T1-03 | 1h |
| T1-06 | 实现 SQLite schema 初始化（3.6 节中**除 `embeddings` 外**的全部表），含 `PRAGMA journal_mode=WAL`；实现 `to_bigrams()`（§5.3.1）并**断言索引侧与查询侧转换对称** | `src/dsh_coderag/indexer.py` (schema 部分), `src/dsh_coderag/text.py` | `python -m pytest tests/test_schema.py tests/test_text.py -q` | 建库成功；`chunks_fts` 存在且分词器为 `unicode61`；`to_bigrams(to_bigrams(x))` 幂等性测试通过；中文 bigram 往返测试通过 | T1-03 | 2h |
| T1-07 | 实现同步索引：遍历 → 分块 → 事务写入 `files`/`chunks`/`chunks_fts` | `src/dsh_coderag/indexer.py` | `dsh-coderag index tests/fixtures/tiny` 然后 `sqlite3 .../.coderag/index.sqlite3 "select count(*) from chunks"` | 数量 > 0 且与源文件内容匹配 | T1-04, T1-05, T1-06 | 2h |
| T1-08 | 实现 FTS5 检索 + `bm25()` 排序 | `src/dsh_coderag/searcher.py` | `dsh-coderag search "关键词"` | 返回命中的文件路径与行号 | T1-07 | 1.5h |
| T1-09 | 实现 `render.py`：把命中渲染成 3.5 节定义的模型可见格式（**含文件名 + 行号 + 符号名 + chunk 序号**） | `src/dsh_coderag/render.py` | `python -m pytest tests/test_render.py -q` | 快照测试通过 | T1-08 | 1h |
| T1-10 | 实现 `taskman.py` 最小版：`create/status/cancel`，任务状态写 `index_runs` 表 | `src/dsh_coderag/taskman.py` | `python -m pytest tests/test_taskman.py -q` | 状态机 pending→running→ready 正确流转 | T1-06 | 1.5h |
| T1-11 | 实现 MCP server，注册**全部 4 个工具**（`code_search`/`code_outline`/`code_index`/`index_status`），其中 `code_outline` 先返回"暂不支持"的结构化状态 | `src/dsh_coderag/server.py` | `python -m dsh_coderag.server` 后用 stdin 手工发 `initialize` + `tools/list` | 返回 4 个工具，schema 与 3.5 节一致 | T1-03, T1-08, T1-10 | 2h |
| T1-12 | 把 `code_index` 改为**异步**：立刻返回 taskId，后台线程执行（约束 C1） | `src/dsh_coderag/server.py`, `taskman.py` | `code_index` 调用耗时 | < 200 ms 返回 | T1-11 | 1h |
| T1-13 | 实现"索引未就绪"的结构化返回（约束 C6）：`code_search` 在无索引时返回 `status: indexing/empty` 而非 `[]` | `src/dsh_coderag/searcher.py` | `python -m pytest tests/test_status_contract.py -q` | 无索引时返回体含 `status` 字段且不含空数组 | T1-12 | 1h |
| T1-14 | 写仓库根的 `cordis.patch.yml`（**同一个文件既作 dev overlay 也作分发 bundle patch**，因为插入的行引用的是内置包 `@deepseek-ai/dsh-mcp-client`）。python 路径走 `!!js process.env.CODERAG_PYTHON ?? '<默认>'`（约束 C2/E-06） | `cordis.patch.yml` | `npx @deepseek-ai/dsh web --patch ./cordis.patch.yml` | 启动无报错，`--dump-config` 中出现 `mcp-coderag` 行 | T1-11 | 1h |
| T1-15 | **端到端验收**：在 DSH Web 中提问，确认 `mcp__coderag__code_search` 出现且被调用 | — | 人工：问"用户令牌在哪里校验" | 工具被调用，返回含正确文件与行号 | T1-14 | 1h |
| T1-16 | 写 M1 结项记录：把实际观察到的现象（模型何时调用检索、结果是否被采用）记入 `docs/m1-findings.md` | `docs/m1-findings.md` | 文件存在且含 ≥5 条具体观察 | — | T1-15 | 1h |

**M1 出口判据**：`T1-15` 通过 + `T1-16` 完成。

**M1 明确不做**：tree-sitter、增量索引、gitignore、密钥过滤、向量、评测、打包。

---

### 6.2 M2 — 检索质量（Day 3–4）

**目标**：把 M1 的朴素实现替换成生产级实现。

| ID | 任务 | 产出文件 | 验收命令 | 期望结果 | 依赖 | 估时 |
|---|---|---|---|---|---|---|
| T2-01 | 接入 `tree-sitter` + `tree-sitter-language-pack`，实现语言探测（按扩展名映射） | `src/dsh_coderag/parser.py` | `python -m pytest tests/test_parser.py -q` | 对 4 种语言返回正确 grammar | T1-05 | 1.5h |
| T2-02 | 实现**声明感知分块器**（5.1 节 L1）：按 function/class/struct/method 边界切分 | `src/dsh_coderag/chunker.py` | `python -m pytest tests/test_chunker_decl.py -q` | 对 C/C++/Python/TS 各 1 个 fixture，切出数量与人工标注一致 | T2-01 | 3h |
| T2-03 | 实现超大符号降级切分（5.1 节 L2）：>200 行的声明按逻辑块二次切分，加 `#part/N` 后缀 | `chunker.py` | `python -m pytest -k "oversized" -q` | 1000 行函数被切成 ≥5 片且每片含 symbol_name | T2-02 | 1.5h |
| T2-04 | 实现文件头块（5.1 节 L3）与无解析器降级（L4，带 `low_confidence: true`） | `chunker.py` | `python -m pytest -k "module_header or fallback" -q` | 两条用例通过 | T2-02 | 1h |
| T2-05 | chunk 文本拼接上下文前缀（5.1 节末），前缀参与 FTS 索引、渲染时单独成行 | `chunker.py`, `render.py` | `python -m pytest -k "contextual_prefix" -q` | 索引中含前缀、渲染中不重复 | T2-02 | 1h |
| T2-06 | **实现三层安全过滤（5.5 节，最高优先级）**：内置密钥黑名单 + `.gitignore`/`.coderagignore`（`pathspec`）+ 内容级正则扫描 | `walker.py`, `src/dsh_coderag/sanitize.py` | `python -m pytest tests/test_security.py -q` | **关键用例**：含 `.env`、`id_rsa`、`AKIA...` 的 fixture 目录，索引后 `chunks` 表中**零命中** | T1-04 | 3h |
| T2-07 | 过滤结果对模型可见：`index_status`/`code_search` 报告 `skipped`/`redacted` 的数量与原因分类 | `render.py` | `python -m pytest -k "skip_report" -q` | 返回体含 `skipped: {count, reasons}` | T2-06 | 1h |
| T2-08 | 实现内容哈希增量：`files.content_hash` 未变则整文件跳过 | `indexer.py` | `python -m pytest -k "incremental" -q` | 二次索引同一目录，`files` 表无新增行 | T2-07 | 2h |
| T2-09 | 实现三类变更的事务处理：新增 / 修改（先删后插）/ 删除（级联） | `indexer.py` | `python -m pytest -k "add_modify_delete" -q` | 三条用例分别验证 `chunks` 表状态 | T2-08 | 2h |
| T2-10 | 实现**自适应并发与批大小**（5.2 节，约束 C8）：由 CPU/内存推导，动态调整；**参数可被 `IndexConfig` override（未设置时才自适应推导）** | `indexer.py`, `config.py` | `python -m pytest -k "adaptive_concurrency" -q` | 模拟慢/快环境时批大小按规则变化；override 时使用给定值 | T2-09 | 2h |
| T2-11 | 实现文件数上限**显式失败**（5.2 节，约束 C9）：超限时报 `INDEX_TOO_MANY_FILES` 并带 `actual_count` | `walker.py` | `python -m pytest -k "too_many_files" -q` | 错误体含 `actual_count` 与实际数字一致 | T1-04 | 1h |
| T2-12 | 实现任务取消：`code_index` 支持 cancel，工作线程在每个文件边界检查取消标志 | `taskman.py`, `indexer.py` | `python -m pytest -k "cancel" -q` | 取消后状态为 `cancelled` 且不再写库 | T1-10 | 1.5h |
| T2-13 | 实现 `code_outline` 的真实功能（替换 T1-11 的占位实现） | `searcher.py`, `server.py` | `python -m pytest tests/test_outline.py -q` | 对 fixture 文件返回正确的符号树 | T2-02 | 1.5h |
| T2-14 | 实现**顺序保持**（ADR-05）：选按分数、排按 `(path, start_line)` | `searcher.py` | `python -m pytest -k "order_preserving" -q` | 构造分数逆序的输入，输出仍按源码顺序 | T1-08 | 1h |
| T2-15 | 实现 token 预算裁剪（5.4 节）与省略提示 | `searcher.py`, `render.py` | `python -m pytest -k "token_budget" -q` | 超预算时截断且末尾含省略说明行 | T2-14 | 1h |
| T2-16 | 实现结构化日志（JSON Lines 到 **stderr**，绝不写 stdout）与 `last-index.json` 审计转储 | `src/dsh_coderag/log.py` | 运行索引后检查 stderr 与文件 | stderr 每行是合法 JSON；审计文件含 5.7 节全部字段 | T2-10 | 1.5h |
| T2-17 | **M2 端到端验收**：在**本仓库**（DSH 自身，约 3300 个 TS 文件）上跑一次完整索引与检索，记录耗时与质量 | `docs/m2-findings.md` | 人工 | 索引成功；对 5 个真实问题检索，≥4 个找到正确文件 | T2-16 | 2h |
| T2-18 | 分块质量人工抽检 20 个 chunk，记录问题 | `docs/m2-chunk-audit.md` | 文件存在且含 20 条逐条结论 | 无"半个函数" | T2-03 | 1h |
| **T2-19** | **实现标点查询路由（ADR-13）**：`code_search` 检测短标点序列，去掉标点后无可检索词时返回 `status: empty` + 指向 `grep` 的结构化提示；同时确认**未使用 `porter` tokenizer** | `src/dsh_coderag/searcher.py`, `tests/test_tokenizer_semantics.py` | `python -m pytest tests/test_tokenizer_semantics.py -q` | **三条语义测试全绿**：标点路由、无词干化、停用词可检索 | T2-14 | 2h |
| T2-20 | 实现 `code_search` 的 `path` 参数：把检索范围限定到工作区内的子目录 | `searcher.py`, `server.py` | `python -m pytest -k "path_filter" -q` | 传入子目录时只返回该目录下的命中；省略时行为不变 | T1-08 | 1h |
| T2-21 | 实现单文件大小上限（§5.2）：`maxFileBytes` 默认 1 MiB，超过则在读内容前跳过并记 `too_large`；可被 `IndexConfig` / `CODERAG_MAX_FILE_BYTES` 覆盖 | `walker.py`, `config.py` | `python -m pytest -k "too_large" -q` | 超限文件不入库，`skipped.reasons["too_large"]` 与实际数量一致；覆盖值生效 | T2-11 | 1.5h |
| T2-22 | 实现 FTS5 能力探测（TESTING §4.2）与 MCP `_dispatch` 异常兜底（RL-09）：FTS5 不可用时 `index`/`search` 返回 `status: error, code: FTS5_UNAVAILABLE` + 可操作 hint | `sqlite_caps.py`, `indexer.py`, `searcher.py`, `server.py` | `python -m pytest -k "fts5_unavailable" -q` | 模拟不可用时返回结构化错误且不冒泡 `isError`；可用时行为不变 | T1-06 | 2h |

**M2 出口判据**：`T2-06`（安全）、`T2-14`（顺序）、`T2-17`（端到端）、**`T2-19`（分词器语义）** 通过，`T2-18` 抽检无严重问题。

---

### 6.3 M3 — 评测与决策（Day 5–6）

**目标**：用数据回答"检索到底有没有用"，并裁决是否引入向量。

> **本节是 M3 全部任务的唯一权威表。** `EVAL.md` §6 只保留"为什么这么改"的理由，不再定义任务 ID——**一个事实一个家**，避免两处定义漂移。
>
> 本节的任务已合并 `EVAL.md` 的全部修订：拆分 `T3-02` 为 a/b、新增 `T3-04b/c/d`、把 A/B 改为用 `dsh-eval-harness`。

| ID | 任务 | 产出文件 | 验收命令 | 期望结果 | 依赖 | 估时 |
|---|---|---|---|---|---|---|
| **T3-00** | **兼容性验证**：在干净 profile 装 `dsh-eval-harness`，跑通其 `cases/real/` 里一条用例 | `docs/m3-eval-harness-check.md` | `dsh plugin --profile eval-coderag add github:BiBoyang/dsh-eval-harness` | 插件装载成功且能跑一条用例；**若失败则改用 `EVAL.md` §3.6 的自建薄 runner** | T2-17 | 1.5h |
| T3-01 | 设计评测集格式：产出 schema 与构造说明 | `eval/schema.json`, `eval/README.md` | 文件存在；`jsonschema` 能校验 schema 本身 | — | T2-17 | 1h |
| **T3-02a** | **A 批：构造 10 条评测任务**（4 exact / 4 crossfile / 2 natural），流程见 `EVAL.md` §2.4 | `eval/tasks.jsonl` | `python3 scripts/verify-tasks.py eval/tasks.jsonl <被评测仓库>` | 10 条全部通过 schema、路径存在、无答案泄漏 | T3-01 | 1.5h |
| T3-03 | 实现 `dsh_coderag.eval` 的 `load` / `validate` / `run` / `report`。**纯 Python，不调用 LLM** | `src/dsh_coderag/eval/*.py` | `python -m pytest tests/test_eval.py -q` | 跑通 A 批 10 条，产出逐条结果 JSON | T3-02a | 2h |
| T3-04 | 实现指标：Success@1/3/5（**分层 + 总体**）、MRR、token 中位数、**Wilson 置信区间** | `src/dsh_coderag/eval/metrics.py` | `python -m pytest tests/test_metrics.py -q` | 用手工构造样本验证计算正确 | T3-03 | 1.5h |
| **T3-04b** | 实现**失败归因**：每条失败可被打上 `EVAL.md` §2.8 的归因码 `A1`–`A7` | `src/dsh_coderag/eval/attribute.py` | `python -m pytest tests/test_attribute.py -q` | 报告含归因分布 | T3-04 | 1.5h |
| **T3-04c** | 实现**逐 query diff**：报告列出每条 query 的前后对比，并计算**回归条数** | `src/dsh_coderag/eval/report.py` | `python -m pytest tests/test_report_diff.py -q` | 门禁以回归条数为判据，不只看均值 | T3-04 | 2h |
| **T3-04d** | 实现 `golden_version` 校验：不匹配时**直接失败**，除非显式 `--rebaseline` | `src/dsh_coderag/eval/runner.py` | `python -m pytest tests/test_golden_version.py -q` | 版本不符时报错退出 | T3-03 | 1h |
| **T3-02b** | 补足 **B 批 +20 条**（8 exact / 7 crossfile / 5 natural）。**A 批跑出第一组数字后再做，按结果决定重点补哪类** | `eval/tasks.jsonl` | 同 T3-02a 的校验命令 | 30 条全部通过校验 | T3-04c | 3h |
| T3-05 | A 组基线：在 `eval-baseline` 组上跑（`EVAL.md` §3.3），产出基线报告 | `eval/runs/a-v1/` | `python scripts/ab_eval.py run --group eval-baseline ...` | 产出基线报告 | T3-00, T3-02a, T3-15, T3-16 | 2h |
| T3-06 | B 组：在 `eval-coderag` 组上跑，产出对照报告 | `docs/eval-report-m3.md` | `python scripts/ab_eval.py run --group eval-coderag ...` | 报告含**分层指标 + 归因分布 + 逐条 diff** | T3-04d, T3-05, T3-13, T3-14 | 2h |
| **T3-07** | **决策门 M3-DECIDE**：按 `EVAL.md` §2.8 的**精确 R2 条件**裁决（见下） | `docs/adr/ADR-14-semantic-retrieval.md` | 文档含明确结论 + 支撑数据 + 归因分布 | 三条规则之一被明确命中 | T3-06 | 1h |
| T3-08 | **🔁 已重启（`ADR-15` §3；属 M5）** 实现**可选** embedding 生成与缓存（后端、模型与 extra 名由 `ADR-16` 冻结）。**默认关闭**：未配置后端时本模块不得成为导入或启动的阻塞点 | `src/dsh_coderag/embed.py` | `python -m pytest -k "embed" -q` | 同一文本两次调用返回相同向量（缓存生效）；未配置后端时模块可被安全导入且不联网 | T3-07, T5-14 | 3h |
| T3-09 | **🔁 已重启（`ADR-15` §3；属 M5）** 实现**可选**向量存储与暴力余弦检索（numpy；≤10 万 chunk 不引入向量库）。向量索引必须落在**工作区内**（`S-03`） | `src/dsh_coderag/searcher.py` | `python -m pytest -k "vector_search" -q` | top-k 与暴力计算一致；索引路径不越出工作区 | T3-08 | 2h |
| T3-10 | **🔁 已重启（`ADR-15` §3；属 M5）** 实现 RRF 融合（k=60，见 §5.3），并把**未配置/不可用后端时的干净回退**接进 `searcher`（回退后逐条结果与纯 BM25 一致） | `src/dsh_coderag/searcher.py` | `python -m pytest -k "rrf" -q` | 用已知输入验证融合分数；关闭后端时逐条结果与纯 BM25 完全相同 | T3-09 | 1.5h |
| T3-11 | **🔁 已重启（`ADR-15` §3）** 跑 C 组（混合），与 B 组对比，按 `ADR-14` §10.4 的 **V1–V4** 判定是否发布向量路径（**V3 用 α = 0.025**，V4：C 不能显著优于 B 就不发布）。**验收命令已按 `ADR-15` §3.4 换成自建 runner**（原文本引用的 `dsh-eval-harness` API 已废弃） | `docs/eval-report-m3c.md` | `CODERAG_SEMANTIC=on python scripts/ab_eval.py run --cases cases --group eval-coderag-vector --out eval/runs/c-v1 --profile headless --patch cordis.patch.yml --workspace /tmp/dsh-coderag-t3-03-corpus --trials 3` | 报告含 A/B/C 三组对照表，且 V1–V4 逐条给出判定 | T3-10, T5-15 | 2h |
| T3-12 | 回归门禁脚本：L1（pytest）+ L2（`eval_gate`）一键重跑 | `scripts/eval-gate.sh` | `bash scripts/eval-gate.sh` | 退出码 0/1；输出四项指标 + 回归条数 | T3-02b, T3-06 | 1h |
| **T3-13** | **R3 的 A1 修复**：实现 §5.3.1 早已规定的**精度→召回降级**（精度模式 AND 落空时用 OR 重试一次） | `src/dsh_coderag/searcher.py`, `tests/test_cjk_recall.py` | `python -m pytest tests/test_cjk_recall.py -q` | M2 三条中文语义全绿；「标识符 + 中文」混合查询命中；两种模式都空时仍返回 `status: empty` | T3-04b | 1h |
| **T3-14** | **R3 的 A4 修复**：落实 §3.3 第 3 步**结构化加分**——候选池放宽后按「测试路径降级 + `symbol_name` 完全匹配加权」重选 top-k（输出仍按源码顺序，ADR-05 不变） | `src/dsh_coderag/searcher.py`, `tests/test_ranking_signals.py` | `python -m pytest tests/test_ranking_signals.py -q` | 定义处不再被 `tests/`、`*.spec.*` 挤出 top-5；exact 桶 S@5 ≥ 0.90 | T3-04b | 2h |
| **T3-15** | **L2 自建薄 runner**（`EVAL.md` §3.6 降级方案，因 T3-00 判定 harness 不兼容）：fork headless DSH、解析会话日志、执行 §3.4 断言、算 `pass@k`/`pass^k`、与基线做回归门禁 | `src/dsh_coderag/eval/ab.py`, `scripts/ab_eval.py`, `tests/test_ab_eval.py` | `python -m pytest tests/test_ab_eval.py -q` | 离线（无 API key、无网络）覆盖：会话日志解析、9 类断言、`pass@k`/`pass^k` 无偏估计、门禁回归条数；用**假 dsh** 跑通端到端 | T3-00 | 3h |
| **T3-16** | **编写 L2 用例 12–15 条**：locate / crossfile / regression / negative 四桶；每条写出处与理由；答案文件必须在索引内（`credentials*` 被安全过滤，不得作答案） | `cases/*.json`, `tests/test_cases.py` | `python -m pytest tests/test_cases.py -q` | 13 条通过结构校验；设 `CODERAG_L2_CORPUS` 时答案文件全部在索引内 | T3-15 | 2h |

> **🔁 `T3-08`–`T3-11` 已重启（2026-09-23，属 M5）。** 它们曾在 `ADR-15`（2026-09-20）下**显式暂缓**；条件（`T3-07` = R2）当时就已触发，现在按 `ADR-15` §3 的**可选后端**形态恢复执行：**默认关闭 + opt-in，未配置时干净退回纯 BM25，且不得进入必需依赖**。实施前必须先跑**向量天花板探针**（`T5-14`，`ADR-15` §3.2），并由 `ADR-16`（`T5-05`）冻结后端与配置；发布与否服从 `ADR-14` §10.4 的 **V1–V4**（V4：C 组不能显著优于 B 组就不发布向量路径）。**M3 仍然是"决策已闭合"**：本次重启只改执行时机，不改 R2 的事实判断。

**T3-07 的三条判定规则（事先写下，避免事后找理由）**

| 规则 | 条件 | 裁决 |
|---|---|---|
| R1 | Success@5 ≥ 0.80 且 MRR ≥ 0.60 且 S3 提升 ≥ 10 个百分点 | **不需要向量**。项目达成，进入 M4 |
| R2 | Success@5 < 0.80 **且** `natural` 类失败中 **`A5`（零词法重叠）占比 ≥ 50%** | **需要向量**，执行 T3-08..T3-11 |
| R3 | 其他情况 | **先修实现**：按归因分布处理 `A1`–`A4`/`A6`/`A7`，重跑 T3-06，最多迭代 2 次；仍不达标才上向量 |

> **注意 R3 的设计意图**：绝大多数"检索不准"其实是**分词、索引、分块或排序**问题，不是"缺向量"。
> **先怀疑实现，再怀疑架构。** 本机 PoC 已经demonstrated 过一次：trigram 分词器让所有 2 字中文词召回失败（归因 `A1`），当时若直接上向量就是白花钱。

---

### 6.4 M4 — 打包与分发（Day 7）

**目标**：让别人能一条命令装上。

| ID | 任务 | 产出文件 | 验收命令 | 期望结果 | 依赖 | 估时 |
|---|---|---|---|---|---|---|
| T4-01 | 创建 npm bundle 清单：**仓库根**的 `package.json`，声明 `dsh.bundle.patch`，`files: ["cordis.patch.yml"]`，**不含任何 JS 入口**（patch 只引用内置包） | `package.json` | `node -e "console.log(require('./package.json').dsh.bundle)"` | 打印 `{ patch: './cordis.patch.yml' }` | T2-17 | 1h |
| T4-02 | 把 T1-14 的 `cordis.patch.yml` 从"dev overlay"升级为可分发的 bundle patch（本任务只补文档与自检，文件本身应已就绪） | `cordis.patch.yml`, `docs/m4-bundle.md` | `dsh plugin --profile coderag-dev add .` 后 `dsh --profile coderag-dev --dump-config` | 输出中出现本插件的层与 `mcp-coderag` 行 | T4-01 | 1h |
| T4-03 | 写安装脚本 `scripts/install.sh`：检测 conda 环境、`pip install`、**验证 FTS5 + bigram 往返**、打印下一步 | `scripts/install.sh` | `bash scripts/install.sh` | 幂等，可重复运行不报错 | T4-01 | 2h |
| T4-04 | 编写 `README.md`：**顶部必须是安全声明**（约束 E-04）——"安装本插件等于授予它与本机账号同等的权限" | `README.md` | 人工审阅 | 安全声明在第一个屏幕内可见 | T4-01 | 2h |
| T4-05 | README 补全：能力说明、安装、配置、限制、评测数据、已知问题 | `README.md` | 人工审阅 | 含 S1–S4 实测数字 | T4-04 | 2h |
| T4-06 | 在 README 增加「安装故障排查」小节，写明 pnpm 10+ 的 `allowBuilds` 坑（约束 C11）与规避步骤；**本项目无 install script，应在首次 `add` 时就不触发该坑——本任务要用干净 profile 验证这一点** | `README.md`, `docs/m4-install-verification.md` | 人工审阅 + 干净 profile 实测 | 无 install script 报错 | T4-02 | 1h |
| T4-07 | 写 `LICENSE`（**已定为 MIT**，见 §1.6.3）与 `CHANGELOG.md` | `LICENSE`, `CHANGELOG.md` | 文件存在且 `LICENSE` 是 MIT 全文 | — | T1-01 | 0.5h |
| T4-08 | **干净环境验证**：新开一个 profile，从零安装并跑通一次检索 | `docs/m4-install-verification.md` | `dsh plugin --profile clean-test add ...` | 安装成功且工具可用 | T4-02, T4-03 | 2h |
| T4-09 | 在项目 README 与仓库加上 `dsh-plugin` topic（官方 README 第 46 行要求的**唯一**发现机制） | GitHub 仓库设置 | 浏览器确认 | topic 已加 | T4-08 | 0.5h |
| T4-10 | 写 `docs/architecture.md` 与 `AGENTS.md` 的最终版，确保与实现一致 | 两份文档 | 人工对照代码审阅 | 无过时描述 | T4-08 | 2h |

**M4 出口判据**：`T4-08` 在一个**从未装过本项目**的 profile 中通过。

---

### 6.5 M5 — 向量可选后端（v2.0.0）

**目标**：把「纯中文自然语言检索不可用」（L1 `natural` 桶 `S@5 = 0.000`，失败 100% 归因 `A5` 零词法重叠）这一已知短板，以**可选、默认关闭**的后端补齐；**默认路径与 `1.0.0` 逐条一致**。**后端有两个，都默认关闭、都可选**：本地 `ollama`（`ADR-16`）与云端 `openai` 兼容服务（`ADR-17`，2026-09-23 需求变更追加）。

**发布范围约束**（`ADR-15` §3；由 `T5-05` 的 `ADR-16` 冻结成可验收条文）：

- **默认关闭 + opt-in**；未配置时**干净退回纯 BM25**，逐条结果与 1.0.0 一致；
- **不得进入必需依赖**：`pyproject.toml` 的 `dependencies`、bundle 的 tarball、安装脚本的前置条件都不许出现 embedding 相关依赖；
- 后端不可用或未配置时，工具必须返回**结构化状态**并继续以 BM25 工作（`RL-09`），**不得**变成 `isError` 或空列表（`RL-06`）；
- 实施前**必须先跑向量天花板探针**（`ADR-15` §3.2，见 `T5-14`）：用数据决定是否值得全量实施；
- 是否发布向量路径服从 `ADR-14` §10.4 的 **V1–V4**（`V4`：C 组不能显著优于 B 组就不发布）；
- **云端后端额外约束**（`ADR-17`）：非 loopback 地址需要**第二把钥匙** `CODERAG_SEMANTIC_ALLOW_REMOTE=1`；key **只从环境读**、绝不入库入日志（`RL-02`）；**风险声明必须随每一处配置出现**（`D-08`）；`S5`/`V1–V4` **由实际启用的那个后端独立满足**，不得互相背书。

**下表按三批排列**：`T5-01`–`T5-13` 是**实现前的文档前置**（依赖 `T5-05` 的 `ADR-16`），`T5-14`–`T5-17` 是**探针、安装收尾、冒烟与发布**，`T5-18`–`T5-22` 是**云端后端**（2026-09-23 需求变更追加：`ADR-17` + 约束/评测对齐 + 实现 + 打包与风险声明 + 安全评审）；核心实现是已重启的 `T3-08`–`T3-11`。

| ID | 任务 | 产出文件 | 验收命令 | 期望结果 | 依赖 | 估时 |
|---|---|---|---|---|---|---|
| T5-01 | 修 `EVAL.md` 的既有过期项：L2 工具列与第 3 章标题仍写"现成 `dsh-eval-harness`"、`T3-00` 仍写作"新增前置任务"、引用不存在的 `tests/test_retrieval_quality.py` 与 `indexed_workspace` fixture、`eval validate` 缺 `--tasks`/`--root`、`limit` 默认值写成 12（实为 5）、"3~4 小时"与同文件 4–5h 冲突。逐条清单见 `docs/backlog.md`「文档过期项审计」 | `EVAL.md` | `grep -c -e tests/test_retrieval_quality.py -e indexed_workspace -e "limit 默认是" EVAL.md` 以及 `grep -n dsh-eval-harness EVAL.md`，再跑 `python3 scripts/verify-plan.py .` | 前三条 **0 命中**；`dsh-eval-harness` 只出现在 `T3-00` 的**不兼容结论**里、不再作为 L2 的工具选择；门禁全绿 | T4-10 | 1.5h |
| T5-02 | 修 `TESTING.md` 的既有过期项：目录树里的 `test_retrieval_quality.py`（不存在）与 `tests/e2e/`（不存在）、属性测试落点（`test_too_many_files.py` 里没有 hypothesis）、中文用例落点漏了 `test_cjk_recall.py`、不存在的 `indexed_eval_corpus` fixture、`§8` 的"不做多平台矩阵"与 `§5.1` 的"跑多平台矩阵"冲突、`FTS5_UNAVAILABLE` 仍写"必须同步加进去"（已加） | `TESTING.md` | `grep -c -e test_retrieval_quality -e "tests/e2e/" -e indexed_eval_corpus TESTING.md`，再跑 `python3 scripts/verify-plan.py .` | 0 命中；`§5.1` 与 `§8` 对多平台矩阵的口径一致且只有一处结论；门禁全绿 | T4-10 | 1.5h |
| T5-03 | 给 `ADR-14` 的三处决策时快照补**日期化后续状态**（`§7.1` 的"`S3` 未测量"、`§9` 的"未决前置：L2 runner 必须先自建"、`§9` 把已完成的 `T3-12` 仍列在"后续任务"）。**不改写历史结论**，加"后续更新"块说明现状（`D-06` 的边界：ADR 是快照，不是现状描述） | `docs/adr/ADR-14-semantic-retrieval.md` | `grep -c "后续更新" docs/adr/ADR-14-semantic-retrieval.md` | `≥3`（三处各一条），且每处写明日期与当时的实际结果 | T4-10 | 1h |
| T5-04 | 给里程碑快照文档补**日期化后续状态**：`docs/m4-bundle.md` 的"干净 profile 端到端 ⏳ 属 `T4-08`"（`T4-08` 已完成）、`docs/m1-findings.md` 的"`path`/`max_tokens` 尚未生效（T2 范围）"与"召回模式属 T2-19"、`docs/m2-findings.md` 的"缺少精度/召回双模式"（均已在 T2-19/T3-13 落地） | `docs/m4-bundle.md`, `docs/m1-findings.md`, `docs/m2-findings.md` | `grep -c "后续状态" docs/m4-bundle.md docs/m1-findings.md docs/m2-findings.md` | 每份 `≥1`；同一份里同一主题只加一条汇总标注，不逐行改写 | T4-10 | 1h |
| T5-05 | **立 `ADR-16`「向量作为可选后端」**并冻结可验收条文：形态（opt-in / 默认关闭 / 干净回退）、后端与依赖（本地 vs 云端、extra 名）、配置项与环境变量命名、向量索引落点（必须在工作区内，`S-03`）、失败模式与结构化状态、发布范围（2.0.0）、以及引用 `ADR-14` §10.4 的 V1–V4 与 `α = 0.025`。**必须与 `§3.7` ADR 表行、`§6.8` 覆盖矩阵行同一次提交**（`verify-plan` 的 `B1` 强制） | `docs/adr/ADR-16-optional-vector-backend.md`, `PROJECT.md` | `test -f docs/adr/ADR-16-optional-vector-backend.md`，`grep -c "^## " docs/adr/ADR-16-optional-vector-backend.md`，再跑 `python3 scripts/verify-plan.py .` | 文件存在；`≥6` 个二级小节；门禁全绿且 `ADR` 计数 `16`、`§6.8` 矩阵含 `ADR-16` 行 | T4-10 | 2h |
| T5-06 | 按 `ADR-16` 对齐 `AGENTS.md` 的**红线与规范**：`RL-10` 从"决策门前禁止 embedding"改写为"**向量不得进入默认路径或必需依赖；未配置必须干净回退 BM25**"（旧红线的历史使命已由 `T3-07` 完成，见 `ADR-15` §4）；`§3.2` 的"不引入向量数据库（M3 决策前）"改为"不引入向量**数据库**，用 numpy 暴力余弦"；`S-01` 补"本地后端也不得默认启用"；同步 `§6.8` 的 `RL-10` 行 | `AGENTS.md`, `PROJECT.md` | `grep -n -e "禁止在 M3 决策门" -e "向量数据库（M3 决策前）" AGENTS.md`，再跑 `python3 scripts/verify-plan.py .` | 旧表述 0 命中；新表述含"默认路径/必需依赖"与"干净回退"；门禁全绿 | T5-05 | 1.5h |
| T5-07 | 在 `PROJECT.md` §1.4 增加**向量模式的成功标准**（`S5`：可选后端开启时 `natural` 桶的 `S@5` 阈值；`S6`：默认路径零回归——未配置时逐条与 1.0.0 一致）。`S1`–`S4` **不得改名**（§1.4 已声明它们是稳定标识）；同步 `§6.8` 矩阵新增行 | `PROJECT.md` | `python3 scripts/verify-plan.py .` | 输出含 `成功标准 S*: 6 条全部在矩阵里`；门禁全绿 | T5-05 | 1h |
| T5-08 | 对齐 `PROJECT.md` 的**分发形态与选型结论**：`§1.5`/`§1.6` 写清 2.0.0 的"默认安装不变 + 可选 extra"两段式安装；`§2.3`（"为什么第一版不做向量"）补 v2.0 的范围说明并指向 `ADR-16` | `PROJECT.md` | `grep -c "v2.0" PROJECT.md` 再跑 `python3 scripts/verify-plan.py .` | `≥3`；门禁全绿 | T5-05 | 1.5h |
| T5-09 | 对齐 `PROJECT.md` 的**数据模型、依赖与检索路径**：`§3.6` 的"预留的向量表（M3 决策通过后才创建）"改为 v2.0 可选后端的口径；`§4.2` 的"可选（M3 决策通过后才加）"改为 2.0.0 的 extra 名与安装方式；`§5.3` 的向量/RRF 段落标注为"**可选后端路径**"而非默认路径 | `PROJECT.md` | `grep -c "可选后端" PROJECT.md` 再跑 `python3 scripts/verify-plan.py .` | `≥3`；三处均明确"默认关闭"；门禁全绿 | T5-05 | 1.5h |
| T5-10 | 在 `EVAL.md` 把 **C 组（混合）与天花板探针写成可执行方法**：C 组的 profile/env 开关、配对方式、`α = 0.025` 的第二轮口径、`scripts/ab_eval.py run --patch <vector patch>` 的命令形态，以及 `ADR-14` §10.4 的 `V1`–`V4` 逐条落到可判定的断言 | `EVAL.md` | `grep -c -e "C 组" -e "天花板探针" -e "0.025" EVAL.md` 再跑 `python3 scripts/verify-plan.py .` | 三项各自 `≥1`；`V1`–`V4` 每条都有对应的判定命令；门禁全绿 | T5-05 | 1.5h |
| T5-11 | 在 `TESTING.md` 的必测清单新增一条：**「可选后端默认关闭且未配置时回退」**（含"测试必须在无网络、无 Ollama 的条件下通过"的离线约束，`T-02`），并在「对应任务」列引用 `T3-08`–`T3-11` 与 `T5-15` | `TESTING.md` | `grep -c -e "默认关闭" -e "回退" TESTING.md` 再跑 `python3 scripts/verify-plan.py .` | 各 `≥1`；必测清单新增行被 `E2`/`E3`/`E4` 接受；门禁全绿 | T5-05 | 1h |
| T5-12 | 对齐两份 ADR 的**执行状态**（`D-06`：写现状）：`ADR-14` 的"执行：暂缓"、`ADR-15` 的状态行/§1/§3/§5 标注为"已重启为可选后端（2.0.0）"，并保留各自的决策快照性质（不删原始理由） | `docs/adr/ADR-14-semantic-retrieval.md`, `docs/adr/ADR-15-defer-semantic-retrieval.md` | `grep -c -e "已重启" -e "执行中" docs/adr/ADR-14-semantic-retrieval.md docs/adr/ADR-15-defer-semantic-retrieval.md` 再跑 `python3 scripts/verify-plan.py .` | 两份合计 `≥2`；`ADR-15` 仍保留"暂缓"的历史理由；门禁全绿 | T5-05 | 1h |
| T5-13 | 写 `README.md` 与 `docs/architecture.md` 的 **v2.0 说明骨架**（**不含版本号**，版本号属 `T5-17`）：README 新增"可选语义后端"小节（装法、开关、默认关闭、限制如何变化）、`## 已知限制` 里"纯中文自然语言不可用"改为"默认安装下不可用"；`docs/architecture.md` 的模块表与"不做什么"补可选后端路径 | `README.md`, `docs/architecture.md` | `grep -c "可选后端" README.md docs/architecture.md` 再跑 `python3 scripts/verify-plan.py .` | 两份合计 `≥2`；README 的安全声明仍在第一屏（`D-04`）；门禁全绿 | T5-05 | 1.5h |
| T5-14 | 跑**向量天花板探针**（`ADR-15` §3.2）：用一次性脚本对 30 条 query + 全量 chunk 做 embedding，测 `natural` / `crossfile` 的 `S@5` / `MRR` **上限**，给出 go/no-go 结论。**结论决定 `T3-08` 是否继续**；探针脚本不进 `src/`（它不是生产路径） | `docs/m5-vector-probe.md` | `test -f docs/m5-vector-probe.md` 且 `grep -c -e natural -e crossfile -e "S@5" docs/m5-vector-probe.md` | 文件存在；四项指标各自可查；含明确的 go/no-go 结论与所用后端 / 模型 / 耗时 | T5-05 | 2h |
| T5-15 | **可选安装的依赖与安装脚本**：`pyproject.toml` 增加可选 extra `semantic`（内容只有 `numpy`）；默认 `dependencies` **不含** numpy / httpx；`scripts/install.sh` 增加显式开关 `CODERAG_WITH_SEMANTIC` 且**默认路径不装任何向量依赖**。**配置入口与 README 的装法说明由 `T5-21` 负责**（本任务不再重复定义） | `pyproject.toml`, `scripts/install.sh` | `python3 -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print(sorted(d['project']['optional-dependencies']))"` 且 `grep -c CODERAG_WITH_SEMANTIC scripts/install.sh` | extra `semantic` 出现且内容只有 numpy；`dependencies` 不含 numpy / httpx；`install.sh` 默认路径不装任何向量依赖 | T3-10 | 1.5h |
| T5-16 | **可选安装的端到端冒烟测试**（用户指定）：在**全新** `DSH_HOME` 与全新 profile 里跑三件事——（a）默认安装 → 确认没装任何向量依赖、检索逐条与 1.0.0 一致；（b）装可选 extra 并开启后端 → 在 `examples/demo-workspace` 的干净副本上跑通**一次真实语义检索**；（c）后端不可用时 → 返回结构化 `status` 且不报 `isError`（`RL-09`） | `docs/m4-install-verification.md` | `bash scripts/install.sh`（默认态）与 `CODERAG_WITH_SEMANTIC=1 bash scripts/install.sh`（可选态），两态各跑一次 `--dump-config` 与一次 MCP `tools/call` | 两次安装退出码都是 `0`；默认态的解释器里没有 numpy / httpx；可选态下 `code_search` 命中 demo 工作区的目标文件；后端不可用时是结构化状态而不是 `isError` | T5-15 | 2h |
| T5-17 | **发布 v2.0.0**：版本号 `1.0.0` → `2.0.0`（`pyproject.toml`、`package.json`、README 的"当前版本"与示例输出、`docs/architecture.md` 的"实现版本"），`CHANGELOG.md` 增加 `[2.0.0]` 条目；并核对**发布范围**——默认安装没有新增任何必需的 embedding 依赖（`T5-05` 冻结的约束） | `pyproject.toml`, `package.json`, `CHANGELOG.md`, `README.md`, `docs/architecture.md` | `python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"` 且 `node -e "console.log(require('./package.json').version)"` | 两者都打印 `2.0.0`；`CHANGELOG.md` 含 `## [2.0.0]`；README / `docs/architecture.md` 的"当前版本"类字样已是 `2.0.0`（历史证据里的 `1.0.0` 保留不动）；`CHANGELOG.md` 的 `[2.0.0]` 条目要覆盖**两条**可选后端（本地/云端）与风险声明 | T5-16, T5-13, T5-22 | 1.5h |
| T5-18 | **立 `ADR-17`「云端可选后端」并同步约束与矩阵**：冻结形态（与本地对称）、OpenAI 兼容协议、双重开关、key 只从环境读、**风险声明必须随每一处配置出现**（`D-08`）；同时改 `AGENTS.md` 的 `S-01`/`S-02`/`RL-02`/`RL-10`/`E-02` 与 `PROJECT.md` 的 §3.7/§6.8/§1.6.4。**ADR 行与 §6.8 矩阵行必须同一次提交**（`verify-plan` 的 `B1` 强制） | `docs/adr/ADR-17-optional-cloud-embedding.md`, `AGENTS.md`, `PROJECT.md` | `test -f docs/adr/ADR-17-optional-cloud-embedding.md`，`grep -c "^## " docs/adr/ADR-17-optional-cloud-embedding.md`，再跑 `python3 scripts/verify-plan.py .` | 文件存在；`≥6` 个二级小节；门禁全绿且 `ADR` 计数 `17`、矩阵含 `ADR-17` 行（`D-08` 属 `AGENTS.md` 的 `D-0x` 点号系列，与 `D-01`–`D-07` 一样**不进** §6.8 矩阵——那里的 `D1`–`D5` 是 §1.5 的另一套编号） | T5-05 | 2h |
| T5-19 | 按 `ADR-17` 对齐**评测与测试**口径：`EVAL.md` §3.7 补"判据按后端独立判定"与云端失败注入方式；`TESTING.md` 的 `M11` 扩到云端（无 key / 401 / 429 / 超时四种失败都是结构化回退，且**key 不出现在日志/状态/异常**） | `EVAL.md`, `TESTING.md` | `grep -c -e "ALLOW_REMOTE" -e "按后端" EVAL.md TESTING.md` 再跑 `python3 scripts/verify-plan.py .` | 两项各 `≥1`；`M11` 的离线约束仍成立（用不可达地址与假 key，不联网）；门禁全绿 | T5-18 | 1.5h |
| T5-20 | **实现云端后端**（OpenAI 兼容 `/v1/embeddings`）：`urllib` POST + `Authorization: Bearer`、批处理、超时、**重试上限 2**、维度以响应为准；`_BACKEND=openai` 与 `ollama` 共存互斥；**未设 key 时不发起任何请求**；**空字符串（含纯空白）一律等价于「未设」**，让默认值继续生效（`ADR-17` §4 冻结；沿用 `config.py` 既有的 `raw is None or not raw.strip()` 语义，**禁止**用 `os.environ.get(name, default)` 直接取值） | `src/dsh_coderag/embed.py` | `python -m pytest -k "embed" -q` | 离线（无网络、无真 key）覆盖：无 key → `SEMANTIC_AUTH_MISSING` 且**零请求**；401/429/5xx/超时 → 结构化回退 BM25；**key 绝不出现在日志、状态与异常文本里**；`_MAX_CHUNKS` 超限显式失败并报实际数量；**`CODERAG_SEMANTIC_MODEL` 为空串时仍用默认 `bge-m3`**（空串 ≠ 覆盖） | T3-08, T5-18 | 3h |
| T5-21 | **发布前的配置入口与安全警告**：`cordis.patch.yml` 的 `config.env` 留出**两条后端**的**关闭态**入口（空串 = 未设）、`!!js` 形式的 key 投递、以及**逐字风险警告**；`README.md` 重写配置章节（点明**哪些变量 export 不生效**、配置写在哪三处、整体替换规则）并新增云端小节与同一段警告；放松 `AGENTS.md` 的 `RL-02`（允许**仓库之外**的 DSH 本机层用字面 key）并扩 `S-05`（凭据禁入日志）；`.gitignore` 加防误提交护栏 | `cordis.patch.yml`, `README.md`, `AGENTS.md`, `.gitignore` | `grep -c "CODERAG_SEMANTIC_ALLOW_REMOTE" cordis.patch.yml README.md` 且 `grep -c -e "SECURITY WARNING" -e "OFF THIS MACHINE" cordis.patch.yml` 且 `grep -c -e "安全风险" -e "离开这台机器" README.md` 且 `grep -c cordis.patch.local.yml .gitignore`；再跑 `DSH_HOME=<tmp> ./scripts/dsh plugin --profile v add .` 与 `DSH_HOME=<tmp> ./scripts/dsh --profile v --dump-config` | 四个文件各自出现所需内容；patch **组合成功**（`--dump-config` 退出码 0，`env` 块含 `CODERAG_ROOT` + `CODERAG_MAX_TOKENS` + 9 个 `CODERAG_SEMANTIC_*` 共 11 项）；patch 与 README 里**没有任何真实 key**（只有 `!!js` 表达式与 `sk-...` 占位符）；两处警告**要点齐全**（`D-08`：语言随文件，要点一条不少） | T5-18 | 2h |
| T5-22 | **云端后端的安全评审与冒烟**（离线优先）：逐条留原始输出——(a) 仓库与 git 历史无 key（含 `sk-` 模式扫描）；(b) 日志/结构化状态/异常无 key；(c) **外发内容清单**与声明一致（chunk 文本 + 上下文前缀行，含路径）；(d) 无 key / 401 / 429 / 超时四种失败都结构化回退、不 `isError` 不空列表；(e) 未开启时**零网络调用**。**没有真 key 就不跑在线路径**，如实标注「已实现未验证」 | `docs/m5-cloud-security-review.md` | `test -f docs/m5-cloud-security-review.md` 且 `grep -c -e "外发" -e "key" -e "回退" docs/m5-cloud-security-review.md` | 文件存在；三项各自可查；含明确的「离线已验证 / 在线未验证」边界与所用命令 | T5-20, T5-21 | 2h |

---

### 6.6 任务依赖图（**由脚本生成，请勿手改**）

> 本图由 `python3 scripts/verify-plan.py . --emit-graph` 从 §6.1–§6.4 各任务表的「依赖」列**自动生成**。
> **改依赖只改任务表**，然后重跑上面那条命令覆盖本节——`verify-plan.py` 会校验两者逐行一致（检查项 `C5`）。
>
> 记法：`T1-07  ← T1-04, T1-05, T1-06` 读作「T1-07 依赖 T1-04/05/06」。
> `(无硬阻塞)` 表示该任务没有跨里程碑或顺序敏感的前置，按 ID 顺序执行即可（见 §6.0.1）。

```text
# 由 scripts/verify-plan.py --emit-graph 从任务表「依赖」列生成。请勿手改。

T1-01  (根，无依赖)
T1-02  ← T1-01
T1-03  ← T1-01
T1-04  ← T1-03
T1-05  ← T1-03
T1-06  ← T1-03
T1-07  ← T1-04, T1-05, T1-06
T1-08  ← T1-07
T1-09  ← T1-08
T1-10  ← T1-06
T1-11  ← T1-03, T1-08, T1-10
T1-12  ← T1-11
T1-13  ← T1-12
T1-14  ← T1-11
T1-15  ← T1-14
T1-16  ← T1-15
T2-01  ← T1-05
T2-02  ← T2-01
T2-03  ← T2-02
T2-04  ← T2-02
T2-05  ← T2-02
T2-06  ← T1-04
T2-07  ← T2-06
T2-08  ← T2-07
T2-09  ← T2-08
T2-10  ← T2-09
T2-11  ← T1-04
T2-12  ← T1-10
T2-13  ← T2-02
T2-14  ← T1-08
T2-15  ← T2-14
T2-16  ← T2-10
T2-17  ← T2-16
T2-18  ← T2-03
T2-19  ← T2-14
T2-20  ← T1-08
T2-21  ← T2-11
T2-22  ← T1-06
T3-00  ← T2-17
T3-01  ← T2-17
T3-02a  ← T3-01
T3-02b  ← T3-04c
T3-03  ← T3-02a
T3-04  ← T3-03
T3-04b  ← T3-04
T3-04c  ← T3-04
T3-04d  ← T3-03
T3-05  ← T3-00, T3-02a, T3-15, T3-16
T3-06  ← T3-04d, T3-05, T3-13, T3-14
T3-07  ← T3-06
T3-08  ← T3-07, T5-14
T3-09  ← T3-08
T3-10  ← T3-09
T3-11  ← T3-10, T5-15
T3-12  ← T3-02b, T3-06
T3-13  ← T3-04b
T3-14  ← T3-04b
T3-15  ← T3-00
T3-16  ← T3-15
T4-01  ← T2-17
T4-02  ← T4-01
T4-03  ← T4-01
T4-04  ← T4-01
T4-05  ← T4-04
T4-06  ← T4-02
T4-07  ← T1-01
T4-08  ← T4-02, T4-03
T4-09  ← T4-08
T4-10  ← T4-08
T5-01  ← T4-10
T5-02  ← T4-10
T5-03  ← T4-10
T5-04  ← T4-10
T5-05  ← T4-10
T5-06  ← T5-05
T5-07  ← T5-05
T5-08  ← T5-05
T5-09  ← T5-05
T5-10  ← T5-05
T5-11  ← T5-05
T5-12  ← T5-05
T5-13  ← T5-05
T5-14  ← T5-05
T5-15  ← T3-10
T5-16  ← T5-15
T5-17  ← T5-13, T5-16, T5-22
T5-18  ← T5-05
T5-19  ← T5-18
T5-20  ← T3-08, T5-18
T5-21  ← T5-18
T5-22  ← T5-20, T5-21
```

### 6.7 进度追踪表

> 每个任务开工前把状态改为 `进行中`；通过验收后改为 `已完成`，**填上验收命令的实际输出**，并在「提交」列填上 commit 短 SHA。**缺任何一项都视为未完成**（`AGENTS.md` §5.1 的 DoD 七条）。
>
> 提交规范见 `AGENTS.md` §7.0–§7.2：**开工前 `git status --short` 必须为空**，一个任务至少一个提交，主题行 ≤72 字符并带 `Refs: <任务ID>`。

| ID | 状态 | 验收输出（粘贴实际结果） | 提交（短 SHA） | 备注 |
|---|---|---|---|---|
| T1-01 | 已完成 | `$ pip install -e . && dsh-coderag --version`<br>`Successfully built dsh-coderag`<br>`Installing collected packages: dsh-coderag`<br>`Successfully installed dsh-coderag-0.1.0`<br>`dsh-coderag 0.1.0`<br>（forBSH 环境，退出码 0） | `954d1ca` | 产出三文件；仅打包骨架，无独立单测 |
| T1-02 | 已完成 | `$ python -m pytest tests/test_config.py -q`<br>`...                                                                      [100%]`<br>（退出码 0；3 个点 = 3 个用例通过） | `8c11c80` | 正常 / 缺必填 / 类型错误 |
| T1-03 | 已完成 | `$ python -c "from dsh_coderag.types import ErrorCode; print(len(ErrorCode))"`<br>`10`<br>（≥9；§5.6 现有 10 个，含新增的 FTS5_UNAVAILABLE，任务描述里的「9 个」已过时） | `16859d5` | tests/test_types.py 5 例全过；ruff/mypy 通过 |
| T1-04 | 已完成 | `$ python -m pytest tests/test_walker.py -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过） | `1a528cb` | 新增 tests/fixtures/tiny 与 conftest 的 tiny_repo fixture |
| T1-05 | 已完成 | `$ python -m pytest tests/test_chunker.py -q`<br>`..............                                                           [100%]`<br>（退出码 0；14 个用例通过） | `ca85e60` | 固定 80 行 / 20 行重叠；symbol_kind=None；每行至少被一个 chunk 覆盖 |
| T1-06 | 已完成 | `$ python -m pytest tests/test_schema.py tests/test_text.py -q`<br>`....................                                                     [100%]`<br>（退出码 0；20 个用例通过） | `36c000c` | 5 张表（不含 embeddings）；WAL；chunks_fts=unicode61；bigram 索引/查询对称且幂等；§5.3.1 代码块同步为实际实现（原文有首尾空格且非幂等） |
| T1-07 | 已完成 | `$ dsh-coderag index tests/fixtures/tiny`<br>`indexed 3 files, 3 chunks into /Users/vermi/个人项目/python/dsh-coderag/tests/fixtures/tiny/.coderag/index.sqlite3`<br>`$ sqlite3 tests/fixtures/tiny/.coderag/index.sqlite3 "select count(*) from chunks;"`<br>`3`<br>（files: app.ts / lib.c / main.py；行区间 1-3 / 1-3 / 1-2） | `ced4777` | 新增 open_index 与 CLI index 子命令；重复索引不产生重复行 |
| T1-08 | 已完成 | `$ dsh-coderag search add`（在 tests/fixtures/tiny 内，已先 `dsh-coderag index tests/fixtures/tiny`）<br>`lib.c:1-3`<br>`main.py:1-2`<br>`app.ts:1-3`<br>（退出码 0；按 bm25 排序，T2-14 再改为顺序保持） | `716c4db` | 新增 search() 与 CLI search 子命令；无索引时抛 FileNotFoundError，不返回空列表 |
| T1-09 | 已完成 | `$ python -m pytest tests/test_render.py -q`<br>`....                                                                     [100%]`<br>（退出码 0；4 个用例通过，含 2 个 inline-snapshot 快照） | `0e638e8` | 格式见 §3.5；符号缺失时省略 []；omitted>0 时输出 token 预算提示 |
| T1-10 | 已完成 | `$ python -m pytest tests/test_taskman.py -q`<br>`.......                                                                  [100%]`<br>（退出码 0；7 个用例通过，含 pending→running→ready 与持久化） | `e1c51d6` | TaskManager: create/status/cancel + mark_running/ready/failed；非法流转抛 TaskStateError |
| T1-11 | 已完成 | `$ python -m dsh_coderag.server`（stdin 发 initialize + notifications/initialized + tools/list）<br>`{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"experimental":{},"tools":{"listChanged":false}},"serverInfo":{"name":"coderag","version":"0.1.0"}}}`<br>`tools: 4`<br>`names: ['code_search', 'code_outline', 'code_index', 'index_status']`<br>`serverInfo: {'name': 'coderag', 'version': '0.1.0'}`<br>（stdout 全部为合法 JSON-RPC；stderr 为空） | `fcdc300` | 4 工具 schema 与 §3.5 一致；code_outline 返回未实现的结构化状态；code_index 暂同步（T1-12 改异步） |
| T1-12 | 已完成 | `code_index` 内存传输实测（50 个文件的工作区）<br>`elapsed_ms: 3.1`<br>`returned_state: pending`<br>`taskId_prefix_ok: True`<br>`final_state: ready files: 50 chunks: 50`<br>（< 200 ms 要求；后台线程走 pending→running→ready） | `c8aba73` | 新增 TaskManager.start(worker) 后台线程；失败写入 failed + 日志到 stderr |
| T1-13 | 已完成 | `$ python -m pytest tests/test_status_contract.py -q`<br>`...                                                                      [100%]`<br>（退出码 0；3 个用例通过） | `808ac17` | search() 返回 SearchResult；无索引→indexing、无命中→empty、异常→error，均不含裸 [] |
| T1-14 | 已完成 | `$ ./scripts/dsh web --patch ./cordis.patch.yml --dump-config`（E-07：dsh 命令经包装脚本）<br>`- id: mcp-coderag`<br>`  name: '@deepseek-ai/dsh-mcp-client'`<br>`  config:`<br>`    serverName: coderag`<br>`    transport: stdio`<br>`    command: !!js process.env.CODERAG_PYTHON ?? '/opt/anaconda3/envs/forBSH/bin/python'`<br>（rc=0，stderr 为空）<br>配置的 command 实测：`serverInfo {name: coderag, version: 0.1.0}`、`tools [code_search, code_outline, code_index, index_status]` | `41f5d54` | 同一文件兼作 dev overlay 与 bundle patch；未真正 boot web（避免占用 3080），用 --dump-config + 直接跑配置命令验证 |
| T1-15 | 已完成 | 人工验收（DSH Web :3099，工作区 `examples/demo-workspace`，创造模式）<br>问「用户令牌在哪里校验」→ 先 grep×2，再调 `mcp__coderag__code_search`，返回 `status: ready` / `hits: 1` / `── src/auth/token.py:1-20`<br>问「连接池代码在哪？」→ **首发** code_search，参数 `{"query":"连接池 connection pool","limit":10}`，返回 `── src/db/pool.py:1-8` | `cd71afa` | 工具出现且被调用，返回正确文件+行号；R5 部分缓解（未知标识符时优先 code_search，已知标识符仍可能先 grep） |
| T1-16 | 已完成 | `$ test -f docs/m1-findings.md && grep -c '^### 观察' docs/m1-findings.md`<br>`exists`<br>`8` | `7dcdb57` | 8 条具体观察 + 3 条开发期缺陷修复记录 + 已知限制 |
| T2-01 | 已完成 | `$ python -m pytest tests/test_parser.py -q`<br>`......................                                                   [100%]`<br>（退出码 0；22 个用例通过。其中 4 例对 python/c/cpp/typescript 四种 grammar 做实际解析，断言 root 节点分别为 module / translation_unit / translation_unit / program 且 `has_error` 为 False；1 例断言 `EXTENSION_LANGUAGES` 覆盖 `walker.CODE_EXTENSIONS` 全部 7 个后缀） | `ea49999` | 新增 `parser.py`：扩展名→grammar 名映射 + `get_language`/`get_parser`；`pyproject.toml` 钉 `tree-sitter-language-pack>=0.13,<0.14`（原未钉版本装到 1.20.0，实际运行时需联网从 GitHub 下载 grammar，本机实测 `available_languages()==0`、`get_language('python')` 报 DownloadError，离线不可用） |
| T2-02 | 已完成 | `$ python -m pytest tests/test_chunker_decl.py -q`<br>`................                                                         [100%]`<br>（退出码 0；16 个用例通过。其中 4 个语言 fixture 各有一例断言**完整 chunk 列表**（kind/name/start/end）与人工标注逐条一致：sample.py 5 块（4 声明）/ sample.c 3 块（2 声明）/ sample.cpp 4 块（3 声明）/ sample.ts 4 块（2 声明）；另含 2 条 Hypothesis 性质测试：覆盖全文、区间不重叠） | `818ec58` | 新增 4 语言 fixture `tests/fixtures/decl/*`、`decl_repo` fixture 与 `tests/test_chunker_decl.py`；重写 `tests/test_chunker.py`（朴素定长切分被声明感知替换，仅对无 grammar 语言保留非重叠定长 fallback）；chunker.py 按 tree-sitter 声明边界切分，并对声明外非空行补 gap chunk，保证覆盖全文且不重叠 |
| T2-03 | 已完成 | `$ python -m pytest -k "oversized" -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过。1000 行函数切成 5 片，命名 `big_function#part/1..5`，每片 ≤200 行、连续覆盖 [1,1000] 且区间不重叠；`max_chunk_lines` 可覆盖；小声明不加后缀） | `6e9c2fb` | 新增 `tests/fixtures/oversized/big.py`（1000 行）与 `tests/test_chunker_oversized.py`；chunker.py 增加 `MAX_CHUNK_LINES=200`，按 body 直接子语句/注释边界二次切分；`pyproject.toml` 钉 `tree-sitter>=0.25.2,<0.26`（0.26.0 与 language-pack 0.13 不兼容，释放大 Tree 时段错误） |
| T2-04 | 已完成 | `$ python -m pytest -k "module_header or fallback" -q`<br>`.......                                                                  [100%]`<br>（退出码 0；7 个用例通过：3 条 module header（领先区块标记 `symbol_kind="module"`、上限 40 行、文件以声明开头时无 header）+ 4 条 fallback（按空行分段、`low_confidence=true`、覆盖全文、不重叠）） | `1ca177a` | chunker.py 新增 `MODULE_HEADER_LINES=40` 与 `_module_header`；L4 fallback 改为按空行分段并统一标记 `low_confidence`（超 200 行段落再按窗口切分）；移除旧定长 fallback 常量 |
| T2-05 | 已完成 | `$ python -m pytest -k "contextual_prefix" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：每个 chunk 文本以 `// file: ...  \|  symbol: ...  \|  lines M-N` 前缀开头、前缀进入 `chunks.text` 与 `chunks_fts.text_bigram`、渲染时前缀被剥离且代码正文只出现一次、非前缀注释不误伤） | `9fc358a` | chunker.py 为每个 chunk 拼接 §5.1 上下文前缀；render.py 新增 `strip_context_prefix`，输出前剥离（位置信息已由 `── path:lines [symbol] (chunk N)` 单独成行，避免重复、不污染代码正文）；覆盖度/属性测试改为先剥前缀再比对 |
| T2-06 | 已完成 | `$ python -m pytest tests/test_security.py -q`<br>`........                                                                 [100%]`<br>（退出码 0；8 个用例通过：`.env` / `id_rsa` / `credentials.py` / `.gnupg/settings.py` / `config.py`（含 `AKIA...`）均未进入 `chunks`；`ignored_dir/`（`.coderagignore`）与运行时 `.gitignore` 目录被排除；反向用例 `normal.py`、`env_reader.py`（`os.environ`）正常入库） | `72ab575` | 新增 `sanitize.py`（第 1 层文件名/路径黑名单 + 第 3 层内容正则，只返回模式名、不返回或记录内容）；重写 `walker.py` 接入 pathspec（先 `.gitignore` 后 `.coderagignore`，`GitIgnoreSpec`）；`indexer.py` 写库前对每个 chunk 调 `scan_secret`，命中即丢弃，整文件全 redact 时不写 `files` 行；新增 `tests/fixtures/secrets/`（全假凭据）与 `tests/test_security.py` |
| T2-07 | 已完成 | `$ python -m pytest -k "skip_report" -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过：`walk_with_report` 把 `credentials.py`/`.gnupg/settings.py` 计为 `secret_file`、`ignored_dir/skipped.py` 计为 `gitignored`；`search()` 附带 SkipReport 并渲染出 `skipped: 3 (gitignored: 1, secret_file: 2)`；`index_status` JSON 含 `skipped: {count, reasons}`；零跳过时输出 `skipped: 0`） | `7a43bf3` | types.py 加 `SkipReport`；walker 加 `walk_with_report`（`walk` 返回类型不变）；searcher 检索时基于当前 walk 附加 skipped；render.py 新增 `_format_skip_report` 与 `render_status(skipped=...)`；server.py 的 `index_status` 返回 skipped JSON；同步 §3.5 返回格式示例。按方案 A 未做 schema 持久化，redacted chunk 数留待 T2-09/T2-16 |
| T2-08 | 已完成 | `$ python -m pytest -k "incremental" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：二次索引 `files`/`chunks` 的 id 与 content_hash 全部不变、`summary.chunks == 0`；monkeypatch 证明内容未变的文件不再调用 `chunk_text`；改动过的文件被重建；一个文件变更时其它文件 id 不变；文件从正常变为含密钥时旧行被清除） | `bf3d043` | indexer.py：`_index_file` 先算 sha256 与 `files.content_hash` 比对，命中则整文件跳过；新增 `_delete_file_rows` 统一清理；全 redact 分支也清旧行 |
| T2-09 | 已完成 | `$ python -m pytest -k "add_modify_delete" -q`<br>`...                                                                      [100%]`<br>（退出码 0；3 个用例分别验证 chunks 表状态：新增文件后出现其 chunk；修改文件后旧 chunk 被替换（旧符号消失、新符号出现）且 `files` 仍为 1 行；删除文件后其 `chunks`/`files`/`chunks_fts` 行级联清除） | `ea40021` | indexer.py：`index_sync` 收集本次 walk 的路径集合，新增 `_remove_missing_files` 在一个事务内级联删除工作区已不存在的文件；新增/修改沿用 T2-08 的每文件事务（先删后插） |
| T2-10 | 已完成 | `$ python -m pytest -k "adaptive_concurrency" -q`<br>`.........                                                                [100%]`<br>（退出码 0；9 个用例通过：`adaptive_workers(cpu_count=1/4/16)` 得 1/3/8，内存上限把 8 压到 2/1；`next_batch_size` 慢批减半、快批翻倍、中间不变且封顶 512；`IndexConfig(batch_size=7, max_workers=2)` 覆盖生效；env `CODERAG_BATCH_SIZE`/`CODERAG_MAX_WORKERS` 生效；`index_sync(config=...)` 跑通） | `ae0083a` | config.py 新增 `adaptive_workers`/`next_batch_size` 与常量，`IndexConfig` 增可选 `batch_size`/`max_workers` 及 `workers`/`start_batch_size` 属性；indexer.py 重构为「并行 prepare（读+hash+chunk+密钥扫描）→ 自适应批量串行写库」；本机 workers=8，50 文件并发索引实测 files/chunks 均 50，全量套件重复 5 次稳定 |
| T2-11 | 已完成 | `$ python -m pytest -k "too_many_files" -q`<br>`....                                                                     [100%]`<br>（退出码 0；4 个用例通过：3 个可索引文件 + `max_files=2` 时抛 `TooManyFilesError`，`actual_count==3`、`max_files==2`、`code==INDEX_TOO_MANY_FILES`，`payload` 为 `{code, actual_count, max_files, message}`；恰好等于上限不报错；非代码扩展名与密钥文件不计入上限；`index_sync` 超限时在写任何 `files` 行前失败，DB files 计数为 0，绝不静默截断） | `c2d7300` | walker.py 新增 `TooManyFilesError(actual_count, max_files)`（带 `code` 与 `payload`）及 `walk`/`walk_with_report` 的 `max_files` 参数，走完全部文件后超限即抛；indexer.py 把 `IndexConfig.max_files` 传给 walk（无 config 时用默认 20000）；异常 message 含实际数量，异步索引失败时经 `index_status` 可见 |
| T2-12 | 已完成 | `$ python -m pytest -k "cancel" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：`TaskManager.start` 为每个任务建 `threading.Event` 并把 `should_cancel` 传给 worker，`cancel()` 置位并写 `cancelled`；worker 取消后不再 `mark_ready`（状态保持 cancelled）；`index_sync(should_cancel=...)` 在每个文件/批次边界轮询，取消后不写库、不 mark ready；取消前已提交的批次保留） | `366dc8d` | taskman.py 新增 `IndexWorker` Protocol 与每任务 `threading.Event`，`cancel` 置位事件，`_run_worker` 取消后跳过 mark_ready 并容忍 `TaskStateError`；indexer.py `index_sync` 新增关键字参数 `should_cancel`，prepare 与写库循环在每个文件边界轮询 |
| T2-13 | 已完成 | `$ python -m pytest tests/test_outline.py -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过：`outline(sample.py)` 返回 4 个顶层符号 + `class Pool` 下的 `method acquire`（行号 4-5 / 8-9 / 12-14 / 17-19 / 18-19）；`max_depth=1` 不展开方法；未知语言返回空；路径越界抛 `ValueError`；MCP `code_outline` 精确渲染符号树；缺失文件返回 `status: empty`） | `7e28014` | searcher.py 新增 `OutlineSymbol` 与 `outline()`（复用 chunker 的 `DECLARATION_KINDS`/`WRAPPER_NODE_TYPES`，按 body 递归，类内函数标 `method`，wrapper 取外层 span）；server.py 用真实实现替换 T1-11 占位并渲染缩进树；§3.5 增加 code_outline 返回示例；更新原占位断言 |
| T2-14 | 已完成 | `$ python -m pytest -k "order_preserving" -q`<br>`...                                                                      [100%]`<br>（退出码 0；3 个用例通过：`b.py` 命中次数远多于 `a.py`（bm25 更优），但输出仍为 `a.py` → `b.py` 且 `hits[0].score > hits[1].score`；同一文件内多 chunk 按 `start_line` 升序；跨文件按 `(path, start_line)` 稳定排序） | `dfdc0b1` | searcher.py `_search` 的 SQL 加 `c.id` 作为 bm25 并列时的唯一 tiebreaker，取 top-k 后对 hits 按 `(path, start_line)` 重排（ADR-05：选按分数、排按位置） |
| T2-15 | 已完成 | `$ python -m pytest -k "token_budget" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：5 条约 100 字符的命中在 `max_tokens=20` 下只保留 1 条并报 `omitted=4`；大预算全保留；`render_search_result` 末尾输出 `[4 more hits omitted by token budget; raise max_tokens to see them]`；`omitted=1` 用单数；极小预算仍至少保留 1 条） | `59e5fe3` | searcher.py `search` 新增 `max_tokens`（默认 4000），按输出顺序累加 `len(text)/3.5` 裁剪并记录 `omitted`；types.py `SearchResult` 增 `omitted` 字段；render.py 改从 `result.omitted` 生成省略提示；server.py 把 MCP `max_tokens` 传入 search |
| T2-16 | 已完成 | `$ python -m pytest tests/test_log.py -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：`log_event` 每行一个合法 JSON 且含 `ts/level/event/task_id/duration_ms`，stdout 保持为空；索引后 stderr 依次输出 `index_start`/`index_done` 两条合法 JSON；`.coderag/last-index.json` 含 `root/task_id/files/chunks/skipped{count,reasons}/redacted{count}/duration_ms{walk,prepare,write,cleanup,total}`；skipped/redacted 计数正确） | `7f3fb79` | 新增 `log.py`（JSON-Lines 到 stderr + `build_audit_record` + `write_audit_dump`，绝不写 stdout）；indexer.py 在索引起止发日志、按阶段计时、写 `last-index.json`；`_PreparedFile.redacted` 由 bool 改为计数 |
| T2-17 | 已完成 | 人工验收（DSH 参考源码 `0d1f50007f` 的复制，3063 个 `.ts`）：`$ dsh-coderag index <corpus>`<br>`indexed 3074 files, 51230 chunks`（墙钟 **3.42 s**；audit total 3299.0 ms = walk 188.6 / prepare 2066.5 / write 1034.3 / cleanup 1.2；skipped 3 / redacted 2；二次增量 **0 chunk / 0.47 s**）<br>5 个真实问题的标识符改写查询 **5/5 命中正确文件**（Q1 `packages/mcp/mcp-client/src/index.ts` 名次 4；Q2 `.../mcp-client/src/transport.ts` 1；Q3 `packages/sandbox/sandbox-policy/src/session-mode.ts` 2；Q4 `packages/preset/persona/src/index.ts` 1；Q5 `packages/spill/spill-local/src/store.ts` 1）；纯中文原问句 5/5 返回 `empty` | `f47fe4d` | 产出 `docs/m2-findings.md`（索引耗时分解、5 问结果、7 条观察、2 个依赖阻断记录、已知限制）；为遵守 RL-01/S-03 用 rsync 复制目录而非原地索引；发现「中文原问句 AND-of-bigrams 全 empty」与「测试/实验文件在 BM25 中压过实现文件」两项 M2 质量缺口，指向 T2-19/T3 归因 |
| T2-18 | 已完成 | 人工抽检（DSH 参考源码 3074 文件 / 51230 chunk）：`docs/m2-chunk-audit.md` 含 **20 条逐条结论**（4 个 `#part/N` + 4 function + 2 class + 3 interface + 3 module + 4 gap）。核心判据：**声明块 >200 行 = 0**，抽检的 function/class/interface 均边界完整、花括号净 0，**无"半个函数"**。发现 3 个 gap 侧问题：gap 无行数上限（最大 **3080 行**）、gap 碎片化（单行 4980 / ≤2 行 6977）、TS `type`/`const` 未纳入声明（gap 占比 69.6%） | `cc35258` | 产出 `docs/m2-chunk-audit.md`；按 AGENTS §9 把两个越界缺陷记入新增 `docs/backlog.md`（未顺手修）；`#part/N` 拆分不自包含是 §5.1 L2 既定取舍，依赖 T2-05 上下文前缀 |
| T2-19 | 已完成 | `$ python -m pytest tests/test_tokenizer_semantics.py -q`<br>`................                                                         [100%]`<br>（退出码 0；16 个用例全绿，覆盖三条语义：**标点路由** 7 个纯标点查询返回 `status: empty` 且 hint 含 `grep`，而 `self.authenticate`/`std::vector` 正常 READY；**无词干化** `connection` 不命中 `connect_only.py`，且 `chunks_fts` schema 为 `unicode61`、不含 `porter`；**停用词可检索** `for/if/and/in/not` 均命中 `stopwords.py`） | `5f02646` | searcher.py 新增 `_is_punctuation_only`（无标识符/CJK 即路由）与 `PUNCTUATION_QUERY_HINT`，`_build_match` 保持 `to_bigrams` 两侧对称；`tests/test_tokenizer_semantics.py` 在 tmp_path 内建语料。**取舍**：ADR-13 的规则是「去掉标点后无可检索词才路由」，故 `self.(`/`std::` 仍会正常检索（TESTING §3.11 的示例参数与此冲突，以 PROJECT/ADR-13 为准）；按 AGENTS §9 把「精度/召回双模式未实现」记入 `docs/backlog.md` |
| T2-20 | 已完成 | `$ python -m pytest -k "path_filter" -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过：`path="pkg"` 只返回 `pkg/a.py`；省略 path 时四个目录都返回（行为不变）；`path` 可指向单个文件；`my_pkg` 不会因 `_` 通配误匹配 `myXpkg`（LIKE 转义）；`../outside` 返回 `status: error` + `SEARCH_INVALID_QUERY`；MCP `code_search` 传 `path` 生效） | `4c555ee` | searcher.py `search` 新增 `path` 参数与 `_path_prefix`（resolve 后必须仍在工作区内）+ `_escape_like`；`_search` 加 `f.path = ? OR f.path LIKE ? ESCAPE '\'` 过滤；server.py 把工具 `path` 参数传入 search |
| T2-21 | 已完成 | `$ python -m pytest -k "too_large" -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过：超过 `max_file_bytes` 的文件在读内容前被跳过并计入 `skipped.reasons["too_large"]`；`index_sync` 后 `files` 表只含小文件；审计转储含 `too_large`；恰好等于上限的文件保留；`DEFAULT_MAX_FILE_BYTES == 1 MiB`；env `CODERAG_MAX_FILE_BYTES` 覆盖生效） | `8cab6ed` | config.py 新增 `max_file_bytes`（默认 1 MiB）+ env；walker.py `walk_with_report` 用 `stat` 大小在读内容前跳过并记 `too_large`；indexer.py 传入 `config.max_file_bytes`；新增 `tests/test_file_size_limit.py` | |
| T2-22 | 已完成 | `$ python -m pytest -k "fts5_unavailable" -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过：本机 `fts5_available()` 为 True；mock 不可用时 `search()` 返回 `status: error` + `code: FTS5_UNAVAILABLE` + 可操作 hint；`index_sync` 抛 `Fts5UnavailableError`；MCP `code_search`/`code_index` 均返回结构化错误且 `isError` 不为 True；`_dispatch` 兜底把未预期异常转成 `SEARCH_FAILED`） | `2c9b405` | 新增 `sqlite_caps.py`（`fts5_available()` + `Fts5UnavailableError` + `FTS5_HINT`）；searcher/indexer 开库前探测；server 的 `_code_index`/`_index_status` 加 FTS5 守卫、`_dispatch` 加 `except Exception` 兜底（RL-09）；新增 `tests/test_fts5_unavailable.py` | |
| T3-00 | 已完成 | `$ ./scripts/dsh plugin --profile eval-coderag add github:BiBoyang/dsh-eval-harness`<br>首次：`Error: ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED`（git-hosted `prepare` 被 pnpm 10+ 拦截）<br>按报错把精确 key 写入 `allowBuilds` 后：<br>`✓ Lockfile passes supply-chain policies (verified 5m ago)`<br>`Lockfile is up to date, resolution step is skipped`<br>`Done in 2.3s using pnpm v12.4.2`<br>`$ ./scripts/dsh --profile eval-coderag --dump-config`（stderr 0 字节）<br>`# == dsh-eval-harness`<br>`- id: dsh-eval-harness`<br>`  name: dsh-eval-harness`<br>跑 `cases/real/01-bash-tool.yml`：`summary: total 1 / passed 0 / failed 0 / errored 1`；`error: no session log (session.jsonl / session.jsonl.zstd) ...`；DSH 实际落盘 `session.v3.jsonl.zstd` | `49841d3` | 插件可安装、可装载；但 harness 0.4.0 的 trace 收集器只认 v0 文件名，运行用例不兼容。按 T3-00 失败分支改走 `EVAL.md` §3.6 自建薄 runner，T3-05/T3-06 不依赖该插件。详细实际输出见 `docs/m3-eval-harness-check.md` |
| T3-01 | 已完成 | `$ test -f eval/schema.json && test -f eval/README.md && echo "files exist"`<br>`files exist`<br>`$ python3 -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('eval/schema.json'))); print('schema OK')"`<br>`schema OK` | `48fd9ea` | 新增 `eval/schema.json`（JSON Schema Draft 2020-12，约束单条 task）与 `eval/README.md`（字段表、A/B 配比、构造硬规则、校验方法）。`golden_version` 按 EVAL.md §2.7 作为文件级元数据留在 `eval/tasks.meta.json`，不重复进每行。 |
| **T3-02a** | 已完成 | `$ python3 scripts/verify-tasks.py eval/tasks.jsonl /Users/vermi/projects/dsh`<br>`== verify-tasks ==`<br>`tasks : eval/tasks.jsonl`<br>`corpus: /Users/vermi/projects/dsh`<br>`解析到 10 条任务（exact 4 / crossfile 4 / natural 2）`<br>`[V1 ] 读取与解析            PASS  10 条有效任务`<br>`[V2 ] schema           PASS  10/10 条通过 schema.json`<br>`[V3 ] 唯一 ID            PASS  10 个唯一 ID / 10 条`<br>`[V4 ] 路径格式             PASS  14 条路径`<br>`[V5 ] 路径存在             PASS  14/14 条路径存在`<br>`[V6 ] 无答案泄漏            PASS  10 条 query`<br>`[V7 ] exact 标识符存在      PASS  4 条 exact`<br>`[V8 ] natural 无标识符     PASS  2 条 natural`<br>`[V9 ] class 配比         PASS  exact/crossfile/natural = 4/4/2，目标比例 12:11:7（±1）`<br>`[V10] 任务数下限            PASS  10 ≥ 10`<br>`PASS: 10 条任务全部通过 10 项检查`<br>（退出码 0。同一脚本的变异测试：`$ python3 scripts/test-verify-tasks.py` → `PASS: 基线通过，13 个变异全部被预期检查检出`） | `4229eb0` | 新增 `scripts/verify-tasks.py`（V1–V10：解析 / schema / 唯一 ID / 路径格式 / 路径存在 / 无答案泄漏 / exact 标识符真实存在 / natural 零标识符 / class 配比 / 任务数下限）与 `scripts/test-verify-tasks.py`（13 个变异逐一证明每项检查会失败）。**修正 A 批评测集 2 类缺陷**：10 条 `expect_paths` 的前导 `/`（绝对路径，V4 检出）与 L-007 的 `types.ts` 被截断成 `types.t`（V5 检出）。V6 必须带标识符边界，否则 `delegationDepthOf` 里的 `depth` 会误报为泄漏。pytest 221 例全绿，ruff / mypy 干净 |
| T3-03 | 已完成 | `$ python -m pytest tests/test_eval.py -q`（forBSH 环境）<br>`...........................s                                             [100%]`<br>（27 passed / 1 skipped；跳过的 1 条是需 `CODERAG_EVAL_CORPUS` 门控的 A 批集成用例）<br>`$ CODERAG_EVAL_CORPUS=/tmp/dsh-coderag-t3-03-corpus python -m pytest tests/test_eval.py -q`<br>`............................                                             [100%]`<br>（28 passed，A 批集成用例实跑）<br>被评测语料（DSH checkout 的 rsync 副本，遵守 RL-01/S-03 不原地索引）：<br>`$ python -m dsh_coderag index /tmp/dsh-coderag-t3-03-corpus`<br>`indexed 3967 files, 63046 chunks into /private/tmp/dsh-coderag-t3-03-corpus/.coderag/index.sqlite3`<br>`$ python -m dsh_coderag.eval run --tasks eval/tasks.jsonl --root /tmp/dsh-coderag-t3-03-corpus --k 5`<br>`task_count=10 hit_count=1 k=5`<br>`class_counts: {"exact": {"total": 4, "hit": 1}, "crossfile": {"total": 4, "hit": 0}, "natural": {"total": 2, "hit": 0}}`<br>`L-001  exact     hit=True  rank=1    status=ready   matched=packages/mcp/mcp-client/src/index.ts`<br>`L-002  exact     hit=False rank=None status=empty   matched=None`<br>`L-003  exact     hit=False rank=None status=empty   matched=None`<br>`L-004  exact     hit=False rank=None status=empty   matched=None`<br>`L-005  crossfile hit=False rank=None status=empty   matched=None`<br>`L-006  crossfile hit=False rank=None status=empty   matched=None`<br>`L-007  crossfile hit=False rank=None status=empty   matched=None`<br>`L-008  crossfile hit=False rank=None status=empty   matched=None`<br>`L-009  natural   hit=False rank=None status=empty   matched=None`<br>`L-010  natural   hit=False rank=None status=empty   matched=None`<br>（逐条结果 JSON 由 `build_report`/`write_report` 产出；A 批全部 10 条跑通） | `84b1c4e` | 新增 `src/dsh_coderag/eval/`：`tasks.py`（`load_tasks`/`validate_tasks`）、`runner.py`（`run_eval`，直接复用生产 `searcher.search`，k=5 按 EVAL §2.5 选项 A）、`report.py`（逐 query JSON）、`__main__.py`（CLI）、`__init__.py`。**纯 Python、不调 LLM**。测试 27 例用 tmp_path 合成语料（T-03/T-04），1 条 A 批集成用例由环境变量门控。**重要发现**：A 批仅 1/10 命中——9 条含中文 query 全部 `status: empty`，根因是 `_build_match` 把 CJK bigram 一并 AND（裸标识符可回到 top-5：名次 5/3/4）；且 exact 定义处在裸查询下也只排 3–5（被 spec/使用处压过）。二者均**不在 T3-03 范围内**，按 AGENTS §9 记入 `docs/backlog.md`，未顺手修。ruff / `mypy --strict src/` 干净，全量 249 例通过 |
| T3-04 | 已完成 | `$ python -m pytest tests/test_metrics.py -q`（forBSH 环境）<br>`............................                                             [100%]`<br>（28 passed，退出码 0。期望值全部在测试里**手工算出**、不复用实现：Wilson `24/30 → low=0.626943 high=0.904949`，与 EVAL §2.6 的「≈[0.63, 0.90]」一致；边界 `0/10 → [0, 0.277533]`、`10/10 → [0.722467, 1.0]` 不越界；MRR ranks `[1,2,None,4] → 0.4375`；`must_not` 只在 k 前缀内判负；空桶的 success / interval / MRR / token 一律报 `None` 而非 `0.0`；分层测试证明 overall 是「每条 query 等权」的 1/4，而不是类均值 (1.0+0.0)/2）<br>附：同模块跑真实 A 批（`/tmp/dsh-coderag-t3-03-corpus`）得到第一组分层数字：<br>`overall    n=10  S@1=0.100 [0.02,0.40]  S@3=0.100 [0.02,0.40]  S@5=0.100 [0.02,0.40]  MRR=0.100  tokens_med=0`<br>`exact      n=4   S@1=0.250 [0.05,0.70]  S@3=0.250 [0.05,0.70]  S@5=0.250 [0.05,0.70]  MRR=0.250  tokens_med=0`<br>`crossfile  n=4   S@1=0.000 [0.00,0.49]  S@3=0.000 [0.00,0.49]  S@5=0.000 [0.00,0.49]  MRR=0.000  tokens_med=0`<br>`natural    n=2   S@1=0.000 [0.00,0.66]  S@3=0.000 [0.00,0.66]  S@5=0.000 [0.00,0.66]  MRR=0.000  tokens_med=0` | `f238f09` | 新增 `src/dsh_coderag/eval/metrics.py`：`count_hits`/`is_hit_at`/`success_at_k`、`mean_reciprocal_rank`、`median_tokens`、`wilson_interval`（用 `statistics.NormalDist`，**零新依赖**）、`compute_metrics`、`layered_metrics`（overall + 3 桶，宏平均）。`must_not_paths` 与 `expect_symbols` 在**每个 k 的前缀上**判定；空桶显式报 `None`。**未改 `__init__.py` / `report.py`**——指标接线属 T3-04c/T3-06。全量 277 例通过，ruff / `mypy --strict src/` 干净 |
| **T3-04b** | 已完成 | `$ python -m pytest tests/test_attribute.py -q`（forBSH 环境）<br>`..............................                                           [100%]`<br>（30 passed，退出码 0。`classify` 对 7 个码各有一条纯样例，A1/A3 的判据是**目标文件**而非全语料——全语料判据会误标 L-004）<br>A 批真实归因（`/tmp/dsh-coderag-t3-03-corpus`，9 条失败）：<br>`L-002 exact     A1  query 要求命中目标文件里不存在的词 ['定义','义在','在哪']；其中 ['义在','在哪'] 在整个索引中也不存在`<br>`L-003 exact     A1  同上`<br>`L-004 exact     A1  query 要求命中目标文件里不存在的词 ['的定','定义']`<br>`L-005 crossfile A1  目标文件缺少 18 个词，其中 10 个全索引皆无`<br>`L-006 crossfile A5  query 的任何一个词都不出现在目标文件的索引文本中`<br>`L-007 crossfile A5  同上`<br>`L-008 crossfile A1  目标文件缺少 16 个词，其中 11 个全索引皆无`<br>`L-009 natural   A5  同上`<br>`L-010 natural   A5  同上`<br>`distribution: {"overall": {"A1": 5, "A5": 4}, "exact": {"A1": 3}, "crossfile": {"A1": 2, "A5": 2}, "natural": {"A5": 2}}`<br>`natural_a5_share: 1.0` | `76b49e8` | 新增 `src/dsh_coderag/eval/attribute.py`：`collect_evidence`（只读地查文件系统 / `files`+`chunks_fts` / 一次 `probe_k=50` 广搜）+ 纯函数 `classify`（固定优先级 A4→A6→A7/A2→A5→A1→A3）+ `attribute_run` / `attribution_distribution` / `natural_a5_share` / `build_attribution_report`，**零新依赖**。⚠️ **R2 的两项字面条件都已满足**（`S@5=0.10<0.80`、natural 失败 100% 为 A5），但 §2.8 还要求「A1–A4/A6/A7 全部修完再考虑向量」，而 5 条 A1 恰是实现 bug；且当前只是 A 批 10 条。**T3-07 必须显式处理这个冲突，不能直接照字面判 R2**。全量 307 例通过，ruff / `mypy --strict src/` 干净。**后续修复 `bd9fd8d`**：A4 判据原先拿 probe 的**源码顺序位置**与 `run_k` 比较，几乎永不命中，30 条复测时把 2 条 A4 误判成 A3；改为「目标出现在 probe_k 候选集内即 A4」并补了回归用例 |
| **T3-13** | 已完成 | `$ python -m pytest tests/test_cjk_recall.py -q`（forBSH 环境）<br>`......                                                                   [100%]`<br>（6 passed，退出码 0：2 字词可检索；精度模式 `用户令牌` 只命中 `token.py`、排除只含「用户」「令牌」的 `separate.py`；`令牌未定义词` 精度落空后由召回命中；`verify_token未定义词` 混合查询命中；两种模式都空仍是 `status: empty` + hint；标点路由不经过召回）<br>同一语料（`/tmp/dsh-coderag-t3-03-corpus`，查询侧改动**无需重建索引**）A 批前后对比：<br>`exact     S@5 0.250 [0.05,0.70] -> 1.000 [0.51,1.00]   MRR 0.250 -> 0.412`<br>`overall   S@5 0.100 [0.02,0.40] -> 0.400 [0.17,0.69]   MRR 0.100 -> 0.165`<br>`crossfile S@5 0.000 -> 0.000` ｜ `natural S@5 0.000 -> 0.000`<br>逐条：L-002 `empty → ready rank 5`、L-003 `empty → ready rank 5`、L-004 `empty → ready rank 4`；其余 6 条仍未命中<br>归因：`{"overall":{"A1":5,"A5":4}} → {"overall":{"A1":2,"A5":4}}`，`natural_a5_share` 仍为 `1.0` | `e7d7624` | 新增 `_build_recall_match`（OR 构造）与 `_join_phrases`；`search()` 仅在**精度模式 0 条**时用召回模式重试一次，两者都 0 才 `empty`——即 §5.3.1 的流程 1→2→3。**未改精度模式语义**（重叠 bigram 使 AND 等价于精确子串，新文件有断言）。因行为变化同步更新 `tests/test_attribute.py` 里依赖旧行为的 3 个用例——改成直接喂**显式失败结果**只测 collector+classifier，判据未被放宽（T-08）。**exact 桶已回到 EVAL §2.7 的 0.90 阈值之上（1.000）**；crossfile/natural 仍不达标，A5 仍是 natural 失败的全部，故 R2 的字面条件依旧成立——**T3-07 仍须处理 R2 与 §2.8「A1 先修完」的冲突**。全量 314 例通过，ruff / `mypy --strict src/` 干净 |
| **T3-02b** | 已完成 | `$ python3 scripts/verify-tasks.py eval/tasks.jsonl /Users/vermi/projects/dsh`<br>`解析到 30 条任务（exact 12 / crossfile 11 / natural 7）`<br>`[V1 ] 读取与解析            PASS  30 条有效任务`<br>`[V2 ] schema           PASS  30/30 条通过 schema.json`<br>`[V3 ] 唯一 ID            PASS  30 个唯一 ID / 30 条`<br>`[V4 ] 路径格式             PASS  46 条路径`<br>`[V5 ] 路径存在             PASS  46/46 条路径存在`<br>`[V6 ] 无答案泄漏            PASS  30 条 query`<br>`[V7 ] exact 标识符存在      PASS  12 条 exact`<br>`[V8 ] natural 无标识符     PASS  7 条 natural`<br>`[V9 ] class 配比         PASS  exact/crossfile/natural = 12/11/7，目标比例 12:11:7（±1）`<br>`[V10] 任务数下限            PASS  30 ≥ 10`<br>`PASS: 30 条任务全部通过 10 项检查`<br>（退出码 0，被评测仓库 `/Users/vermi/projects/dsh`） | `43a2b65` | 新增 **L-011..L-030**（8 exact / 7 crossfile / 5 natural），凑齐 12/11/7。**每行的 `notes` 都写了出处（`file:line` + 原文片段）与选取理由**；crossfile 全部改成「定义处 → 使用/写入处 → 复用/封锁处」的三文件链路。**按用户指示提前执行**：任务表原依赖 `T3-04c`（尚未完成），此处按 A 批已暴露的 crossfile/natural 缺口定重点，未使用 `T3-04c` 的 diff。**未跑 L1 评测**——用户要先人工排查 query 是否泄漏答案，在其复核前不对评测集调参（EVAL §2.9 陷阱 3/14）。⚠️ `eval/tasks.meta.json` 尚未创建（属 T3-04d），**T3-04d 必须把初始 `golden_version` 定为本次 B 批后的状态**，否则踩 EVAL §2.9 陷阱 15。golden 集改动已按 EVAL §2.7 单独成一个提交（`43a2b65`） |
| **T3-14** | 已完成 | `$ python -m pytest tests/test_ranking_signals.py -q`（forBSH 环境）<br>`..........                                                               [100%]`<br>（10 passed，退出码 0：先断言**原始 bm25 冠军确实是 spec**、再断言选中 impl；四种测试路径形态（`tests/`、`__tests__/`、`*.spec.*`、`*.test.*`）都被降级，而 `tests_helper.py` 不被降级；输出仍按源码顺序、结果可重复；`symbol_name` 完全匹配可在 SQL 中被加权、部分匹配不加权）<br>30 条 golden 集复测（同一语料，查询侧改动**无需重建索引**）：<br>`exact     S@5 0.833 -> 1.000 [0.76,1.00]   MRR 0.582 -> 0.700`<br>`crossfile S@5 0.000 -> 0.091 [0.02,0.38]   MRR 0.000 -> 0.091`<br>`natural   S@5 0.000 -> 0.000`<br>`overall   S@5 0.333 -> 0.433 [0.27,0.61]   MRR 0.233 -> 0.313`<br>逐条：L-013 `未命中 -> rank 1`、L-018 `未命中 -> rank 3`、**L-005 `未命中 -> rank 1`**；L-003 名次 5→3<br>归因：`{"A4":2,"A1":2,"A5":16} -> {"A5":16,"A1":1}`，**A4 清零** | `1559cf3`, `0d269d1` | 两轮迭代。**第一轮**（`1559cf3`）：候选池放宽到 `max(4k,20)` 后按 `selection_key` 重排，测试路径整体降到非测试之后（无魔数），`symbol_name` 完全匹配减 `SYMBOL_MATCH_BOOST=2.0`。**第二轮**（`0d269d1`）：(a) 把测试路径降级**移进 SQL 的 ORDER BY 第一层**——原来的池 20 会被 `*_spec/*.e2e` 打满、目标根本进不了池（L-005 正是这样漏的），放进 SQL 后 `LIMIT k` 直接看到最终排序，候选池常量随之删除；(b) 召回从两级改为**三级**（精度 AND → 仅标识符 OR → 含 CJK bigram 的 OR），因为中文 bigram 精度极低，在带 `locales.ts` 的仓库里会以超高 bm25 压掉真正的代码。输出顺序始终 `(path, start_line)`（ADR-05 不变）。**未实现** §3.3 的「同文件局部性加权」与「声明定义处加权」——数据不支持，未引入。全量 326 例通过，ruff / `mypy --strict src/` 干净 |
| **T3-07** | 已完成 | `$ test -f docs/adr/ADR-14-semantic-retrieval.md && echo "ADR-14 exists" && wc -l < docs/adr/ADR-14-semantic-retrieval.md`<br>`ADR-14 exists`<br>`168`<br>`$ grep -n "R2 命中\|natural_a5_share = 1.0\|\"A5\": 16\|裁决：R2" docs/adr/ADR-14-semantic-retrieval.md`<br>`54:overall   {"A5": 16, "A1": 1}`<br>`58:natural_a5_share = 1.0`<br>`88:| R2 | S@5 < 0.80 且 natural 失败中 A5 ≥ 50% | 0.433 < 0.80 ✅；natural_a5_share = 1.0 ≥ 0.50 ✅ | ✅ **命中** |`<br>`91:**裁决：R2 命中 → 引入向量检索。**`<br>（文档含明确结论 + 分层指标与 Wilson CI + 归因分布 + 30 条逐条结果 + R1/R2/R3 对账 + 6 条限制） | `8842a38` | 新增 `docs/adr/ADR-14-semantic-retrieval.md`（`docs/adr/` 此前不存在，这是第一个 ADR 文件）。**裁决：R2 命中 → 引入向量**（执行 T3-08..T3-11），并明确"**只补齐、不替换**"——exact 已 1.000，替换只会回退。**执行偏差**：`T3-07` 原依赖 `T3-06`（B 组 L2 对照），本次在 `T3-06` 未完成时裁决，原因与边界写在 ADR §9——R2 只看 L1 指标，而 **S3 未测量**，所以结论只覆盖"词法够不到中文自然语言"，**不等于"向量能提升端到端"**。ADR §4 记录了决策前按 §2.8 但书修完 A1（T3-13）与 A4（T3-14）、避免踩 §2.9 陷阱 8；§7 列出 6 条必须与结论同时引用的限制（30 条 CI 宽 [0.274,0.608]、诊断配比非真实流量、L-008 判据偏差、第二轮对比需把 α 收紧到 0.025 等）。**后续 `ADR-15`（2026-09-20）：R2 结论保留但执行暂缓**——v1.0 不含向量，`T3-08`–`T3-11` 标为暂缓，后续版本以**可选后端**引入（默认关闭）。依据是 S3 已由纯词法 + 采纳率修复达成（+59.0pp）、分块修复实测对 S1/S2 零收益、以及向量要求用户装 Ollama + 1.2 GB 模型 |
| **T3-15** | 已完成 | `$ python -m pytest tests/test_ab_eval.py -q`（forBSH 环境）<br>`........................................                                 [100%]`<br>（40 passed，退出码 0，**全程离线**：无网络、无 API key。覆盖用例加载与 4 类非法输入、会话日志解析（tool/最终文本/步数/turn_end/usage/interrupted/错误结果）、会话发现（版本化文件名、跳过子代理日志、压缩日志给出可操作报错、多根歧义）、9 类断言的通过与失败、`pass@k`/`pass^k` 的**无偏**组合数定义、命令构造、门禁回归条数与 delta、两种 Markdown 报告，以及用**假 dsh** 跑通的端到端）<br>`$ python scripts/ab_eval.py --help`<br>`usage: ab_eval.py [-h] {run,gate} ...`<br>`L2 end-to-end A/B runner for dsh-coderag.`<br>`$ python scripts/ab_eval.py gate --baseline ... --current ...` 退出码 0/1 = 门禁是否无回归 | `adbcdbb` | 新增 `src/dsh_coderag/eval/ab.py`（全部逻辑）、`scripts/ab_eval.py`（薄 CLI）、`tests/test_ab_eval.py`（40 例）。补齐了 `T3-00` 判定失败后 `EVAL.md` §3.6 一直悬空的自建 runner。**三处与骨架的有意差异**（已同步进 `EVAL.md` §3.6 表）：① 读 `session.v{version}.jsonl`，通过 overlay 把 `session-persistence-jsonl` 配成 `compression: none`，**因此不需要 zstd 依赖**；② 用例是 **JSON 不是 YAML**（项目未声明 YAML 依赖、`mypy`/测试环境也没有，不为一个用例格式加依赖）；③ 实现 §3.4 的 9 类断言，`output_judge` **显式报错拒绝**而不是静默忽略。`pass@k`/`pass^k` 用 `C(c,k)/C(n,k)` 无偏估计，门禁看**回归条数**。**未运行真实 A/B**（需要模型 API key，且要先把 DSH 副本索引好）——那是 `T3-05`/`T3-06`。同时更新了 `T3-05`/`T3-06` 的验收命令（不再引用不可用的 `dsh-eval-harness`）。全量 366 例通过，ruff / `mypy --strict src/` 干净。**后续修复（T3-05 冒烟暴露，各自单独提交）**：`cea83f3` 断言匹配折叠 DSH 的 `mcp__<server>__` 命名空间——真实日志写 `mcp__coderag__code_search` 而用例断言裸名 `code_search`，导致 9 条 `tools_called: [code_search]` **无论表现多好都恒判失败**（用 A/B 冒烟日志离线重算：B 由 4/13 翻到 9/13，A 不变）；`d47f317` `run_group` 入口把 `out_dir`/`workspace`/`dsh`/`patches`/`dsh_home` 解析为绝对路径并对缺失启动器/patch/workspace 快速失败——子进程 `cwd=workspace`，相对 `--dsh`/`--patch`/`--out` 会被重新基准化而静默失败（修复前字面命令 13 条全部 `无法启动 dsh：[Errno 2]`）。runner 测试 40 → 52 例，全量 386 例通过 |
| **T3-16** | 已完成 | `$ python -m pytest tests/test_cases.py -q`（forBSH 环境）<br>`.........s                                                               [100%]`<br>（9 passed / 1 skipped；跳过的 1 条是需要语料的索引成员校验）<br>`$ CODERAG_L2_CORPUS=/tmp/dsh-coderag-t3-03-corpus python -m pytest tests/test_cases.py -q`<br>`..........                                                               [100%]`<br>（10 passed：**13 条用例的 answer_paths 全部在索引内**） | `3597b3a` | 新增 `cases/*.json` **13 条**（locate 4 / crossfile 5 / regression 2 / negative 2）与 `tests/test_cases.py`。每条在 `notes` 里写了**出处（`file:line` + 符号）与选取理由**，`answer_paths` 作为复核元数据（不参与判分，但被测试用来卡"答案文件必须在索引里"这个公平性陷阱）。**桶的设计意图**：`locate`/`crossfile` 断言 `tools_called: [code_search]`（同时测检索质量与工具采纳）；`regression` **不**断言工具被调用，用来验证"检索不该让简单题变差"；`negative` 是**反臆造控制组**，断言只要求出现"没有/not found"一类措辞——两条负例（Kafka、Elasticsearch）都在全副本 grep 过 **0 命中**。**未运行**（需要 API key）——那是 `T3-05`/`T3-06`。**后续 `7a9936b`**：每条用例补 `accept`/`reject` 审核样例，测试逐条真跑正则（必须接受全部正确、拒绝全部错误）——这一关当场抓到两条反臆造控制组的假通过（`没有` 匹配到「我没有细看」），收窄为「否定词 + 技术名」后修掉；另收紧 8 条过松/过严正则。**审核办法直接写在对话里，不额外产出文档**；出处与理由留在每行的 `notes` 里。全量 376 例通过，ruff（我新增的文件）/ `mypy --strict src/` 干净。**后续 `a94054f`**：crossfile 桶 `max_steps` 12→16（T3-05 冒烟发现 12 连基线都误杀——`crossfile-todo-snapshot` 的 `output_matches` 在 A/B 两组都已通过，只是步数超限；正确性由答案断言独立把关，16 对另外 4 条 crossfile 用例非绑定） |
| **T3-05** | 已完成 | `$ python scripts/ab_eval.py run --cases cases --group eval-baseline --out eval/runs/a-v1 --profile headless --workspace /tmp/dsh-coderag-t3-03-corpus --trials 3`<br>`eval-baseline: taskSuccess 0.3076923076923077 (12/39) -> eval/runs/a-v1/report.json`<br>（39 次 attempt 的 `error` 全为空、`session_log` 全非空；A 组墙钟约 22 min） | `2a2e8d8`（产物入库） | trials=3。分层：`locate 0/12`、`crossfile 0/15`、`regression 6/6`、`negative 6/6`；Wilson 95% `[0.186, 0.464]`。基线无 `code_search`，**凡断言 `tools_called: [code_search]` 的 9 条必失败**，且失败原因全是该断言本身而非答错；4 条不涉及该断言的用例（negative×2、regression×2）全过。语料 `/tmp/dsh-coderag-t3-03-corpus`（3967 文件 / 63046 chunk，`chunks_fts` 同数）。产物**已入库**：`2a2e8d8` 把 `eval/runs/` 的报告与门禁结论纳入 git，只忽略原始 `.sessions/` 与每次重跑都会变的派生输出（`l1-current`/`l1-gate`）——这是"工作区干净"（`AGENTS.md` §7.0）与 CI 里 L1 门禁能生效的前提 |
| **T3-06** | 已完成 | `$ python scripts/ab_eval.py run --cases cases --group eval-coderag --out eval/runs/b-v1 --profile headless --patch cordis.patch.yml --workspace /tmp/dsh-coderag-t3-03-corpus --trials 3`<br>`eval-coderag: taskSuccess 0.5641025641025641 (22/39) -> eval/runs/b-v1/report.json`<br>`$ python scripts/ab_eval.py gate --baseline eval/runs/a-v1/report.json --current eval/runs/b-v1/report.json --out eval/runs/gate-v1.json --markdown eval/runs/gate-v1.md`<br>`delta: +25.6pp ｜ S3(≥+10pp): True ｜ gate: PASS（回归 0 条）`<br>`改善 6 条，回归 0 条` | `5a867a7` | 产出 `docs/eval-report-m3.md`（**分层指标 + 逐条 diff + L2 失败归因**）。**核心结论：接入 coderag 的 B 组比不接入的 A 组高 `+25.6pp`（0.308 → 0.564），S3 成立**。提升全部来自 `locate`（0 → 0.333）与 `crossfile`（0 → 0.400）；`regression`/`negative` 两组均 1.000，即 A 组也过的 4 条**无区分度**。B 的 17 条失败中 **16 条是没调用 `code_search`**（R5 工具采纳），1 条工具报错，**0 条 `max_steps` 撞顶**——没有一条是"检索返回了错误文件"，故 `+25.6pp` 衡量的是"工具被采纳的用例变多"，不是排序变准（后者属 L1）。`pass@3` A 4/13 → B 10/13；`pass^3` 两组均 4/13（尚未把任何用例变成 3/3 稳定通过）。Wilson 区间 `[0.186,0.464]` vs `[0.410,0.707]` 有重叠且 attempt 间不独立，`+25.6pp` 是小样本估计，不等于真实流量上的效应。`eval/runs/` 的报告与门禁结论已入库（`2a2e8d8`）；原始 `session.v3.jsonl` 按 `.gitignore` 排除。**R5 之后的当前 B 组见 `T3-06` 的后续记录与 `docs/eval-report-m3.md` §9**（taskSuccess 0.897、S3 +59.0pp） |
| **T3-04c** | 已完成 | `$ python -m pytest tests/test_report_diff.py`（forBSH 环境）<br>`.......................                                                  [100%]`<br>`23 passed in 0.07s`<br>真实金标集（30 条，`/tmp/dsh-coderag-t3-03-corpus`）：自比 + 注入一条回归<br>`[self-diff] compared=30 regressions=0 unchanged=30 gate_passed=True`<br>`[one flipped] victim=L-001 regressions=1 gate_passed=False`<br>`## 回归（命中 → 未命中）`<br>`- **L-001**（exact）：hit #1 (packages/mcp/mcp-client/src/index.ts) → miss ｜ DEFAULT_TOOL_CALL_TIMEOUT_MS`<br>全量 `412 passed, 2 skipped`；`ruff check src tests` / `mypy --strict src/` 干净 | `350c99a` | `report.py` 新增 `QueryDiff` / `diff_runs` / `gate_diff` / `render_diff_markdown`，加 `tests/test_report_diff.py` 23 例。**口径**：只有"命中→未命中"算回归，名次变化单列 `rank_improved`/`rank_regressed`；只对比**两侧都存在**的 query，单侧的进 `only_in_baseline`/`only_in_current` 且**不计入回归**；命中率只按可比集合计算，避免"增删一条 query"污染均值。**门禁默认容忍 0 条回归**：EVAL §2.7 引的"≥2 条才失败"是行业起点，同节又说本项目更严（"有没有单条回归"），且 L2 的 `ab.py` 已是"任何回归即失败"，故取更严口径并留 `max_regressions` 显式放宽。`waivers` 保留人工豁免通道（对应 EVAL §2.7 的"除非能解释清楚"），被豁免的回归仍列出，**未匹配到回归的 waiver 显式报出**（不静默吞掉）。`k` 不一致直接报错（排名不可比）；schema 或结果行非法报错。**未改 `__main__.py`**（T3-04c 的产出文件只有 `report.py`），CLI 接线留给 `T3-12` 的 `eval-gate.sh` |
| **T3-04d** | 已完成 | `$ python -m pytest tests/test_golden_version.py`（forBSH 环境）<br>`..................                                                       [100%]`<br>`18 passed in 0.21s`<br>真实金标集（30 条）三种走法：<br>`$ python -m dsh_coderag.eval run --tasks eval/tasks.jsonl --root /tmp/dsh-coderag-t3-03-corpus --expect-golden-version m3-b1`<br>`tasks 30 / hit 13 (k=5, corpus=/tmp/dsh-coderag-t3-03-corpus, golden_version=m3-b1)` → **exit 0**<br>把 `--expect-golden-version` 换成 `m3-b2`：<br>`golden_version 不匹配：期望 'm3-b2'，实际 'm3-b1'。改了 golden 集就必须同步升版本号，否则分数变化无法归因（EVAL.md 2.7 / 2.9 陷阱 15）。若本次确实是在重建基线，请显式传 --rebaseline。` → **exit 2，且未写出报告**<br>同上再加 `--rebaseline` → exit 0<br>全量 `430 passed, 2 skipped`；`ruff check src tests` / `mypy --strict src/` 干净 | `9a96ee7` | 新增 `eval/tasks.meta.json`（**初始 `golden_version = m3-b1`**，即 T3-02b 冻结的 30 条 B 批状态）与 `tests/test_golden_version.py` 18 例；`runner.py` 新增 `GoldenMeta` / `load_golden_meta` / `check_golden_version` / `GoldenVersionError`，`EvalRun` 带上 `golden_version` 作为溯源字段；`__main__.py` 的 `run` 增加 `--expect-golden-version` 与 `--rebaseline`。**校验发生在 `validate_tasks` 与任何检索之前**——方法论破坏要快速失败，不能跑完再报（有专门用例锁这一点）。元数据缺失、JSON 非法、`golden_version` 缺失/空/非字符串**一律报错，不设默认值**。**范围说明**：本任务「产出文件」只列了 `runner.py`，但"版本不符时报错退出"必须落到 CLI，故一并改了 `__main__.py`；`eval/tasks.meta.json` 由 T3-02b 的备注明确指派给 T3-04d；`eval/README.md` 同步为当前状态。**未把 `golden_version` 写进报告 JSON**（那属 `report.py`，本任务范围外）——目前只在 stderr 摘要与 `EvalRun` 上可见，**建议后续补进报告**以支持报告级溯源 |
| **T3-12** | 已完成 | `$ bash scripts/eval-gate.sh`（`CODERAG_GATE_PYTHON` 指向 forBSH python）<br>**干净基线**：`══ 门禁：PASS ══`，**退出码 0**<br>`S1 Success@5    = 0.433`<br>`S2 MRR          = 0.313`<br>`S4 token_median = 2492`<br>`S3 E2E delta    = +25.6pp`<br>`回归条数        = L1 0（逐 query） + L2 0（用例级） = 0`<br>**注入一条回归**（把 baseline 里一条 miss 改成 hit 再跑）：`回归条数 = L1 1（逐 query） + L2 0（用例级） = 1` → `══ 门禁：FAIL ══`，**退出码 1**<br>全量 `440 passed, 2 skipped`；`ruff check src tests` / `mypy --strict src/` 干净 | `7ff58c6` | 新增 `scripts/eval-gate.sh` 与 `tests/test_eval_gate_cli.py`（5 例）。脚本串起三层：L1 `pytest` → **L1 指标 + 逐 query 门禁**（`python -m dsh_coderag.eval gate`）→ **L2 A/B 门禁**（`scripts/ab_eval.py gate`），输出 **S1–S4 + 回归条数**。**退出码 0/1/2**：0 通过、1 有回归 / pytest 红 / L2 FAIL、2 环境不可用（缺语料或缺 baseline）——**缺 baseline 绝不静默放行**。为拿到 S1/S2/S4，`eval/__main__.py` 新增 `gate` 子命令（**T3-04c 备注里明确把这条接线留给 T3-12**）：它把 **baseline 报告里的 `golden_version` 当作 pin**，于是"改了题却没升版本号"直接判 FAIL，而不是悄悄重定义对比基线；版本破坏记为门禁失败（1）而非输入错误（2）。**前置**：需要一份 L1 baseline 报告（`CODERAG_L1_BASELINE`，默认 `eval/runs/l1-baseline.json`）；L2 报告可选，缺则跳过并提示。⚠️ **`eval/runs/` 已被 `.gitignore` 忽略**，baseline 因此不入库 → 新克隆上脚本以 2 退出并打印生成命令；**待定项**：是否把 L1 baseline 提交到 `eval/baselines/`，否则 CI 里的 L1 门禁无法生效 |
| **T4-01** | 已完成 | `$ node -e "console.log(require('./package.json').dsh.bundle)"`<br>`{ patch: './cordis.patch.yml' }`<br>`$ node -e "const p=require('./package.json'); console.log('main:',p.main,'\| bin:',p.bin,'\| scripts:',p.scripts)"`<br>`main: undefined \| bin: undefined \| scripts: undefined`<br>`$ npm pack --dry-run`<br>`npm notice 1.1kB LICENSE`<br>`npm notice 14.8kB README.md`<br>`npm notice 1.5kB cordis.patch.yml`<br>`npm notice 270B package.json`<br>`npm notice total files: 4`（`package size: 9.5 kB`） | `340cf5f` | 新增仓库根 `package.json`：`name`/`version`/`description`/`license` + `files: ["cordis.patch.yml"]` + `dsh.bundle.patch: "./cordis.patch.yml"`，**无任何 JS 入口**（`main`/`bin`/`scripts` 全为 `undefined`）。DSH 的解析方式已在 `dsh-app-boot` 源码核实：`patchPath = join(packageDir, declared)`（相对包目录解析）。tarball 只含 4 个文件 / 9.5 kB，`cordis.patch.yml` 是唯一的分发内容 → bundle 里没有构建脚本，**C11（pnpm 拒绝 install script）从根上不适用**，正是 §1.6.1 的设计意图。**下一任务 `T4-02` 才真正验证 `dsh plugin add .` 能装载这一层**（本任务只做清单） |
| **T4-02** | 已完成 | `$ ./scripts/dsh plugin --profile coderag-dev add .`（E-07：经包装脚本；沙箱先拒绝写 `~/.dsh`，按沙箱规则提权一次）<br>`dsh: initialized profile coderag-dev at /Users/vermi/.dsh/profiles/coderag-dev`<br>`Already up to date`<br>`dependencies:`<br>`+ dsh-coderag link:../../../个人项目/python/dsh-coderag`<br>`Done in 1.7s using pnpm v12.4.2`（rc=0，**无 install script 报错**，无 `ERR_PNPM_*`）<br>`$ ./scripts/dsh --profile coderag-dev --dump-config`<br>`# == @deepseek-ai/dsh-base`<br>`…（# == @deepseek-ai/dsh-base 层：84 条 / 332 行）…`<br>`# == dsh-coderag`<br>`- id: mcp-coderag`<br>`  name: '@deepseek-ai/dsh-mcp-client'`<br>`  config:`<br>`    serverName: coderag`<br>`    transport: stdio`<br>`    command: !!js process.env.CODERAG_PYTHON ?? '/opt/anaconda3/envs/forBSH/bin/python'`<br>`    args:`<br>`      - '-c'`<br>`      - import dsh_coderag.server as s; s.run()`<br>`    env:`<br>`      CODERAG_ROOT: !!js process.env.CODERAG_ROOT ?? process.cwd()`<br>（rc=0；stdout `10843` 字节 / stderr `0` 字节，即无 patch 应用警告。期望两项逐项对应：本插件的层 = `# == dsh-coderag`（第 333 行，层标签取**包名**）；MCP 行 = `- id: mcp-coderag`（第 334 行）。登记后 profile 清单 `dsh.profile.bundles` 由 `["@deepseek-ai/dsh-base"]` 变为 `["@deepseek-ai/dsh-base", "dsh-coderag"]`） | `269ac19` | 新增 `docs/m4-bundle.md`（分发形态、DSH 源码核实的解析/登记行为、验收实录、8 项自检清单、复现步骤与已知边界）。**`cordis.patch.yml` 无需改动**——T1-14 已把同一文件写成 dev overlay 兼 bundle patch；本任务确认为"已就绪"。tarball 只含 4 文件且无 `scripts`，**C11/E-05 从根上不适用**。**范围外发现**（未顺手改，AGENTS §9）：`README.md` 第 44–48 行仍写"本地 `dsh plugin add .` 属 T4-02、尚未验证"，本任务完成后该句过期，留给 `T4-06`/`T4-08` 一并更新 |
| **T4-03** | 已完成 | `$ CODERAG_PYTHON=/opt/anaconda3/envs/forBSH/bin/python bash scripts/install.sh`（第 1 次）<br>`conda  ：当前 shell 激活的是 base → /opt/anaconda3`<br>`解释器 ：/opt/anaconda3/envs/forBSH/bin/python（来源：CODERAG_PYTHON）`<br>`版本   ：3.10.21  ✅`<br>`FTS5   ：可用 ✅（预检）`<br>`安装   ：检测到本仓库已 editable 装在此解释器上，保持 editable（改 src/ 立即生效）`<br>`安装   ："...python" -m pip install -e .`<br>`Successfully installed dsh-coderag-0.1.0`<br>`FTS5   ：可用 ✅`<br>`bigram ：幂等 ✅  '用户令牌' -> '用户 户令 令牌'`<br>`往返   ：中文查询命中 ✅  标识符命中 ✅  无关词不命中 ✅`<br>`包版本 ：dsh_coderag 0.1.0`<br>`完成：安装与自检通过 ✅`（rc=0）<br>**第 2 次（幂等）**：同样 rc=0；脚本自身输出与第 1 次逐字相同——两次完整输出的 diff 只差 pip 自己的临时 wheel 缓存目录与 sha256（那是 pip 的输出，不是脚本的）<br>`$ CODERAG_PYTHON=/nonexistent/python bash scripts/install.sh`<br>`错误：解释器不可执行或不存在：/nonexistent/python（来源：CODERAG_PYTHON）`（rc=2）<br>`$ python -m pytest tests/test_install_script.py`<br>`5 passed in 0.58s` | `55702df` | 新增 `scripts/install.sh`（**产出文件只列了它**；`tests/test_install_script.py` 5 例是按 DoD §5.1 第 5 条补的）。流程：① 选解释器 `CODERAG_PYTHON` → 当前激活的 conda 环境 → PATH 上的 python3/python，并单独报告 conda 状态；② 版本门禁 `>=3.10,<3.13`（对应风险 R8），不符时打印实际版本与 `conda create` 指引；③ **FTS5 预检放在 pip 之前**（只用 stdlib：缺 FTS5 就没必要装，早失败）；④ `pip install`，`CODERAG_PIP_ARGS` 支持受限网络镜像，PEP 668 给 conda/venv 指引；⑤ 自检做**真实 FTS5 往返**（`unicode61` + bigram，含"无关词不命中"阴性对照与 `to_bigrams` 幂等），再打印下一步。**关键设计——editable 保护**：本机 forBSH 是 `pip install -e .`，而普通 `pip install .` 会把开发安装冻结成 site-packages 副本、之后改 `src/` 不生效，**后续任务会在不知情下测到旧代码**；故检测到"本仓库已 editable 装在该解释器上"时保持 editable，可用 `CODERAG_EDITABLE=0/1` 强制。退出码 0/1/2（pip 失败 1、环境不可用 2）与 `scripts/eval-gate.sh` 一致。测试用 `CODERAG_SKIP_INSTALL=1` 做到**离线**（`TESTING.md` T-02），并断言两次运行 stdout 逐字相同以锁住"幂等"这一验收项 |
| **T4-04** | 已完成 | 人工审阅（`README.md`，`D-04` 要求安全声明在第一个屏幕内）<br>`$ sed -n '1,8p' README.md \| grep -n "机器权限"`<br>`5:> **安装本插件等于授予它与本机账号同等的机器权限。**`<br>（第 5 行，位于文档顶部引用块；同块还写明三档权限**不约束插件**（`E-04`）与"只在你信任的仓库与本机安装"） | `d483e64` | 新建 `README.md`；顶部安全声明对应约束 `C12`/`E-04`。**此前未列入 §6.7 是历史遗漏**，本行按用户指示补记，README 内容未改 |
| **T4-05** | 已完成 | 人工审阅（`README.md` 含能力说明 / 安装 / 配置 / 限制 / 评测数据 / 已知问题，`D-03`）<br>`$ grep -c '^## ' README.md`<br>`13`（装上去能带来什么、当前状态、它是怎么工作的、安装、配置、工具、CLI、实测评测数据、已知限制、安全与隐私、开发、文档、许可）<br>`$ grep -E '^[\|] \*\*S[1-4]\*\*' README.md`<br>`\| **S1** \| 检索本身有效：Success@5 \| ≥ 0.80 \| **0.433**（30 条，95% CI [0.274, 0.608]） \| ❌ \|`<br>`\| **S2** \| 排序质量：MRR \| ≥ 0.60 \| **0.313** \| ❌ \|`<br>`\| **S3** \| 端到端有提升（有检索 vs 无检索） \| ≥ +10pp \| **+59.0pp**（0.308 → 0.897） \| ✅ \|`<br>`\| **S4** \| 成本：单次返回 token 中位数 \| ≤ 4000 \| **2492** \| ✅ \|`<br>（S1–S4 全部为实测数字；另有分层指标表、L2 A/B 表与失败归因） | `d5c6f84`, `ca51c5f` | 补全 README 全部章节；此后 `a33c44e` 对齐了 4 处过期陈述。**此前未列入 §6.7 是历史遗漏**，本行按用户指示补记。**后续 `ca51c5f`**（用户指示）：在**靠前位置**新增「装上去能带来什么（冒烟测试实测）」章节——数据取自已入库的冒烟运行 `eval/runs/a-smoke` / `b-smoke` / `gate-smoke.md`（13 条 × 1 次：A 4/13 = 0.308 → B 10/13 = 0.769，**+46.2pp、0 回归**；`locate` 0/4→3/4、`crossfile` 0/5→3/5、`regression`/`negative` 保持 2/2 不变差），并如实标注"冒烟级小样本、不回答排序准不准"、指向完整 3-trial L2 与 L1；同时改掉 `T4-02` 造成过期的陈述（M4 状态行、`cordis.patch.yml` 的"将来的分发 patch"、安装注意块、"尚未打包"限制）并补全文档表（新增 `ADR-15` 与 `docs/m4-bundle.md`）。**证据命令改为与行号无关**：用 `grep -E '^[|] \*\*S[1-4]\*\*'` 而不是 `sed -n 'A,Bp'`——每次在 README 前面插内容都会让硬编码行号失效并打印出错误的行 |
| **T4-06** | 已完成 | 人工审阅（README 新增 `### 安装故障排查`：pnpm 10+ 的 `allowBuilds` 报错原文、登记失败的自查方法、以及 pnpm 缺失 / 解释器路径 / PEP 668 / 缺 FTS5 几类现象与对策）<br>**干净 profile 实测**（全新 `DSH_HOME`，profile `clean-test` 此前不存在）：<br>`$ rm -rf /tmp/dsh-coderag-t4-06 && DSH_HOME=/tmp/dsh-coderag-t4-06 ./scripts/dsh plugin --profile clean-test add .`<br>`dsh: initialized profile clean-test at /tmp/dsh-coderag-t4-06/profiles/clean-test`<br>`Already up to date`<br>`dependencies:`<br>`+ dsh-coderag link:../../../../../Users/vermi/个人项目/python/dsh-coderag`<br>`Done in 5.3s using pnpm v12.4.2`（**rc=0**）<br>`$ … add . 2>&1 \| grep -iE "ERR_PNPM\|allowBuilds\|build script\|prepare"`<br>（**无匹配**，grep 退出码 1——四类关键字一个都没出现）<br>干净 profile 的 `pnpm-workspace.yaml` 只有 `packages:` / `nodeLinker: hoisted` / `autoInstallPeers: false`——**没有 `allowBuilds`**<br>`$ DSH_HOME=/tmp/dsh-coderag-t4-06 ./scripts/dsh --profile clean-test --dump-config \| grep -n -A6 '^# == dsh-coderag'`<br>`333:# == dsh-coderag`<br>`334:- id: mcp-coderag`<br>`335-  name: '@deepseek-ai/dsh-mcp-client'`<br>（rc=0，stderr 0 字节） | `59e77e7` | 新增 `docs/m4-install-verification.md`（方法、实际输出、坑本身、尚未验证部分；T4-08 会往同一文件追加端到端）。README 的新小节用 `###` 而非 `##`，以免改动 `grep -c '^## '` 这个 T4-05 证据。**核心结论**：干净 profile 首次 `add` **完全不需要 `allowBuilds`**——本 bundle 的 `package.json` 连 `scripts` 段都没有（`T4-01`），pnpm 没有可拒绝的东西，**C11/E-05 从根上不适用**；坑的文本仍写进 README，因为**别的**带 `prepare` 的 git 插件会踩它，而 `dsh plugin add` 在 pnpm 非零退出时**静默跳过 bundle 登记**，用户会误以为装了却没加载，所以文档给了 `--dump-config` 这条自查。**范围修正**：README 里"安装脚本（`T4-03`）还没做"与"无 `scripts/install.sh`"两处在 T4-03 落地后已过期，本任务一并改掉并指向 `bash scripts/install.sh` |
| **T4-07** | 已完成 | `$ test -f LICENSE && test -f CHANGELOG.md && echo "两份文件都在"`<br>`两份文件都在`<br>`$ head -3 LICENSE`<br>`MIT License`<br>`（空行）`<br>`Copyright (c) 2026 Vermilion Pasvikin`<br>`$ grep -cE "Permission is hereby granted, free of charge\|The above copyright notice and this permission notice\|THE SOFTWARE IS PROVIDED" LICENSE`<br>`3`（MIT 三个必备条款都在）<br>`$ grep -cE "YEAR\|<name>\|placeholder\|TODO" LICENSE`<br>`0`（无占位符） | `101a51a` | `LICENSE` **在初始提交 `9ed8bcd` 时就是 MIT 全文**（年份 2026、版权人 `Vermilion Pasvikin`），本任务核实后**无需改动**——与 `T4-02` 的 `cordis.patch.yml` 同类情况。新增 `CHANGELOG.md`（Keep a Changelog 格式，`[0.1.0] - 2026-09-23`）：按「新增 / 安全」列出 4 个 MCP 工具、FTS5 + bigram 索引、三层安全过滤、声明感知分块、增量索引与自适应并发、顺序保持检索、bundle 与安装脚本、L1 + L2 评测；并写明**尚未发布到 PyPI/npm**、**不含向量**（指向 `ADR-15`）。**范围修正**（README 由本任务造成的过期陈述）：M4 状态行改为"只差 `T4-08`"；「已知限制」里"无 `CHANGELOG.md`"删掉；文档表补 `CHANGELOG.md` 一行 |
| **T4-08** | 已完成 | **M4 出口判据**。全新 `DSH_HOME=/tmp/dsh-coderag-t4-08` + 全新 profile `clean-test`（此前不存在）：<br>`$ DSH_HOME=/tmp/dsh-coderag-t4-08 ./scripts/dsh plugin --profile clean-test add .`<br>`dsh: initialized profile clean-test at /tmp/dsh-coderag-t4-08/profiles/clean-test`<br>`+ dsh-coderag link:../../../../../Users/vermi/个人项目/python/dsh-coderag`<br>`Done in 31ms using pnpm v12.4.2`（rc=0）<br>零状态工作区：`rsync --exclude .coderag examples/demo-workspace/ /tmp/dsh-coderag-t4-08-ws/`（**无任何索引**）<br>用 `--dump-config` 里那一行**原样**启动子进程（`/opt/anaconda3/envs/forBSH/bin/python -c 'import dsh_coderag.server as s; s.run()'`，工作区走 `config.env` 的 `CODERAG_ROOT`），在 stdin/stdout 上说换行分隔 JSON-RPC：<br>`<<< serverInfo {"name":"coderag","version":"0.1.0"}`<br>`--- tools --- ['code_search', 'code_outline', 'code_index', 'index_status']`<br>`code_index -> {"taskId": "idx-20260923-5fc3", "state": "pending"}`<br>`index_status -> running -> {"state": "ready", "total_files": 3, "total_chunks": 7}`<br>`code_search("用户令牌在哪里校验") ->`<br>`status: ready`<br>`hits: 1 (sorted by source order)`<br>`── src/auth/token.py:1-6  [module]  (chunk 0)`<br>（4 次 `tools/call` 的 `isError` 全为 `false`；子进程退出码 `0`；stderr 仅 2 行 JSON-Lines 日志，stdout 每一行都是合法 JSON-RPC） | `ab94dcf` | 把 `docs/m4-install-verification.md` 第 5 节写成 T4-08 的端到端记录（方法 / 原始报文 / stderr 日志 / **这次不覆盖什么**）。**驱动不经过模型**：用 stdlib 直接说 JSON-RPC，所以它证明的是"装完之后工具真的可用、返回结构化结果"，**不**证明"模型会用得好"（后者是 L2 A/B）。**命中是易例**：`用户令牌在哪里校验` 与 demo 工作区 `token.py` 的 docstring 有 bigram 重叠，属"有词法线索"；**纯中文自然语言在大仓库上仍是 `S@5 = 0.000`**（L1 `natural` 桶），文档明确写了这条限制不因本任务改变。探针脚本事后**不留在仓库**（本任务产出文件只列文档），启动方式与协议报文都记进文档以便复现。**范围修正**（README 由本任务造成的过期陈述）：M4 状态行改为"出口判据已通过，剩 `T4-09`/`T4-10`"；安装注意块与「已知限制」不再说"干净 profile 未验证"，只保留"registry 安装未验证"；文档表描述同步 |
| **T4-09** | 已完成 | 验收命令是「浏览器确认 / topic 已加」。**用 GitHub API 核实**（topic 发现页会滞后，仓库的 topic 列表才是这个任务的确切目标）：<br>`$ curl -s https://api.github.com/repos/VermilionPasvikin/dsh-coderag/topics`<br>`{"names":["dsh-plugins","mcp","python","rag","vibe-coding","dsh-plugin"]}`<br>`$ curl -s https://api.github.com/repos/VermilionPasvikin/dsh-coderag`<br>`"topics":["dsh-plugin","dsh-plugins","mcp","python","rag","vibe-coding"]`（两个端点一致）<br>DSH 官方 README 第 46 行要求的正是**单数** `dsh-plugin`：<br>`- Add the [dsh-plugin](https://github.com/topics/dsh-plugin) topic to your plugin repository for discoverability.` | —（本任务无仓库改动，仅 GitHub 仓库设置） | **由用户执行**（Agent 无仓库写权限）。**第一次加的是 `dsh-plugins`（复数），不满足官方要求**——我用 API 核实后报告，用户随即补上单数形式，本行证据是**补好之后**重新验的两次 API 返回。`README.md` 除 M4 状态行外无需改动（M4 状态行已由"剩 `T4-09`/`T4-10`"改为**已完成**） |
| **T4-10** | 已完成 | 验收命令是「人工对照代码审阅 / 无过时描述」，审阅方法：抽出 `AGENTS.md` 里**所有可核对的声明**（章节引用、文件路径、工具可用性、分支、scope 列表），逐条对**已安装的 DSH 包**与**本仓库代码**核对，并用 AST 统计编码规范的实际符合度。<br>实际测量：<br>`C-09 缺 future import 的模块: 无`<br>`C-03 裸 except: 无`<br>`C-04 超过 50 行的函数: 12`（最长 `indexer.index_sync` 99 行）<br>`C-02 的 pydocstyle: No module named pydocstyle`<br>`C-07 Windows 风格路径测试: 无命中`<br>`git branch -a → 只有 main`<br>`AGENTS 的 §引用全部存在（§1.3/§2.3/§2.4/§3.4–3.7/§4.3.1/§5.3.1/§6.7…）`<br>新增 `docs/architecture.md`（222 行）；修正 AGENTS 5 处 | `6c7335b` | 新增 **`docs/architecture.md`**：运行时形态（DSH 如何拉起、为什么用 `-c`）、模块表与**用真实 import 图核对过的**依赖方向、索引/检索数据流、5 张表的数据模型、工具契约、安全模型、异步与上限、可观测性、评测分层、非目标。**AGENTS.md 修正 5 处**：① C-02 的检查方式（`pydocstyle` **未安装**、`ruff` 的 `D` 规则也未开 → 改为"只靠人看"）；② C-04 标注**当前未达标**（12 个函数 > 50 行，规则不放宽）；③ C-07 标注**当前未达标**（6 处 `as_posix()` 合规，但零 Windows 路径测试）；④ §7.1 的 scope 列表补齐（原表漏了 `types`/`parser`/`text`/`sanitize`/`sqlite_caps`/`log`，以及实际在用的 `bundle`/`install`/`adr`/`repo`/`readme`/`project`/`testing`/`cases`）；⑤ §7.3 分支改为实情（**只有 `main`**，M1–M4 都没开里程碑分支）。另新增两条 backlog 欠账（C-04 / C-07），修掉 `PROJECT.md` §3.4 里"`eval` **当前未创建**"与"`render` 被 M3 的 eval 调用"两处过期陈述，并把 eval 的依赖改成实测值（`runner`→searcher；`attribute`→indexer/walker/text）。**核实教训**：核查 DSH 侧引用必须读**已安装的包**——E-04 引的 `tool-cordis/README.md` 第 182 行在安装版里属实，但本机 `~/projects/dsh` 参考副本较旧（只有 76 行），一度被我误判为错误引用；已把这条写进 E-04 的依据格 |
| **T5-01** | 已完成 | `$ grep -c -e tests/test_retrieval_quality.py -e indexed_workspace -e "limit 默认是" EVAL.md`<br>`0`（三项旧表述全部 0 命中）<br>`$ grep -n dsh-eval-harness EVAL.md`<br>10 处命中（`:378` `:383` `:394` `:396` `:415` `:475` `:500` `:587` `:639` `:644`），**全部是"未采用/不兼容"结论或调研记录**，无一处再把它作为 L2 的工具选择：`:378` 选型表结论列 `已否决——T3-00 实测与本机 DSH 不兼容`；`:383` `当时看中…的理由（记录用，日后若要重估可从这里接手）`；`:394`/`:396`/`:415` §3.2 标题与 `T3-00` 实测结论；`:475` `已被 T3-00 判定不兼容并否决`；`:500` §3.6 状态；`:587` §5.1 `未采用…L2 用自建 scripts/ab_eval.py`；`:639`/`:644` §6 修订记录（后者标 `已撤销`）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.10s` | `5635909`（`EVAL.md`）, `a2fb5d8`（backlog 欠账记录） | 纯文档改动（`EVAL.md` + 一条 backlog 记录），无代码变更。**审计清单逐条落地**：① L2 工具列与第 3 章标题不再写"现成 `dsh-eval-harness`"；② `T3-00` 不再写作"新增前置任务"，改为实测结论（可装载但 trace 采集器只认 `session.jsonl(.zstd)`，本机落盘 `session.v3.jsonl.zstd` → 判定不兼容）；③ 三处 `tests/test_retrieval_quality.py` 与 `indexed_workspace` fixture 换成真实落点（`tests/test_eval.py` 等 + `eval_corpus` fixture / `CODERAG_EVAL_CORPUS` opt-in）；④ `eval validate` 补 `--tasks`/`--root`；⑤ `limit` 默认值 12 → **5**；⑥ "L2 只在 M3 决策门跑一次"改为实情（已跑 `a-v1`/`b-v1`/`b-r5`/`a-smoke`/`b-smoke` 多轮）；⑦ "3~4 小时" → **4–5h**（与 §2.1/§2.4 一致）；⑧ §5.1 与 §7 速查的 `eval_run`/`eval_gate` 换成 `scripts/ab_eval.py`，§3.5 的示例代码改为**可实际执行**的命令。**另外三处同类的文档错误一并修正并记录在此**：§2.4 完整流程的 Step 2/Step 3 条数写 `10 exact`/`9 crossfile`（合计 26），与 §2.3 的 12/11 及 `eval/tasks.jsonl` 实际 30 条矛盾，改为 **12/11**；§6 修订记录里"`T3-05`/`T3-06` 改用 `dsh-eval-harness`"标为**已撤销**；§8「未能核实的事项」删掉已被 `T3-00` 实测回答的 `dsh-eval-harness` 兼容性一条。**顺带发现一个越界缺陷**（已按 `AGENTS.md` §9 记入 `docs/backlog.md`，未顺手修）：`tests/test_eval.py::test_a_batch_runs_against_indexed_corpus` 仍断言 `len(tasks) == 10`，而 golden 集已是 30 条；该用例由 `CODERAG_EVAL_CORPUS` opt-in，默认套件与 `eval-gate.sh` 都不设它，故不影响门禁，但设了就会假红（实测 `AssertionError: assert 30 == 10`）。`EVAL.md` §4.1 已在引用处标注这条欠账 |
| **T5-02** | 已完成 | `$ grep -c -e test_retrieval_quality -e "tests/e2e/" -e indexed_eval_corpus TESTING.md`<br>`0`（三项旧表述全部 0 命中；无命中时 `grep -c` 退出码为 1，属预期）<br>`$ grep -n "多平台矩阵" TESTING.md`<br>`763:**跑多平台矩阵**（3 OS × 2 Python）…**这一条推翻了本文件 1.0 版的"第一版只跑 macOS"建议**`<br>`803:**⚠️ 为什么多平台矩阵是必要的（推翻了本文件早先"第一版只跑 macOS"的建议）**`<br>`873:多平台矩阵：按 §5.1 跑（3 OS × 2 Python）——本文件 1.0 版"第一版只跑 macOS"的建议已被推翻`<br>（三处口径一致，都指向"跑"；原先 §7 速查里那句 `不做多平台矩阵` 已删——它正是唯一与本结论冲突的一处）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.59s` | `1aafdb5`（`TESTING.md`） | 纯文档改动（`TESTING.md`），无代码变更。**审计清单逐条落地**：① 目录树里的 `test_retrieval_quality.py`（从未创建）与 `tests/e2e/…`（目录不存在）删掉，换成真实落点，并给整棵树加"**代表性命中，不是完整清单**"的口径 + 当前真实数量（**44** 个 `test_*.py`）；② 属性测试落点改正——Hypothesis **只在** `tests/test_chunker_decl.py`（M6 的两条不变式 `test_chunker_never_loses_content`/`test_chunker_never_overlaps`），`test_too_many_files.py` 的 M8 是**手写例子**、不含 hypothesis，`test_properties.py` 不存在；③ 中文用例主落点补上 `test_cjk_recall.py`（`T3-13`），并写明 `cjk_corpus` 是建在该文件里的 `tmp_path` fixture、`tests/fixtures/cjk/` 不存在；④ 不存在的 `indexed_eval_corpus` fixture 换成 `eval_corpus`（`tmp_path` 小语料）+ `CODERAG_EVAL_CORPUS` 的 opt-in 回放；⑤ §5.1 与 §7 的多平台矩阵口径统一为"跑（3 OS × 2 Python）"；⑥ `FTS5_UNAVAILABLE` 不再写"必须同步加进去"，改为"早已加进去并已实现"（`T1-03`/`T2-22` 两行）。**另外三处同类问题一并修正并记录在此**：§3.3 的"更严版本"指向不存在的 `tests/e2e/test_stdio_protocol.py`，改为真实落点 `tests/test_cwd_shadowing.py::test_launcher_serves_mcp_with_shadowing_modules_in_cwd`；§3.8 代码块里的 `tests/test_properties.py` 改为"设计稿"标注；§3.3 不再声称子进程级用例已断言"stdout 每一行合法 + stderr 是 JSON Lines"——**实测该用例只读第一条回答并断言 `serverInfo.name == "coderag"`**，完整覆盖现状（进程内 `tests/test_server.py::test_no_stdout_pollution_during_tool_call` + `tests/test_log.py::test_index_writes_json_lines_to_stderr`；子进程级的更强断言**尚未落地**）已如实写进文档。**核实教训**：本任务在提交前自查出三处自己刚写下的错误断言（`grep -c` 那次命中来自我新加的说明文字本身；`PROJECT.md` §5.6 错误码表里 `FTS5_UNAVAILABLE` 的位置我先写成"第 6 个"、实为**第 2 个**；子进程级用例的断言范围被高估），三处都是**跑命令核对**才发现的——**文档里的每个"事实"都必须逐条跑命令验证，不能凭印象写** |
| **T5-03** | 已完成 | `$ grep -c "后续更新" docs/adr/ADR-14-semantic-retrieval.md`<br>`3`（三处各一条，全部带日期 `2026-09-23`）<br>`$ grep -n "后续更新" docs/adr/ADR-14-semantic-retrieval.md`<br>`139:` §7.1 → `S3 **已测量**（2026-09-20 的复核，数据见 §10.1）：…A 组 12/39 = **0.308** → B 组 22/39 = **0.564**，**+25.6pp**，门禁 0 回归 / 6 条改善`<br>`158:` §8 表 → `表中 T3-12 **已完成**（7ff58c6，产物 scripts/eval-gate.sh）…S1 0.433 / S2 0.313 / S4 2492 / S3 +25.6pp，回归条数 L1 0 + L2 0 = 0，门禁 PASS 退出码 0；注入一条回归后退出码 1`<br>`162:` §8 未决前置 → `该前置**已完成**——自建薄 runner 由 T3-15 落地（src/dsh_coderag/eval/ab.py + scripts/ab_eval.py，adbcdbb），T3-05/T3-06 已在它上面跑完（报告入库于 2a2e8d8）`<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.33s` | `05d81b8`（`docs/adr/ADR-14-semantic-retrieval.md`） | 纯文档改动（`docs/adr/ADR-14-semantic-retrieval.md`）。**只加"后续更新"块，原句一字未改**（`git diff` 只有 3 处新增、0 删除行）——`ADR` 是**决策时快照**、不是现状描述（`D-06` 的边界），所以历史结论保持原样、由日期化现状块并置说明。三处的依据都指向**已有产物**而非转述：`7ff58c6`（`T3-12`）、`adbcdbb`（`T3-15` 自建 runner）、`2a2e8d8`（`T3-05` 报告入库），数字取自 §10.1 与 `PROJECT.md` §6.7 的对应行。**边界说明**：§7 只声明"限制 1 已过期、限制 2–6 仍有效"，没有动 §1 的裁决；§8 只声明那两个前置已完成，**没有**改 `T3-08`–`T3-11` 的执行状态——那属 `T5-12` 的范围 |
| **T5-04** | 已完成 | `$ grep -c "后续状态" docs/m4-bundle.md docs/m1-findings.md docs/m2-findings.md`<br>`docs/m4-bundle.md:1`<br>`docs/m1-findings.md:1`<br>`docs/m2-findings.md:1`（每份恰好 1 条**汇总**标注，不逐行改写）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.34s` | `c22cd34`（3 份里程碑快照） | 纯文档改动（3 份里程碑快照）。**只新增汇总块，原句一字未改**——三份都是**当时观测的存档**，按 `D-06` 的边界不改写历史。① `docs/m4-bundle.md`：§1 表里"干净 profile 端到端 ⏳ 属 `T4-08`"**已完成**（全新 `DSH_HOME`+全新 profile `clean-test`，原样 argv 起子进程走完 `initialize`/`tools/list`/`tools/call`，4 次调用 `isError` 全 `false`、退出码 0、stdout 每行合法 JSON-RPC，`ab94dcf`），并声明该注同样覆盖 §5「已知边界」里同源的两条；**"从 registry 安装 ⏳ 未发布"明确保留**（本项目迄今未发布到 PyPI/npm）。② `docs/m1-findings.md`：`path`/`max_tokens` **已生效**（`tests/test_path_filter.py` / `tests/test_token_budget.py`），召回模式/查询改写/标点路由**已落地**（`T2-19`=`5f02646`、`T3-13`=`e7d7624`）。③ `docs/m2-findings.md`：观察 3 的结论与"已知限制"里同一条**已落地**，并**明确保留根因**——纯中文原问句在大仓库上 `natural` 桶 `S@5` 仍是 **0.000**，那是 M5 的目标。**三份都同时写明"其余限制仍然有效"**，避免日期化标注被读成"整份文件已过期" |
| **T5-05** | 已完成 | `$ test -f docs/adr/ADR-16-optional-vector-backend.md`<br>（退出码 0，文件存在）<br>`$ grep -c "^## " docs/adr/ADR-16-optional-vector-backend.md`<br>`10`（决策 / 形态 / 后端与依赖 / 配置与环境变量命名 / 向量索引落点 / 失败模式与结构化状态 / 发布范围与验收判据 / 数据与安全 / 诚实的限制 / 与其它决策的关系；要求 ≥6）<br>`$ python3 scripts/verify-plan.py .`<br>`✅ [B1] ADR: 16 条全部在矩阵里`<br>`✅ [F4] 矩阵 48 行 ≥ 下限 45`（原 47 行 + `ADR-16` 一行）<br>`✅ [B4] 48 个矩阵键全部对应真实定义`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.34s` | `608f08c`（`ADR-16` + §3.7/§6.8 行 + 命名表） | 新增 `docs/adr/ADR-16-optional-vector-backend.md`，并**同一次提交**更新 `PROJECT.md` 的 §3.7 ADR 表行与 §6.8 覆盖矩阵行（`verify-plan` 的 `B1` 强制），另补了文首命名表的环境变量行。**冻结的条文**（逐条对应 `ADR-15` §3 的重启条件）：① 形态=默认关闭 + opt-in + **关闭态输出与 1.0.0 逐字节一致**（否则 M9 快照全红、`S6` 无从判定）；② 后端=**本地 Ollama + `bge-m3`**，云端 embedding 因 `S-01`/`S-02` 否决；③ 依赖=extra **`semantic`，内容只有 `numpy`**，HTTP 走 stdlib `urllib`（不引入 httpx）、不引入向量库，`CODERAG_WITH_SEMANTIC` 未设则 `install.sh` 不装；④ 配置命名冻结 `CODERAG_SEMANTIC`（只有 `on` 启用）/`_BACKEND`/`_URL`（**必须 loopback**）/`_MODEL`/`_TIMEOUT`/`_BATCH`/`_MAX_CHUNKS`，全部可覆盖（`RL-07`）；⑤ 索引落点 `<root>/.coderag/vectors/`（`S-03`/`S-04`），且只有已入库 chunk 会被 embedding（`RL-03` 延伸）；⑥ 失败冻结 7 个 `SEMANTIC_*` code，一律**回退 BM25**、不 `isError`、不空列表、重试上限 2（`RL-06`/`RL-08`/`RL-09`）；⑦ 发布=2.0.0，服从 `ADR-14` §10.4 的 V1–V4（V3 **α = 0.025**，V4 C 不显著优于 B 就不发布），**探针 `T5-14` 先行、由数据给 go/no-go**。**两处刻意的边界**：`T5-05` **不改** `PROJECT.md` §5.6 错误码表与 `types.py`（`tests/test_types.py` 逐项断言 10 个码）——`SEMANTIC_*` 由实现任务（`T3-08`–`T3-11`）登记，ADR-16 §6/§9 已写明这是契约先行；`S5`/`S6` 两条成功标准留给 `T5-07` 登记进 §1.4（ADR-16 §7.1 已标注归属）。**命名与任务表既有验收命令对齐**：`T3-11` 用 `CODERAG_SEMANTIC=on`、`T5-15` 用 `grep -c CODERAG_WITH_SEMANTIC`，ADR-16 冻的正是这两个名字，未引入第三套命名 |
| **T5-06** | 已完成 | `$ grep -n -e "禁止在 M3 决策门" -e "向量数据库（M3 决策前）" AGENTS.md`<br>（**无匹配**，grep 退出码 1——两句旧表述都 0 命中）<br>`$ grep -c "默认路径或必需依赖" AGENTS.md`<br>`1`（RL-10 新表述）<br>`$ grep -c "干净回退 BM25" AGENTS.md`<br>`1`（RL-10 新表述）<br>`$ grep -c "本地后端" AGENTS.md`<br>`1`（S-01 新增的"本地后端也不得默认启用"）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.53s` | `ff9eb78`（`AGENTS.md` + §6.8 `RL-10` 行） | 纯文档改动（`AGENTS.md` + `PROJECT.md` 的 §6.8 `RL-10` 行）。**RL-10 改写为发布范围约束**："向量不得进入默认路径或必需依赖；未配置时必须干净回退 BM25"，并逐项点名 `dependencies` / tarball / `install.sh` 默认路径 / README 安装前置四处；**旧表述的历史保留在同格的理由里**（"旧 RL-10 的使命已完成——`T3-07` 已裁定，`ADR-15` §4 明确它不因暂缓而恢复"），并把"新红线保护的对象换了"写明：从"别过早引入"变成"**别把可选做成必需**"。**§3.2** 的"不引入向量数据库（M3 决策前）"改为"不引入向量**数据库**"——理由换成 `ADR-14` 的"≤10 万 chunk 用 `numpy` 暴力余弦即可"，做法列"默认路径 SQLite FTS5；可选向量后端用 `numpy`（`ADR-16` §3.1）"。**S-01** 补上"**本地后端（如 Ollama）同样不得默认启用**"，并把 `CODERAG_SEMANTIC` 未设即关闭、`_URL` 只允许 loopback 两条可验收细节写进去。**§8 反模式清单**里"过早引入重依赖"的正确做法同步补上"向量只做可选 extra 且默认关闭"（原先只引 RL-10，而 RL-10 已不再讲"过早"）。**§6.8 矩阵行**同步：强制点由 `T3-07`（旧红线的落点）改为 **`T3-10, T5-15, T5-16`**——分别强制"未配置时逐条回退纯 BM25"、"默认安装零向量依赖"、"默认安装的解释器里没有 numpy"，这三个正是新 RL-10 的可验收形式 |
| **T5-07** | 已完成 | `$ python3 scripts/verify-plan.py .`<br>`  ✅ [B1] 成功标准 S*: 6 条全部在矩阵里`<br>`  ✅ [F4] 矩阵 50 行 ≥ 下限 45`（原 48 行 + `S5`/`S6` 两行）<br>`  ✅ [B4] 50 个矩阵键全部对应真实定义`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.92s` | `1b78f72`（§1.4 + §6.8 的 `S5`/`S6` 行） | 纯文档改动（`PROJECT.md`）。**`S1`–`S4` 一行未改**（稳定标识不得改名），新增两条：`S5` = 开启后端后 **`natural` 桶 `Success@5` ≥ 0.40**（沿用 `EVAL.md` §2.7 已有的 natural 桶阈值，不新造数字；7 条里至少命中 3 条，0.40 对 7 条是可判定的），`S6` = 未配置时 30 条逐条与 `1.0.0` 一致、**回归条数 = 0** 且 `exact` 桶保持 **1.000**（由 `T3-12` 门禁给出）。**两条的适用范围写清了**（这是本任务最容易写错的地方）：`S5` **只约束已发布的向量路径**——探针 no-go、或 `T3-11` 按 V4 判定「C 不显著优于 B」而不发布时，`S5` 不参与判定；`S6` 则**无条件适用**，是 2.0.0 的硬门禁。同时把 §1.4 的两处措辞对齐到六条：导语由「下面这四条同时成立」改为「下面这些标准同时成立（`S1`–`S4` 是 v1.0 判据；`S5`/`S6` 是 v2.0.0 追加）」，稳定标识说明补上 `S5`/`S6`（首次编辑时误留了一条重复的稳定标识说明，已删）。`§6.8` 的强制点分别指向 `T3-11, T5-15`（`S5`：C 组判定 + 打包出 extra）与 `T3-10, T5-16`（`S6`：干净回退 + 默认安装零向量依赖） |
| **T5-18** | 已完成 | `$ test -f docs/adr/ADR-17-optional-cloud-embedding.md`<br>（退出码 0，文件存在）<br>`$ grep -c "^## " docs/adr/ADR-17-optional-cloud-embedding.md`<br>`8`（决策 / 为什么冻结 OpenAI 兼容协议 / 形态 / 配置与环境变量命名 / **安全风险声明** / 失败模式与结构化状态 / 发布范围与验收判据 / 与其它决策的关系；要求 ≥6）<br>`$ python3 scripts/verify-plan.py .`<br>`  ✅ [B1] ADR: 17 条全部在矩阵里`<br>`  ✅ [F4] 任务数 91 ≥ 下限 50`（原 86 + `T5-18`–`T5-22` 五个）<br>`  ✅ [C-DEP] 91 个任务 / 107 条依赖边，引用全部有效`（原 100 条 + 新增 7 条）<br>`  ✅ [C-CYCLE] 依赖图无环`<br>`  ✅ [D3] 根 = T1-01；91/91 个任务可达根`<br>`  ✅ [C5] §6.6 与任务表逐行一致（91 行）`<br>`  ✅ [F4] 矩阵 51 行 ≥ 下限 45`（原 50 + `ADR-17` 行）<br>`  ✅ [B4] 51 个矩阵键全部对应真实定义`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ python3 scripts/test-verify-plan.py .`<br>`全部 19 个变异均被检出 ✅`（校验脚本自身的变异自测仍全绿——说明改了任务表之后检查器没有失效）<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.97s` | `8e3f320`（`ADR-17` + `ADR-16` 指针 + `AGENTS.md` + `PROJECT.md`） | 需求变更（用户指示，2026-09-23）：向量后端除本地 Ollama 外，还要**可选**支持线上模型 API，且风险声明必须写进配置处 / README / 一切配置与说明书性质的文件。**按项目自己的规则办**（`AGENTS.md` §9、`R-03`）：**不改写 ADR-16，另立 `ADR-17`** 记录"为什么推翻"——`ADR-16` 只加一条日期化指针，逐条声明**哪四处只对 `ollama` 继续有效**（§1.3 云端否决、§3.1 云端行、§6 `SEMANTIC_BACKEND_NOT_LOCAL`、§8.1 loopback 硬限制），其余条文（默认关闭/干净回退/extra/落点/RRF/V1–V4）**两条后端同等继承**，原文一字未改。**新冻结的形态**：`openai` 兼容 `/v1/embeddings`（一份实现覆盖多家，改 URL+model 即换供应商；继续用 stdlib `urllib`，**不引入任何厂商 SDK**）；**双重开关**（`CODERAG_SEMANTIC=on` **且** `CODERAG_SEMANTIC_ALLOW_REMOTE=1` 才允许非 loopback）——防止"改一个 URL 就把代码发出去"；key 只从环境读；新增失败码 `SEMANTIC_AUTH_MISSING` / `_AUTH_REJECTED` / `_RATE_LIMITED`；`S5`/`V1–V4` **按实际启用的后端独立满足**，不得互相背书。**约束改动四处 + 新增一条**：`S-01`（两条后端都不得默认启用 + 云端双重开关）、`S-02`（**唯一例外**：显式启用的云端后端，外发内容以清单为准，其余路径仍零外发）、`RL-02`（key 只从环境读，patch 里只许出现 `!!js` 表达式，日志/状态/异常也不得出现）、`RL-10`（覆盖两条后端，且云端也不需要额外 Python 依赖）、新增 **`D-08`**（风险声明必须随每一处配置出现，缺一处即文档缺陷，与 `D-04` 同级）。**`E-02` 补了一条已核实的实现事实**（读已安装的 `@deepseek-ai/dsh-mcp-client`：`{...scrubbedParentEnv(), ...extra}`，即**显式写进 `config.env` 的值在清洗之后合并、能存活**）——这既是 key 的投递路径，也解释了"为什么直接在 shell 里 export 不管用、而 patch 里放表达式是安全的"。**一处自查纠错**：我最初把 `D-08` 也加进了 §6.8 矩阵，`B4` 立刻报 `矩阵有 1 个键不对应真实定义：['D-08']`——因为校验器解析的是 §1.5 的 `D1`–`D5` 系列，而 `AGENTS.md` 用的是 `D-01`…`D-07` **点号系列**（本来就不进矩阵）。已在提交前撤掉该行，并把 `T5-18` 的期望结果改成只要求 `ADR-17` 行 |
| **T5-08** | 已完成 | `$ grep -c "v2.0" PROJECT.md`<br>`11`（要求 ≥3）<br>`$ grep -c "两段式安装" PROJECT.md`<br>`2`<br>`$ grep -n "^#### 1.6.4" PROJECT.md`<br>`203:#### 1.6.4 可选依赖：2.0.0 的 extra（**不进默认安装**）`<br>`$ grep -c "第二版怎么做成可选的" PROJECT.md`<br>`1`（§2.3 新增块的结句）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.53s` | `750627a`（§1.5/§1.6/§2.3） | 纯文档改动（`PROJECT.md`）。**先说明验收口径的局限**：`grep -c "v2.0"` 这个阈值**在我改动之前就已满足**（任务表 §6.5 与 §1.4 里的 `v2.0.0` 字样本身就会命中），所以它不是一个有效的代理指标——我另外用三条锚点 grep 证明"该写的内容真的写进去了"（见左列第 2–4 条）。**实际改动三处**：① **§1.5** 在 `D1`–`D5` 表后加"**2.0.0 的交付形态：两段式安装**"表——默认段（`pip install .` + `dsh plugin add .`，依赖只有四个，**与 1.0.0 步骤完全相同**）与可选段（extra `semantic` + 用户自装 Ollama，再设 `CODERAG_SEMANTIC=on`），并写明"两段都不做的人也永远不会碰到向量"；② **§1.6 新增 `1.6.4`**：把 extra 名/内容/是否进 tarball/是否进 `install.sh` 默认路径/用户侧那一半逐项冻结（全部指向 `ADR-16` §3.1/§3.2/§7.1），并解释"为什么不把 numpy 放进 `dependencies`"；③ **§2.3** 补"**v2.0.0 的范围**"块——写明决策门 `T3-07` 已裁定（R2 命中 → `ADR-14`；端到端已由纯词法达成 → 先暂缓 `ADR-15`、再重启为可选 `ADR-16`），并**明确本节三条证据至今未被推翻**、它们现在约束的是默认路径："`不做`从不等于`永远不做`，而是`不默认做`"，结句指向 `ADR-16`（"本节回答为什么第一版不做，`ADR-16` 回答第二版怎么做成可选的"）。**自查修正一处笔误**：初稿把 `ADR-16` 打成 `ADDER-16`，提交前用 `grep -c ADDER` 复核为 0 <br>**复核（2026-09-23，用户要求修复）**：同一条命令重跑得 **12**（当时记 11），T5-09 那行也从 23 涨到 27——**这两条命令是自指的**：记录 `grep -c "<模式>"` 的**证据行本身就含该模式**，所以每多一行证据就 +1，历史读数再也复现不出来。判据（≥3）两次都成立，但**把一个会漂的数字当证据是错的**。可复现的度量（排除 §6.7 的证据行，因为证据行都以 `| **T5-` 开头）：`grep -v '^| \*\*T5-' PROJECT.md | grep -c "v2.0"` → **10**（≥3，且此后不再随新增证据漂移）。教训已写进 `AGENTS.md` §5.3。 |
| **T5-09** | 已完成 | `$ grep -c "可选后端" PROJECT.md`<br>`23`（要求 ≥3）<br>`$ grep -n "向量索引的落点\|可选：2.0.0 的 extra\|第 2 阶段：可选后端路径" PROJECT.md`<br>`659:**向量索引的落点（2.0.0 的可选后端，**默认关闭**、默认不创建）**（ADR-16 §5）`<br>`746:**可选：2.0.0 的 extra semantic（**默认关闭**、默认不装）**（ADR-16 §3.2）`<br>`1002:**第 2 阶段：可选后端路径（ADR-16；**默认关闭**）**`<br>（三处都写明"默认关闭"）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.48s` | `b936dfc`（§3.6/§4.2/§5.3 等） | 纯文档改动（`PROJECT.md`）。**三处指定修改**：① **§3.6** 的"预留的向量表（M3 决策通过后才创建）"改为可选后端口径——**向量不进 `index.sqlite3`**，而是 `<root>/.coderag/vectors/{embeddings.npy,manifest.json}`；SQLite `embeddings(... vector BLOB)` 表**列为被否决方案**并给了三条理由（逐行读 BLOB 抵消 numpy 向量化、与 BM25 共用库造成写放大、独立文件可整体丢弃且 manifest 就是"旧向量还能不能用"的依据）。**这是一处实质性设计改动**：1.0 版的预留设计是 SQL 表，`ADR-16` §5 冻的是文件形式，§3.6 必须服从后者（否则文档与冻结条文自相矛盾）。② **§4.2** 的"可选（M3 决策通过后才加）"改为"2.0.0 的 extra `semantic`（默认关闭、默认不装）"：extra 内容只剩 `numpy` 一项，Ollama 明确标为"用户自装的系统服务、不是 Python 依赖也不是安装前置"，**`httpx` 行删掉**（`ADR-16` §3.1/§3.2 已否决云端后端并改用 stdlib `urllib`）；"明确不引入"里 ChromaDB/Qdrant/Milvus/**faiss** 改为默认与可选路径都不引入。③ **§5.3** 的"第 2 阶段（M3 决策通过后）：混合检索"改为"**第 2 阶段：可选后端路径（默认关闭）**"，并补两条理由（为什么用 RRF 而不是加权分数——量纲不可比、归一化会漂移；为什么是"补齐而非替换"——`exact` 桶必须保持 1.000）。**另外两处同源残留一并改掉**（都属于"依赖与检索路径"）：§4.1 环境表里 `Ollama \| 未安装 \| M3 决策通过后才需要` 改为"仅可选后端需要，默认关闭"；§5 的 A/B/C 对照表里 `C · 混合 \| （M3 决策后）BM25 + 向量 + RRF` 改为"可选后端路径，默认关闭，只在 `T3-11` 的 C 组实验里以 `CODERAG_SEMANTIC=on` 开启" <br>**复核（2026-09-23，用户要求修复）**：同一条命令重跑得 **27**（当时记 23）——与 T5-08 同因：**证据行自指**（记录 `grep -c "可选后端"` 的那行本身含该字样）。可复现的度量：`grep -v '^| \*\*T5-' PROJECT.md | grep -c "可选后端"` → **23**（恰好回到当时的值，因此"当时 23"这个读数本身没错，错的是它不可复现；≥3 成立）。教训已写进 `AGENTS.md` §5.3。 |
| **T5-10** | 已完成 | `$ grep -c "C 组" EVAL.md`<br>`6`<br>`$ grep -c "天花板探针" EVAL.md`<br>`2`<br>`$ grep -c "0.025" EVAL.md`<br>`7`（三项各自 ≥1）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.38s` | `91ab96f`（`EVAL.md` §3.7） | 纯文档改动（`EVAL.md` 新增 §3.7）。**先核实 schema 再写命令，并在提交前把每条命令真跑一遍**——这是本任务唯一容易做假的地方（写出一堆看着合理但跑不通的"判定命令"）。实测：L2 `report.json` 的真 schema 是 `cases[].{name,successes,trials,pass@k,pass^k}`（**没有** `results`/`metrics`）；L1 `gate` 的真 schema 是 `metrics.{exact,natural,...}.success["5"]` + `regression_count`。据此写的三条命令都实跑过：V3 的配对符号检验用 `b-v1` vs `b-r5` 当替身 → `C better on 8, worse on 0, discordant n=8, one-sided p=0.0039` → `V3: PASS`；V1/V2 的两条 `python -c` 对 `eval/runs/l1-gate.json` → `exact@5 = 1.0 regressions = 0`、`natural@5 = 0.0`。**内容**：① §3.7.1 天花板探针（`T5-14`）——目标/语料/脚本落点（**一次性脚本不进 `src/`，因此不背测试与覆盖率义务**）/必须记录项/判定（`natural` 上限低于 `S5` 的 0.40 即 no-go），并写清探针（理论上限）与 C 组（真实链路：RRF、top-k、预算裁剪）的分工——**先看天花板，因为天花板不够就不必看落地**；② §3.7.2 C 组命令与**五条配对要求**（同 13 条用例 / 同工作区 / 同 trials=3 / 同 profile+patch / 逐条对比），并逐条写明违反后的后果；③ §3.7.3 把 **V1–V4 逐条落到命令**：V1/V2 走 L1 `gate`（`natural@5 ≥ 0.40` 且 > B 组的 0.000；`exact@5 == 1.0` 且 `regressions == 0`），V3 走配对符号检验（**单侧**、**α = 0.025**、要求报告显式声明"这是第二次检验"），V4 是**发布决定而非统计量**（V1 或 V3 未过即不发布；`S6` 仍须无条件成立） |
| **T5-11** | 已完成 | `$ grep -c "默认关闭" TESTING.md`<br>`6`<br>`$ grep -c "回退" TESTING.md`<br>`8`（各 ≥1）<br>`$ python3 scripts/verify-plan.py .`<br>`  ✅ [E2] 必测清单 11 项：M1, M2, M3, M4, M5, M6, M7, M8, M9, M10, M11`<br>`  ✅ [E3] 必测清单引用的 14 个任务全部存在`<br>`  ✅ [E4] 必测清单覆盖 L3 端到端层`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.66s` | `4ba69b7`（`TESTING.md`） | 纯文档改动（`TESTING.md`）。**§2 必测清单新增 M11**「可选后端默认关闭且未配置时回退」，层列为 `L1+L2`，对应任务列引用 `T3-08, T3-09, T3-10, T3-11, T5-15`（`E3` 校验通过：14 个被引用任务全部存在）；`E2` 由 10 项变 **11 项**（脚本的 `MIN_TEST_ITEMS = 10` 是下限，增项被接受）。**新增 §3.12 给出离线可测的方法**（它正是 M11 那格引用的落点）：三组用例——① 默认关闭（`monkeypatch.delenv`，断言"与纯 BM25 逐条一致"即 `S6`，并断言 `sys.modules` 里没有 numpy）；② 开关打开但后端不可用（**把 `CODERAG_SEMANTIC_URL` 指向 `http://127.0.0.1:1`**，于是不需要 Ollama、也不需要网络，就满足了 `T-02`）；③ 非 loopback URL 必须被拒绝（安全拒绝）。另列四条"不许这样测"的反例，其中最关键的一条：**只断言 `status != "error"` 是太弱的**——回退的定义是"逐条与纯 BM25 一致"，必须比结果而不是比状态字段；以及"只断言 `isError is False`"漏掉 `RL-06` 的另一半（不能返回空列表）。**同时把 §7 速查的"必须有的十类测试"改为"十一类"**并补 M11（否则速查与 §2 立刻不一致）。**一处诚实标注**：`SEMANTIC_*` code 尚未进 `ErrorCode`（`ADR-16` §6 写明是契约先行），所以第二、三组用例在 `T3-10` 之前会因 code 不存在而红——这是测试正确地指向未实现的契约，不是测试写错 |
| **T5-12** | 已完成 | `$ grep -c -e "已重启" -e "执行中" docs/adr/ADR-14-semantic-retrieval.md docs/adr/ADR-15-defer-semantic-retrieval.md`<br>`docs/adr/ADR-14-semantic-retrieval.md:1`<br>`docs/adr/ADR-15-defer-semantic-retrieval.md:3`（两份合计 **4** ≥ 2）<br>`$ grep -c "暂缓" docs/adr/ADR-15-defer-semantic-retrieval.md`<br>`7`（**历史理由仍在**）<br>`$ git diff --stat`<br>`ADR-14: 2 +-`、`ADR-15: 6 ++++++`（**7 insertions, 1 deletion**——唯一被删的是 ADR-14 的状态行本身，且替换后 `复核：2026-09-20 维持` 与指向 `ADR-15` 的引用都保留）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.38s` | `52f3fc3`（两份 ADR） | 纯文档改动（两份 ADR）。**`ADR-14` 只改状态行的"执行"字段**：`执行：**暂缓**` → `执行状态（2026-09-23）：**已重启**为可选后端（2.0.0）——形态冻结在 ADR-16；此前的暂缓见 ADR-15`，其余（`已决定（T3-07）`/`复核 2026-09-20 维持`/`裁决日期`）一字未动。**`ADR-15` 是纯新增 6 行**：① 状态行下加"执行状态（2026-09-23）：暂缓**已结束**、`T3-08`–`T3-11` **已重启**"，并**明写快照性质不变**（§2 暂缓理由 / §3 重启条件 / §6 限制都按原文保留）；② §1 加"后续更新"——四条里第 1 条的暂缓已结束、第 2 条的形态要求被 ADR-16 冻结成可验收条文、第 3/4 条不变（**"重启的是执行，不是重开决策门"**）；③ §3 加"后续更新"——四条重启条件**逐条兑现**（形态 / `T5-14` 探针先行 / V1–V4 继承且 α=0.025 / `T3-11` 验收命令换成自建 runner），并附上 `T3-11` 的完整命令；④ §5 后果那一条加一行"这三项**已重启**——本行只描述 2026-09-20 的状态"。**全部保留历史**：`暂缓` 在 ADR-15 里仍有 **7** 处命中，§2 的"端到端目标已由纯词法达成"等原始理由未删改；`git diff` 显示 7 增 1 删，删的那一行是 ADR-14 状态行自身（已按上句替换，无信息丢失） |
| **T5-13** | 已完成 | `$ grep -c "可选后端" README.md docs/architecture.md`<br>`README.md:3`<br>`docs/architecture.md:4`（两份合计 **7** ≥ 2）<br>`$ sed -n '1,8p' README.md \| grep -c "机器权限"`<br>`1`（`D-04`：安全声明仍在第一屏）<br>`$ sed -n '/^## 可选语义后端/,/^## 工具/p' README.md \| grep -c "1\.0\.0\|v1\.0\|2\.0\.0\|v2\.0"`<br>`0`（**新增段落不含任何版本号**——版本号属 `T5-17`）<br>`$ tail -c 1 README.md \| xxd`→`0a`、`docs/architecture.md` 同（`D-07`：末尾恰好一个换行）<br>`$ python3 scripts/verify-plan.py .`<br>`计划完备性：通过 ✅   （28 项检查全部实际执行，无空过）`<br>`$ /opt/anaconda3/envs/forBSH/bin/python -m pytest`<br>`445 passed, 2 skipped in 2.31s` | `56d0545`（`README.md` + `docs/architecture.md`） | 纯文档改动（两份）。**README 新增 `## 可选语义后端（默认关闭）`**（放在「配置」与「工具」之间）：它解决什么问题（`natural` 桶 0.000、100% 归因零词法重叠）、**两段式装法**（`pip install -e ".[semantic]"`／`CODERAG_WITH_SEMANTIC=1 bash scripts/install.sh` + 用户自装 `ollama pull bge-m3`）、**开关表**（`CODERAG_SEMANTIC` 未设即关闭、`_URL` 只允许本机、`_MODEL`/`_TIMEOUT`/`_BATCH`/`_MAX_CHUNKS`）、失败行为（干净回退、带 `SEMANTIC_*` code、不 `isError`、不空列表），以及**"限制如何变化"对照表**（自然语言 0.000 → 目标 ≥0.40 但**明确写"是否达标要看探针与 C 组数据，本节不预先承诺"**；`S1`/`S2` 与端到端**不变**；依赖多一个 numpy；默认路径行为是硬门禁 `S6`）。**`## 已知限制` 第一条改为"默认安装下，纯中文自然语言检索不可用"**（原写"基本不可用（已知且已决定暂缓）"），并把 `ADR-15` 的"暂缓"与 `ADR-16` 的"重启为可选后端"两句都保留、指向新小节。**`docs/architecture.md` 三处**：① 模块表 **`searcher` 行补可选后端路径**（向量召回 + RRF，并写明"关闭时不得 import numpy"）；② **新增 `embed` 模块行**（`embed.py`：调 Ollama 生成/缓存 embedding、读写 `.coderag/vectors/`；不排序不融合、不参与 BM25 路径、未启用时不得成为导入或启动的阻塞点）；③ 依赖方向图加 `searcher ──► embed`（**仅在可选后端启用时**，延迟导入）；④ §11 非目标的"v1.0.0 不含向量检索"改为"**默认路径不含向量检索**"并补 `ADR-16` 的四条形态要点——**同时把这条里的版本号去掉**，于是 `architecture.md` 只剩第 8 行"实现版本"一处版本号（那正是 `T5-17` 要改的），`T5-17` 不必再碰这一条 |

---

### 6.8 覆盖矩阵（**完备性的可验证形式**）

> **为什么需要这张表**：覆盖关系**不能自动推断**。例如红线 RL-01（"禁止修改 DSH 文件"）约束的是**所有**任务，不会被任何一个任务"引用"；而 ADR-07（中文分词）则由 `T1-06` 和 `T2-19` 具体落地。
> 本表把每条定义**显式**映射到"由谁强制"，然后由 `scripts/verify-plan.py` 反向验证**这张表自身完整且引用有效**。

**强制点的三种取值**：
- `T*-**` —— 由某个具体任务实现/验证
- `*全局*` —— 适用于所有任务的边界规则，无单一落点
- `—` —— 已被其他文档的规则取代，本项目不单独落地（须在「说明」里写明）

| 定义 | 强制点 | 说明 |
|---|---|---|
| ADR-01 | *全局* | 架构决策（Python + MCP）。由 §1.6 的仓库布局与 T1-14 落地 |
| ADR-02 | T3-07 | 第一版只做 BM25；由决策门强制，`RL-10` 是它的红线形式 |
| ADR-03 | T1-11 | 工具集固定为 4 个；`RL-05` 是它的红线形式 |
| ADR-04 | T1-12 | 索引异步化，立刻返回 taskId |
| ADR-05 | T2-14, T3-14 | 检索结果按源码顺序输出 |
| ADR-06 | T1-13 | 索引未就绪返回结构化状态；`RL-06` 是它的红线形式 |
| ADR-07 | T1-06, T2-19, T3-13 | 中文 bigram 预处理 + 精度/召回双模式 |
| ADR-08 | T2-06 | 三层安全过滤（密钥黑名单 / 忽略规则 / 内容扫描） |
| ADR-09 | T2-09 | 索引状态与忽略规则一并持久化 |
| ADR-10 | T2-11 | 超过文件数上限显式失败并报实际数量 |
| ADR-11 | T2-10 | 并发度与批大小自适应，不硬编码 |
| ADR-12 | T3-04 | 指标用 `Success@k`，不用 nDCG |
| ADR-13 | T2-19 | 标点/短符号查询路由到 `grep`，不做全表 `LIKE` |
| ADR-14 | T3-07, T3-08, T3-09, T3-10, T3-11 | R2 命中：词法为底 + 向量补齐自然语言查询；执行由已重启的 `T3-08`–`T3-11` 落地，判据是 `ADR-14` §10.4 的 V1–V4 |
| ADR-15 | T3-08, T3-11, T5-16 | **已重启为可选后端（2.0.0）**：默认关闭、未配置时干净退回纯 BM25、**不得进入必需依赖**；重启条件见 `ADR-15` §3，形态由 `ADR-16`（`T5-05`）冻结 |
| ADR-16 | T3-08, T3-09, T3-10, T3-11, T5-15 | **可选后端的可验收形态（2.0.0）**：默认关闭 + opt-in、未配置时输出与 1.0.0 逐字节一致、extra 名 `semantic`（只有 numpy）/后端 `ollama`+`bge-m3`/索引落点 `<root>/.coderag/vectors/`/失败码 `SEMANTIC_*` 并回退 BM25；发布服从 `ADR-14` §10.4 的 V1–V4（V3 `α = 0.025`、V4 不显著优于 B 就不发布），探针 `T5-14` 先行 |
| ADR-17 | T5-20, T5-21, T5-22 | **云端后端也是可选的（2.0.0）**：`openai` 兼容 `/v1/embeddings`、双重开关（`ALLOW_REMOTE=1` 才允许非 loopback）、key 只从环境读、形态与本地对称；**风险声明随每一处配置出现**（`D-08`）；判据按后端独立满足 |
| C1 | T1-12 | MCP 工具 60s 超时 → 索引必须异步 |
| C2 | T1-14 | stdio 环境清洗 → key 必须走 `config.env` |
| C3 | *全局* | preset `complete:true` 吞注入 → 本项目不做 prompt 注入（见 `AGENTS.md` E-03） |
| C4 | T1-11 | MCP 工具集必须固定 |
| C5 | T1-06, T2-19 | 中文检索必须专门处理（bigram） |
| C6 | T1-13 | 索引未就绪必须返回结构化状态 |
| C7 | T2-06 | 忽略规则是安全边界，不是体验优化 |
| C8 | T2-10 | 批处理参数必须自适应 |
| C9 | T2-11 | 文件数上限必须显式报错 |
| C10 | T2-09 | 索引状态必须跨重启持久化 |
| C11 | T4-02, T4-06 | pnpm 10+ 拒绝 install script → 本项目零 install script |
| C12 | T4-04 | DSH 插件 = 完整机器权限 → README 必须披露 |
| RL-01 | *全局* | 禁止修改 DSH 仓库任何被跟踪文件 |
| RL-02 | *全局* | 禁止把凭据写入仓库 |
| RL-03 | T2-06 | 禁止索引密钥文件 |
| RL-04 | T1-11, T2-19 | 禁止 stdout 非协议内容 |
| RL-05 | T1-11 | 禁止增删 MCP 工具 |
| RL-06 | T1-13 | 禁止用空列表代替状态 |
| RL-07 | T2-10 | 禁止硬编码资源参数 |
| RL-08 | T2-11, T2-21 | 禁止静默截断 |
| RL-09 | T1-13, T2-22 | 禁止让异常冒泡成 `isError` |
| RL-10 | T3-10, T5-15, T5-16 | **改写后**（旧表述"决策门前禁止 embedding"的使命已由 `T3-07` 完成）：向量不得进入默认路径或必需依赖——`dependencies`/tarball/`install.sh` 默认路径零向量依赖（强制于 `T5-15`），未配置时逐条回退纯 BM25（强制于 `T3-10`），默认安装的解释器里没有 numpy（强制于 `T5-16`）；形态冻结于 `ADR-16` §1/§3.2/§7.1 |
| RL-11 | *全局* | 提交纪律：工作区干净、一任务一提交 |
| S1 | T3-04, T3-06 | 成功标准：检索本身有效（Success@5 ≥ 0.80） |
| S2 | T3-04, T3-06 | 成功标准：排序质量合格（MRR ≥ 0.60） |
| S3 | T3-05, T3-06, T3-07 | 成功标准：端到端有提升（≥10 个百分点） |
| S4 | T2-15, T3-04 | 成功标准：token 中位数 ≤ 4000 |
| S5 | T3-11, T5-15 | 成功标准（可选后端）：开启时 **`natural` 桶 `Success@5` ≥ 0.40**；只约束**已发布**的向量路径（探针 no-go 或 V4 判定不发布时不参与判定） |
| S6 | T3-10, T5-16 | 成功标准（默认路径，无条件）：未配置 `CODERAG_SEMANTIC` 时逐条与 `1.0.0` 一致——回归条数 **= 0** 且 `exact` 桶保持 **1.000** |
| D1 | T1-01, T4-03 | 交付物 1：Python 包 `dsh_coderag` |
| D2 | T1-11 | 交付物 2：MCP 服务（stdio） |
| D3 | T4-01, T4-02 | 交付物 3：DSH bundle（npm 包） |
| D4 | T3-02a, T3-02b | 交付物 4：评测集与评测脚本 |
| D5 | T4-04, T4-05 | 交付物 5：README（含安全声明） |

**如何校验**：

```sh
python3 scripts/verify-plan.py .          # 完备性校验：28 项检查
python3 scripts/test-verify-plan.py .     # 校验器自身的变异测试：19 个破坏用例
```

`verify-plan.py` 执行 **28 项检查**，分七组：

| 组 | 检查项 | 说明 |
|---|---|---|
| **A** | `A1`–`A6` | `EVAL.md` §6 与任务表的漂移：标题匹配、ID 提取、解析失败与空集区分、权威版本声明、孤立 ID、合并声明 |
| **B** | `B1`–`B8` | 覆盖矩阵：ADR/C/RL/S/D 五类覆盖、数量下限、虚构键、重复键、`—` 说明、强制点格式、全局行 |
| **C** | `C-DEP` / `C-CYCLE` / `C1` / `C3` / `C4` / `C5` | 依赖存在性、无环、重复 ID、自依赖、依赖格式、§6.6 图与表同步 |
| **D** | `D1`–`D3` | 唯一根 = `T1-01`；所有任务可达根；根自身无依赖 |
| **E** | `E1`–`E4` | `TESTING.md` 必测清单 M1–M10 的任务映射、`AGENTS.md` §5.2 的 T-01–T-08 |
| **F** | `F4` | 各类数量的下限阈值（防止"解析为 0 也算通过"） |

**`test-verify-plan.py` 是它的可信度证明**：把四份文档复制到临时目录，逐个施加 19 种人为破坏（删矩阵行、重复任务 ID、自依赖、孤立 T1、EVAL 幽灵 ID、图漂移、制造环…），断言校验器**必须返回非零**。**全部 19 个变异均被检出**才算通过。

> **为什么需要变异测试**：一个只会说"通过"的校验器毫无价值。上面的 28 项绿灯，只有在证明它们**在坏数据上会变红**之后才有意义。
>
> 更新计划后请**两个都跑**。改动任务表后如果 `C5` 失败，用 `python3 scripts/verify-plan.py . --emit-graph` 重新生成 §6.6。



---

## 7. 风险登记册

| # | 风险 | 概率 | 影响 | 触发信号 | 应对 |
|---|---|---|---|---|---|
| R1 | **检索没带来提升**（S3 不成立） | 中 | 高 | M3 对照实验无差异 | 这是**合法结论**。按 T3-07 的 R1 规则收尾，把项目定位改为"符号检索 + 结构大纲"，不做向量 |
| R2 | tree-sitter grammar 与目标语言不匹配 | 中 | 中 | 解析报错或切分位置异常 | 走 L4 降级并标注 `low_confidence`；优先保证 C/C++/Python 三种 |
| R3 | 大仓库索引超时/吃满内存 | 中 | 中 | 索引 > 5 分钟或内存 > 4 GB | 自适应限流（T2-10）+ 文件数上限（T2-11）；先支持 2 万文件以内 |
| R4 | 中文查询召回差 | 中 | 中 | 中文评测任务 Recall 明显低于英文 | 按 `EVAL.md` §2.8 归因：先查 A1（分词）再查 A5（语义）。**本机 PoC 已证明分词是主因** |
| R5 | 模型不使用新工具 | 中 | 高 | T1-15 中工具从未被调用 | 工具 `description` 写明"当你不知道确切标识符时优先用它"；在项目 `AGENTS.md` 里写一句使用指引 |
| R6 | DSH 上游破坏性变更 | 低 | 中 | DSH 升级后 MCP 行为变化 | 本项目不依赖 DSH 内部 API，只依赖 MCP 协议，天然隔离 |
| R7 | pnpm 拒绝 install script 导致"装了不加载" | 中 | 中 | `dsh plugin add` 后工具不出现 | 按 T4-06 在 README 写清 `allowBuilds`；用 `--dump-config` 自检 |
| R8 | 用户机器无 conda / Python 版本不符 | 高 | 中 | 安装失败 | T4-03 的安装脚本要检测并给出明确指引；长期考虑提供 Docker 或 uvx 方案 |
| R9 | 密钥被误索引（安全事故） | 低 | **极高** | T2-06 测试失败 | **T2-06 是 M2 的强制门禁**，不通过不允许进入 M3 |
| R10 | 范围蔓延（想做文档 RAG、GUI、记忆） | 高 | 中 | 任务表里出现非目标项 | 回到 1.3 节的非目标表；所有新想法记入 `docs/backlog.md`，不进当前里程碑 |

---

## 8. 参考资料

### 8.1 本项目直接依赖的一手事实（本机核实）

| 事实 | 位置 |
|---|---|
| MCP client 配置字段与 60s 超时 | `packages/mcp/mcp-client/README.md` |
| stdio 环境变量清洗规则 | 同上，"Environment scrubbing (stdio)" |
| preset `complete: true` 吞掉 system-prompt 注入 | `packages/preset/persona/README.md` 第 42/49 行 |
| 插件 = 完整机器权限（官方明示设计非目标） | `packages/extensions/tool-cordis/README.md` 第 182 行；`.agents/notes/implemented/architecture/2026-07-08-agent-scope-contexts.zh.md` 第 145 行 |
| FTS5 分词限制 | `packages/session-query/session-query-sqlite/README.md` |
| 工具注册与执行流水线 | `packages/core/tools/README.md`；`docs/tool-execution-pipeline.zh.md` |
| 插件开发入门（官方教程） | `docs/user/develop/basic/index.zh.md`、`tool.zh.md`、`publish.zh.md` |
| 能力 seam 三件套模式 | `docs/user/develop/practice/index.zh.md` |
| 插件发现机制（`dsh-plugin` topic） | `README.zh.md` 第 50 行；`CONTRIBUTING.md` 第 15 行 |

### 8.2 关键论文

| 主题 | 来源 |
|---|---|
| 代码检索 BM25 打败稠密向量 | CodeRAG-Bench, arXiv 2406.14497 |
| 检索经常不提升性能（80%） | Repoformer, arXiv 2403.10059 |
| 长上下文 vs RAG（16K 打败 196K） | NVIDIA OP-RAG, arXiv 2409.01666 |
| 长上下文并非总赢 | Google DeepMind, arXiv 2407.16833 (EMNLP 2024) |
| RAG 七个失败点 | arXiv 2401.05856 |
| 无答案时模型仍作答（拒答率仅 43%） | RGB, arXiv 2309.01431 |
| 上下文腐化 | Chroma, "Context Rot", 2025-07-14 |
| 提示注入防御被自适应攻击击破 | arXiv 2510.09023 |
| 混合检索与 rerank 的收益 | Anthropic, "Contextual Retrieval", 2024-09-19 |

### 8.3 同类项目（可借鉴的实现）

| 项目 | 借鉴什么 |
|---|---|
| [Aider `repomap.py`](https://github.com/Aider-AI/aider) | tree-sitter 符号图 + 图排序构造仓库地图 |
| [Continue `core/indexing/README.md`](https://github.com/continuedev/continue) | 内容寻址 + 分支缓存的增量索引设计 |
| [code-rag `src/chunker.ts`](https://github.com/Ankali-Aylina/code-rag) | 声明感知分块（花括号深度 + 签名识别） |
| [dsh-knowledge `src/knowledge/retrieval.ts`](https://github.com/Soren-ABT/dsh-knowledge) | BM25(`K1=1.5,B=0.75`) + 向量 + RRF(`K=60`) + MMR 的完整实现 |
| [dsh-code-index](https://github.com/lemonxiny55/dsh-code-index) | repo map 注入的边界控制（`mapMaxChars` 3200 / TTL 60s / 可关闭） |
| [dsh-recall](https://github.com/Relistencode/dsh-recall) | 语义层的覆盖率门槛（≥90% 才并入）与 `semantic→fuzzy→literal` 降级链 |

### 8.4 学习资源（中文）

| 资源 | 说明 |
|---|---|
| [DeepSeek Harness Handbook](https://github.com/sandbaseai/deepseek-harness-handbook) | 173 篇带源码验证日期的指南，含简体中文 |
| [《一切皆插件》](https://github.com/diguike/book-deepseek-harness) | 21 章源码精读 + 可运行的 mini-dsh |
| [DSH discussion #380](https://github.com/deepseek-ai/deepseek-harness/discussions/380) | 「写第一个 dsh 插件踩的六个坑」，含本机复核 |
| [DSH discussion #462](https://github.com/deepseek-ai/deepseek-harness/discussions/462) | 插件运行时验证方法论：mock llm + headless + 审计 dump，**零成本无 key** |
| [MCP Python SDK 文档](https://py.sdk.modelcontextprotocol.io/) | 官方 SDK，注意 v1/v2 API 差异 |
