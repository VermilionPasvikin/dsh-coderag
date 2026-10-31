# L2 run: arm20-c-t3

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.517 (31/60)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 2/3 | 0.667 | 9.0 | 255186.3 | completed |
| crossfile-mcp-instruction-path | 0/3 | 0.000 | 25.0 | 1203313.0 | completed |
| crossfile-session-log-format | 2/3 | 0.667 | 16.0 | 655548.7 | completed |
| crossfile-skill-precedence | 0/3 | 0.000 | 22.7 | 1249808.0 | completed |
| crossfile-subprocess-env-scrub | 2/3 | 0.667 | 6.7 | 165997.0 | completed |
| crossfile-todo-snapshot | 1/3 | 0.333 | 26.3 | 1233424.3 | completed |
| crossfile-tool-cancel-code | 2/3 | 0.667 | 8.7 | 242061.3 | completed |
| locate-image-count-limit | 2/3 | 0.667 | 6.7 | 135643.0 | completed |
| locate-parallel-tool-calls | 1/3 | 0.333 | 4.3 | 79312.3 | completed |
| locate-repeat-tool-reminder | 0/3 | 0.000 | 3.0 | 41609.7 | completed |
| locate-spill-notice | 1/3 | 0.333 | 7.3 | 161013.7 | completed |
| locate-tool-timeout-default | 3/3 | 1.000 | 4.7 | 77867.7 | completed |
| locate-web-fetch-cap | 0/3 | 0.000 | 10.0 | 258210.7 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 3.0 | 38342.0 | completed |
| negative-kafka | 3/3 | 1.000 | 4.3 | 60460.0 | completed |
| negative-vector-database | 2/3 | 0.667 | 7.3 | 134513.3 | completed |
| regression-context-window-code | 3/3 | 1.000 | 3.0 | 40235.3 | completed |
| regression-instruction-cap-rejects | 1/3 | 0.333 | 7.7 | 153713.0 | completed |
| regression-prune-marker | 3/3 | 1.000 | 3.3 | 44303.0 | completed |
| regression-repeat-thresholds | 0/3 | 0.000 | 5.0 | 80952.3 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read', 'read', 'grep', 'read', 'read', 'read', 'read', 'bash', 'read', 'read', 'read', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'read', 'read'] 的保序子序列
- **crossfile-mcp-instruction-path**: 步数 26 超过 max_steps=16
- **crossfile-mcp-instruction-path**: 步数 22 超过 max_steps=16
- **crossfile-mcp-instruction-path**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'bash', 'grep', 'bash', 'read', 'read', 'grep', 'bash', 'grep', 'read', 'read', 'grep', 'read', 'read', 'read', 'read', 'read', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'read', 'bash', 'read', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 27 超过 max_steps=16
- **crossfile-session-log-format**: 步数 23 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 23 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 19 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 26 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'bash', 'bash', 'read', 'bash'] 的保序子序列
- **crossfile-todo-snapshot**: 步数 26 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 38 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'read', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'bash', 'bash', 'read', 'bash', 'bash'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'read', 'read'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['grep', 'grep', 'grep', 'read', 'read', 'read', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash'] 的保序子序列
- **locate-web-fetch-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-web-fetch-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'bash', 'read', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-web-fetch-cap**: 步数 13 超过 max_steps=10
- **negative-vector-database**: 步数 10 超过 max_steps=8
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'grep', 'grep', 'read', 'read', 'read'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'read', 'grep', 'read', 'bash'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'bash'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash'] 的保序子序列
