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

## 检索：未实现精度/召回双模式（发现于 T2-17 / T2-19）

- 现象：`_build_match` 把所有词作为必须命中的短语（AND）；DSH 语料上纯中文原问句
  5/5 返回 `status: empty`（T2-17），T2-19 只解决了标点路由，未改这一点。
- 设计（§5.3.1）：先精度模式（标识符整体短语 + CJK bigram 短语），0 条时**降级到召回模式**，
  两者都 0 才 empty。
- 建议：实现召回模式（放宽 AND / 子串命中），中文自然语言查询才有机会命中。

## 缺口 P1：单文件大小上限 `maxFileBytes` 未实现（文档一致性审查）

- 文档承诺：PROJECT §5.2「`maxFileBytes` 默认 1 MiB，超过则跳过并记入 `skipped`」；
  PROJECT §3.5 与 AGENTS §4.2 的 `skipped` 示例都含 `too_large`。
- 实际：**无任何任务行实现它**；`config.py` 无 `max_file_bytes`；`indexer._prepare_file`
  用 `absolute.read_bytes()` 整文件读入、`chunk_text()` 返回全部 chunk 后再写库（indexer.py:286）。
- 风险：生成的/压缩的超大单文件会一次性占用等量内存并产生超长 chunk 列表；DSH 语料最大
  文件 489 KB、>1 MiB 的 0 个，本语料暂不触发。
- 建议方案：`IndexConfig` 加 `max_file_bytes`（env `CODERAG_MAX_FILE_BYTES`，默认 1 MiB）；
  `walk_with_report` 用已有的 `stat` 大小在**读内容前**跳过并计 `reason="too_large"`；
  indexer 传入 `config.max_file_bytes`；补测试与 §6.6 验收。估时 1–2h。

## 缺口 P2：FTS5 能力探测未实现、`FTS5_UNAVAILABLE` 从不发出（文档一致性审查）

- 文档承诺：TESTING §4.2「FTS5 能力探测（**必须做**）」并给出 `sqlite_caps.fts5_available()`；
  PROJECT §5.6 列 `FTS5_UNAVAILABLE`（须给可操作提示）。
- 实际：无 `src/dsh_coderag/sqlite_caps.py`；`init_schema` 直接 `executescript`（indexer.py:126-128）；
  `server._dispatch` 只捕获 `ConfigError/FileNotFoundError/TaskNotFoundError`（server.py:179-194）。
- 风险：FTS5 缺失的发行版（2025-07 前的 uv CPython、某些 macOS 系统 python）上，
  `CREATE VIRTUAL TABLE ... USING fts5` 抛 `sqlite3.OperationalError` → 可能冒泡成 MCP
  `isError`，违反 RL-09；测试也无法 skip。
- 建议方案：(1) 新增 `sqlite_caps.fts5_available()`（TESTING §4.2 已给实现）；
  (2) `index_sync`/`search` 开库前探测，不可用则返回
  `status: error, code: FTS5_UNAVAILABLE` + 可操作 hint；(3) `server._dispatch` 加兜底
  `except Exception` → `SEARCH_FAILED`（RL-09 纵深防御）；(4) 可用时测试正常跑、
  不可用时 `pytest.skip`。估时 1.5–2h。
