# Changelog

本项目的所有重要变更都记录在这里。
格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- **DSH 原生设置页（三个入口，13 个字段）**：bundle 新增一个 JS 双端插件。
  - Host 半侧（`lib/index.js`，ESM）持有 `coderag` 行的 schemastery Config，**13 个字段全部
    `.volatile()`**：`root` / `maxFiles` / `maxFileBytes` / `maxTokens` / `extraExtensions` /
    `semantic` / `semanticBackend` / `semanticUrl` / `semanticModel` / `semanticQueryTimeout` /
    `semanticBatch` / `semanticMaxChunks` / `semanticAllowRemote`。
    保存时 Loader 只提交 volatile 值、**不重挂载设置行**；Host 再把它们映射成 `CODERAG_*`
    合并进既有 `mcp-coderag` 行的 `config.env`。`env` 是 MCP 行的普通字段，因此该行会重挂载、
    Python 子进程以新环境重启。
  - Client 半侧（`lib/client.js`，lazy-CJS ModuleLoader factory，只 external `react` 与
    `react/jsx-runtime`）注册三个原生入口：**`settings.section`（设置 → CodeRAG，主入口）**、
    `plugins.row.config`（key `dsh-coderag#coderag`）与 `plugins.bundle.config`（key
    `dsh-coderag`，bundle 详情页）。后两者不传 form，组件用 `ctx.configForms.get('coderag')`
    + `useSyncExternalStore` 订阅快照。
  - 保存**即时热重载**（本机实测：改 root 后 1.5–2 秒内模型调 `mcp__coderag__index_status`
    返回新 root；改回后同样恢复），页面提示「已保存，MCP 已按新环境热重载」。
  - 同步只碰上述 13 个变量；云端 API key 走 DSH credentials（见下条），不写入 Config / profile patch。
  - 首次保存前，profile 里已有的 `mcp-coderag` env 不会被启动同步清掉（全空设置不同步）。
- **云端 API Key 走 DSH credentials（reference `CODERAG_SEMANTIC_API_KEY`）**：设置页密码框
  保存后立即清空，只显示「已配置（不可查看）」，删除需二次确认；值**不回读、不写 profile patch、
  不进 state/错误/日志**。Host 在同步 MCP 行和启动 admin 子进程时用 `credentials.resolve` 取它；
  key 变更后页面调用 `refresh` 动作让 MCP env 立即更新。
- **Host 运维路由（仅 Web profile）**：`GET /coderag-admin/state`、`POST /coderag-admin/action`
  （`health` / `start-local` / `vectorize` / `stop` / `refresh` / `index` / `remove-vectors`）、
  `GET /coderag-admin/job`；
  全部经过 `connection.requestRejection` 鉴权，响应固定为 `{ok,value}` / `{ok:false,error}`。
  `start-local` detached 启动 `ollama serve` 并轮询 `/api/tags` ≤15 秒；`vectorize` 流式解析
  admin CLI 的 JSON 行，job 存内存，`stop` 杀子进程但保留检查点。
- **设置页新增「建索引」与「删除向量库索引」（`T8-08`）**：建索引调用 admin `index`
  （`index_sync(build_vectors=False)`，即使语义开关打开也不联系 embedding 后端）；代码索引
  缺失时「开始向量化」禁用并提示先建索引（修复直接点击时报
  `no code index … index the workspace before vectorizing` 的入口）；删除向量库只删
  `<root>/.coderag/vectors/`（含检查点与缓存），保留 `.coderag/index.sqlite3`，二次确认，
  没有向量库时是 no-op。
- **设置页运维面板**：云端 Key（状态/保存/删除）、语义后端（本地/云端连通性检查、一键启动本地、
  可关闭错误弹窗）、向量数据库（存在性/模型/维度/chunk 计数/检查点/生成时间、刷新、增量向量化、
  开始/停止、进度条、完成后自动刷新）；有未保存参数改动时提示先保存。
