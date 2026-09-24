# L2 run: clean-plugin-3

- profile: `headless` ｜ trials: 3
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.821 (32/39)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 2/3 | 0.667 | 6.7 | 194005.3 | completed |
| crossfile-skill-precedence | 2/3 | 0.667 | 12.3 | 513018.3 | completed |
| crossfile-subprocess-env-scrub | 3/3 | 1.000 | 5.3 | 132746.7 | completed |
| crossfile-todo-snapshot | 2/3 | 0.667 | 13.3 | 606630.3 | completed |
| crossfile-tool-cancel-code | 3/3 | 1.000 | 7.0 | 215106.0 | completed |
| locate-image-count-limit | 3/3 | 1.000 | 3.7 | 71254.7 | completed |
| locate-repeat-tool-reminder | 3/3 | 1.000 | 3.0 | 45086.0 | completed |
| locate-spill-notice | 1/3 | 0.333 | 7.7 | 210720.3 | completed |
| locate-tool-timeout-default | 2/3 | 0.667 | 3.3 | 51259.0 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 3.7 | 51205.0 | completed |
| negative-kafka | 2/3 | 0.667 | 4.0 | 63085.0 | completed |
| regression-context-window-code | 3/3 | 1.000 | 2.7 | 40906.0 | completed |
| regression-prune-marker | 3/3 | 1.000 | 2.7 | 37632.7 | completed |

## 失败明细

- **crossfile-goal-round-limit**: 有工具返回错误：['call_02_Y8HF8s79YOUrKvrOz5iV9325']
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'bash', 'read', 'read', 'bash', 'read', 'grep', 'grep', 'read', 'read', 'grep', 'read', 'read', 'read', 'bash', 'grep', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'read', 'read'] 的保序子序列; 步数 18 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 18 超过 max_steps=16
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'read', 'grep', 'grep', 'grep', 'bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'grep', 'grep', 'bash', 'read', 'grep', 'read', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read'] 的保序子序列
- **negative-kafka**: 有工具返回错误：['call_00_UKwM72M9JKiMhDgvEQkv4866']
