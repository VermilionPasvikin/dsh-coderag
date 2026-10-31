# L2 run: arm20-b-t3

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.600 (36/60)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 2/3 | 0.667 | 8.7 | 214755.0 | completed |
| crossfile-mcp-instruction-path | 0/3 | 0.000 | 25.3 | 1268523.3 | completed |
| crossfile-session-log-format | 0/3 | 0.000 | 20.3 | 863054.7 | completed |
| crossfile-skill-precedence | 1/3 | 0.333 | 23.7 | 1206371.0 | completed |
| crossfile-subprocess-env-scrub | 2/3 | 0.667 | 8.7 | 222212.7 | completed |
| crossfile-todo-snapshot | 0/3 | 0.000 | 21.0 | 764820.0 | completed |
| crossfile-tool-cancel-code | 3/3 | 1.000 | 7.3 | 170368.3 | completed |
| locate-image-count-limit | 3/3 | 1.000 | 5.7 | 124979.3 | completed |
| locate-parallel-tool-calls | 2/3 | 0.667 | 5.3 | 95122.7 | completed |
| locate-repeat-tool-reminder | 0/3 | 0.000 | 3.3 | 48271.7 | completed |
| locate-spill-notice | 3/3 | 1.000 | 6.3 | 139667.0 | completed |
| locate-tool-timeout-default | 2/3 | 0.667 | 4.7 | 77460.3 | completed |
| locate-web-fetch-cap | 2/3 | 0.667 | 9.7 | 251572.0 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 3.0 | 38794.3 | completed |
| negative-kafka | 3/3 | 1.000 | 4.0 | 63572.3 | completed |
| negative-vector-database | 2/3 | 0.667 | 8.0 | 143226.3 | completed |
| regression-context-window-code | 3/3 | 1.000 | 3.3 | 47262.7 | completed |
| regression-instruction-cap-rejects | 1/3 | 0.333 | 6.3 | 113879.0 | completed |
| regression-prune-marker | 3/3 | 1.000 | 3.3 | 44092.3 | completed |
| regression-repeat-thresholds | 1/3 | 0.333 | 4.3 | 71627.7 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-mcp-instruction-path**: 步数 24 超过 max_steps=16
- **crossfile-mcp-instruction-path**: 步数 23 超过 max_steps=16
- **crossfile-mcp-instruction-path**: 步数 29 超过 max_steps=16
- **crossfile-session-log-format**: 步数 20 超过 max_steps=16
- **crossfile-session-log-format**: 步数 22 超过 max_steps=16
- **crossfile-session-log-format**: 步数 19 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 32 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 23 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'grep', 'read', 'read'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'read', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 25 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 18 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 20 超过 max_steps=16
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'grep', 'bash', 'bash'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'bash'] 的保序子序列
- **locate-web-fetch-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'read', 'bash'] 的保序子序列; 步数 14 超过 max_steps=10
- **negative-vector-database**: 步数 10 超过 max_steps=8
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'bash', 'bash'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'read'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'read'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash'] 的保序子序列
