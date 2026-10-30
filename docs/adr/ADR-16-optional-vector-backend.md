# ADR-16：向量作为**可选后端**（v2.0.0）

> **状态**：已决定（冻结可验收条文）｜ **裁决日期**：2026-09-23 ｜ **生效版本**：**2.0.0**
> **依据**：[`ADR-14`](./ADR-14-semantic-retrieval.md) §10.4（V1–V4）、[`ADR-15`](./ADR-15-defer-semantic-retrieval.md) §3（重启条件）、`PROJECT.md` §1.4（S1–S4）、§6.5（M5 任务表）
> **关联**：`ADR-02`（第一版只做 BM25）、`ADR-13`（标点路由）、`RL-10`、`S-01`、`S-03`、`RL-06`、`RL-08`、`RL-09`
> **取代关系**：**不取代** `ADR-14` 的 R2 判断，也**不撤销** `ADR-15`；它执行的是 `ADR-15` §3 的重启，并把形态固化成可验收条文。

---

> ## 后续更新（2026-09-24，出自 `T5-14`）
>
> **新增一条强制条文：向量召回必须继承生产的排序档位。**
>
> `T5-14` 的探针（数据见 [`docs/m5-vector-probe.md`](../m5-vector-probe.md)）实测：本语料 **38489/63046（61%）的 chunk 来自测试文件**。若向量单路只按余弦排序、不套用生产检索的第一层排序「**非测试路径优先**」（`searcher.TEST_PATH_TIER_SQL` 的六种形态：`tests/**`、`**/tests/**`、`__tests__/**`、`**/__tests__/**`、`*.spec.*`、`*.test.*`），则：
>
> | 桶 | 纯余弦（不可接受） | 生产档位（冻结口径） | BM25 基线 |
> |---|---|---|---|
> | `natural` `S@5` | **0.000** | **0.429** | 0.000 |
> | `crossfile` `S@5` | 0.273 | **0.636** | 0.091 |
> | `exact` `S@5` | 0.833 | **0.917** | **1.000** |
>
> 因此冻结：**向量路的候选排序与 RRF 融合后的最终排序都必须让测试文件排在非测试文件之后**，与 BM25 路径共用同一套档位。这不是可选项——不继承既与生产口径不可比，又会让 `exact` 进一步回退。
>
> - **落点**：`T3-09`（向量召回）与 `T3-10`（RRF 融合）实现时必须兑现；`T3-11` 的 C 组判定与 `T5-16` 的端到端冒烟按此口径验收。
> - **探针结论**：`T5-14` 判 **GO（边际）**——`natural` 上限 0.429 ≥ `S5` 的 0.40（7 条中 3 条，Wilson [0.158, 0.750]）。**这只是"值得实施"，不是发布批准**；发布与否仍由 §7.2 的 `V1`–`V4`（α = 0.025）决定。
> - **`exact` 只有 0.917 < 1.000**：再次确认 §1.2 的「补齐不替换」——向量不得替换 BM25。
> - **边界**：本条只冻结排序档位与探针结论，**不改** §1–§10 的任何原文。

> ## 后续更新（2026-09-25，出自 `T3-11`）：**`V4` 触发 → 向量路径不发布**
>
> C 组（BM25 + 向量 + RRF）已在真实语料上跑完，按 §7.2 的 `V1`–`V4` 逐条判定：
>
> | # | 判据 | 实测 | 结论 |
> |---|---|---|---|
> | `V1` | `natural@5 ≥ 0.40` 且 > B 组 | **6/20 = 0.300**（扩桶后 20 条） | ❌ 未达 |
> | `V2` | `exact@5 == 1.000` 且逐条回归 `== 0` | `0.917`，1 条未豁免回归（`L-015`） | ❌ 未达 |
> | `V3` | C 组 L2 配对符号检验（**α = 0.025**） | **未跑**——`V4` 是「`V1` **或** `V3` 未过即不发布」的析取，`V1` 已定论 | — |
> | `V4` | `V1` 或 `V3` 未过 → **不发布** | `V1` 未过 | ✅ 触发 |
>
> **补充证据（为什么不是"再调调融合就好了"）**：只读原型测过五种融合策略（等权 RRF / 档位门控 / 数据文件档位 / 按分数裁剪 / 四者合并），最好的组合 `natural = 6/20 = 0.300`；
> 而**把 20 条的目标文件在向量排序里的最佳名次直接算出来，落在 top-5 的只有 7 条（7/20 = 0.350）**——
> 即**当前 embedding 表示下的 oracle 上限也不到 0.40**。因此差距只能从 embedding 侧（换模型 / 换输入文本）补，属新的决策，不在本 ADR 范围内。
>
> **发布决定（项目所有者，2026-09-25）**：
> ① 本 ADR 的全部条文**继续有效**，但**没有对应的发布对象**——向量路径不进入 2.0.0；
> ② 2.0.0 **只发布在 GitHub**（tag / release），**不发布到 PyPI、也不发布到 npm**；
> ③ `T5-15`（extra `semantic`）/ `T5-16`（可选安装冒烟）/ `T5-20`（云端实现）/ `T5-22`（云端安全评审）随之**移出 2.0.0 范围**（任务行保留，备将来重启向量线）；
> ④ 2.0.0 的价值主张是**默认路径的实测提升**（13 个任务 × 3 次：任务成功率 `0.282 → 0.821`，中位 token/次 `−8.9%`，每个做对的任务 token `−62.7%`）。
>
> 原始数据：[`docs/eval-report-m3c.md`](../eval-report-m3c.md) §10、[`eval/runs/clean-a3`](../../eval/runs/clean-a3/report.md) / [`clean-b3`](../../eval/runs/clean-b3/report.md)。

