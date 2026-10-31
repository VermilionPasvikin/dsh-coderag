# L2 run: forced-b-bm25

- profile: `eval-coderag` ｜ trials: 1
- workspace: `/Users/vermi/projects/dsh`
- taskSuccess: 0.769 (10/13)

| case | successes | rate | steps | tokens | turn_end |
|---|---:|---:|---:|---:|---|
| crossfile-goal-round-limit | 1/1 | 1.000 | 10.0 | 332439.0 | completed |
| crossfile-skill-precedence | 0/1 | 0.000 | 19.0 | 1007840.0 | completed |
| crossfile-subprocess-env-scrub | 1/1 | 1.000 | 9.0 | 217601.0 | completed |
| crossfile-todo-snapshot | 0/1 | 0.000 | 26.0 | 970136.0 | completed |
| crossfile-tool-cancel-code | 1/1 | 1.000 | 8.0 | 211284.0 | completed |
| locate-image-count-limit | 1/1 | 1.000 | 6.0 | 107854.0 | completed |
| locate-repeat-tool-reminder | 1/1 | 1.000 | 3.0 | 45687.0 | completed |
| locate-spill-notice | 0/1 | 0.000 | 14.0 | 406874.0 | completed |
| locate-tool-timeout-default | 1/1 | 1.000 | 6.0 | 136361.0 | completed |
| negative-elasticsearch | 1/1 | 1.000 | 5.0 | 81004.0 | completed |
| negative-kafka | 1/1 | 1.000 | 7.0 | 124833.0 | completed |
| regression-context-window-code | 1/1 | 1.000 | 6.0 | 91239.0 | completed |
| regression-prune-marker | 1/1 | 1.000 | 5.0 | 76989.0 | completed |

## 失败明细

- **crossfile-skill-precedence**: 步数 19 超过 max_steps=16
- **crossfile-todo-snapshot**: 步数 26 超过 max_steps=16
- **locate-spill-notice**: 步数 14 超过 max_steps=10
