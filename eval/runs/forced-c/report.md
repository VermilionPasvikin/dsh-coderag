# L2 run: forced-c-vector

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.846 (11/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 10.0 | 302843.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 22.0 | 1024747.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 9.0 | 201123.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 29.0 | 985031.0 | completed |
| crossfile-tool-cancel-code | 1/1 | 1.000 | 6.0 | 126634.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 4.0 | 76224.0 | completed |
| locate-repeat-tool-reminder | 1/1 | 1.000 | 4.0 | 65697.0 | completed |
| locate-spill-notice | 1/1 | 1.000 | 7.0 | 193220.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 4.0 | 59100.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 5.0 | 72998.0 | completed |
| negative-kafka | 1/1 | 1.000 | 7.0 | 112901.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 4.0 | 71273.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 4.0 | 65670.0 | completed |

## 失败明细

- **crossfile-skill-precedence**: 步数 22 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 29 超过 max_steps=16
