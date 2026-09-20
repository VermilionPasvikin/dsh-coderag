# L2 gate

- baseline: `eval-baseline` → 0.308
- current: `eval-coderag` → 0.769
- delta: +46.2pp ｜ S3(≥+10pp): True
- gate: PASS （回归 0 条）

## 改善

- crossfile-skill-precedence: 0.000 → 1.000
- crossfile-subprocess-env-scrub: 0.000 → 1.000
- crossfile-todo-snapshot: 0.000 → 1.000
- locate-image-count-limit: 0.000 → 1.000
- locate-spill-notice: 0.000 → 1.000
- locate-tool-timeout-default: 0.000 → 1.000
