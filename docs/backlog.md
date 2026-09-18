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
