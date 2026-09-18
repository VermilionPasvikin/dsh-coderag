# M2 分块质量抽检：20 个 chunk 逐条结论

> 依据 PROJECT.md 的 T2-18。在 DSH 参考源码（commit `0d1f50007f`，3074 文件 /
> 51230 chunk）上对声明感知分块（§5.1）做**分层抽样**：4 个超大符号拆分块（`#part/N`）、
> 4 个 function、2 个 class、3 个 interface、3 个 module 头、4 个 gap 块，共 20 条。
>
> 判据：声明块应覆盖完整声明（不出现"半个函数"）；`#part/N` 块应落在语句边界；
> gap/module 块应是有意义的非声明内容。

## 抽检结果

| # | chunk（工作区相对路径:行） | 类型 | 行数 | 结论 |
|---|---|---|---|---|
| 01 | `packages/acp/acp/src/index.ts:97-174` `apply#part/1` | 超大拆分 | 68 | ⚠️ 语句边界正确、含函数签名；但花括号净 +1（未闭合），非自包含 |
| 02 | `packages/acp/acp/src/index.ts:175-373` `apply#part/2` | 超大拆分 | 190 | ⚠️ 从 `const implementation = {` 起，纯函数体中段；靠前缀 `#part/2` 才知归属 |
| 03 | `packages/acp/acp/src/index.ts:374-437` `apply#part/3` | 超大拆分 | 61 | ✅ 收尾闭合原函数（花括号净 -1） |
| 04 | `packages/acp/acp/src/model-control.ts:32-231` `AcpModelControl#part/1` | 超大拆分 | 190 | ⚠️ 含类声明头、花括号未闭合，非自包含 |
| 05 | `.../encode_gif.py:19-21` `fail` | function | 3 | ✅ 完整 Python 函数 |
| 06 | `.../encode_gif.py:24-32` `positive_float` | function | 9 | ✅ 完整 |
| 07 | `.../encode_gif.py:35-43` `positive_int` | function | 9 | ✅ 完整 |
| 08 | `.../encode_gif.py:46-54` `nonnegative_float` | function | 9 | ✅ 完整 |
| 09 | `.../test_encode_gif.py:13-99` `EncodeGifTest` | class | 80 | ✅ 完整类（含全部方法） |
| 10 | `packages/acp/acp/src/content.ts:25-39` `AcpContentError` | class | 14 | ✅ 完整类 |
| 11 | `packages/acp/acp/src/index.ts:75-84` `AcpConfig` | interface | 10 | ✅ 完整接口 |
| 12 | `packages/acp/acp/src/index.ts:458-461` `SessionListCursor` | interface | 4 | ✅ 完整接口 |
| 13 | `packages/acp/acp/src/model-control.ts:13-16` `ModelChoice` | interface | 4 | ✅ 完整接口 |
| 14 | `.../encode_gif.py:1-16` | module | 12 | ✅ 文件头（shebang + import + 常量） |
| 15 | `.../test_encode_gif.py:1-10` | module | 8 | ✅ 文件头（docstring + import + 常量） |
| 16 | `packages/acp/acp/src/codec.ts:1-13` | module | 11 | ✅ 文件头（模块级 doc 注释） |
| 17 | `.../encode_gif.py:336-337` | gap | 2 | ⚠️ `if __name__ == "__main__": main()` 完整但无符号 |
| 18 | `.../test_encode_gif.py:102-103` | gap | 2 | ⚠️ 同上，无符号 |
| 19 | `packages/acp/acp/src/content.ts:41` | gap | 1 | ❌ 仅一行块注释（`/** Narrow a wire MIME ... */`），噪声 |
| 20 | `packages/acp/acp/src/content.ts:46` | gap | 1 | ❌ 仅一行块注释，噪声 |

## 主要发现

### 1. 声明块无"半个函数"（核心判据通过）
- 全部 15592 个声明块中，**行数 > 200 的有 0 个**（49 个恰好 200，为上限）。
- 抽检的 function/class/interface 块均从声明头开始、到声明体结束，花括号净 0。
- 结论：tree-sitter 声明边界（§5.1 L1）把函数/类/接口切得完整；M2 出口"无半个函数"成立。

### 2. `#part/N` 拆分块落在语句边界，但不自包含
- 全库 465 个 `#part/N` 块，分布在 167 个文件。
- 抽检 01–04：拆分点确实在函数体直接语句边界（不是任意行），但：
  - 尾部块的起止花括号不平衡（01 净 +1、03 净 -1）；
  - part 2+ 不含函数签名，单看正文无法判断它属于哪个函数——**只能靠 `#part/N` 名称与上下文前缀**。
- 结论：这是 §5.1 L2 的既定取舍（超大符号必须二次切分）。上下文前缀（T2-05）
  `symbol: function apply#part/2` 是必要的补偿，不能在渲染时丢掉。

### 3. gap 块占比 69.6%，且大量是 1–5 行的碎片
- 51230 个 chunk 中 **gap（symbol_kind=None）35638 个（69.6%）**；其中单行 4980 个、
  ≤2 行 6977 个、≤5 行 14946 个。
- 很多是 import、块注释、模块级小语句。抽检 19、20 就是**只有一行块注释**的 chunk。
- 结论：碎片化 gap 块会稀释 FTS 文档并增加噪声；应给注释/小片段设置最小合并或最小长度。

### 4. gap 块没有行数上限——最大 chunk 达 3080 行（最严重）
- 声明块有 `MAX_CHUNK_LINES=200` 上限，但 **gap 块没有**（`_uncovered_regions` 不做窗口切分）。
- 最大的 5 个 chunk 全是 gap：
  - `packages/extensions/tool-cordis/src/api-catalog.ts:82-3161`（**3080 行**）
  - `.../api-catalog.ts:3719-6745`（3027 行）
  - `.../cordis-client-runner/src/client/slot-catalog.ts:77-2800`（2724 行）
- 根因：这些是生成的目录文件，顶层是巨大的 `export const X = { ... }`，既非 function/class
  也不是当前 `DECLARATION_KINDS["typescript"]` 里的类型，于是整段成为一个 gap 块。
- 后果：一次命中会返回数千行（即使 `max_tokens` 会保留首条并提示省略），严重挤占预算。
- 结论：**gap 块也必须受 `MAX_CHUNK_LINES` 约束**（按窗口切分），并考虑把 `lexical_declaration`
  / `type_alias_declaration` 纳入声明集合。

### 5. TypeScript 的 `type` 别名与 `const`/变量声明被当作 gap
- `DECLARATION_KINDS["typescript"]` 只含 function/class/interface/method，未含
  `type_alias_declaration` 与 `lexical_declaration`（含箭头函数）。
- 抽检 17/18 这类 `if __name__ == ...` 也是 gap。
- 结论：补这两类会同时降低 gap 占比与碎片化，是低风险改进（T3 归因前的实现修复）。

### 6. 语料中没有 `method` 类型的独立块
- DSH 是 TS 为主，类内方法由所属 class 块覆盖（T2-02 的 outermost 设计），故
  `symbol_kind=method` 计数为 0。这是设计的预期结果，不是缺陷。

## 结论

- **核心判据通过**：声明块覆盖完整声明，未发现"半个函数"。
- 需要跟进的三个分块问题：**gap 块无上限（最大 3080 行）**、gap 碎片化（单行/≤2 行近万）、
  TS `type`/`const` 未纳入声明。三者都属于"实现修复"（EVAL.md 的 A1/A3 类），不是架构问题。
- `#part/N` 拆分是既定取舍，前提是上下文前缀不被丢弃。
