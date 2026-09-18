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
| 环境变量 | `CODERAG_*` | `CODERAG_ROOT` / `CODERAG_MAX_FILES` / `CODERAG_MAX_TOKENS` / `CODERAG_PYTHON` |
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

项目成功的判据**不是"功能做完了"，而是下面这四条同时成立**：

| # | 标准 | 度量方式 | 阈值 |
|---|---|---|---|
| **S1** | **检索本身有效** | 在自建评测集上，`code_search` 的 **Success@5** | ≥ 0.80 |
| **S2** | **排序质量合格** | 正确文件在结果中的平均排名 **MRR** | ≥ 0.60 |
| **S3** | **端到端有提升** | 评测集任务通过率：有检索 vs 无检索 | 相对提升 ≥ 10 个百分点 |
| **S4** | **成本可接受** | 单次 `code_search` 返回的 token 数 | 中位数 ≤ 4000 |

> `S1`–`S4` 是本项目的稳定标识——`§6.7 覆盖矩阵` 与 `EVAL.md` 都按这些 ID 引用它们，**不要改名**。

> **为什么把 S3 设成必要条件**：调研中有一条关键实证——Repoformer 的测量显示**最多 80% 的检索结果并不提升下游任务性能**，只有约 20% 的实例真正受益。如果 S3 不成立，说明检索在做无用功，**此时砍掉它是正确的工程决策，而不是项目失败**（依据：CodeRAG-Bench / Repoformer，见第 8 章）。

### 1.5 交付形态

| ID | 交付物 | 落点 | 判据 |
|---|---|---|---|
| **D1** | Python 包 `dsh_coderag` | `src/dsh_coderag/` + `pyproject.toml` | `pip install .` 可安装；`dsh-coderag --version` 可用 |
| **D2** | MCP 服务（stdio 传输） | `src/dsh_coderag/server.py` | 4 个工具可被任何 MCP 宿主发现并调用 |
| **D3** | DSH bundle（npm 包） | 仓库根 `package.json` + `cordis.patch.yml` | `dsh plugin add` 一条命令安装 |
| **D4** | 评测集与评测脚本 | `eval/tasks.jsonl` + `src/dsh_coderag/eval/` | 可重复跑出 S1–S4 的数字 |
| **D5** | README（含安全声明与限制） | `README.md` | 顶部披露插件权限范围；含实测数据与已知限制 |

> `D1`–`D5` 是稳定标识，被 `§6.7 覆盖矩阵` 引用，**不要改名**。

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
| 本地开发 / tarball | `dsh plugin --profile <p> add .` 或 `add ./dsh-coderag-0.1.0.tgz` | bundle 清单在仓库根 |
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
| `config` | `src/dsh_coderag/config.py` | 配置读取与校验（环境变量） | 不做默认值猜测（缺失必填项要报错） |
| `walker` | `src/dsh_coderag/walker.py` | 遍历工作区、应用忽略规则与密钥黑名单 | 不读文件内容 |
| `chunker` | `src/dsh_coderag/chunker.py` | tree-sitter 声明感知分块 | 不写数据库 |
| `indexer` | `src/dsh_coderag/indexer.py` | SQLite schema、增量写入、幂等 | 不做检索 |
| `searcher` | `src/dsh_coderag/searcher.py` | FTS5 查询、打分、顺序保持、预算裁剪 | 不做索引 |
| `taskman` | `src/dsh_coderag/taskman.py` | 异步任务创建/进度/取消/持久化 | 不执行具体索引逻辑 |
| `render` | `src/dsh_coderag/render.py` | 把结果渲染成模型可见文本 | 不做检索决策 |
| `server` | `src/dsh_coderag/server.py` | MCP 协议实现、4 个工具注册 | 不含业务逻辑（薄层） |
| `eval` | `src/dsh_coderag/eval/` | 评测集加载、运行、指标计算、报告 | 不参与生产路径 |
| `cli` | `src/dsh_coderag/__main__.py` | 命令行入口（`index` / `search`） | 供人调试用，非模型接口 |

**模块依赖方向（禁止反向依赖）**：