- **Node 测试扩到 69 项**：新增 Host admin 服务（CLI 调用/流式 job/stop/ollama 轮询/密钥 scrub）、
  路由鉴权与 action 分发、浏览器 admin helpers 与面板渲染。
- **`@deepseek-ai/schemastery` 被内联进 Host bundle**：安装后**零运行时 npm 依赖**，
  不触发 pnpm 的 install-script 限制（`E-05`）。
- **`scripts/experiments/` 下的两个可复现探针**：`loader-volatile-probe.mjs`（对 `app.asar`
  实测 Loader 单行更新 / volatile 语义）与 `host-settings-sync-probe.mjs`（用真实 Loader
  跑构建后的 Host 插件、验证设置 → env → 重挂载）。
- **Node 测试**：`tests/plugin/*.test.mjs`（settings 映射、MCP 行同步、表单纯逻辑、
  client 产物与三个 slot 注册的 server-render 测试、bundle 清单/产物契约）。
- **`CODERAG_EXTRA_EXTENSIONS`：让用户自行扩展可索引的文件后缀**（`T6-17`）。内置白名单
  （`.py` / `.c` / `.h` / `.cpp` / `.hpp` / `.ts` / `.js`）保持不变，这个变量**只增不减**：
  逗号或空格分隔、大小写不敏感、可省前导点，例如 `CODERAG_EXTRA_EXTENSIONS=.mxml,.as`。
  含点号的 token、路径分隔符与通配符一律报 `ConfigError`——`Path.suffix` 只取最后一段，
  静默接受会让用户以为生效了。**密钥过滤不受影响**：扩展名闸门在第 1 层黑名单**之前**，
  `.env*` / `*.pem` / `credentials*` 即使把其后缀加进白名单也仍然不入库（`RL-03`）。
  没有对应 tree-sitter grammar 的后缀走 L4 低置信度分块（`low_confidence: true`）。

### 变更

- **`cordis.patch.yml`**：新增 `coderag` 设置行（13 个 `!!js` 默认值）；`mcp-coderag` 行只保留
  解释器与 `CODERAG_SEMANTIC_API_KEY`。原先的 12 个管理型 env 改由设置行
  （`!!js` 读同名 shell 变量作默认值）→ Host 同步提供，避免两份真相互相覆盖。
- **运维面板依赖 `dsh_coderag.admin`**（T7-01）：状态、健康、可恢复向量化都由它提供；
  Host 以私有 0700 cwd + `-c` 启动器调用（去掉 cwd/sys.path[0] 防影子模块）；缺失或失败时
  页面显示可关闭的结构化错误，不影响参数表单本身。
- **README**：新增「运维面板」章节（key/后端/向量库、路由与安全边界）与相应已知限制。
- **超时墙分层收敛（`T8-07`）**：设置页把「语义请求超时」换成「语义查询超时」
  （`semanticQueryTimeout` → `CODERAG_SEMANTIC_QUERY_TIMEOUT`，默认 10 秒）。`CODERAG_SEMANTIC_TIMEOUT`
  不再是设置项，降级为**建索引批次**的高级传输上限（默认 30 → 60 秒，最多重试 2 次）；查询路径改用
  固定的 120 秒后台传输上限，因此旧 profile 里保存过的小值不会再打断冷加载，DSH 的
  `toolCallTimeoutMs` 仍是唯一的外层兜底。

### 修复

- **L1 的 hit@1 / MRR 把源码展示顺序当成检索名次**（`T8-19`）：`SearchResult.hits` 按 ADR-05
  输出源码顺序，评测运行器却直接用它算排名，于是 MRR 量的是「答案文件在路径字母序里排第几」。
  现在 `SearchResult.ranking` 单独携带检索名次（BM25 选择序 / RRF 融合序），运行器用它算
  `rank`/MRR；模型可见输出不变。43 条 L1 重算：BM25 MRR 0.219 → 0.2597（hit@1 8 → 10）、
  云端 0.269 → 0.4671（hit@1 3 → 12），`Success@5` 不变（13/43、31/43）（EVAL.md §2.5）。
