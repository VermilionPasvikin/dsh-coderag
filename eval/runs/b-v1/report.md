# L2 run: eval-coderag

- profile: `headless` ｜ trials: 3
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.564 (22/39)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/3 | 0.000 | 6.0 | 153858.0 | completed |
| crossfile-skill-precedence | 2/3 | 0.667 | 9.7 | 422803.7 | completed |
| crossfile-subprocess-env-scrub | 1/3 | 0.333 | 5.0 | 113785.7 | completed |
| crossfile-todo-snapshot | 2/3 | 0.667 | 12.0 | 474061.3 | completed |
| crossfile-tool-cancel-code | 1/3 | 0.333 | 5.0 | 136737.3 | completed |
| locate-image-count-limit | 2/3 | 0.667 | 3.3 | 67416.0 | completed |
| locate-repeat-tool-reminder | 0/3 | 0.000 | 2.7 | 40665.3 | completed |
| locate-spill-notice | 0/3 | 0.000 | 6.0 | 146933.3 | completed |
| locate-tool-timeout-default | 2/3 | 0.667 | 3.3 | 50770.7 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 3.3 | 44444.0 | completed |
| negative-kafka | 3/3 | 1.000 | 4.3 | 62210.0 | completed |
| regression-context-window-code | 3/3 | 1.000 | 2.7 | 37473.0 | completed |
| regression-prune-marker | 3/3 | 1.000 | 2.0 | 26285.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'grep', 'grep'] 的保序子序列
- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'read', 'read', 'read', 'grep', 'grep', 'read', 'read', 'read', 'read'] 的保序子序列
- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'read', 'read', 'read', 'bash', 'read', 'read', 'read'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'read', 'bash', 'grep', 'read', 'read', 'grep', 'read', 'bash', 'read', 'bash', 'read', 'bash', 'glob'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'read', 'read', 'grep', 'grep', 'read', 'grep'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'grep', 'read', 'grep'] 的保序子序列
- **crossfile-todo-snapshot**: 有工具返回错误：['call_02_LY6LnY4fsQUhbEZfApeY7852']
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'grep', 'read', 'grep'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['grep', 'glob'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'bash', 'read', 'read', 'read', 'bash'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'read', 'bash', 'grep', 'bash'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read'] 的保序子序列