---

## 1. 决策

1. **向量检索在 2.0.0 以可选后端形式提供，默认关闭。** 它是一条**补齐路径**，不是默认路径：未配置时引擎的行为与 `1.0.0` 的纯 BM25 **逐条完全一致**。
2. **融合方式是 RRF（k=60）**，只做**补齐、不替换**：`exact` 桶必须保持 `S@5 = 1.000`（`ADR-14` §10.4 的 V2）。
3. **后端冻结为本地 Ollama + `bge-m3`。** 云端 embedding（需要 API key、会把代码文本发到第三方）**不采用**——它同时违反 `S-01`（默认不联网）与 `S-02`（不外发数据）。
4. **依赖冻结为可选 extra `semantic`，其内容只有 `numpy`。** embedding 后端通过 HTTP 调用**本机 Ollama 服务**（不是 Python 依赖）；HTTP 客户端用**标准库 `urllib.request`**，因此**不引入 `httpx`**，也**不引入任何向量数据库**（`ADR-14`：≤10 万 chunk 用暴力余弦）。
5. **`numpy` 不得出现在 `dependencies`、bundle 的 tarball、`scripts/install.sh` 的默认路径与 README 的安装前置条件里。** 这是发布范围约束，不是性能取舍。
6. **向量索引冻结在 `<root>/.coderag/vectors/`**——必须落在工作区内（`S-03`），不得写到工作区之外。
7. **是否发布向量路径服从 `ADR-14` §10.4 的 V1–V4**（V3 用 **α = 0.025**；**V4：C 组不能显著优于 B 组就不发布**）。见 §7。
8. **实施前必须先跑向量天花板探针**（`ADR-15` §3.2 / `T5-14`），**由数据给 go/no-go**；探针若判定 no-go，则 §7 的 V4 直接生效，向量路径不发布。

> **一句话**：默认安装与 `1.0.0` 完全相同；想要语义检索的人显式多装一个 extra、显式打开一个开关；这两件事都不做的人，永远碰不到 numpy，也永远碰不到向量。

> **后续更新（2026-09-23）**：**"云端 embedding 不采用"这一条被 [`ADR-17`](./ADR-17-optional-cloud-embedding.md) 部分取代**——新增与 `ollama` 平级的 `openai` 后端（OpenAI 兼容 `/v1/embeddings`），触发原因是用户要求"可选地对接外部线上模型 API"。
>
> 具体地，**以下四处只对 `ollama` 后端继续有效**：§1.3（"云端不采用"整条）、§3.1 表格里"云端 embedding API → 否决"那一行、§6 的 `SEMANTIC_BACKEND_NOT_LOCAL`（改为只在 `ollama` 被指向远端时触发）、§8.1（"只允许 loopback"的硬限制；`openai` 后端改由 `CODERAG_SEMANTIC_ALLOW_REMOTE=1` 这把第二钥匙把关）。
>
> **其余条文全部继续有效，且对两条后端同等生效**：默认关闭 + opt-in、关闭态逐字节一致、"干净回退"的三条含义、extra 名与内容、向量索引落点、RRF(k=60) 补齐不替换、重试上限、V1–V4（V3 `α = 0.025`、V4 不显著不发布）。**本 ADR 的决策快照性质不变**：以上原文一字未改。

---

## 2. 形态：默认关闭 + opt-in + 干净回退

