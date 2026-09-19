# TESTING.md — 测试方案设计

> **文档版本**：1.0 ｜ **撰写日期**：2026-09-17
> **配套**：[`PROJECT.md`](./PROJECT.md) ｜ [`AGENTS.md`](./AGENTS.md) ｜ [`EVAL.md`](./EVAL.md)
>
> **本文件是 `AGENTS.md` 第 5 节（测试与验收规范）的展开。** `AGENTS.md` 规定"必须做什么"，本文件规定"具体怎么做"。

---

## 0. 三条设计原则

| # | 原则 | 含义 |
|---|---|---|
| **P1** | **零成本可运行** | 所有测试必须能在**无网络、无模型 API key** 的条件下跑完。这是硬约束——你不是每次改代码都想花钱 |
| **P2** | **确定性** | 同样的输入必须给出同样的结果。检索有浮点打分，是确定性的主要威胁（见 §3.4） |
| **P3** | **测行为，不测实现** | 测试名与断言描述"系统做了什么"，不是"代码怎么写的"。改实现不应该改测试 |

---

## 1. 测试分层

```
                    ┌─────────────────────────────┐
   少、慢、贵        │  L3 端到端（MCP 进程 + DSH）  │  ~3 条，手工触发
                    ├─────────────────────────────┤
                    │  L2 集成（模块间 + SQLite）   │  ~40 条，每次提交
                    ├─────────────────────────────┤
   多、快、便宜      │  L1 单元（纯函数）            │  ~100 条，每次提交
                    └─────────────────────────────┘
```

| 层 | 测什么 | 数量目标 | 跑多久 | 何时跑 |
|---|---|---|---|---|
| **L1 单元** | `text.py` / `chunker.py` / `walker.py` / `sanitize.py` / `render.py` 的纯函数行为 | 100+ | < 5s | 每次提交 |
| **L2 集成** | 索引→检索全链路（真实 SQLite）、MCP 协议（内存传输）、CLI | 40+ | < 30s | 每次提交 |
| **L3 端到端** | 真实 `dsh` 子进程 spawn 你的 MCP server，模型真的调用工具 | 3 条 | 分钟级 | 里程碑出口 |

**不追求"覆盖率 100%"**。`PROJECT.md` 与 `AGENTS.md` 都没有要求覆盖率数字。**对检索类库，覆盖率是弱指标**——一个 100% 覆盖但断言很弱的测试套件毫无价值。本方案用**必测清单**（§2）替代覆盖率目标。

**建议的 CI 覆盖率门禁：`--cov-branch --cov-fail-under=88`。** 依据（三个独立来源一致）：

