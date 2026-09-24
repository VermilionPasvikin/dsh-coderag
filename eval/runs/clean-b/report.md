# L2 run: clean-plugin

- profile: `headless` ｜ trials: 1
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.615 (8/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 9.0 | 264606.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 12.0 | 634182.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 6.0 | 177177.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 19.0 | 1007547.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 3.0 | 50879.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 4.0 | 73588.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 2.0 | 27291.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 5.0 | 148743.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 3.0 | 45316.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 3.0 | 39570.0 | completed |
| negative-kafka | 1/1 | 1.000 | 7.0 | 128001.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 43215.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 2.0 | 27526.0 | completed |

## 失败明细

- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'bash', 'read', 'read', 'grep', 'grep', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read'] 的保序子序列
- **crossfile-todo-snapshot**: 步数 19 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'grep', 'read', 'read', 'grep', 'read'] 的保序子序列