引擎有三种可观测状态，**由配置决定，不由"后端起没起来"决定**：

| 状态 | 触发条件 | 行为 |
|---|---|---|
| **未启用**（默认） | `CODERAG_SEMANTIC` 未设或不为 `on` | 纯 BM25。**输出与 `1.0.0` 逐字节一致**，不出现任何语义相关字段，不 import `numpy`，不发起任何网络调用 |
| **已启用 + 后端可用** | `CODERAG_SEMANTIC=on` 且 Ollama 可达且模型就绪 | BM25 与向量各自召回，RRF(k=60) 融合；结果仍按源码顺序排列（`ADR-05` 不变） |
| **已启用 + 后端不可用** | 开关为 `on`，但 Ollama 未启动 / 模型缺失 / URL 非本机 | **干净退回纯 BM25**，结果与未启用时逐条一致；同时在结构化状态里写明原因（§6），**不是 `isError`，也不是空列表** |

**"干净回退"的冻结含义**（三条都要满足，`T3-10` 的验收即按此写）：

1. **不改变返回条数**：同一条 query，回退后返回的命中数、路径、行号、顺序与纯 BM25 完全相同；
2. **不改变文本格式**：`status:` 行与命中区块的排版不变，模型侧的解析不受影响；
3. **不报错**：不抛异常、不返回 `isError`、不返回空列表（`RL-06`/`RL-09`）；失败信息只出现在**新增的**结构化字段里。

> **为什么强调"逐字节一致"**：模型可见文本有快照测试（`TESTING.md` §3.5 / M9）。若关闭态也新增一行 `semantic: off`，快照全红、且 `S6`（默认路径零回归）无从判定。**语义信息只在启用态出现。**

---

## 3. 后端与依赖

### 3.1 为什么是本地 Ollama + `bge-m3`

| 候选 | 结论 | 理由 |
|---|---|---|
| **本地 Ollama + `bge-m3`** | **采用** | `ADR-14` 已选型（多语、对中文有效）；进程在本机，代码文本不出机器；对用户是**一次性系统级安装**，不污染 Python 依赖树 |
| 云端 embedding API | **否决** | 需要 API key（`S-01` 默认不联网）、会把代码文本发给第三方（`S-02` 不外发数据） |
| Python embedding 库（`sentence-transformers` 等） | **否决** | 会把 `torch` 之类拉进依赖树（数百 MB），且与"extra 里只有 numpy"的冻结相冲突 |
| 向量数据库（faiss / chroma / lancedb） | **否决** | `ADR-14` 已定：≤10 万 chunk 用暴力余弦；引入向量库是过早优化（`AGENTS.md` §8） |

### 3.2 依赖冻结

```toml
# pyproject.toml（形态，由 T5-15 落地）
[project.optional-dependencies]
semantic = ["numpy>=1.26"]
```

| 冻结项 | 内容 |
|---|---|
| **extra 名** | **`semantic`**（安装：`pip install -e ".[semantic]"`） |
| extra 内容 | **只有 `numpy`** |
| **不得出现在 `dependencies`** | `numpy`、`httpx`、任何 embedding / 向量库 / `torch` |
| **不得出现在 bundle tarball** | 同上（tarball 仍只有 `package.json` / `cordis.patch.yml` / `LICENSE` / `README.md`） |
| **不得成为安装前置** | `scripts/install.sh` 的**默认路径**（`CODERAG_WITH_SEMANTIC` 未设）不得安装任何向量依赖；README 的默认安装步骤也不得提到 Ollama |
| HTTP 客户端 | **标准库 `urllib.request`**——不引入 `httpx`/`requests` |
| 后端服务 | Ollama 是**用户显式安装的系统服务**，不是 Python 依赖，也不是本项目的安装前置 |

**命名冻结**（安装侧）：`CODERAG_WITH_SEMANTIC` —— `scripts/install.sh` 的显式开关，**未设 = 不装**（`1` 才装 extra `semantic`）。

---

## 4. 配置项与环境变量命名（**冻结**）

全部沿用 `CODERAG_*` 前缀（`PROJECT.md` 文首的命名表）。**必填项缺失时报错而非猜测**（`config.py` 的既有约定）；下表的值都是**文档化的默认值**，且都可用环境变量覆盖——`RL-07` 禁止的是**不可覆盖的硬编码**，不是有默认值。

