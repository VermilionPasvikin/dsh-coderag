# M5 向量天花板探针（`T5-14`）

> 目的：在写实现之前用**数据**回答「向量**最多**能把这 30 条抬到哪」（`ADR-15` §3.2、`ADR-16` §1.8）。探针测的是**理论上限**——全量 chunk + 全量 query 直接算余弦，不走 RRF、不走 top-k 预算裁剪。

## 1. 方法与口径

| 项 | 值 |
|---|---|
| 后端 / 模型 | Ollama `http://127.0.0.1:11434/api/embed` / `bge-m3` |
| 维度 | `1024`（与 `bge-m3` 的 `embedding_length` 一致） |
| 语料 | `/tmp/dsh-coderag-t3-03-corpus`（**与 L1 同源同版本**） |
| chunk 数 | `63046` |
| 评测集 | `eval/tasks.jsonl`（golden `m3-b1`，30 条） |
| 召回 | 全量 chunk 暴力余弦，`top_k = 5` |
| 排序档位 | **与生产一致**：第一层是「非测试路径优先」（`searcher.TEST_PATH_TIER_SQL`，`T3-14`），第二层才是余弦降序。**第二列另给纯余弦（无档位）读数**——不是生产口径，仅用于说明该档位有多关键 |
| embedding 输入 | `chunks.text` **原样**（chunker 已把上下文前缀行 `// file: … \| symbol: … \| lines …` 拼在正文之前，`ADR-16` §5 的第 5 条只允许已入库 chunk 进向量） |
| query 输入 | 查询原句，不加任何指令前缀 |
| 命中判据 | 与 `EVAL.md` §2.5 **逐条一致**：按上述排序后，第一个 `expect_paths` 出现在第几位即为 `rank`；`rank ≤ 5` 记命中 |
| 次要口径 | `dedup` = 先对 `top-5` 里的重复路径去重再定位（生产返回的是 chunk 不去重，故仅作敏感性参考） |

> **口径上的诚实说明**：探针把**上下文前缀行**一起 embedding 了（含工作区相对路径与符号名）。这确实是实现将要发送的文本，但它也可能让「路径名与查询语义接近」的 chunk 占便宜。因此这里给出的是**生产口径的上限**，而不是「纯代码文本」的上限。

## 2. 天花板指标（向量，全量余弦 + 生产排序档位）

| 桶 | n | S@1 | S@3 | **S@5** | MRR | S@5 的 Wilson 95% | dedup S@5 | 纯余弦 S@5（无档位） |
|---|---|---|---|---|---|---|---|---|
| **overall** | 30 | 0.500 | 0.633 | **0.700** | 0.565 | [0.521, 0.833] | 0.700 | 0.433 |
| **exact** | 12 | 0.833 | 0.833 | **0.917** | 0.854 | [0.646, 0.985] | 0.917 | 0.833 |
| **crossfile** | 11 | 0.364 | 0.636 | **0.636** | 0.470 | [0.354, 0.848] | 0.636 | 0.273 |
| **natural** | 7 | 0.143 | 0.286 | **0.429** | 0.219 | [0.158, 0.750] | 0.429 | 0.000 |

> **为什么必须带排序档位**：本语料 **38489/63046（61%）的 chunk 来自测试文件**。纯余弦会把 `tests/*.spec.ts` 排到真实实现之前（例如 L-026 的正确文件 `guard/repeat-tool-reminder/src/index.ts` 在纯余弦下根本不进 top-5，而它自己的 spec 文件是 top-1）。生产检索的第一层排序就是「非测试优先」（`T3-14` 把该档位放进 SQL `ORDER BY` 第一层），所以向量路径也必须继承它；不继承则既不是生产口径，也会让 `exact` 直接回退。右列给出无档位读数仅为对照。

### 2.1 探针自身的对照检验（不是排序规则的伪影）

| 对照 | `natural` S@5 | 说明 |
|---|---|---|
| 真实 query + 真实向量 | **3/7** | 本报告主读数 |
| 打乱「向量行 ↔ 路径」对应 | 0/7 | 语义对应被破坏 → 命中应归零 |
| 随机单位向量当 query | 0/7 | 无信号输入 → 命中应归零 |

> 两个对照都是 0，说明这 3 个命中来自**真实的语义对齐**，而不是「非测试优先」档位本身把正确答案凑进了 top-5。

## 3. 与 B 组（纯 BM25 / 1.0.0 默认路径）对照

| 桶 | BM25 S@5 | 向量 S@5（生产档位） | Δ（pp） | 向量 S@5（纯余弦） | BM25 MRR | 向量 MRR |
|---|---|---|---|---|---|---|
| **overall** | 0.433 | 0.700 | +26.7 | 0.433 | 0.313 | 0.565 |
| **exact** | 1.000 | 0.917 | -8.3 | 0.833 | 0.700 | 0.854 |
| **crossfile** | 0.091 | 0.636 | +54.5 | 0.273 | 0.091 | 0.470 |
| **natural** | 0.000 | 0.429 | +42.9 | 0.000 | 0.000 | 0.219 |

