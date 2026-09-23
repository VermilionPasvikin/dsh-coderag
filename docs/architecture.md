# dsh-coderag 架构

> **定位**：这份文档描述**已经构建出来的实现**——模块边界、数据流、数据模型与运行形态。
> 设计意图与取舍理由在 [`PROJECT.md`](../PROJECT.md) §3（架构设计）与 §3.7（ADR 表）；
> 安装与打包见 [`docs/m4-bundle.md`](m4-bundle.md) 与 [`docs/m4-install-verification.md`](m4-install-verification.md)。
> 两者冲突时以**代码**为准，并请提 issue/改文档。
>
> 实现版本：`1.0.0`｜Python `>=3.10,<3.13`｜验证环境 macOS + DSH `0.1.5-rc.1`。

---

## 1. 运行时形态

引擎是一个普通 Python 包 `dsh_coderag`（`src/` 布局），有**两个**入口，服务两个不同的消费者：

| 入口 | 命令 | 消费者 | 位置 |
|---|---|---|---|
| MCP 服务器 | `python -c 'import dsh_coderag.server as s; s.run()'` | DSH（内置包 `@deepseek-ai/dsh-mcp-client`） | `src/dsh_coderag/server.py` |
| CLI | `dsh-coderag index\|search` | 人（调试/自检） | `src/dsh_coderag/__main__.py` |

DSH 侧不加载任何 JavaScript：仓库根的 `cordis.patch.yml` 只 `insert` 一条 `mcp-coderag` 行，
引用内置包 `@deepseek-ai/dsh-mcp-client`，由后者以 **stdio** 拉起上面那条 Python 命令。
`package.json` 的 `dsh.bundle.patch` 指向同一个文件——**同一个 patch 既是本地开发 overlay，
也是分发的 bundle patch**。

传给子进程的配置只有一个通道：**`config.env`**。stdio 子进程的环境会被 DSH 清洗
（匹配 `/KEY|PASSWORD|SECRET|TOKEN/i` 的变量与**所有** `DSH_*` 都会被删除），所以
`CODERAG_ROOT` 必须在 patch 的 `config.env` 里显式给（默认 `process.cwd()`）；
`CODERAG_PYTHON` 在 **DSH 进程内**求值（`!!js`），可由启动 shell 覆盖。

**为什么用 `-c` 而不是 `-m`**：子进程的 cwd 是**被索引的工作区**，而 `python -m` 会在我们的代码
运行之前先导入 `runpy`；工作区里一个叫 `types.py` / `token.py` 的文件会遮蔽 `runpy` 依赖的模块，
让服务器在解释器启动阶段就死掉。`-c` 绕开 `runpy`；`dsh_coderag/__init__.py` 再在**任何可被遮蔽的
导入之前**把 cwd 从 `sys.path` 移除（引擎只把用户文件当文本读，从不 import 它们）。

## 2. 模块与依赖方向

每个模块的顶部 docstring 都写明「负责什么、不负责什么」（`AGENTS.md` D-01），下表是它的汇总：

| 模块 | 文件 | 职责 | 不负责 |
|---|---|---|---|
| `config` | `config.py` | 环境变量读取与校验、自适应并发/批大小推导 | 不猜默认值（缺失必填项报错） |
| `types` | `types.py` | 跨模块数据类与两个稳定枚举（含错误码） | 不含行为 |
| `parser` | `parser.py` | 扩展名 → tree-sitter grammar，加载 grammar | 不解析语法树、不遍历 |
| `text` | `text.py` | CJK bigram 预转换（索引与查询两侧共用） | 不做分词决策 |
| `sanitize` | `sanitize.py` | 第 1 层文件名/路径黑名单 + 第 3 层内容正则 | 不遍历、不读文件、不写库 |
| `sqlite_caps` | `sqlite_caps.py` | 运行时探测 SQLite FTS5 能力 | 不打开索引库 |
| `walker` | `walker.py` | 遍历工作区、应用忽略规则与密钥黑名单、上报 skip 原因与文件数上限 | 不读文件内容 |
| `chunker` | `chunker.py` | 声明感知分块、超大声明切片、module 头、无 grammar 降级、上下文前缀 | 不写数据库 |
| `indexer` | `indexer.py` | schema、连接 pragma、增量写入、批量写库、内容级 redact、审计转储 | 不做检索 |
| `searcher` | `searcher.py` | FTS5 查询构造、bm25 排序、顺序保持、预算裁剪、标点路由、`code_outline`；**可选后端启用时**再做向量召回与 RRF 融合（k=60） | 不做索引；**关闭时不得 import `numpy`**（`RL-10`） |
| `embed` | `embed.py` | **可选后端（默认关闭）**：调用本机 Ollama 生成/缓存 embedding，读写 `<root>/.coderag/vectors/{embeddings.npy,manifest.json}` | 不排序、不融合（融合在 `searcher`）；不参与 BM25 路径；未启用时整个模块不得成为导入或启动的阻塞点 |
| `taskman` | `taskman.py` | 任务 id 与 `pending/running/ready/failed/cancelled` 状态机（落 `index_runs` 表） | 不执行索引本身 |
| `render` | `render.py` | 把 search/status 结果渲染成模型可见文本（字节稳定契约） | 不检索、不排序、不裁剪 |
| `log` | `log.py` | stderr 上的 JSON-Lines 日志 + `.coderag/last-index.json` 审计 | 不写 stdout、不索引/检索 |
| `server` | `server.py` | MCP 协议、4 个工具 schema、参数校验、dispatch | 不含检索逻辑（薄层） |
| `cli` | `__main__.py` | 命令行入口（`index` / `search`） | 非模型接口 |
| `eval` | `eval/` | L1 评测（tasks/runner/metrics/attribute/report）、L2 A/B runner、门禁 CLI | **不参与生产检索路径**、不调模型（除 `ab.py` 拉起 headless DSH） |

