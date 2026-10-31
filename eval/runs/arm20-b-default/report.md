# L2 run: arm20-b-default

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.600 (12/20)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 8.0 | 223138.0 | completed |
| crossfile-mcp-instruction-path | 0/1 | 0.000 | 20.0 | 927918.0 | completed |
| crossfile-session-log-format | 0/1 | 0.000 | 28.0 | 1660290.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 26.0 | 1713984.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 9.0 | 231383.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 23.0 | 808044.0 | completed |
| crossfile-tool-cancel-code | 1/1 | 1.000 | 8.0 | 282868.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 4.0 | 78806.0 | completed |
| locate-parallel-tool-calls | 1/1 | 1.000 | 5.0 | 91237.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 41258.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 17.0 | 518523.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 4.0 | 61309.0 | completed |
| locate-web-fetch-cap | 1/1 | 1.000 | 7.0 | 106673.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 3.0 | 37020.0 | completed |
| negative-kafka | 1/1 | 1.000 | 4.0 | 51336.0 | completed |
| negative-vector-database | 1/1 | 1.000 | 5.0 | 83352.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 40238.0 | completed |
| regression-instruction-cap-rejects | 0/1 | 0.000 | 7.0 | 120486.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 38616.0 | completed |
| regression-repeat-thresholds | 1/1 | 1.000 | 6.0 | 109251.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'grep', 'read', 'read', 'read', 'read', 'grep', 'bash', 'read', 'read', 'read'] 的保序子序列
- **crossfile-mcp-instruction-path**: 步数 20 超过 max_steps=16
- **crossfile-session-log-format**: 步数 28 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 26 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 23 超过 max_steps=16
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'grep', 'grep', 'read', 'grep', 'bash', 'grep', 'read', 'read', 'grep', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 17 超过 max_steps=10
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'grep', 'read', 'read', 'grep', 'bash'] 的保序子序列