- **默认路径的工具采纳（`T8-12`）**：MCP `initialize` 发布 instructions，要求「先 `code_search`、再 `grep`；`grep` 只用于精确串或正则」。13 条默认 C 组的采纳从 `0/13` 提升到 `10/13`、任务成功 `4/13` → `10/13`；详见 `ADR-18`。
- **语义检索的 token 预算按源码顺序裁剪，exact 命中被大文件挤掉**（`T8-09`）：融合已经选中
  `protocol.ts`（融合第 1–2 名），但 4000-token 预算按源码顺序被前面三个大文件吃满，exact 命中
  从未进入模型上下文。现在 `fuse_candidates` 保留融合名次、`_trim_to_budget` 按名次裁剪后再排成
  源码顺序（ADR-05 的"输出按位置"不变）；43 条 L1 上 exact 11/12 → 12/12、总命中 30 → 31，
  crossfile / natural 逐条不变；BM25 默认路径不受影响（ADR-16 §13）。
- **融合把源码顺序当成 BM25 名次**（`T8-10`）：`_search` 选完 top-k 后按源码顺序返回，RRF 于是把
  "第几行"当成"第几名"给词法分。现在 `_search` 返回 BM25 选择顺序，`_apply_semantic` 在关闭、
  失败、无向量命中三条回退路径上恢复源码顺序；融合拿到真实名次，输出仍按源码顺序，BM25 默认
  路径与 2.1.1 逐条一致（ADR-16 §14）。43 条 L1 命中集合不变（31/43、exact 12/12）。
- **admin 子进程可被共享临时目录里的影子模块劫持并读到云端 key**：改为在私有 0700 cwd
  中运行，并使用 `python -c` 启动器（导入前从 `sys.path` 去掉 `''`/cwd）；`status` 不再
  接收 key，只接收 `CODERAG_SEMANTIC_KEY_PRESENT=1` 标记，`health`/`vectorize` 才注入 key。
- **并发 `vectorize()` 可在凭据 await 期间双 spawn/双写**：加入同步 `starting` 占位，
  第二个请求立即拒绝；失败回滚该占位。
- **删除 key 后 MCP 行仍保留旧值**：凭据 provider 明确返回未配置时同步删除
  `CODERAG_SEMANTIC_API_KEY`；只有 provider 不可用/故障才保留旧值。
- **admin 服务无 dispose**：插件卸载时终止 vectorize 子进程并删除私有 cwd；
  `start-local` 的异步 ENOENT 立即失败、相对 root 转绝对路径、`normalizeHealth` 透传 code。
- **旧 `vectorize` 子进程迟到的 close/error 会把新 job 标成 error**：每次运行改用独立
  `handle{child,stopRequested,key}`；close/error 只在 `active === handle` 时生效，
  `stop` 与 5 秒 SIGKILL 兜底也只操作自己的 handle；有 handle 存活时拒绝新任务。
  回归测试覆盖「停止后立刻启动第二个，旧 child 迟到事件不得影响新 job」。
- **设置保存 / Key 保存按钮可能长期停在“保存中…”**：设置写入加 15 秒超时并恢复按钮；
  key 写入成功后先释放 spinner，再等待 Host 的 MCP env refresh。
- **`dsh-coderag index`（CLI）此前完全没有读取可选配置**：`CODERAG_MAX_FILES` /
  `CODERAG_MAX_TOKENS` / `CODERAG_MAX_FILE_BYTES` / `CODERAG_EXTRA_EXTENSIONS` 在 CLI 路径上
  都被忽略（`T6-07` 当时只把配置接进了 MCP 那条路径）。现在 CLI 与 MCP 共用
  `config.load_config_for(root)`，两条路径读同一份配置。