| 环境变量 | 默认 | 作用 | 备注 |
|---|---|---|---|
| `CODERAG_SEMANTIC` | **未设（等价 `off`）** | 总开关；**只有 `on` 才启用** | 其余取值（含 `1`/`true`/`yes`）一律按**关闭**处理并在状态里说明取值非法，**不猜** |
| `CODERAG_SEMANTIC_BACKEND` | `ollama` | 后端 id | 2.0.0 **唯一**支持的取值；其他取值 → 结构化失败（§6） |
| `CODERAG_SEMANTIC_URL` | `http://127.0.0.1:11434` | Ollama 基址 | **必须是 loopback**（`127.0.0.1` / `::1` / `localhost`）；非本机地址**拒绝启用**（§6、§8） |
| `CODERAG_SEMANTIC_MODEL` | `bge-m3` | embedding 模型名 | 需与用户 `ollama pull` 的名字一致 |
| `CODERAG_SEMANTIC_TIMEOUT` | `30` | 单次 HTTP 请求超时（秒） | 后端卡住时必须**超时**而不是永久阻塞（`E-01`：工具调用总预算 60 s） |
| `CODERAG_SEMANTIC_QUERY_TIMEOUT` | `10` | 交互查询路径的**墙钟预算**（秒） | 超时返回 `SEMANTIC_TIMEOUT` 并保留 BM25；必须明显小于宿主的工具调用预算，给模型留一次重试的机会（§11，2026-10-30 增补） |
| `CODERAG_SEMANTIC_BATCH` | `16` | 单次 embedding 请求的文本条数 | 可覆盖（`RL-07`） |
| `CODERAG_SEMANTIC_MAX_CHUNKS` | `100000` | 参与向量化的 chunk 上限 | 超过时**显式失败并报实际数量**，**绝不静默截断**（`RL-08`） |

**配置落点**：`src/dsh_coderag/config.py` 增加一个**独立的** `SemanticConfig`；它**不参与** BM25 路径的任何必填校验，因此默认安装下缺少它不会让引擎启动失败。

> **形状冻结（不冻结实现细节）**：字段名与上表一一对应（`enabled` / `backend` / `url` / `model` / `timeout_s` / `query_timeout_s` / `batch` / `max_chunks`；其中 `query_timeout_s` 按 §11 于 2026-10-30 增补，其余七个保持 2.0.0 的语义）。实现方式（dataclass / 校验顺序 / 错误类型）留给 `T3-08`。

---

## 5. 向量索引落点（`S-03`）

```
<root>/.coderag/
├── index.sqlite3                     # 既有：BM25 索引（T1–T2）
└── vectors/                          # 新增：可选后端的向量索引（2.0.0）
    ├── embeddings.npy                # float32，行序 = chunk_id 升序
    └── manifest.json                 # model / dim / chunk 数 / 逐 chunk 内容哈希 / 生成时间 / 格式版本
```

**冻结条文**：

1. **必须**位于 `<root>/.coderag/` 之内——`<root>` 是本次调用的工作区根，因此向量文件**永远在工作区内**（`S-03`）。
2. **禁止**写入 `~/.cache`、`/tmp`、用户目录或任何工作区之外的路径；**禁止**把向量放进 SQLite 之外的独立全局库。
3. `.coderag/` 已被本项目的 `.gitignore` 模板排除（`S-04`），向量文件随之一并排除；**不得**把 `.npy` 提交进仓库。
4. `manifest.json` 记录**模型名与维度**：模型换了（例如 `bge-m3` → 其他）而维度或语义空间不同时，**必须重新生成**，不得混用旧向量。manifest 与实际请求的模型不一致时按 §6 的结构化失败处理，而不是静默用错的向量。
5. **只有已入库的 chunk 会被 embedding**——三层安全过滤（`AGENTS.md` §4.1）在入库前已经执行，因此被拦下的密钥文件**不可能**出现在向量索引里（`RL-03` 的延伸）。
6. 工作区里加 `.coderagignore` 或删文件后，增量重建遵循既有 `T2-08` 的变更检测；向量索引与 BM25 索引**同源同版本**，不做两套独立的过滤规则。

---

## 6. 失败模式与结构化状态

**总原则**（`RL-06` + `RL-09`）：后端不可用**绝不**变成 `isError`、**绝不**返回空列表、**绝不**静默降级成"看起来正常但少了一半结果"。所有失败都转成带 `status` 与 `code` 的结构化返回值，并且**引擎继续以 BM25 工作**。

