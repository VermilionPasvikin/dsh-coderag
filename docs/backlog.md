# Backlog：越界缺陷与待办

> 记录各任务期间发现、但不在当前任务范围内因而**未顺手修**的问题（AGENTS.md §9）。
> 每条都写明发现任务与建议动作。

## 分块器：gap 块没有 `MAX_CHUNK_LINES` 上限（发现于 T2-18）

- 现象：`_uncovered_regions` 把整段非声明区域合成一个 gap 块，不按窗口切分。DSH 语料里
  `packages/extensions/tool-cordis/src/api-catalog.ts:82-3161` 是 **3080 行**的单块；
  最大 5 个 chunk 全是 gap。
- 根因：生成的目录文件顶层是巨大的 `export const X = { ... }`，不被识别为声明。
- 后果：单次命中返回数千行，即使有 `max_tokens` 裁剪也会用首条挤占预算。
- 建议：gap 区域也受 `MAX_CHUNK_LINES` 约束（复用 `_windows`）。
- **已尝试修复并回滚（2026-09-20）**：按本节的"建议"实现了 gap 窗口化，并**同时**做了下一节
  的 TS 声明扩展（两者一起测，因为都是"分块"这一个假设）。全量重建索引后实测：
  - **结构确实改善**：63046 → 66165 chunk；gap 68.0% → **65.5%**；
    **最大单块 3302 → 200 行**；新增 `type` 1742 / `const` 905 个声明块。
  - **但 S1/S2 毫无变化**：`Success@5` 0.433 → **0.433**、`MRR` 0.313 → **0.313**，
    逐条 diff **0 改善 / 0 回归**——命中的仍是那 13 条。
  - 唯一收益是 **S4**：token 中位数 2492 → **2341**（−6%），即那条 3302 行的块不再挤占预算。
  - **结论：分块不是 S1/S2 的杠杆**（至少这一版实现不是）。按"无改善即回滚"回滚，
    main 保持绿；改动留在 `git stash@{0}`（"T2-18 follow-up: chunking fix"）。
  - **未被证伪的可能**：(a) gap 窗口化对极端长文件仍有独立价值（S4 + 长块可读性），
    可作为**独立的小修复**重新提交，但预期不会动 S1/S2；(b) 把 TS `const`/`type`
    纳入声明后，还需要**查询侧**能利用这些符号才会兑现收益——`symbol_name` 完全匹配
    加分属 `T3-14`，单改分块不够。

## 分块器：TS `type` 别名与 `const`/箭头函数未纳入声明（发现于 T2-18）

- 现象：`DECLARATION_KINDS["typescript"]` 只含 function/class/interface/method；
  `type_alias_declaration` 与 `lexical_declaration`（含箭头函数）落入 gap。
- 后果：DSH 语料 69.6% 的 chunk 是 gap（35638/51230），单行 gap 4980 个。
- 建议：把这两类纳入声明集合（`lexical_declaration` 仅在值含箭头/函数时）。
- **已尝试修复并回滚（2026-09-20）**：实现方式已在这条上验证可行——`type_alias_declaration`
  直接进 `DECLARATION_KINDS`；`lexical_declaration` 用**谓词**（值里含 `arrow_function`／
  `function` 才算，避免每个 `const x = 1` 都成一块）；`_symbol_name` 需能从
  `variable_declarator` 子节点取名字；包装节点（`export_statement`）的内层查找也要走谓词。
  新索引产出 `type` 1742 / `const` 905 个声明块，但 **S1/S2 逐条无变化**——细节与回滚原因见上一节。

## 检索：skip 报告在每次检索时重新 walk（发现于 T2-17）

- 现象：`search()` 为填写 `skipped` 而 `walk_with_report` 全仓库，单次检索约 180 ms。
- 建议：把 skip 统计随索引持久化（ADR-09 / `last-index.json`），检索直接读取。

## ✅ 已解决：精度/召回双模式（发现于 T2-17 / T2-19 / T3-03，由 **T3-13** 修复）

> 保留原始分析作为记录。修复见 `src/dsh_coderag/searcher.py` 的
> `_build_recall_match` 与 `tests/test_cjk_recall.py`。

- 现象：`_build_match` 把所有词作为必须命中的短语（AND）；DSH 语料上纯中文原问句
  5/5 返回 `status: empty`（T2-17），T2-19 只解决了标点路由，未改这一点。
