# ADR-17：向量后端的**云端可选形态**（OpenAI 兼容 embeddings）

> **状态**：已决定（冻结可验收条文）｜ **裁决日期**：2026-09-23 ｜ **生效版本**：**2.0.0**
> **依据**：用户需求变更（2026-09-23）：向量后端除本地 Ollama 外，还需**可选**支持调用外部线上模型 API；并要求把安全风险写进配置处、README 与一切配置/说明书性质的文件
> **关联**：[`ADR-16`](./ADR-16-optional-vector-backend.md)（被本 ADR **部分取代**）、[`ADR-14`](./ADR-14-semantic-retrieval.md) §10.4（V1–V4）、[`ADR-15`](./ADR-15-defer-semantic-retrieval.md) §3、`RL-02`、`RL-10`、`S-01`、`S-02`、`S-05`、`E-02`
> **取代关系**：**只取代 `ADR-16` 里"云端 embedding 一律不采用"这条**（§1.3 / §3.1 的云端行 / §6 的 `SEMANTIC_BACKEND_NOT_LOCAL` / §8.1 的 loopback 硬限制）。`ADR-16` 的其余条文（默认关闭、干净回退、extra 名、索引落点、RRF、V1–V4）**全部继续有效**，云端后端与本地后端**受同一套条文约束**。

---

## 1. 决策

1. **新增第三个可选后端：`openai`**——任何**兼容 OpenAI `/v1/embeddings` 协议**的线上服务（OpenAI、Azure OpenAI、SiliconFlow、DashScope 兼容模式、自建 vLLM/TEI 等）。它与 `ollama` **平级、互斥、都默认关闭**。
2. **形态与本地后端完全对称**：`CODERAG_SEMANTIC=on` 才启用；未配置时逐字节回退纯 BM25；失败一律回退 BM25 并给结构化状态；融合仍是 RRF(k=60)、只补齐不替换。
3. **双重开关**：把后端指向**非 loopback 地址**需要**两个**条件同时成立——`CODERAG_SEMANTIC=on` **且** `CODERAG_SEMANTIC_ALLOW_REMOTE=1`。缺后者一律拒绝启用。这是防止"本地配置被改一个 URL 就把代码发出去"的硬闸。
4. **Key 只从环境读**：`CODERAG_SEMANTIC_API_KEY` 必须是运行时环境变量，**绝不**写进 `cordis.patch.yml` 的字面值、README 示例、测试 fixture、日志或错误信息（`RL-02`）。
5. **风险声明必须随每一处配置出现**：凡出现"启用云端后端"的位置——`cordis.patch.yml` 的注释、README 的云端小节、`config.py` 的配置说明、本 ADR、任何示例——都必须带§5 那段风险声明。缺一处视为文档缺陷（`AGENTS.md` 的 `D-08`）。
6. **每个后端各自过判据**：`S5`（`natural` 桶 `S@5 ≥ 0.40`）与 `V1–V4` 由**实际启用的那个后端**独立满足。**不得**用本地后端的探针结果替云端背书，反之亦然。
7. **默认路径不变**：两条后端都不得进入 `dependencies`、tarball、`install.sh` 默认路径或 README 安装前置（`RL-10`）。

---

## 2. 为什么冻结 OpenAI 兼容协议，而不是各家的 SDK

| 候选 | 结论 | 理由 |
|---|---|---|
| **OpenAI 兼容 `/v1/embeddings`** | **采用** | 一份实现覆盖多家（改 `URL` + `MODEL` 即可换供应商/换模型），完全满足"可选地对接不同模型"；请求体只有 `{"model", "input"}`，响应只有 `data[].embedding`，用**标准库 `urllib.request`** 就能发——**继续不引入任何厂商 SDK、不引入 `httpx`** |
| 各厂商官方 SDK | 否决 | 每个供应商一个依赖 = 依赖树随"支持几家"线性膨胀；且与 `ADR-16` §3.2 冻结的"HTTP 客户端走标准库"冲突 |
| 只支持 OpenAI 一家 | 否决 | 与本次需求（可选部署不同模型）不一致；兼容协议是免费的额外覆盖 |