**依赖方向（禁止反向依赖）**：

```
server  ──► {taskman, searcher, indexer, render, walker, sqlite_caps, config, types}
cli     ──► {indexer, searcher, types}
taskman ──► {indexer, types}
searcher──► {indexer, walker, chunker, parser, text, sqlite_caps, config, types}
indexer ──► {walker, chunker, sanitize, text, log, sqlite_caps, config, types}
walker  ──► {sanitize, config, types}
chunker ──► {parser, types}
render  ──► types
eval    ──► {searcher, indexer, walker, text, config, types}
searcher ──► embed      （**仅在可选后端启用时**；延迟导入，关闭时这条边不存在）
            （`runner` 复用生产 `searcher`；`attribute` 另外读 `walker`/`indexer`/`text` 做归因；
              markdown 渲染是 eval 自己的，不经过 render）
```

叶子模块：`config` / `types` / `parser` / `text` / `sanitize` / `sqlite_caps` / `log`，
不依赖任何其它 `dsh_coderag` 模块。

## 3. 索引数据流

```
walker.walk_with_report(root, max_files, max_file_bytes)
  ├─ 第 1 层：sanitize 的密钥文件名/路径黑名单        → skipped.reasons["secret_file"]
  ├─ 第 2 层：.gitignore → .coderagignore（pathspec） → skipped.reasons["gitignored"]
  ├─ stat 大小 > max_file_bytes（读内容之前）          → skipped.reasons["too_large"]
  └─ 超过 max_files → 抛 TooManyFilesError(actual, max)，报告实际数量，绝不静默截断
        ↓  (排序后的代码文件列表 + SkipReport)
indexer.index_sync（线程池并行 prepare，串行批量写库）
  ├─ prepare（不碰数据库）：读文本 → sha256 → chunker.chunk_text → 每个 chunk 过 sanitize.scan_secret
  ├─ 增量：content_hash 与 files.content_hash 相同 → 整文件跳过（不重新分块）
  ├─ 写库：每文件一个事务，先删旧行再插新行（files / chunks / chunks_fts）
  ├─ 全 redact 的文件：不写 files 行，并清掉旧行
  └─ 收尾：删除工作区里已不存在的文件（级联清 chunks / chunks_fts）
        ↓
taskman（异步路径）：start() 立刻返回 taskId，后台线程推进状态；失败写 failed
        ↓
log：stderr 上 index_start / index_done（JSON-Lines）+ .coderag/last-index.json 审计
```

**自适应**：并发度与批大小从 `os.cpu_count()` / 可用内存 / 前几批耗时推导，也可由
`IndexConfig` 或 `CODERAG_MAX_WORKERS` / `CODERAG_BATCH_SIZE` 覆盖——**没有硬编码常量**
（`AGENTS.md` RL-07 / C8）。

**取消**：`index_sync(should_cancel=...)` 在每个文件与每个批次边界轮询；取消后不再写库、
不标记 `ready`（`taskman` 用每任务一个 `threading.Event`）。

## 4. 检索数据流

