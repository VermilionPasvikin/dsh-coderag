# L2 run: eval-baseline

- profile: `headless` ｜ trials: 1
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.308 (4/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 6.0 | 140621.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 10.0 | 401802.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 4.0 | 77873.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 17.0 | 797589.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 5.0 | 134399.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 4.0 | 95470.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 44204.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 5.0 | 169598.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 4.0 | 61198.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 50944.0 | completed |
| negative-kafka | 1/1 | 1.000 | 4.0 | 51798.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 2.0 | 25832.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 2.0 | 25292.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'glob', 'grep', 'grep', 'read', 'read', 'read', 'grep', 'grep', 'read', 'read'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'bash', 'read', 'read', 'bash', 'grep', 'bash', 'read', 'bash', 'bash', 'read', 'read', 'bash', 'read', 'bash'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'bash'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'bash'] 的保序子序列; 步数 17 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'read', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'grep', 'grep'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['grep', 'grep', 'grep', 'grep', 'read', 'bash', 'grep', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read'] 的保序子序列
