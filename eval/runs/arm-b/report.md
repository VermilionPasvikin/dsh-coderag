# L2 run: arm-b-bm25

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.308 (4/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 10.0 | 313587.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 34.0 | 1859786.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 5.0 | 86032.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 35.0 | 1564692.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 10.0 | 274727.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 4.0 | 80947.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 41368.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 11.0 | 236513.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 6.0 | 95383.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 50224.0 | completed |
| negative-kafka | 1/1 | 1.000 | 4.0 | 50608.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 39842.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 38334.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 34 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash'] 的保序子序列; 步数 35 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 11 超过 max_steps=10
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'read', 'bash', 'read', 'bash'] 的保序子序列
