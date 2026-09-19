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

## 分块器：TS `type` 别名与 `const`/箭头函数未纳入声明（发现于 T2-18）

- 现象：`DECLARATION_KINDS["typescript"]` 只含 function/class/interface/method；
  `type_alias_declaration` 与 `lexical_declaration`（含箭头函数）落入 gap。
- 后果：DSH 语料 69.6% 的 chunk 是 gap（35638/51230），单行 gap 4980 个。
- 建议：把这两类纳入声明集合（`lexical_declaration` 仅在值含箭头/函数时）。

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