## 4. 逐条结果

| ID | 桶 | rank（生产档位） | 期望路径最佳名次 | 纯余弦 rank | 命中 | 期望路径 | top-1（余弦） |
|---|---|---|---|---|---|---|---|
| L-001 | exact | — | 191 | — | ❌ | packages/mcp/mcp-client/src/index.ts | packages/lsp/tool-lsp/src/index.ts（0.727） |
| L-002 | exact | 1 | 1 | 1 | ✅ | packages/llm/llm/src/error.ts | packages/llm/llm/src/error.ts（0.679） |
| L-003 | exact | 1 | 1 | 1 | ✅ | packages/subagent/subagent/src/depth.ts | packages/subagent/subagent/src/depth.ts（0.612） |
| L-004 | exact | 1 | 1 | 5 | ✅ | packages/sandbox/sandbox-policy/src/session-mode.ts | packages/sandbox/sandbox-policy/src/session-mode.ts（0.576） |
| L-005 | crossfile | 3 | 3 | 3 | ✅ | packages/mcp/mcp-client/src/index.ts<br>packages/mcp/mcp-client/src/tools.ts | packages/experimental/browser-use-runtime/src/mcp.ts（0.624） |
| L-006 | crossfile | — | 114 | — | ❌ | packages/sandbox/sandbox-policy/src/session-mode.ts<br>packages/sandbox/sandbox-policy/src/index.ts | packages/api/workspace-controller/src/client/model.ts（0.605） |
| L-007 | crossfile | 3 | 3 | — | ✅ | packages/core/session/src/types.ts<br>packages/subagent/subagent/src/depth.ts<br>packages/subagent/subagent/src/child-agent.ts | packages/client/ui-settings-plugins/src/client/locales.ts（0.616） |
| L-008 | crossfile | — | 21 | — | ❌ | packages/subprocess/subprocess/src/index.ts | packages/subprocess/subprocess-local/src/index.ts（0.611） |
| L-009 | natural | 3 | 3 | — | ✅ | packages/llm/llm/src/retry-policy.ts | packages/llm/llm-deepseek/src/common/request-files.ts（0.634） |
| L-010 | natural | — | 199 | — | ❌ | packages/compaction/compaction-basic/src/index.ts | packages/api/workspace-files/src/index.ts（0.629） |
| L-011 | exact | 1 | 1 | 1 | ✅ | packages/session-query/session-query-sqlite/src/query.ts | packages/session-query/session-query-sqlite/src/query.ts（0.691） |
| L-012 | exact | 1 | 1 | 2 | ✅ | packages/core/session/src/known-event-types.ts | packages/core/session/src/known-event-types.ts（0.662） |
| L-013 | exact | 1 | 1 | 5 | ✅ | packages/identity/anonymous-user-id/src/index.ts | packages/identity/anonymous-user-id/src/index.ts（0.687） |
| L-014 | exact | 1 | 1 | 3 | ✅ | packages/attachment/attachment-local/src/request-image.ts | packages/attachment/attachment-local/src/request-image.ts（0.624） |
| L-015 | exact | 1 | 1 | 2 | ✅ | packages/ssh/ssh/src/protocol.ts | packages/ssh/ssh/src/protocol.ts（0.683） |
| L-016 | exact | 4 | 4 | — | ✅ | packages/compaction/compaction-tool-result-pruner/src/config.ts | packages/experimental/ptc-runtime-python/py/bootstrap.py（0.571） |
| L-017 | exact | 1 | 1 | 1 | ✅ | packages/hooks/hook-protocol/src/events.ts | packages/hooks/hook-protocol/src/events.ts（0.659） |
| L-018 | exact | 1 | 1 | 1 | ✅ | packages/context/file-reference-local/src/search.ts | packages/context/file-reference-local/src/search.ts（0.634） |
| L-019 | crossfile | 1 | 1 | 2 | ✅ | packages/skill/skill-filesystem/src/index.ts<br>packages/skill/skill/src/index.ts | packages/skill/skill/src/index.ts（0.541） |
| L-020 | crossfile | — | 17 | — | ❌ | packages/spill/spill-policy/src/notice.ts<br>packages/spill/spill-policy/src/index.ts<br>packages/client/ui-tool/src/client/tool/models/terminal-card-model.ts | packages/guard/repeat-tool-reminder/src/index.ts（0.629） |
| L-021 | crossfile | 1 | 1 | — | ✅ | packages/goal/goal/src/index.ts<br>packages/goal/goal/src/fold.ts<br>packages/goal/goal-round-driver/src/index.ts | packages/goal/goal/src/index.ts（0.583） |
| L-022 | crossfile | 2 | 2 | — | ✅ | packages/core/tools/src/index.ts<br>packages/core/agent-loop/src/tool-calls.ts<br>packages/session/session-checkpoint-policy/src/index.ts | packages/api/workspace-controller/src/directory-picker.ts（0.621） |
| L-023 | crossfile | 1 | 1 | 1 | ✅ | packages/settings/settings/src/index.ts<br>packages/settings/settings-file/src/index.ts | packages/settings/settings/src/index.ts（0.627） |
| L-024 | crossfile | — | 15 | — | ❌ | packages/todo/tool-todo/src/types.ts<br>packages/todo/tool-todo/src/index.ts<br>packages/session-query/session-query/src/extraction.ts | packages/fs/tool-fs-search/src/search-core.ts（0.593） |
| L-025 | crossfile | 1 | 1 | — | ✅ | packages/fs/fs/src/types.ts<br>packages/fs/fs-local/src/fsio.ts | packages/fs/fs-local/src/fsio.ts（0.646） |
| L-026 | natural | 1 | 1 | — | ✅ | packages/guard/repeat-tool-reminder/src/index.ts | packages/guard/repeat-tool-reminder/src/index.ts（0.613） |
| L-027 | natural | — | 654 | — | ❌ | packages/fs/fs-observation-policy/src/index.ts | packages/subagent/subagent-codex/src/wire.ts（0.608） |
| L-028 | natural | — | 26 | — | ❌ | packages/context/time-context/src/index.ts | packages/core/agent-loop/src/tool-calls.ts（0.595） |
| L-029 | natural | 5 | 5 | — | ✅ | packages/web/web-fetch-http/src/provider.ts | packages/experimental/webworker-runtime/src/transport/tunnel.ts（0.592） |
| L-030 | natural | — | 80 | — | ❌ | packages/session-query/session-log-export/src/index.ts<br>packages/session-query/session-log-export/src/archive.ts | packages/client/ui-conversation/src/client/contract/snapshot.ts（0.633） |

