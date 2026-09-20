# L2 run: eval-coderag

- profile: `headless` ｜ trials: 1
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.769 (10/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 6.0 | 189668.0 | completed |
| crossfile-skill-precedence | 1/1 | 1.000 | 15.0 | 751037.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 6.0 | 126955.0 | completed |
| crossfile-todo-snapshot | 1/1 | 1.000 | 7.0 | 213821.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 7.0 | 163729.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 3.0 | 58500.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 44423.0 | completed |
| locate-spill-notice | 1/1 | 1.000 | 4.0 | 105280.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 4.0 | 58657.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 3.0 | 40441.0 | completed |
| negative-kafka | 1/1 | 1.000 | 4.0 | 53029.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 2.0 | 26951.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 2.0 | 27463.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['grep', 'glob', 'read'] 的保序子序列