**响应解析的容错**：只依赖 `data[i].embedding` 与 `data[i].index`；缺 `usage`、多返回字段都不算失败。返回的**维度以实际向量长度为准**并写进 `manifest.json`——因此换模型不需要改代码，只需要重建向量索引（`ADR-16` §5.4）。

---

## 3. 形态：与本地后端对称，唯一差异是"数据出机器"

| 状态 | 触发 | 行为 |
|---|---|---|
| 未启用（默认） | `CODERAG_SEMANTIC` 未设或不为 `on` | 纯 BM25，输出与 `1.0.0` 逐字节一致；**零网络调用**；不 import `numpy` |
| 已启用 + 云端可达 | `=on`、`_BACKEND=openai`、`ALLOW_REMOTE=1`（若 URL 非 loopback）、key 存在 | 云端 embedding + BM25 → RRF 融合 |
| 已启用 + 云端不可用 | 无 key / 401 / 403 / 429 / 5xx / 超时 / 响应非法 | **干净回退纯 BM25**（逐条一致）+ 结构化状态；不 `isError`、不空列表（`RL-06`/`RL-09`） |
| 已启用但后端是本地 | `_BACKEND=ollama` | 走 `ADR-16` 原路径：**URL 仍必须是 loopback**，`ALLOW_REMOTE` 对它不生效 |

**"干净回退"的冻结含义**与 `ADR-16` §2 完全一致（条数不变、文本格式不变、不报错），云端后端不新增例外。

**重试与超时**：沿用 `ADR-16` §6——**重试上限 2 次**，超时由 `CODERAG_SEMANTIC_TIMEOUT` 控制（默认 30 s），失败信息必须可操作（哪个 URL、哪个模型、HTTP 状态码、耗时），**且绝不包含 key**（`S-05`）。

---

## 4. 配置项与环境变量命名（冻结）

沿用 `CODERAG_*` 前缀；`ADR-16` §4 的表**全部继续有效**，本 ADR 只改其中两项的语义并新增三项。

| 环境变量 | 默认 | 云端后端下的语义 | 备注 |
|---|---|---|---|
| `CODERAG_SEMANTIC` | 未设 = 关闭 | 总开关，只有 `on` 启用 | 不变 |
| `CODERAG_SEMANTIC_BACKEND` | `ollama` | **新增取值 `openai`** | 其他取值 → `SEMANTIC_BACKEND_UNSUPPORTED` |
| `CODERAG_SEMANTIC_URL` | `http://127.0.0.1:11434` | `openai` 后端下**必须显式给出**（无默认值，避免误打误撞调用某家服务）；**非 loopback 时要求 `ALLOW_REMOTE=1`** | 例：`https://api.openai.com/v1` |
| `CODERAG_SEMANTIC_MODEL` | `bge-m3` | `openai` 后端下**必须显式给出**（如 `text-embedding-3-small`） | 不再有默认，防止"以为在本地、其实在云端" |
| `CODERAG_SEMANTIC_API_KEY` | **未设** | **`openai` 后端的必填项**；未设 → `SEMANTIC_AUTH_MISSING`，**不发起任何请求** | **只从环境读**（`RL-02`）；见 §5 的投递方式 |
| `CODERAG_SEMANTIC_ALLOW_REMOTE` | 未设 = 不允许 | **非 loopback 地址的第二把钥匙**，必须为 `1` | 本地后端不受它影响 |
| `CODERAG_SEMANTIC_TIMEOUT` / `_BATCH` / `_MAX_CHUNKS` | `30` / `16` / `100000` | 同 `ADR-16` | 云端下 `_BATCH` 直接对应请求里的 `input` 数组长度；`_MAX_CHUNKS` 是**费用硬闸** |

**Key 的投递路径（已核实，`E-02` 的坑）**：

