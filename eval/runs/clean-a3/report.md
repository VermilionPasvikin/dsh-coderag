# L2 run: clean-baseline-3

- profile: `headless` ｜ trials: 3
- workspace: `/private/tmp/dsh-coderag-t3-03-corpus`
- taskSuccess: 0.282 (11/39)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 0/3 | 0.000 | 7.7 | 285190.7 | completed |
| crossfile-skill-precedence | 0/3 | 0.000 | 12.3 | 606207.0 | completed |
| crossfile-subprocess-env-scrub | 0/3 | 0.000 | 4.7 | 94866.3 | completed |
| crossfile-todo-snapshot | 0/3 | 0.000 | 12.0 | 379895.0 | completed |
| crossfile-tool-cancel-code | 0/3 | 0.000 | 6.7 | 159276.0 | completed |
| locate-image-count-limit | 0/3 | 0.000 | 3.7 | 79687.3 | completed |
| locate-repeat-tool-reminder | 0/3 | 0.000 | 3.3 | 55724.3 | completed |
| locate-spill-notice | 0/3 | 0.000 | 6.7 | 173747.7 | completed |
| locate-tool-timeout-default | 0/3 | 0.000 | 4.7 | 71723.3 | completed |
| negative-elasticsearch | 2/3 | 0.667 | 3.0 | 40402.3 | completed |
| negative-kafka | 3/3 | 1.000 | 3.7 | 48771.7 | completed |
| regression-context-window-code | 3/3 | 1.000 | 2.0 | 25876.0 | completed |
| regression-prune-marker | 3/3 | 1.000 | 2.7 | 35147.3 | completed |

## 失败明细

- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['glob', 'grep', 'read', 'read', 'read', 'grep', 'grep', 'read', 'read', 'read'] 的保序子序列
- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'grep', 'read', 'read', 'read', 'read', 'grep', 'read'] 的保序子序列
- **crossfile-goal-round-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'read', 'grep', 'bash', 'grep', 'bash', 'read', 'read', 'read'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'bash', 'bash', 'grep', 'read', 'grep', 'bash', 'read', 'read', 'bash', 'grep', 'bash', 'bash', 'read', 'bash', 'read', 'read', 'bash', 'bash', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'read', 'grep', 'bash', 'read', 'bash', 'bash', 'read', 'read', 'read', 'read', 'read', 'read', 'bash', 'bash', 'bash', 'bash', 'bash', 'read', 'read', 'read', 'bash'] 的保序子序列
- **crossfile-skill-precedence**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'read', 'grep', 'read', 'read', 'read', 'read', 'bash', 'grep', 'grep', 'read', 'read', 'bash', 'grep', 'bash', 'read', 'read', 'bash', 'bash', 'read'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'read', 'bash', 'grep'] 的保序子序列
- **crossfile-subprocess-env-scrub**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'glob', 'glob', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'bash', 'grep', 'grep', 'bash', 'grep', 'bash', 'grep', 'read', 'read', 'read', 'grep'] 的保序子序列; 有工具返回错误：['call_01_3zcTjUNR3wHcmPXWi1ZR2894']
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'grep', 'bash', 'read', 'read'] 的保序子序列; 有工具返回错误：['call_01_YpTWhTE0SM0yYIdEnntE2510']
- **crossfile-todo-snapshot**: tools_called ['code_search'] 不是 ['bash', 'glob', 'glob', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'read', 'grep', 'read', 'read', 'read', 'bash', 'read', 'bash', 'read', 'read', 'read'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'grep', 'grep', 'read', 'read', 'read', 'read', 'grep'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'grep', 'grep', 'read', 'read', 'read', 'grep', 'bash', 'bash'] 的保序子序列
- **crossfile-tool-cancel-code**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'grep', 'grep', 'read', 'read', 'read', 'grep', 'bash', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read', 'read', 'grep', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read'] 的保序子序列
- **locate-image-count-limit**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'grep', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read'] 的保序子序列
- **locate-repeat-tool-reminder**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'grep', 'bash', 'read', 'read', 'grep', 'grep', 'read', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'glob', 'read', 'bash', 'read', 'bash', 'bash', 'read', 'bash', 'read'] 的保序子序列
- **locate-spill-notice**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'grep', 'read', 'read', 'grep', 'grep', 'read', 'bash', 'bash'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['grep', 'bash', 'read', 'grep', 'grep'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'read', 'read', 'read', 'grep'] 的保序子序列
- **locate-tool-timeout-default**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'read', 'bash'] 的保序子序列
- **negative-elasticsearch**: 最终回答不匹配正则 '(?i)((没有|不存在|未找到|找不到|未包含)[^。\\n]{0,15}elasticsearch)|(elasticsearch[^。\\n]{0,60}(没有|不存在|未找到|找不到|未包含))|(no\\s+elasticsearch)|(not\\s+(found|present|used|exist))'