```
cli ──► server ──► {taskman, searcher} ──► {indexer, walker} ──► chunker
  └──────────────────────► eval ──────────────────────────────►┘
config ◄── 所有模块（只被读取，不依赖任何模块）
render ◄── server, eval（只被调用）
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
  symbol_kind   TEXT,                      -- function|class|method|module
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

**预留的向量表（M3 决策通过后才创建，此前不建）**：

```sql
-- 仅当 M3-DECIDE 判定需要语义检索时创建
CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id  INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  model     TEXT NOT NULL,
  dim       INTEGER NOT NULL,
  vector    BLOB NOT NULL          -- float32 little-endian，dim*4 字节
);
```

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
| Ollama | 未安装 | M3 决策通过后才需要 |
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

**可选（M3 决策通过后才加）**

| 依赖 | 用途 | 备注 |
|---|---|---|
| `ollama`（外部服务）+ `bge-m3` 模型 | 本地 embedding | 约 1.2 GB，免费、中文强 |
| `numpy` | 暴力余弦相似度 | 10 万 chunk 以内不需要向量数据库 |
| `httpx` | 调用云端 embedding API | 仅当用户显式配置 |

**明确不引入（第一版）**

| 不引入 | 理由 |
|---|---|
| LangChain / LlamaIndex | 已在 DSH 之上，再套一层编排是重复抽象；且带来版本破坏性风险 |
| ChromaDB / Qdrant / Milvus | 第一版没有向量，不需要向量库。将来优先考虑 `sqlite-vec` 或纯 numpy 暴力检索 |
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
| **L3 文件头** | 每个文件产生一个 `symbol_kind="module"` 的头部块（前 40 行），内含 license/import/宏定义，便于回答"这个模块是干什么的"。 |
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
| **状态持久化** | 每次索引开始/结束都写 `index_runs` 与 `workspace_index`（约束 C10） |
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

**第 2 阶段（M3 决策通过后）：混合检索**

```
BM25 排名 ─┐
            ├─► RRF 融合（k=60）─► 截断 ─► 顺序保持 ─► 预算裁剪