stdio 子进程的环境会被清洗——**环境里**名字匹配 `/KEY|PASSWORD|SECRET|TOKEN/i` 的变量与所有 `DSH_*` 变量都会被丢掉（`E-02`）。所以**用户直接在 shell 里 `export CODERAG_SEMANTIC_API_KEY=...` 是到不了子进程的**。已核实的正确做法（读已安装的 `@deepseek-ai/dsh-mcp-client`：`{...scrubbedParentEnv(), ...extra}`——**显式配置的 `env` 在清洗之后合并，能存活**）：

```yaml
# cordis.patch.yml（只放表达式，仓库里永远没有真实 key）
env:
  CODERAG_SEMANTIC_API_KEY: !!js process.env.CODERAG_SEMANTIC_API_KEY ?? ''
```

`!!js` 在**宿主进程（DSH）**求值，因此用户 shell 里的变量能被读到；随后作为**显式 env** 合并进子进程，绕开清洗。

---

## 5. ⚠️ 安全风险声明（**必须逐字出现在每一处启用云端后端的地方**）

> **开启云端后端 = 你的部分源码文本会离开这台机器。**
>
> - **外发内容**：已入库 chunk 的文本，**包括每个 chunk 的上下文前缀行**（形如 `// file: <工作区相对路径> | symbol: <种类 名字> | lines <起>-<止>`）。也就是说**文件路径与符号名也会一并外发**。
> - **保护仍然有效的部分**：三层过滤在入库前执行，因此被拦下的密钥文件（`.env`、`*.pem`、`id_rsa*` 等）**从来没有 chunk**，不可能被外发（`RL-03`）。
> - **不再成立的部分**：本地后端承诺的"代码不出机器"**在云端后端下不成立**——这是本后端与 `ollama` 的**唯一实质性差异**，也是它必须默认关闭、必须双重开关的原因。
> - **费用**：云端按 token 计费。首次索引会对**全量 chunk** 做 embedding，是一次性真实支出；`CODERAG_SEMANTIC_MAX_CHUNKS` 是硬上限，超过**显式失败并报实际数量**（`RL-08`），不静默截断。
> - **合规**：代码可能是公司资产或含第三方许可限制。外发前请自行确认你有权把这段代码发给该服务商。
> - **API key**：只从环境变量读取；**绝不**写入仓库、配置文件字面值、README 示例、测试 fixture、日志或错误信息（`RL-02`/`S-05`）。key 泄露视为安全事故，按 `AGENTS.md` §11 处理（回滚 + 轮换 + 报告）。
> - **传输**：非 loopback 地址必须显式设 `CODERAG_SEMANTIC_ALLOW_REMOTE=1`；**请使用 `https://`**。本项目不做证书固定，传输安全依赖服务商与你的系统信任链。

**这段声明的落点清单**（每一处都要有，缺一处即文档缺陷）：

| # | 位置 | 由谁落地 |
|---|---|---|
| 1 | `cordis.patch.yml` 的 `config.env` 注释（紧邻云端配置项） | `T5-20` |
| 2 | `README.md` 的「可选语义后端」云端小节 | `T5-20` |
| 3 | `src/dsh_coderag/config.py` 的 `SemanticConfig` 字段说明 | `T5-19` |
| 4 | 本 ADR §5 | `T5-18` |
| 5 | `PROJECT.md` §1.6.4（说明书性质的文件） | `T5-18` |

---

## 6. 失败模式与结构化状态

`ADR-16` §6 的 7 个 `SEMANTIC_*` code **全部继续有效**；云端后端新增 3 个：

| 冻结 code | 触发条件 | 引擎行为 |
|---|---|---|
| `SEMANTIC_AUTH_MISSING` | `_BACKEND=openai` 但 `_API_KEY` 未设 | **不发起任何请求**，回退 BM25，提示如何投递（见 §4） |
| `SEMANTIC_AUTH_REJECTED` | HTTP 401 / 403 | 回退 BM25，提示检查 key 与权限；**不重试**（重试不会变好） |
| `SEMANTIC_RATE_LIMITED` | HTTP 429 | 回退 BM25；**重试上限仍为 2**，且不做指数退避的长等待（不拖住 60 s 的工具预算，`E-01`） |

