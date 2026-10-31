# L2 run: arm-cloud-b

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.308 (4/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 8.0 | 243200.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 18.0 | 1059059.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 7.0 | 162815.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 38.0 | 2254704.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 16.0 | 519901.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 7.0 | 149166.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 3.0 | 42615.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 9.0 | 170039.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 6.0 | 98589.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 50116.0 | completed |
| negative-kafka | 1/1 | 1.000 | 6.0 | 89192.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 4.0 | 59575.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 38324.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'read', 'read', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 18 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['glob', 'grep', 'grep', 'grep', 'read', 'read', 'grep', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'read', 'read', 'grep', 'bash', 'read', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'read', 'read', 'read', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash'] 的保序子序列; 步数 38 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'grep', 'grep', 'bash', 'read', 'grep', 'grep', 'read', 'read', 'read', 'grep', 'bash', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read', 'grep', 'grep'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'grep', 'grep', 'grep', 'glob', 'bash', 'read', 'bash', 'grep', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'grep', 'read'] 的保序子序列
