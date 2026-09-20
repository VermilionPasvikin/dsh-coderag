# L2 run: eval-baseline

- profile: `headless` ｜ trials: 3
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.308 (12/39)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/3 | 0.000 | 7.0 | 207734.3 | completed |
| crossfile-skill-precedence | 0/3 | 0.000 | 10.3 | 507086.0 | completed |
| crossfile-subprocess-env-scrub | 0/3 | 0.000 | 4.3 | 88582.3 | completed |
| crossfile-todo-snapshot | 0/3 | 0.000 | 11.7 | 401063.0 | completed |
| crossfile-tool-cancel-code | 0/3 | 0.000 | 5.7 | 134974.7 | completed |
| locate-image-count-limit | 0/3 | 0.000 | 3.0 | 65391.7 | completed |
| locate-repeat-tool-reminder | 0/3 | 0.000 | 2.0 | 27856.7 | completed |
| locate-spill-notice | 0/3 | 0.000 | 6.3 | 159074.3 | completed |
| locate-tool-timeout-default | 0/3 | 0.000 | 4.0 | 60017.3 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 3.0 | 52646.3 | completed |
| negative-kafka | 3/3 | 1.000 | 3.7 | 49387.7 | completed |
| regression-context-window-code | 3/3 | 1.000 | 2.3 | 30946.7 | completed |
| regression-prune-marker | 3/3 | 1.000 | 2.3 | 30083.7 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['grep', 'glob', 'read', 'read', 'read', 'read', 'read', 'grep', 'grep', 'read', 'read', 'read'] 的保序子序列
- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'bash'] 的保序子序列
- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'grep', 'grep', 'read', 'read', 'grep', 'read', 'read', 'grep', 'read', 'grep', 'grep', 'read', 'read', 'read'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'read', 'grep', 'grep', 'read', 'bash', 'grep', 'grep', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'glob'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'bash', 'read', 'read', 'grep', 'grep', 'read', 'bash', 'read', 'bash', 'read', 'read', 'read', 'read', 'bash'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'grep', 'read'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'glob', 'glob', 'read', 'read', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'read', 'grep', 'read', 'bash', 'grep', 'grep', 'glob', 'grep', 'read', 'bash', 'grep'] 的保序子序列; 有工具返回错误：['call_00_QjYM8wNLYvXVbhNemGLn8678']
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'glob', 'glob', 'read', 'read', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'read', 'grep', 'read'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'glob', 'glob', 'read', 'read', 'read', 'read', 'read', 'read', 'glob', 'read', 'read', 'grep', 'read', 'read', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'read', 'read'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read', 'read', 'grep', 'grep', 'read'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'bash', 'read'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'grep', 'read', 'read', 'grep', 'read', 'read', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'glob', 'read', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['grep', 'glob'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['grep', 'glob'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['grep', 'glob'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'read', 'grep', 'grep'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'bash', 'bash'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'grep', 'grep', 'grep', 'bash', 'grep', 'read', 'read'] 的保序子序列; 有工具返回错误：['call_01_4azhnIA9OeZ1XY1gErjs9028']
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['grep', 'glob', 'read', 'grep'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'grep', 'grep'] 的保序子序列
