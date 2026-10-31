# L2 run: arm-sem-c

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.250 (3/12)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| semantic-compaction-threshold | 0/3 | 0.000 | 2.7 | 40302.7 | completed |
| semantic-image-cap | 0/3 | 0.000 | 8.7 | 252952.0 | completed |
| semantic-skill-catalog-tags | 0/3 | 0.000 | 2.7 | 38533.7 | completed |
| semantic-spill-cap | 3/3 | 1.000 | 7.7 | 213623.7 | completed |

## 失败明细

- **semantic-compaction-threshold**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash'] 的保序子序列
- **semantic-compaction-threshold**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep'] 的保序子序列
- **semantic-compaction-threshold**: tools_called ['code_search'] 不是 ['bash', 'grep'] 的保序子序列
- **semantic-image-cap**: 最终回答不匹配正则 '32\\s*(MiB|MB|兆字节)'
- **semantic-image-cap**: 最终回答不匹配正则 '32\\s*(MiB|MB|兆字节)'
- **semantic-image-cap**: 最终回答不匹配正则 '32\\s*(MiB|MB|兆字节)'
- **semantic-skill-catalog-tags**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read'] 的保序子序列
- **semantic-skill-catalog-tags**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read'] 的保序子序列
- **semantic-skill-catalog-tags**: tools_called ['code_search'] 不是 ['grep'] 的保序子序列
