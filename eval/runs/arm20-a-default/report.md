# L2 run: arm20-a-default

- profile: `eval-baseline` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.250 (5/20)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 9.0 | 221404.0 | completed |
| crossfile-mcp-instruction-path | 0/1 | 0.000 | 38.0 | 1691429.0 | completed |
| crossfile-session-log-format | 0/1 | 0.000 | 22.0 | 945018.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 21.0 | 1225043.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 4.0 | 72021.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 30.0 | 1195401.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 10.0 | 169160.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 5.0 | 104543.0 | completed |
| locate-parallel-tool-calls | 0/1 | 0.000 | 7.0 | 136707.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 39407.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 9.0 | 238679.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 5.0 | 73060.0 | completed |
| locate-web-fetch-cap | 0/1 | 0.000 | 8.0 | 169989.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 47329.0 | completed |
| negative-kafka | 1/1 | 1.000 | 4.0 | 46193.0 | completed |
| negative-vector-database | 1/1 | 1.000 | 8.0 | 121192.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 38151.0 | completed |
| regression-instruction-cap-rejects | 0/1 | 0.000 | 6.0 | 95864.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 35467.0 | completed |
| regression-repeat-thresholds | 0/1 | 0.000 | 7.0 | 129194.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-mcp-instruction-path**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'grep', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 38 超过 max_steps=16
- **crossfile-session-log-format**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'grep', 'bash', 'bash', 'grep', 'bash', 'bash', 'bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 22 超过 max_steps=16
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'bash', 'read', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 21 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'read', 'read', 'read', 'grep', 'bash', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read'] 的保序子序列; 步数 30 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'bash'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'read', 'read', 'read', 'read', 'grep', 'grep', 'read', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-web-fetch-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'read', 'read', 'grep', 'grep'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
