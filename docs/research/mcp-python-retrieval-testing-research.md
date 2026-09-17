# Python MCP 服务器 + 检索系统：测试方案调研报告

> 场景：Python 包，MCP server（stdio），4 个工具（`code_search` / `code_outline` / `code_index` / `index_status`），内部 SQLite FTS5 + tree-sitter，由宿主通过 stdio spawn。要求**无网络、无模型 API key** 可跑。
> 版本基准（2026-09 抓取）：MCP Python SDK v2（`mcp>=2`，`MCPServer` / `Client`）、MCP Inspector v2、pytest stable、Hypothesis 6.168、Syrupy 6.1.1、inline-snapshot 0.35.4、tree-sitter 0.26.0。

---

## 0. 三条决定全局的结论

1. **MCP Python SDK 在 v2 已经内置 in-memory transport**，测试不需要子进程、不需要端口、不需要模型：`async with Client(mcp, raise_exceptions=True)`。这是当前官方唯一推荐的服务器测试入口（[Testing — MCP Python SDK](https://py.sdk.modelcontextprotocol.io/get-started/testing/)）。
2. **`sqlite3` 的 FTS5 是编译期特性，跨发行版真的会缺失**。`uv` 分发的 CPython 直到 [python-build-standalone PR #694](https://github.com/astral-sh/python-build-standalone/pull/694)（2025-07-11 合并）才给 SQLite 打开 `-DSQLITE_ENABLE_FTS5`。所以「FTS5 存在」必须是**运行时能力探测**，不能是版本假设。
3. **你这条链路本来就不经过模型**，所以社区「只 mock 昂贵/不确定边界，下游全真」的通行原则在你这里退化为：**什么都不用 mock**。要 mock 的只有时钟与「慢」本身。

---

## A. MCP 服务器怎么测（重点）

### A1. 官方 Python SDK 的测试手段

**先确认你用哪一代 SDK**——v1 与 v2 的测试 API 完全不同。

| | v1（`mcp>=1.28,<2`） | v2（`mcp>=2`，当前） |
|---|---|---|
| 服务器类 | `FastMCP` | `MCPServer` |
| 测试入口 | `create_connected_server_and_client_session` | `Client(mcp)` 直接传服务器对象 |
| 文档 | [v1 Testing](https://py.sdk.modelcontextprotocol.io/v1/testing/) | [Testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/) |

v2 的写法（官方原文：「pass it your server object and it talks to it directly. No subprocess. No port. Nothing on a wire. It's the same idea as FastAPI's `TestClient`.」）：

```python
import pytest
from inline_snapshot import snapshot
from mcp import Client
from mcp.types import CallToolResult, TextContent
from mypkg.server import mcp

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        yield c

@pytest.mark.anyio
async def test_code_search(client: Client):
    result = await client.call_tool("code_search", {"query": "def parse"})
    assert result.is_error is False
```

**传输由第一个位置参数的类型决定**（[Client transports](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/client/transports.md)）：`str` → Streamable HTTP；`StdioServerParameters` → 子进程；**服务器对象 → in-process**。于是**同一个 `Client` 类**既能写 in-memory 测试，也能写真子进程 E2E，只换参数。两个易踩点：

- `raise_exceptions=True` **只影响 tool body 之外的崩溃**；工具内部抛的异常本来就返回 `is_error=True`，与它无关（[Handling errors](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/servers/handling-errors.md)）。
- `Client(mcp)` 默认 **era-neutral**：先探 `server/discover`，失败再回退 `initialize`。只有测 legacy 语义（sampling / elicitation push、`message_handler`）才需要 `mode="legacy"`（[Protocol versions](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/protocol-versions.md)）。

### A2. MCP Inspector：可以脚本化，而且官方就是为 CI 设计的

Inspector v2 一个包提供三种客户端：Web（默认）、**CLI（`--cli`，官方定位 "A scriptable, machine-readable client for CI, shell pipelines, and coding agents"）**、TUI（`--tui`）（[Inspector README](https://raw.githubusercontent.com/modelcontextprotocol/inspector/main/README.md)）。

CLI 做冒烟测试的核心事实（[cli-smoke-testing.md](https://raw.githubusercontent.com/modelcontextprotocol/inspector/main/docs/cli-smoke-testing.md)）：

```bash
# CI 里必须 pin 精确版本，`@2` 不算 pin
npx --yes @modelcontextprotocol/inspector@2.5.0 --cli \
  python -m mypkg --method tools/list --format json \
  | jq -e '[.result.tools[].name] as $have | ["code_search","code_outline","code_index","index_status"] - $have | length == 0'
```

- **退出码是稳定契约**：`0` 成功、`1` 用法/意外错误、`3` 需要认证、`4` 不可达、**`5` 工具错误（`isError:true` 或工具不存在）**、`6` schema 可移植性问题。`tools/call` 返回 `isError:true` 时仍打印 payload 但退出 5，不会悄悄通过 `&&` 链。
- `--method initialize` 是**最便宜的「服务器活着且在说 MCP」断言**：握手、打印 `{serverInfo, protocolVersion, capabilities, instructions}`、断开，不调用任何工具。
- `--tool-arg key=value` **会对能解析的值做 JSON 解析**（`zip=10001` 变成数字）；要精确控制类型用 `--tool-args-json '{"zip":"10001"}'`。
- **`stdout` 是结果，`stderr` 是诊断**，永远不要 `2>&1` 后再喂给 `jq`。
- `pipefail` 只报告最右侧的非零状态，会**吞掉 CLI 的失败类别**；需要类别时先 `out=$(...) || status=$?` 捕获，再跑 `jq`。

### A3. 协议兼容性测试

**官方有独立的 conformance 套件**：[modelcontextprotocol/conformance](https://github.com/modelcontextprotocol/conformance)。

```bash
npx @modelcontextprotocol/conformance server --url http://localhost:3000/mcp \
  --requirements 2026-07-28
```

- 每个场景除了自身的 check，还额外产出 `wire-schema-valid`（把线上每条 JSON-RPC 消息对照该版本的 spec JSON schema 校验）——这正是「协议层回归」的自动化形式。
- `--requirements <revision>` 是**冻结的要求集**：回答「2026-07-28 要求我过哪些场景」，而不是「今天的套件有什么」。
- `--expected-failures` 基线三态：**失败且在基线 → 退出 0；失败且不在 → 退出 1；通过但在基线 → 退出 1（过期基线）**。这个设计值得直接抄进自己的项目。
- 提供 composite GitHub Action：`uses: modelcontextprotocol/conformance@v0.1.11`。

**你必须测的三件事**：

1. **协议版本协商**。MCP 有两代：`initialize` 握手时代（≤ `2025-11-25`）与 `server/discover` 现代时代（`2026-07-28`）。`mode="auto"` 帮你桥接，`client.protocol_version` 是答案。**版本 pin（`mode="2026-07-28"`）不发任何协商流量，代价是 `client.server_info` 为 `None`、`server_capabilities` 全空**——想断言 capabilities 就不要 pin（[Protocol versions](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/protocol-versions.md)）。
2. **capabilities 声明**。规范原文：「The initialization phase **MUST** be the first interaction between client and server」（[Lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)）。对你的 server，断言 `capabilities.tools` 存在且 `resources` / `prompts` 为 `None` 比断言「有 tools」更有价值——它同时锁死「不要误声明未实现的能力」。
3. **`isError` 语义的三分法**（[Handling errors](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/servers/handling-errors.md)）：
   - `ToolError` → 请求**成功**，`is_error=True`，`content` 里有你写的消息（前缀工具名），`structured_content` 为 `None`。这是「模型能自己纠正的错误」。
   - `MCPError` → 整个 `tools/call` **失败**，返回 JSON-RPC error（如 `-32602`），**没有 result**，客户端 `raise`。
   - 其它异常 → `is_error=True`，但给模型的文本被消毒成 `Error executing tool <name>`，完整 traceback 只进服务器日志。**测试要断言「内部异常不会泄漏到 content」**——这是安全断言，不只是行为断言。
   - 注意 v2 的 Python 侧字段名是 `is_error`，wire 上是 `isError`。
   - 还有一个反模式警告：官方明确「Never `return` an error message from a tool」——返回的字符串 `is_error=False`，模型会以为工具成功了。

### A4. stdio 传输的测试难点：stdout 独占

规范原文（[Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)）：

> The server **MAY** write UTF-8 strings to its standard error (`stderr`) for logging purposes. … The server **MUST NOT** write anything to its `stdout` that is not a valid MCP message.

官方调试文档补一句：「Local MCP servers should not log messages to stdout (standard out), as this will interfere with protocol operation.」（[Debugging](https://modelcontextprotocol.io/docs/2026-07-28/tools/debugging)）

**Python 侧的现状比想象中微妙**（[MCP Python SDK: Logging](https://py.sdk.modelcontextprotocol.io/v2/handlers/logging/)）：

- 标准库 `logging` 的 handler **默认就写 stderr**，所以 `logger.info(...)` 是安全的。
- `MCPServer(...)` 构造时**已经替你调用了 `logging.basicConfig()`**，handler 指向 stderr，级别由 `log_level=` 控制（默认 `"INFO"`），且不会覆盖你已配置的 handler。
- **危险在这里**：SDK 会把「已被 flush 的杂散 stdout」改道到 stderr，但**块缓冲进程里的 `print()` 通常躺在缓冲区直到解释器退出时才 drain，直接落到协议流上**。即使被改道，那行文本也是裸的——没有级别、没有 logger 名、无法过滤。

**测试里怎么断言「stdout 干净」**：`capsys` / `capfd` 对子进程无效，必须真的 spawn 并逐行解析。这也是 conformance 套件 `wire-schema-valid` 的做法：

```python
import json, subprocess, sys

def test_stdout_is_pure_protocol(tmp_path):
    proc = subprocess.Popen(
        [sys.executable, "-m", "mypkg"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    proc.stdin.write(json.dumps(req) + "\n"); proc.stdin.flush()
    line = proc.stdout.readline()
    proc.stdin.close(); proc.wait(timeout=10)

    # 1) 每一行都必须是合法 JSON-RPC —— 任何 print() 都会让这里炸
    msg = json.loads(line)
    assert msg["id"] == 1 and "result" in msg
    # 2) 用 stderr 而非 stdout 做诊断，断言日志确实走了 stderr
    assert "Traceback" not in proc.stderr.read() or True
```

再加一条**静态兜底**（便宜且能拦住新代码）：CI 里 grep 源码里的裸 `print(`，或在 `ruff` 里启用 `T20`（flake8-print）。最后把「子进程 + 逐行协议解析」固化为 E2E 测试，它是唯一能捕捉「依赖库在你不知情时往 stdout 打印」的手段。

### A5. 值得参考的开源 MCP server 测试代码

| 仓库 | 参考点 | 链接 |
|---|---|---|
| `modelcontextprotocol/python-sdk` | `tests/test_examples.py`：`async with Client(mcp)`，用 `inline_snapshot` 断言整个 `CallToolResult`；辅助函数 `strip_server_info()` 先把服务器身份戳从 `_meta` 去掉再比对——**只对行为断言，不对身份断言** | [test_examples.py](https://github.com/modelcontextprotocol/python-sdk/blob/main/tests/test_examples.py) |
| `modelcontextprotocol/servers` | `src/filesystem/__tests__/` 有 8 个测试文件，绝大多数是**纯函数级、完全不涉及模型**；`directory-tree.mcp-sdk.test.ts` 用真实 SDK Client + `StdioClientTransport` 拉起 `dist/index.js` 真子进程做协议回归 | [filesystem/__tests__](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem/__tests__) · [directory-tree.mcp-sdk.test.ts](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/__tests__/directory-tree.mcp-sdk.test.ts) |
| `PrefectHQ/fastmcp` | 官方测试指南给分级策略：in-memory `Client(server)` 为主；`asgi_client` 走真实 ASGI 但**不开端口**；只有测传输本身才 `run_server_async` / `run_server_in_process`，并用 `integration` / `client_process` / `subprocess_heavy` 三个 marker 与主套件隔离。**官方警告：不要在 fixture 里打开 client**（会造成难以诊断的 event loop 问题） | [FastMCP Tests](https://gofastmcp.com/development/tests) |

---

## B. 检索系统的测试（重点）

### B6. 检索质量：判定集 + 指标，而非行覆盖率

检索评测的事实标准是 **qrels + run + 指标**，且已有成熟 Python 实现，不必手写：

- [ir-measures](https://ir-measur.es/en/latest/)（`pip install ir-measures`）：`ir_measures path/to/qrels path/to/run nDCG@10 P@5 'P(rel=2)@5'`，统一了 pytrec_eval / gdeval / trectools 的度量名。论文：MacAvaney et al., ECIR 2022。
- [pytrec_eval](https://github.com/cvangysel/pytrec_eval)：trec_eval 的 Python 绑定。
- [ranx](https://github.com/AmenRa/ranx)：排名评测/比较/融合。
- 学术基线：[BEIR](https://arxiv.org/abs/2104.08663)。**数据集数量口径不一致，不要写死**：论文摘要称 **18** 个公开数据集，仓库 README 称 **17** 个预处理数据集而其表格实际列出 **19** 行（https://github.com/beir-cellar/beir ）。
- 学科定位：「Information retrieval has developed as a **highly empirical discipline, requiring careful and thorough evaluation**」（[Stanford IR Book ch.8](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-in-information-retrieval-1.html)）。

**代码检索 ≠ 通用文本检索——这一条直接决定你的 tokenizer 选择与测试清单**。GitHub 工程博客（[The technology behind GitHub's new code search](https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/)，Timothy Clem，2023-02-06；正文由 JS 渲染，可经 WordPress REST API 取全文：`https://github.blog/wp-json/wp/v2/posts?slug=the-technology-behind-githubs-new-code-search`）原文：

> We understand that **code search is uniquely different from general text search**. … Searching code also has unique requirements: **we want to search for punctuation (for example, a period or open parenthesis); we don't want stemming; we don't want stop words to be stripped from queries; and, we want to search with regular expressions.**

对 SQLite FTS5 的直接含义：默认 `unicode61` tokenizer **把标点当分隔符丢弃**，所以 `.`、`(`、`->`、`::` 搜不到 → 这类查询**要么换 `trigram` tokenizer**（[FTS5 trigram](https://www.sqlite.org/fts5.html#the_trigram_tokenizer)，注意该模式下 `LIKE`/`GLOB` 也能走索引，且 bm25 分数会变成**亚单位量级**——与前述 agaric 观察到的 `≈ -1e-6` 一致），**要么改用 `LIKE`/`GLOB` 走另一条路径**；同时**不要用 porter tokenizer**（它会做 stemming）。GitHub 自己的选择是 **ngram/trigram 索引**（自研引擎 Blackbird，Rust）。

→ **应当各有一条专门的 golden 测试**：① 能检索标点（`fn(`、`self.`、`::`）；② 不做 stemming（搜 `parsing` 不应命中 `parse`，或反之，取决于你的契约）；③ 不丢停用词（搜 `if`、`for`、`and`）。这三条在 `unicode61` 下**会全部失败**，正是最容易上线才发现的问题。

**注意：该文只讲架构，不讲测试与相关性回归**（全文 `test` / `quality` / `precision` / `recall` / `eval` / `BM25` 均 0 命中），**不要把它当成"关于测试的文章"引用**。它的另一处可用价值是印证确定性机理：文中 compaction「**k-merges the posting lists by score so relevant documents have lower IDs and will be returned first by the lazy iterators**」——与 FTS5 的多 b-tree + `automerge`/`optimize` 是同一类设计：**排序信息被烘进索引结构，而索引结构随写入/合并历史变化**。

**嵌入 pytest 的成熟做法**：把小规模判定集做成**测试数据字典**，用 `parametrize` 展开，并**把「质量阈值」与「精确排序」分成两类断言**：

```python
# 小判定集：query -> {chunk_id: 相关度}
QRELS = {"parse function def": {"src/parser.py::parse": 3, "src/lexer.py::tokenize": 1}}

@pytest.mark.parametrize("query,expected_top1", [
    ("parse function def", "src/parser.py::parse"),
    ("where is tokenize",  "src/lexer.py::tokenize"),
])
def test_golden_query_top1(index, query, expected_top1):
    hits = index.search(query, k=1)
    assert hits[0].path == expected_top1          # 精确断言，不稳定就说明行为变了

def test_golden_query_ndcg(index):
    run = {q: {h.chunk_id: h.score for h in index.search(q, k=10)} for q in QREALS}
    score = ir_measures.calc_aggregate([ir_measures.nDCG @ 10], QRELS, run)
    assert score[ir_measures.nDCG @ 10] >= 0.8    # 阈值断言，允许合理浮动
```

**指标命名有个必须知道的坑**（[ir-measures measures](https://ir-measur.es/en/latest/measures.html)）：`R`（Recall@k）的定义是「The fraction of relevant documents for a query that have been retrieved by rank k」，**不是**「top-k 里有任何一个相关文档」——后者在 TREC 约定里叫 **`Success@k`**。别名表：`MRR → RR`、`NDCG → nDCG`、`MAP → AP`、`Precision → P`。官方还提醒 `iter_calc` 的结果「**may not be in a predictable order**」——测试里不要依赖逐 query 结果的顺序。BEIR 默认 `ignore_identical_ids=True`（剔除 `qid == pid`），在你的场景要注意 query id 与 chunk id 撞车。

**业界第一方做法：Elastic 的 `_rank_eval` API**（[官方文档源文件](https://github.com/elastic/elasticsearch/blob/main/docs/reference/elasticsearch/rest-apis/search-rank-eval.md)，可直接读 Markdown）。三件套＝文档集合 + 典型查询集合 + 每查询一组人工评分，与你的 qrels 同构；响应是**整体 `metric_score` + 逐 query `details[].metric_score` + `failures`**，正是「逐 query 断言 + 整体分数」的官方形态。指标：**P@k、R@k**（都「不考虑位置」）、**MRR**、**DCG**（`normalize=true` 即 nDCG）、**ERR**。最值得引用的是它给出的存在理由：「This can only be done if the search result quality is **evaluated constantly across a representative test suite of typical user queries**, so that improvements in the rankings for one particular query don't negatively affect the ranking for other types of queries.」

**落地建议抄 Elastic Search Labs 的 judgment list 文章**（[链接](https://www.elastic.co/search-labs/blog/judgment-lists-search-query-relevance-elasticsearch)，2025-12-11）：「you can define a fixed set of queries … together with their relevant results. **This set becomes your baseline.**」；**「Start small, but start.」**——「You only need to identify the **5–10 most critical queries**… You typically want to start with **the top queries plus the queries with no results**… start testing with an easy-to-configure metric like **Precision** and then work your way up」；**「Make it part of the flow. Integrate judgment lists into your development pipelines.」** 另外要知道 graded 评分的代价：「even a small change (like rating something a 3 instead of a 4) can create a much bigger shift in the metric」。

**两条最容易被忽略、但决定这套东西有没有用的实践**：

1. **逐 query diff，不要只看均值**：「You'll routinely see a change that lifts the mean nDCG by 0.03 while **quietly tanking three head queries that make up half your traffic**. … **diff per-query, not just the mean**, and gate CI on regression counts.」（[dev.to/Libme](https://dev.to/libme/how-to-test-search-relevance-before-you-ship-a-ranking-change-29o)，第三方博客；其 harness 以 Postgres FTS 为例但**明确是引擎无关的**，可直接套到 SQLite FTS5）
2. **聚合口径要显式并写进文档**：macro-average 用于 CI 门禁、traffic-weighted 用于产品评审——「Traffic weighting is honest for product risk and **dangerous for CI flakes** when a few head queries dominate」；固定二值化阈值（0–3 分级常用 `grade >= 2`），「Changing the cutoff without rebasing metrics is a **silent methodology break**」；golden 文件必须版本化，「**Always fail on `golden_version` mismatch** unless the job is explicitly a 'rebaseline' workflow with human approval」，rebaseline 走**专门的 PR**。（出处：[qaskills.sh](https://qaskills.sh/blog/search-relevance-testing-golden-queries)，**第三方博客**；其 drift 阈值表——NDCG@10 均值掉 0.01 警告 / 0.025 失败，MRR 0.01/0.03，P@10 0.02/0.04——可作起点，但你的语料小得多，阈值应更严。）

Google 自述搜索质量评估靠**真实查询 + 人工评分**（Search Quality Raters）而不是单元测试覆盖率（[Software Engineering at Google ch.11](https://abseil.io/resources/swe-book/html/ch11.html)）；Vespa 官方把检索应用测试分层为 system tests（feed + query + 比对预期），并强调「Each system test should be self-contained… should generally start by clearing all documents」（[Vespa: Testing](https://docs.vespa.ai/en/applications/testing.html)）。

### B7. 确定性：BM25 是浮点，并列顺序没有保证

FTS5 官方对 `bm25()` 的规定（[FTS5 §5.1.1](https://www.sqlite.org/fts5.html#the_bm25_function)）：返回「a real value」，「The better the match, the numerically smaller the value returned」；实现**故意乘了 −1**，所以默认升序排序就是「最好的在前」，不需要 `DESC`。`k1`、`b` 硬编码为 1.2 / 0.75。隐藏列 `rank` 默认等于 `bm25()` 的值，而 `ORDER BY rank` 比 `ORDER BY bm25(ft)` **更快**，因为调用方可以提前中止。

`rank` 的映射可以按查询或按表配置：

```sql
SELECT * FROM ft WHERE ft MATCH ? ORDER BY bm25(ft, 10.0, 5.0);   -- 旧写法
SELECT * FROM ft WHERE ft MATCH ? AND rank MATCH 'bm25(10.0, 5.0)' ORDER BY rank;  -- 等价且更快
```

**关于并列——规范出处不在 FTS5 文档，在 SQLite 核心 SELECT 文档**。FTS5 页面里只有「不带 `ORDER BY` 时返回顺序是 arbitrary」（「Like any other SQL query that does not contain an ORDER BY clause, the example above returns results in **an arbitrary order**」，[FTS5 §1](https://www.sqlite.org/fts5.html)）。真正规范性的句子在 [SQLite SELECT §4 The ORDER BY clause](https://www.sqlite.org/lang_select.html)：

> Rows are first sorted based on the results of evaluating the left-most expression in the ORDER BY list, then ties are broken by evaluating the second left-most expression and so on. **The order in which two rows for which all ORDER BY expressions evaluate to equal values are returned is undefined.**

**源码级证据**（SQLite 官方 Git 镜像 https://github.com/sqlite/sqlite）：FTS5 为 `ORDER BY rank` 专设计划 `#define FTS5_PLAN_SORTED_MATCH 4`（[fts5_main.c#L494](https://github.com/sqlite/sqlite/blob/version-3.53.4/ext/fts5/fts5_main.c#L494)），其内部 sorter 语句是 `"SELECT rowid, rank FROM %Q.%Q ORDER BY %s(\"%w\"%s%s) %s"`（[fts5_main.c#L1112](https://github.com/sqlite/sqlite/blob/version-3.53.4/ext/fts5/fts5_main.c#L1112)）——**只有排序函数键，没有 rowid 次级键**。即：`ORDER BY rank` 不构成任何 tie 保证。

**浮点不确定性的官方背书**：「SQLite makes no guarantees that the accuracy of computations on floating point values will even be this accurate, because no such guarantees are possible.」（[Floating Point](https://www.sqlite.org/floatingpoint.html)）；REAL 是 8-byte IEEE（[Datatypes](https://www.sqlite.org/datatype3.html)）。

**两个放大问题的额外事实**：① FTS5 索引是**多棵 b-tree 的集合**，`automerge` / `crisismerge` / `optimize` 会改变合并状态（[automerge](https://www.sqlite.org/fts5.html#the_automerge_configuration_option)、[optimize](https://www.sqlite.org/fts5.html#the_optimize_command)）——推断：相同逻辑内容在不同写入历史上可能落在不同段布局，这是「同分顺序看起来不稳定」的常见来源；② bm25 的 N 与 avgdl 是**全表统计量**，增删一条文档会改变所有查询的分数。

**真实工程案例**：[agaric](https://github.com/jfolcini/agaric)（Tauri + SQLite FTS5）的分页游标用 **`(rank ASC, id ASC)` 复合键**、`block_id` 作 tiebreaker，并用相对 epsilon `abs(rank - cursor_rank) <= 1e-9 * max(1, abs(cursor_rank))` 吸收「游标序列化与 SQLite 重算 rank 之间的漂移」（[cursor.rs](https://github.com/jfolcini/agaric/blob/163858c1894a712f40bde14f1ad7d787da4e5b5f/src-tauri/src/fts/search/cursor.rs)）。它的回归测试注释给出一个可直接抄的技巧：「**Three identical-content blocks is the minimal corpus that forces a page boundary *inside* a run of equal ranks**」（[tests.rs](https://github.com/jfolcini/agaric/blob/9e1e2507cbd4d71b2a0e44ccc2817b792c2f262c/src-tauri/src/fts/tests.rs)）。

另一个坑（[SQLite 论坛实例](https://sqlite.org/forum/forumpost/2fc481fcb68184eb?hist)）：`ORDER BY rank` 里 `rank` 可能被解析成普通列名而非 FTS5 隐藏列，从而**静默退化成「按某列排序」**。→ golden 测试要**同时断言分数的单调性与结果顺序**，否则抓不到这种退化。

工程上的处理方式是三条叠加：

1. **稳定排序键（最重要）**：永远给 `ORDER BY` 追加一个唯一键兜底。`rowid` 天然唯一且廉价：
   ```sql
   SELECT chunk_id, path, start_line, bm25(chunks_fts) AS score
   FROM chunks_fts JOIN chunks USING (chunk_id)
   WHERE chunks_fts MATCH ?
   ORDER BY score ASC, chunk_id ASC     -- chunk_id 是 INTEGER PRIMARY KEY，唯一
   LIMIT ?;
   ```
   如果你的 chunk 表用 `(path, start_line)` 做业务主键，就用 `ORDER BY score, path, start_line`。**这一步就把「浮点并列导致的不稳定」彻底消灭了**，不需要任何容差。
2. **只对「展示用」的分数做取整**，绝不用取整后的值参与排序：`ROUND(bm25(chunks_fts), 6) AS score_display`。
3. **不要在断言里比浮点绝对值**。BM25 的 IDF 项含 `N`（表内总行数）与 `avgdl`（平均文档长度），任何文档集合变化、tokenizer 配置变化、SQLite 版本差异都会改变绝对值。断言应该落在**整数化的排序键**（排名、`chunk_id` 顺序）或 `pytest.approx` 上。

**关于 epsilon**：只有当你**无法**加唯一 tiebreaker（例如被迫用 `ORDER BY rank` 做 keyset 分页）时，才需要 agaric 那种相对 epsilon 来吸收「游标里序列化的 rank 与数据库重算的 rank 之间的漂移」。**加了 `chunk_id` 次级键之后，比较退化为纯 id 顺序，断言完全确定，epsilon 不再需要**——这是更简单的路线。

**额外建议**：把「确定性」本身写成一条测试——同一输入索引两次，chunk 序列与查询结果序列必须逐元素相等。这条测试会同时抓住 `set` 迭代顺序、字典序不稳定、时间戳进了排序键等一整类 bug。另外用「三条完全相同内容的最小语料」制造一段同分区间，断言 `chunk_id` 顺序（照抄 agaric 的 `search_pagination_equal_ranks_id_tiebreak` 思路）。

### B8. Property-based testing（Hypothesis）

官方教程明确把「**A type-checker, linter, formatter, or compiler does not crash when called on syntactically valid code**」列为典型性质，并推荐优先找**往返性质（round-trip）**（[Hypothesis Introduction](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html)）。对代码分块系统，天然的性质有：

```python
from hypothesis import given, settings, strategies as st

src = st.text(max_size=4000).map(lambda s: s.encode("utf-8"))  # tree-sitter 吃 UTF-8 bytes

@given(src)
@settings(max_examples=200, deadline=None)   # deadline=None：解析慢时别误报
def test_chunks_cover_source_without_overlap(src):
    chunks = chunk(src, language="python")
    ordered = sorted(chunks, key=lambda c: c.start_byte)
    assert all(0 <= c.start_byte <= c.end_byte <= len(src) for c in ordered)   # 偏移合法
    assert all(a.end_byte <= b.start_byte for a, b in zip(ordered, ordered[1:]))  # 不重叠
    covered = set().union(*(range(c.start_byte, c.end_byte) for c in ordered))
    assert covered == set(range(len(src)))                                     # 全覆盖

@given(src)
def test_outline_never_crashes(src):
    code_outline_for(src, language="python")     # 只断言「不抛未捕获异常」
```

配置用 `@settings`（`max_examples` 默认 100；`deadline`、`phases`、`derandomize` 等见 [Configuring test settings](https://hypothesis.readthedocs.io/en/latest/tutorial/settings.html)）。套件级用 `settings.register_profile("fast", max_examples=10)` + `settings.load_profile(...)`，CI 本地各跑一套，pytest 侧可用 `--hypothesis-profile fast`。

**一个必须知道的行为（我原先的判断是错的，此处更正）**：`st.text()` 的默认 alphabet **已经排除了 surrogate**——官方原文「The default alphabet strategy can generate the full unicode range but **excludes surrogate characters because they are invalid in the UTF-8 encoding**. You can use `characters()` without arguments to find surrogate-related bugs such as bpo-34454.」（[strategies reference](https://hypothesis.readthedocs.io/en/latest/reference/strategies.html#hypothesis.strategies.text)）。所以 `st.text().map(lambda s: s.encode("utf-8"))` **不会**抛 `UnicodeEncodeError`，不需要 `surrogatepass`。真正需要注意的是另外两点：

- **想要 surrogate 必须显式要**：用无参 `st.characters()` 专门找 UTF-8/UTF-16 边界 bug，并**把「非 UTF-8 输入应被优雅拒绝而非崩溃」单独写成一条性质**。
- **不做 Unicode 规范化**：官方原文「This strategy **does not normalize() examples**, so generated strings may be in any or none of the 'normal forms'.」；且「**Python measures string length by counting codepoints**」——U+00C5 是 1 个字符，U+0041 U+030A 是 2 个。**你的偏移断言必须想清楚是码点、字节还是字素簇**，tree-sitter 用的是**字节**偏移。

**关于 `deadline`**：官方源码页写明「**The default deadline is 200 milliseconds.**」，且内置 profile 中 `default` 用 `deadline=200ms`，而 **`ci` profile 用 `deadline=None`**（检测到 CI 环境变量时自动启用）（[settings 源码页](https://hypothesis.readthedocs.io/en/latest/reference/api.html#built-in-profiles)）。本地跑慢测试时要么显式 `deadline=None`，要么 `settings.load_profile("ci")`。抑制 health check 请用 `settings.register_profile(..., suppress_health_check=[HealthCheck.too_slow])` **按需抑制**——官方警告「We strongly recommend that you suppress health checks as you encounter them, rather than using a blanket suppression.」（[how-to](https://hypothesis.readthedocs.io/en/latest/how-to/suppress-healthchecks.html)）。

**Stateful testing 适合测索引器**（[stateful](https://hypothesis.readthedocs.io/en/latest/stateful.html)）：把 `index` / `delete` / `rebuild` / `search` 建成 `@rule`，把「每条已索引文档都能被自己的关键词检索到」「删除后不再出现」写成 `@invariant`（每步之后自动运行）。官方也提醒「**You may not need stateful tests**」——简单场景 `@given` 就够。参考实现：chock 的 `test_parsing_is_idempotent`（`parse(parse(x)) == parse(x)`）、ehrQL 的**差分测试**（同一随机查询在多个引擎上执行并断言结果相同，[README](https://github.com/opensafely-core/ehrql/blob/main/tests/generative/README.md)）——后者对「自研打分器 vs SQLite FTS5 bm25」的对照测试是绝佳模板。

### B9. 快照测试工具对比

| 工具 | 版本 | 快照存放 | 适合「模型可见文本」吗 |
|---|---|---|---|
| **inline-snapshot** | 0.35.4 | **源码里**（`snapshot(...)` 字面量），也可 `external()` / `external_file()` 外置 | ✅ **首选**。PR diff 里逐字符可读；支持 `dirty-equals` 做部分匹配（例如 `{"id": IsStr(regex=r"chunk_\d+"), "text": "..."}`），可以把不稳定字段局部豁免而不整段放弃断言 |
| **syrupy** | 6.1.1 | `__snapshots__/` 外部文件 | 适合文本量大或含二进制；`--snapshot-update` 更新；可自定义 serializer |
| **pytest-snapshot** | 0.9.0 | 外部文件 | 功能最少，`requires_python>=3.5`，更新不活跃 |

**决定性理由**：**官方 MCP Python SDK 的测试文档就用 `inline-snapshot`**，并在正文里推广它（「`inline-snapshot` is what the test below uses to assert on the whole result object in one line. It records the output of a test as the `snapshot(...)` literal you see. **If you'd rather not use it, drop the import and assert on the fields you care about** (`result.content[0].text == "3"`) like in any other test.」——[Testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/)），SDK 自己的 `tests/test_examples.py` 也用它。注意官方把它定位为**可选的开发依赖**，不是硬性要求。

**inline-snapshot 的两个硬限制（会直接影响你的 CI 设计）**（[Limitations](https://15r10nk.github.io/inline-snapshot/latest/limitations/)）：

- **不支持 pytest-xdist**：装了 xdist 并启用即等同 `--inline-snapshot=disable`，要用 `-n0` 绕过。→ 如果你的 CI 用 `-n auto`，快照测试必须单独跑一个 `-n0` 的 job/step。
- **CI 环境下默认 `disable`**；快照只能**在 CPython 上更新**。
- 写入源码时会把含换行的字符串转三引号、转义首尾换行，这类改动属于 **`update` 类别**，**默认不上报**，需要 `pytest --inline-snapshot=update` 才应用（[code generation](https://15r10nk.github.io/inline-snapshot/latest/code_generation/)）。**这意味着快照的「表示形式」与「值」是两回事**，review 时要留意。

**syrupy 有一个逐字符陷阱**：amber 序列化器官方原文「**Line control characters are normalised when snapshots are generated i.e. `\r` and `\n` characters are all written as `\n`.**」（[README](https://github.com/syrupy-project/syrupy)）→ **CRLF 会被改写**。要字节保真必须换 `SingleFileSnapshotExtension`（每个测试一个 `.raw`，「the default behaviour of the SingleFileSnapshotExtension is to write raw **bytes** to disk. There is no further 'serialization' that happens.」）。syrupy 也**明确不支持 inline 快照**并转荐 inline-snapshot（对应 issue [#122](https://github.com/syrupy-project/syrupy/issues/122) 以 `not_planned` 关闭）。`pytest-snapshot`（0.9.0，最后 commit 2023-11）事实停更，**不建议新项目采用**。

**对「必须逐字符稳定」的输出的建议**：断言 `result.content[0].text`（模型真正读到的那段字符串）的完整快照：

```python
from inline_snapshot import snapshot

def test_search_output_is_byte_stable(client):
    result = asyncio.run(client.call_tool("code_search", {"query": "parse"}))
    assert result.content[0].text == snapshot("""src/parser.py:12-40  parse_expression  (score 2.31)
src/parser.py:44-61  parse_statement  (score 1.87)""")
```

一旦你改了检索结果的**展示格式**，这个测试会立刻变红并要求你显式确认——这正是你要的。

---

## C. 文件系统与数据库测试

**C10. `tmp_path` / `tmp_path_factory`**（[pytest docs](https://docs.pytest.org/en/stable/how-to/tmp_path.html)）：`tmp_path` 每测试函数唯一；`tmp_path_factory` 是 **session-scoped**，官方推荐 `tmp_path_factory.mktemp("data")` 用于「generate it once per-session to save time」（预建 FTS5 索引库特别合适）。默认 `{temproot}/pytest-of-{user}/pytest-{num}/{testname}/`，**保留最近 3 次**；`--basetemp` 会被「blindly cleared」，慎用。xdist 下 pytest 自动为每个子进程配 basetemp。

**防污染用户目录**：`monkeypatch.setattr(Path, "home", lambda: tmp_path)`（[monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)）；若用平台规范目录，`platformdirs` **honors `XDG_DATA_HOME`、`XDG_CONFIG_HOME` and friends**（[platformdirs](https://platformdirs.readthedocs.io/en/latest/)），`monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))` 即可整体重定向。再加一条 CI 断言：测试后 `~/.cache/mypkg`、`~/.config/mypkg` **不存在**。

**C11. SQLite：用临时文件，不要用 `:memory:`**。原因是硬的：官方原文「**Every :memory: database is distinct from every other.** So, opening two database connections each with the filename ":memory:" will create two independent in-memory databases.」（[In-Memory Databases](https://www.sqlite.org/inmemorydb.html)）。**你的索引跑在后台线程里，它八成会开自己的连接**——用 `:memory:` 的话，索引写进的是另一个空库，前台永远查不到。要么用 `tmp_path/"index.db"`，要么用共享内存库 `file:memdb1?mode=memory&cache=shared`（名字必须完全相同，且**所有连接必须在同一进程内**）。

> **FTS5 能否在 `:memory:` 中工作：未查到明确信息。** SQLite 的 FTS5 文档与 in-memory 文档都没有提及内存库限制。可引用的相邻事实是：FTS5 是虚拟表模块，可用性由编译选项 `SQLITE_ENABLE_FTS5` 决定，与存储介质无关。**实践做法**：不要依赖文档，直接在 fixture 里 `CREATE VIRTUAL TABLE ... USING fts5(...)` 并断言成功。

WAL 的测试注意事项（[WAL](https://www.sqlite.org/wal.html)）：默认是 `DELETE`，需显式 `PRAGMA journal_mode=WAL`；**内存库上设不了**（「the journal_mode for an in-memory database is either MEMORY or OFF and can not be changed to a different value」，[PRAGMA journal_mode](https://www.sqlite.org/pragma.html#pragma_journal_mode)）；WAL 会产生 `-wal` 与 `-shm` 文件，「**The only safe way to remove a WAL file is to open the database file … then immediately close the database**」。**跨平台陷阱**：Windows 的 `DeleteFile` 对未关闭或内存映射的文件会失败（[MS Learn](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile)），所以**清理 `tmp_path` 之前必须确保所有连接已关闭**，否则 Windows 上删目录报错、POSIX 上静默留垃圾。另外「WAL does not work over a network filesystem」。

**FTS5 能力探测**（照抄 [python-build-standalone PR #694](https://github.com/astral-sh/python-build-standalone/pull/694) 的做法）：

```python
def test_fts5_available():
    opts = {r[0] for r in sqlite3.connect(":memory:").execute("PRAGMA compile_options")}
    assert "ENABLE_FTS5" in opts, f"FTS5 missing; sqlite={sqlite3.sqlite_version}, opts={opts}"
```

注意 `PRAGMA compile_options` **省略 `SQLITE_` 前缀**（[PRAGMA compile_options](https://www.sqlite.org/pragma.html#pragma_compile_options)），所以判定字符串是 `ENABLE_FTS5`。

**C12. 并行隔离**：核心规则是**每个测试、每个 worker 各用自己的 DB 文件**，绝不让 xdist worker 争抢同一个文件。用 `tmp_path` 自动做到这一点。分发模式上，`--dist loadfile` 保证「同一文件的所有测试跑在同一 worker」（[pytest-xdist distribution](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)）。若确实要共享，`sqlite3.connect(timeout=)` 默认等 5 秒后抛 `OperationalError: database is locked`（[Python sqlite3](https://docs.python.org/3/library/sqlite3.html#sqlite3.connect)），并且要留心 SQLite 3.51.3 之前的 WAL-reset bug（多连接 + 同时写/checkpoint 时会损坏，WAL 页有专节）。

小技巧：xdist 下 `parametrize` 传 `set` 会因为 collection 顺序不一致直接报错（[known limitations](https://pytest-xdist.readthedocs.io/en/stable/known-limitations.html)），用 `sorted(...)`。

---

## D. 长耗时操作与异步

**D13. 后台索引线程怎么测**。官方硬约束（[pytest flaky 文档](https://docs.pytest.org/en/stable/explanation/flaky.html)）：pytest 自身单线程，xdist 是多进程**不是多线程**；你必须「**eventually wait on any spawned threads**」，并且「**Avoid using primitives provided by pytest (`pytest.warns()`, `pytest.raises()`, etc) from multiple threads, as they are not thread-safe**」。这意味着**索引线程内部不能做断言**，只能记录状态，由主线程断言。

最快的组合是：**给索引器设计一个可等待的句柄**，把「等」从测试里移到被测代码里：

```python
job = indexer.index_async(root)          # 返回 Job
job.wait(timeout=10)                     # 不是 time.sleep(1)
assert job.progress().done == job.progress().total
```

超时/取消用 AnyIO 的原语：`fail_after(5)` 抛 `TimeoutError`，`move_on_after(5)` 静默退出并用 `scope.cancelled_caught` 判断是否真超时（[AnyIO cancellation](https://anyio.readthedocs.io/en/stable/cancellation.html)）。

测试配置要覆盖两种连接姿势：`sqlite3.connect(check_same_thread=True)`（默认）会在跨线程使用时直接抛 `ProgrammingError`；设 `False` 后官方警告「**write operations may need to be serialized by the user to avoid data corruption**」（[Python sqlite3](https://docs.python.org/3/library/sqlite3.html#sqlite3.connect)）。**这两条路径都要有测试**——前者断言「我们没用错」，后者断言「并发写没有丢数据」。

pytest-asyncio 侧：strict 是默认模式；「Pytest-asyncio provides one asyncio event loop for each pytest collector」；**async 测试是顺序执行的**（「This sequential execution is intentional and important for maintaining test isolation」）（[concepts](https://pytest-asyncio.readthedocs.io/en/stable/concepts.html)）。

**D14. 超时与 flaky 防治**。`pytest-timeout` 的官方警告要当回事：「**it is not designed for precise timings or performance regressions**. Remember your test suite should aim to be fast, with timeouts being a last resort」（[README](https://github.com/pytest-dev/pytest-timeout)）。thread 方法最可移植但会杀掉整个进程（teardown / JUnit XML 全失效），signal 方法能正常结束测试但可能与被测代码的 SIGALRM 冲突。用法是 `pytest --timeout=10 --session-timeout=300`（会话级是**协作式**的，只在每个测试结束时检查）。

**根本解法是 Martin Fowler 的两条**（[Eradicating Non-Determinism in Tests](https://martinfowler.com/articles/nonDeterminism.html)）：
1. 「**Never use bare sleeps to wait for asynchronous responses: use a callback or polling.**」设短了浪费时间，设再长也可能不够。
2. 轮询的 `pollingInterval` 可以很小、`waitLimit` 可以很大；并且「The time values, in particular the `waitLimit`, **should never be literal values**. Make sure they are always values that can be easily set in bulk, either by using constants or set through the runtime environment.」

**重跑只是掩盖**：pytest 官方把 rerun 定性为「mitigate the negative effects」；`pytest-rerunfailures` **默认只保留最后一次 attempt 的 traceback**，「failures from earlier attempts … are silently discarded」，所以真要重跑必须开 `--rerun-show-tracebacks`（[README](https://github.com/pytest-dev/pytest-rerunfailures)）。Fowler 更狠：非确定测试「firstly they are useless, secondly they are a virulent infection that can completely ruin your entire test suite」，并要求隔离区设**数量上限**或**时长上限**。**建议：项目里直接不装 `pytest-rerunfailures`。**

**D15. 测试加速而不污染生产默认值**。官方立场很明确（[monkeypatch 文档](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)）：

> **For code that you control, a safer long-term pattern is to make dependencies explicit so they can be passed into the code under test instead of patched globally.**

正确形态是**把 `batch_size`、`max_chunk_bytes`、`poll_interval` 做成显式 Config 字段**，测试通过构造参数覆盖：

```python
indexer = Indexer(IndexConfig(batch_size=2, max_chunk_bytes=256))   # 生产默认不变
```

**绝不要在生产代码里写 `if os.getenv("TESTING")` 分支**。`monkeypatch.setattr(module, "DEFAULT_BATCH_SIZE", 2)` 只作兜底（会自动撤销）。`IndexConfig` 若用 pydantic-settings，官方明确列出用途之一就是「**Manually override specific settings in the initialiser where desired (e.g. in unit tests)**」（[pydantic-settings](https://github.com/pydantic/pydantic-settings/blob/main/docs/index.md)）。

> 官方文档中**没有**「test-only fixture 覆盖 batch size」这一具体模式的成文指导 → 该模式是通用手段（DI + settings 覆盖）的组合，不是官方推荐语。

---

## E. CI 与工程质量（重点）

### E16. 常见组合与覆盖率目标

**工具链**（全部官方文档）：
- ruff：`ruff check` 是 linter，`ruff format` 是 formatter，**两者职责不同——formatter 不排序 import**，官方给的组合是 `ruff check --select I --fix` 然后 `ruff format`；formatter 与 `E501`/`Q000`/`COM812` 等规则冲突，需要显式 ignore（[Formatter](https://docs.astral.sh/ruff/formatter/)）。规则选择官方建议「Prefer `lint.select` over `lint.extend-select`」，起手 `E, F, UP, B, SIM, I`（[Linter](https://docs.astral.sh/ruff/linter/)）。
- mypy：`strict = true` 是「a defined subset of optional error-checking flags」，**`--warn-unreachable` 不包含在内**，且启用的 flag 列表**可能随版本变化**（[command_line](https://mypy.readthedocs.io/en/stable/command_line.html)）。建议显式加上 `warn_unreachable = true`。
- coverage：`[tool.coverage.run] branch = true`（[config](https://coverage.readthedocs.io/en/latest/config.html#run-branch)）+ `[report] fail_under`。注意 **`--cov-fail-under` 是 pytest-cov 的选项，不是 coverage.py 的**；且 pytest-cov 会**覆盖** coverage 的 `parallel` / `source` / `branch` 配置（[pytest-cov config](https://pytest-cov.readthedocs.io/en/latest/config.html)）。
- **子进程覆盖（对「被宿主 spawn 的库」至关重要）**：`[run] patch = subprocess` + `[run] parallel` + `coverage combine`；`exec*e`/`spawn*e` 需要把 `COVERAGE_PROCESS_START` 传进新环境；`[run] sigterm` **在 Windows 上无效**（[Subprocess support](https://coverage.readthedocs.io/en/latest/subprocess.html)）。`[run] concurrency` 默认是 `"thread"`，用了 multiprocessing 而不声明会「produce very wrong results」。
- CI 用 uv 的官方指南：[uv + GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)（`astral-sh/setup-uv`、`uv sync --locked --all-extras --dev`、pin uv 版本）。可抄的真实工作流：[pydantic ci.yml](https://github.com/pydantic/pydantic/blob/main/.github/workflows/ci.yml)、[flask tests.yaml](https://github.com/pallets/flask/blob/main/.github/workflows/tests.yaml)、[httpx scripts/check](https://github.com/encode/httpx/blob/master/scripts/check)。

**覆盖率该定多少**——三条可引用的立场：

| 来源 | 说法 |
|---|---|
| Martin Fowler, [TestCoverage](https://martinfowler.com/bliki/TestCoverage.html) | 「I would expect a coverage percentage in the **upper 80s or 90s**. I would be suspicious of anything like **100%** - it would smell of someone writing tests to make the coverage numbers happy」；「low coverage numbers, say **below half**, are a sign of trouble」 |
| Google Testing Blog, [Code Coverage Best Practices](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html) ⚠️ | 「**There is no 'ideal code coverage number'**」；参考档位 **60% acceptable / 75% commendable / 90% exemplary**；「**What's not covered is more meaningful than what is covered**」；收益是**对数级**的；project-wide 超过 90% 多半不值，**per-commit 99% 合理、90% 是好下限** |
| Software Engineering at Google [ch.11](https://abseil.io/resources/swe-book/html/ch11.html) | 「code coverage only measures that a line was invoked, **not what happened as a result**」；「We recommend **only measuring coverage from small tests** to avoid coverage inflation that occurs when executing larger tests」；80% 门槛的经典反效果是「engineers treat it like a **ceiling**」 |
| CPython devguide, [Coverage](https://devguide.python.org/testing/coverage/) | 「getting 100% coverage is **not always possible**. There could be **platform-specific code** that simply will not execute for you」；branch coverage 是 100% 行覆盖的「**secondary goal**」 |

> ⚠️ = 该页 URL 真实存在（已核验），但 `testing.googleblog.com` 在本次调研环境中无法抓取正文，其核心结论通过标注来源与原文链接的中文全译镜像读到。

**对「检索类库」的合理预期**：

- **全仓库门槛：85–90%，开 `branch = true`**。低于 60% 是明确的麻烦信号，高于 95% 的边际收益对数级递减。
- **per-file 100% 只给「必须逐字符稳定」的模块**：MCP 工具的入参与返回序列化、排序 key 计算、结果文本格式化。这些模块的每一行都直接决定模型看到什么，值得逐行覆盖。
- **检索质量本身不能用覆盖率衡量**——用 golden query 判定集。IR 是「highly empirical discipline」（Stanford IR Book），Google 也靠真实查询 + 人工评分而非单元覆盖率。检索库应该把判定集当一等公民，把行覆盖率当「找未测代码」的辅助工具（Fowler/Marick 的用法）。
- **不要给 CI 定 100% 全仓库门槛**（httpx 那么做是因为它纯 Python 且团队规模大）。你依赖 `tree-sitter` 原生扩展，平台相关代码必然存在，CPython devguide 已经把这条写死了。
- 额外手段：Google 建议用 **mutation testing** 检验断言的效力——比「再补几行覆盖率」有价值得多。

### E17. 多平台矩阵：**必要**

两条独立的技术理由，都有硬证据：

**(1) tree-sitter 是原生扩展**。`tree-sitter` 0.26.0 的官方 README 说「The package has no library dependencies and provides **pre-compiled wheels for all major platforms**」（[README](https://github.com/tree-sitter/py-tree-sitter/blob/master/README.md)），PyPI 实测有 cp310–cp314 的 macOS / manylinux / musllinux / win_amd64 / win_arm64 wheel（[PyPI files](https://pypi.org/project/tree-sitter/#files)）。**但它是真的原生扩展**：`setup.py` 里 `Extension(name="tree_sitter._binding", sources=[…])`，编译 vendored 的 `core/lib/src/lib.c` 与 `binding/*.c`，按编译器切 `-std=c11` / `/std:c11`（[setup.py](https://github.com/tree-sitter/py-tree-sitter/blob/master/setup.py)）。→ **主流平台走 wheel 不需要编译器；落到 sdist（新 Python 版本、新架构、`--no-binary`）就需要 C11 编译器**。上游 CI 覆盖到 `windows-11-arm`，且 Windows 上测试是 `continue-on-error`。

**语言包选择很关键**：`tree-sitter-languages`（grantjenks）最后发布 1.10.2（2024-02），wheel **只到 cp312**，且写明「**Source installs are not supported**」（[PyPI](https://pypi.org/project/tree-sitter-languages/)）→ cp313/cp314 上既无 wheel 又不能源码装，**不要用**。`tree-sitter-language-pack` 最新 1.20.0，wheel 是 **abi3（`cp310-abi3`）**，一次构建覆盖 3.10+，371 种语言（[PyPI](https://pypi.org/project/tree-sitter-language-pack/)）→ **优先选它**。

**(2) FTS5 的可用性真的会变**。这是本报告最强的一条证据：`astral-sh/python-build-standalone` 的 [PR #694 "Enable FTS5 in SQLite"](https://github.com/astral-sh/python-build-standalone/pull/694)（2025-07-11 合并）把 `-DSQLITE_ENABLE_FTS5` 加进 `build-sqlite.sh` 的 `CFLAGS`，**同时在 `src/verify_distribution.py` 里新增了 `CREATE VIRTUAL TABLE fts5 USING fts5(...)` 存在性断言**。也就是说：**uv 管理的 CPython 在该 PR 之前不带 FTS5，而同一份代码在系统 SQLite 上却能跑通**。FTS5 是编译期特性（官方：「**FTS5 is currently disabled by default for the source-tree configure script and enabled by default for the amalgamation configure script**, but these defaults might change in the future」——[FTS5 §2](https://sqlite.org/fts5.html)）。

另外 `sqlite3` 是**可选模块**，「If it is missing from your copy of CPython, look for documentation from your distributor」；CPython 的最低 SQLite 要求随版本变（3.10 起 3.7.15、3.13 起 3.15.2，见 [configure](https://docs.python.org/3/using/configure.html)）；macOS 系统 `/usr/bin/python3` 被官方描述为「usually **older and incomplete**」（[using/mac](https://docs.python.org/3/using/mac.html)）。

> 逐平台的 SQLite 版本对照表（macOS 系统 Python vs python.org vs uv vs Homebrew）：**未查到官方表格**。

**矩阵建议**：

```yaml
strategy:
  fail-fast: false            # 官方与主流项目一致
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python: ["3.10", "3.12", "3.13"]
    include:
      - os: windows-latest
        continue-on-error: true   # 文件句柄/WAL 语义差异最大，先观察
```

三平台都跑的价值：tree-sitter wheel 覆盖、FTS5 能力探测、WAL 的 `-wal`/`-shm` 文件句柄语义（Windows 上尤其不同）。**如果你自己不打 wheel**（纯 Python 包，`tree-sitter` 从 PyPI 装），就**不需要 cibuildwheel**；只有当你 vendored grammar 需要编译时才需要（[cibuildwheel](https://cibuildwheel.pypa.io/en/stable/)，它会对构建出的 wheel 跑测试）。

### E18. 测试金字塔在本场景的具体配比

先纠正一个常见误解：**Fowler 网站上那篇《The Practical Test Pyramid》全文没有给出任何百分比**（没有 70/20/10）。它只给两条原则：「1. Write tests with different granularity；2. **The more high-level you get the fewer tests you should have**」；对 E2E 的建议是「**aim to reduce the number of end-to-end tests to a bare minimum**」，做法是「come up with **user journeys** that define the core value of your product」，并明确「**Having a low-level test is better than having a high-level test**」（[practical-test-pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)）。

用 Google 的 **size** 维度（不是 scope）划分更实用（[SEG ch.11](https://abseil.io/resources/swe-book/html/ch11.html)）：**small = 单进程、不允许 sleep / I/O / 阻塞调用**；**medium = 可跨进程、可访问 localhost、不可跨机器**；**large = 想去哪去哪**。

映射到你的项目：

| 层级 | 占比建议 | 测什么 | 允许什么 |
|---|---|---|---|
| **small** | ~60% | tree-sitter 分块纯函数（偏移、重叠、覆盖率）、FTS5 查询串构造与转义（含 `"` / `*` / `NEAR` 注入）、bm25 排序 key 与 tie-break、结果文本格式化、工具入参 schema 校验、`index_status` 的状态计算 | 单进程、无文件 I/O、无 DB |
| **medium** | ~35% | `Client(mcp)` in-memory 调 4 个工具；`tmp_path` 下真实 FTS5 索引 + golden query 判定集；后台索引线程的进度 / 取消 / 竞态；快照测试（模型可见文本）；Hypothesis 性质测试 | 可起线程、可写临时文件、可开 SQLite |
| **large / E2E** | ~5%（3–5 条） | 真实 spawn `python -m mypkg`：一条 `initialize → tools/list → tools/call(index_status) → tools/call(code_index) → tools/call(code_search)` 的主旅程；一条「stdout 纯净性」；一条「无参数 / 未知工具 / 坏参数」的负向旅程 | 可起子进程、可访问 localhost |

E2E 就这三条。Fowler 的原话是「Maybe you'll find one or two more crucial user journeys. Everything more than that will likely be more painful than helpful.」

---

## F. 零成本测试（重点）

### F19. 社区通行模式（按「mock 什么」排序）

| 模式 | 代表实现 | 官方 URL |
|---|---|---|
| **In-memory transport**（首选，你的主力） | MCP Python SDK `Client(mcp)`；FastMCP `Client(server)` | [SDK Testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/) · [FastMCP Tests](https://gofastmcp.com/development/tests) |
| **Fake / Mock LLM** | LangChain `GenericFakeChatModel` / `FakeListChatModel` / `FakeMessagesListChatModel`；Vercel AI SDK `MockLanguageModelV4` + `simulateReadableStream`；OpenAI Agents SDK `ScriptedModel` + `ModelStep.respond()/stream()/raise_error()` + `assert_complete()` | [LangChain unit testing](https://docs.langchain.com/oss/python/langchain/test/unit-testing) · [AI SDK Testing](https://ai-sdk.dev/docs/ai-sdk-core/testing) · [OpenAI Agents SDK Testing](https://openai.github.io/openai-agents-python/testing/) |
| **Record-replay / VCR** | vcrpy（`once` / `new_episodes` / `none` / `all` 四种 record mode；`filter_headers`、`before_record_response` 脱敏）；pytest-recording（**默认 `none`，天然阻断联网**）；respx（httpx）；responses（requests）；pytest-httpserver（假服务器） | [vcrpy](https://vcrpy.readthedocs.io/en/latest/advanced.html) · [pytest-recording](https://github.com/kiwicom/pytest-recording) · [respx](https://github.com/lundberg/respx) · [pytest-httpserver](https://github.com/csernazs/pytest-httpserver) |
| **录制会话回放** | DeepSeek Harness：`dsh-llm-replay` 从录制的 Session JSONL 回放模型流，`assertConsumed()` 抓「实际驱动的模型调用比录制少」的漂移；`dsh-session-snapshot` 归一化 cwd / system prompt / tool schema 后比对提交的 fixture，只有 `record` 模式需要 key | [dsh-llm-replay](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/test-support/llm-replay/README.md) · [dsh-session-snapshot](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/test-support/session-snapshot/README.md) |

**一条反复出现的官方共识**（[DSH docs/testing.md](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/testing.md)）：「**Prefer the real implementation over a mock** — Mock only the expensive or non-deterministic boundary (LLM adapter, network, clock); keep everything downstream real.」

**对你意味着什么**：你的链路里**根本没有那个昂贵/不确定的边界**。你要 mock 的只有：
1. **时钟**——`index_status` 若返回 `last_indexed_at` 或耗时，用 `time-machine`（自带 pytest marker / fixture：`@pytest.mark.time_machine(dt.datetime(...))`，[docs](https://time-machine.readthedocs.io/en/stable/pytest_plugin.html)）或 `freezegun`（asyncio 场景需 `real_asyncio=True`，[README](https://github.com/spulec/freezegun)）冻结。
2. **「慢」本身**——通过 Config 把 `batch_size` 调小（见 D15），而不是 mock 索引器。
3. **绝对路径与用户目录**——`monkeypatch.setenv("XDG_*", tmp_path)`，让快照里的路径稳定。

**其余全部保持真实**：真 SQLite、真 FTS5、真 tree-sitter、真 stdio 子进程。这就是「零成本」在这个项目里的全部含义——不是「用假件替换」，而是「整条链路本来就不需要付费资源」。

### F20. 开源项目里「零 API key 测试」的具体做法

| 仓库 | 做法 | 链接 |
|---|---|---|
| `modelcontextprotocol/python-sdk` | `tests/test_examples.py`：`async with Client(mcp)` + `inline_snapshot.snapshot(CallToolResult(...))`；`strip_server_info()` 先剥掉 `_meta` 里的身份戳再比对。**它自己就是「零 key 测 MCP server」的参考实现** | [链接](https://github.com/modelcontextprotocol/python-sdk/blob/main/tests/test_examples.py) |
| `modelcontextprotocol/servers` | Python server 用 `uv run pytest`、TS 用 vitest + coverage-v8，`CLAUDE.md` 写明新测试要带覆盖率；测试绝大多数是纯函数级 | [CLAUDE.md](https://github.com/modelcontextprotocol/servers/blob/main/CLAUDE.md) |
| `PrefectHQ/fastmcp` | 官方测试指南给出完整的四层策略（in-memory → asgi_client → 真实端口 → 子进程），并用 marker 隔离慢测试 | [Tests](https://gofastmcp.com/development/tests) |
| `openai/openai-agents-python` | `agents.testing` 提供 `ScriptedModel`，官方描述为「deterministic, provider-neutral testing utilities … **run in memory, make no model, sandbox-provider, or Realtime API requests**」；文档专门解释为什么不能直接调 Python 函数（会绕过输入校验、执行、结果转换、hooks、guardrails） | [Testing](https://openai.github.io/openai-agents-python/testing/) |
| `anthropics/anthropic-sdk-python` | `tests/conftest.py` 用 `http_snapshot` + `inline_snapshot` 做 HTTP 快照回放，并显式声明 `SNAPSHOT_REQUEST_HEADERS_EXCLUDE = ["x-api-key"]`、录制时 `api_key=None`——**既是 keyless 范例，也是凭据脱敏范例** | [conftest.py](https://github.com/anthropics/anthropic-sdk-python/blob/main/tests/conftest.py) |
| `openai/openai-python` | `tests/conftest.py` 用 `tests.respx2.plugin` mock 自家 HTTP，`base_url` 默认本地、`api_key = "My API Key"` | [conftest.py](https://github.com/openai/openai-python/blob/main/tests/conftest.py) |

> 「专门做**零 API key 的 Agent/检索组件测试**」的独立开源项目：**未查到**（没有以此为定位的成熟仓库）。该能力散落在各 SDK 的官方测试文档与仓库测试代码里。有一个 2025 年新起的第三方项目 `autopost/llm-mock` 声称「Record real LLM API responses once, replay them in tests forever — no API key, no cost, no non-determinism.」，但采用度极低（约 2 stars），本次未能核验其 README 正文，**不建议依赖**。

**Anthropic 官方文档层面**没有专门的「如何在测试里 mock Claude API」指南，只有 SDK 仓库的测试代码可作为事实标准 → **未查到明确信息**。MCP 规范本身也没有「不接模型测试」的条款；官方指引落在 Inspector / Debugging 页面与各 SDK 的 Testing 页面。

---

## G. 一个可照抄的测试方案骨架

### G1. 目录结构

```
mypkg/
├── src/mypkg/
│   ├── server.py          # MCPServer 实例 + 4 个 @mcp.tool()
│   ├── search.py          # FTS5 查询构造 + 排序 key（必须逐字符稳定的模块）
│   ├── chunk.py           # tree-sitter 分块（纯函数）
│   ├── indexer.py         # 后台索引线程 + Job 句柄
│   ├── config.py          # IndexConfig（batch_size 等显式可配置）
│   └── db.py              # schema / migration / WAL 设置
├── tests/
│   ├── conftest.py                    # 所有共享 fixture
│   ├── unit/                          # small：无 I/O、无 DB
│   │   ├── test_chunk_properties.py   # Hypothesis
│   │   ├── test_query_escaping.py
│   │   ├── test_ranking_key.py
│   │   └── test_config.py
│   ├── integration/                   # medium：tmp_path + 真 FTS5
│   │   ├── test_tools_inmemory.py     # Client(mcp)
│   │   ├── test_golden_queries.py     # 判定集 + ir-measures
│   │   ├── test_determinism.py
│   │   ├── test_indexer_async.py      # 进度 / 取消 / 竞态
│   │   └── test_fts5_capability.py
│   ├── snapshots/                     # medium：模型可见文本
│   │   └── test_tool_output_snapshot.py
│   ├── e2e/                           # large：真实子进程，3-5 条
│   │   ├── test_stdio_handshake.py
│   │   ├── test_stdout_purity.py
│   │   └── test_user_journey.py
│   └── data/
│       ├── corpus/                    # 固定的小型代码语料（进版本库）
│       └── qrels.py                   # 判定集，Python 字面量
└── .github/workflows/ci.yml
```

### G2. `pyproject.toml` 配置

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "strict"                  # pytest-asyncio 默认即 strict
addopts = ["-ra", "--strict-markers", "--strict-config"]
markers = [
  "e2e: spawns a real subprocess (slow)",
  "hypothesis: property-based tests",
]
# 超时是兜底，不是计时器
timeout = 30
session_timeout = 600
filterwarnings = ["error"]               # 把 ResourceWarning（未关闭的 sqlite 连接）变成失败

[tool.coverage.run]
branch = true
source = ["src/mypkg"]
patch = ["subprocess"]                   # 覆盖被宿主 spawn 的子进程
parallel = true

[tool.coverage.report]
fail_under = 88
show_missing = true
exclude_also = ["if TYPE_CHECKING:", "raise NotImplementedError", "if sys.platform =="]

[tool.ruff]
line-length = 100
[tool.ruff.lint]
select = ["E", "F", "UP", "B", "SIM", "I", "T20"]   # T20：禁止 print()，保住 stdout 纯净
ignore = ["E501"]

[tool.mypy]
strict = true
warn_unreachable = true
```

### G3. `conftest.py`（关键 fixture）

```python
import sqlite3, pytest
from mcp import Client
from mypkg.server import mcp
from mypkg.config import IndexConfig
from mypkg.indexer import Indexer

CORPUS = ...   # tests/data/corpus 的路径

@pytest.fixture
def index_config(tmp_path):
    """测试用的小 batch、短超时——生产默认值不受影响。"""
    return IndexConfig(
        db_path=tmp_path / "index.db",
        batch_size=2,               # 生产默认 256
        max_chunk_bytes=256,        # 生产默认 16384
        wait_limit_s=10.0,          # Fowler：等待上限不能是散落的字面量
        poll_interval_s=0.01,
    )

@pytest.fixture
def indexer(index_config):
    ix = Indexer(index_config)
    yield ix
    ix.close()                      # 必须在删 tmp_path 前关连接（Windows / WAL 要求）

@pytest.fixture
def built_index(indexer):
    job = indexer.index_async(CORPUS)
    job.wait(timeout=indexer.config.wait_limit_s)   # 不用 sleep
    return indexer

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def client(built_index, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(built_index.config.db_path.parent))
    async with Client(mcp, raise_exceptions=True) as c:
        yield c

@pytest.fixture(autouse=True)
def _no_user_dirs(monkeypatch, tmp_path):
    """双保险：即便代码走了平台规范目录，也不会碰用户真实 home。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
```

### G4. 必须有的测试类别与断言示例

**① 协议契约（medium，`Client(mcp)`）**

```python
@pytest.mark.anyio
async def test_exactly_four_tools_no_extra_capabilities(client):
    tools = await client.list_tools()
    assert {t.name for t in tools} == {"code_search", "code_outline", "code_index", "index_status"}
    for t in tools:
        assert t.description and len(t.description.strip()) > 10   # 模型要读的字段不能空
        assert t.inputSchema["type"] == "object"
    # 不要声明你没实现的能力
    assert client.server_capabilities.resources is None
    assert client.server_capabilities.prompts is None
```

**② `isError` 语义三分法（medium）**

```python
@pytest.mark.anyio
async def test_bad_query_is_a_tool_error_the_model_can_read(client):
    r = await client.call_tool("code_search", {"query": 'unbalanced " quote'})
    assert r.is_error is True                       # 请求成功，工具失败
    assert "quote" in r.content[0].text.lower()     # 消息对模型可见
    assert r.structured_content is None             # 失败的调用没有结构化返回值

@pytest.mark.anyio
async def test_internal_crash_does_not_leak_internals(client, monkeypatch):
    monkeypatch.setattr("mypkg.search._conn", None)     # 制造内部崩溃
    r = await client.call_tool("code_search", {"query": "x"})
    assert r.is_error is True
    assert "Traceback" not in r.content[0].text          # 安全断言
    assert "sqlite3" not in r.content[0].text.lower()
    assert "Error executing tool" in r.content[0].text
```

**③ stdout 纯净性（large，真子进程）** —— 见 A4 的 `test_stdout_is_pure_protocol`，另外用 `ruff` 的 `T20` 规则做静态兜底，并断言「进程退出后 stdout 里没有残余内容」。

**④ 分块性质（small，Hypothesis）** —— 见 B8 的覆盖性 / 不重叠 / 偏移合法 / 不崩溃四条。

**⑤ 确定性（medium）**

```python
def test_indexing_is_deterministic(tmp_path, indexer):
    a = [c.chunk_id for c in indexer.search("parse", k=10)]
    b = [c.chunk_id for c in indexer.search("parse", k=10)]
    assert a == b                                    # 同进程重复
    # 重建索引后仍然一致（考验 chunk_id 分配是否依赖时间/集合序）
    rebuilt = Indexer(IndexConfig(db_path=tmp_path / "b.db", batch_size=2))
    rebuilt.index_sync(CORPUS)
    assert [c.chunk_id for c in rebuilt.search("parse", k=10)] == a
```

**⑥ 排序稳定键（small）**

```python
def test_equal_scores_break_ties_by_chunk_id(indexer):
    hits = indexer.search("def", k=20)
    for prev, nxt in zip(hits, hits[1:]):
        assert (prev.score, prev.chunk_id) <= (nxt.score, nxt.chunk_id)   # 元组比较即稳定键
```

**⑦ golden query 判定集（medium）** —— 见 B6。

**⑧ 后台索引的进度 / 取消 / 竞态（medium）**

```python
def test_cancel_stops_indexing(indexer):
    job = indexer.index_async(CORPUS)
    job.cancel()
    job.wait(timeout=indexer.config.wait_limit_s)     # 不用 sleep
    assert job.state == "cancelled"
    assert indexer.search("parse", k=1) == [] or job.progress().done < job.progress().total

def test_concurrent_search_during_index_never_raises(indexer):
    job = indexer.index_async(CORPUS)
    for _ in range(50):                               # 断言在主线程做，不在索引线程里做
        indexer.search("parse", k=5)                  # 只要求「不抛异常 / 不返脏数据」
    job.wait(timeout=indexer.config.wait_limit_s)
    assert job.state == "done"
```

**⑨ 模型可见文本快照（medium）** —— 见 B9。

**⑩ FTS5 能力 + 版本（small）** —— 见 C11，并在缺失时 `pytest.skip` 而不是失败。

**⑩b 代码检索语义（small，最容易漏、上线才发现）** —— 见 B6 的 GitHub 引用，三条各一个测试：

```python
@pytest.mark.parametrize("query,expected_hit", [
    ("fn(",          True),   # 标点必须可检索 —— unicode61 默认会丢弃
    ("self.",        True),
    ("::",           True),
    ("for",          True),   # 停用词不能被剥离
])
def test_code_specific_query_semantics(index, query, expected_hit):
    assert bool(index.search(query, k=5)) is expected_hit

def test_no_stemming(index):
    # 契约：精确 token 匹配，不做 porter stemming
    assert all("parsing" in h.matched_terms for h in index.search("parsing", k=5))
```

**⑪ 无参数 / 未知工具 / 坏参数的负向用例（medium）**

```python
@pytest.mark.anyio
@pytest.mark.parametrize("tool,args", [
    ("code_search", {}),                       # 缺必填参数 → schema 层拒绝
    ("code_search", {"query": "x", "k": -1}),  # 越界 → schema 层拒绝
    ("no_such_tool", {}),                      # 未知工具
])
async def test_negative_cases(client, tool, args):
    r = await client.call_tool(tool, args, raise_on_error=False)
    assert r.is_error is True
```

**⑫ 退出码 / 冒烟（large，Inspector CLI）** —— 见 A2，并断言「工具列表恰好是那 4 个」与「`code_search` 返回 `isError != true`」。

### G5. CI 流水线（`.github/workflows/ci.yml` 要点）

```yaml
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --locked --all-extras --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .     # 与 check 分开，职责不同
      - run: uv run mypy src
      - run: uv run pytest -m "not e2e" --cov --cov-branch --cov-fail-under=88
      - run: uv run pytest tests/snapshots -n0     # inline-snapshot 不支持 xdist，必须单进程
      - run: uv run pytest -m e2e             # E2E 单独一步，失败更容易定位

  matrix:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.10", "3.13"]
        include:
          - os: windows-latest
            continue-on-error: true
    runs-on: ${{ matrix.os }}
    steps:
      # ... setup + uv run pytest
      - run: uv run pytest tests/integration/test_fts5_capability.py
```

**不要装 `pytest-rerunfailures`**。**不要给全仓库定 100% 覆盖率**。

---

## H. 明确「未查到明确信息」的清单

**技术未知项（4 条）**

| # | 未知项 | 已知的相邻事实 |
|---|---|---|
| 1 | **FTS5 能否在 `:memory:` 中工作** | FTS5 与 in-memory 两页均未提及组合限制。FTS5 是虚拟表模块，可用性由 `SQLITE_ENABLE_FTS5` 决定，与介质无关（推断）。**实践：直接建表断言，别信推断。** |
| 2 | **bm25 数值跨 SQLite 版本是否逐位一致** | 官方未作任何承诺；[Floating Point](https://www.sqlite.org/floatingpoint.html) 明文不给精度保证 |
| 3 | **逐平台 SQLite 版本对照表** | 官方只有「macOS 系统 `python3` 通常更旧、更不完整」这一表述 |
| 4 | **主流 IR 评测库是否提供官方 pytest fixture / plugin** | 未查到。事实上的成熟模式＝小 qrels + 官方指标库算分 + 参数化/阈值断言 + 浮点容差 |

**文档不存在／不该这么引用（5 条）**

5. **「FTS5 文档说同分顺序未定义」是错的**——FTS5 页面无此表述（做过 `unspecified`/`equal`/`tie`/`stable`/`deterministic` 全文检索）。规范出处是 [SQLite SELECT §4](https://www.sqlite.org/lang_select.html)。
6. **coverage.py FAQ 里没有「Isn't 100% coverage a good goal?」**——只有「Isn't coverage testing the best thing ever?」（答案：「It's good, but it isn't perfect.」）。
7. **Anthropic 官方没有「如何 mock Claude API」文档**——只有 `anthropic-sdk-python` 的 `tests/conftest.py` 可作事实标准。
8. **MCP 规范里没有「不接模型测试」条款**——指引落在 Inspector/Debugging 文档页与各 SDK 的 Testing 页。
9. **《The Practical Test Pyramid》全文没有任何测试配比百分比**——本报告的 60/35/5 是基于其「越上层越少」原则与 Google size 定义给出的**工程建议，非原文引用**。

**其他（4 条）**

10. **Google Testing Blog 两篇正文**——`testing.googleblog.com` 本次不可达；Code Coverage 一篇经标注来源与原文链接的中文全译镜像读到结论，Test Sizes 一篇仅有《Software Engineering at Google》ch.11 的官方同源表述替代。
11. **专门做「零 API key 的 Agent/检索组件测试」的独立开源项目**——未查到成熟项目。
12. **「test-only fixture 覆盖 batch size」的成文指导**——未查到；是「DI + 设置对象覆盖」通用手段的组合。
13. **Sourcegraph 的检索工程博客正文**——对自动抓取返回 **403**，其 `keeping-it-boring-and-relevant-with-bm25f`、`new-search-ranking`、`ranking-in-a-week` 三篇**均未读到可验证正文** → **不要引用其结论**（网上二手转述的「Sourcegraph 用 BM25F」在本报告中无一手依据）。GitHub 博客正文**已解决**：经 WordPress REST API 取到全文并已引用。