另外三条既有 code 在云端下的语义澄清：

- `SEMANTIC_BACKEND_NOT_LOCAL`：**改为只在 `_BACKEND=ollama` 时触发**——本地后端被指向远端地址仍然拒绝（`ADR-16` §8.1 对本地路径继续有效）；`openai` 后端走 §1.3 的双重开关，不报这个码。
- `SEMANTIC_EMBED_FAILED`：涵盖 5xx、超时、响应体非法。
- `SEMANTIC_MODEL_MISMATCH`：换云端模型后维度变化，必须重建向量索引（`ADR-16` §5.4）。

**登记方式**：与 `ADR-16` §6 相同——`ADR-16`/`ADR-17` 是这些名字的**唯一权威**，同步进 `PROJECT.md` §5.6 与 `src/dsh_coderag/types.py` 的 `ErrorCode` 由实现任务（`T3-08`–`T3-11`、`T5-19`）完成（那会同时改动 `tests/test_types.py` 里对 10 个码的逐项断言）。

---

## 7. 发布范围与验收判据

| 项 | 冻结条文 |
|---|---|
| 发布范围 | 与 `ADR-16` §7.1 相同：默认安装**不新增任何必需依赖**；云端后端不需要额外 Python 依赖（标准库 `urllib` 足够） |
| `S5` | `natural` 桶 `S@5 ≥ 0.40`，**由实际启用的后端独立满足**（§1.6） |
| `S6` | 未配置 `CODERAG_SEMANTIC` 时逐条与 `1.0.0` 一致、回归条数 = 0——**无条件适用**，云端后端也不例外 |
| `V1`–`V4` | 逐条沿用 `ADR-14` §10.4 / `ADR-16` §7.2（V3 **α = 0.025**；V4 不显著优于 B 就不发布） |
| 探针 | 云端路径的 `S5` 判定需要**在该后端上重跑探针与 L1**（`T5-14` 的本地结果不能替它背书）。**没有 key 就不跑**，并如实标注"已实现未验证"——**不得**用估算或转述的数字代替实测 |
| 额外门槛 | 云端后端额外要求：key 不在仓库/日志/状态/异常中出现；未启用时零网络调用；四种失败（无 key / 401 / 429 / 超时）都是结构化状态且回退 BM25。由 `T5-21` 的安全评审留原始输出 |

---

## 8. 与其它决策的关系

| 决策 | 关系 |
|---|---|
| `ADR-16`（可选向量后端） | **部分取代**：只取代"云端一律不采用"（§1.3/§3.1 云端行/§6 的 `SEMANTIC_BACKEND_NOT_LOCAL` 适用范围/§8.1 loopback 硬限制）。形态、extra、落点、RRF、V1–V4 全部继承；`ADR-16` 保持快照并加日期化指针 |
| `ADR-15`（暂缓） | 不变：重启条件里的"默认关闭 + 不得成为安装前置"被两条后端共同满足 |
| `S-01`（默认不联网） | **有条件放宽**：默认仍然不联网；云端后端是**显式 opt-in + 双重开关**，且必须在配置处声明风险 |
| `S-02`（不外发数据） | **有唯一例外**：仅限用户显式启用的云端 embedding 后端，外发内容以 §5 的清单为准；**其余任何路径（含本地后端）仍不得外发任何东西**（无遥测、无统计、无路径上报） |
| `RL-02`（凭据不入库） | 不变且被强化：云端 key 只从环境读，仓库里只允许出现 `!!js` 表达式 |
| `RL-10`（不得进入必需依赖） | 不变，覆盖**两条**后端 |
| `E-02`（stdio 环境清洗） | §4 给出已核实的 key 投递方式；这条既解释"为什么直接 export 没用"，也解释"为什么 patch 里放表达式是安全的" |
