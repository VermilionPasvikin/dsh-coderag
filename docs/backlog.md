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
- 建议：`classify` 的 A5 判据应从"目标文件里一个 query 词都没有"放宽为"目标文件里没有
  **判别性**（低文档频率）的词"。需要按 token 统计文档频率，属独立改动。
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