```
searcher.search(root, query, k=5, path=None, max_tokens=4000)
  ├─ 打开索引；FTS5 不可用 → status=error + code=FTS5_UNAVAILABLE + 可操作 hint
  ├─ 标点路由：去掉标点后没有可检索词元 → status=empty + 「改用 grep」的提示（ADR-13）
  ├─ text.to_bigrams(query) —— 与索引侧同一函数，两侧必须对称
  ├─ 第 1 级 精度：所有词元 AND
  ├─ 第 2 级 召回：仅标识符的 OR
  ├─ 第 3 级 召回：含 CJK bigram 的 OR（中文 bigram 精度低，放最后，避免压掉真正的代码）
  ├─ 排序（写在 SQL 的 ORDER BY 里，让 LIMIT 看到最终序）：
  │     ① 非测试路径优先（tests/ / __tests__/ / *.spec.* / *.test.*）
  │     ② bm25，且 symbol_name 完全匹配减 SYMBOL_MATCH_BOOST
  │     ③ c.id 作为确定性 tiebreak
  ├─ 取 top-k 后按 (path, start_line) 重排 —— **选按分数、排按位置**（ADR-05）
  ├─ path 参数：resolve 后必须仍在工作区内，否则 SEARCH_INVALID_QUERY
  └─ token 预算：按输出顺序累加裁剪，记录 omitted
        ↓
render.render_search_result → 模型可见文本（status / query / scanned / hits / skipped / omitted）
```

零命中或索引未就绪**永远不是空列表 `[]`**：返回带 `status` 的结构化结果
（`indexing` / `empty` / `error`），避免模型把"没有结果"读成"代码里不存在"（RL-06）。

`code_outline` 复用 `chunker` 的声明类别与 wrapper 节点类型，递归输出符号树（类内函数标
`method`），`max_depth` 控制展开。

## 5. 数据模型

索引固定落在 `<工作区>/.coderag/index.sqlite3`（`S-03`），连接开 `journal_mode = WAL` 与
`foreign_keys = ON`。5 张表：

| 表 | 作用 | 关键列 |
|---|---|---|
| `files` | 每个入库文件一行 | `path`（工作区相对、正斜杠、UNIQUE）、`size`、`mtime_ns`、`content_hash`、`lang` |
| `chunks` | 每个 chunk 一行 | `file_id`（级联删除）、`seq`、`start_line`、`end_line`、`symbol_kind`、`symbol_name`、`text`、`UNIQUE (file_id, seq)` |
| `chunks_fts` | FTS5 虚拟表，`tokenize = 'unicode61'` | `text_bigram`（索引列）、`symbol`、`path`、`chunk_id`/`file_id`（UNINDEXED） |
| `index_runs` | 异步任务状态机 | `task_id`、`state`、`total_files`/`done_files`、`total_chunks`/`done_chunks`、`message` |
| `workspace_index` | 工作区级元数据 | `root`、`db_schema`、`ready`、`last_task_id` |

路径在所有入库点都由 `Path.as_posix()` 转成正斜杠的工作区相对路径
（`walker.py` / `indexer.py` / `chunker.py` / `searcher.py` 各一处入口）。

## 6. MCP 工具契约

工具集**固定 4 个，不动态增删**（RL-05）。模型侧看到的名称带 `mcp__coderag__` 前缀。

| 工具 | 参数 | 行为 |
|---|---|---|
| `code_search` | `query`（必填）、`path`、`limit`（默认 5，上限 50）、`max_tokens`（默认 4000） | 检索，返回文件:行号 + 符号 |
| `code_outline` | `path`（必填）、`max_depth`（默认 2） | 单文件符号大纲 |
| `code_index` | `path`、`force` | **立刻**返回 `taskId`，后台索引（E-01：工具调用默认 60s 超时） |
| `index_status` | `task_id`（可省） | 任务或工作区索引状态，含 `skipped` 计数与原因 |

工具描述面向**模型**编写（`AGENTS.md` D-02）：不含 UI、传输层、实现机制词汇。
所有异常都在 `server._dispatch` 里转成带 `status`/`code` 的结构化返回值，**不让内部异常冒泡成
MCP 的 `isError`**（RL-09）。

## 7. 安全模型

索引入口三层过滤，**按顺序、缺一不可**：

1. **内置黑名单**（`sanitize.py`，无关闭开关）：`.env` / `.env.*` / `*.pem` / `*.key` / `*.p12` /
   `*.pfx` / `id_rsa*` / `id_ed25519*` / `.npmrc` / `.pypirc` / `.netrc` / `.git-credentials` /
   `credentials*` / `*_rsa` / `*_ed25519`；路径片段 `/.ssh/`、`/.aws/`、`/.gnupg/`、`/.kube/`、
   `/.docker/config.json`
2. **项目忽略规则**：`.gitignore` → `.coderagignore`（后者优先），用 `pathspec`，不自造语义
3. **内容级正则**：私钥头、`AKIA…`、`sk-…`、`ghp_…`、`xox…`——命中的 chunk 不入库

