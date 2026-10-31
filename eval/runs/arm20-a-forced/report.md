# L2 run: arm20-a-forced

- profile: `eval-baseline` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.200 (4/20)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/1 | 0.000 | 10.0 | 290504.0 | completed |
| crossfile-mcp-instruction-path | 0/1 | 0.000 | 30.0 | 1404623.0 | completed |
| crossfile-session-log-format | 0/1 | 0.000 | 19.0 | 774449.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 22.0 | 678789.0 | completed |
| crossfile-subprocess-env-scrub | 0/1 | 0.000 | 20.0 | 781897.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 22.0 | 752524.0 | completed |
| crossfile-tool-cancel-code | 0/1 | 0.000 | 13.0 | 350537.0 | completed |
| locate-image-count-limit | 0/1 | 0.000 | 10.0 | 215745.0 | completed |
| locate-parallel-tool-calls | 0/1 | 0.000 | 4.0 | 65902.0 | completed |
| locate-repeat-tool-reminder | 0/1 | 0.000 | 4.0 | 57402.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 8.0 | 215859.0 | completed |
| locate-tool-timeout-default | 0/1 | 0.000 | 3.0 | 41317.0 | completed |
| locate-web-fetch-cap | 0/1 | 0.000 | 9.0 | 191832.0 | completed |
| negative-elasticsearch | 0/1 | 0.000 | 6.0 | 83815.0 | completed |
| negative-kafka | 1/1 | 1.000 | 7.0 | 99443.0 | completed |
| negative-vector-database | 1/1 | 1.000 | 8.0 | 313315.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 3.0 | 40835.0 | completed |
| regression-instruction-cap-rejects | 0/1 | 0.000 | 7.0 | 130137.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 37007.0 | completed |
| regression-repeat-thresholds | 0/1 | 0.000 | 6.0 | 79845.0 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'read', 'read', 'read'] 的保序子序列
- **crossfile-mcp-instruction-path**: tools_called ['code_search'] 不是 ['bash', 'glob', 'grep', 'bash', 'bash', 'read', 'read', 'bash', 'grep', 'read', 'grep', 'bash', 'read', 'grep', 'bash', 'read', 'read', 'grep', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash'] 的保序子序列; 步数 30 超过 max_steps=16
- **crossfile-session-log-format**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'read', 'read', 'grep', 'bash', 'read', 'read', 'grep', 'read', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 19 超过 max_steps=16
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 22 超过 max_steps=16
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'grep', 'bash', 'read', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 20 超过 max_steps=16
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列; 步数 22 超过 max_steps=16
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'read', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'read', 'read', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'grep'] 的保序子序列
- **locate-web-fetch-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'read', 'grep', 'bash', 'grep', 'bash', 'bash', 'grep', 'bash', 'bash'] 的保序子序列
- **negative-elasticsearch**: 最终回答不匹配正则 '(?i)((没有|不存在|未找到|找不到|未包含)[^。\\n]{0,15}elasticsearch)|(elasticsearch[^。\\n]{0,60}(没有|不存在|未找到|找不到|未包含))|(no\\s+elasticsearch)|(not\\s+(found|present|used|exist))'
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'read', 'bash'] 的保序子序列