- **开启向量层后中文模糊/疑问查询频繁 `tool call timed out`**（`T8-05`）：查询路径现在只尝试一次、
  先校验配置再加载向量索引、并受 `CODERAG_SEMANTIC_QUERY_TIMEOUT`（默认 10 秒）的墙钟预算约束；
  预算耗尽返回扩展码 `SEMANTIC_TIMEOUT` 并保留 BM25。请求不会被取消——后台继续加载模型，
  同一进程的下一次查询走热路径（冷启动实测 10.32 s → 6.28 s → 0.35 s）。MCP 的 `call_tool`
  改走 `asyncio.to_thread`，一次慢检索不再冻结同一会话里的其它工具调用（`ADR-16` §11）。

## [2.1.1] - 2026-09-30

**只发布在 GitHub**（tag / release，`v2.1.1`）——**不发布到 PyPI，也不发布到 npm**。
**默认路径的检索行为没有变化**：本版本只修一个「配置面在 MCP 路径上不生效」的缺陷。
`2.1.0` 的 README 曾把受影响的 5 个变量**如实**标注为「未生效」，本版本把接线补上、让它们成立。

### 修复

- **可调上限在 MCP 路径上完全不生效**：`CODERAG_MAX_FILES` / `CODERAG_MAX_TOKENS` /
  `CODERAG_MAX_FILE_BYTES` / `CODERAG_BATCH_SIZE` / `CODERAG_MAX_WORKERS` 会被 `config.py`
  读进 `IndexConfig`，但 `server.py` 建索引时把 `index_sync` **裸传**给任务管理器（不带配置），
  检索预算又**硬编码 `4000`**——因此这些上限从未到达真正执行的那条路径。
  修法是新增 `server.py::workspace_config(root)`：把已知的 `root` 填进环境副本再调
  `load_config()`，于是 `build_server(root=...)`（测试与嵌入调用）在**不设 `CODERAG_ROOT`** 时
  也读得到可调变量，而显式设置的值仍然优先、格式错误仍然抛 `ConfigError`。
  它接进**三处**：建索引、`code_search` 的**默认**预算（工具参数 `max_tokens` 仍可逐次覆盖）、
  以及工作区形态 `index_status` 的 `skipped` 统计。
- **`index_status` 的过滤统计与配置一致**：上一处的修复暴露出它重新遍历工作区时用的还是
  **默认上限**，因此 `skipped.count` 会与真实过滤结果不符（违反「过滤必须可见」）。
  现在它按配置的上限统计；超限时返回 `INDEX_TOO_MANY_FILES` + 实际数量，而不是兜底的
  `SEARCH_FAILED`。**`RL-08` 未被放松**：超限仍显式失败，不静默截断。

### 新增

- **3 条走 MCP 工具的测试**（`tests/test_server.py`）：`CODERAG_MAX_FILES` 超限时任务 `failed`
  并报实际数量、`CODERAG_MAX_FILE_BYTES` 把超限文件计入 `skipped.too_large`、不传 `max_tokens`
  时预算取自环境。它们**在修复前会红**（`assert 2 == 1`、命中数未被裁剪），所以这条接线
  不会再静默失效。**注意**：原有的 `T2-11` / `T2-21` 单测此前一直是**全绿**的——它们把
  `IndexConfig` 直接交给 `index_sync`，恰好绕过了没传配置的那条路径。

### 变更

- 版本号 `2.1.0` → `2.1.1`（`pyproject.toml`、`package.json`、`src/dsh_coderag/__init__.py`）。

## [2.1.0] - 2026-09-30

**只发布在 GitHub**（tag / release，`v2.1.0`）——**不发布到 PyPI，也不发布到 npm**；
安装方式仍是「克隆 + 装 Python 包 + `--patch`」（见 [`README.md`](README.md) 的「安装」）。
**默认路径的检索行为没有变化**：`dependencies` 仍是 `mcp` / `tree-sitter` /
`tree-sitter-language-pack` / `pathspec` 四个，**不含 `numpy`**；本版本改的是**入口与平台支持**。

