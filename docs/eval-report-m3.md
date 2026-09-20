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

原始 `session.v3.jsonl` 在各 run 目录的 `.sessions/` 下（原始日志不入库；报告与门禁结论入库）。

---

## 9. R5 复测：工具采纳才是端到端的主杠杆（2026-09-20）

§5 的结论是"B 组 16/17 条失败是模型没调用 `code_search`"。这正是 `PROJECT.md` §7 的 **R5（模型不使用新工具）**，且已从"风险"变成"已发生"。本次按 R5 的既定应对改了 **`code_search` 的 `description`**（`c06a7d9`），**只改这一个工具的文本**，其余不动，以便归因。

**改法**：旧文本只在"你不知道确切标识符时"才建议使用——而采纳最差的三条（`crossfile-goal-round-limit`、`locate-repeat-tool-reminder`、`locate-spill-notice`）恰好都是**看起来像已知标识符**的查询，等于给了模型一个不调用的借口。新文本把它变成"任何定位类问题的第一步，**包括你已经知道标识符时**"，并把字面搜索降级为"仅当你必须匹配精确字符串或正则时"。

### 9.1 结果（同一语料、同一模型、13 条 × 3 trials）

| 指标 | 改前（`b-v1`） | 改后（`b-r5`） | 变化 |
|---|---:|---:|---|
| **调用过 `code_search` 的 attempt** | 13/39 = 33.3% | **31/39 = 79.5%** | **+46.2pp** |
| `taskSuccess` | 22/39 = 0.564 | **35/39 = 0.897** | **+33.3pp** |
| S3（vs A 组 0.308） | +25.6pp | **+59.0pp** | — |

> **勘误（2026-09-20）**：本节初版把"`code_search` 调用**总次数**"（14 → 38）误写成"调用过的 **attempt** 数"，得出 35.9% → 97.4%。正确口径是按 attempt 去重：**13/39 → 31/39**（调用总次数 14 → 38）。结论方向不变，幅度小一档。

逐条：**8 条改善，0 条回归**。三条"从未调用"的用例全部从 0/3 变成 2/3（`crossfile-goal-round-limit`、`locate-repeat-tool-reminder`、`locate-spill-notice`）。

**采纳之后检索还挡路吗？** 在**调用了 `code_search` 的 31 个 attempt 里只有 1 个失败（3%）**。剩下 4 条失败的构成是：**3 条根本没调用**（采纳）+ **1 条 `max_steps` 20 > 16 且伴有一次工具报错**——**没有一条是"检索返回了错误文件"**。

### 9.2 中间态：门禁曾 **FAIL（回归 1 条）**，根因是**断言误杀**

首轮 `taskSuccess` 是 34/39，门禁判 FAIL：

```
delta: +30.8pp ｜ S3(≥+10pp): True
gate: FAIL（回归 1 条）
  negative-elasticsearch: 1.000 → 0.667
```

按 `EVAL.md` §2.7，**单条回归即失败**，不能因为均值大涨就放行。但这条"回归"是**断言误杀**——第 3 次 attempt 的最终回答（原文）：

> 没有。  我在整个工作区（含 packages/、docs/、配置与依赖清单）搜索过 `elasticsearch` / `Elasticsearch` / `ELASTICSEARCH` / `elastic`，**没有任何匹配**；也没有对应的客户端依赖或检索服务封装。

**这是正确答案**（该用例的 `notes` 记录全副本 grep 0 命中）。旧断言正则要求**否定词与技术名同句、相距 ≤15 个非句号字符**：

```
((没有|不存在|未找到|找不到|未包含)[^。\n]{0,15}elasticsearch)|(no\s+elasticsearch)|(not\s+(found|present|used|exist))
```

而这次回答**先给结论（"没有。"独立成句）、再给证据**，技术名落在下一句 → 不匹配。采纳率上来之后回答句式变了，撞上只认"同句紧邻"的正则。

### 9.3 修复：接受"名字在前"的方向，但**仍要求同句**

