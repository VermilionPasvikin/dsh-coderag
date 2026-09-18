# M2 结项记录：DSH 仓库端到端索引与检索

> 依据 PROJECT.md 的 T2-17。在真实大仓库（DSH 参考源码）上跑一次完整索引与检索，
> 记录耗时与质量。下列数字都是**实际观测**，不是预期。
>
> 环境：forBSH（Python 3.10.21，SQLite 3.53.4/FTS5），tree-sitter 0.25.2 +
> tree-sitter-language-pack 0.13.0，tree-sitter 自适应并发（本机 workers=8）。
> 语料：DSH 参考源码 commit `0d1f50007f`（0.1.6-alpha.1），3063 个 `.ts` 文件。
> 为遵守 RL-01 / S-03，**不**在参考检出内写索引：用 `rsync`（排除 `.git`、
> `node_modules`）复制到临时目录后再索引，参考检出保持原样。

## 索引结果

命令：`dsh-coderag index <corpus>`（复制目录）

```
indexed 3074 files, 51230 chunks into <corpus>/.coderag/index.sqlite3
```

`last-index.json` 审计（`docs` 目录不计入；`.coderag/` 被忽略规则排除）：

```json
{
  "files": 3074,
  "chunks": 51230,
  "skipped": { "count": 3, "reasons": { "secret_file": 3 } },
  "redacted": { "count": 2 },
  "duration_ms": { "walk": 188.6, "prepare": 2066.5, "write": 1034.3, "cleanup": 1.2, "total": 3299.0 }
}
```

| 指标 | 全量首建 | 二次（增量） |
|---|---|---|
| 文件 | 3074 | 3074（0 chunk 写入） |
| chunk | 51230 | 0 |
| 墙钟 | **3.42 s** | **0.47 s** |
| 审计 total | 3299.0 ms | 393.8 ms |
| 索引库 | — | **112 MB** |

阶段耗时（首建）：prepare 2066.5 ms（62.6%）> write 1034.3 ms（31.4%）> walk 188.6 ms。
解析（tree-sitter 分块 + 密钥扫描）是主要成本，SQLite 写入次之。

stderr 是合法 JSON Lines（节选）：

```
{"ts":..., "level":"info", "event":"index_start", "task_id":null, "duration_ms":null, "root":"..."}
{"ts":..., "level":"info", "event":"index_done", "task_id":null, "duration_ms":3298.96, "files":3074, "chunks":51230, "skipped":3, "redacted":2}
```

## 5 个真实问题的检索结果

对每个问题先跑**纯中文原问句**，再跑**模型常用的标识符改写查询**（M1 观察 5 的行为），
取 top-5，判断正确文件是否命中。

| # | 真实问题 | 实际查询 | 正确文件 | 名次 | 结果 |
|---|---|---|---|---|---|
| Q1 | MCP 工具调用的默认超时是多少 | `toolCallTimeoutMs connection` | `packages/mcp/mcp-client/src/index.ts` | 4/5 | ✅ |
| Q2 | stdio 子进程会清洗哪些环境变量 | `scrubbedParentEnv transport` | `packages/mcp/mcp-client/src/transport.ts` | 1/5 | ✅ |
| Q3 | 文件沙箱有哪些权限模式 | `sandbox-policy mode` | `packages/sandbox/sandbox-policy/src/session-mode.ts` | 2/5 | ✅ |
| Q4 | persona 如何注入 system prompt | `persona systemPrompt` | `packages/preset/persona/src/index.ts` | 1/5 | ✅ |
| Q5 | 会话输出过长时如何 spill | `spill store` | `packages/spill/spill-local/src/store.ts` | 1/5 | ✅ |

**5/5 命中正确文件**（出口判据要求 ≥4）。但**5 个纯中文原问句全部返回 `status: empty`**
（见观察 3）。

## 具体观察

### 观察 1：3074 文件 / 51230 chunk 全量索引 3.42 s
- prepare 阶段占 62.6%，说明成本在 tree-sitter 解析与分块，而非 SQLite。
- 平均约 17 个 chunk/文件、约 15.5k chunk/s（8 workers）。
- 结论：M2 之后首次索引大仓库是秒级，符合 60 s 工具超时的异步化设计（ADR-04）。

