# L2 run: arm-a-baseline

- profile: `eval-baseline` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.308 (4/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 10.0 | 263198.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 24.0 | 1115872.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 7.0 | 130802.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 29.0 | 1588381.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 9.0 | 277631.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 4.0 | 75506.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 4.0 | 78310.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 11.0 | 185639.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 4.0 | 56605.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 3.0 | 34317.0 | completed |
| negative-kafka | 1/1 | 1.000 | 5.0 | 70746.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 37031.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 2.0 | 22333.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'read', 'read', 'read', 'read', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'read'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'bash', 'read', 'read', 'read', 'bash', 'read', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 24 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'read', 'read', 'grep', 'bash', 'read'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'glob', 'bash', 'read', 'grep', 'read', 'read', 'bash', 'bash', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 29 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'grep', 'bash', 'read', 'read', 'read', 'grep', 'bash', 'read', 'bash', 'read', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'bash', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'glob', 'read', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'bash'] 的保序子序列; 步数 11 超过 max_steps=10
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep'] 的保序子序列