这条正则之所以紧，是为了挡住 `reject` 里的"可能在 packages/queue 下面，**我没有细看**。"一类含糊作答（`T3-16` 的审核就是为这个收窄的）。所以**没有放宽成"只要出现否定词"**，而是新增一个**方向**的替代分支：

```diff
- ((没有|不存在|未找到|找不到|未包含)[^。\n]{0,15}elasticsearch)|(no\s+elasticsearch)|(...)
+ ((没有|不存在|未找到|找不到|未包含)[^。\n]{0,15}elasticsearch)
+ |(elasticsearch[^。\n]{0,60}(没有|不存在|未找到|找不到|未包含))   ← 新增：名字 → 否定，仍限同句
+ |(no\s+elasticsearch)|(not\s+(found|present|used|exist))
```

`negative-kafka` 有**完全相同的缺陷**（同一模板），一并按同样方式修正。两个用例各补了一条 `accept` 样例（就是本次真实回答的句式），由 `tests/test_cases.py` 逐条跑 `accept`/`reject` 验证（9 passed / 1 skipped）——**拒绝项一条都没被放过**。

**复评口径**：改的是**判分**，不是行为——模型会话记录未变。因此**没有重跑模型**（省下 39 次调用），而是用修好的断言对 `b-r5` 的**同一批 `session.v3.jsonl` 重新判分**：只有 `negative-elasticsearch` 第 3 次 attempt 从 `False` 翻到 `True`（**1 条，且正是被误杀的那条**），其余 38 条逐条不变。

### 9.4 最终门禁判定：两处都 PASS

```
$ python scripts/ab_eval.py gate --baseline eval/runs/b-v1/report.json --current eval/runs/b-r5/report.json
delta: +33.3pp ｜ gate: PASS（回归 0 条）        ← R5 这一轮自己的前后对比

$ python scripts/ab_eval.py gate --baseline eval/runs/a-v1/report.json --current eval/runs/b-r5/report.json
delta: +59.0pp ｜ gate: PASS（回归 0 条）        ← 当前 S3（有检索 vs 无检索）
```

### 9.5 结论

- **R5 是端到端的主杠杆**：只改一段模型可见文本，采纳率（按 attempt）33.3% → 79.5%、`taskSuccess` 0.564 → 0.897、**S3 +25.6pp → +59.0pp**。这印证了 `ADR-14` §10.3 的判断——端到端瓶颈是**工具采纳**，不是排序。
- **采纳之后，检索质量已不是当前瓶颈**：调用了工具的 31 个 attempt 里只失败 1 个（3%）；4 条残余失败是 3 条采纳 + 1 条步数，**没有一条归因于检索排序**。这把 `T3-08`–`T3-11`（向量）的**端到端收益**进一步压窄——向量能买到的只剩 **L1 的静态检索质量**（`natural` S@5 = 0、`crossfile` = 0.091）。
- **顺带暴露并修好了一条脆弱断言**：多调用检索后回答句式变化（先结论后证据），旧正则误杀。修法是**新增方向而非放宽强度**，含糊作答仍被拒。
- **口径提醒**：本节的 `b-r5` 报告是**重新判分**的结果（判分改动、会话未变）。`b-v1`→`b-r5` 的 delta 同时包含"工具文本改动"与"断言修正"两个因素，其中断言修正只影响 `negative-elasticsearch` 一条（+1 attempt）。

### 9.6 数据位置

| 文件 | 内容 |
|---|---|
| `eval/runs/b-r5/report.json`, `report.md` | R5 后的 B 组（按修好的断言重新判分） |
| `eval/runs/gate-r5.{json,md}` | `b-v1` → `b-r5`（R5 本轮的前后对比） |
| `eval/runs/gate-current.{json,md}` | `a-v1` → `b-r5`（当前 S3） |
| `eval/runs/gate-v1.{json,md}` | `a-v1` → `b-v1`（T3-06 的历史对照，保留） |
| `eval/runs/b-v1/` | R5 前的基线 |