| 冻结 code | 触发条件 | 引擎行为 |
|---|---|---|
| `SEMANTIC_BACKEND_UNAVAILABLE` | `CODERAG_SEMANTIC=on` 但 Ollama 不可达 / 模型未 pull | 回退 BM25，`status` 仍为正常检索状态，附该 code 与可操作提示（启动 Ollama、`ollama pull bge-m3`） |
| `SEMANTIC_BACKEND_NOT_LOCAL` | `CODERAG_SEMANTIC_URL` 不是 loopback | **拒绝启用**后端（安全拒绝），回退 BM25，提示只允许本机地址 |
| `SEMANTIC_BACKEND_UNSUPPORTED` | `CODERAG_SEMANTIC_BACKEND` 不是 `ollama` | 同上：拒绝启用并回退 |
| `SEMANTIC_EMBED_FAILED` | 单次 embedding 请求超时 / 非 2xx / 响应格式非法 | **重试上限 2 次**后放弃本次向量召回，回退 BM25（**禁止无限重试**，`AGENTS.md` §8） |
| `SEMANTIC_INDEX_TOO_LARGE` | chunk 数 > `CODERAG_SEMANTIC_MAX_CHUNKS` | **显式失败并报告实际数量**，不截断、不部分向量化（`RL-08`） |
| `SEMANTIC_INDEX_MISSING` | 已启用但 `vectors/` 不存在 | 提示先跑 `code_index`；本次仍用 BM25 返回结果 |
| `SEMANTIC_MODEL_MISMATCH` | `manifest.json` 的模型/维度与当前配置不一致 | 提示需要重建向量索引；本次仍用 BM25 |

**这些 code 的登记方式**：`ADR-16` 是它们的**唯一权威**（名字与语义以上表为准）。这七个码已由实现任务 `T3-08`–`T3-11` 同步进 `src/dsh_coderag/types.py` 的 `ErrorCode` 与 `tests/test_types.py` 的逐项断言；`T5-05` 不改 `PROJECT.md` §5.6 与 `types.py`，以免在实现落地前制造文档/代码不一致。后续新增的码（如 §11 的 `SEMANTIC_TIMEOUT`）不改这十个码，见 §6 末段的增补说明。

**重试与超时**：任何重试都**有上限**（最多 2 次），且诊断信息必须可操作（哪个 URL、哪个模型、超时多少秒）。

**查询路径的增补（2026-10-30，§11 / `T8-05`）**：交互检索**不重试**——它已经有面向调用方的墙钟预算（默认 `CODERAG_SEMANTIC_QUERY_TIMEOUT=10` 秒），重试只会把"慢"变成"更慢"。预算耗尽时返回**扩展码** `SEMANTIC_TIMEOUT`，与上面的七个冻结码一样走 `SemanticError` → `SemanticNotice` → 回退 BM25 的通道；它**不**写进 `types.py` 的 `ErrorCode` 枚举（与 `T8-02` 的 `SEMANTIC_REDIRECT_REFUSED` 同一手法：`str` Enum + `cast`，消费方只读 `.value`），因此 §6 的十个码不被改动。`SEMANTIC_EMBED_FAILED` 仍然覆盖**非预算**的失败（连接被拒、非 2xx、响应非法）。

---

## 7. 发布范围与验收判据（v2.0.0）

### 7.1 发布范围

| 项 | 冻结条文 |
|---|---|
| 版本 | 默认安装的形态**不变**：`dependencies` 仍只有 `mcp` / `tree-sitter` / `tree-sitter-language-pack` / `pathspec` |
| 两段式安装 | 默认：`pip install -e .` + `dsh plugin add .`（与 1.0.0 相同）；可选：`CODERAG_WITH_SEMANTIC=1 bash scripts/install.sh` 或 `pip install -e ".[semantic]"` |
| tarball | 不含任何向量/embedding 依赖、不含 JS 入口（既有 `T4-01` 结论不变） |
| 默认路径零回归 | 未配置 `CODERAG_SEMANTIC` 时，逐条结果与 `1.0.0` 一致（对应 `S6`，由 `T5-07` 登记进 `PROJECT.md` §1.4） |
| 语义路径成功标准 | `natural` 桶 `S@5` 的阈值（对应 `S5`，同样由 `T5-07` 登记） |

### 7.2 V1–V4（逐条冻结，引用 `ADR-14` §10.4）