向量排名 ─┘
```

RRF 公式：`score(d) = Σ_r 1 / (k + rank_r(d))`，`k = 60`（Elasticsearch / Azure / Weaviate 的默认值）。

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

**铁律**：任何内部异常都**不得**向上冒泡成 MCP 的 `isError` 而丢失结构。必须转成带 `status` 与 `code` 的**正常返回值**，让模型能据此决策。

### 5.7 可观测性

- **结构化日志**：JSON Lines 输出到 `stderr`（**绝不能写 stdout**，stdout 是 MCP 协议通道）。
- 每条日志含：`ts`, `level`, `event`, `task_id`, `duration_ms`, 及事件相关字段。
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
| C · 混合 | （M3 决策后）BM25 + 向量 + RRF |

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

**任务编号规则**：`T<里程碑>-<序号>`，例如 `T1-03`。每个任务必须独立可验收。**带字母后缀的（如 `T3-02a`）是同一任务的批次拆分**，各自独立提交。

---

#### 6.0.1 任务表的读法与依赖约定

**列的含义**：

| 列 | 含义 | 执行要求 |
|---|---|---|
| **ID** | 任务编号 | 一个任务一个提交（`AGENTS.md` §7.0）。**带字母后缀的（如 `T3-02a`）是同一任务的批次拆分**，仍各自独立提交 |
| **任务** | 要做什么 | 一句话，无歧义。括号里的"（条件）"表示仅在决策门命中时执行 |
| **产出文件** | 只允许改这些文件 | 超出范围即为越界，见 `AGENTS.md` §9 |
| **验收命令** | 必须实际执行 | 输出要贴进 §6.6 |
| **期望结果** | 命令输出应满足的条件 | 不满足即未完成 |
| **依赖** | **硬阻塞**：必须先完成的任务 | 见下方约定 |
| **估时** | 参考工时 | 超过 3 倍请停下来报告（`AGENTS.md` §9） |

**依赖列的约定（重要）**：

> **依赖列只列「硬阻塞」**——跨里程碑的，或里程碑内顺序敏感的。
> **同里程碑内其余部分按 ID 升序执行即可**，不要求把全部前置关系都写成边。

这条约定的后果是：**很多任务是"叶子"**（没有任何任务依赖它），例如 `T1-02`（`config.py`）、`T1-09`（`render.py`）、`T4-07`（`LICENSE`）。**这是正常的，不是漏边。**

但有一条**必须成立**的约束：**除 `T1-01`（仓库骨架，整棵依赖图的唯一根）外，每个任务都必须能沿依赖边传递追溯到 `T1-01`。** 违反它意味着出现了一个"建在空气上"的孤岛任务——通常是漏了依赖边。

> ⚠️ 判据的精确形式是"**追溯到 `T1-01`**"，不是"追溯到任意 `T1-*`"。后者会让所有 M1 任务自动通过，等于没检查。

这条约束（以及本节的其余约定）由 `scripts/verify-plan.py` 机械校验，见 §6.7。

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
| T3-05 | A 组基线：用 `dsh-eval-harness` 在 `eval-baseline` profile 上跑（`EVAL.md` §3.3） | `eval/runs/a-v1/` | `eval_run(cases_dir="cases", profile="eval-baseline", trials=3)` | 产出基线报告 | T3-00, T3-02a | 2h |
| T3-06 | B 组：在 `eval-coderag` profile 上跑，产出对照报告 | `docs/eval-report-m3.md` | `eval_run(..., profile="eval-coderag", trials=3)` | 报告含**分层指标 + 归因分布 + 逐条 diff** | T3-04d, T3-05 | 2h |
| **T3-07** | **决策门 M3-DECIDE**：按 `EVAL.md` §2.8 的**精确 R2 条件**裁决（见下） | `docs/adr/ADR-14-semantic-retrieval.md` | 文档含明确结论 + 支撑数据 + 归因分布 | 三条规则之一被明确命中 | T3-06 | 1h |
| T3-08 | （条件）若 T3-07 判定需要：Ollama + `bge-m3`，实现 embedding 生成与缓存 | `src/dsh_coderag/embed.py` | `python -m pytest -k "embed" -q` | 同一文本两次调用返回相同向量（缓存生效） | T3-07 = R2 | 3h |
| T3-09 | （条件）实现向量存储与暴力余弦检索（numpy，≤10 万 chunk 不引入向量库） | `src/dsh_coderag/searcher.py` | `python -m pytest -k "vector_search" -q` | top-k 与暴力计算一致 | T3-08 | 2h |
| T3-10 | （条件）实现 RRF 融合（k=60，见 §5.3） | `src/dsh_coderag/searcher.py` | `python -m pytest -k "rrf" -q` | 用已知输入验证融合分数 | T3-09 | 1.5h |
| T3-11 | （条件）跑 C 组（混合），与 B 组对比 | `docs/eval-report-m3c.md` | `eval_run(..., profile="eval-coderag-vector")` | 报告含三组对照表 | T3-10 | 2h |
| T3-12 | 回归门禁脚本：L1（pytest）+ L2（`eval_gate`）一键重跑 | `scripts/eval-gate.sh` | `bash scripts/eval-gate.sh` | 退出码 0/1；输出四项指标 + 回归条数 | T3-02b, T3-06 | 1h |

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

### 6.5 任务依赖图（**由脚本生成，请勿手改**）

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
T3-00  ← T2-17
T3-01  ← T2-17
T3-02a  ← T3-01
T3-02b  ← T3-04c
T3-03  ← T3-02a
T3-04  ← T3-03
T3-04b  ← T3-04
T3-04c  ← T3-04
T3-04d  ← T3-03
T3-05  ← T3-00, T3-02a
T3-06  ← T3-04d, T3-05
T3-07  ← T3-06
T3-08  ← T3-07
T3-09  ← T3-08
T3-10  ← T3-09
T3-11  ← T3-10
T3-12  ← T3-02b, T3-06
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
```

