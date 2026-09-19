# L2 用例审核表

> 共 **13** 条。本文件由 `python scripts/case-review.py` 从 `cases/*.json` 生成，
> **请勿手改**；改用例请改 JSON 后重新生成（有测试守着一致性）。

## 怎么审：5 个性质，其中 3 个已机械核查

| 性质 | 谁查 | 怎么查 |
|---|---|---|
| 答案文件在索引里（否则检索组永远赢不了） | 机械 ✅ | `CODERAG_L2_CORPUS=<副本> pytest tests/test_cases.py` |
| prompt 不泄漏答案路径 | 机械 ✅ | `leak_candidates` 扫描 + `tests/test_cases.py` |
| 断言不误杀正确答案 / 不放过错误答案 | 机械 ✅ | 每条下方的「应接受 / 应拒绝」样例，逐条真跑正则 |
| 问题真实、且只有一个合理答案 | **人** | 读每条「问」与「出处」：我会这么问吗？别人会不会答到别的文件？ |
| 配比与 `max_steps` 合理 | **人** | 看桶的分布；`max_steps` 是拍的（10/12/8），冒烟后可能要调 |

**桶的意图**：`locate`/`crossfile` 断言 `tools_called: [code_search]`（同时测检索质量与工具采纳）；
`regression` **不**断言工具被调用，用来验证「检索不该让简单题变差」；
`negative` 是反臆造控制组（`A`/`B` 都该过，测『没有就直说』而不是测区分度）。

---

### 1. `crossfile-goal-round-limit` — crossfile

- **问**：目标模式里轮次上限的默认值是多少？它存在哪、又在哪儿触发封锁？列文件。
- **答案文件**：`packages/goal/goal/src/index.ts`、`packages/goal/goal/src/fold.ts`、`packages/goal/goal-round-driver/src/index.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['256', 'goal']`；`max_steps=12`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：goal/goal/src/index.ts:244 `defaultMaxGoalRounds: z.number().default(256)` ＋ fold.ts:112（随状态持久化）＋ goal-round-driver/src/index.ts:166（触发封锁）。理由：默认值 → 持久化 → 封锁三处，且要求报出具体数字 256，答案可机械判定。
- **应接受**（2）
  - 默认 256 轮，配置在 packages/goal/goal/src/index.ts，随状态持久化在 fold.ts，封锁在 packages/goal/goal-round-driver/src/index.ts。
  - 默认值是 256；goal-round-driver 达到上限时把目标标记为 blocked。
- **应拒绝**（2）
  - 默认 100 轮，在 goal 里。
  - 没有轮次上限。

### 2. `crossfile-skill-precedence` — crossfile

- **问**：项目自带的技能是怎么被发现的？如果两个技能重名，谁生效？请把相关的文件都列出来。
- **答案文件**：`packages/skill/skill-filesystem/src/index.ts`、`packages/skill/skill/src/index.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['skill-filesystem', 'BUNDLED_SKILL_RANK|skill/skill/src/index']`；`max_steps=12`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：skill-filesystem/src/index.ts:723 `discoverRoot`（发现）＋ skill/src/index.ts:28 `BUNDLED_SKILL_RANK`、:78 `readonly rank`（同层同名按 rank 决胜）。理由：『发现』与『谁生效』分属两个包，单文件检索答不全；两个正则分别对应两处证据。
- **应接受**（2）
  - 发现逻辑在 packages/skill/skill-filesystem/src/index.ts 的 discoverRoot；同名覆盖由 packages/skill/skill/src/index.ts 的 BUNDLED_SKILL_RANK 决定。
  - skill-filesystem 负责发现；skill/skill/src/index.ts 里的 rank 决定谁生效。
- **应拒绝**（2）
  - 都在 packages/skill/skill/src/index.ts 一个文件里。
  - 技能是按文件名字母序加载的。

### 3. `crossfile-subprocess-env-scrub` — crossfile, semantic-gap

