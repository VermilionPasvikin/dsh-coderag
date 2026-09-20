# L2 run: eval-coderag

- profile: `headless` ｜ trials: 3
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.897 (35/39)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 2/3 | 0.667 | 5.7 | 175436.0 | completed |
| crossfile-skill-precedence | 3/3 | 1.000 | 13.7 | 684373.0 | completed |
| crossfile-subprocess-env-scrub | 3/3 | 1.000 | 4.0 | 78055.3 | completed |
| crossfile-todo-snapshot | 2/3 | 0.667 | 15.3 | 639011.0 | completed |
| crossfile-tool-cancel-code | 3/3 | 1.000 | 6.0 | 173852.0 | completed |
| locate-image-count-limit | 3/3 | 1.000 | 3.3 | 64286.7 | completed |
| locate-repeat-tool-reminder | 2/3 | 0.667 | 3.0 | 47332.3 | completed |
| locate-spill-notice | 2/3 | 0.667 | 6.0 | 178680.3 | completed |
| locate-tool-timeout-default | 3/3 | 1.000 | 3.3 | 57510.3 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 2.7 | 44954.0 | completed |
| negative-kafka | 3/3 | 1.000 | 3.3 | 50723.0 | completed |
| regression-context-window-code | 3/3 | 1.000 | 2.7 | 38779.3 | completed |
| regression-prune-marker | 3/3 | 1.000 | 2.3 | 32511.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'read', 'read', 'grep', 'read'] 的保序子序列
- **crossfile-todo-snapshot**: 步数 20 超过 max_steps=16; 有工具返回错误：['call_01_QldkKY4Ti8vmbVgE3pO27411']
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'grep', 'grep', 'read', 'grep', 'read'] 的保序子序列
