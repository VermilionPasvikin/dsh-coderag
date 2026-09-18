# dsh-coderag

> **安全声明（请先读）**：安装本插件等于授予它与本机账号**同等的机器权限**。
> DSH 的三档文件权限（read-only / workspace-write / danger-full-access）**不约束插件**（E-04）。
> 请只在你信任的仓库与本机上安装和运行。

dsh-coderag 是一个以 MCP 服务形态提供的**代码库检索引擎**：让 DeepSeek Harness（DSH）的
Agent 能按语义与结构找到代码，而不是靠猜关键词反复 grep。

## 当前状态

- **M1 已完成**：DSH → MCP → Python → SQLite → 返回结果 的闭环已跑通，并有实测证据
  （`docs/m1-findings.md`、`PROJECT.md` §6.6）。
- **M2 / M3 / M4 尚未开始**：tree-sitter 分块、安全过滤、增量索引、评测、打包均未落地。
- **尚无 S1–S4 评测数字**：实测数据将在 M3 产出后补入（T4-05）。本文件只描述当前状态。

## 它是怎么工作的

- 引擎是 Python 包 `dsh_coderag`，以 **MCP stdio 服务器**运行。
- DSH 通过内置包 `@deepseek-ai/dsh-mcp-client` 在本机**拉起一个子进程**
  （`python -m dsh_coderag.server`），两者用 stdin/stdout 上的 JSON-RPC 通信，**不经过网络、不监听端口**。
- 索引存放在 `<工作区>/.coderag/index.sqlite3`（SQLite FTS5 + CJK bigram），**不写到工作区之外**。
- 仓库根的 `cordis.patch.yml` 同时是本地开发 overlay 与分发 bundle patch。

## 快速开始

前置：Python 3.10–3.12；DSH；一个装有依赖的 conda 环境（下文示例名 `forBSH`）。

    conda activate forBSH
    pip install -e .
    dsh-coderag index /path/to/repo
    dsh-coderag search "你想找的行为或标识符" --root /path/to/repo

把它挂到 DSH 上（本地开发方式）：

    ./scripts/dsh web --patch ./cordis.patch.yml

`dsh plugin add` 的一键安装属 M4，尚未提供。

## 配置

stdio 子进程的环境会被清洗（匹配 `*KEY*` / `*PASSWORD*` / `*SECRET*` / `*TOKEN*` 的变量与所有
`DSH_*` 变量都会被删除），所以配置必须写进 `cordis.patch.yml` 的 `config.env`：

| 变量 | 作用 | 默认 |
|---|---|---|
| `CODERAG_PYTHON` | 运行服务器的解释器路径 | 本机 `forBSH` 路径 |
| `CODERAG_ROOT` | 要索引的工作区根 | DSH 进程的工作目录 |
| `CODERAG_MAX_FILES` | 文件数上限（已解析，尚未生效） | 20000 |
| `CODERAG_MAX_TOKENS` | 单次检索的 token 预算（已解析，尚未生效） | 4000 |

激活目标环境后可用 `which python` 查解释器路径。

## 工具（固定 4 个，不动态增删）

| 工具 | 作用 |
|---|---|
| `code_search` | 按自然语言或标识符检索代码，返回文件路径与行号 |
| `code_index` | 建立 / 刷新索引，立刻返回 taskId，后台执行 |
| `index_status` | 查询任务或工作区索引状态 |
| `code_outline` | 返回单个文件的符号大纲（**尚未实现**，返回结构化“暂不支持”） |

模型侧看到的工具名形如 `mcp__coderag__code_search`。

## 已知限制

- **模型是否使用检索并不稳定**：已知确切标识符时它仍可能先 grep（R5，见 `docs/m1-findings.md`）。
- `code_search` 的 `path` 与 `max_tokens` 参数**尚未生效**。
- 检索按 bm25 相关度排序，**尚未**做到 ADR-05 的源码顺序保持（T2-14）。
- 中文查询目前只有精度模式；整句自然语言可能返回 `empty`，召回降级与标点路由尚未实现（T2-19）。
- M1 没有 tree-sitter 分块、gitignore / 密钥过滤、增量索引与任务取消；这些属 M2。

## 文档

- `PROJECT.md`：项目概况、架构、实现方案、任务表与进度。
- `AGENTS.md`：强制性约束（红线、DSH 环境坑、安全、提交规范）。
- `TESTING.md` / `EVAL.md`：测试方案与评测方案。
- `cordis.patch.yml`：DSH 接入配置。

## 许可

MIT，见 `LICENSE`。