- **问**：启动子进程时，父进程的环境变量哪些会被过滤掉？这套规则写在哪个文件？
- **答案文件**：`packages/subprocess/subprocess/src/index.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['subprocess/subprocess/src/index|scrubbedParentEnv|SENSITIVE_ENV_PATTERN']`；`max_steps=12`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：packages/subprocess/subprocess/src/index.ts `scrubbedParentEnv` 与 `SENSITIVE_ENV_PATTERN`。理由：L1 的 L-008 已证明这是典型的『中文意图 vs 英文代码』零词法重叠案例（环境变量/过滤 ↔ env/scrub）。作为 L2 里的语义缺口探针：若 A/B 都失败，说明词法检索在这类问题上确实无能为力（对应 ADR-14 的 R2）。
- **应接受**（2）
  - 规则在 packages/subprocess/subprocess/src/index.ts 的 scrubbedParentEnv（SENSITIVE_ENV_PATTERN 加 DSH_ 前缀）。
  - subprocess/subprocess/src/index.ts；名字匹配敏感模式的变量不会传给子进程。
- **应拒绝**（2）
  - 在 packages/subprocess/subprocess-local/src/index.ts。
  - 所有环境变量都会被继承。

### 4. `crossfile-todo-snapshot` — crossfile

- **问**：整份待办清单是怎么被存进会话里的？以后检索会话时它又是怎么变成可搜索文本的？列文件。
- **答案文件**：`packages/todo/tool-todo/src/types.ts`、`packages/todo/tool-todo/src/index.ts`、`packages/session-query/session-query/src/extraction.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['tool-todo', 'session-query']`；`max_steps=12`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：tool-todo/src/types.ts:31 `'todo/write'`（事件载荷）＋ tool-todo/src/index.ts:210 `session.append('todo/write', ...)`（写入）＋ session-query/src/extraction.ts:29 `case 'todo/write':`（检索提取）。理由：跨『写会话』与『被检索』两侧，且两个包名都要说出来。
- **应接受**（2）
  - 写入在 packages/todo/tool-todo/src/index.ts（session.append('todo/write')），检索提取在 packages/session-query/session-query/src/extraction.ts。
  - tool-todo 负责写入会话，session-query 的 extraction 把它转成可搜索文本。
- **应拒绝**（2）
  - 只在 packages/todo/tool-todo/src/index.ts 里，就这一个文件。
  - 待办清单不落盘。

### 5. `crossfile-tool-cancel-code` — crossfile

- **问**：工具还没真正执行就被取消时用的那个错误码，在哪定义、在哪写进结果、又被哪个检查点策略复用？列文件。
- **答案文件**：`packages/core/tools/src/index.ts`、`packages/core/agent-loop/src/tool-calls.ts`、`packages/session/session-checkpoint-policy/src/index.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['core/tools', 'agent-loop']`；`max_steps=12`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：core/tools/src/index.ts:469 `TOOL_ABORTED_BEFORE_DISPATCH`（定义）＋ core/agent-loop/src/tool-calls.ts:257（写进结果）＋ session-checkpoint-policy/src/index.ts:47（复用）。理由：『定义处 + 使用处』三文件链，是跨文件理解的标准形态。
- **应接受**（2）
  - 错误码 TOOL_ABORTED_BEFORE_DISPATCH 定义在 packages/core/tools/src/index.ts，写进结果在 packages/core/agent-loop/src/tool-calls.ts，检查点策略复用见 session-checkpoint-policy。
  - core/tools 定义，agent-loop 写入结果。
- **应拒绝**（2）
  - 定义在 packages/session/session-checkpoint-policy/src/index.ts。
  - 没有这样的错误码。

### 6. `locate-image-count-limit` — locate

