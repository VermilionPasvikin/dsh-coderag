# L2 run: arm-cloud-a

- profile: `eval-baseline` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.308 (4/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 9.0 | 211103.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 22.0 | 1096853.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 9.0 | 209805.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 22.0 | 899432.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 5.0 | 97706.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 6.0 | 113625.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 38491.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 6.0 | 122844.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 4.0 | 57735.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 3.0 | 53464.0 | completed |
| negative-kafka | 1/1 | 1.000 | 6.0 | 73732.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 37005.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 2.0 | 22308.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 22 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'read', 'grep', 'grep', 'bash', 'read', 'read', 'grep', 'read', 'grep'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'read', 'read', 'read', 'grep', 'bash', 'grep', 'bash', 'read', 'read', 'read', 'read', 'read', 'bash', 'read', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 22 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'bash', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'read', 'read', 'read', 'bash', 'bash'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash'] 的保序子序列