### 新增：Python CLI 成为唯一的跨平台入口

- `dsh-coderag doctor`（探测解释器、按 `pyproject.toml` 的 `requires-python` 校验版本、
  预检 SQLite FTS5、打印可直接复制的 `CODERAG_PYTHON`）与 `dsh-coderag install-deps`
  （`pip install` + 装后自检：FTS5 可用 + 中文 bigram 往返）把原先住在 `scripts/install.sh`
  （239 行）里的安装逻辑收了进来。
- `scripts/install.sh` 与 `scripts/dsh` **退化为薄包装**（38 / 31 行，只做「找到解释器 → 转发」），
  三个平台因此走**同一条代码路径**，而这条路径能被 `pytest` 直接覆盖。
- 包导入不再依赖第三方 wheel：`index_sync` / `search` 改为按需导入（PEP 562），
  所以在**依赖尚未安装**的机器上也能先跑 `doctor` / `install-deps`。
- 失败一律是**结构化 JSON + 退出码**（`0` 成功 / `1` 操作失败 / `2` 环境不可用），不吐 traceback。

### 新增：macOS 与 Windows 的逐平台实测

- **实测平台：macOS 26.4 与 Windows 10（26100，`win_amd64`）**。逐平台证据：
  [`docs/m6-crossplatform-baseline.md`](docs/m6-crossplatform-baseline.md)（依赖 wheel 齐备、
  FTS5、离线 grammar、MCP 子进程可拉起）、
  [`docs/m6-macos-verification.md`](docs/m6-macos-verification.md)、
  [`docs/m6-windows-smoke.md`](docs/m6-windows-smoke.md)。
- 全量测试两平台都通过，且**收集到的用例数相同（572 条）**：Windows `570 passed, 2 skipped`、
  macOS `567 passed, 5 skipped`，差值恰好是 Windows 专用的路径用例。
- **Linux 尚未实测，因此不声称支持。**
- 一处必须并列声明的差异：两平台实测用的 DSH 版本**不同**（macOS `0.1.5-rc.1`、
  Windows `0.2.0-rc.2`），**没有任何一个版本被两平台都跑过**。

### 变更

- 版本号 `2.0.0` → `2.1.0`（`pyproject.toml`、`package.json`、`src/dsh_coderag/__init__.py`）。
- **恢复可选 extra `semantic`（内容只有 `numpy`）**：`T5-15` 移出 2.0.0 范围后 numpy 一度失去声明住所，
  向量测试只能靠手工装 numpy 才跑得动。恢复后的内容与
  [`ADR-16`](docs/adr/ADR-16-optional-vector-backend.md) §3.2 冻结的逐字一致，而
  `dependencies` / bundle tarball / `install.sh` 默认路径 / README 安装前置条件**一律不动**（`RL-10`）。
  可选路径目前的安装入口是 `pip install -e ".[semantic]"`；`ADR-16` §3.2 的
  `CODERAG_WITH_SEMANTIC` 安装开关**仍未实现**。
- `wilson_interval` 在 `0/n` 与 `n/n` 两个精确端点改为显式钉住，不再报出 `2.8e-17` 这类浮点残差。

### 修复

- `scripts/dsh` / `scripts/install.sh` 的 `CONDA_PREFIX` 分支原先只检查可执行位，
  一个**已激活但不可用**的 conda 环境会被导出成 `CODERAG_PYTHON`，MCP 子进程随之起不来；
  现在每个候选都必须通过「真的能跑」校验（`-c ''`）。
- Windows 上 `tests/test_walker.py` 的路径断言与 `tests/test_dsh_script.py` 的解释器断言
  改为按**平台无关的规范化路径**比较（**不是**放宽断言）。

## [2.0.0] - 2026-09-25