- **问**：一条消息里最多能附几张图片？这个上限定义在哪个文件？
- **答案文件**：`packages/attachment/attachment-local/src/index.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['DEFAULT_MAX_IMAGES_PER_MESSAGE|attachment-local/src/index']`；`max_steps=10`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：packages/attachment/attachment-local/src/index.ts:36 `export const DEFAULT_MAX_IMAGES_PER_MESSAGE = 20`。理由：先要找出常量名（中文问句里没有任何标识符），再定位文件；答案含具体数字，可机械断言。
- **应接受**（2）
  - 上限是 20 张，定义在 packages/attachment/attachment-local/src/index.ts。
  - 常量是 DEFAULT_MAX_IMAGES_PER_MESSAGE，见 attachment-local/src/index.ts。
- **应拒绝**（2）
  - 上限是 10，定义在 packages/attachment/attachment/src/index.ts。
  - 没有数量限制。

### 7. `locate-repeat-tool-reminder` — locate

- **问**：助手连续好几次用完全一样的参数调用同一个工具时，系统会怎么提醒它？给我实现这个提醒的文件路径就行。
- **答案文件**：`packages/guard/repeat-tool-reminder/src/index.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['repeat-tool-reminder']`；`max_steps=10`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：packages/guard/repeat-tool-reminder/src/index.ts:63 `GENTLE_REMINDER`、:199-202 阈值判定与 `detailedReminder`。理由：纯中文行为描述，代码里的词是 reminder/remind，中文『提醒』猜不到；配 tools_called 同时测检索质量与工具采纳意愿。
- **应接受**（2）
  - 实现在 `packages/guard/repeat-tool-reminder/src/index.ts`，达到阈值后会在工具结果后面追加提醒。
  - The reminder lives in packages/guard/repeat-tool-reminder/src/index.ts.
- **应拒绝**（2）
  - 在 packages/guard/timeout-policy/src/index.ts。
  - 不确定，仓库里似乎没有相关实现。

### 8. `locate-spill-notice` — locate

- **问**：工具输出太长被存到磁盘以后，模型看到的那段提示文本是谁生成的？给我文件路径。
- **答案文件**：`packages/spill/spill-policy/src/notice.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['spill-policy/src/notice|formatSpillNotice']`；`max_steps=10`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：packages/spill/spill-policy/src/notice.ts:20 `formatSpillNotice`。理由：中文问『提示文本』，代码里是 notice/format…，词形不重叠；答案是一个小而专一的文件，适合 locate。
- **应接受**（2）
  - 提示文本由 `formatSpillNotice` 生成，定义在 packages/spill/spill-policy/src/notice.ts。
  - 见 packages/spill/spill-policy/src/notice.ts:20 的 formatSpillNotice。
- **应拒绝**（2）
  - 在 packages/compaction/compaction-basic/src/index.ts。
  - 没有这样的提示文本，输出是被直接截断的。

### 9. `locate-tool-timeout-default` — locate

- **问**：工具调用默认多久算超时？这个默认值定义在哪个文件？
- **答案文件**：`packages/mcp/mcp-client/src/index.ts`
- **断言**：`tools_called=['code_search']`；`output_matches=['DEFAULT_TOOL_CALL_TIMEOUT_MS|mcp-client/src/index']`；`max_steps=10`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：packages/mcp/mcp-client/src/index.ts:37 `const DEFAULT_TOOL_CALL_TIMEOUT_MS = 60_000`。理由：刻意把 MCP 这个英文线索拿掉，只留中文『工具调用超时』，考验检索能否补上标识符缺口。
- **应接受**（2）
  - 默认 60 秒，定义在 packages/mcp/mcp-client/src/index.ts（DEFAULT_TOOL_CALL_TIMEOUT_MS）。
  - DEFAULT_TOOL_CALL_TIMEOUT_MS = 60_000，在 mcp-client/src/index.ts。
- **应拒绝**（2）
  - 默认 30 秒，在 packages/web/tool-web/src/index.ts。
  - 没有默认超时时间。

### 10. `negative-elasticsearch` — negative

