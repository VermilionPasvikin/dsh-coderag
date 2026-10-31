# L2 run: cloud-c-after-t810

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.385 (5/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 10.0 | 277991.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 15.0 | 881364.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 9.0 | 219443.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 25.0 | 1050330.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 7.0 | 191386.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 4.0 | 84565.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 5.0 | 78601.0 | completed |
| locate-spill-notice | 1/1 | 1.000 | 10.0 | 202721.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 6.0 | 96968.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 51035.0 | completed |
| negative-kafka | 1/1 | 1.000 | 4.0 | 50695.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 39898.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 2.0 | 23721.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'read', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'bash', 'bash', 'bash', 'read'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'read', 'grep', 'grep', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash'] 的保序子序列; 步数 25 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'read', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'grep', 'bash', 'grep', 'read'] 的保序子序列
