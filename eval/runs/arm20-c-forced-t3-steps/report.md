# L2 run: arm20-c-forced-t3-steps

- profile: `eval-coderag` ｜ trials: 3
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.967 (58/60)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 3/3 | 1.000 | 9.0 | 313761.0 | completed |
| crossfile-mcp-instruction-path | 3/3 | 1.000 | 23.7 | 1218445.7 | completed |
| crossfile-session-log-format | 2/3 | 0.667 | 24.3 | 1030781.0 | completed |
| crossfile-skill-precedence | 3/3 | 1.000 | 18.0 | 717170.7 | completed |
| crossfile-subprocess-env-scrub | 3/3 | 1.000 | 7.3 | 195952.0 | completed |
| crossfile-todo-snapshot | 2/3 | 0.667 | 26.7 | 1175091.3 | completed |
| crossfile-tool-cancel-code | 3/3 | 1.000 | 8.0 | 232097.7 | completed |
| locate-image-count-limit | 3/3 | 1.000 | 4.3 | 87897.7 | completed |
| locate-parallel-tool-calls | 3/3 | 1.000 | 4.3 | 70837.3 | completed |
| locate-repeat-tool-reminder | 3/3 | 1.000 | 4.0 | 69720.3 | completed |
| locate-spill-notice | 3/3 | 1.000 | 7.3 | 187838.7 | completed |
| locate-tool-timeout-default | 3/3 | 1.000 | 5.3 | 87431.3 | completed |
| locate-web-fetch-cap | 3/3 | 1.000 | 6.0 | 128839.7 | completed |
| negative-elasticsearch | 3/3 | 1.000 | 5.7 | 95002.0 | completed |
| negative-kafka | 3/3 | 1.000 | 6.7 | 108133.0 | completed |
| negative-vector-database | 3/3 | 1.000 | 8.0 | 200499.3 | completed |
| regression-context-window-code | 3/3 | 1.000 | 4.0 | 58353.0 | completed |
| regression-instruction-cap-rejects | 3/3 | 1.000 | 7.0 | 139259.0 | completed |
| regression-prune-marker | 3/3 | 1.000 | 4.0 | 55642.7 | completed |
| regression-repeat-thresholds | 3/3 | 1.000 | 5.7 | 96233.7 | completed |

## 失败明细

- **crossfile-session-log-format**: 步数 38 超过 max_steps=28
- **crossfile-todo-snapshot**: 步数 36 超过 max_steps=28
