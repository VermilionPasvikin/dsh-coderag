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

## 检索：未实现精度/召回双模式（发现于 T2-17 / T2-19 / T3-03）

- 现象：`_build_match` 把所有词作为必须命中的短语（AND）；DSH 语料上纯中文原问句
  5/5 返回 `status: empty`（T2-17），T2-19 只解决了标点路由，未改这一点。
- T3-03 量化：A 批 10 条中 9 条含中文，**全部 `status: empty`**；把同一标识符的中文后缀去掉后，
  三个 exact 目标都回到 top-5（`CONTEXT_WINDOW_EXCEEDED_CODE` 名次 5、
  `delegationDepthOf` 3、`SANDBOX_MODES` 4）。所以失败不是索引缺失或标识符搜不到，
  而是 AND 把**不可能命中的 CJK bigram** 也当成必须命中项，一条不中就整条归零。
  这意味着 exact 桶（EVAL.md §2.3 的 regression 桶）被同一个根因拖到 1/4。
- 设计（§5.3.1）：先精度模式（标识符整体短语 + CJK bigram 短语），0 条时**降级到召回模式**，
  两者都 0 才 empty。
- 建议：实现召回模式（放宽 AND / 子串命中），中文自然语言查询才有机会命中。

## 检索：exact 查询的定义处被使用处与测试文件压过（发现于 T3-03）

- 现象：裸标识符查询能命中，但**定义处排在第 3–5 名**。例：`CONTEXT_WINDOW_EXCEEDED_CODE`
  的前 4 条全是 `*.spec.ts`（compaction-basic、llm-pi-ai 的测试），定义处
  `packages/llm/llm/src/error.ts` 第 5；`SANDBOX_MODES` 前 3 条是 `invariant.ts`，
  定义处 `session-mode.ts` 第 4。
- 后果：`k=5` 时 exact 桶在 rank 边缘压线，任何轻微打分变化就会翻成未命中；EVAL.md §2.7
  对 exact 的阈值是 0.90，这个排名分布没有余量。
- 建议：路径/符号信号加权——测试路径（`tests/`、`*.spec.*`）降权，声明定义处加权
  （§3.3 第 3 步「结构化加分」目前未实现）。

