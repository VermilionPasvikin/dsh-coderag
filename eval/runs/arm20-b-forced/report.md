# L2 run: arm20-b-forced

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.750 (15/20)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 8.0 | 218051.0 | completed |
| crossfile-mcp-instruction-path | 0/1 | 0.000 | 20.0 | 804121.0 | completed |
| crossfile-session-log-format | 0/1 | 0.000 | 28.0 | 1078649.0 | completed |
| crossfile-skill-precedence | 1/1 | 1.000 | 16.0 | 601739.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 9.0 | 196352.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 19.0 | 732277.0 | completed |
| crossfile-tool-cancel-code | 1/1 | 1.000 | 9.0 | 266496.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 5.0 | 114593.0 | completed |
| locate-parallel-tool-calls | 1/1 | 1.000 | 6.0 | 121174.0 | completed |
| locate-repeat-tool-reminder | 1/1 | 1.000 | 3.0 | 41121.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 12.0 | 293644.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 5.0 | 80760.0 | completed |
| locate-web-fetch-cap | 1/1 | 1.000 | 5.0 | 87947.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 5.0 | 70808.0 | completed |
| negative-kafka | 1/1 | 1.000 | 6.0 | 92722.0 | completed |
| negative-vector-database | 0/1 | 0.000 | 10.0 | 276845.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 5.0 | 75525.0 | completed |
| regression-instruction-cap-rejects | 1/1 | 1.000 | 7.0 | 131578.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 39876.0 | completed |
| regression-repeat-thresholds | 1/1 | 1.000 | 5.0 | 78145.0 | completed |

## 失败明细

- **crossfile-mcp-instruction-path**: 步数 20 超过 max_steps=16
- **crossfile-session-log-format**: 步数 28 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 19 超过 max_steps=16
- **locate-spill-notice**: 步数 12 超过 max_steps=10
- **negative-vector-database**: 步数 10 超过 max_steps=8
