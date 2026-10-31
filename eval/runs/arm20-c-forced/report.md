# L2 run: arm20-c-forced

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.800 (16/20)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 9.0 | 275509.0 | completed |
| crossfile-mcp-instruction-path | 0/1 | 0.000 | 35.0 | 2909967.0 | completed |
| crossfile-session-log-format | 1/1 | 1.000 | 15.0 | 512007.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 17.0 | 730395.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 6.0 | 157255.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 26.0 | 1028476.0 | completed |
| crossfile-tool-cancel-code | 1/1 | 1.000 | 9.0 | 203162.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 5.0 | 96340.0 | completed |
| locate-parallel-tool-calls | 1/1 | 1.000 | 7.0 | 113686.0 | completed |
| locate-repeat-tool-reminder | 1/1 | 1.000 | 5.0 | 81380.0 | completed |
| locate-spill-notice | 1/1 | 1.000 | 7.0 | 240831.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 5.0 | 85704.0 | completed |
| locate-web-fetch-cap | 1/1 | 1.000 | 6.0 | 138934.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 5.0 | 105053.0 | completed |
| negative-kafka | 1/1 | 1.000 | 5.0 | 75577.0 | completed |
| negative-vector-database | 0/1 | 0.000 | 12.0 | 263661.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 4.0 | 55993.0 | completed |
| regression-instruction-cap-rejects | 1/1 | 1.000 | 10.0 | 286930.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 3.0 | 39665.0 | completed |
| regression-repeat-thresholds | 1/1 | 1.000 | 5.0 | 82864.0 | completed |

## 失败明细

- **crossfile-mcp-instruction-path**: 步数 35 超过 max_steps=16
- **crossfile-skill-precedence**: 步数 17 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 26 超过 max_steps=16
- **negative-vector-database**: 步数 12 超过 max_steps=8
