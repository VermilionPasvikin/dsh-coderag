# Changelog

本项目的所有重要变更都记录在这里。
格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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