- T3-03 量化：A 批 10 条中 9 条含中文，**全部 `status: empty`**；把同一标识符的中文后缀去掉后，
  三个 exact 目标都回到 top-5（`CONTEXT_WINDOW_EXCEEDED_CODE` 名次 5、
  `delegationDepthOf` 3、`SANDBOX_MODES` 4）。所以失败不是索引缺失或标识符搜不到，
  而是 AND 把**不可能命中的 CJK bigram** 也当成必须命中项，一条不中就整条归零。
  这意味着 exact 桶（EVAL.md §2.3 的 regression 桶）被同一个根因拖到 1/4。
- 设计（§5.3.1）：先精度模式（标识符整体短语 + CJK bigram 短语），0 条时**降级到召回模式**，
  两者都 0 才 empty。
- **结果（T3-13）**：精度模式返回 0 时用 OR 重试一次。A 批 exact 桶 1/4 → **4/4**
  （S@5 0.250 → 1.000），总体 S@5 0.100 → 0.400、MRR 0.100 → 0.165；归因里 A1 由 5 → 2，
  且 remaining 两条都是含中文的 crossfile 查询。
- **仍未实现**：§5.3.1 的单字中文查询退化为 `LIKE` + `low_confidence: true`（当前单字走普通
  FTS 短语，命中率未验证）。

## ✅ 已解决：exact 查询的定义处被使用处与测试文件压过（发现于 T3-03，T3-02b 复测，由 **T3-14** 修复）

> 保留原始分析作为记录。修复见 `src/dsh_coderag/searcher.py` 的
> `TEST_PATH_TIER_SQL` / `SYMBOL_MATCH_BOOST` 与 `tests/test_ranking_signals.py`。

- 现象：裸标识符查询能命中，但**定义处排在第 3–5 名**。例：`CONTEXT_WINDOW_EXCEEDED_CODE`
  的前 4 条全是 `*.spec.ts`（compaction-basic、llm-pi-ai 的测试），定义处
  `packages/llm/llm/src/error.ts` 第 5；`SANDBOX_MODES` 前 3 条是 `invariant.ts`，
  定义处 `session-mode.ts` 第 4。
- **30 条 golden 集复测（T3-02b，修正 A4 判据后）**：exact 桶 S@5 = **0.833 (10/12)**，
  未达 EVAL.md §2.7 的 0.90。两条失败经归因均为 **A4（排名过低）**：
  - `L-013 ANONYMOUS_USER_ID_FILE_NAME` → `k=5` 返回的 5 条**全部**是
    `packages/identity/anonymous-user-id/tests/anonymous-user-id.spec.ts`，定义处
    `src/index.ts` 不在其中；`k=50` 才把定义处纳入候选集。
  - `L-018 DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES` → `k=5` 返回 2 条
    `file-reference-local/src/index.ts`（使用方）+ 3 条 `tests/search.spec.ts`，
    定义处 `src/search.ts` 被挤出前 5。
- 后果：`k=5` 时 exact 桶在 rank 边缘压线，任何轻微打分变化就会翻成未命中。因为失败是
  **排序**而非分词/索引/分块，修它不需要向量（EVAL.md §2.8 的 `A4`）。
- **结果（T3-14）**：
  - 测试路径作为 **SQL `ORDER BY` 的第一层**降级（`TEST_PATH_TIER_SQL`），`LIMIT k`
    直接看到最终排序；`symbol_name` 完全匹配再减 `SYMBOL_MATCH_BOOST`。exact
    S@5 **0.833 → 1.000**、MRR **0.582 → 0.700**；L-013 名次 1、L-018 名次 3。
  - 同一轮把召回改成**三级**（精度 AND → 仅标识符 OR → 含 CJK bigram 的 OR）后，
    crossfile 的 `L-005` 也从「未命中」变成**名次 1**，crossfile S@5 0.000 → 0.091。
- **仍未实现**：`§3.3` 的「同文件多命中（局部性）加权」与「声明定义处加权」——两条
  A4 失败靠测试路径降级即可修复，未引入未被数据支持的新权重。
- 关联：本条与 `A4` 的判据修正（`bd9fd8d`）相互独立——修好判据才看见 A4。

## 检索：仅共享一个通用词的 query 会被误判成 A1（发现于 T3-14 复测）