| 来源 | 立场 |
|---|---|
| Fowler, [TestCoverage](https://martinfowler.com/bliki/TestCoverage.html) | "upper 80s or 90s"；对 100% "suspicious"；**"below half" 是有问题** |
| Google, Code Coverage Best Practices | "There is no 'ideal code coverage number'"；**"What's not covered is more meaningful than what is covered"** |
| Google SEG ch.11 | 覆盖率只证明某行**被执行过**，不证明发生了什么；且 80% 门槛会被当成 **ceiling** |

**本项目采用的三档策略**：

| 范围 | 目标 | 理由 |
|---|---|---|
| 全仓库 | **88% + branch** | 兜底，不作为质量目标 |
| **必须逐字符稳定的模块**（结果文本格式化、排序 key、MCP 序列化） | **per-file 100%** | 它们一旦漂移就是模型可见契约的破坏 |
| 检索质量 | **不用覆盖率衡量** | 用 golden query 判定集（`EVAL.md`） |

**明确不给全仓库定 100%**：我们有原生扩展依赖（tree-sitter、SQLite），**平台相关代码必然存在**，CPython 官方 devguide 也说 "getting 100% is not always possible. There could be platform-specific code"。

---

## 2. 必测清单（**这些必须有，缺一不可**）

| # | 类别 | 为什么必须 | 层 | 对应任务 |
|---|---|---|---|---|
| **M1** | **安全过滤** | 泄露用户私钥是安全事故，不是 bug | L1+L2 | T2-06 |
| **M2** | **中文分词对称性** | 索引侧与查询侧转换不一致会导致静默的零召回 | L1 | T1-06 |
| **M3** | **状态契约** | RL-06：空结果会让模型编造 | L2 | T1-13 |
| **M4** | **stdout 洁净** | RL-04：任何多余字节都破坏 MCP 协议 | L2+L3 | T1-11 |
| **M5** | **检索质量** | 这是项目存在的理由 | L2 | T3-03 |
| **M6** | **分块完整性** | 切出的 chunk 必须覆盖全文且不重叠 | L1(属性) | T2-02 |
| **M7** | **顺序保持** | ADR-05：选按分数、排按位置 | L1 | T2-14 |
| **M8** | **容量上限显式失败** | RL-08：静默截断会让用户以为索引完整 | L1 | T2-11 |
| **M9** | **模型可见文本快照** | 工具描述/返回格式是稳定契约 | L2 | T1-09 |
| **M10** | **异常不冒泡** | RL-09：内部异常必须转成结构化状态 | L2 | T1-13 |

---

## 3. 具体怎么写

### 3.1 目录结构

```
tests/
├── conftest.py                    # 共享 fixture：tiny_repo / decl_repo / oversized_repo / secrets_repo / index_db
├── fixtures/
│   ├── tiny/                      # 极小仓库：.py/.c/.ts 各 1 个
│   ├── decl/                      # 声明感知分块的 4 语言样例（T2-02）
│   ├── oversized/                 # 单函数 1000 行（T2-03）
│   └── secrets/                   # ⚠️ 全假凭据：.env / id_rsa / config.py(AKIA) / normal.py（T2-06）
├── test_config.py / test_types.py / test_text.py
├── test_schema.py
├── test_walker.py / test_too_many_files.py
├── test_chunker.py / test_chunker_decl.py / test_chunker_oversized.py / test_contextual_prefix.py
├── test_parser.py
├── test_indexer.py / test_incremental.py / test_indexer_changes.py
├── test_searcher.py / test_order_preserving.py / test_token_budget.py / test_path_filter.py
├── test_security.py / test_skip_report.py
├── test_status_contract.py / test_server.py / test_render.py / test_outline.py
├── test_taskman.py / test_cancel.py / test_adaptive_concurrency.py / test_log.py
├── test_tokenizer_semantics.py
└── test_retrieval_quality.py      # M5（M3 规划，跑 eval/tasks.jsonl）

（属性测试（M6/M8）位于 test_chunker_decl.py / test_too_many_files.py，未单独建 test_properties.py；
  `cjk/` fixture 尚未创建，中文用例在 test_searcher.py / test_tokenizer_semantics.py 内用 tmp_path 自建。）
```

**`tests/fixtures/secrets/` 里放什么**（刻意构造，**内容必须是假的**）：

```
tests/fixtures/secrets/
├── .env                    →  FAKE_KEY=sk-abcdefghijklmnopqrstuvwxyz123456
├── id_rsa                  →  -----BEGIN OPENSSH PRIVATE KEY-----\nFAKE...
├── config.py               →  AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
├── normal.py               →  正常代码（作为对照组，必须被索引）
└── .coderagignore          →  一行，忽略 ignored_dir/
```

> ⚠️ **RL-02 提醒**：这些是**假凭据**，用于验证过滤器工作。**绝不要放真实凭据**，即使是为了测试。

### 3.2 MCP 服务器怎么测（M3 / M4 / M10）

**官方 SDK 提供了内存传输**，不需要起子进程。这是首选方式：

```python
# tests/test_server.py
from collections.abc import AsyncGenerator
import pytest
from inline_snapshot import snapshot
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from dsh_coderag.server import build_server

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def client(tmp_path) -> AsyncGenerator[ClientSession]:
    server = build_server(root=tmp_path)
    async with create_connected_server_and_client_session(
        server, raise_exceptions=True           # 测试里让异常可见
    ) as session:
        yield session

@pytest.mark.anyio
async def test_index_absent_returns_structured_status_not_empty_list(client, tmp_path):
    """M3 / RL-06：无索引时必须返回结构化状态，绝不返回空列表。"""
    result = await client.call_tool("code_search", {"query": "anything"})
    text = result.content[0].text
    assert text.startswith("status:")
    status = text.splitlines()[0].split(":", 1)[1].strip()
    assert status in {"indexing", "empty", "error"}
    # 关键断言：不是一个空的结果数组
    assert text.strip() not in ("[]", "hits: 0", "")
```

**来源**：MCP Python SDK 官方测试文档 <https://py.sdk.modelcontextprotocol.io/v1/testing/>（`create_connected_server_and_client_session` + `anyio_backend` fixture 的用法照抄自该文档）。

**该文档同时官方推荐 [`inline-snapshot`](https://15r10nk.github.io/inline-snapshot/latest/) 做快照测试** —— 本方案采纳（见 §3.5）。

### 3.3 stdout 洁净测试（M4，**这条最容易被忽略**）

`RL-04`：stdout 是 MCP 的 JSON-RPC 通道，任何多余字节都会破坏协议。但**开发时你一定会不小心写 `print()`**。所以必须有测试拦它：

```python
# tests/test_server.py
@pytest.mark.anyio
async def test_no_stdout_pollution_during_tool_call(capsys, client):
    """M4 / RL-04：工具调用期间 stdout 必须零输出。"""
    await client.call_tool("code_search", {"query": "test"})
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout 被污染: {captured.out!r}"
```

**更严的版本**（子进程级，作为 L3 的一部分）：真实 spawn 一次 server，发 `initialize` + `tools/list`，然后断言 **stdout 的每一行都是合法 JSON-RPC**、且 **stderr 是合法的 JSON Lines 日志**：

```python
# tests/e2e/test_stdio_protocol.py
def test_stdio_channel_is_clean():
    """L3：真实子进程，stdout 必须只含 JSON-RPC。"""
    proc = subprocess.Popen([sys.executable, "-m", "dsh_coderag.server"],
                            stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True)
    # ... 发送 initialize / tools/list ...
    out, err = proc.communicate(timeout=10)
    for line in out.splitlines():
        json.loads(line)          # 任何非 JSON 行都会抛异常
    for line in err.splitlines():
        if line.strip():
            json.loads(line)      # stderr 必须是 JSON Lines
```

### 3.4 确定性测试（M7）

**问题**：BM25 返回浮点分数，**分数相同的两条结果排序不稳定**（SQLite 不保证 tie 的顺序）。这会让同一个查询在不同运行中返回不同顺序，进而让快照测试随机失败。

**修法（必须做）**：SQL 排序键永远是**复合键**，最后一项是唯一的：

```sql
ORDER BY rank ASC,              -- 见下：rank 就是 bm25()，且更快
         c.path ASC,            -- 稳定键 1
         c.start_line ASC       -- 稳定键 2（全局唯一）
```

**关于 FTS5 `bm25()` 的四个事实（官方文档 + 本机实测）**：

| 事实 | 说明 |
|---|---|
| **返回负数，越小越好** | FTS5 实现故意乘了 −1，所以**默认升序即最佳在前**，不需要 `DESC`。本机实测：`alpha`（1/3 文档命中）得 `-0.52`，排在 `alpha beta` 之前 ✅ |
| **⚠️ 量级由 IDF 决定，与 tokenizer 无关** | **这是本机受控实测的结论，推翻了一条外部说法**。同一批 20 个文档、同一个 tokenizer，只改「被查词出现在几个文档里」：1/20 → `-3.20`；2/20 → `-2.48`；5/20 → `-1.26`；**≥10/20 → `-0.000001`**（`unicode61` 与 `trigram` 在每个档位都给出几乎相同的值）。**所以当你看到 ≈1e-6 这种分数时，原因是"被查词出现在半数以上文档里"（IDF 趋零），不是"你换了 trigram"。** 不要在分数展示逻辑里写针对某个 tokenizer 的特判 |
| **`ORDER BY rank` 比 `ORDER BY bm25(t)` 更快** | 隐藏列 `rank` 默认等于 `bm25()`，但用它可以**提前中止**扫描 |
| **`k1`/`b` 是硬编码的 1.2 / 0.75** | ⚠️ **不能调**。网上常见引用的 "K1=1.5, B=0.75"（来自其他 BM25 实现）**在 FTS5 里不适用**。要改必须自己写 ranking function |
| **分数相同时的行序：无定义** | ⚠️ **出处是 SQLite 核心 SELECT 文档，不是 FTS5 文档**（FTS5 页面只说"不带 ORDER BY 时返回 arbitrary order"）。[SQLite SELECT §4](https://www.sqlite.org/lang_select.html) 原文：***"The order in which two rows for which all ORDER BY expressions evaluate to equal values are returned is undefined."*** 源码级佐证：FTS5 为 `ORDER BY rank` 专设计划 `FTS5_PLAN_SORTED_MATCH`，其内部 sorter 的 SQL 里**只有排序函数键，没有 rowid 次级键** |

**因此**：

1. **排序键必须带唯一项**（`chunk_id` 或 `(path, start_line)`）。加了唯一键之后比较退化为纯 id 顺序，**断言完全确定，不需要任何 epsilon 容差**。

> **⚠️ 这不是可选的优化，而是相关性门禁的前置条件。**
>
> 如果不写唯一次级键，那么当评测分数变化时，你**分不清**它是：
> - (a) 检索质量真的变了，还是
> - (b) 只是同分项的顺序这次抖动到了别的位置
>
> 两者会**混在同一个红叉里，无法归因**。`EVAL.md` §2.7 的门禁规则（看回归条数、逐条 diff）**建立在"同样的输入必然给同样的顺序"之上**。所以：**`T2-14`（顺序保持 + 确定性）必须先于 `T3-04c`（逐 query diff）完成。**
2. **不要比对浮点绝对值**。IDF 含文档总数 `N`、`avgLog` 含平均文档长度——文档集合、分词器、SQLite 版本任何一个变了，绝对值都会变。SQLite 官方另有免责声明：*"makes no guarantees that the accuracy of computations on floating point values will even be this accurate"*。
3. 只对**展示用**的分数取整（`ROUND(bm25(...), 6)`），**绝不用取整值排序**。
4. **只有一种情况才需要相对 epsilon**：被迫用 `ORDER BY rank` 做 keyset 分页时。本项目的工具返回固定 top-k，**不需要**。

**验证 tie-break 最省力的语料构造**（来自开源项目 agaric 的回归测试）：**造三条内容完全相同的 chunk**，强制分页/截断边界落在同分区间内部——这样并列一定发生，测试必然覆盖到 tie-break 分支。

**测试**：

```python
def test_search_order_is_deterministic(indexed_workspace):
    """M7：同一查询连跑 20 次，结果顺序必须完全一致。"""
    runs = [search(indexed_workspace, "handler", k=10) for _ in range(20)]
    assert all(r == runs[0] for r in runs)

def test_output_ordered_by_source_position_not_score(indexed_workspace):
    """M7 / ADR-05：输出按 (path, start_line) 升序，而不是按分数降序。"""
    result = search(indexed_workspace, "handler", k=10)
    keys = [(h.path, h.start_line) for h in result.hits]
    assert keys == sorted(keys), "输出未按源码顺序排列"
```

**不要把分数写进快照**。快照里只放**排序后的路径与行号**——分数会随 SQLite 版本变化。

### 3.5 模型可见文本的快照测试（M9）

工具描述、返回格式、状态字符串都是**模型看到的契约**。它们必须逐字符稳定，且改动必须是有意的。

**方案：`inline-snapshot`**（MCP 官方 SDK 文档推荐）：

```python
# tests/test_render.py
from inline_snapshot import snapshot

def test_search_result_format_is_stable(indexed_workspace):
    out = render_search_result(search(indexed_workspace, "verify_token", k=2))
    assert out == snapshot("""\
status: ready
query: "verify_token"
scanned: 3 files / 7 chunks
hits: 2 (sorted by source order)

── src/auth/token.py:1-4  [function verify_token]  (chunk 0)
def verify_token(raw: str) -> Claims:
    ...
""")
```

**为什么选 `inline-snapshot`**：
- 期望值**内联在测试文件里**，读代码时一眼可见（不用跳去 `__snapshots__/` 目录）
- 用 `pytest --inline-snapshot=fix` 一键更新
- 被 MCP 官方 SDK 文档点名推荐
- `syrupy` **明确不支持 inline 快照**并以 `not_planned` 关闭了对应 issue，官方转荐 inline-snapshot；`pytest-snapshot`（0.9.0）最后提交是 2023-11，**事实停更**

**⚠️ `inline-snapshot` 有两个会静默破坏 CI 的硬限制**

| 限制 | 后果 | 防范 |
|---|---|---|
| **不支持 `pytest-xdist`** | 装了并启用 xdist **等同 `--inline-snapshot=disable`**——快照测试会**静默跳过，不是失败** | **快照测试必须单独跑一个 `-n0` 的 CI step**（见 §5.1） |
| **CI 环境下默认 `disable`** | 同上，静默跳过 | 同上；且快照只能在 CPython 上更新 |

**还有一类"改了但不上报"的情况**：写入源码时把含换行的字符串转成三引号、或转义首尾换行，属于 **`update` 类别，默认不上报**——需要 `pytest --inline-snapshot=update` 才会看到。**PR diff 里出现这类改动时不要惊讶。**

> **对本项目的影响**：我们的 CI 计划里本来有 `-n auto`（并行）。加了这条约束后，**`pytest` 拆成两步**：先 `pytest -n auto -m "not snapshot"` 跑并行，再 `pytest -n0 -m snapshot` 跑快照。**这是 `TESTING.md` 与 `PROJECT.md` 里 CI 配置的强制要求。**

**对比**：`syrupy` 把快照放在单独的 `__snapshots__/` 目录（便于大块数据，但读代码时要跳转）。**它的 amber 序列化器会把 `\r\n` 归一化成 `\n`**——要字节保真必须换 `SingleFileSnapshotExtension`。本项目输出都很小，**内联更好**。

**工具描述的快照**（`tools/list` 的返回）：

```python
@pytest.mark.anyio
async def test_tool_descriptions_are_stable(client):
    """M9：工具描述是模型可见契约，改动必须有意为之。"""
    tools = await client.list_tools()
    assert [t.name for t in tools.tools] == snapshot(
        ["code_search", "code_outline", "code_index", "index_status"]
    )
    assert tools.tools[0].description == snapshot("...")
```

> 这条测试同时守住了 `RL-05`（工具集固定为 4 个）——任何人想加第 5 个工具，这条会立刻变红。

### 3.6 安全过滤测试（M1，**硬门禁**）

```python
# tests/test_security.py
def test_secret_files_never_enter_index(indexed_secrets_repo):
    """M1 / RL-03：这是安全事故级断言，不通过不允许进入 M3。"""
    paths = all_indexed_paths(indexed_secrets_repo)
    assert not any(p.endswith(".env") for p in paths)
    assert not any("id_rsa" in p for p in paths)
    assert not any("config.py" in p for p in paths)   # 含 AKIA... 的

def test_normal_file_still_indexed(indexed_secrets_repo):
    """对照组：过滤不能误伤正常文件。"""
    assert "normal.py" in all_indexed_paths(indexed_secrets_repo)

def test_content_level_scan_redacts_inline_secret(tmp_path):
    """M1：代码注释里的密钥也必须被拦下。"""
    (tmp_path / "leak.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    index(tmp_path)
    assert chunks_of(tmp_path, "leak.py") == []

def test_skipped_reasons_are_reported(indexed_secrets_repo):
    """§4.2：过滤必须对模型可见，静默过滤会让模型以为代码不存在。"""
    status = index_status(indexed_secrets_repo)
    assert status["skipped"]["reasons"]["secret_file"] >= 2
```

**加一条反向测试**（防止过滤被写得过宽）：

```python
def test_filter_does_not_swallow_environment_module(tmp_path):
    """防过度过滤：os.environ 相关代码是正常代码，不能被密钥规则误伤。"""
    (tmp_path / "env_reader.py").write_text(
        "import os\ndef get_path():\n    return os.environ['PATH']\n", encoding="utf-8")
    index(tmp_path)
    assert chunks_of(tmp_path, "env_reader.py") != []
```

### 3.7 中文分词对称性测试（M2）

这是我在 PoC 中实际踩到的坑（`PROJECT.md` §5.3.1）。

```python
# tests/test_text.py（对称性）+ tests/test_cjk_recall.py（精度/召回；T3-13 落地）
from dsh_coderag.text import to_bigrams

def test_bigrams_are_symmetric_between_index_and_query():
    """M2：索引侧与查询侧必须用同一个转换函数。任何一侧漏掉都会静默零召回。"""
    text = "校验用户令牌的有效性"
    assert to_bigrams(text) == "校验 验用 用户 户令 令牌 牌的 的有 有效 效性"

def test_two_char_cjk_word_is_retrievable(cjk_corpus):
    """M2：2 字中文词必须能检索到 —— 这是 trigram 方案失败、改用 bigram 的直接原因。"""
    result = search(cjk_corpus, "令牌", k=5)
    assert any("token" in h.path for h in result.hits), f"2 字词召回失败: {[h.path for h in result.hits]}"

def test_precision_mode_matches_exact_substring(cjk_corpus):
    """M2：精度模式（连续 bigram 短语）等价于精确子串匹配。"""
    result = search(cjk_corpus, "用户令牌", k=5)
    assert [h.path for h in result.hits] == ["src/auth/token.py"]

def test_recall_mode_used_when_precision_returns_nothing(cjk_corpus):
    """M2：精度模式返回 0 时必须自动降级到召回模式，而不是直接返回空。"""
    result = search(cjk_corpus, "认证令牌方式", k=5)
    assert len(result.hits) > 0

def test_latin_identifier_is_not_bigrammed():
    """M2：拉丁标识符不能被切碎。"""
    assert "verify_token" in to_bigrams("def verify_token(raw): pass")
```

### 3.8 属性测试（M6 / M8，用 Hypothesis）

检索系统的**不变式**适合用属性测试——人工构造的例子永远不够全。

```python
# tests/test_properties.py
from hypothesis import given, strategies as st, settings

@given(st.text(min_size=1, max_size=2000))
@settings(max_examples=200, deadline=None)
def test_chunker_never_loses_content(text):
    """M6：分块必须覆盖全文（拼回来等于原文的非空白字符）。"""
    chunks = chunk_text(text, lang="python")
    joined = "".join(c.text for c in chunks)
    assert normalize(joined) == normalize(text)

@given(st.text(min_size=1, max_size=2000))
@settings(max_examples=200, deadline=None)
def test_chunks_do_not_overlap(text):
    """M6：chunk 的行区间不能重叠。"""
    chunks = chunk_text(text, lang="python")
    spans = sorted((c.start_line, c.end_line) for c in chunks)
    for (_, e1), (s2, _) in zip(spans, spans[1:]):
        assert s2 > e1

@given(st.text(min_size=1, max_size=500))
@settings(max_examples=300, deadline=None)
def test_to_bigrams_never_raises_and_is_idempotent_on_latin(text):
    """M2：任意输入不得崩溃；纯拉丁文本转换后不变。"""
    out = to_bigrams(text)
    assert isinstance(out, str)
    if not any("\u4e00" <= ch <= "\u9fff" for ch in text):
        assert out == text

@given(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=100),
       st.integers(min_value=1, max_value=10))
@settings(max_examples=50, deadline=None)
def test_file_limit_fails_loudly_never_truncates(paths, limit):
    """M8 / RL-08：超过上限必须显式失败，绝不静默截断。"""
    if len(paths) <= limit:
        pytest.skip("未超过上限")
    with pytest.raises(TooManyFilesError) as exc:
        walk_with_limit(paths, max_files=limit)
    assert exc.value.actual_count == len(paths)      # 必须带真实数量
```

**Hypothesis 的注意点**：

- **`deadline` 默认 200ms，会让带 SQLite 的分块属性测试随机失败。** 最省事的解法是在 `conftest.py` 里一行：`settings.load_profile("ci")` —— Hypothesis 内置的 `ci` profile 就是 `deadline=None`，且**检测到 CI 环境变量时自动启用**。比给每个 `@settings` 手写 `deadline=None` 干净。
- **health check 要按需抑制，不要 blanket suppression**（官方警告）。
- **⚠️ 长度单位陷阱**：`st.text()` 的长度按 **Unicode 码点**计（`U+00C5` = 1，`U+0041 U+030A` = 2），而 **tree-sitter 用的是字节偏移**，且 `st.text()` **不做 Unicode 规范化**。所以在写"chunk 偏移合法""chunk 覆盖全文"这类性质时，**必须想清楚断言用的是码点还是字节**——两者在含组合字符或非 ASCII 时会分歧。
- **不要为 surrogate 写 workaround**：`st.text()` **默认就排除代理字符**（官方原文：*"excludes surrogate characters because they are invalid in the UTF-8 encoding"*），所以 `st.text().map(lambda s: s.encode("utf-8"))` **不会抛异常**。想测 surrogate 必须**显式**用无参 `st.characters()`；"非 UTF-8 输入应被优雅拒绝而非崩溃"应当作**单独一条性质**来写。
- 属性测试**必须能重现失败**：Hypothesis 会自动保存失败的输入到 `.hypothesis/`，**加进 `.gitignore`**（但要在 CI 缓存它，否则复现不了）。
- 不要给属性测试加 `@pytest.mark.slow` 然后默认跳过——**它们是最有价值的测试**。

### 3.9 异步任务测试（索引的 taskId 流程）

```python
def test_index_returns_task_id_immediately(tmp_path, big_repo):
    """E-01：必须立刻返回，不能阻塞（MCP 工具超时 60s）。"""
    t0 = time.monotonic()
    task_id = start_index(big_repo)
    elapsed = time.monotonic() - t0
    assert task_id.startswith("idx-")
    assert elapsed < 0.2, f"阻塞了 {elapsed:.2f}s"

def test_task_state_machine_progresses(tmp_path):
    """状态机：pending → running → ready。"""
    task_id = start_index(tmp_path)
    assert wait_for_state(task_id, "ready", timeout=30)

def test_cancel_stops_writing(tmp_path, big_repo):
    """取消后不得再写库。"""
    task_id = start_index(big_repo)
    cancel(task_id)
    assert wait_for_state(task_id, "cancelled", timeout=10)
    before = count_chunks(big_repo)
    time.sleep(1)
    assert count_chunks(big_repo) == before

def test_index_state_survives_restart(tmp_path):
    """C10：索引状态必须跨进程重启持久化。"""
    task_id = start_index(tmp_path)
    wait_for_state(task_id, "ready", timeout=30)
    reopened = reopen_index(tmp_path)
    assert reopened.status()["state"] == "ready"
    assert reopened.status()["skipped"]["count"] >= 0   # 忽略规则也要一起持久化
```

**避免 flaky**（`AGENTS.md` 没有覆盖，此处补充）：
- **不要用 `time.sleep` 猜时间**，用 `wait_for_state(..., timeout=)` 轮询
- **超时要宽松**：CI 上的机器比你的慢 3–5 倍，给 30s 而不是 5s
- **测试里的批大小要调小**：通过构造参数传入，不要改生产默认值

```python
@pytest.fixture
def fast_index_config():
    """测试专用的索引配置；生产默认值不受影响。"""
    return IndexConfig(batch_size=4, max_workers=1, max_files=100)
```

### 3.10 检索质量测试（M5）

见 `EVAL.md` §4.1。要点：

```python
@pytest.mark.parametrize("task", load_tasks("eval/tasks.jsonl"), ids=lambda t: t["id"])
def test_recall_at_5(task, indexed_eval_corpus):
    result = search(indexed_eval_corpus, task["query"], k=5)
    assert any(h.path in task["expect_paths"] for h in result.hits), (
        f"{task['id']} ({task['class']}) 未命中。"
        f"query={task['query']!r} 实际返回={[h.path for h in result.hits]}"
    )
```

**注意**：`indexed_eval_corpus` 这个 fixture 会索引一个真实仓库，**必须缓存**（用固定路径的 SQLite + mtime 校验），否则每次 pytest 都要重建索引。

### 3.11 分词器语义测试（**三条必测，且预期是"路由"行为**）

依据：GitHub 官方博客《The technology behind GitHub's new code search》原文——*"we want to search for punctuation (for example, a period or open parenthesis); **we don't want stemming**; **we don't want stop words to be stripped** from queries"*（经其 WordPress REST API 取得全文）。

**本机实测的背景事实**（`forBSH`，SQLite 3.53.4）：

| 查询 | `unicode61` | `trigram` | `porter` |
|---|---|---|---|
| `"("` / `"."` / `"::"` / `"->"` | ❌ 全部 0 | ❌ 全部 0 | ❌ 全部 0 |
| `"self."` / `"std::vector"` | ✅ 1 | ✅ 1 | ✅ 1 |
| `LIKE '%(%'` | ✅ 1 | ✅ 1 | — |

> **三条 tokenizer 对短标点的表现完全一致——换 tokenizer 解决不了。** 所以下面三条测试**测的不是"FTS 能搜到标点"，而是"我们正确地路由到了 grep 并告诉模型"**（ADR-13）。**把预期写成"能搜到标点"会让测试永远红且方向错误。**

```python
# tests/test_tokenizer_semantics.py
import pytest
from dsh_coderag import search, SearchStatus

# ── 测试 1：标点查询必须被显式路由，而不是静默返回空 ────────────────
@pytest.mark.parametrize("query", ["(", "::", "->", "[", "#", "{}", "()"])
def test_punctuation_query_routes_to_grep_with_structured_hint(indexed_fixture, query):
    """ADR-13：短标点 FTS 搜不到（实测三档 tokenizer 全失败）。

    正确行为 = 不做全表扫描、返回结构化提示指向 grep，
    而不是返回空列表让模型以为"代码里没有"（RL-06 的同一个根因）。
    """
    r = search(indexed_fixture, query, k=5)
    assert r.status is SearchStatus.EMPTY
    assert "grep" in r.hint.lower(), "必须明确建议使用 grep 工具"
    assert r.hits == []

def test_query_with_punctuation_but_searchable_words_still_returns_hits(indexed_fixture):
    """对照组：`self.authenticate` 里的标点被丢弃，但 `authenticate` 仍能命中。

    这条防止我们把"含标点"一律路由掉 —— 那样会误伤最常见的查询形态。
    """
    r = search(indexed_fixture, "self.authenticate", k=5)
    assert r.status is SearchStatus.READY
    assert r.hits, "含标点但有可检索词时，必须正常检索"

# ── 测试 2：不做词干化（防 porter）──────────────────────────────────
def test_no_stemming(indexed_fixture):
    """`connection` 不应命中只含 `connect` 的文档。"""
    r = search(indexed_fixture, "connection", k=5)
    assert all("connect_only.py" != h.path for h in r.hits)

def test_tokenizer_is_not_porter(indexed_fixture):
    """直接锁死索引所用的 tokenizer 名称，防止有人"顺手"改成 porter。"""
    assert current_fts_tokenizer(indexed_fixture) == "unicode61"

# ── 测试 3：不剥离停用词（代码里 for/if/and 是标识符）──────────────
@pytest.mark.parametrize("word", ["for", "if", "and", "in", "not"])
def test_stopwords_are_searchable(indexed_fixture, word):
    """代码里的 `for`/`if`/`and` 是关键词，不是停用词 —— 绝不能被剥离。"""
    r = search(indexed_fixture, word, k=5)
    assert r.status in (SearchStatus.READY, SearchStatus.EMPTY)
    # 语料里确实有该词时必须能命中
    if fixture_contains(indexed_fixture, word):
        assert r.hits, f"停用词 {word!r} 被剥离了 —— tokenizer 配置有问题"
```

> **与 ADR-13 对齐**：路由的精确判据是「去掉标点后**没有可检索词**」。因此 `self.(`、`std::` 不属于路由用例（它们含标识符 `self`/`std`，会走 FTS）；真正路由的是纯标点，即上面参数化列出的那些。`self.authenticate`/`std::vector` 是「含标点但仍有可检索词」的对照组。

**这三条的价值**：它们在**默认配置下就会暴露问题**——如果你不小心用了 `porter`、或者以为换个 tokenizer 就能搜标点，这三条会立刻告诉你方向错了。**评测设计里"预期失败"的测试同样重要，前提是你知道它为什么失败。**

---

## 4. 测试基础设施

### 4.1 `conftest.py` 骨架

```python
# tests/conftest.py
import shutil
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """把 tiny fixture 复制到 tmp_path —— 测试绝不写仓库内文件（T-03）。"""
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURES / "tiny", dst)
    return dst

@pytest.fixture
def indexed_tiny(tiny_repo: Path) -> Path:
    from dsh_coderag import index_sync
    index_sync(tiny_repo)
    return tiny_repo

@pytest.fixture
def index_db(tmp_path: Path) -> Path:
    """⚠️ 必须用**临时文件**，绝不能用 `:memory:`。

    SQLite 官方原文：「Every :memory: database is distinct from every other.」
    我们的索引跑在后台线程、另开连接 —— 用 :memory: 时它写进的是**另一个空库**，
    前台永远查不到数据，而且不报错。这是本项目最容易犯的测试错误。
    """
    return tmp_path / "index.sqlite3"

@pytest.fixture
def indexer(index_db: Path):
    """yield 之后必须 close()，且**必须在 pytest 删 tmp_path 之前**。

    WAL 模式会产生 -wal / -shm 文件，Windows 上 DeleteFile 对未关闭/内存映射
    的文件会失败（见 §4.4）。
    """
    inst = open_index(index_db)
    yield inst
    inst.close()
```

> ⚠️ **不要写 `in_memory_db` 这个 fixture。** 官方文档明确：每个 `:memory:` 库彼此独立。要共享只能 `file:memdb1?mode=memory&cache=shared`（同进程 + 名字完全相同），但那样测试间又会互相污染。**用临时文件，每测试一个。**

### 4.2 FTS5 能力探测（**必须做，不能做版本假设**）

**FTS5 是 SQLite 的编译期特性，跨发行版真的会缺失。** 实例：`uv` 分发的 CPython 直到 [python-build-standalone PR #694](https://github.com/astral-sh/python-build-standalone/pull/694)（2025-07-11 合并）才加上 `-DSQLITE_ENABLE_FTS5`；该 PR 同时在 `verify_distribution.py` 里加了 `CREATE VIRTUAL TABLE ... USING fts5(...)` 的存在性断言。

**你的机器有，不代表用户的机器有**（macOS 系统 python3 被官方描述为 "usually older and incomplete"）。所以：

```python
# src/dsh_coderag/sqlite_caps.py
def fts5_available() -> bool:
    """探测当前 SQLite 是否编译了 FTS5。

    注意 PRAGMA compile_options 里的名字是 `ENABLE_FTS5`，**前缀 SQLITE_ 被省略**。
    """
    with sqlite3.connect(":memory:") as conn:
        opts = {row[0] for row in conn.execute("PRAGMA compile_options")}
        if "ENABLE_FTS5" not in opts:
            return False
        try:
            conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
            return True
        except sqlite3.OperationalError:
            return False            # 编译选项在但实际不可用
```

**本机实测**（2026-09-17，`forBSH` 环境）：`ENABLE_FTS5 present: True`，SQLite 3.53.4。

**接入方式**：

| 场景 | 行为 |
|---|---|
| `code_index` / `code_search` 被调用且 FTS5 不可用 | 返回 `status: error, code: FTS5_UNAVAILABLE`，**并给出可操作的提示**（升级 Python / 改用带 FTS5 的发行版） |
| 测试里 FTS5 不可用 | `pytest.skip("本环境 SQLite 未编译 FTS5")`，**不是 fail** |
| `scripts/install.sh` | 启动时探测，不通过就**明确报错**而不是让用户后面撞墙 |

`FTS5_UNAVAILABLE` 是 `PROJECT.md` §5.6 错误码表的新增项，**必须同步加进去**。

@pytest.fixture
def fast_index_config():
    """测试专用参数；不污染生产默认值。"""
    from dsh_coderag.config import IndexConfig
    return IndexConfig(batch_size=4, max_workers=1)
```

### 4.3 `pyproject.toml` 里的配置

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q -m 'not e2e' --strict-markers --strict-config"
asyncio_mode = "strict"
timeout = 30                    # 单测试上限（需 pytest-timeout）
session_timeout = 600
# ResourceWarning（未关闭的 sqlite 连接）升级为失败 —— 能抓住一整类泄漏
filterwarnings = ["error"]
markers = [
  "e2e: 端到端测试，会 spawn 真实子进程",
  "hypothesis: 属性测试",
  # ⚠️ 必须把快照测试单独标记：inline-snapshot 不支持 xdist，
  #    启用 -n auto 时它会被静默 disable。CI 用两个 step 分别跑。
  "snapshot: 使用 inline-snapshot 的测试，必须 -n0 单进程运行",
]

[tool.coverage.run]
source = ["src/dsh_coderag"]
branch = true                   # 分支覆盖，不只是行覆盖
patch = ["subprocess"]          # 子进程覆盖（我们真的 spawn server）
parallel = true
omit = ["*/eval/*"]             # 评测代码本身不要求覆盖

[tool.coverage.report]
fail_under = 88
exclude_also = ["if TYPE_CHECKING:", "if sys.platform =="]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
# T20 = flake8-print：**静态禁止 print()**，这是 stdout 纯净性（RL-04）的第一道防线
select = ["E", "F", "UP", "B", "SIM", "I", "T20"]

[tool.mypy]
strict = true
warn_unreachable = true         # `strict` 不含它，必须显式加
```

**几个非显然的配置**：

| 配置 | 为什么 |
|---|---|
| `filterwarnings = ["error"]` | SQLite 连接没关会触发 `ResourceWarning`。不升级为 error 的话它只是被静默吞掉 |
| `patch = ["subprocess"]` | 我们真的会 spawn MCP server 子进程；不配这个，子进程里的代码覆盖率全丢 |
| `T20` | **在 CI 里静态拦住 `print()`**。等到运行时才发现 stdout 被污染就太晚了 |
| `warn_unreachable` | mypy 官方说明 `strict` 是"a defined subset"，**这个 flag 不在其中**，且 flag 列表随版本变化 |
| `branch = true` | 分支覆盖对"状态机"（`pending→running→ready`）这类代码才有意义 |

### 4.4 开发依赖

```toml
[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-cov",
  "pytest-anyio",           # MCP SDK 的 async 测试需要
  "pytest-asyncio",         # 提供 §4.3 的 asyncio_mode
  "pytest-timeout",         # 提供 §4.3 的 timeout / session_timeout
  "anyio",
  "inline-snapshot",        # MCP 官方 SDK 文档推荐
  "hypothesis",             # 属性测试
  "ruff",
  "mypy",
]
```

---

## 5. CI

### 5.1 矩阵策略

**跑多平台矩阵**（3 OS × 2 Python）。理由见下方「为什么多平台矩阵是必要的」——**这一条推翻了本文件 1.0 版的"第一版只跑 macOS"建议**。

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  check:                            # 快：风格 + 类型 + 单元/集成
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: ruff format --check src tests
      - run: mypy --strict src
      # ⚠️ pytest 必须拆成两步：inline-snapshot 不支持 xdist，
      #    启用 -n auto 会让快照测试静默跳过（不是失败）
      - run: pytest -q -n auto -m "not e2e and not snapshot" --cov-branch --cov-fail-under=88
      - run: pytest -q -n0 -m "not e2e and snapshot"
      - uses: actions/cache@v4        # 缓存失败样本，否则复现不了
        with: { path: .hypothesis, key: hypothesis-${{ github.run_id }}, restore-keys: hypothesis- }

  matrix:                           # ⚠️ 必要，理由见下
    strategy:
      fail-fast: false              # 一个平台挂了不掩盖其他平台的结果
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.10", "3.12"]
    runs-on: ${{ matrix.os }}
    continue-on-error: ${{ matrix.os == 'windows-latest' }}   # 先观察，不阻塞
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: ${{ matrix.python }} }
      - run: pip install -e ".[dev]"
      - run: pytest -q -m "not e2e"
```

**⚠️ 为什么多平台矩阵是必要的（推翻了本文件早先"第一版只跑 macOS"的建议）**

两条硬理由：

1. **FTS5 是编译期特性，跨发行版真的会缺失。** `uv` 分发的 CPython 直到 2025-07 才加上 `-DSQLITE_ENABLE_FTS5`；macOS 系统 python3 被官方描述为 "usually older and incomplete"。**你的 macOS + conda 环境有，不代表用户的机器有。** 这正是 §4.2 能力探测必须存在的原因，而矩阵是验证探测本身的手段。
2. **`tree-sitter` 是原生扩展。** 官方 README 称"provides pre-compiled wheels for all major platforms"，PyPI 有 cp310–cp314 全平台 wheel；但 `setup.py` 里确有 `Extension(name="tree_sitter._binding", ...)` 编译 vendored C 源码——**主流平台不装编译器，落到 sdist 就需要 C11**。

**明确不加的东西**：

| 不加 | 理由 |
|---|---|
| **`pytest-rerunfailures`** | **不要装这个插件。** 它**默认只保留最后一次 attempt 的 traceback**，"failures from earlier attempts … are silently discarded"。**重跑是掩盖 flaky，不是修复它**——而 flaky 的根因（sleep、竞态、未关连接）恰恰是最该修的 |
| 覆盖率 100% 门禁 | 见 §1：对检索类库是弱指标 |
| L2/L3 评测进 CI | 需要 API key 与时间，放在发布前手工跑 |
| 性能基准测试 | 没有性能需求前不做 |
| cibuildwheel | 我们不自建 wheel，纯 Python 包从 PyPI 装 `tree-sitter` |

### 5.2 三个必须进 CI 的门禁

1. `ruff check` —— 风格
2. `mypy --strict src` —— `AGENTS.md` 的 `C-01`
3. `pytest -q` —— 含 **M1 安全测试**（`T2-06` 是硬门禁）

---

## 6. 反模式清单

| 反模式 | 为什么错 | 正确做法 |
|---|---|---|
| **用 `:memory:` 做索引测试库** | ⚠️ **最隐蔽的一个**。SQLite 官方："Every :memory: database is distinct from every other." 索引跑在后台线程、另开连接 → 它写进**另一个空库**，前台永远查不到，**且不报错** | 临时文件（§4.1） |
| **装 `pytest-rerunfailures`** | 默认只保留最后一次 attempt 的 traceback，earlier failures **被静默丢弃**。重跑掩盖 flaky 而不修复它 | 不装。修根因（轮询代替 sleep） |
| **在索引线程里做断言** | pytest 官方明令：*"Avoid using primitives provided by pytest (`pytest.warns()`, `pytest.raises()`) from multiple threads, as they are not thread-safe"* | 工作线程只**记录状态**，**主线程断言** |
| **测试写进仓库内固定路径** | 并行跑测试会互相踩；污染工作区 | 一律用 `tmp_path`（`T-03`） |
| **用 `time.sleep` 等异步** | CI 上必然 flaky；且 `waitLimit` 不该是字面量 | `wait_for_state(..., timeout=)` 轮询，超时值走配置 |
| **断言 `assert "关键词" in result`** | 任何格式变化都不会被抓住 | 快照测试（`T-06`） |
| **为了过测试而放宽断言** | `T-08` 明令禁止 | 改代码，或提问 |
| **给属性测试加 skip** | 它是最有价值的测试 | 修 `deadline` 或缩小输入范围 |
| **测私有函数** | 改实现就要改测试（违反 P3） | 测公开行为 |
| **把 BM25 分数写进快照** | 分数含 IDF/avgdl，文档集或 SQLite 版本一变就红 | 快照只放**路径与行号** |
| **用 `tree-sitter-languages`** | ⚠️ 它的 wheel **只到 cp312**，且官方声明 *"Source installs are not supported"* | 用 **`tree-sitter-language-pack`**（abi3，`cp310-abi3`，一份 wheel 覆盖所有 Python 版本） |
| **测试依赖真实 LLM** | 违反 P1（零成本），且结果不确定 | 用内存传输 + 固定 fixture |
| **安全测试用真实凭据** | 违反 RL-02 | 全部用假凭据 |
| **索引 fixture 每次重建** | 测试从 5 秒变 5 分钟 | 缓存索引 + mtime 校验 |
| **过滤规则只测"拦住了"** | 容易写得过宽，误伤正常代码 | 同时测**反向**（`env_reader.py` 必须被索引） |
| **不关 SQLite 连接就删 tmp_path** | WAL 会产生 `-wal`/`-shm`；Windows 上 `DeleteFile` 对未关闭/内存映射文件会失败 | fixture 里 `yield` 后 `close()`，**且在删目录之前** |

---

## 7. 一页纸速查

```
写测试时……
  → 放 tests/，用 tmp_path，绝不写仓库内文件
  → 断言描述行为，不描述实现
  → 模型可见文本用 inline_snapshot
  → 异步操作用轮询，不用 sleep
  → 不用 LLM，不用网络

必须有的十类测试：
  M1 安全过滤（硬门禁）  M2 中文分词对称性   M3 状态契约
  M4 stdout 洁净        M5 检索质量         M6 分块完整性
  M7 顺序保持           M8 容量上限失败      M9 文本快照
  M10 异常不冒泡

CI 三条门禁：
  ruff check  |  mypy --strict src  |  pytest -q

什么不该做：
  不追 100% 覆盖率 · 不做多平台矩阵 · 不把评测塞进 CI · 不为过测试改断言
```

---

## 8. 未能核实的事项

1. **`mcp.shared.memory` 在 SDK v2 中的路径** —— 本文的 API 用法取自 **v1 文档**（`https://py.sdk.modelcontextprotocol.io/v1/testing/`）。`PROJECT.md` 已把依赖钉在 `mcp>=1.28,<2`，故 v1 用法有效。**若将来升级到 v2，必须改两处**：测试入口从 `create_connected_server_and_client_session(app, ...)` 变为 `Client(mcp, raise_exceptions=True)`；服务器类从 `FastMCP` 变为 `MCPServer`（v2 官方原文：*"No subprocess. No port. Nothing on a wire. It's the same idea as FastAPI's `TestClient`."*）。
2. **`inline-snapshot` 与 `pytest-anyio` 的兼容性** —— 官方 SDK 文档同时推荐了两者但未给组合示例，**未实测**。若冲突，退路是 `syrupy`。
3. **`--cov-fail-under=88` 这个具体数字** —— 选用它有 Fowler（"upper 80s or 90s"）与 Google（60/75/90 三档）的依据，但**没有"检索类库该定多少"的权威建议**。
4. **FTS5 在 `:memory:` 数据库中是否可用** —— 未查到明确信息（FTS5 文档与 in-memory 文档均未提及此组合）。实践上直接建表断言即可。**但即便可用，也不要用于索引测试**（原因见 §4.1 的 `:memory:` 陷阱）。
5. **FTS5 `bm25()` 分数并列时的行序保证** —— SQLite 官方文档**未给出任何保证**。这就是排序键必须带唯一项的原因。
6. **逐平台的 SQLite 版本/FTS5 对照表** —— **未查到官方表格**。所以必须做运行时能力探测（§4.2），而不是查表假设。
7. **`sqlite3` 的 `check_same_thread` 与后台线程的交互** —— 未实测。索引器跨线程用连接时必须覆盖 `True`/`False` 两条路径。
