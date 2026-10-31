# L1 43 条检索评测：云端 qwen3.7 vs 本地 bge-m3（2026-10-31）

## 口径

- 评测集：`eval/tasks.jsonl`，43 条（exact 12 / crossfile 11 / natural 20），`golden_version=m3-b3`。
- 语料：`/Users/vermi/projects/dsh`，HEAD `ddefc45`，索引 3,967 文件 / 63,046 chunks。
- 纯检索层：直接调 `searcher.search(root, query, k=5)`，不启动 agent、无提示词，因此**没有「强制变体」**；`trials=3` 以三次独立完整运行执行。
- 向量库：`~/projects/dsh/.coderag/vectors`，`model=qwen3.7-text-embedding`、`dim=1024`、`chunk_count=63046`（用户于 2026-10-30 15:26 UTC 重建）。
- 云端配置：`CODERAG_SEMANTIC=on`、`BACKEND=openai`、`URL=.../compatible-mode/v1`、`ALLOW_REMOTE=1`、`QUERY_TIMEOUT` 默认 10 s。
- 命令：

```bash
for i in 1 2 3; do
  python -m dsh_coderag.eval run --tasks eval/tasks.jsonl \
    --root /Users/vermi/projects/dsh --expect-golden-version m3-b3 \
    --out eval/runs/l1-cloud-$i.json
done
env -u CODERAG_SEMANTIC python -m dsh_coderag.eval run --tasks eval/tasks.jsonl \
  --root /Users/vermi/projects/dsh --expect-golden-version m3-b3 \
  --out eval/runs/l1-bm25-now.json
```

## 三次运行

三次命中数均为 30/43，逐条命中与 rank 完全一致（检索确定性成立）：

```
hit counts per run: [30, 30, 30]  identical results: True
```

## 总体

| 配置 | 命中@1 | @3 | @5 | S@5 | Wilson 95% | MRR | token 中位 | 平均延迟 |
|---|---|---|---|---|---|---|---|---|
| BM25（本次重跑） | 8 | 11 | 13 | 0.302 | [0.186, 0.451] | 0.219 | 2,876 | 0.233 s |
| bge-m3 + RRF | 2 | 9 | 19 | 0.442 | [0.304, 0.589] | 0.170 | 2,134 | 0.364 s |
| **qwen3.7 + RRF** | 3 | 9 | **30** | **0.698** | [0.549, 0.814] | **0.243** | 2,000 | 0.541 s |

配对 McNemar（11 条 gain、0 条 loss）：精确双侧 p = 2 × 2⁻¹¹ ≈ **0.00098**。

## 分桶

| 桶 | BM25 @5 | bge-m3 @5 | qwen3.7 @5 |
|---|---|---|---|
| exact (12) | 12 | 11 | 11 |
| crossfile (11) | 1 | 5 | **10** |
| natural (20) | 0 | 3 | **9** |

## 逐条变化（qwen3.7 vs bge-m3）

- **新命中（11）**：L-006、L-008、L-022、L-023、L-024（crossfile）；L-009、L-029、L-032、L-033、L-040、L-043（natural）。
- **名次提升（4）**：L-007（crossfile 5→4）、L-025（crossfile 5→4）、L-026（natural 5→4）、L-017（exact 2→1）。
- **退步 / 丢失：0 条**。
- 仅剩的 exact 失败仍是 L-015（BM25 rank 3 → 向量 miss），与 bge-m3 相同，来自 RRF 融合压 top-1，而非模型能力。

## 延迟

| 配置 | 总量 | 均值 | p50 | p95 | max |
|---|---|---|---|---|---|
| bge-m3 | 15.66 s | 0.364 s | 0.365 s | 0.371 s | 0.380 s |
| qwen3.7 | 23.26 s | 0.541 s | 0.475 s | 0.533 s | 2.668 s |

延迟增加来自每次查询的云端 embedding 往返（约 +0.18 s/查询，首次含 TLS/冷启动 2.67 s）；无任何 `SEMANTIC_*` 回退，43/43 `status=ready`。

## 结论

1. 在完全相同的 43 条 golden 集上，云端 qwen3.7 把 top-5 召回从 19/43 提到 30/43（+11 条，0 条丢失，p≈0.001），主要收益在 crossfile（+5）与 natural（+6）。
2. MRR 从 0.170 升到 0.243；但命中@1 仅 2→3，问题仍是 RRF 把精确命中压后——exact 桶与 bge 持平（11/12），未解决 L-015。
3. 代价是查询延迟从 0.364 s 升到 0.541 s（+49%）与云端费用（每 43 条查询约 1–2 千 token，可忽略；主要成本是用户已支付的一次全量重建约 ¥5.4）。
4. 限制：bge-m3 基线来自同日 20:2x 的同一套任务/语料/代码（HEAD `7057c1c`，此后无代码改动），未在本次重跑（重建 bge-m3 向量约需 85 分钟）；L1 无 agent 与提示词，故不涉及「强制变体」；trials=3 三次结果完全一致，统计功效来自 43 条配对样本而非重复运行。