- 现象：`L-008`「stdio 子进程会继承哪些环境变量，哪些会被过滤掉？」的目标
  `packages/subprocess/subprocess/src/index.ts` 与 query **只共享 `stdio` 这一个通用词**；
  真正的判别词（子进程/环境变量/过滤）在代码里对应 `scrubbedParentEnv`、
  `SENSITIVE_ENV_PATTERN`，**零词法重叠**。
- 后果：归因打的是 `A1`（"query 要求命中目标文件里不存在的词，AND 落空"），但这是
  **语义缺口**不是分词问题——`pool=500` + 仅标识符召回也进不了 top-5，说明排序怎么调都
  救不回来，属于 `A5` 的适用场景。R2 只看 `natural` 桶的 A5 占比，本条在 `crossfile`，
  **不影响 R2 判定**，但会误导 R3 的"先修实现"清单。
- 建议：`classify` 的 A5 判据应从"一个共同词都没有"**收紧**为"没有**判别性**（低文档频率）的
  共同词"——与 `ADR-14:140` 的措辞一致（**以 `ADR-14:140` 为准**）。需要按 token 统计文档频率，
  属独立改动。
- 结论：**不做排序硬凑**；保留为真实的语义检索失败样本。


## ✅ 已解决：MCP 服务器会被工作区里与标准库同名的模块打断（发现于 README 安装验证）

- 现象：在**工作区根目录含 `token.py`** 的仓库里，`python -m dsh_coderag.server` 直接
  `ImportError: cannot import name 'EXACT_TOKEN_TYPES' from 'token'
  (/path/to/workspace/token.py)`，MCP 服务器根本起不来。
- 根因：DSH 以**工作区为 cwd** 启动 MCP 子进程（`cordis.patch.yml` 的
  `CODERAG_ROOT: process.cwd()` 正依赖这一点），而 `python -m` 会把 cwd（`''`）放到
  `sys.path` 最前，于是工作区里的 `token.py` 覆盖了标准库 `token`。`types.py`、
  `parser.py`、`config.py`、`logging.py` 等同理——**对 Python 项目命中率不低**。
- 影响面：只在被索引工作区的**根目录**有同名文件时触发；DSH 自己的 TS 语料不会触发，
  所以 M2/M3 的全部实测都没暴露它。
- 建议动作（按优先级）：
  1. `cordis.patch.yml` 的 `args` 改为不把 cwd 放进 `sys.path` 的启动方式，例如
     `['-c', 'import runpy,sys; sys.path.pop(0); runpy.run_module("dsh_coderag.server", run_name="__main__")']`；
     或 Python ≥3.11 时用 `-P`（本项目支持 3.10，故不能只靠 `-P`）。
  2. 在 `dsh_coderag/server.py` 顶部做 `sys.path` 防御（删除 `''`/cwd 项后再导入其余模块），
     但需注意 `-m` 下导入已经发生，真正可靠的拦截点在 `__main__` 入口。
  3. 补一条回归测试：在 `tmp_path` 放一个 `token.py`，断言 `python -m dsh_coderag.server`
     仍能完成 MCP 握手。
- **已解决（commit 见本节末）**：采纳了两层防护，并修正了上面"建议 1"的方向——
  用 `runpy.run_module` 的 `-c` 一行**并不解决问题**，因为 `-c` 里 `import runpy` 时
  `runpy` 仍会走 `types`（`runpy → importlib.util → contextlib → functools →
  from types import GenericAlias`），工作区的 `types.py` 一样能打断它。真正的解法是
  **让 `-c` 只导入我们自己的包**，把 `sys.path` 清理放进包内、且在第一个可被遮蔽的导入之前：
  1. `cordis.patch.yml` 的 `args` 改为 `['-c', 'import dsh_coderag.server as s; s.run()']`
     ——`-c` 本身不导入 `runpy`，因此解释器启动阶段不会被工作区文件打断。
  2. `dsh_coderag/__init__.py` 在**任何子模块导入之前**删除 `sys.path` 里的 `''` / `.` / cwd
     （引擎只把用户文件当文本读，从不 import 它们，所以移除是安全的）。
  3. `tests/test_cwd_shadowing.py` 三条回归：patch 里的启动串与测试常量一致、
     `-c "import dsh_coderag"` 在工作区含 `token.py`/`types.py`/`parser.py`/`logging.py`/
     `config.py` 时仍成功、以及用**与 patch 完全相同的 argv** 完成一次 MCP 握手。
