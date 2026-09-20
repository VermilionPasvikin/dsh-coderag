# L2 gate

- baseline: `eval-coderag` → 0.564
- current: `eval-coderag` → 0.897
- delta: +33.3pp ｜ S3(≥+10pp): True
- gate: PASS （回归 0 条）

## 改善

- crossfile-goal-round-limit: 0.000 → 0.667
- crossfile-skill-precedence: 0.667 → 1.000
- crossfile-subprocess-env-scrub: 0.333 → 1.000
- crossfile-tool-cancel-code: 0.333 → 1.000
- locate-image-count-limit: 0.667 → 1.000
- locate-repeat-tool-reminder: 0.000 → 0.667
- locate-spill-notice: 0.000 → 0.667
- locate-tool-timeout-default: 0.667 → 1.000