三条硬规则：命中第 3 层时**只记路径与模式名，绝不记匹配到的内容**；日志里**绝不打印**被过滤的
文本（S-05）；过滤结果必须**对模型可见**（`skipped: {count, reasons}`），否则模型会以为代码不存在
（§4.2）。

其余：默认不联网、不采集遥测（S-01/S-02）；索引进工作区、不写工作区之外（S-03）；
索引目录被本仓库的 `.gitignore` 模板排除（S-04）。

## 8. 异步、并发与上限

| 机制 | 位置 | 规则 |
|---|---|---|
| 异步索引 | `server._code_index` → `taskman.start` | 立刻返回 `taskId`，后台线程跑 `index_sync`（E-01） |
| 状态机 | `taskman.py` + `index_runs` 表 | `pending → running → ready / failed / cancelled`；非法流转抛 `TaskStateError`；状态随任务落库（ADR-09） |
| 并发/批大小 | `config.adaptive_workers` / `next_batch_size` | 由 CPU 与内存推导，可配置覆盖；慢批减半、快批翻倍（RL-07） |
| 文件数上限 | `walker.TooManyFilesError` | 超限**显式失败**并报实际数量（RL-08） |
| 单文件大小 | `walker.walk_with_report` | 超过 `max_file_bytes`（默认 1 MiB）在读内容前跳过并计入 `too_large` |
| 取消 | `taskman.cancel` + `index_sync(should_cancel=)` | 边界轮询，取消后不写库、不标 ready |
| 检索预算 | `searcher.search(max_tokens=)` | 默认 4000，裁剪并报告 `omitted` |

## 9. 可观测性

- **stdout 只属于协议**（RL-04）：日志一律走 stderr 的 JSON-Lines（`log.log_event`），
  每行含 `ts` / `level` / `event` / `task_id` / `duration_ms`。
- **审计转储**：每次索引写 `<root>/.coderag/last-index.json`，含 `root` / `task_id` / `files` /
  `chunks` / `skipped{count,reasons}` / `redacted{count}` / 分阶段耗时（walk / prepare / write /
  cleanup / total）。
- 日志里可以有绝对路径（便于排查），但**绝不出现代码内容**（S-05）。

## 10. 评测与测试分层

| 层 | 位置 | 说明 |
|---|---|---|
| L1 检索质量 | `eval/tasks.py` / `runner.py` / `metrics.py` / `attribute.py` / `report.py` | 30 条 golden 集；`run_eval` 直接走**生产** `searcher.search`（k=5）；`Success@k` / `MRR` / token 中位数 / Wilson 区间；逐 query diff 与 `golden_version` 门禁；A1–A7 失败归因 |
| L2 端到端 | `eval/ab.py` + `scripts/ab_eval.py` | 每个 attempt 起一个 headless DSH，读会话日志判断言；`pass@k` / `pass^k`；A/B 门禁看回归条数 |
| L3 一键门禁 | `scripts/eval-gate.sh` | pytest → L1 指标 + 逐 query 门禁 → L2 门禁；退出码 `0/1/2` |
| 单元/性质测试 | `tests/` | 离线、不需要 API key（`TESTING.md` T-02）；安全测试 `tests/test_security.py` 是 M2 的强制门禁 |

评测**不改生产路径**：`eval` 只调用 `searcher.search`，报告写到 `eval/runs/`。

## 11. 不做什么（非目标）

- **默认路径不含向量检索**：默认安装没有任何 embedding / 向量库依赖——这是 `RL-10` 的硬要求，
  不是"暂时没做"。R2 的事实判断仍成立（纯词法够不到"零词法重叠"的中文自然语言），
  执行先按 [`ADR-15`](adr/ADR-15-defer-semantic-retrieval.md) 推迟，再由
  [`ADR-16`](adr/ADR-16-optional-vector-backend.md) 重启为**可选后端路径**：
  **默认关闭 + opt-in**，未配置时输出与纯 BM25 **逐条一致**（成功标准 `S6`），
  依赖只进可选 extra，索引落在 `<root>/.coderag/vectors/`。
- **不做 prompt 注入**：走 MCP 工具路线；`complete: true` 的 preset 会静默丢弃 system-prompt
  型注入（`AGENTS.md` E-03）。
- **不修改宿主**：不改 DSH 仓库中任何被 git 跟踪的文件（RL-01）；`cordis.patch.yml` 只 `insert`。
- **不新增/删除 MCP 工具**（RL-05）；**不硬编码资源参数**（RL-07）；**不静默截断**（RL-08）。