**只发布在 GitHub**（tag / release，`v2.0.0`）——**不发布到 PyPI，也不发布到 npm**，
`pip install dsh-coderag` 与 `npm i dsh-coderag` 都不可用；安装方式仍是「克隆 + 装 Python 包 + `--patch`」。
**默认安装与 `1.0.0` 逐条一致**（成功标准 `S6`：30 条 query 逐条 diff 回归条数 = 0、`exact` 桶保持 `1.000`），
`dependencies` 仍是 `mcp` / `tree-sitter` / `tree-sitter-language-pack` / `pathspec` 四个，
**不含 `numpy` / `httpx` / 任何 embedding 或向量库依赖**。

### 默认路径的实测提升

本版本的价值主张是**默认路径的实测提升**，不是向量：同一份 DSH 语料（3967 文件 / 63046 chunk）、
同一套 13 个「找代码」任务各跑 3 次（共 78 个真实模型会话），只差一层本插件的 patch——

- 任务成功率 **11/39 = 28.2% → 32/39 = 82.1%**（**+53.8pp**，95% Wilson 区间 `[0.165, 0.438]` 与 `[0.673, 0.910]` **不重叠**）；
- 中位 token / 次 **80,072 → 72,909**（**−8.9%**），折算到**每个做对的任务 −62.7%**（560,868 → 209,311）；
- `locate` 桶 **0/12 → 9/12**、`crossfile` 桶 **0/15 → 12/15**，而 `identifier` / `regression` 保持满分、`negative` 仅 3/3 变 2/3。

> **⚠️ 这是诊断性配比，不是真实流量上的提升幅度**：这 13 个任务**刻意偏向"需要检索"的那一类**
> （`locate` + `crossfile` 占 10/13），配比按**诊断价值**而非真实频率确定（`EVAL.md` §2.3/§2.9）。
> 它回答的是「**当问题确实需要检索时**，装与不装差多少」。样本为单一语料、单一模型、13 条题 × 3 次，
> 3 次尝试不独立（同题重跑），真实置信区间比 Wilson 更宽。
> 原始数据：[`eval/runs/clean-a3/report.md`](eval/runs/clean-a3/report.md)（不装）／
> [`eval/runs/clean-b3/report.md`](eval/runs/clean-b3/report.md)（装了）。

### 可选向量路径：已实现，按 `V4` 不发布

- 语义检索作为**可选、默认关闭**的后端**已在仓库内实现**（`embed.py` / `vectors.py` + `searcher.py` 的
  RRF(k=60) 融合与干净回退；形态冻结于 [`ADR-16`](docs/adr/ADR-16-optional-vector-backend.md)，
  云端 `openai` 兼容后端冻结于 [`ADR-17`](docs/adr/ADR-17-optional-cloud-embedding.md)），
  **但本版本不发布这条路径**：`CODERAG_SEMANTIC` 未设即为关闭，未配置时零网络调用、不 import `numpy`。
- 不发布的依据是实测触发 [`ADR-14`](docs/adr/ADR-14-semantic-retrieval.md) §10.4 的 **`V4`**：
  `V1` 未达（`natural` 桶 `Success@5 = 6/20 = 0.300 < 0.40`）、`V2` 未达（`exact@5 = 0.917 ≠ 1.000`，1 条回归）；
  `V3` 未测量（`V1` 已是析取项，结论不会改变）。细则见
  [`docs/eval-report-m3c.md`](docs/eval-report-m3c.md)。
- **`ADR-16` / `ADR-17` 的条文仍然有效**，只是本版本对应的发布对象不存在；
  因此 `T5-15`（extra `semantic` + `install.sh` 开关）、`T5-16`（可选安装冒烟）、
  `T5-20`（云端后端实现）、`T5-22`（云端安全评审）移出 2.0.0 范围。

### 变更

- 版本号 `1.0.0` → `2.0.0`（`pyproject.toml`、`package.json`、`src/dsh_coderag/__init__.py`）。

### 新增