### 6.6 进度追踪表

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
| T2-01 | 已完成 | `$ python -m pytest tests/test_parser.py -q`<br>`......................                                                   [100%]`<br>（退出码 0；22 个用例通过。其中 4 例对 python/c/cpp/typescript 四种 grammar 做实际解析，断言 root 节点分别为 module / translation_unit / translation_unit / program 且 `has_error` 为 False；1 例断言 `EXTENSION_LANGUAGES` 覆盖 `walker.CODE_EXTENSIONS` 全部 7 个后缀） | `ea49999` | 新增 `parser.py`：扩展名→grammar 名映射 + `get_language`/`get_parser`；`pyproject.toml` 钉 `tree-sitter-language-pack>=0.13,<0.14`（原未钉版本装到 1.20.0，实际运行时需联网从 GitHub 下载 grammar，本机实测 `available_languages()==0`、`get_language('python')` 报 DownloadError，离线不可用） | |
| T2-02 | 已完成 | `$ python -m pytest tests/test_chunker_decl.py -q`<br>`................                                                         [100%]`<br>（退出码 0；16 个用例通过。其中 4 个语言 fixture 各有一例断言**完整 chunk 列表**（kind/name/start/end）与人工标注逐条一致：sample.py 5 块（4 声明）/ sample.c 3 块（2 声明）/ sample.cpp 4 块（3 声明）/ sample.ts 4 块（2 声明）；另含 2 条 Hypothesis 性质测试：覆盖全文、区间不重叠） | `818ec58` | 新增 4 语言 fixture `tests/fixtures/decl/*`、`decl_repo` fixture 与 `tests/test_chunker_decl.py`；重写 `tests/test_chunker.py`（朴素定长切分被声明感知替换，仅对无 grammar 语言保留非重叠定长 fallback）；chunker.py 按 tree-sitter 声明边界切分，并对声明外非空行补 gap chunk，保证覆盖全文且不重叠 |
| T2-03 | 已完成 | `$ python -m pytest -k "oversized" -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过。1000 行函数切成 5 片，命名 `big_function#part/1..5`，每片 ≤200 行、连续覆盖 [1,1000] 且区间不重叠；`max_chunk_lines` 可覆盖；小声明不加后缀） | `6e9c2fb` | 新增 `tests/fixtures/oversized/big.py`（1000 行）与 `tests/test_chunker_oversized.py`；chunker.py 增加 `MAX_CHUNK_LINES=200`，按 body 直接子语句/注释边界二次切分；`pyproject.toml` 钉 `tree-sitter>=0.25.2,<0.26`（0.26.0 与 language-pack 0.13 不兼容，释放大 Tree 时段错误） | |
| T2-04 | 已完成 | `$ python -m pytest -k "module_header or fallback" -q`<br>`.......                                                                  [100%]`<br>（退出码 0；7 个用例通过：3 条 module header（领先区块标记 `symbol_kind="module"`、上限 40 行、文件以声明开头时无 header）+ 4 条 fallback（按空行分段、`low_confidence=true`、覆盖全文、不重叠）） | `1ca177a` | chunker.py 新增 `MODULE_HEADER_LINES=40` 与 `_module_header`；L4 fallback 改为按空行分段并统一标记 `low_confidence`（超 200 行段落再按窗口切分）；移除旧定长 fallback 常量 | |
| T2-05 | 已完成 | `$ python -m pytest -k "contextual_prefix" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：每个 chunk 文本以 `// file: ...  |  symbol: ...  |  lines M-N` 前缀开头、前缀进入 `chunks.text` 与 `chunks_fts.text_bigram`、渲染时前缀被剥离且代码正文只出现一次、非前缀注释不误伤） | `9fc358a` | chunker.py 为每个 chunk 拼接 §5.1 上下文前缀；render.py 新增 `strip_context_prefix`，输出前剥离（位置信息已由 `── path:lines [symbol] (chunk N)` 单独成行，避免重复、不污染代码正文）；覆盖度/属性测试改为先剥前缀再比对 | |
| T2-06 | 已完成 | `$ python -m pytest tests/test_security.py -q`<br>`........                                                                 [100%]`<br>（退出码 0；8 个用例通过：`.env` / `id_rsa` / `credentials.py` / `.gnupg/settings.py` / `config.py`（含 `AKIA...`）均未进入 `chunks`；`ignored_dir/`（`.coderagignore`）与运行时 `.gitignore` 目录被排除；反向用例 `normal.py`、`env_reader.py`（`os.environ`）正常入库） | `72ab575` | 新增 `sanitize.py`（第 1 层文件名/路径黑名单 + 第 3 层内容正则，只返回模式名、不返回或记录内容）；重写 `walker.py` 接入 pathspec（先 `.gitignore` 后 `.coderagignore`，`GitIgnoreSpec`）；`indexer.py` 写库前对每个 chunk 调 `scan_secret`，命中即丢弃，整文件全 redact 时不写 `files` 行；新增 `tests/fixtures/secrets/`（全假凭据）与 `tests/test_security.py` | |
| T2-07 | 已完成 | `$ python -m pytest -k "skip_report" -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过：`walk_with_report` 把 `credentials.py`/`.gnupg/settings.py` 计为 `secret_file`、`ignored_dir/skipped.py` 计为 `gitignored`；`search()` 附带 SkipReport 并渲染出 `skipped: 3 (gitignored: 1, secret_file: 2)`；`index_status` JSON 含 `skipped: {count, reasons}`；零跳过时输出 `skipped: 0`） | `7a43bf3` | types.py 加 `SkipReport`；walker 加 `walk_with_report`（`walk` 返回类型不变）；searcher 检索时基于当前 walk 附加 skipped；render.py 新增 `_format_skip_report` 与 `render_status(skipped=...)`；server.py 的 `index_status` 返回 skipped JSON；同步 §3.5 返回格式示例。按方案 A 未做 schema 持久化，redacted chunk 数留待 T2-09/T2-16 | |
| T2-08 | 已完成 | `$ python -m pytest -k "incremental" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：二次索引 `files`/`chunks` 的 id 与 content_hash 全部不变、`summary.chunks == 0`；monkeypatch 证明内容未变的文件不再调用 `chunk_text`；改动过的文件被重建；一个文件变更时其它文件 id 不变；文件从正常变为含密钥时旧行被清除） | `bf3d043` | indexer.py：`_index_file` 先算 sha256 与 `files.content_hash` 比对，命中则整文件跳过；新增 `_delete_file_rows` 统一清理；全 redact 分支也清旧行 | |
| T2-09 | 已完成 | `$ python -m pytest -k "add_modify_delete" -q`<br>`...                                                                      [100%]`<br>（退出码 0；3 个用例分别验证 chunks 表状态：新增文件后出现其 chunk；修改文件后旧 chunk 被替换（旧符号消失、新符号出现）且 `files` 仍为 1 行；删除文件后其 `chunks`/`files`/`chunks_fts` 行级联清除） | `ea40021` | indexer.py：`index_sync` 收集本次 walk 的路径集合，新增 `_remove_missing_files` 在一个事务内级联删除工作区已不存在的文件；新增/修改沿用 T2-08 的每文件事务（先删后插） | |
| T2-10 | 已完成 | `$ python -m pytest -k "adaptive_concurrency" -q`<br>`.........                                                                [100%]`<br>（退出码 0；9 个用例通过：`adaptive_workers(cpu_count=1/4/16)` 得 1/3/8，内存上限把 8 压到 2/1；`next_batch_size` 慢批减半、快批翻倍、中间不变且封顶 512；`IndexConfig(batch_size=7, max_workers=2)` 覆盖生效；env `CODERAG_BATCH_SIZE`/`CODERAG_MAX_WORKERS` 生效；`index_sync(config=...)` 跑通） | `ae0083a` | config.py 新增 `adaptive_workers`/`next_batch_size` 与常量，`IndexConfig` 增可选 `batch_size`/`max_workers` 及 `workers`/`start_batch_size` 属性；indexer.py 重构为「并行 prepare（读+hash+chunk+密钥扫描）→ 自适应批量串行写库」；本机 workers=8，50 文件并发索引实测 files/chunks 均 50，全量套件重复 5 次稳定 | |
| T2-11 | 已完成 | `$ python -m pytest -k "too_many_files" -q`<br>`....                                                                     [100%]`<br>（退出码 0；4 个用例通过：3 个可索引文件 + `max_files=2` 时抛 `TooManyFilesError`，`actual_count==3`、`max_files==2`、`code==INDEX_TOO_MANY_FILES`，`payload` 为 `{code, actual_count, max_files, message}`；恰好等于上限不报错；非代码扩展名与密钥文件不计入上限；`index_sync` 超限时在写任何 `files` 行前失败，DB files 计数为 0，绝不静默截断） | `c2d7300` | walker.py 新增 `TooManyFilesError(actual_count, max_files)`（带 `code` 与 `payload`）及 `walk`/`walk_with_report` 的 `max_files` 参数，走完全部文件后超限即抛；indexer.py 把 `IndexConfig.max_files` 传给 walk（无 config 时用默认 20000）；异常 message 含实际数量，异步索引失败时经 `index_status` 可见 | |
| T2-12 | 已完成 | `$ python -m pytest -k "cancel" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：`TaskManager.start` 为每个任务建 `threading.Event` 并把 `should_cancel` 传给 worker，`cancel()` 置位并写 `cancelled`；worker 取消后不再 `mark_ready`（状态保持 cancelled）；`index_sync(should_cancel=...)` 在每个文件/批次边界轮询，取消后不写库、不 mark ready；取消前已提交的批次保留） | `366dc8d` | taskman.py 新增 `IndexWorker` Protocol 与每任务 `threading.Event`，`cancel` 置位事件，`_run_worker` 取消后跳过 mark_ready 并容忍 `TaskStateError`；indexer.py `index_sync` 新增关键字参数 `should_cancel`，prepare 与写库循环在每个文件边界轮询 | |
| T2-13 | 已完成 | `$ python -m pytest tests/test_outline.py -q`<br>`......                                                                   [100%]`<br>（退出码 0；6 个用例通过：`outline(sample.py)` 返回 4 个顶层符号 + `class Pool` 下的 `method acquire`（行号 4-5 / 8-9 / 12-14 / 17-19 / 18-19）；`max_depth=1` 不展开方法；未知语言返回空；路径越界抛 `ValueError`；MCP `code_outline` 精确渲染符号树；缺失文件返回 `status: empty`） | `7e28014` | searcher.py 新增 `OutlineSymbol` 与 `outline()`（复用 chunker 的 `DECLARATION_KINDS`/`WRAPPER_NODE_TYPES`，按 body 递归，类内函数标 `method`，wrapper 取外层 span）；server.py 用真实实现替换 T1-11 占位并渲染缩进树；§3.5 增加 code_outline 返回示例；更新原占位断言 | |
| T2-14 | 已完成 | `$ python -m pytest -k "order_preserving" -q`<br>`...                                                                      [100%]`<br>（退出码 0；3 个用例通过：`b.py` 命中次数远多于 `a.py`（bm25 更优），但输出仍为 `a.py` → `b.py` 且 `hits[0].score > hits[1].score`；同一文件内多 chunk 按 `start_line` 升序；跨文件按 `(path, start_line)` 稳定排序） | `dfdc0b1` | searcher.py `_search` 的 SQL 加 `c.id` 作为 bm25 并列时的唯一 tiebreaker，取 top-k 后对 hits 按 `(path, start_line)` 重排（ADR-05：选按分数、排按位置） | |
| T2-15 | 已完成 | `$ python -m pytest -k "token_budget" -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：5 条约 100 字符的命中在 `max_tokens=20` 下只保留 1 条并报 `omitted=4`；大预算全保留；`render_search_result` 末尾输出 `[4 more hits omitted by token budget; raise max_tokens to see them]`；`omitted=1` 用单数；极小预算仍至少保留 1 条） | `59e5fe3` | searcher.py `search` 新增 `max_tokens`（默认 4000），按输出顺序累加 `len(text)/3.5` 裁剪并记录 `omitted`；types.py `SearchResult` 增 `omitted` 字段；render.py 改从 `result.omitted` 生成省略提示；server.py 把 MCP `max_tokens` 传入 search | |
| T2-16 | 已完成 | `$ python -m pytest tests/test_log.py -q`<br>`.....                                                                    [100%]`<br>（退出码 0；5 个用例通过：`log_event` 每行一个合法 JSON 且含 `ts/level/event/task_id/duration_ms`，stdout 保持为空；索引后 stderr 依次输出 `index_start`/`index_done` 两条合法 JSON；`.coderag/last-index.json` 含 `root/task_id/files/chunks/skipped{count,reasons}/redacted{count}/duration_ms{walk,prepare,write,cleanup,total}`；skipped/redacted 计数正确） | `7f3fb79` | 新增 `log.py`（JSON-Lines 到 stderr + `build_audit_record` + `write_audit_dump`，绝不写 stdout）；indexer.py 在索引起止发日志、按阶段计时、写 `last-index.json`；`_PreparedFile.redacted` 由 bool 改为计数 | |
| T2-17 | 已完成 | 人工验收（DSH 参考源码 `0d1f50007f` 的复制，3063 个 `.ts`）：`$ dsh-coderag index <corpus>`<br>`indexed 3074 files, 51230 chunks`（墙钟 **3.42 s**；audit total 3299.0 ms = walk 188.6 / prepare 2066.5 / write 1034.3 / cleanup 1.2；skipped 3 / redacted 2；二次增量 **0 chunk / 0.47 s**）<br>5 个真实问题的标识符改写查询 **5/5 命中正确文件**（Q1 `packages/mcp/mcp-client/src/index.ts` 名次 4；Q2 `.../mcp-client/src/transport.ts` 1；Q3 `packages/sandbox/sandbox-policy/src/session-mode.ts` 2；Q4 `packages/preset/persona/src/index.ts` 1；Q5 `packages/spill/spill-local/src/store.ts` 1）；纯中文原问句 5/5 返回 `empty` | `f47fe4d` | 产出 `docs/m2-findings.md`（索引耗时分解、5 问结果、7 条观察、2 个依赖阻断记录、已知限制）；为遵守 RL-01/S-03 用 rsync 复制目录而非原地索引；发现「中文原问句 AND-of-bigrams 全 empty」与「测试/实验文件在 BM25 中压过实现文件」两项 M2 质量缺口，指向 T2-19/T3 归因 | |
| … | | | | |