## 5. 结论：go / no-go

### **GO**

- 判定规则（`EVAL.md` §3.7.1）：`natural` 桶的 `S@5` **上限** ≥ `S5` 的 **0.40** 才继续实施。
- 实测 `natural` 桶 `S@5` 上限 = **0.429**（3/7），**≥ 0.40**（生产排序档位；纯余弦口径下为 0.000，**不是**生产口径）。
- 天花板过线，**值得进入实现**（`T3-08`–`T3-11`），再由 C 组实测真实链路剩余多少（`V1`/`V3`）。
- `crossfile` 桶 `S@5` 上限 = **0.636**（7/11，BM25 基线 0.091 → **+54.5pp**），`exact` = **0.917**（11/12）。
- **`exact` 低于 BM25 的 1.000**，因此向量**不能替换** BM25，只能按 `ADR-16` §2 的「补齐不替换」（RRF 融合）使用——`V2` 要求 `exact@5` 保持 1.000。

### 这个 GO 有多脆

- `natural` 只有 7 条，命中 3 条；**再少一条就跌破 0.40**（Wilson 95% 区间 [0.158, 0.750]）。
- 因此本结论只回答「值不值得继续实现」，**不构成发布批准**；发布与否仍由 C 组的 `V1`/`V3`（α = 0.025）决定。
- 前提条件必须兑现：**向量路径要继承生产的第一层排序档位（非测试优先）**。这是 `T3-09`/`T3-10` 的实现要求，不是可选项。

## 6. 限制与适用范围

- **这是上限，不是落地成绩**：真实链路还要过 RRF 融合、`k` 截断与 `max_tokens` 预算（`EVAL.md` §3.7.1）。对 `natural` 桶（BM25 基线 0.000）向量排序基本决定融合结果，故该上限是**紧的**；对 `exact`/`crossfile`，RRF 融合后的名次可能高于或低于向量单路（BM25 那一路会补位），桶级数字只作参考。
- **样本很小**：`natural` 只有 7 条，Wilson 区间 [0.158, 0.750] 很宽，单条翻转就能移动 0.143。
- **查询侧无词法线索**是真问题，但向量对**中文原问句**的效果依赖模型；本结论只对 `bge-m3` + 本语料 + 这 30 条成立。
- 探针**没有**为「云端后端」背书：`ADR-17` §1.6/§7 要求每个后端各自重跑探针与 L1，云端的 `S5` 需在云端模型上另行判定。

## 7. 复现

```sh
# 探针脚本不进仓库（它不是生产路径）；这里记录命令以便复现
/opt/anaconda3/bin/python /tmp/m5-vector-probe.py \
    --corpus /tmp/dsh-coderag-t3-03-corpus --tasks eval/tasks.jsonl \
    --model bge-m3 --url http://127.0.0.1:11434/api/embed --out docs/m5-vector-probe.md
```

- BM25 基线报告：`/tmp/m5-probe-cache/bm25.json`（由 `python -m dsh_coderag.eval run --expect-golden-version m3-b1` 生成）。
- chunk embedding 分片缓存在 `/tmp/m5-probe-cache/`（`SHARD = 2048`），中断后可续跑。

## 8. 耗时

- 30 条 query embedding：`0.6s`。
- **冷跑（含全量 63046 chunk embedding）实测 `168.5 min`**（Apple M4，Ollama 串行——实测并发不提升吞吐；期间机器睡眠会拉长墙钟时间）。
- 本报告的指标是在**分片缓存命中**后重出的，本次进程只耗时 `1.4s`（未重算 embedding）。