| # | 判据 | v2.0.0 的落地判定 |
|---|---|---|
| **V1** | 主成功判据是 **`natural` 桶 `S@5` 的提升**，不是端到端 | 比对 B 组与 C 组的 L1 分层指标，`natural` 桶为准；端到端已由纯词法达成（`ADR-15` §2.1），不作为发布判据 |
| **V2** | **`exact` 桶必须保持 1.000**，任何单条回归即失败 | 由 `T3-12` 的 `scripts/eval-gate.sh` 执行：`回归条数 = L1 逐 query 回归 + L2 用例级回归`，**不为 0 即不发布** |
| **V3** | C vs B 若做端到端对比，按 `EVAL.md` §2.6 第二轮把 **α 收紧到 0.025** | C 组命令带 `--group eval-coderag-vector`（`T3-11` 的验收命令）；报告必须显式声明这是**第二次检验**并用 0.025 |
| **V4** | **C 组不能显著优于 B 组，就不发布向量路径** | 若 V1 未达阈值、或 V3 的对比未达 α=0.025 的显著，则**不发布**：extra 与代码保留在仓库，但 README 与 CHANGELOG 按"未启用/未发布"表述，且不删除已建的向量能力 |

### 7.3 前置顺序（不可跳过）

```
T5-14 天花板探针（go/no-go）
   └─ go ─→ T3-08 → T3-09 → T3-10 → T3-11（C 组 + V1–V4 判定）→ T5-15/T5-16/T5-17
   └─ no-go ─→ 到此为止：不发布向量路径（V4 直接生效），M5 以文档与探针结论收口
```

**探针是决定来源**：它给出 `natural`/`crossfile` 的 `S@5`/`MRR` **上限**。上限都不足以达标时，全量实施没有意义。

---

## 8. 数据与安全

| # | 冻结条文 |
|---|---|
| 1 | **只允许 loopback**：`CODERAG_SEMANTIC_URL` 非本机地址时拒绝启用（§6）。这是防止"把用户代码发给远端"的最后一道闸 |
| 2 | **不外发遥测**（`S-02`）：除了发往本机 Ollama 的 chunk 文本，不发送任何东西；不发路径、不发统计、不发文件名 |
| 3 | **发送内容仅限已入库 chunk 文本**：被三层过滤拦下的文件从来没有 chunk，因此不可能被 embedding（`RL-03`） |
| 4 | **向量文件落在 `<root>/.coderag/`**（`S-03`/`S-04`），不进仓库、不出工作区 |
| 5 | **默认不联网**（`S-01`）：未启用时**零**网络调用；启用时也只有 loopback 一种目标 |
| 6 | **日志不出现代码内容**（`S-05`）：后端失败只记 URL / 模型 / 状态码 / 耗时，不记文本 |
| 7 | **内存约束**：暴力余弦的规模上限由 `CODERAG_SEMANTIC_MAX_CHUNKS` 显式约束，不靠"应该够用" |

---

## 9. 诚实的限制

1. **探针可能给出 no-go。** 那时本 ADR 的 §7.2 V4 直接生效——**不发布**。这不是失败，是这条决策的正常出口。
2. **Ollama 是用户要自己装的系统服务**（另有约 1.2 GB 的 `bge-m3` 下载）。默认安装的用户**感知不到**它，但想用语义检索的用户要付这个代价——这正是把它做成 opt-in 的原因（`ADR-15` §2.4）。
3. **提升量级未知。** 在探针与 `T3-11` 的数据出来之前，本 ADR 只冻结**形态**，不承诺收益。`ADR-15` §2.3 已说明 `S1` 的门槛高于"三桶各自达标"。
4. **向量只影响 L1（静态检索质量），不影响端到端的主要瓶颈。** `ADR-14` §10.5 已指出端到端最大的可改进项是**工具采纳（R5）**，与向量正交。
5. **`natural` 桶只有 7 条**，`S@5` 的 Wilson 区间很宽；任何"提升 X%"的表述都必须带区间（`EVAL.md` §2.6）。
6. **本 ADR 不改变 `S1`/`S2` 当前未达标的事实**（`= 0.433` / `= 0.313`）；它只冻结"补齐路径怎么进、什么时候不进"。
7. **`SEMANTIC_*` 的 code 已进入 `ErrorCode`**（`T3-08`–`T3-11` 已落地，见 §6）；后续新增码（如 §11 的 `SEMANTIC_TIMEOUT`）按 §6 的扩展手法处理——`str` Enum + `cast`，不改那十个冻结码。
8. **查询预算换来的是"慢而不超时"，不是"快"**（§11）：冷启动的首次查询仍会花掉预算（默认 10 s）并只拿到 BM25 结果；预热只在**同一进程**内有效（CLI 每次都是新进程），而且后台加载仍受 `CODERAG_SEMANTIC_TIMEOUT` 约束——把它设得比模型冷加载时间还短时，预热永远完不成。


---

## 10. 与其它决策的关系

