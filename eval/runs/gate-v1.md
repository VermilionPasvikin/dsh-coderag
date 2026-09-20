# L2 gate

- baseline: `eval-baseline` → 0.308
- current: `eval-coderag` → 0.564
- delta: +25.6pp ｜ S3(≥+10pp): True
- gate: PASS （回归 0 条）

## 改善

- crossfile-skill-precedence: 0.000 → 0.667
- crossfile-subprocess-env-scrub: 0.000 → 0.333
- crossfile-todo-snapshot: 0.000 → 0.667
- crossfile-tool-cancel-code: 0.000 → 0.333
- locate-image-count-limit: 0.000 → 0.667
- locate-tool-timeout-default: 0.000 → 0.667