- **实测验证**：在同时含上述 5 个同名文件的工作区里，DSH 会话中
  `code_search` 调用 5 次、返回 `status: ready` / `scanned: 6 files / 7 chunks` /
  `auth.py:1-3`，**无任何 ImportError**。
- **残余边界（无法从包内修复）**：手工执行 `python -m dsh_coderag.server`（不经 `-c`）
  且工作区含 `types.py` 这类 **`runpy` 自身依赖**的文件时，失败发生在解释器启动阶段、
  早于我们的代码；另外 `sitecustomize.py` 之类由 `site` 在启动时导入的文件同样无法拦截。
  请使用 `cordis.patch.yml` 的启动方式。
- 关联：属 `T1-14`（patch 启动方式）/ `T4-02`（可分发的 bundle patch）范围；
  已在发布前修掉。

## 编码规范欠账：12 个函数超过 50 行（发现于 T4-10）—— **已还清**

- 现状：`src/` 里 **0 个**函数超过 50 行（AST 复检 `end_lineno - lineno + 1`）；
  `AGENTS.md` C-04 的「当前未达标」标注已移除，检查方式补上了这条 AST 口径。
- 落地提交：`d48f87d`（`server`）、`387e224`（`searcher`）、`27efc2e`（`indexer`）、
  `3b8f343`（`eval` 的 tasks / report / `__main__` / attribute）、`7dd986f`（`eval/ab`）。
- 手法：一律**提取私有 helper**（如 `_search_sql`、`_TraceAcc`、`_plan_group`、`_IndexFacts`、
  `_run_options`），公开 API 与行为不变；拆分后 445 条测试与 L1/L2 门禁全绿。

## 编码规范欠账：没有 Windows 风格路径的测试（发现于 T4-10）

