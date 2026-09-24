# L1 逐 query diff

- 对比条数：30（k=5）
- golden_version：m3-b1 → m3-b1
- 命中率：0.433 → 0.567（+13.3pp）
- 回归：1 ｜ 改善：5 ｜ 名次变好：2 ｜ 名次变差：6
- 门禁：FAIL（未豁免回归 1 条，容忍 0）
  - 未豁免回归 1 条 > 容忍 0

## 回归（命中 → 未命中）

- **L-015**（exact）：hit #3 (packages/ssh/ssh/src/protocol.ts) → miss ｜ SSH_MAX_PROCESS_HANDLES

## 改善（未命中 → 命中）

- **L-007**（crossfile）：miss → hit #5 (packages/subagent/subagent/src/child-agent.ts) ｜ 子代理的递归深度限制如何跨重启保留下来
- **L-019**（crossfile）：miss → hit #4 (packages/skill/skill/src/index.ts) ｜ 技能是怎么被发现的，同名冲突时又按什么规则决定谁生效？
- **L-021**（crossfile）：miss → hit #4 (packages/goal/goal/src/index.ts) ｜ 目标创建时没指定轮次上限的话默认是多少，这个上限存在哪里，又在哪触发封锁？
- **L-025**（crossfile）：miss → hit #5 (packages/fs/fs-local/src/fsio.ts) ｜ 读取文件超过大小上限时用的错误码在哪定义、又在哪里被抛出？
- **L-026**（natural）：miss → hit #5 (packages/guard/repeat-tool-reminder/src/index.ts) ｜ 助手连续好几次用完全一样的参数调用同一个工具时，系统会怎么处理

## 逐条对比

| query | 类 | baseline | current | 变化 |
|---|---|---|---|---|
| L-001 | exact | hit #1 (packages/mcp/mcp-client/src/index.ts) | hit #4 (packages/mcp/mcp-client/src/index.ts) | rank_regressed |
| L-002 | exact | hit #5 (packages/llm/llm/src/error.ts) | hit #4 (packages/llm/llm/src/error.ts) | rank_improved |
| L-003 | exact | hit #3 (packages/subagent/subagent/src/depth.ts) | hit #3 (packages/subagent/subagent/src/depth.ts) | unchanged |
| L-004 | exact | hit #5 (packages/sandbox/sandbox-policy/src/session-mode.ts) | hit #4 (packages/sandbox/sandbox-policy/src/session-mode.ts) | rank_improved |
| L-005 | crossfile | hit #1 (packages/mcp/mcp-client/src/index.ts) | hit #3 (packages/mcp/mcp-client/src/index.ts) | rank_regressed |
| L-006 | crossfile | miss | miss | unchanged |
| L-007 | crossfile | miss | hit #5 (packages/subagent/subagent/src/child-agent.ts) | improvement |
| L-008 | crossfile | miss | miss | unchanged |
| L-009 | natural | miss | miss | unchanged |
| L-010 | natural | miss | miss | unchanged |
| L-011 | exact | hit #1 (packages/session-query/session-query-sqlite/src/query.ts) | hit #2 (packages/session-query/session-query-sqlite/src/query.ts) | rank_regressed |
| L-012 | exact | hit #1 (packages/core/session/src/known-event-types.ts) | hit #2 (packages/core/session/src/known-event-types.ts) | rank_regressed |
| L-013 | exact | hit #1 (packages/identity/anonymous-user-id/src/index.ts) | hit #1 (packages/identity/anonymous-user-id/src/index.ts) | unchanged |
| L-014 | exact | hit #1 (packages/attachment/attachment-local/src/request-image.ts) | hit #1 (packages/attachment/attachment-local/src/request-image.ts) | unchanged |
| L-015 | exact | hit #3 (packages/ssh/ssh/src/protocol.ts) | miss | regression |
| L-016 | exact | hit #1 (packages/compaction/compaction-tool-result-pruner/src/config.ts) | hit #2 (packages/compaction/compaction-tool-result-pruner/src/config.ts) | rank_regressed |
| L-017 | exact | hit #1 (packages/hooks/hook-protocol/src/events.ts) | hit #2 (packages/hooks/hook-protocol/src/events.ts) | rank_regressed |
| L-018 | exact | hit #3 (packages/context/file-reference-local/src/search.ts) | hit #3 (packages/context/file-reference-local/src/search.ts) | unchanged |
| L-019 | crossfile | miss | hit #4 (packages/skill/skill/src/index.ts) | improvement |
| L-020 | crossfile | miss | miss | unchanged |
| L-021 | crossfile | miss | hit #4 (packages/goal/goal/src/index.ts) | improvement |
| L-022 | crossfile | miss | miss | unchanged |
| L-023 | crossfile | miss | miss | unchanged |
| L-024 | crossfile | miss | miss | unchanged |
| L-025 | crossfile | miss | hit #5 (packages/fs/fs-local/src/fsio.ts) | improvement |
| L-026 | natural | miss | hit #5 (packages/guard/repeat-tool-reminder/src/index.ts) | improvement |
| L-027 | natural | miss | miss | unchanged |
| L-028 | natural | miss | miss | unchanged |
| L-029 | natural | miss | miss | unchanged |
| L-030 | natural | miss | miss | unchanged |
