# L2 run: forced-cloud-c

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.846 (11/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 10.0 | 271334.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 18.0 | 663589.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 7.0 | 142168.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 24.0 | 921035.0 | completed |
| crossfile-tool-cancel-code | 1/1 | 1.000 | 9.0 | 218250.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 5.0 | 106762.0 | completed |
| locate-repeat-tool-reminder | 1/1 | 1.000 | 4.0 | 62574.0 | completed |
| locate-spill-notice | 1/1 | 1.000 | 9.0 | 261635.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 4.0 | 56685.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 4.0 | 55556.0 | completed |
| negative-kafka | 1/1 | 1.000 | 5.0 | 90531.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 4.0 | 56338.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 4.0 | 55274.0 | completed |

## 失败明细

- **crossfile-skill-precedence**: 步数 18 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 24 超过 max_steps=16