- 现象：`AGENTS.md` C-07 要求「单元测试覆盖 Windows 风格输入」，但 `tests/` 里**一个都没有**
  （搜 `C:\`、`PureWindowsPath`、`ntpath`、反斜杠路径输入均无命中）。
- 现状：**生产代码是合规的**——`walker.py` / `indexer.py` / `chunker.py` / `searcher.py` / `sanitize.py`
  共 6 处用 `Path.as_posix()` 把入库路径转成正斜杠的工作区相对路径；缺的是**把这些行为钉住的测试**。
- 建议：补一条参数化测试，喂入 Windows 风格（如 `a\\b\\c.py`）与绝对路径，断言入库路径为正斜杠且相对；
  可复用 `tests/test_walker.py` 的 `tmp_path` 模式。
- 补齐后同步删掉 `AGENTS.md` C-07 行的「当前未达标」标注。

## ✅ 已解决：A 批回放用例的条数断言停在 10（发现于 T5-01，2026-09-23 由用户指示修复）

- 现象：`tests/test_eval.py::test_a_batch_runs_against_indexed_corpus` 断言 `len(tasks) == 10`，
  而 `eval/tasks.jsonl` 在 `T3-02b` 补足 B 批后已是 **30 条**（12 exact + 11 crossfile + 7 natural）。
- 复现（opt-in，需已索引语料）——**修复前**：
  ```sh
  CODERAG_EVAL_CORPUS=/tmp/dsh-coderag-t3-03-corpus python -m pytest tests/test_eval.py -q
  # E  AssertionError: assert 30 == 10
  ```
- 影响：默认套件**不受影响**（该用例用 `CODERAG_EVAL_CORPUS` 门控，未设则 skip，`eval-gate.sh`
  默认也不设它）。但若按 `EVAL.md` §4.1 设了该变量跑真实语料回放，这一条会假红。
- 根因：断言写的是 A 批的条数，B 批并入后没有同步；docstring 也仍写 "the frozen 10-task A-batch"。
- **修法（不是把数字改成 30）**：新增 `_golden_task_count()`，把期望条数锚在 **`eval/tasks.jsonl` 的非空行数**上；
  断言改为 `len(tasks) == _golden_task_count()`，并把 `run.results` / `task_count` / `results` 三处
  `== 10` 一并改为 `== len(tasks)`。用例同时改名为
  `test_golden_set_runs_against_indexed_corpus`（原名里的 "A-batch" 已不成立），docstring 与
  `EVAL.md` §4.1、`TESTING.md` §3.10 的引用同步。**这样 golden 集再扩也不会漂**，而它真正要证的
  "每一条都被回放、不被静默截断"仍然成立。
- **修复后复跑**（同一条命令）：`28 passed in 6.86s`（修复前是 `1 failed`）。
- 归属备注：本条属 `tests/` 代码改动，不在 `T5-01` 的产出文件（`EVAL.md`）内，当时按 `AGENTS.md` §9
  **只记录未修**；2026-09-23 由用户明确指示修复，故在此闭环。

## 文档过期项审计（2026-09-23；由 `T5-01`–`T5-04` 修复）

> 审计方式：把主文档与 `docs/` 的可核对陈述（`docs/research/` 除外）逐条对**已安装的 DSH 包**与
> **本仓库代码**核对。结论：**既有过期项 22 处**，只影响文档可信度、不影响代码行为。修复任务见
> `PROJECT.md` §6.5 的 `T5-01`–`T5-04`；**这是 2.0.0 动工前的基线清理**。

**`EVAL.md`（→ `T5-01`）**

- `:29` L2 工具列写"`dsh-eval-harness`（现成）"，`:370` 章节标题写"用现成工具，不要自己写"——
  实际 L2 跑自建的 `scripts/ab_eval.py`，且 `§3.6` 已写"状态：已实现"。
- `:411` "因此 `T3-00` 是一个新增的前置任务"——`T3-00` 已完成。
- `:541` / `:544` / `:645` 引用不存在的 `tests/test_retrieval_quality.py`；`:556` 引用不存在的
  `indexed_workspace` fixture。
- `:183` / `:641` 的 `python -m dsh_coderag.eval validate eval/tasks.jsonl` 缺 `--tasks`/`--root`，
  按现 CLI 会失败。
- `:225` "`limit` 默认是 **12**"——`PROJECT.md` §3.5 与 `server.py` 都是 **5**。
- `:38` "L2 只在 M3 决策门跑一次"——已跑 `a-v1`/`b-v1`/`b-r5`/`a-smoke` 多轮。
- `:640` "（3~4 小时）"与 `:52`/`:157` 的 4–5h 冲突。
- `:572` / `:646` 仍把 `eval_run`/`eval_gate` 当"L2 主选"——已被 `§3.6` 的自建 runner 取代。

**`TESTING.md`（→ `T5-02`）**

- `:100` 目录树列 `test_retrieval_quality.py`（不存在）；`:178` 列 `tests/e2e/test_stdio_protocol.py`
  （目录不存在，也没有任何带 `e2e` marker 的用例）。
- `:102` 说属性测试在 `test_too_many_files.py`——hypothesis 只在 `test_chunker_decl.py`。
- `:103` 漏了 `test_cjk_recall.py`（`T3-13` 的中文用例主落点）。
- `:484` 引用不存在的 `indexed_eval_corpus` fixture（实际是 `eval_corpus`）。
- `:838` "不做多平台矩阵"与 `:730` "跑多平台矩阵（3 OS × 2 Python）"直接冲突。
- `:645` "`FTS5_UNAVAILABLE` … 必须同步加进去"——早已加进 `PROJECT.md` §5.6。

**`docs/adr/ADR-14`（→ `T5-03`：加日期化后续状态，**不改写历史结论**）**

- `:137` "**S3 未测量** … `T3-05`/`T3-06` 尚未执行"——`§10.1` 已记录 S3（0.308 → 0.564）。
- `:156` "未决前置：L2 runner 必须先自建"——已完成（`§10`）。
- `:154` 把已完成的 `T3-12` 仍列在"后续任务"里。

**里程碑快照（→ `T5-04`：加日期化后续状态）**

- `docs/m4-bundle.md:19` / `:138` / `:140` "干净 profile 端到端 ⏳ 属 `T4-08`"——`T4-08` 已完成。
- `docs/m1-findings.md:92-94` "`path`/`max_tokens` 尚未生效（T2 范围）"、"召回模式属 T2-19"——均已落地。
- `docs/m2-findings.md:79-80` / `:120` "缺少精度/召回双模式与标点路由"——已落地（`searcher` 三级召回、`ADR-13` 路由）。

**已核对、无需改动**：`docs/backlog.md`、`docs/m2-chunk-audit.md`、`docs/m3-eval-harness-check.md`、
`docs/eval-report-m3.md`、`docs/architecture.md`（除版本号，属 `T5-13`/`T5-17`）。

**已由项目所有者裁决（2026-09-23；四个问题全部有答案，不要再自行裁决）**

1. **版本号原先写错了**：`0.1.0` 不正确，**当前版本应为 `1.0.0`**，下一个版本是 **`2.0.0`**。
   已就地更正：`pyproject.toml` / `package.json` / `src/dsh_coderag/__init__.py` / `README.md` /
   `docs/architecture.md` / `CHANGELOG.md` / `PROJECT.md` 的 M5 目标（原写 `v0.2.0`）；
   `tests/test_cwd_shadowing.py` 里硬编码的版本断言改为与 `__version__` 比较（否则每次升版都脆断）。
   这同时解决了"`ADR-15` 的 `v1.0` 指什么"——**`v1.0` 就是 `1.0.0` 这条发布线**，`ADR-15` 无需改措辞。
   **历史证据里的 `0.1.0` 一律保留**：§6.7 进度表与 `docs/m4-install-verification.md` 的原始输出
   记录的是当时真正打印出来的字符串（`AGENTS.md` §5.3 要求原始输出）。
2. **`TESTING.md` §1 的"~100 / ~40 / 3"是目标（下限）**，不是现状——已在 §1 显式标注，
   不再算"过期项"。
3. **A5 判据以 `ADR-14:140` 的「收紧」为准**（不是"放宽"）——本文件前面的建议措辞已改齐。
4. **`EVAL.md` 的两处示例数字已与真实 30 条集对齐**：`24/30 → 13/30`、`Success@5 = 0.800 → 0.433`、
   CI `[0.63, 0.90] → [0.274, 0.608]`（`20/24 → 13/30`、`0.833 → 0.433` 同上）。

## 计划：`ADR-17` 的落点表把两处实现工作指派给文档任务 `T5-19`（发现于 T5-19）— **已解决（2026-09-24）**

- 现象：`ADR-17` §5「落点清单」第 3 项把 `src/dsh_coderag/config.py` 的 `SemanticConfig`
  字段说明指派给 `T5-19`；§6 又把 `SEMANTIC_*` code 登记进 `PROJECT.md` §5.6 与
  `src/dsh_coderag/types.py` 的动作之一指派给 `T5-19`。但 `PROJECT.md` §6.5 的 `T5-19`
  任务行「产出文件」列只有 `EVAL.md`、`TESTING.md`，验收命令也只 grep 这两份文档。
- 根因：`SemanticConfig` 与 `SEMANTIC_*` code 目前都还不存在（`config.py` 对 `SEMANTIC`
  零命中、`ErrorCode` 仍是 10 个），它们的实现属当时被 `T5-14` 阻塞的 `T3-08`–`T3-11`；
  落点表的任务号疑似应为 `T5-20`（实现云端后端）或 `T3-08`。
- **裁决与处置（2026-09-24，项目所有者）**：`T3-08` 的「产出文件」扩为
  `embed.py` + `config.py` + `types.py` + `tests/test_embed.py` + `tests/test_config.py`
  + `tests/test_types.py`；`ADR-17` §5 第 3 项与 §6 的登记动作改指派给 **`T3-08`**
  （同表第 1/2 项一并按实情更正为 `T5-21`）。本条关闭。

## 文档：`README.md` / `PROJECT.md` 的实测数字停留在旧金标集（发现于 T3-11 扩桶）

- 现象：`README.md` 的「实测评测数据」与 `PROJECT.md` §1.4/§6.7 里的 `S1 = 0.433`、`S2 = 0.313`、
  `S4 = 2492` 是在 **30 条、`golden_version = m3-b1`** 上测的。2026-09-25 把 `natural` 扩到 20 条后
  金标集变成 **43 条、`m3-b2`**，同一套默认路径的实测值变为 `S1 = 0.302`、`S2 = 0.219`、`S4 = 2876`
  （`eval/runs/l1-baseline.json` 已随之重建，门禁 `PASS`）。
- 根因：换金标集必然改变分母，桶配比变化（`natural` 7→20）会稀释 `Success@5`。这不是回归，
  是**评测口径变化**；但文档里只写数字不写口径，读者会误以为是实现退化。
- 建议：把 `README.md` / `PROJECT.md` 的**当前值**改标为 `golden_version = m3-b2`（43 条）的读数，
  并在同一处注明**历史 `m3-b1`（30 条）的读数**（`0.433 / 0.313 / 2492`）以保留可追溯性；
  `§6.7` 里已粘贴的历史证据**不动**（`AGENTS.md` §5.3 要求原始输出）。
- 归属：`T5-13`/`T5-17` 的文档对齐范围；本次（`T3-11`）不顺手改，以免污染评测相关提交。

## README 结构与 `AGENTS.md` D-03/D-05 的偏离（2026-09-25，项目所有者指示）

- 变更：按用户指示把 `README.md` 从 453 行重构为 191 行，只保留四块——**顶部安全声明**、
  **实测评测提升**（3 trials 的 A/B）、**安装**、**配置**、**安全与隐私警告**；
  删去了「当前状态」「它是怎么工作的」「工具」「CLI」「实测评测数据（S1/S2 未达标）」
  「已知限制」「开发」「文档」等小节。
- 偏离的条文：
  - `D-03` 要求 README 包含**能力说明 / 安装 / 配置 / 限制 / 安全声明 / 实测评测数据 / 已知问题**——
    新的 README **没有「限制」与「已知问题」小节**。
  - `D-05` 要求「任何新增的已知限制必须写进 README 的 `## 已知限制`」——该小节已不存在，
    因此**今后新增限制无处可写**（当前仍记录在 `docs/backlog.md` 与本文件各任务的备注里）。
  - `D-08` **未偏离**：README 仍带完整的云端后端外发风险声明（7 条要点齐全），
    因为那是「安全性警告」的一部分。
