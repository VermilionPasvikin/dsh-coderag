# L2 run: cloud-c-instructions

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.769 (10/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 8.0 | 260332.0 | completed |
| crossfile-skill-precedence | 1/1 | 1.000 | 12.0 | 560106.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 7.0 | 159029.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 43.0 | 2340637.0 | completed |
| crossfile-tool-cancel-code | 1/1 | 1.000 | 8.0 | 234366.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 5.0 | 110413.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 41715.0 | completed |
| locate-spill-notice | 1/1 | 1.000 | 10.0 | 276559.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 5.0 | 79851.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 3.0 | 37892.0 | completed |
| negative-kafka | 1/1 | 1.000 | 3.0 | 39439.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 41531.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 39728.0 | completed |

## 失败明细

- **crossfile-todo-snapshot**: 步数 43 超过 max_steps=16
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'grep', 'grep', 'grep'] 的保序子序列