| 决策 | 关系 |
|---|---|
| `ADR-02`（第一版只做 BM25） | **一致**：2.0.0 的**默认路径**仍是纯 BM25；向量是可选后端 |
| `ADR-14`（R2 命中 → 引入向量） | **执行本 ADR 的方式落地**；R2 的事实判断不变，V1–V4 被逐条继承（§7.2） |
| `ADR-15`（暂缓语义检索） | **它是本 ADR 的执行**：`ADR-15` §3 的四条重启条件被逐条兑现（形态 / 探针先行 / V1–V4 / `T3-11` 验收命令换成自建 runner） |
| `RL-10`（决策门前禁止 embedding 依赖） | 原始禁令因 `T3-07` 已通过而**完成使命**（`ADR-15` §4）。`T5-06` 将其改写为**发布范围约束**："向量不得进入默认路径或必需依赖；未配置必须干净回退 BM25"——本 ADR §1.5/§2 正是那条红线的可验收形式 |
| `S-01` / `S-02` / `S-03` | §8 逐条落地：默认不联网、不外发数据、索引不出工作区 |
| `RL-06` / `RL-08` / `RL-09` | §6 逐条落地：不空列表、不静默截断、不冒泡 `isError` |
| `RL-07` | §4 的可覆盖默认值（不硬编码批大小与规模上限） |
| `S5` / `S6` | 由 `T5-07` 登记进 `PROJECT.md` §1.4：`S5` = 开启时 `natural` 桶 `S@5` 阈值，`S6` = 默认路径零回归 |
| `E-01`（工具调用 60 s 预算） | §11 增补：查询路径的墙钟预算（默认 10 s）必须明显小于宿主预算；`call_tool` 走 `asyncio.to_thread`，一次慢检索不再冻结整个 MCP 会话 |

---

## 11. 2026-10-30 增补：查询路径的预算与预热（`T8-05`）

### 11.1 触发事实

用户报告：在 Windows + RTX 3070 + 本地 Ollama + `bge-m3` 的机器上，通过设置页开启向量化后，**中文自然语言/疑问句检索**频繁收到 DSH 的 `tool call timed out`（该机器的 `toolCallTimeoutMs = 30`），且响应里**没有** `semantic: {code: ...}`——说明调用方在服务端给出结构化 notice 之前就放弃了。两个对照查询：

| 查询 | 纯 BM25 | 开启向量层 |
|---|---|---|
| `向量增强层未开启，自动回退BM25` | 快速命中 | — |
| `决定向量增强层关闭时的自动回退行为代码在哪？` | — | **大概率超时** |

### 11.2 取证与实测（本机 macOS 26.4 / Ollama 0.34.3 / `bge-m3` 1.2 GB）

| # | 观察 | 数值 |
|---|---|---|
| 1 | 冷加载 embedding（首次请求；`ollama ps`：673 MB / 100% GPU / context 4096） | **15.94 s** |
| 2 | 冷启动后的第一条 `search()` | **16.48 s** |
| 3 | 热查询（模型已加载） | **0.32–0.38 s**（walk 0.28 s + embed 0.02 s + `load_index` 0.001 s） |
| 4 | 建 1,705 chunk 的向量索引（batch 16） | **138.5 s**（≈81 ms/chunk） |
| 5 | `CODERAG_SEMANTIC_TIMEOUT=5` + 模型已卸载：每条查询 | **15.3 s**（3 × 5 s），连跑 3 条后 `ollama ps` 仍为空 |
| 6 | 构建期间并发查询 | 0.5–2.7 s，无超时 |
| 7 | 本次修复后（模型已卸载，单进程连跑 3 次） | 10.32 s（`SEMANTIC_TIMEOUT`）→ 6.28 s（无 notice）→ 0.35 s（无 notice） |

第 5 行是根因的决定性证据：旧的 `_post_with_retry` 把**冷加载**当成可重试失败，最多 3 次 × 单次超时（默认 30 s = 90 s），而每次超时都会取消正在进行的加载——**模型永远预热不起来**。客户端预算（30 s）通常在服务端第 2–3 次尝试之间到期，于是用户看到的是传输层超时，而不是结构化的 `SEMANTIC_*`。第 7 行是修复后的同一实验：第一次用完预算后**不取消**请求，后台加载完成后第二次查询即转为热路径。

### 11.3 决策（`T8-05`）

查询路径与索引路径**分开**处理：

