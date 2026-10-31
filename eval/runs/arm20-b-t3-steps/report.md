# L2 run: arm20-b-t3-steps

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.683 (41/60)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 3/3 | 1.000 | 10.3 | 275128.0 | completed |
| crossfile-mcp-instruction-path | 3/3 | 1.000 | 23.3 | 1222882.3 | completed |
| crossfile-session-log-format | 2/3 | 0.667 | 11.7 | 537605.3 | completed, error |
| crossfile-skill-precedence | 3/3 | 1.000 | 24.3 | 1556474.0 | completed |
| crossfile-subprocess-env-scrub | 2/3 | 0.667 | 7.7 | 183251.0 | completed |
| crossfile-todo-snapshot | 2/3 | 0.667 | 32.0 | 1503141.7 | completed |
| crossfile-tool-cancel-code | 2/3 | 0.667 | 8.3 | 290242.7 | completed |
| locate-image-count-limit | 2/3 | 0.667 | 5.0 | 106975.3 | completed |
| locate-parallel-tool-calls | 1/3 | 0.333 | 4.7 | 81099.3 | completed |
| locate-repeat-tool-reminder | 1/3 | 0.333 | 3.0 | 46969.0 | completed |
| locate-spill-notice | 1/3 | 0.333 | 7.7 | 187808.3 | completed |
| locate-tool-timeout-default | 2/3 | 0.667 | 4.3 | 68008.3 | completed |
| locate-web-fetch-cap | 1/3 | 0.333 | 7.0 | 163068.7 | completed |
| negative-elasticsearch | 2/3 | 0.667 | 4.0 | 52358.7 | completed |
| negative-kafka | 3/3 | 1.000 | 4.0 | 53547.7 | completed |
| negative-vector-database | 3/3 | 1.000 | 8.0 | 139316.0 | completed |
| regression-context-window-code | 3/3 | 1.000 | 3.3 | 46244.0 | completed |
| regression-instruction-cap-rejects | 1/3 | 0.333 | 6.3 | 112903.7 | completed |
| regression-prune-marker | 3/3 | 1.000 | 3.3 | 43865.3 | completed |
| regression-repeat-thresholds | 1/3 | 0.333 | 5.7 | 103469.7 | completed |

## 失败明细

- **crossfile-session-log-format**: turn_end 期望 'completed'，实际 'error'; 最终回答不匹配正则 'session-format|filename\\.ts'; 最终回答不匹配正则 'session-persistence-jsonl|zstd'; dsh 退出码 1
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'grep', 'grep', 'grep', 'read', 'grep', 'read', 'bash'] 的保序子序列
- **crossfile-todo-snapshot**: 步数 50 超过 max_steps=28
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'read'] 的保序子序列
- **locate-parallel-tool-calls**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'read', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'bash', 'bash', 'read', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'bash', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'bash', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'grep', 'read'] 的保序子序列
- **locate-web-fetch-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
- **locate-web-fetch-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'bash', 'bash', 'read'] 的保序子序列
- **negative-elasticsearch**: 最终回答不匹配正则 '(?i)((没有|不存在|未找到|找不到|未包含)[^。\\n]{0,15}elasticsearch)|(elasticsearch[^。\\n]{0,60}(没有|不存在|未找到|找不到|未包含))|(no\\s+elasticsearch)|(not\\s+(found|present|used|exist))'
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'read', 'grep', 'read', 'read', 'bash'] 的保序子序列
- **regression-instruction-cap-rejects**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'grep', 'read', 'read', 'bash'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'read', 'bash', 'read'] 的保序子序列
- **regression-repeat-thresholds**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'bash', 'grep'] 的保序子序列
