# Python MCP 服务器 + 检索系统：测试方案（精简版，约 4700 字）

> 完整证据版（115 个 URL、约 7500 字）见同目录 `mcp-python-retrieval-testing-research.md`。本版是满足篇幅要求的正文，每一节保留结论与关键 URL。
> 场景：Python 包，MCP server（stdio），4 个工具，SQLite FTS5 + tree-sitter，由宿主 spawn。要求**无网络、无模型 API key** 可跑。

**三条决定全局的结论**

1. **MCP Python SDK v2 内置 in-memory transport**：`async with Client(mcp, raise_exceptions=True)`。无子进程、无端口、无模型（[Testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/)）。
2. **FTS5 是编译期特性，跨发行版真会缺失**——`uv` 分发的 CPython 直到 [PR #694](https://github.com/astral-sh/python-build-standalone/pull/694)（2025-07）才打开 `-DSQLITE_ENABLE_FTS5`。必须做**运行时能力探测**。
3. **这条链路本来不经过模型**，社区「只 mock 昂贵/不确定边界」原则退化为**什么都不用 mock**，只需处理时钟与「慢」。

---

## A. MCP 服务器怎么测

### A1 官方 SDK 测试手段（v1/v2 是两套 API）

| | v1（`mcp>=1.28,<2`） | v2（`mcp>=2`，当前） |
|---|---|---|
| 服务器类 | `FastMCP` | `MCPServer` |
| 测试入口 | `create_connected_server_and_client_session` | `Client(mcp)` 传服务器对象 |
| 文档 | [v1 Testing](https://py.sdk.modelcontextprotocol.io/v1/testing/) | [Testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/) |

```python
@pytest.fixture
def anyio_backend(): return "asyncio"

@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        yield c
```

**传输由第一个位置参数的类型决定**：`str`→HTTP；`StdioServerParameters`→子进程；**服务器对象→in-process**（[transports](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/client/transports.md)）。同一个 `Client` 类既能写 in-memory 测试也能写真子进程 E2E。

坑：`raise_exceptions=True` **只影响 tool body 之外的崩溃**——工具内部异常本来就返回 `is_error=True`（[handling-errors](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/servers/handling-errors.md)）。

### A2 MCP Inspector 可脚本化，官方就是为 CI 设计的

`npx @modelcontextprotocol/inspector --cli python -m mypkg --method tools/list --format json | jq -e ...`

**退出码是稳定契约**：`0` 成功 / `1` 用法错误 / `3` 需认证 / `4` 不可达 / **`5` 工具错误（isError:true）** / `6` schema 问题。`--method initialize` 是最便宜的「活着且在说 MCP」断言。CI 必须 pin 精确版本（`@2` 不算 pin）。

坑：`--tool-arg k=v` 会对可解析值做 JSON 解析（`zip=10001` 变数字）→ 用 `--tool-args-json`；**stdout 是结果、stderr 是诊断**，绝不 `2>&1`；`pipefail` 只报最右非零状态，会吞掉 CLI 的失败类别。（[cli-smoke-testing](https://raw.githubusercontent.com/modelcontextprotocol/inspector/main/docs/cli-smoke-testing.md)）

### A3 兼容性测试

**官方有独立 conformance 套件**：`npx @modelcontextprotocol/conformance server --url <url> --requirements 2026-07-28`。除场景自身 check 外还产出 `wire-schema-valid`（把线上每条 JSON-RPC 消息对照 spec schema 校验）。`--expected-failures` 三态值得抄：失败且在基线→0；失败且不在→1；**通过但在基线→1（过期基线）**。有 composite GitHub Action。（[conformance](https://github.com/modelcontextprotocol/conformance)）

三件必测：

1. **协议版本协商**。MCP 有两代：`initialize` 握手（≤2025-11-25）与 `server/discover`（2026-07-28）。`mode="auto"` 自动桥接。**版本 pin 不发协商流量，代价是 `server_info` 为 `None`、`server_capabilities` 全空**——想断言 capabilities 就别 pin（[protocol-versions](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/protocol-versions.md)）。
2. **capabilities 声明**。规范原文「The initialization phase **MUST** be the first interaction」（[Lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)）。断言 `capabilities.tools` 存在**且 `resources`/`prompts` 为 `None`**——锁死「不误声明未实现的能力」。
3. **`isError` 三分法**：`ToolError`→请求成功、`is_error=True`、`content` 有你的消息、`structured_content=None`；`MCPError`→整个调用失败、JSON-RPC error、**没有 result**；其它异常→`is_error=True` 但消息被消毒成 `Error executing tool <name>`。**断言「内部异常不泄漏到 content」是安全断言**。官方反模式警告：「Never `return` an error message from a tool」。注意 Python 侧字段是 `is_error`，wire 上是 `isError`。

### A4 stdio：stdout 被协议独占

规范原文：「The server **MUST NOT** write anything to its `stdout` that is not a valid MCP message」；stderr 允许日志（[Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)）。官方调试页：「Local MCP servers should not log messages to stdout」（[Debugging](https://modelcontextprotocol.io/docs/2026-07-28/tools/debugging)）。

**Python 侧的微妙之处**（[SDK Logging](https://py.sdk.modelcontextprotocol.io/v2/handlers/logging/)）：标准库 logging 默认写 stderr，`MCPServer(...)` 构造时已替你 `basicConfig()` 指向 stderr（`log_level=` 控制）。**但 SDK 只把「已 flush 的杂散 stdout」改道到 stderr——块缓冲进程里的 `print()` 通常躺在缓冲区直到解释器退出才 drain，直接落到协议流上**；即使被改道，那行也是裸的（无级别、无 logger 名）。

**测试**：`capsys`/`capfd` 对子进程无效，必须真 spawn 并逐行 `json.loads()`：

```python
proc = subprocess.Popen([sys.executable, "-m", "mypkg"], stdin=PIPE, stdout=PIPE, text=True, bufsize=1)
proc.stdin.write('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'); proc.stdin.flush()
msg = json.loads(proc.stdout.readline())   # 任何 print() 都会让这里炸
assert msg["id"] == 1 and "result" in msg
```

再加静态兜底：ruff 启用 `T20`（flake8-print）。

### A5 可参考的开源测试代码

- [python-sdk `tests/test_examples.py`](https://github.com/modelcontextprotocol/python-sdk/blob/main/tests/test_examples.py)：`Client(mcp)` + inline-snapshot；`strip_server_info()` 先剥掉 `_meta` 身份戳再比对——**只断言行为，不断言身份**。
- [servers `src/filesystem/__tests__/`](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem/__tests__)：8 个文件多为纯函数级；`directory-tree.mcp-sdk.test.ts` 用真实 SDK Client + `StdioClientTransport` 拉起真子进程做协议回归。
- [FastMCP Tests](https://gofastmcp.com/development/tests)：四层策略（in-memory → `asgi_client` 不开端口 → 真实端口 → 子进程），用 marker 隔离。**官方警告：不要在 fixture 里打开 client**（难诊断的 event loop 问题）。

---

## B. 检索系统的测试

### B6 检索质量：判定集 + 指标

指标计算交给成熟库：[ir-measures](https://ir-measur.es/en/latest/)（`ir_measures qrels run nDCG@10 P@5`）、[pytrec_eval](https://github.com/cvangysel/pytrec_eval)、[ranx](https://github.com/Amendra/ranx)、[BEIR](https://arxiv.org/abs/2104.08663)（**数据集数量口径不一，不要写死**：论文 18、README 17、表格 19 行）。

**指标命名的坑**（[measures](https://ir-measur.es/en/latest/measures.html)）：`R`（Recall@k）**不是**「top-k 里有任一相关文档」，后者叫 `Success@k`。别名 `MRR→RR`、`NDCG→nDCG`、`MAP→AP`。官方还提醒 `iter_calc` 结果「may not be in a predictable order」——不要把逐 query 结果顺序写进断言。BEIR 默认 `ignore_identical_ids=True`（剔除 `qid == pid`），注意 query id 与 chunk id 撞车。

**代码检索 ≠ 通用文本检索——这条直接决定 tokenizer 与测试清单。** GitHub 工程博客原文（[链接](https://github.blog/engineering/architecture-optimization/the-technology-behind-githubs-new-code-search/)，正文可经 `https://github.blog/wp-json/wp/v2/posts?slug=the-technology-behind-githubs-new-code-search` 取全文）：

> Searching code also has unique requirements: **we want to search for punctuation (for example, a period or open parenthesis); we don't want stemming; we don't want stop words to be stripped from queries**; and, we want to search with regular expressions.

对 FTS5 的直接含义：默认 `unicode61` **把标点当分隔符丢弃**，`. ` `(` `::` 搜不到 → 要么换 [trigram tokenizer](https://www.sqlite.org/fts5.html#the_trigram_tokenizer)（该模式下 `LIKE`/`GLOB` 也走索引，且 bm25 分数变成**亚单位量级**），要么走 `LIKE`/`GLOB` 路径；同时**不要用 porter tokenizer**。**这三条各需一条 golden 测试，它们在 `unicode61` 下会全部失败**。（该文只讲架构不讲测试——全文 `test`/`precision`/`recall`/`BM25` 零命中，不要当作测试文章引用。）

**业界第一方做法**：Elastic [`_rank_eval`](https://github.com/elastic/elasticsearch/blob/main/docs/reference/elasticsearch/rest-apis/search-rank-eval.md)（可直接读 Markdown 源文件）——三件套＝文档 + 典型查询 + **每查询人工评分**；响应是**整体 `metric_score` + 逐 query `details[]` + `failures`**，正是「逐 query 断言 + 整体分数」的官方形态；指标为 P@k / R@k / MRR / DCG(`normalize`=nDCG) / ERR。存在理由那句最值得引：「search result quality is **evaluated constantly across a representative test suite of typical user queries**」。

**落地建议**（[Elastic Search Labs](https://www.elastic.co/search-labs/blog/judgment-lists-search-query-relevance-elasticsearch)）：**「Start small, but start.」**——只需 **5–10 条最关键 query**（含历史零结果的），先上 Precision 再上 nDCG；「**Make it part of the flow.** Integrate judgment lists into your development pipelines.」

**两条决定成败的实践**：① **逐 query diff，不要只看均值**——「a change that lifts the mean nDCG by 0.03 while **quietly tanking three head queries that make up half your traffic**」（[dev.to](https://dev.to/libme/how-to-test-search-relevance-before-you-ship-a-ranking-change-29o)，引擎无关，可套 FTS5）；② **聚合口径写进文档**：macro-average 用于 CI、traffic-weighted 用于产品评审；固定二值化阈值（0–3 分级常用 `grade >= 2`），golden 文件版本化并「**Always fail on `golden_version` mismatch**」（[qaskills.sh](https://qaskills.sh/blog/search-relevance-testing-golden-queries)，第三方）。

### B7 确定性：BM25 是浮点，并列顺序没有保证

FTS5 官方（[§5.1.1](https://www.sqlite.org/fts5.html#the_bm25_function)）：`bm25()` 返回 real，**越小越好**（实现故意乘 −1，故升序即最佳在前）；`k1`/`b` 硬编码 1.2/0.75；隐藏列 `rank` 默认等于 `bm25()`，**`ORDER BY rank` 比 `ORDER BY bm25(ft)` 更快**（可提前中止）。N 与 avgdl 是**全表统计量**，增删一条文档会改变所有查询的分数。

**并列顺序的规范出处不在 FTS5 文档，而在 SQLite 核心 SELECT 文档**：

> **The order in which two rows for which all ORDER BY expressions evaluate to equal values are returned is undefined.**（[SELECT §4](https://www.sqlite.org/lang_select.html)）

**源码级佐证**：FTS5 为 `ORDER BY rank` 专设 `FTS5_PLAN_SORTED_MATCH`，其 sorter 是 `SELECT rowid, rank FROM ... ORDER BY <rankfn>(...)`——**没有 rowid 次级键**（[fts5_main.c#L1112](https://github.com/sqlite/sqlite/blob/version-3.53.4/ext/fts5/fts5_main.c#L1112)）。浮点另有官方免责：「SQLite makes no guarantees that the accuracy of computations on floating point values will even be this accurate」（[Floating Point](https://www.sqlite.org/floatingpoint.html)）。

**解法（叠加）**：

1. **永远加唯一 tiebreaker**：`ORDER BY score ASC, chunk_id ASC`（`chunk_id` 是 INTEGER PRIMARY KEY）。这一步就彻底消灭不稳定，**不需要任何容差**。
2. 只对**展示用**分数取整，绝不用取整值排序。
3. **不比对浮点绝对值**——用整数化排序键或 `pytest.approx`。

**真实案例**：[agaric](https://github.com/jfolcini/agaric) 用 `(rank ASC, id ASC)` + 相对 epsilon 吸收游标漂移；其回归测试的技巧可直接抄——**「造三条完全相同内容的最小语料，强制分页边界落在同分区间内部」**（[tests.rs](https://github.com/jfolcini/agaric/blob/9e1e2507cbd4d71b2a0e44ccc2817b792c2f262c/src-tauri/src/fts/tests.rs)）。

另一个坑（[SQLite 论坛](https://sqlite.org/forum/forumpost/2fc481fcb68184eb?hist)）：`ORDER BY rank` 里 `rank` 可能被解析成普通列名而非 FTS5 隐藏列，**静默退化成「按某列排序」** → golden 测试要**同时断言分数单调性与结果顺序**。

### B8 Property-based testing

官方把「**A type-checker, linter, formatter, or compiler does not crash when called on syntactically valid code**」列为典型性质（[Introduction](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html)）。适合你的性质：**全覆盖**（区间并集 == 全文）、**不重叠**（`a.end_byte <= b.start_byte`）、**偏移合法**、**不崩溃**、**幂等/确定性**。

```python
@given(st.text(max_size=4000).map(lambda s: s.encode("utf-8")))
@settings(max_examples=200, deadline=None)
def test_chunks_cover_without_overlap(src):
    chunks = sorted(chunk(src, language="python"), key=lambda c: c.start_byte)
    assert all(0 <= c.start_byte <= c.end_byte <= len(src) for c in chunks)
    assert all(a.end_byte <= b.start_byte for a, b in zip(chunks, chunks[1:]))
```

**`st.text()` 的行为要准确掌握**（[strategies](https://hypothesis.readthedocs.io/en/latest/reference/strategies.html#hypothesis.strategies.text)）：默认 alphabet **已排除 surrogate**（因为它们在 UTF-8 中非法），所以 `encode("utf-8")` **不会抛异常**；但它**不做 Unicode 规范化**，且 Python 长度按**码点**计——**tree-sitter 用的是字节偏移，偏移断言必须想清楚单位**。想要 surrogate 必须显式用无参 `st.characters()`，并把「非 UTF-8 输入应优雅拒绝而非崩溃」单独写成一条性质。

`deadline` 默认 **200ms**，内置 `ci` profile 用 `deadline=None`——本地跑慢测试用 `settings.load_profile("ci")` 最省事。Health check 要**按需抑制**，官方警告不要 blanket suppression（[how-to](https://hypothesis.readthedocs.io/en/latest/how-to/suppress-healthchecks.html)）。

### B9 快照测试

| 工具 | 版本 | 存放 | 结论 |
|---|---|---|---|
| **inline-snapshot** | 0.35.4 | **源码里** | ✅ **首选**（唯一支持 inline；PR diff 逐字符可读；支持 `dirty-equals` 局部豁免不稳定字段） |
| syrupy | 6.1.1 | `__snapshots__/` | 文本量大时用；**amber 会把 `\r\n` 归一化为 `\n`**，要字节保真须换 `SingleFileSnapshotExtension` |
| pytest-snapshot | 0.9.0 | 外部文件 | 事实停更，不建议新项目 |

**决定性理由**：官方 MCP Python SDK 的测试文档就用它（[Testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/)），SDK 自己的 `test_examples.py` 也用它。syrupy **明确不支持 inline 快照**并转荐 inline-snapshot（[issue #122](https://github.com/syrupy-project/syrupy/issues/122) 以 `not_planned` 关闭）。

**两个会破坏 CI 设计的硬限制**（[Limitations](https://15r10nk.github.io/inline-snapshot/latest/limitations/)）：**不支持 pytest-xdist**（启用即等同 `--inline-snapshot=disable`——用 `-n auto` 时快照测试会**静默失效**而不是失败）；**CI 环境默认 `disable`**。→ 快照测试必须单独跑一个 `-n0` 的 step。

---

## C. 文件系统与数据库测试

**C10** `tmp_path` 每测试唯一；`tmp_path_factory` 是 **session-scoped**，官方推荐 `tmp_path_factory.mktemp("data")`（预建 FTS5 索引库用它）。默认 `{temproot}/pytest-of-{user}/pytest-{num}/{testname}/`，**保留最近 3 次**；`--basetemp` 会被「blindly cleared」。防污染：`monkeypatch.setattr(Path,"home",...)`；`platformdirs` **honors `XDG_DATA_HOME`/`XDG_CONFIG_HOME`**，`monkeypatch.setenv` 即可整体重定向。（[tmp_path](https://docs.pytest.org/en/stable/how-to/tmp_path.html)、[platformdirs](https://platformdirs.readthedocs.io/en/latest/)）

**C11 用临时文件，不要 `:memory:`**：官方原文「**Every :memory: database is distinct from every other.**」（[In-Memory DB](https://www.sqlite.org/inmemorydb.html)）——你的后台索引线程会另开连接，写进的是另一个空库，前台永远查不到。要共享用 `file:memdb1?mode=memory&cache=shared`（同进程、名字完全相同）。

WAL（[WAL](https://www.sqlite.org/wal.html)）：非默认；**内存库上设不了**；产生 `-wal`/`-shm`；**Windows 的 `DeleteFile` 对未关闭/内存映射文件会失败**（[MS Learn](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile)）→ **清理 `tmp_path` 前必须关所有连接**。

能力探测（照抄 [PR #694](https://github.com/astral-sh/python-build-standalone/pull/694)）：

```python
opts = {r[0] for r in sqlite3.connect(":memory:").execute("PRAGMA compile_options")}
assert "ENABLE_FTS5" in opts, f"missing; sqlite={sqlite3.sqlite_version}"
```

注意 `PRAGMA compile_options` **省略 `SQLITE_` 前缀**，判定字符串是 `ENABLE_FTS5`。

**C12** 每测试/每 worker 各用自己的 DB 文件；`--dist loadfile` 保证同文件同 worker；共享时 `connect(timeout=)` 默认 5 秒后 `database is locked`；xdist 下 `parametrize` 传 `set` 会直接报错，用 `sorted(...)`。

> **未查到**：FTS5 能否在 `:memory:` 中工作（官方两页均未提及组合限制）。**实践：直接建表断言，别信推断。**

---

## D. 长耗时操作与异步

**D13** 官方硬约束（[flaky](https://docs.pytest.org/en/stable/explanation/flaky.html)）：pytest 单线程、xdist 是多进程；必须「eventually wait on any spawned threads」；**「Avoid using primitives provided by pytest (`pytest.warns()`, `pytest.raises()`) from multiple threads, as they are not thread-safe」** → **索引线程内不能断言**，只记录状态，主线程断言。给索引器设计可等待句柄（`job.wait(timeout)` / `job.progress()` / `job.cancel()`）而不是 sleep。超时用 AnyIO `fail_after`/`move_on_after`（[cancellation](https://anyio.readthedocs.io/en/stable/cancellation.html)）。覆盖 `check_same_thread=True/False` 两条路径（[sqlite3](https://docs.python.org/3/library/sqlite3.html#sqlite3.connect)）——前者会直接抛 `ProgrammingError`，后者官方警告「**write operations may need to be serialized by the user to avoid data corruption**」。pytest-asyncio 侧：strict 是默认模式，**async 测试顺序执行**（「This sequential execution is intentional and important for maintaining test isolation」，[concepts](https://pytest-asyncio.readthedocs.io/en/stable/concepts.html)）。

**D14** `pytest-timeout` 官方警告：「**it is not designed for precise timings or performance regressions**… timeouts being a last resort」（[README](https://github.com/pytest-dev/pytest-timeout)）。根治靠 Fowler 两条（[nonDeterminism](https://martinfowler.com/articles/nonDeterminism.html)）：「**Never use bare sleeps**… use a callback or polling」；`waitLimit`「**should never be literal values**… set through the runtime environment」。**重跑只是掩盖**：`pytest-rerunfailures` 默认**只保留最后一次 attempt 的 traceback**，「failures from earlier attempts … are silently discarded」（[README](https://github.com/pytest-dev/pytest-rerunfailures)）→ **建议不装这个插件**。

**D15** 官方立场（[monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)）：「**For code that you control, a safer long-term pattern is to make dependencies explicit so they can be passed into the code under test instead of patched globally.**」→ 把 `batch_size`/`max_chunk_bytes`/`poll_interval` 做成显式 Config 字段，测试传小值；**绝不写 `if os.getenv("TESTING")` 分支**。

---

## E. CI 与工程质量

**E16 工具链**：ruff `check` 与 `format` 职责不同——**formatter 不排 import**（先 `ruff check --select I --fix` 再 `ruff format`）（[Formatter](https://docs.astral.sh/ruff/formatter/)）。mypy `strict = true` 是「a defined subset」，**`--warn-unreachable` 不含在内**且 flag 列表会随版本变 → 显式加上（[command_line](https://mypy.readthedocs.io/en/stable/command_line.html)）。coverage `branch = true`；**`--cov-fail-under` 是 pytest-cov 的**，且它会**覆盖** coverage 的 `parallel`/`source`/`branch`（[pytest-cov](https://pytest-cov.readthedocs.io/en/latest/config.html)）。**子进程覆盖对你的库至关重要**：`[run] patch = subprocess` + `parallel` + `coverage combine`，且 **`sigterm` 在 Windows 无效**（[Subprocess](https://coverage.readthedocs.io/en/latest/subprocess.html)）。CI 用 uv 的官方指南：[uv + GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)。

**覆盖率目标——四条可引用立场**

| 来源 | 立场 |
|---|---|
| [Fowler](https://martinfowler.com/bliki/TestCoverage.html) | 「**upper 80s or 90s**」；「suspicious of anything like **100%**」；「**below half** = trouble」 |
| Google, Code Coverage Best Practices | 「**There is no 'ideal code coverage number'**」；60/75/90 三档；「**What's not covered is more meaningful**」；收益**对数级**；**per-commit 99% 合理、90% 好下限** |
| [SEG ch.11](https://abseil.io/resources/swe-book/html/ch11.html) | 「coverage only measures that a line was invoked, **not what happened**」；「only measure coverage from **small tests**」；80% 门槛会被当成 **ceiling** |
| [CPython devguide](https://devguide.python.org/testing/coverage/) | 「getting 100% is **not always possible**. There could be **platform-specific code**」 |

**对你的具体建议**：全仓库 **85–90% + branch**；**per-file 100% 只给「必须逐字符稳定」的模块**（工具序列化、排序 key、结果格式化）；**检索质量用 golden query 判定集，不用覆盖率衡量**；**不要给全仓库定 100%**（你有原生扩展依赖）。额外手段：**mutation testing** 检验断言效力。

「测试够了没有」的判据**不是数字**——Fowler 给的是两条：① 很少把 bug 漏到生产；② 很少因为怕改出生产 bug 而不敢改代码。他还提醒「One sign you are testing too much is if your tests are slowing you down」（[TestCoverage](https://martinfowler.com/bliki/TestCoverage.html)）。

**E17 多平台矩阵：必要**（两条独立理由）

1. **tree-sitter 是原生扩展**：官方 README 称提供「**pre-compiled wheels for all major platforms**」（[README](https://github.com/tree-sitter/py-tree-sitter/blob/master/README.md)），但 `setup.py` 确有 `Extension(name="tree_sitter._binding", ...)` 编译 vendored C 源码 → **主流平台不需编译器，落到 sdist 就需要 C11**。语言包：`tree-sitter-languages` wheel **只到 cp312** 且「**Source installs are not supported**」（[PyPI](https://pypi.org/project/tree-sitter-languages/)）→ **不要用**；`tree-sitter-language-pack` 是 **abi3**（[PyPI](https://pypi.org/project/tree-sitter-language-pack/)）→ **优先**。
2. **FTS5 跨发行版会缺失**（PR #694，见上）。

写法：`fail-fast: false`，windows 加 `continue-on-error: true`。**若你不自己打 wheel，就不需要 cibuildwheel。**

**E18 测试金字塔**（先纠正一个误解）：**Fowler 的《The Practical Test Pyramid》全文没有给出任何百分比**。原则是「**The more high-level you get the fewer tests you should have**」，E2E 要「**reduce … to a bare minimum**」，「**Having a low-level test is better than having a high-level test**」（[链接](https://martinfowler.com/articles/practical-test-pyramid.html)）。Google 的 size 维度更实用：**small = 单进程、不允许 sleep / I/O / 阻塞调用**；**medium = 可跨进程、只可 localhost**；**large = 想去哪去哪**（[SEG ch.11](https://abseil.io/resources/swe-book/html/ch11.html)）。

映射（60/35/5 是工程建议，非原文）：**small** 分块纯函数、查询串转义、排序 key、结果格式化、入参校验；**medium** `Client(mcp)` 调 4 个工具、真 FTS5 + golden query、索引进度/取消、快照、Hypothesis；**large 3–5 条** 主旅程 + stdout 纯净性 + 负向。

---

## F. 零成本测试

**F19 通行模式**：in-memory transport（`Client(mcp)`、FastMCP `Client(server)`）；fake/mock LLM（LangChain [`GenericFakeChatModel`](https://docs.langchain.com/oss/python/langchain/test/unit-testing)、Vercel AI SDK [`MockLanguageModelV4`](https://ai-sdk.dev/docs/ai-sdk-core/testing)、OpenAI Agents SDK [`ScriptedModel`](https://openai.github.io/openai-agents-python/testing/)）；record-replay（[vcrpy](https://vcrpy.readthedocs.io/en/latest/advanced.html)、[pytest-recording](https://github.com/kiwicom/pytest-recording)（**默认 `none`，天然阻断联网**）、[respx](https://github.com/lundberg/respx)）；录制会话回放（DSH [`dsh-llm-replay`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/test-support/llm-replay/README.md)）。

官方共识（[DSH testing.md](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/testing.md)）：「**Prefer the real implementation over a mock** — Mock only the expensive or non-deterministic boundary (LLM adapter, network, clock); keep everything downstream real.」

**对你**：只处理 ①**时钟**（[time-machine](https://time-machine.readthedocs.io/en/stable/pytest_plugin.html) 自带 pytest marker/fixture）②**「慢」**（Config 调小 batch_size）③**绝对路径**（`XDG_*` → tmp_path）。其余全真。

**F20 开源参考**：[python-sdk `test_examples.py`](https://github.com/modelcontextprotocol/python-sdk/blob/main/tests/test_examples.py)（「零 key 测 MCP server」的参考实现）；[anthropic-sdk-python `conftest.py`](https://github.com/anthropics/anthropic-sdk-python/blob/main/tests/conftest.py)（`http_snapshot` + `SNAPSHOT_REQUEST_HEADERS_EXCLUDE = ["x-api-key"]`，**keyless + 凭据脱敏双范例**）；[openai-agents-python Testing](https://openai.github.io/openai-agents-python/testing/)（「deterministic, provider-neutral testing utilities … **run in memory, make no model … requests**」）。

> **未查到**：专门定位为「零 API key 的 Agent/检索组件测试」的独立开源项目；Anthropic 官方文档层面的 mock 指南；MCP 规范中「不接模型测试」条款。

---

## G. 可照抄的测试方案骨架

**结构**：`tests/{unit,integration,snapshots,e2e,data}`；`data/corpus/`（小型固定语料）+ `data/qrels.py`（判定集）。

**pyproject 关键项**：

```toml
[tool.pytest.ini_options]
asyncio_mode = "strict"                 # pytest-asyncio 默认即 strict
timeout = 30
session_timeout = 600
filterwarnings = ["error"]              # ResourceWarning（未关闭的 sqlite 连接）变失败
markers = ["e2e: spawns a real subprocess", "hypothesis: property-based tests"]

[tool.coverage.run]
branch = true
patch = ["subprocess"]                  # 覆盖被宿主 spawn 的子进程
parallel = true
[tool.coverage.report]
fail_under = 88
exclude_also = ["if TYPE_CHECKING:", "if sys.platform =="]

[tool.ruff.lint]
select = ["E", "F", "UP", "B", "SIM", "I", "T20"]   # T20：禁 print()，保住 stdout 纯净
[tool.mypy]
strict = true
warn_unreachable = true
```

**conftest 关键 fixture**：`index_config`（tmp_path DB + 小 batch_size + 非字面量的 `wait_limit_s`/`poll_interval_s`）、`indexer`（yield 后 `close()`，**必须在删 tmp_path 前**）、`built_index`（`job.wait(timeout=...)`，**不用 sleep**）、`client`（`Client(mcp, raise_exceptions=True)`）、autouse 的 `_no_user_dirs`（HOME / XDG_* → tmp_path）。

**13 类必测与断言要点**

| # | 类别 | 关键断言 |
|---|---|---|
| 1 | 协议契约 | 工具集合恰为 4 个；description 非空；**未实现能力为 `None`** |
| 2 | isError 三分法 | 含**安全断言**：`"Traceback" not in content`、`"sqlite3" not in content` |
| 3 | **stdout 纯净性** | 真子进程 + 逐行 `json.loads` |
| 4 | 分块性质 | Hypothesis：全覆盖 / 不重叠 / 偏移合法 / 不崩溃 |
| 5 | 确定性 | 同输入两次 + 重建索引后仍一致 |
| 6 | 排序稳定键 | `(score, chunk_id)` 元组单调 |
| 7 | **代码检索语义** | 标点可检索（`fn(`、`self.`、`::`）；不 stemming；不丢停用词（`for`）——**`unicode61` 下会全部失败** |
| 8 | golden query | 精确 top-1 **+** 逐 query nDCG delta 计数（不只看均值） |
| 9 | 索引进度/取消/竞态 | 断言在**主线程**做；不用 sleep |
| 10 | 模型可见文本快照 | inline-snapshot；单独 `-n0` step |
| 11 | FTS5 能力探测 | `ENABLE_FTS5` 缺失时 `skip` 而非 fail |
| 12 | 负向用例 | 缺参 / 越界 / 未知工具 |
| 13 | Inspector CLI 冒烟 | `--format json` + `jq -e`；退出码 5 = 工具错误 |

**CI**：`check` job（ruff check → `ruff format --check` → mypy → `pytest -m "not e2e" --cov-branch --cov-fail-under=88` → **`pytest tests/snapshots -n0`** → `pytest -m e2e`）+ `matrix` job（3 OS × 2 Python，`fail-fast: false`）。**不装 pytest-rerunfailures；不给全仓库定 100%。**

---

## H. 未查到明确信息 / 不该这么引用

**技术未知**：① FTS5 能否在 `:memory:` 中工作（官方未提及组合限制）；② bm25 数值跨 SQLite 版本是否逐位一致（官方无承诺）；③ 逐平台 SQLite 版本对照表；④ 主流 IR 库是否提供官方 pytest plugin（**没有**，事实模式＝小 qrels + 指标库 + 参数化断言）。

**文档不存在／不该这么引用**：⑤ **「FTS5 文档说同分顺序未定义」是错的**——出处是 [SQLite SELECT §4](https://www.sqlite.org/lang_select.html)；⑥ coverage.py FAQ 里**没有**「Isn't 100% coverage a good goal?」；⑦ Anthropic 官方**没有** mock 指南；⑧ MCP 规范里**没有**「不接模型测试」条款；⑨ **《The Practical Test Pyramid》全文没有任何百分比**（本文的 60/35/5 是工程建议）；⑩ **Sourcegraph 检索博客三篇正文对抓取返回 403**（备用域名 404），**三篇均未读到可验证正文 → 请勿引用其观点**；网络二手转述的「Sourcegraph 用 BM25F」在本文无一手依据。