1. **只尝试一次**：查询有面向调用方的截止时间，重试只会更慢（索引路径保持 §6 的最多 2 次重试）。
2. **先验索引，再发请求**：`validate_embedding_backend` → `load_index` → `embed_query`。配置错误仍先于索引错误报告（`SEMANTIC_BACKEND_UNSUPPORTED` 不被 `SEMANTIC_INDEX_MISSING` 掩盖），而没有向量索引时**不再**先付一次 embedding 请求。
3. **墙钟预算**：`CODERAG_SEMANTIC_QUERY_TIMEOUT`（默认 10 s，正整数，可覆盖）从进入语义分支起计时（包含 `load_index`）；HTTP 层仍用 `CODERAG_SEMANTIC_TIMEOUT`（默认 30 s），**必须大于**预算——否则预算到点会切断正在加载的请求，预热失效。
4. **超时不取消，后台继续**：`embed_query` 在 daemon 线程里跑请求；预算到点的主线程抛 `SEMANTIC_TIMEOUT` 并回退 BM25，线程继续直到加载完成（日志 `semantic_query_warmup_completed`）。选择这一条而不是取消，是因为"取消"正是旧行为永远预热不起来的原因。
5. **不阻塞事件循环**：`server.call_tool` 用 `asyncio.to_thread` 调 `_dispatch`，一次慢检索不会冻结同一 MCP 会话里的其它工具调用。

### 11.4 验收（可复现）

```console
$ /opt/homebrew/bin/ollama stop bge-m3          # 确保模型未加载
$ CODERAG_SEMANTIC=on CODERAG_SEMANTIC_QUERY_TIMEOUT=10 .venv/bin/python -
# 同一进程内连续三次 search()，同一句中文疑问句
run=1 elapsed=10.32s hits=5 semantic=SEMANTIC_TIMEOUT
run=2 elapsed=6.28s hits=5 semantic=None
run=3 elapsed=0.35s hits=5 semantic=None
{"level": "warning", "event": "semantic_query_timeout", "duration_ms": 9982.25, "url": "http://127.0.0.1:11434/api/embed", "model": "bge-m3", "budget_s": 9.973115083000266}
{"level": "info", "event": "semantic_query_warmup_completed", "duration_ms": 16224.08, "url": "http://127.0.0.1:11434/api/embed", "model": "bge-m3"}
```

第 1 次用完预算即返回（BM25 结果照常、带 `SEMANTIC_TIMEOUT`），后台加载在 16.2 s 完成；第 2 次赶在加载完成时命中（6.28 s），第 3 次为热路径 0.35 s。单元测试覆盖单次尝试、预算映射、后台线程不被取消、事件循环不被阻塞（`tests/test_embed.py` / `tests/test_rrf.py` / `tests/test_server.py` / `tests/test_render.py`）。

### 11.5 被否决的方案

| 方案 | 否决理由 |
|---|---|
| 只把 `_dispatch` 放进线程 | 解决级联，不解决单次查询 90 s 与冷启动永远失败 |
| 只加预算并取消请求 | 每次冷启动都从头开始，用户永远等不到一次成功 |
| 把 `CODERAG_SEMANTIC_TIMEOUT` 默认值降到 10 s | 索引批次需要 30 s 级余量；冷加载 16 s 也会被这个值切断 |
| 查询向量缓存 | 实测收益 < 0.2 s，且不解决冷加载（`T3-12` 的缓存只服务索引批次） |
| 强制 `keep_alive` 常驻模型 | 把约 673 MB 显存常驻强加给所有用户；Ollama 自带的 5 分钟 keep-alive 已足够 |

### 11.6 回滚

删除 `config.py` 的 `query_timeout_s` / `ENV_SEMANTIC_QUERY_TIMEOUT`，把 `searcher._semantic_candidates` 恢复为"先 `embed_texts` 再 `load_index`"，删除 `embed.embed_query` 与 `SEMANTIC_TIMEOUT`，把 `server.call_tool` 改回同步调用；测试与本节一起删除，`ADR-16` §4/§6 的增补段落同步撤回。默认路径（`CODERAG_SEMANTIC` 未设）的行为不受影响。

### 11.7 仍未验证

- **Windows 现场**：本节数值全部来自 macOS；用户环境的 `toolCallTimeoutMs = 30`、Windows 上的 `load_index` / `walk_with_report` 开销与 Ollama 冷加载时间尚未测量。
- **多客户端并发**：同一进程内多个并发查询会各自启动一个加载请求，Ollama 的排队行为未测量。
- **模型侧呈现**：目前只验证了 `render._format_semantic_notice` 的文本与 MCP 的返回值；在真实 DSH 会话里模型读到该 notice 后的重试行为未复跑。
