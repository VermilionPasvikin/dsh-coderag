# L2 run: arm20-c-t3-steps

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.683 (41/60)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/3 | 0.333 | 9.7 | 309326.3 | completed |
| crossfile-mcp-instruction-path | 2/3 | 0.667 | 25.3 | 1143010.3 | completed |
| crossfile-session-log-format | 2/3 | 0.667 | 21.7 | 1018245.3 | completed |
| crossfile-skill-precedence | 3/3 | 1.000 | 20.0 | 1120900.0 | completed |
| crossfile-subprocess-env-scrub | 0/3 | 0.000 | 6.7 | 151210.7 | completed |
| crossfile-todo-snapshot | 3/3 | 1.000 | 23.7 | 1021075.3 | completed |
| crossfile-tool-cancel-code | 3/3 | 1.000 | 7.3 | 193605.0 | completed |
| locate-image-count-limit | 3/3 | 1.000 | 6.0 | 124016.0 | completed |
| locate-parallel-tool-calls | 0/3 | 0.000 | 4.3 | 75549.7 | completed |
| locate-repeat-tool-reminder | 1/3 | 0.333 | 3.3 | 51793.0 | completed |
| locate-spill-notice | 3/3 | 1.000 | 6.3 | 137777.0 | completed |
| locate-tool-timeout-default | 2/3 | 0.667 | 4.3 | 67498.0 | completed |
| locate-web-fetch-cap | 3/3 | 1.000 | 8.3 | 209244.3 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 4.0 | 63830.0 | completed |
| negative-kafka | 3/3 | 1.000 | 3.7 | 46731.3 | completed |
| negative-vector-database | 3/3 | 1.000 | 6.7 | 114457.0 | completed |
| regression-context-window-code | 3/3 | 1.000 | 3.3 | 45543.3 | completed |
| regression-instruction-cap-rejects | 0/3 | 0.000 | 5.7 | 107721.7 | completed |
| regression-prune-marker | 3/3 | 1.000 | 3.0 | 39132.3 | completed |
| regression-repeat-thresholds | 0/3 | 0.000 | 5.3 | 88998.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-mcp-instruction-path**: 步数 31 超过 max_steps=28
- **crossfile-session-log-format**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'bash', 'read', 'read', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'read', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'grep', 'bash'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read', 'grep', 'read', 'grep', 'read', 'read', 'grep', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read', 'grep', 'grep', 'grep', 'read'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['grep', 'grep', 'grep', 'read', 'read', 'read', 'read', 'grep'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'bash'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['bash', 'bash', 'read', 'bash', 'read', 'bash'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'grep', 'bash'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'grep', 'read', 'read', 'read', 'grep'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'read', 'read', 'bash', 'read', 'bash'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'read'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'read'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'read', 'grep', 'read'] 的保序子序列