- 未删除的既有信息（仍在仓库中，只是不在 README）：能力说明与架构见 `docs/architecture.md`；
  已知限制与欠账见本文件；评测细节见 `docs/eval-report-m3.md` 与 `docs/eval-report-m3c.md`。
- 建议：由项目所有者裁决是 (a) 修订 `AGENTS.md` 的 `D-03`/`D-05` 以匹配新的 README 定位，
  还是 (b) 在 README 里恢复一个精简的「已知限制」小节。**在裁决前不要按旧的 D-03/D-05 判 README 不合格。**

> **补充（2026-09-25，同日第二次修改）**：按用户指示把「**项目功能概述**」（能力说明）与
> 「**它是怎么工作的**」（架构与运行形态）加回了 README，并补回「**文档**」索引表。
> 因此 `D-03` 要求的**能力说明 / 安装 / 配置 / 安全声明 / 实测评测数据**六项现已齐备，
> **仍然缺的只有「限制」与「已知问题」两项**（`D-03`）以及 `D-05` 的 `## 已知限制` 落点。
> README 现为 250 行，结构与新增小节的每条声明都已逐条对本仓库代码核实
> （18 条文档链接全部有效；MCP 工具前缀、标点路由、token 预算省略报告、文件数上限、
> stdio 拉起方式、索引落点均实跑/实查确认）。