---

### 6.7 覆盖矩阵（**完备性的可验证形式**）

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
| ADR-05 | T2-14 | 检索结果按源码顺序输出 |
| ADR-06 | T1-13 | 索引未就绪返回结构化状态；`RL-06` 是它的红线形式 |
| ADR-07 | T1-06, T2-19 | 中文 bigram 预处理 + 精度/召回双模式 |
| ADR-08 | T2-06 | 三层安全过滤（密钥黑名单 / 忽略规则 / 内容扫描） |
| ADR-09 | T2-09 | 索引状态与忽略规则一并持久化 |
| ADR-10 | T2-11 | 超过文件数上限显式失败并报实际数量 |
| ADR-11 | T2-10 | 并发度与批大小自适应，不硬编码 |
| ADR-12 | T3-04 | 指标用 `Success@k`，不用 nDCG |
| ADR-13 | T2-19 | 标点/短符号查询路由到 `grep`，不做全表 `LIKE` |
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
| RL-08 | T2-11 | 禁止静默截断 |
| RL-09 | T1-13 | 禁止让异常冒泡成 `isError` |
| RL-10 | T3-07 | 禁止在决策门前引入向量依赖 |
| RL-11 | *全局* | 提交纪律：工作区干净、一任务一提交 |
| S1 | T3-04, T3-06 | 成功标准：检索本身有效（Success@5 ≥ 0.80） |
| S2 | T3-04, T3-06 | 成功标准：排序质量合格（MRR ≥ 0.60） |
| S3 | T3-05, T3-06, T3-07 | 成功标准：端到端有提升（≥10 个百分点） |
| S4 | T2-15, T3-04 | 成功标准：token 中位数 ≤ 4000 |
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
| **C** | `C-DEP` / `C-CYCLE` / `C1` / `C3` / `C4` / `C5` | 依赖存在性、无环、重复 ID、自依赖、依赖格式、§6.5 图与表同步 |
| **D** | `D1`–`D3` | 唯一根 = `T1-01`；所有任务可达根；根自身无依赖 |
| **E** | `E1`–`E4` | `TESTING.md` 必测清单 M1–M10 的任务映射、`AGENTS.md` §5.2 的 T-01–T-08 |
| **F** | `F4` | 各类数量的下限阈值（防止"解析为 0 也算通过"） |

**`test-verify-plan.py` 是它的可信度证明**：把四份文档复制到临时目录，逐个施加 19 种人为破坏（删矩阵行、重复任务 ID、自依赖、孤立 T1、EVAL 幽灵 ID、图漂移、制造环…），断言校验器**必须返回非零**。**全部 19 个变异均被检出**才算通过。

> **为什么需要变异测试**：一个只会说"通过"的校验器毫无价值。上面的 28 项绿灯，只有在证明它们**在坏数据上会变红**之后才有意义。
>
> 更新计划后请**两个都跑**。改动任务表后如果 `C5` 失败，用 `python3 scripts/verify-plan.py . --emit-graph` 重新生成 §6.5。



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
