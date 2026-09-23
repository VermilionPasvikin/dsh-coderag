# Changelog

本项目的所有重要变更都记录在这里。
格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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