## 四个 M5 任务因发布范围调整而出范围（2026-09-25，项目所有者裁定）

- 事实：`T3-11` 的 C 组实测触发 `ADR-14` §10.4 的 **`V4`**（`V1` 未达 `natural 6/20 = 0.300`、
  `V2` 未达 `exact 0.917` + 1 条回归），**向量路径不发布**；只读原型进一步给出 oracle 上界
  `7/20 = 0.350 < 0.40`，说明融合/重排侧无解。项目所有者裁定 2.0.0 **只发布在 GitHub**，
  **不发布到 PyPI / npm**。
- 结果：`T5-15`（extra `semantic` + `install.sh` 开关）、`T5-16`（可选安装冒烟）、
  `T5-20`（云端后端实现）、`T5-22`（云端安全评审）**移出 2.0.0 范围**。
- 保留情况：四个任务的**任务行仍留在 `PROJECT.md` §6.5**（并在该节记了日期化裁决），
  以便将来重启向量线时直接复用；`ADR-16`/`ADR-17` 的条文**仍然有效**，只是没有对应发布对象。
  `T5-17` 的依赖已由 `T5-16, T5-13, T5-22` 收窄为 **`T5-13`**，§6.6 依赖图已同步重建。
- 说明：`pyproject.toml` **从来没有** `semantic` extra（`T5-15` 未执行），`dependencies` 里
  **没有** numpy / httpx / 任何向量库，因此「默认安装零向量依赖」（`RL-10`）**当前即成立**。
