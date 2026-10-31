# L2 run: arm-sem-b

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.083 (1/12)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| semantic-compaction-threshold | 0/3 | 0.000 | 3.3 | 53590.0 | completed |
| semantic-image-cap | 0/3 | 0.000 | 11.3 | 372723.3 | completed |
| semantic-skill-catalog-tags | 0/3 | 0.000 | 3.0 | 49556.3 | completed |
| semantic-spill-cap | 1/3 | 0.333 | 6.0 | 156606.0 | completed |

## 失败明细

- **semantic-compaction-threshold**: tools_called ['code_search'] 不是 ['grep', 'glob', 'read', 'grep', 'read'] 的保序子序列
- **semantic-compaction-threshold**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash'] 的保序子序列
- **semantic-compaction-threshold**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash'] 的保序子序列
- **semantic-image-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'grep', 'read', 'grep', 'read', 'grep', 'bash'] 的保序子序列; 最终回答不匹配正则 '32\\s*(MiB|MB|兆字节)'
- **semantic-image-cap**: 最终回答不匹配正则 '32\\s*(MiB|MB|兆字节)'; 步数 18 超过 max_steps=16
- **semantic-image-cap**: 最终回答不匹配正则 '32\\s*(MiB|MB|兆字节)'
- **semantic-skill-catalog-tags**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read'] 的保序子序列
- **semantic-skill-catalog-tags**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read'] 的保序子序列
- **semantic-skill-catalog-tags**: tools_called ['code_search'] 不是 ['grep', 'grep', 'read'] 的保序子序列
- **semantic-spill-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'read', 'bash', 'bash', 'bash', 'bash', 'read', 'read'] 的保序子序列
- **semantic-spill-cap**: tools_called ['code_search'] 不是 ['bash', 'grep', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash', 'bash'] 的保序子序列
