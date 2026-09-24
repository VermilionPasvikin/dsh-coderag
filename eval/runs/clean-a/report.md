# L2 run: clean-baseline

- profile: `headless` ｜ trials: 1
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.308 (4/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 6.0 | 180611.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 12.0 | 694500.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 4.0 | 65525.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 16.0 | 507994.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 5.0 | 121164.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 3.0 | 53301.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 42521.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 5.0 | 131565.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 4.0 | 60122.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 58107.0 | completed |
| negative-kafka | 1/1 | 1.000 | 3.0 | 39065.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 2.0 | 25874.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 2.0 | 25227.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'grep', 'grep', 'grep', 'read'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'read', 'read', 'read', 'read', 'read', 'grep', 'grep', 'read', 'read', 'bash', 'bash', 'grep', 'grep', 'grep', 'read', 'read', 'read', 'bash', 'grep', 'grep', 'read', 'bash', 'bash', 'bash', 'grep'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'grep', 'grep'] 的保序子序列; 有工具返回错误：['call_01_Tw1UX8CGHQ6nMrzpXkdl6154']
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'glob', 'glob', 'bash', 'read', 'bash', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['grep', 'grep', 'grep', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['glob', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['glob', 'grep', 'read', 'read', 'grep', 'read', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'grep', 'read'] 的保序子序列