- **问**：项目里用了 Elasticsearch 做检索吗？没有的话直接说没有。
- **答案文件**：（控制组：无答案文件）
- **断言**：`output_matches=['(?i)((没有|不存在|未找到|找不到|未包含)[^。\\n]{0,15}elasticsearch)|(no\\s+elasticsearch)|(not\\s+(found|present|used|exist))']`；`max_steps=8`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：全副本 grep `elasticsearch` **0 命中**。理由：同上的反臆造控制组，但这一条更贴近本项目的领域——被问『你们是不是也用 ES』时最容易顺着答。 断言要求「否定词 + 技术名」（或英文的 no X / not used），只写「我没有细看」不算——那种措辞没有陈述『不存在』。
- **应接受**（2）
  - 项目里没有使用 Elasticsearch。
  - There is no Elasticsearch here; retrieval is SQLite FTS5.
- **应拒绝**（3）
  - 有的，Elasticsearch 集成在 packages/messaging/elasticsearch/src/index.ts。
  - 可能在 packages/queue 下面，我没有细看。
  - 我没有细看相关代码，说不定有。

### 11. `negative-kafka` — negative

- **问**：这个仓库里有 Kafka 相关的集成代码吗？如果没有就直说没有，不要臆造。
- **答案文件**：（控制组：无答案文件）
- **断言**：`output_matches=['(?i)((没有|不存在|未找到|找不到|未包含)[^。\\n]{0,15}kafka)|(no\\s+kafka)|(not\\s+(found|present|used|exist))']`；`max_steps=8`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：全副本 grep（排除 .git/node_modules/.coderag）`kafka` **0 命中**。理由：反臆造控制组（EVAL §2.9 与 RL-06 的同一个根因：空结果会被读成『不存在』，也可能被读成『我再编一个』）。断言只要求出现『没有/not found』一类措辞。 断言要求「否定词 + 技术名」（或英文的 no X / not used），只写「我没有细看」不算——那种措辞没有陈述『不存在』。
- **应接受**（2）
  - 这个仓库里没有 Kafka 相关的集成代码。
  - There is no Kafka integration in this repository.
- **应拒绝**（3）
  - 有的，Kafka 集成在 packages/messaging/kafka/src/index.ts。
  - 可能在 packages/queue 下面，我没有细看。
  - 我没有细看相关代码，说不定有。

### 12. `regression-context-window-code` — regression, identifier

- **问**：`CONTEXT_WINDOW_EXCEEDED_CODE` 定义在哪个文件？
- **答案文件**：`packages/llm/llm/src/error.ts`
- **断言**：`output_matches=['llm/llm/src/error']`；`max_steps=8`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：packages/llm/llm/src/error.ts:25。理由：同上的回归题；这条同时是 L1 里 T3-13 修过的『标识符 + 中文』形态，用来确认端到端层面也不回退。
- **应接受**（2）
  - 定义在 packages/llm/llm/src/error.ts:25。
  - llm/llm/src/error.ts（CONTEXT_WINDOW_EXCEEDED_CODE）。
- **应拒绝**（2）
  - 在 packages/llm/llm/src/retry-policy.ts。
  - 没有这个常量。

### 13. `regression-prune-marker` — regression, identifier

- **问**：`PRUNE_MARKER` 这个常量定义在哪个文件？
- **答案文件**：`packages/compaction/compaction-tool-result-pruner/src/config.ts`
- **断言**：`output_matches=['compaction-tool-result-pruner|config\\.ts']`；`max_steps=8`；`no_tool_errors`；`turn_end=completed`
- **出处 / 理由**：出处：packages/compaction/compaction-tool-result-pruner/src/config.ts:7。理由：**不给 tools_called 断言**——这是一条『检索不该让简单题变差』的回归题。标识符可直接 grep，预期 A 组也能过；若 B 组反而失败，说明检索干扰了基线。
- **应接受**（2）
  - `PRUNE_MARKER` 定义在 packages/compaction/compaction-tool-result-pruner/src/config.ts。
  - compaction-tool-result-pruner/src/config.ts:7
- **应拒绝**（2）
  - 在 packages/compaction/compaction-basic/src/index.ts。
  - 不存在这个常量。
