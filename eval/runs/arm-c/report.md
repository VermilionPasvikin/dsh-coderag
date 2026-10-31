# L2 run: arm-c-vector

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.231 (3/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 11.0 | 308966.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 9.0 | 398811.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 7.0 | 122004.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 17.0 | 697239.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 8.0 | 217789.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 3.0 | 53503.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 2.0 | 24645.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 7.0 | 164981.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 7.0 | 120011.0 | completed |
| negative-elasticsearch | 0/1 | 0.000 | 2.0 | 24033.0 | completed |
| negative-kafka | 1/1 | 1.000 | 3.0 | 46622.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 42014.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 38356.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read', 'bash', 'bash', 'grep', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'grep', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'grep', 'bash', 'read', 'read', 'read'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'grep', 'bash', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'bash', 'read', 'read', 'bash', 'read', 'read'] 的保序子序列; 步数 17 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'grep', 'read', 'read', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'read', 'read', 'grep', 'bash', 'read'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read', 'grep', 'grep', 'read'] 的保序子序列
- **negative-elasticsearch**: 最终回答不匹配正则 '(?i)((没有|不存在|未找到|找不到|未包含)[^。\\n]{0,15}elasticsearch)|(elasticsearch[^。\\n]{0,60}(没有|不存在|未找到|找不到|未包含))|(no\\s+elasticsearch)|(not\\s+(found|present|used|exist))'