### 观察 2：增量索引 0 chunk / 0.47 s，幂等生效
- 第二次 `index` 输出 `0 chunks`，审计 total 393.8 ms；文件哈希未变即整文件跳过（T2-08）。
- 结论：重复索引成本只与 walk + 哈希有关，与 chunk 数无关。

### 观察 3：纯中文自然语言查询 5/5 返回 empty，标识符改写后 5/5 命中
- 例：`工具调用默认超时` → `status: empty`；`toolCallTimeoutMs connection` → 命中。
- 根因：`_build_match` 把查询切成 bigram/词后**全部作为必须命中的短语（AND）**，中文
  bigram 在英文源码里几乎不存在；且缺少精度/召回双模式与停用词/标点路由。
- 结论：这正是 T2-19（分词器语义、标点路由、召回兜底）要解决的；也再次印证 M1 观察 5
  —— 模型必须把中文问题改写成含英文标识符的查询。

### 观察 4：测试文件与实验包在 BM25 中压过实现文件
- Q1 的 top-3 是 `experimental/computer-use-*` 与 `*.spec.ts`；正确实现 `mcp/mcp-client/src`
  只排到第 4。Q3 若不写 `sandbox-policy` 前缀，top-5 全是 `*.spec.ts`。
- 原因：测试/实验文件中相关标识符出现更密集，BM25 只看词频与长度；我们没有路径/源码加权。
- 结论：M2 的「选谁」仍是纯 BM25；**过滤 `tests/` 或对 `src/` 加权**是可考虑的改进（T3 归因）。

### 观察 5：单次检索约 180 ms，主要是 skip 报告触发的重新 walk
- 5 条查询的 `search()` 实测 176–191 ms。FTS 本身很快；延迟来自 T2-07 方案 A 在每次
  检索时重新 `walk_with_report`（3074 文件的 rglob + pathspec 匹配）。
- 结论：功能正确但对大仓库偏慢。T2-07 的「按当前 walk 上报」是权宜；把 skip 统计持久化
  （ADR-09 / `last-index.json`）可把每次检索的 walk 去掉。

### 观察 6：安全过滤在真实仓库上生效
- `skipped: {secret_file: 3}`、`redacted: {count: 2}`：DSH 源码里确有被文件名黑名单与
  内容正则命中的文件/chunk，均未入库，且 stdout 全程为空。
- 结论：RL-03 / RL-04 在 3000+ 文件规模上验证。

### 观察 7：索引库 112 MB，顺序保持与 token 预算生效
- 51230 chunk 的 `chunks` + `chunks_fts` 约 112 MB（含 WAL/索引），约 2.2 KB/chunk。
- 检索结果按 `(path, start_line)` 输出（ADR-05），`max_tokens` 默认 4000 时单条长 chunk
  （如 tool-cordis 的 api-catalog 有 3000+ 行）会占满预算并触发省略提示。

## 开发期发现并修复的两个依赖阻断（T2-01 / T2-03）

1. **`tree-sitter-language-pack` 1.20.0 离线不可用**：wheel 不含 grammar，运行时从 GitHub
   Release 下载（沙箱拒绝写 home 缓存 + 请求 timeout）。改为钉 `>=0.13,<0.14`（最后一个
   打包 grammar 的 abi3 wheel）。
2. **`tree-sitter` 0.26.0 与 language-pack 0.13 不兼容**：释放大 `Tree` 时段错误，1000 行
   函数解析必崩。改为钉 `>=0.25.2,<0.26`（与 0.13 的构建线一致），`tests/fixtures/oversized`
   与 DSH 大仓库均通过。

## 已知限制与未验证事项

- 本记录是**单机、单语料、纯词法**观测；无人工标注的 ground truth，「命中正确文件」由人工判断，
  不是 `Success@k`（T3 才做量化评测）。
- 语料是 DSH 参考源码的**复制**（内容一致），不是原地索引；这是为满足 RL-01/S-03 的取舍。
- 中文自然语言查询依赖模型改写（观察 3）；召回模式、标点路由、停用词可检索属 T2-19。
- 每次检索的 ~180 ms 含 T2-07 的重新 walk；persist skip 统计后可显著下降（观察 5）。
- 测试/实验文件会与实现文件竞争排名（观察 4），M2 未做路径/源码加权。
- 日志与审计中的 `task_id` 目前为 `null`（`index_sync` 不知道 taskman 的任务 id）。
