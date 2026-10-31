# L2 run: arm20-b-forced-t3-steps

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.967 (58/60)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 3/3 | 1.000 | 11.0 | 347923.3 | completed |
| crossfile-mcp-instruction-path | 2/3 | 0.667 | 27.3 | 1525328.7 | completed |
| crossfile-session-log-format | 3/3 | 1.000 | 18.7 | 849894.7 | completed |
| crossfile-skill-precedence | 3/3 | 1.000 | 22.7 | 1116402.7 | completed |
| crossfile-subprocess-env-scrub | 3/3 | 1.000 | 10.0 | 284573.3 | completed |
| crossfile-todo-snapshot | 2/3 | 0.667 | 27.3 | 1244280.0 | completed |
| crossfile-tool-cancel-code | 3/3 | 1.000 | 9.3 | 293382.0 | completed |
| locate-image-count-limit | 3/3 | 1.000 | 6.0 | 121833.3 | completed |
| locate-parallel-tool-calls | 3/3 | 1.000 | 5.0 | 86613.3 | completed |
| locate-repeat-tool-reminder | 3/3 | 1.000 | 4.0 | 63360.3 | completed |
| locate-spill-notice | 3/3 | 1.000 | 9.7 | 215201.7 | completed |
| locate-tool-timeout-default | 3/3 | 1.000 | 4.7 | 70802.0 | completed |
| locate-web-fetch-cap | 3/3 | 1.000 | 5.7 | 106474.3 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 5.0 | 74793.0 | completed |
| negative-kafka | 3/3 | 1.000 | 5.7 | 88231.0 | completed |
| negative-vector-database | 3/3 | 1.000 | 7.7 | 174162.7 | completed |
| regression-context-window-code | 3/3 | 1.000 | 4.3 | 65205.7 | completed |
| regression-instruction-cap-rejects | 3/3 | 1.000 | 7.7 | 164235.3 | completed |
| regression-prune-marker | 3/3 | 1.000 | 4.0 | 56548.3 | completed |
| regression-repeat-thresholds | 3/3 | 1.000 | 5.0 | 81375.0 | completed |

## 失败明细

- **crossfile-mcp-instruction-path**: 步数 32 超过 max_steps=28
- **crossfile-todo-snapshot**: 步数 41 超过 max_steps=28
