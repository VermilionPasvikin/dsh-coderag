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

## ✅ 已还清：没有 Windows 风格路径的测试（发现于 T4-10，由 **T6-03a** 还清）

- 现象：`AGENTS.md` C-07 要求「单元测试覆盖 Windows 风格输入」，但 `tests/` 里**一个都没有**
  （搜 `C:\`、`PureWindowsPath`、`ntpath`、反斜杠路径输入均无命中）。
- 现状：**生产代码是合规的**——`walker.py` / `indexer.py` / `chunker.py` / `searcher.py` / `sanitize.py`
  共 6 处用 `Path.as_posix()` 把入库路径转成正斜杠的工作区相对路径；缺的是**把这些行为钉住的测试**。
- 建议：补一条参数化测试，喂入 Windows 风格（如 `a\\b\\c.py`）与绝对路径，断言入库路径为正斜杠且相对；
  可复用 `tests/test_walker.py` 的 `tmp_path` 模式。
- 补齐后同步删掉 `AGENTS.md` C-07 行的「当前未达标」标注。
- **落地（`T6-03a`，2026-09-30）**：`tests/test_path_filter.py` 新增
  `test_stored_paths_are_forward_slashed_and_workspace_relative`（把 `files.path` 钉成
  `pkg/sub/util.py`，并断言无反斜杠、无盘符、非绝对路径——这条在 Windows 上就是真正的 C-07 检查）
  与 `test_path_filter_accepts_windows_style_separators`（参数化 `pkg/sub` / `pkg\\sub` / `.\\pkg\\sub`，
  用 `PureWindowsPath` 构造 Windows 风格输入；`skipif` 非 Windows，因为反斜杠只在 Windows 上作为分隔符解析）。
  `AGENTS.md` 的 C-07 行已同步去掉「当前未达标」。**Windows 全量套件 568 passed / 2 skipped**。

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

## ✅ 已解决：`README.md` / `PROJECT.md` 的实测数字停留在旧金标集（发现于 T3-11 扩桶，2026-09-25 由 **T5-17** 复核关闭）

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

> **后续（2026-09-25）**：**README 那一半已自动失效**——README 已重构，不再包含 L1 的实测数字小节；它现在给的 A/B 数字来自 `cases/`（L2 用例），**与金标集版本无关**。因此本条的剩余部分只剩 `PROJECT.md`：`§6.7` 里 `m3-b1` 口径的历史证据**按 `AGENTS.md` §5.3 保留不动**，无需改标；`§1.4` 的阈值本身没有随金标集变化。**本条可视为已关闭**（由 `T5-17` 复核一次即可）。
>
> **复核与关闭（2026-09-25，`T5-17`）**：上面两条声明已逐条实测，全部成立——
> `grep -n '0\.433\|0\.313\|2492\|Success@5\|MRR' README.md` → **无命中**（README 确已无 L1 数字）；
> `python3 scripts/verify-plan.py .` → `成功标准 S*: 6 条全部在矩阵里`、`计划完备性：通过 ✅`（§1.4 的
> `S1`–`S6` 标识与阈值结构未变）；`§6.7` 的 `m3-b1` 历史证据一字未动。**本条关闭**——只改本小节标题与
> 这一段，原始分析原样保留。
>
> **⚠️ 关闭时另发现一处残留（不在本条原范围内，故只记录、不顺手改）**：`PROJECT.md` §1.4 的 `S5` 行括号里
> 仍写「其余口径与 L1 相同：**30 条**、宏平均、`k=5`」与「**7 条**里至少 3 条命中」，`S6` 行仍写「**30 条**
> query」——这三处**样本数**在 `natural` 7→20、金标集 30→43 之后已经过期（阈值 `≥ 0.40` 与「回归条数 = 0」
> 本身不受影响，故本条结论不变）。归属是 `T5-17` 产出文件范围之外的独立小修，建议下次动 `PROJECT.md` 时
> 把样本数改为 43 / 20 并注明 `golden_version = m3-b3`。

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

## 平台范围变更：从「只实测 macOS」到**跨平台**（2026-09-25，项目所有者指示）

- 事实：项目所有者需要在 **Windows** 机器上继续开发，并要求本项目**具备跨平台能力**——
  Windows / macOS / Linux 同等可用，**不是**改成只在 Windows 上跑。这**推翻了**此前的平台口径——
  `docs/architecture.md` 声明验证环境只有 macOS，`docs/m4-install-verification.md` 写着
  「Python 侧只在 forBSH 上实测过」。
- 记账：新增里程碑 **M6（v2.1.0）= `PROJECT.md` §6.5.1 的 `T6-01`–`T6-05`**，
  **本次不做代码实现**，只把任务与判据写进计划并同步文档。附带发现 `PROJECT.md` §6.6 的导语
  仍写「从 §6.1–§6.4 各任务表生成」（脚本实际读整个 §6），已改为「§6.1–§6.5.1」。
- **设计决定（项目所有者裁定，2026-09-25）**：**Python CLI 是唯一跨平台入口**。
  把「探测解释器 / 校验版本区间 / 预检 FTS5 / `pip install` / 恒等自检」从 `scripts/install.sh`
  （239 行）搬进已有的 `src/dsh_coderag/__main__.py`，新增 `doctor` 与 `install-deps` 子命令；
  `scripts/install.sh` 与 `scripts/dsh` **退化为薄包装**（只做"找到解释器 → 转发"）。
  **被否决的方案**是为 Windows 另写 `install.ps1` / `dsh.ps1`：那会让 239 行安装逻辑永久分叉，
  真正的风险是两套实现日后必然漂移，且**无法被 pytest 覆盖**。
  **不删除**这两个 shell 脚本——macOS 的既有实证记录引用它们，删掉会失去可复现性。
- **未落地的既有要求（本条的欠账部分）**：`TESTING.md` §5.1 要求跑 **3 OS × 2 Python 矩阵**，
  而仓库里**没有 `.github/`**——该矩阵至今一次都没跑过。M6 不假装它跑过，也不把它的结论
  算作跨平台证据；证据只认 `docs/m6-crossplatform-baseline.md`（逐平台基线）与
  `docs/m6-windows-smoke.md`（端到端冒烟，两平台结论并列）。
- 边界：M6 **不放宽 2.0.0 的任何既有判据**（`S1`–`S6`、`RL-10` 一律不动），
  **也不降低 macOS 的既有验收**——跨平台是"多一个平台达标"，不是"把原来的标准摊薄"。
- 另一条相关的未还欠账：`C-07`「单元测试覆盖 Windows 风格输入」当前未达标（本文件有专条），
  归 `T6-03a` 一并还清。

## Windows 基线上的既有测试失败（发现于 `T6-02`，**T6-03a 已处置 (a)(b)(c)**）

> 判定方法：把 HEAD（`dc7d971`）签出到独立 worktree，用**同一个解释器**跑同一批用例——
> 下面三条在 HEAD 上**同样失败**，即与 `T6-02` 的改动无关。完整命令与输出见
> `PROJECT.md` §6.7 的 `T6-02` 行。`T6-03a` 的出口判据是「Windows 上全量通过且**无 xfail**」，
> 所以这三条必须先有处置口径。

### ✅ (a) 可选向量依赖 `numpy` 不在任何已声明的 extra 里 —— 已由 `T6-03a` 按 2026-09-30 裁决处置

- 现象：在没有 numpy 的解释器上，`tests/test_vectors.py` 与 `tests/test_vector_search.py`
  **收集阶段就失败**（`ModuleNotFoundError: No module named 'numpy'`，`--ignore` 之外无解）；
  `tests/test_index_vectors.py` 的 4 条则断言失败，stderr 给出
  `"code": "SEMANTIC_BACKEND_UNAVAILABLE", "message": "numpy is required for the optional vector backend"`。
  `mypy --strict src/` 同时报 `src/dsh_coderag/vectors.py:31: Cannot find implementation or
  library stub for module named "numpy"`（那是 `if TYPE_CHECKING:` 里的导入）。
- 根因：`pyproject.toml` 的 `optional-dependencies` **只有 `dev`**——`T5-15`（extra `semantic`）
  已按 2026-09-25 的发布范围裁决**移出 2.0.0**（见本文件「四个 M5 任务因发布范围调整而出范围」），
  于是**没有任何声明途径**能装出跑这些测试所需的 numpy。macOS 侧一直是**手工**
  `pip install numpy` 才跑通的（`T3-09` 的备注即如此记录）。
- **处置（`T6-03a`，2026-09-30 项目所有者裁决，方案 A）**：恢复
  `semantic = ["numpy>=1.26"]`（与 `ADR-16` §3.2 冻结的内容逐字一致）——这不是放宽 `RL-10`，
  而是修复一处既有的不自洽：`RL-10` 原文要求"向量只能是**可选的 extra**"，而 extra 当时并不存在。
  `dependencies` / bundle tarball / `install.sh` 默认路径 / README 前置条件一律不动。
  `T6-04` 的「默认态解释器里没有 numpy」同时改为**过渡式断言**（在一次性全新解释器里跑默认安装后
  断言 `import numpy` 失败）——那一条原本是**代理指标**：它验的是状态而非因果，既会因别处装了 numpy
  而假红，也会在 `--skip-install` 时假绿。详见 `PROJECT.md` §6.5.1 的 2026-09-30 裁决。
- 实测后果（隔离 venv 量出，conda 环境当时保持无 numpy）：全量 `6 failed, 528 passed` →
  **`564 passed, 2 skipped`**；那三个向量模块 **38 passed**；`mypy --strict src/` 由 1 error 变干净。
- 仍保留：`ADR-16` §3.2 的 `CODERAG_WITH_SEMANTIC` 安装开关未实现（`T5-15` 仍在范围外）；
  可选路径目前的安装入口只有 `pip install -e ".[semantic]"`。

### ✅ (b) `tests/test_walker.py::test_walk_recurses_into_subdirectories` 断言里假定正斜杠 —— 已由 `T6-03a` 修

- 现象：`assert 'pkg/sub/util.js' in ['app.ts', 'lib.c', 'main.py', 'pkg\\sub\\util.js']`。
- 根因：**测试自己的 helper** 用了 `str(path.relative_to(base))`
  （`tests/test_walker.py` 的 `_relative_paths`），在 Windows 上产出反斜杠。
  生产代码是合规的（`walker.py` / `indexer.py` 等 6 处用 `Path.as_posix()` 入库），
  即这条与 `C-07` 是同一主题的**测试侧**版本。
- 修法：`_relative_paths` 改用 `path.relative_to(base).as_posix()`。断言本身一字未改（`T-08`）。

### ✅ (c) `tests/test_metrics.py::test_wilson_interval_stays_inside_zero_and_one_at_the_boundaries` —— 已由 `T6-03a` 修实现

- 现象：`wilson_interval(0, 10).low` 在 Windows 上是 `2.7755575615628914e-17`，断言要求 `== 0.0`；
  macOS 的既有证据（`T3-04`）记的是 `0/10 → [0, 0.277533]`，即当时恰好是精确的 `0.0`。
- 根因：Wilson 下界在 `p_hat = 0` 时数学上恰为 0（`center` 与 `margin` 相等），实现按
  `center - margin` 算，两条式子走了不同的浮点路径，差值落在区间**内部**约 `2.8e-17`——
  `max(0.0, ...)` 拦不住，因为它只防负数。**平台/`libm` 相关**，不是逻辑错误。
- 修法：在**实现**里把两个精确端点钉住（`successes == 0` → `low = 0.0`；`successes == total` →
  `high = 1.0`），与 `Interval` 自己 docstring 的「clamped to [0, 1]」契约一致。
  **没有放宽断言**（`T-08`）——`== 0.0` 与 `== 1.0` 原样保留，这正是 `T6-03a` 要求的修法。

## 薄包装的 LF 保证目前只靠「写入时是 LF」（发现于 `T6-02`；**已由 `T6-11` 修复**）

> **状态：已修复（`T6-11`，2026-09-30）。** 仓库新增 `.gitattributes`：`*.sh text eol=lf`、
> `scripts/dsh text eol=lf`、`.gitattributes text eol=lf`；三个脚本由 `w/crlf` 变为 `w/lf`
> （工作树 CR 由 31 / 38 / 155 变为 0），并由 `tests/test_script_eol.py` 兜住。
> **没有改脚本内容、也没有改用户级 `core.autocrlf`**。下面的过程记录保留。

- 事实：`scripts/dsh` / `scripts/install.sh` / `scripts/eval-gate.sh` 在 git **索引里都是 `i/lf`**，
  但仓库**没有 `.gitattributes`**，而 Git for Windows 的默认 `core.autocrlf=true` 会把这些文件
  在工作树里签出成 **CRLF**（本机实测：三个文件均为 `w/crlf`）。
- 后果：Windows 用户若用 Git for Windows 自带的 `bash` 跑它们，脚本正文带 `\r`；
  `sh`/`bash` 对 `\r` 的容忍度不一致（本机 `bash -n` 能过，但 `./script.sh` 的 shebang 解析会失败）。
- 建议：加 `.gitattributes` —— `*.sh text eol=lf` 与 `scripts/dsh text eol=lf`，让**每个平台**都签出 LF；
  这样 `T6-03a` 才能加一条稳定的「脚本无 CRLF」测试。属独立小改动，需所有者确认是否纳入 M6。
- **后续实测（2026-09-30，`T6-05` 复核）把这条的严重度下调**：`git ls-files --eol` 显示三个脚本的
  **blob 都是 `i/lf`**（仓库侧本来就是对的），CRLF 只出现在本机工作树；而 **Git for Windows 的 bash
  容忍 CRLF**——实测 `./scripts/dsh --version` 在 CRLF 下正常打印 `0.1.5-rc.1`（走钉版本的 npx）。
  所以「CRLF 会让 sh/bash 报错」在**能跑这两个脚本的那个 shell 上并不成立**。`*.sh text eol=lf`
  仍是一个便宜的加固（能让「脚本必须 LF」在每个平台都可断言），但**已不再是隐患**。

## 环境变量配置面在 MCP 路径上不生效（发现于 `T6-05` 复核，2026-09-30；**已由 `T6-07` 修复**）

> **状态：已修复（`T6-07`，2026-09-30）。** 修法与验收见下；本条目保留为「症状 → 根因 → 修法」的记录，
> 因为它是「单测全绿但端到端无效」这一类缺陷的样本，且 `docs/` 里曾以它为已知限制引用过。

- **现象（实测）**：`README.md` 的配置表曾承诺 5 个上限变量，但通过 MCP 使用时**没有一个起作用**：

  | 变量 | 实测 | 结果 |
  |---|---|---|
  | `CODERAG_MAX_TOKENS` | 子进程环境设 `1` 与设 `8000`，同一条 `code_search` 输出**逐字相同**（6 hits、无省略提示） | 不生效 |
  | `CODERAG_MAX_FILES` | 设为 `1`，6 个文件的工作区 `index_status` 仍是 `state: ready, total_files: 6` | 不生效 |
  | `CODERAG_MAX_FILE_BYTES` | 设为 `20` 字节，48 字节的文件仍被索引（`total_files: 2`、`skipped.count: 0`） | 不生效 |
  | `CODERAG_BATCH_SIZE` / `CODERAG_MAX_WORKERS` | 未单独观测（它们只改**怎么做**、不改结果） | 源码判定不生效 |

- **根因（源码）**：`config.py` 确实把这 5 个读进 `IndexConfig`，但
  ① `server.py:295` 建索引时把 `index_sync` **裸传**给 `TaskManager.start(...)`，**不带配置**；
  ② `load_config()` 全项目只被调用一次（`server.py:155`），且**只取 `.root`**；
  ③ `server.py:218` 的 `max_tokens` 是**硬编码默认 4000**，不读 `CODERAG_MAX_TOKENS`。
  `__main__.py:446` 的 `index_sync(Path(args.path))` 同样不带配置。
- **后果**：`cordis.patch.yml` 里那条 `CODERAG_MAX_TOKENS`（还专门为「`TOKEN` 会被清洗」写了注释）
  以及 README 承诺的文件数/文件大小/并发上限**目前都是空承诺**——想用小机器保护自己的用户拿不到保护。
  注意这**不是**「静默截断」（`RL-08`）：上限根本没被应用，没有截断发生。
- **已做的处置**：`README.md` 的表格照实改写成「当前是否真的生效」四列，并指出**要限检索预算请用
  MCP 工具参数 `max_tokens`**；本任务**不修代码**（`T6-05` 的产出文件只有文档）。
- **修法（`T6-07` 已实施，2026-09-30）**：新增 `server.py::workspace_config(root)`——它把已知的
  `root` 填进环境后再调 `load_config()`，因此 `build_server(root=...)`（测试与嵌入调用）在不设
  `CODERAG_ROOT` 时也读得到可调变量，而显式设置的值仍然优先、格式错误仍然抛 `ConfigError`。
  然后把它接进三处：**建索引**（`TaskManager(...).start(target, partial(index_sync, config=config))`）、
  **检索的默认预算**（`arguments.get("max_tokens", workspace_config(root).max_tokens)`）、
  **工作区形态 `index_status` 的 skip 统计**（`walk_with_report(root, max_files=..., max_file_bytes=...)`，
  `§4.2` 要求过滤可见；超限时返回 `INDEX_TOO_MANY_FILES` 而不是兜底的 `SEARCH_FAILED`）。
- **验收（`T6-07`）**：`tests/test_server.py` 新增 3 条**走 MCP 工具**的测试（`CODERAG_MAX_FILES` /
  `CODERAG_MAX_FILE_BYTES` / `CODERAG_MAX_TOKENS` 各一条），**实测在未修复的 `server.py` 上 3 条全红**
  （`3 failed`，症状为 `assert 2 == 1` 与命中数未被裁剪），修复后全绿；`README.md` 的配置表随之
  由「未生效」改回真实状态。**这也解释了 `T2-21` / `T2-11` 的单测为什么全绿却端到端无效**：
  它们直接调 `index_sync(config=...)`，绕过了没传配置的那条路。

## `PROJECT.md` §6.7 进度表的行形态（发现于 `T6-09`，2026-09-30；**已由 `T6-10` 修复**）

> **状态：已修复（`T6-10`，2026-09-30）。** 修法与验收见下。本条目保留，因为它记录了**一次我自己的
> 误判**——首轮扫描报「14 行」，准确口径下只有 **6 行**是坏的。

- **事实（实测，已更正）**：§6.7 共 **97** 行进度记录。原因是贴进来的命令输出里带了 `|`（shell 管道、
  被整段粘贴的 Markdown 表格），Markdown 把它们读成**单元格分隔符**，于是该行多出列。
  **首轮我用朴素的 `split("|")` 数格数，得出「14 行」——那是错的**：它把**已经转义过的 `\|` 也算了进去**。
  按 Markdown 的真实口径（**未转义**的 `|` 数 ≠ 6）：

  | 分类 | 行 | 未转义 `|` 数 |
  |---|---|---|
  | **真的坏了（6 行）** | `T2-21` / `T2-22` | 7 |
  | | `T4-05` | 7 |
  | | `T5-09` | 8 |
  | | `T5-08` | 9 |
  | | `T3-07` | 11 |
  | **早已正确转义（8 行，不要动）** | `T2-05`(2) / `T3-10`(1) / `T4-01`(4) / `T4-04`(1) / `T4-06`(5) / `T4-07`(5) / `T5-13`(6) / `T5-17`(1) | 均为 6 |

- **后果**：渲染时坏行会向右多出空列，表头与其余行对不齐——**内容不丢、命令与读数都还在**，但表格结构是坏的。
- **修法（`T6-10` 已实施）**：把单元格内部的 `|` 转义成 `\|`（Markdown 里仍渲染为 `|`，**读数一字不改**）。
  每一步都过一道**无损校验**：把两行的竖线与转义反斜杠都去掉后，**非空白字符必须完全相同**——
  这条校验本身就是必要的，因为 `T4-05` 的正则里存在裸 `|`，转义会在它两侧引入空白。
  另外 `scripts/verify-plan.py` 新增 **`G1`**：§6.7 的每一行必须是 5 列（未转义 `|` 恰为 6），
  `scripts/test-verify-plan.py` 补了对应的**变异用例**（去掉 `T4-05` 行一处 `\|` 的转义）——
  门禁由 28 → **29 项**、变异由 19 → **20 个**，从此贴输出带 `|` 会**在门禁处报错**而不是悄悄破坏表格。
- **顺带修掉的一个真缺陷**：`scripts/test-verify-plan.py` **在 Windows 上根本跑不起来**——
  `subprocess.run` 没指定编码、子进程也没固定 UTF-8，cp936 控制台下 `UnicodeDecodeError` 让
  `r.stdout` 变成 `None`，随后 `None + str` 抛 `TypeError`。现在两侧都钉成 UTF-8（`T6-10`）。
  这是 `M6` 的「同一份逻辑跨平台」承诺里漏掉的一处：门禁本身是跨平台的，**证明门禁可信的那个脚本却不是**。

## `Chunk.low_confidence` 只存在于内存，从不落库也不渲染（发现于 `T6-17`，2026-09-30，**未顺手修**）

- **事实（实测）**：`chunker.py` 会在 L4（无解析器降级）等路径上把 `Chunk.low_confidence` 置真
  （`chunker.py:83` / `130` / `132`），但 `chunks` 表只有
  `id / file_id / seq / start_line / end_line / symbol_kind / symbol_name / text / content_hash`
  ——**没有这一列**，而 `render.py` 里 `low_confidence` **一次都没出现**。
  实测：把一个 `.MXML` 加进白名单并索引，得到的是 `symbol_kind = None` 的 chunk，
  「这块是低置信度切出来的」这件事**对模型完全不可见**。
- **影响**：`T2-04` 的行文是「无解析器降级（L4，带 `low_confidence: true`）」——字面成立
  （`Chunk` 上确实带这个字段），但**没有任何下游消费者**：模型无从判断某个 chunk 是猜着切的，
  也就无法据此降低信任。这与 `T6-17` 直接相关：**用户自行扩展的后缀全都走这条路**。
- **建议修法**：给 `chunks` 加一列（`SCHEMA_VERSION` 要一起动）并在渲染的位置行上标出来，
  例如 `── path:1-6  [low-confidence]  (chunk 0)`；补一条走 L4 的渲染快照测试。
  属独立改动，需所有者立任务。

## 白名单无法覆盖「没有扩展名」的文件（发现于 `T6-20`，2026-09-30，**未顺手修**）

- **事实（实测）**：把 `.dockerfile,.makefile` 加进 `CODERAG_EXTRA_EXTENSIONS` 后，索引一个同时含
  `Dockerfile` / `Makefile` 的工作区，入库的**只有 `.py`**——两者都没被收录。原因是匹配走
  `candidate.suffix`，而 `Path("Dockerfile").suffix` 是**空字符串**；同时 `_read_extensions` 要求
  每个 token 以字母或数字开头，所以也无法用「空扩展名」表达这个意思。
- **影响**：`Dockerfile` / `Makefile` / `LICENSE` 这类无扩展名文件在任何配置下都进不了索引，
  而它们常常正是「找构建/部署配置」时想搜的东西。
- **建议修法**：给 `_read_extensions` 增加一个显式记号（例如 token `no-extension`，或单独的
  `CODERAG_INCLUDE_EXTENSIONLESS=1`），并让 `walk_with_report` 在 `suffix == ""` 时按该开关收录；
  补一条安全测试——`Dockerfile` 能入库、而 `.env` 这类**同样 `suffix == ""`** 的文件仍被第一层
  密钥黑名单拦下（两者会同时落在这个分支上，必须证明过滤仍先于入库生效）。属独立小改动，需所有者立任务。

## CLI 的 `search` 不读 `CODERAG_MAX_TOKENS`（发现于 `T6-21`，2026-09-30，**未顺手修**）

- **事实（实测）**：`_run_search` 调的是 `search(Path(args.root), args.query, k=args.limit)`，
  **不传 `max_tokens`**，于是 `searcher.search` 用它的默认值 `DEFAULT_MAX_TOKENS`（4000）。
  实测：在工作区里造 40 个含同一标识符的文件并 `index`，然后
  `CODERAG_MAX_TOKENS=5 python -m dsh_coderag search … --limit 40` 与**不设该变量**的输出
  **逐字相同**（行数、字符数都一样）——变量没有被读。
- **影响**：`T6-17` 已把配置通路接进 CLI 的 `index`，但 `search` 这条支线漏了。
  README 的变量表把 `CODERAG_MAX_TOKENS` 标成「✅ 作为 `code_search` 的默认预算」，
  对 MCP 路径成立、对 **CLI 的 `search` 不成立**——同一份表里两种路径行为不同，容易误判。
- **建议修法**：`_run_search` 里同样调 `config.load_config_for(root)` 并把 `config.max_tokens`
  传给 `search(...)`（`--max-tokens` 之类的显式参数若存在应优先），
  再补一条测试断言「设了变量时命中被裁剪、不设时不被裁剪」。属独立小改动，需所有者立任务。

## `TooManyFilesError` 在 CLI 里被误报成 `CLI_UNEXPECTED_ERROR`（发现于 `T6-22`，2026-09-30，**待修**）

- **来源**：所有者实际报错（在 PowerShell 里设 `$CODERAG_MAX_FILES = 110000` 后跑 `index`）：
  `{"status": "error", "code": "CLI_UNEXPECTED_ERROR", "message": "TooManyFilesError: workspace has
  103973 indexable files, over max_files=20000"}`。
- **复现（本轮实测，2 个文件的工作区足够）**：`$env:CODERAG_MAX_FILES = '1'` 后
  `python -m dsh_coderag index <ws>` → 退出码 1，输出与上面同形：
  `{"status": "error", "code": "CLI_UNEXPECTED_ERROR", "message": "TooManyFilesError: workspace has
  2 indexable files, over max_files=1"}`。
- **为什么是缺陷**：`TooManyFilesError` 是**预期内**条件，它自带 `ErrorCode.INDEX_TOO_MANY_FILES`
  （`walker.py`），`RL-08` 要求的就是「显式失败并报告实际数量」——数量报对了，但：
  ① `code` 被 `main()` 的 `except Exception` 兜底成 `CLI_UNEXPECTED_ERROR`；
  ② 消息里泄出 Python 类名 `TooManyFilesError:`（用户可见文本不该有实现词汇）；
  ③ **不给任何修复提示**——而同一条件在 MCP 路径上（`server.py`）返回的是
  `Raise CODERAG_MAX_FILES above {actual_count}, or index a subdirectory.`。
  用户因此得自己猜「变量名对不对、值怎么给」，本轮就实际发生了一次。
- **建议修法**：在 `main()` 的异常链里显式处理 `TooManyFilesError`（放在 `CliError` 之后、`Exception` 之前），
  用它自带的 `code` 与 `payload`，并给一条**可照抄**的提示，例如
  `把 CODERAG_MAX_FILES 提到 103973 以上再重跑（PowerShell：$env:CODERAG_MAX_FILES = '110000'），
  或只索引子目录`；补一条测试断言 `code == index_too_many_files` 且消息里**不含** `TooManyFilesError`。

## 中断的索引对外自称 `ready`，形成静默的部分索引（发现于 `T6-23`，2026-09-30，**待修**）

- **来源**：所有者在真实工作区（`EXTRACTED_READABLE`，103,002 个可索引 `.mxml`）上跑首次索引，
  跑到约 78% 时**被用户用 `Ctrl+C` 主动中断**（已向所有者确认；**不是崩溃**，无 traceback）。**只读检查**该库得到：
  - `files` = **80,437**、`chunks` = **275,387**、`index.sqlite3` = **7.34 GiB**；
  - `workspace_index` = `(root, db_schema=1, ready=1, last_task_id=NULL, updated_at=1790777084)`；
    而本次运行最早的 `indexed_at` 是 **1790778154**——`updated_at` **早于**它，说明这行状态是上一次运行留下的；
  - `index_runs` 表 **0 行**（CLI 这条路径没有运行记录）；
  - 进程列表里没有 `index`（已结束/被打断），`last-index.json` 仍是上次 0 文件运行的记录。
- **为什么是缺陷**：缺了约 22% 文件的部分索引**对外表现为可检索**（`ready = 1`），于是 `code_search` 会对未入库的那部分返回「无结果」——按 `RL-06`，模型会把「查不到」读成「代码里没有」。这与 §8 的「静默截断」是同一类错误：
**观察到的结果变少了，但没有任何信号说明它变少了**。`T6-16` 修的是「0 个文件却说不清原因」，
这里是「少了一部分却完全不说」。
- **建议修法**：让 CLI 的 `index_sync` 与 MCP 路径对齐——开跑时写一行 `index_runs` 并把
  `workspace_index.ready` 置 0，跑完（或失败/被取消）时再更新为终态——**`Ctrl+C` 是用户最常用的结束方式之一，必须被当作正常终态处理**；这样中断后
  `index_status` 会如实报告「未完成」，而不是静默地少 22%。需补一条测试：
  在足以被 `SIGINT` 打断的语料上中断，断言 `ready = 0` 且 `index_runs` 有该次记录。
  属独立改动，需所有者立任务（`T6-23` 已立，待批准）。