- **可选语义后端（默认关闭，本版本不发布）**：`code_search` 新增可选的 `semantic` 字段，
  后端不可用或未配置时**干净回退纯 BM25**（条数、路径、行号、顺序逐条不变，`status` 仍为 `ready`，
  不是空列表），失败只作为结构化 notice 出现、不冒泡成 `isError`。详见
  [`README.md`](README.md) 的「可选语义后端（默认关闭）」小节。
- **评测口径扩张**：L1 `natural` 桶由 7 条扩到 **20** 条（`golden_version` `m3-b1 → m3-b2 → m3-b3`），
  13 条新题在融合机制设计完成后加入且逐条结果未被查看，构成 **holdout**——它证伪了
  「`3/7 = 0.429` 贴线通过」，把 `natural` 上限钉在 `6/20 = 0.300`。

## [1.0.0] - 2026-09-23

首个版本。仓库内 `pyproject.toml` 与 `package.json` 均为 `1.0.0`；**尚未发布到 PyPI 与 npm**。
本版本**不含向量检索**——原因与重启条件见
[`docs/adr/ADR-15-defer-semantic-retrieval.md`](docs/adr/ADR-15-defer-semantic-retrieval.md)。

### 新增

- **MCP 服务器**（stdio transport）：固定 4 个工具 `code_search` / `code_outline` / `code_index` / `index_status`，
  工具集不动态增删。
- **索引**：SQLite **FTS5**（`unicode61`）+ 中文 bigram 预处理；索引固定写在
  `<工作区>/.coderag/index.sqlite3`，不写到工作区之外。
- **三层安全过滤**（按顺序、缺一不可）：内置密钥黑名单 → `.gitignore` / `.coderagignore`（用 `pathspec`）
  → 内容级正则扫描。命中的 chunk 不入库，且只记路径与模式名、绝不记录内容；过滤结果通过
  `skipped: {count, reasons}` 对模型可见。
- **声明感知分块**：tree-sitter 按函数 / 类 / 接口等声明边界切分（Python、C、C++、TypeScript、JavaScript），
  含模块头、超大声明的二次切片、未覆盖区域的 gap 块与低置信 fallback。
- **增量索引**：按内容哈希跳过未变文件；对账新增 / 修改 / 删除；并发度与批大小自适应推导（不硬编码）；
  支持取消；文件数超过上限时**显式失败并报告实际数量**，绝不静默截断。
- **检索**：BM25；选按分数、**输出按源码顺序**；精度与召回双模式；纯标点查询给出结构化提示并改走 `grep`；
  按 token 预算裁剪并报告省略条数；索引未就绪或零命中时返回结构化状态，而不是空列表。
- **审计与日志**：每次索引写 `.coderag/last-index.json`（耗时分解、`skipped` / `redacted` 计数）；
  日志为 stderr 上的 JSON-Lines，**绝不写 stdout**。
- **DSH 集成**：仓库根 `cordis.patch.yml` 同时充当本地开发 overlay 与可分发的 bundle patch；
  `package.json` 声明 `dsh.bundle.patch`，**不含任何 JS 入口、不含 install script**；
  解释器路径可用 `CODERAG_PYTHON` 覆盖，工作区根可用 `CODERAG_ROOT` 覆盖。
- **安装脚本** `scripts/install.sh`：探测解释器与 conda 环境、校验 Python 版本、
  预检 SQLite FTS5、安装后验证中文 bigram 往返，并打印下一步；可重复运行。
- **评测**：30 条 golden 集（L1：`Success@k`、`MRR`、token 中位数、逐 query diff、`golden_version` 门禁）；
  13 条端到端用例（L2：A/B 对照）；`scripts/eval-gate.sh` 一键跑 L1 + L2 门禁。

### 安全

- 默认**不联网**、**不采集遥测**、不外发任何数据。
- **不含任何 embedding / 向量库依赖**，安装不需要本地模型。
- 不读取、不入库被过滤规则命中的文件（`.env*`、`*.pem`、`id_rsa*`、`.ssh/` 等）。
