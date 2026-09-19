# M3 L2 A/B 对照报告（端到端，trials=3）

> **任务**：`T3-06`（`PROJECT.md` §6.3）。**运行日期**：2026-09-20。
> **口径**：`EVAL.md` §3.3–§3.6 的自建薄 runner（`T3-15`），不是 `dsh-eval-harness`（`T3-00` 判定不兼容）。

## 0. 一句话结论

**接入 coderag 的 B 组比不接入的 A 组高 `+25.6pp`**（`taskSuccess` 0.308 → 0.564），**S3（≥ +10pp）成立**，门禁 PASS（0 回归 / 6 条改善）。提升**全部来自 `locate` 与 `crossfile`**；两组 `regression` / `negative` 都是 1.000。B 组剩余失败的主因不是检索不准，而是**模型不调用 `code_search`**。

## 1. 运行配置

| 项 | A · 基线 | B · 词法 |
|---|---|---|
| 组 / profile | `eval-baseline` / `headless` | `eval-coderag` / `headless` |
| patch | 无 | `cordis.patch.yml`（插入 `mcp-coderag` 行） |
| 检索工具 | 无（模型只有 bash/grep/glob/read） | `code_search` / `code_outline` / `code_index` / `index_status` |
| 语料 | `/tmp/dsh-coderag-t3-03-corpus`（DSH checkout 的 rsync 副本） | 同左 |
| 索引 | `files=3967` / `chunks=63046` / `chunks_fts=63046` | 同左 |
| 用例 / trials | 13 条 × 3 = 39 次 | 13 条 × 3 = 39 次 |
| attempt error | 0 条 | 0 条 |
| 空 `session_log` | 0 条 | 0 条 |

模型调用合计 78 次。A 组墙钟约 22 分钟，B 组约 10 分钟。

## 2. 分层指标（`taskSuccess`）

| 桶 | A · 基线 | B · coderag | delta |
|---|---:|---:|---:|
| locate | 0/12 = 0.000 | 4/12 = 0.333 | **+33.3pp** |
| crossfile | 0/15 = 0.000 | 6/15 = 0.400 | **+40.0pp** |
| regression | 6/6 = 1.000 | 6/6 = 1.000 | 0 |
| negative | 6/6 = 1.000 | 6/6 = 1.000 | 0 |
| **overall** | **12/39 = 0.308** | **22/39 = 0.564** | **+25.6pp** |

## 3. 可靠性与区间

| 指标 | A · 基线 | B · coderag |
|---|---:|---:|
| `taskSuccess` | 0.308 [0.186, 0.464] | 0.564 [0.410, 0.707] |
| `pass@3`（13 条中至少 1 次通过） | 4/13 | **10/13** |
| `pass^3`（3 次全通过） | 4/13 | 4/13 |

区间为 Wilson 95%（`src/dsh_coderag/eval/metrics.py`），**以 attempt 为单位**；同一用例的 3 次 attempt 不独立，真实区间应比这里更宽。两个区间在 `[0.410, 0.464]` 有重叠，因此 `+25.6pp` 是**估计值**而非精确效应量。

`pass^3` 两组相同（都是 4 条全部不涉及 `code_search` 断言的用例），说明 coderag 目前提升的是**成功率**，还没有把任何一条用例变成"3/3 稳定通过"。

## 4. 逐条 diff（`successes`/3）

| 用例 | 桶 | A | B | B 调 `code_search`（3 次合计） | 门禁 |
|---|---|:--:|:--:|:--:|---|
| crossfile-goal-round-limit | crossfile | 0/3 | 0/3 | 0 | — |
| crossfile-skill-precedence | crossfile | 0/3 | 2/3 | 2 | 改善 |
| crossfile-subprocess-env-scrub | crossfile | 0/3 | 1/3 | 1 | 改善 |
| crossfile-todo-snapshot | crossfile | 0/3 | 2/3 | 4 | 改善 |
| crossfile-tool-cancel-code | crossfile | 0/3 | 1/3 | 1 | 改善 |
| locate-image-count-limit | locate | 0/3 | 2/3 | 2 | 改善 |
| locate-repeat-tool-reminder | locate | 0/3 | 0/3 | 0 | — |
| locate-spill-notice | locate | 0/3 | 0/3 | 0 | — |
| locate-tool-timeout-default | locate | 0/3 | 2/3 | 2 | 改善 |
| negative-elasticsearch | negative | 3/3 | 3/3 | 0 | — |
| negative-kafka | negative | 3/3 | 3/3 | 2 | — |
| regression-context-window-code | regression | 3/3 | 3/3 | 0 | — |
| regression-prune-marker | regression | 3/3 | 3/3 | 0 | — |

**A 组也全过、因此没有区分度的 4 条**：`negative-elasticsearch`、`negative-kafka`、`regression-context-window-code`、`regression-prune-marker`——正是唯一 4 条**不断言 `code_search`** 的用例。A 组其余 9 条全失败，且失败原因**全部**是 `tools_called: [code_search]` 不成立（基线没有该工具），不是答错。

## 5. 失败归因（L2）

B 组 17 条失败 attempt 的构成：

| 归因 | 条数 | 说明 |
|---|---:|---|
| **未调用 `code_search`** | **16** | 模型选择 bash/grep/glob/read，工具在但没被采纳（R5）。断言 `tools_called` 因此失败 |
| 工具返回错误 | 1 | `crossfile-todo-snapshot` 第 1 次：`code_search` 调了，但 `no_tool_errors` 被一条工具错误触发 |
| **`max_steps` 撞顶** | **0** | 提到 16 后不再有一例撞顶 |

**没有任何一条失败是"检索返回了错误文件"**。这是本报告最重要的限定：`+25.6pp` 衡量的是**端到端任务成功率**，它的提升来自"有工具可用且被采纳的用例变多"，而不是"检索把答案排得更准"（后者是 L1 的职责，见 `T3-04`/`T3-13`/`T3-14` 与 `ADR-14`）。

## 6. 门禁判定

```
baseline eval-baseline → 0.308
current  eval-coderag  → 0.564
delta: +25.6pp ｜ S3(≥+10pp): True
gate: PASS（回归 0 条）
改善 6 条，回归 0 条
```

## 7. 限制（必须与结论同时引用）

1. **13 条 × 3 次仍是小样本**，且用例是按"诊断缺口"人工挑选的，**不代表真实流量配比**（`EVAL.md` §2.9）。
2. **attempt 之间不独立**：Wilson 区间以 attempt 为单位会偏窄；同一用例同一 prompt，3 次只是同分布的重复抽样。
3. **`tools_called` 断言把"工具采纳"与"检索质量"绑在一起**（`EVAL.md` §3.4 要领 1）。16/17 的失败是采纳问题，说明这一版的主要瓶颈在**模型愿不愿意用新工具**，而不是检索排序。
4. **`pass^3` 没有变化**：不要在对外表述里说成"稳定解决"。
5. 本轮运行前修掉了两个 runner/用例缺陷（见 §6.6 的 `T3-15`/`T3-16` 备注）：MCP 工具命名空间不匹配、相对路径基准不一致。**修复前的数字不可比**。

## 8. 数据位置

| 文件 | 内容 |
|---|---|
| `eval/runs/a-v1/report.json`, `report.md` | A 组逐 attempt 结果 |
| `eval/runs/b-v1/report.json`, `report.md` | B 组逐 attempt 结果 |
| `eval/runs/gate-v1.json`, `gate-v1.md` | 门禁判定与逐条 delta |

原始 `session.v3.jsonl` 在各 run 目录的 `.sessions/` 下（按用户指示**未纳入 git**）。
