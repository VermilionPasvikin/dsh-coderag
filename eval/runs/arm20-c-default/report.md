# L2 run: arm20-c-default

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.650 (13/20)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 8.0 | 204427.0 | completed |
| crossfile-mcp-instruction-path | 0/1 | 0.000 | 22.0 | 1187781.0 | completed |
| crossfile-session-log-format | 1/1 | 1.000 | 14.0 | 456662.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 21.0 | 1037112.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 9.0 | 214934.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 21.0 | 893154.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 7.0 | 212867.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 8.0 | 159220.0 | completed |
| locate-parallel-tool-calls | 1/1 | 1.000 | 6.0 | 107872.0 | completed |
| locate-repeat-tool-reminder | 1/1 | 1.000 | 5.0 | 100042.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 9.0 | 248216.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 5.0 | 80057.0 | completed |
| locate-web-fetch-cap | 1/1 | 1.000 | 8.0 | 210061.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 50131.0 | completed |
| negative-kafka | 1/1 | 1.000 | 8.0 | 120940.0 | completed |
| negative-vector-database | 1/1 | 1.000 | 7.0 | 125636.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 40111.0 | completed |
| regression-instruction-cap-rejects | 0/1 | 0.000 | 7.0 | 132105.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 38643.0 | completed |
| regression-repeat-thresholds | 0/1 | 0.000 | 4.0 | 60749.0 | completed |

## 失败明细

- **crossfile-mcp-instruction-path**: 步数 22 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 21 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 21 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'read', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'grep', 'read', 'read', 'grep', 'grep', 'bash', 'bash', 'read', 'read', 'bash'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'read', 'read', 'bash', 'read'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read'] 的保序子序列
