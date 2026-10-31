# L2 run: arm-cloud-c

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.308 (4/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 8.0 | 276068.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 15.0 | 751241.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 6.0 | 133495.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 21.0 | 728720.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 9.0 | 241994.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 4.0 | 75212.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 4.0 | 59024.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 5.0 | 106498.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 5.0 | 72686.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 3.0 | 39496.0 | completed |
| negative-kafka | 1/1 | 1.000 | 4.0 | 50406.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 4.0 | 59595.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 38355.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'grep', 'grep', 'read', 'grep', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'bash', 'grep', 'read', 'read'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'read', 'read', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 21 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'grep', 'read', 'grep', 'grep', 'read', 'read', 'read', 'grep', 'grep', 'bash', 'read', 'read', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'bash'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash'] 的保序子序列
