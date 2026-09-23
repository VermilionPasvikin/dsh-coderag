# EVAL.md — 评测方案设计

> **文档版本**：1.0 ｜ **撰写日期**：2026-09-17
> **配套**：[`PROJECT.md`](./PROJECT.md)（项目文档）｜[`AGENTS.md`](./AGENTS.md)（开发约束）｜[`TESTING.md`](./TESTING.md)（测试方案）
>
> **本文件取代 `PROJECT.md` §5.8 与 §6.3 中关于评测的原始描述。** 两者冲突时以本文件为准。

---

## 0. 这份文档解决什么问题

`PROJECT.md` 里写了一句必须由数据回答的话：

> **如果 S3 不成立，说明检索在做无用功，此时砍掉它是正确的工程决策。**

问题是：**怎么知道 S3 成不成立？** 本文件给出完整答案——三层评测，各层用不同的工具、不同的成本、回答不同的问题。

**同时本文件也回答另外两个问题**：
- 「我不知道怎么造评测集」→ 第 2 章给出可照抄的构造流程与现成样例
- 「我不会设计评测方案」→ 第 1 章的结论先行，直接照做即可

---

## 1. 结论先行：三层评测

| 层 | 回答什么问题 | 需要 API key 吗 | 成本 | 工具 |
|---|---|---|---|---|
| **L1 · 检索质量** | 检索**本身**准不准？（Success@k / MRR） | ❌ 不需要 | 零 | **自己写，pytest 内嵌** |
| **L2 · 端到端 A/B** | 有了检索，Agent**干活**是不是真的更好了？ | ✅ 需要（可录制后回放） | 中 | **自建薄 runner `scripts/ab_eval.py run`**（§3.6；现成框架的选型结论见 §3.1） |
| **L3 · 回归门禁** | 这次改动有没有让之前的效果**变差**？ | 否（跑 L1）+ 可选（跑 L2） | 低 | pytest + `scripts/eval-gate.sh`（L1 `eval gate` + `scripts/ab_eval.py gate`） |

**关键设计**：**L1 完全不需要 LLM**。它是纯函数式的——给定 query 和 golden 标注，算出 Recall/MRR。这意味着：

- 你可以在**每一次 `pytest`** 里跑它（毫秒级）
- 它**零成本、零外部依赖、完全确定性**
- 它把「检索质量」从一个主观问题变成一个**可回归的单元测试**

**L2 才是真正贵的部分**，所以它只在需要端到端结论时跑（M3 决策门、以及之后每次改工具描述或召回策略），不是每次提交都跑。到 `T3-06` 为止已经跑过 `a-v1` / `b-v1` / `b-r5` 与 `a-smoke` / `b-smoke` 多轮，历史报告都留在 `eval/runs/` 下可复算。

---

## 2. L1：检索质量评测集（**你唯一必须亲自做的事**）

### 2.1 为什么不能自动生成

我调研了 RAGAS 的 `TestsetGenerator`、DeepEval 等自动生成方案。**它们都基于一个假设：你已经有文档、可以让 LLM 从文档反推问题。**

这个假设在你的场景下**恰好导致答案泄漏**：LLM 看着 `verify_token` 的代码生成问题，会很自然地写出「`verify_token` 是做什么的」——**问题里带了答案**（函数名）。这样的评测集测的不是检索，是字符串匹配。

**并且更根本的问题**：你要测的是「真实开发者会怎么问」，而 LLM 不知道你的项目里什么是真问题。

> **结论：L1 的评测集必须人工构造。30 条，约 4–5 小时。这是 `T3-02a` / `T3-02b` 估时的来源，也是整个项目唯一无法自动化的一步。**

好消息是：**30 条足够回答核心问题**——但有严格前提。第 2.6 节解释什么时候你只能说『无法区分』。

### 2.2 评测集格式

`eval/tasks.jsonl`，一行一个任务（JSONL 便于 diff 与逐行校验）：

```jsonc
{
  "id": "L-007",
  "class": "natural",              // exact | crossfile | natural（见 2.3）
  "query": "上游服务调用失败的时候是怎么处理的",
  "expect_paths": ["src/net/retry.py"],       // 必须命中（任一即可算命中）
  "expect_symbols": ["retry_call"],            // 可选：必须命中的符号
  "must_not_paths": [],                        // 可选：命中即算错（用于测精度）
  "notes": "纯自然语言，不含任何标识符",
  "added": "2026-09-20"
}
```

**字段约束（写进 `eval/schema.json`，CI 校验）**：

| 字段 | 必填 | 约束 |
|---|---|---|
| `id` | ✅ | 唯一，`L-NNN` 格式 |
| `class` | ✅ | `exact` \| `crossfile` \| `natural` |
| `query` | ✅ | 非空字符串 |
| `expect_paths` | ✅ | 非空数组，路径为**工作区相对路径**，必须真实存在（CI 校验） |
| `expect_symbols` | ❌ | 数组 |
| `must_not_paths` | ❌ | 数组 |
| `notes` | ❌ | 说明这条为什么这样设计 |
| `added` | ✅ | ISO 日期 |

### 2.3 三类任务与配比（30 条的构成）

| class | 条数 | 是什么 | 例子 | 为什么需要 |
|---|---|---|---|---|
| `exact` | **12** | 含精确标识符/错误码/文件名 | `retry_call`、`CONTEXT_WINDOW_EXCEEDED` | 这是 ripgrep 的强项。**如果这一类的 Recall 不高，说明你的索引或查询构造有 bug，与"要不要向量"无关**。它同时是 **regression 桶**（应接近满分） |
| `crossfile` | **11** | 需要跨文件理解的概念 | 「令牌签发和校验分别在哪个文件」 | 这是 DSH 现状最弱的地方——模型猜不到第二个文件 |
| `natural` | **7** | 纯自然语言，**故意不含任何标识符** | 「上游服务不稳定的时候怎么处理的」 | **这一类是 R2 规则的判定依据**（见 2.8），也是唯一可能体现向量价值的桶 |

**总计 30 条**（原设计 24 条，依据 §2.6 的样本量证据上调）。

**⚠️ 为什么是这个配比，而不是"按真实分布配比"**

这是本方案里最反直觉、也最需要你理解的一点。CodeRAG-Bench 实测**同一个 BM25** 在不同查询风格上的 NDCG@10：

| 数据集 | BM25 NDCG@10 | 查询风格 |
|---|---|---|
| HumanEval | **100.0** | 精确标识符 |
| MBPP | 98.6 | 精确标识符 |
| RepoEval | 93.2 | 半结构化 |
| CSN | 89.1 | 半结构化 |
| **DS-1000** | **5.2** | 自然语言 |
| **ODEX** | **6.7** | 自然语言 |

**同一套检索，从 100.0 到 5.2。词汇重叠决定一切。**

CodeXGLUE 的补充证据更狠：把标识符归一化（即消除字符串匹配红利）后，**MRR 从 0.869 掉到 0.507**——**一半以上的分数可能来自字符串匹配**。

**推论**：
1. **不要按真实使用分布配比。** 真实开发者提问大多带标识符，那样 `exact` 会占绝大多数，**BM25 全满分，你永远测不出向量的增量**。
2. **必须分桶报告，不报混合平均。** 一个 0.85 的混合 Recall 可能同时掩盖着「精确查找 1.0」和「自然语言 0.2」。
3. 配比按**诊断价值**而非真实频率确定：`exact` 12 条（regression 桶，用来抓实现 bug）+ `crossfile` 11 条（项目核心价值）+ `natural` 7 条（向量价值区）。

**构造时的硬规则**：

1. **query 里绝对不能出现 `expect_paths` 里的文件名或路径片段**（否则变成作弊）
2. **`exact` 类的标识符必须来自 `expect_paths` 指向的真实代码**
3. **`natural` 类的 query 描述的是"行为"或"意图"，不是"符号"**
4. **每一条都必须是你自己真的想知道答案的问题**。如果你已经知道答案在哪，这条的价值就减半
5. 不要挑"看起来好找"的——**评测集的价值来自它抓到的失败，不是它给出的高分**

### 2.4 怎么造这 30 条：一个可照抄的流程

**选一个仓库作为评测目标。** 建议顺序：

| 选项 | 优点 | 缺点 |
|---|---|---|
| **你自己的某个项目** | 你**真的**知道哪些问题是真问题；答案分布符合真实使用 | 需要你有另一个项目 |
| **DSH 本身**（那 325MB 的参考 checkout） | 规模真实（3300+ TS 文件）、你已经在读它、跨文件关系丰富 | 是 TypeScript，而你的 tree-sitter 第一版主打 C/C++/Python |
| **一个中型开源 C/C++ 项目** | 匹配你的语言优势与 grammar 覆盖 | 你要先熟悉它 |

**推荐：用 DSH 本身 + 一个你熟悉的中型项目，各造一半。** 这样同时覆盖 TS 和 C/C++ 的 grammar。

#### ⚠️ 分两批做，不要一次做 30 条

Elastic Search Labs 的第一方实践建议原文是 ***"Start small, but start."***——*"You only need to identify the 5–10 most critical queries… start with the top queries plus the queries with no results… start testing with an easy-to-configure metric like Precision and then work your way up."*（[judgment lists](https://www.elastic.co/search-labs/blog/judgment-lists-search-query-relevance-elasticsearch)，2025-12-11）

**这个建议针对的正是你最大的风险**：评测集构造（`T3-02a` / `T3-02b`）是整个项目唯一必须人工做的任务。**如果卡在这里，M3 就永远开不了工。**

所以拆成两批，**第一批只要 1–1.5 小时**：

| 批次 | 条数 | 内容 | 产出 | 估时 |
|---|---|---|---|---|
| **A 批（先做）** | **10** | **4 exact + 4 crossfile + 2 natural** | 能立刻跑出 `Success@5` 的可用集合 | **1–1.5h** |
| **B 批（补足）** | +20 | 8 exact + 7 crossfile + 5 natural | 达到 §2.6 的统计功效 | +3h |

**A 批的 10 条怎么选**（照 Elastic 的"最重要 + 历史零结果"思路）：
- **6 条来自你最常问的问题**——你平时在这个仓库里最常找什么？
- **4 条来自"你曾经搜不到"的经历**——**这几条价值最高**，它们直接对应真实痛点

**A 批做完就立刻跑一遍 `T3-03`/`T3-04`**，拿到第一组数字。哪怕只有 10 条、置信区间很宽，它也能告诉你"有没有系统性问题"。**然后才决定 B 批重点补哪一类。**

#### 完整流程（30 条，预计 4–5 小时）

> A 批先走 Step 1–6 的前半（每类按比例减半），**跑通评测链路**后再回来做 B 批。

```
Step 1（30 min） 选 3 个"入口文件"
   挑项目中你确实读过的 3 个文件。它们将成为多数 expect_paths 的来源。

Step 2（60 min） 写 12 条 exact
   打开这些文件，找 12 个"如果我要改它，我得先搜什么"的标识符。
   → query 就写那个标识符（可加少量上下文词）。
   自检：把 query 贴进 ripgrep，能不能找到？应该能——这 12 条是基线。

Step 3（60 min） 写 11 条 crossfile
   找 11 组"概念上在一起、文件上分开"的东西。例如：
     - 某个错误码的定义处 + 抛出处置 + 捕获处置
     - 某个接口的声明 + 实现 + 唯一的调用方
     - 某个配置项的 schema 定义 + 读取处 + 默认值处
   → query 描述这个概念，expect_paths 列出这些文件。

Step 4（60 min） 写 7 条 natural
   回忆你最近一次"想知道某功能怎么实现的"的时刻。
   → query 用你当时会打的字，expect_paths 填你最后找到的那个文件。
   ⚠️ 写完检查：query 里一个标识符都不能有。

Step 5（15 min） 机器校验
   python -m dsh_coderag.eval validate --tasks eval/tasks.jsonl --root <已索引的语料副本>
   → 校验 schema、路径存在性（expect_paths 必须真实存在）、query 不含路径片段或符号名

Step 6（60 min） ⚠️ 三道人工保险（**这一步不能跳**）
   ① 逐条写"参考解"：你自己按 query 去找，能不能找到 expect_paths？
      → **参考解也失败 = 这道题本身有歧义**，删掉或改写，不要留着当"难题"
   ② 逐条对照目标文件的用词，检查 query 是否抄了源文档词汇（§2.9 陷阱 10）
      → 抄了就改写成你自己的话
   ③ 留 5 条 holdout 不放进去，等 M3 决策做完再拿出来验一次
      → 防止"针对这 30 条调参"的过拟合
```

**为什么要"参考解"这一步**：一道评测题如果**连人用相同信息也做不对**，它测的就不是你的检索，而是题目的歧义。这类题留在集合里会系统性压低所有桶的分数，让你误判方向。

### 2.5 判定规则（什么算"命中"）

**判定必须机械、无歧义。** 规则如下：

| 指标 | 定义 |
|---|---|
| **一条 query 算命中** | `expect_paths` 中**至少一个**出现在返回的前 k 条结果的文件路径里 |
| **Success@k**（主指标，本文件即用它） | 命中条数 / 总条数 |
| **MRR**（辅指标） | 对每条 query，取 `expect_paths` 中**排名最高**的那个结果的位置 `r`，贡献 `1/r`；未命中贡献 0；最后取平均 |
| **Token 中位数** | 每次返回的 token 估算值取中位数 |

**⚠️ 术语提醒：这个指标的标准名字是 `Success@k`，不是 `Recall@k`。**

按 TREC / [ir-measures](https://ir-measur.es/en/latest/measures.html) 的约定：

| 名字 | 定义 |
|---|---|
| **`Recall@k`** | 前 k 条中命中的**相关文档数** ÷ **该 query 的全部相关文档数** |
| **`Success@k`** | 前 k 条中**至少有一条**相关文档（0/1） |

我们的 `expect_paths` 通常只列 1–3 个"必需命中"的文件，而且**我们并不声称知道全部相关文件**（这正是检索评测的固有困难）。所以严格意义上算不出分母，**用的是 `Success@k`**。

**本文件与最终报告一律写 `Success@5`**，并在首次出现处注明"即 top-5 中至少命中一个目标文件"。写 `Recall@k` 会让人误以为你做了完整的相关性判定。

> **为什么仍选它做唯一主指标**：它是 0/1 伯努利试验，整套评测的统计推断干净（Wilson 区间直接适用）；换成 `nDCG` 就需要分级相关性表，而人工分级的一致率只有 fair。**指标简单，结论才可信。**

**⚠️ k 必须等于实际喂给模型的条数。**

这条约束容易被忽略但很关键：`PROJECT.md` §3.5 里 `code_search` 的 `limit` 默认是 **5**。如果你评测时报 `Success@5`，就必须让检索**真的只返回 5 条**——否则你测的是一个模型根本看不到的场景（报告 k=5，实际喂给模型 12 条）。

**两个选项，选一个并保持一致**：

| 选项 | 做法 | 代价 |
|---|---|---|
| **A（本方案采用，已落地）** | 默认 `limit` 与评测都用 **5**，报 **Success@5** | 返回的 token 更少（利于 S4），但模型可用的上下文更窄 |
| B | 把默认 `limit` 调大，评测与报告都用同一个更大的 k | 指标数字会因 k 大而虚高，跨项目不可比 |

**本方案选 A**：`PROJECT.md` §3.5 的 `code_search` 默认 `limit` 是 **5**，`T3-03` 的 runner 也固定 `k=5`（`DEFAULT_K`），并在报告中**显式写出 `k=5`**。

**不使用 nDCG**：nDCG 需要分级相关性（0/1/2/3），而代码检索的相关性很难分级——一个文件要么包含答案要么不包含。**强行分级只会引入主观噪声。**

**`must_not_paths` 的处理**：命中即该条判 0 分（用于测精度，例如防止"令牌"把"令牌桶限流"排到前面）。

### 2.6 为什么 30 条够 —— 以及它的**严格前提**

**证据链**：

| 来源 | 结论 |
|---|---|
| Buckley & Voorhees, SIGIR 2000（[NIST](https://www.nist.gov/publications/evaluating-evaluation-measure-stability)） | IR 经典下界：**至少 25 条，50 条更好** |
| Anthropic, "Demystifying evals for AI agents"（2026-01-09） | *"20-50 simple tasks drawn from real failures is a great start"* —— **但前提是 "large effect size means small sample sizes suffice"** |

> ⚠️ **引用时必须连前提一起引。** 30 条只够回答"有检索 vs 完全没检索"；**回答不了"好了多少"**。如果 A/B 差异很小，**你必须报告"无法区分"，而不是"提升 8%"**。

**这就决定了本项目的结论形态**：

| 观察到的差异 | 你能说什么 |
|---|---|
| A 组 0.3，B 组 0.8 | ✅ "检索显著有效" |
| A 组 0.55，B 组 0.65 | ⚠️ "**无法区分**（95% CI 重叠）"——这同样是合格结论 |
| A 组 0.6，B 组 0.62 | ⚠️ "无法区分" |

**量化的报告方法**：用 Wilson 置信区间，而不是点估计。30 条中命中 13 条：

```
Success@5 = 0.433 (13/30, 95% Wilson CI ≈ [0.274, 0.608])
```

**如果置信区间宽到无法判断**（例如 [0.4, 0.9]），优先**增加 `exact` 类**（最便宜、最客观），而不是增加 `natural` 类。

#### ⚠️ 比样本量更危险的：多重比较

Carterette (2012) 证明：**12 个系统做 66 次配对检验时，"至少出现一个假阳性"的概率 > 95%**。

**对本项目的直接约束**：

> **只做一组 A/B 对比（baseline vs treatment）。** 这不是偷懒，是纪律。

**具体地，禁止这样做**：
- ❌ 同时对比 BM25 / BM25+符号加分 / BM25+向量 / BM25+向量+rerank 四个版本，然后挑"提升最明显"的那个报
- ❌ 反复调整评测集直到某个配置胜出
- ❌ 对同一批 30 条任务跑 5 次不同的参数组合，报最好的那次

**允许这样做**：
- ✅ 先跑 A（无检索）vs B（词法），报告结论
- ✅ 若 B 触发 R2 条件，**另起一轮** A/B/C 对比，并**明确声明这是第二次检验**（建议把显著性阈值从 0.05 收紧到 0.025 作为多重比较的粗略校正）

### 2.7 阈值（沿用 PROJECT.md §1.4，此处给出判定细则）

| 指标 | 阈值 | 不达标时先查什么 |
|---|---|---|
| **Success@5（exact 类）** | ≥ 0.90 | 分词/查询构造/索引是否漏文件 —— **不是**"要不要向量" |
| **Success@5（crossfile 类）** | ≥ 0.70 | 分块是否切断了跨文件线索；是否只返回了第一个文件 |
| **Success@5（natural 类）** | ≥ 0.40 | 若 < 0.40 且失败集中在"零词法重叠"，进入 R2 判定 |
| **MRR（全体）** | ≥ 0.60 | 排序权重（符号加分是否过强/过弱） |
| **Token 中位数** | ≤ 4000 | 预算裁剪是否生效 |

**分层报告是本设计的核心**。只报一个总的 `Success@5` 是没有诊断价值的——你无法从 0.75 这个数字里知道该改什么。

#### ⚠️ 但**分桶还不够**：必须逐 query 对比，不能只看均值

这是业界第一方实践里最容易被忽略、却决定这套东西有没有用的一条：

> *"You'll routinely see a change that lifts the mean nDCG by 0.03 while **quietly tanking three head queries** that make up half your traffic. … **diff per-query, not just the mean**, and gate CI on regression counts."*
> ——（[How to test search relevance before you ship a ranking change](https://dev.to/libme/how-to-test-search-relevance-before-you-ship-a-ranking-change-29o)，第三方博客，**引擎无关**，可直接套到 SQLite FTS5）

**具体到本项目的规则**：

| 规则 | 说明 |
|---|---|
| **报告必须列出逐条结果** | 每条 query 的命中/未命中、命中的是哪个文件、排名第几。**不能只给一个汇总数字** |
| **CI 门禁看"回归条数"，不只看均值** | 均值涨了但**有 ≥2 条从命中变未命中** → **判定为失败**，除非能在报告里解释清楚为什么那两条不重要 |
| **回归门禁前必须有确定性** | 见 `TESTING.md` §3.4：**不写 `ORDER BY rank, <唯一键>` 的话，"相关性回归"和"同分顺序抖动"会混在同一个红叉里，无法归因**。**确定性是相关性门禁的前置条件。** |

#### 聚合口径与门槛必须**显式写进代码和文档**

（依据：[Search relevance testing with golden queries](https://qaskills.sh/blog/search-relevance-testing-golden-queries)，第三方博客；下述阈值表可作起点，但**本项目的语料远小于其假设，阈值应更严**）

| 项 | 本项目规定 |
|---|---|
| **主聚合口径** | **宏平均（macro-average）**，即"每条 query 等权"。用于 CI 门禁。**不用流量加权**——本地工具没有流量概念 |
| **二值化** | 本项目是**天然二值**（路径命中/未命中），不存在分级阈值问题。**这也是选 `Success@k` 而非 nDCG 的一个实际好处** |
| **`golden_version` 字段** | 版本号描述**整份文件**，因此放在同目录的 `eval/tasks.meta.json`（`{"golden_version": "..."}`），**不进每一行**——30 次重复只会制造漂移风险。当前值由 `T3-04d` 冻结（`m3-b1`），运行/门禁读取方式见 `EVAL.md` §3.6 |
| **版本不匹配时** | **直接失败**，除非显式指定 `--rebaseline` 并**由人确认**。原文：*"Always fail on `golden_version` mismatch unless the job is explicitly a 'rebaseline' workflow"* |
| **改动 golden 集必须单独成一次提交** | 否则"改了题"和"改了实现"混在一个 diff 里，**你无法判断分数变化来自哪一边**——这是"静默的方法论破坏" |

**漂移阈值的起点参考**（第三方来源，**本项目需收紧**）：NDCG@10 掉 0.01 警告 / 0.025 失败；MRR 0.01 / 0.03；P@10 0.02 / 0.04。

**本项目用更严的理由**：那是基于大流量的合成语料，噪声低；我们只有 10–30 条，**单条翻转就是 3.3–10 个百分点**。所以本项目的门禁不是"分数掉多少"，而是**"有没有单条回归"**——见上表的"回归条数"规则。

### 2.8 失败归因表（**本方案最重要的部分**）

每一条失败的 query **必须被归入下面某一类**。这不是可选的——**没有归因的失败数据无法支撑任何决策**。

| 归因码 | 含义 | 典型修法 | 会不会导致"上向量" |
|---|---|---|---|
| `A1 分词失败` | 中文词被切错、短词无法匹配 | 修 `to_bigrams` / 查询构造 | ❌ 不会 |
| `A2 索引缺失` | 目标文件根本没进索引（被过滤？解析失败？超限？） | 查 `skipped` / `redacted` 报告 | ❌ 不会 |
| `A3 分块切断` | 答案横跨两个 chunk，两边都不完整 | 调分块粒度 / 加文件头块 | ❌ 不会 |
| `A4 排名过低` | 命中了但排在 k 之外 | 调符号加分、加局部性加权 | ❌ 不会 |
| `A5 零词法重叠` | query 与目标代码**没有任何共同词** | **这才是向量检索的适用场景** | ✅ **会** |
| `A6 检索集不含答案` | 答案确实不在被检索的目录里 | 扩大索引范围 | ❌ 不会 |
| `A7 标注错误` | 你的 `expect_paths` 写错了 | 修评测集 | ❌ 不会 |

**R2 规则的精确形式（取代 PROJECT.md 中的模糊表述）**：

> **进入"上向量"分支的条件**：`Success@5 < 0.80` **且** `natural` 类失败中 **`A5` 占比 ≥ 50%**。

**`A1`–`A4` 和 `A6`、`A7` 全部修完、重跑，仍不达标**，才考虑向量。**预测：你会在 `A1` 上花掉最多时间**——这正是我在 PoC 里踩到的坑（见 `PROJECT.md` §5.3.1：`trigram` 分词器让 2 字中文词全部失败）。

### 2.9 陷阱清单（每条都会让你的结论失效）

| # | 陷阱 | 症状 | 防法 |
|---|---|---|---|
| 1 | **答案泄漏到 query** | `exact` 类 Recall 虚高到 1.0 | CI 校验：query 不得含 `expect_paths` 的路径片段或符号名 |
| 2 | **只挑能答对的** | Recall 很高但你自己都不信 | Step 2–4 按数量配额写，不按"好不好找"筛 |
| 3 | **评测集被反复调参过拟合** | 训练集分数涨、真实使用没变化 | **冻结评测集**：`eval/tasks.jsonl` 一旦提交，调参期间禁止修改；新发现的 case 进 `eval/tasks.next.jsonl`，下一个版本才并入 |
| 4 | **只看检索不看端到端** | Recall 0.9 但 Agent 干活没变好 | L1 和 L2 都跑；L2 才是 S3 |
| 5 | **忽略 token 成本** | 检索全塞进去，质量涨了但成本爆炸 | S4 门槛；报 token 中位数 |
| 6 | **单次运行下结论** | 数字抖动被当成改进 | L2 用 `trials: 3`；L1 是确定性的，不受影响 |
| 7 | **没有基线** | 不知道 0.8 是好还是坏 | A 组（无检索）必须跑 |
| 8 | **把 A1 当成 A5** | 分词 bug 被误判为"缺语义检索"，白上一次向量 | **强制失败归因表**（2.8） |
| 9 | **从自己的 git commit 反推 query** | 看起来"从真实历史来"，实际是自己给自己泄漏答案——commit 改了哪些文件，正好就是答案 | **禁止**。query 必须来自"我确实想知道答案"的提问，不是"我知道答案在哪，倒推一个问题" |
| 10 | **合成的 query 抄了源文档词汇** | BM25 分数虚高。SIGIR 2024 实测：合成 query + 稀疏判定使系统排序一致度 **Kendall τ 从 0.8151 崩到 0.157** | query 用你自己的话写；写完**逐条检查是否抄了目标文件的用词** |
| 11 | **天花板效应（eval saturation）** | `exact` 桶全满分 → 整个评测失去区分度 | Anthropic 的区分：**capability eval 应起始于低通过率，regression eval 应接近 100%**。`exact` 桶是后者（满分是对的），**结论只能从 `natural` 桶读** |
| 12 | **多重比较** | 试了 5 个配置，挑最好看的报 | 见 §2.6 末：**只做一组 A/B** |
| 13 | **用 LLM judge 判检索相关性** | 会**系统性偏袒"用了 LLM 的系统"**，而你加向量时通常同时加 LLM rerank → **自造虚假提升** | 见 §5.3。检索相关性用**路径命中**这种机械规则 |
| 14 | **只看均值，不看逐条** | 均值涨 0.03，但**三条最重要的 query 悄悄崩了**——而你看到的是一行绿色 | **报告必须列逐条结果；门禁看回归条数**（§2.7） |
| 15 | **改了 golden 集却不改版本号** | 分数变化无法归因：是"题变了"还是"实现变了"？原文称这是 *"a silent methodology break"* | `golden_version` 不匹配**直接失败**；改 golden 集必须单独成一次提交（§2.7） |
| 16 | **在没有确定性排序的情况下做相关性门禁** | 分数抖动和 run-to-run 顺序抖动混在同一个红叉里，**无法归因** | 先落地 `ORDER BY rank, <唯一键>`（`TESTING.md` §3.4），**再做门禁** |

---

## 3. L2：端到端 A/B（**自建薄 runner**）

### 3.1 工具选型：调研过什么、结论是什么

DSH 生态里有两个现成评测框架。我逐一核实过：

| 工具 | Star | 最后推送 | 断言能力 | 可靠性统计 | A/B | 结论 |
|---|---|---|---|---|---|---|
| [**BiBoyang/dsh-eval-harness**](https://github.com/BiBoyang/dsh-eval-harness) | 13 | 2026-09-03 | ⭐ 14 种断言 | ⭐ `trials` + `pass@k` / `pass^k`（无偏估计） | 通过 baseline 对比 | **已否决**——`T3-00` 实测与本机 DSH 不兼容（§3.2） |
| [hccccc01333/dsh-eval](https://github.com/hccccc01333/dsh-eval) | 3 | 2026-08-14 | 基础 | 无 | ⭐ `compare` 出 B−A | **已否决**——成熟度存疑，未验证 |

**两者都未采用。实际使用的是自建 runner `src/dsh_coderag/eval/ab.py` + `scripts/ab_eval.py`，见 §3.6。**

**当时看中 `dsh-eval-harness` 的理由**（记录用，日后若要重估可从这里接手；全部来自其 README 的一手核实）：

1. **断言词汇丰富**：`tools_called`（保序子序列）、`tools_not_called`、`tool_args_contains`、`tool_result_contains`、`output_contains`、`output_matches`（正则）、`max_steps`、`max_tokens`、`no_tool_errors`、`output_judge`（LLM 语义评审，**结构断言全过后才调用**，不白烧 token）
2. **可靠性统计用了无偏估计**：README 明确写了 `pass^k` 用 `C(c,k)/C(n,k)` 而非 plug-in 的 `(c/n)^k`，理由是「x^k 上凸，Jensen 不等式保证它向上偏」。**这说明作者懂统计，不是随手写的。**
3. **LLM judge 可校准**：`eval_judge_validate` 在人工标注集上报混淆矩阵，且**分开看 TPR 与 TNR**，理由是「标注集里 90% 都是 pass 时，什么都放行的橡皮图章 judge 也能拿 90% agreement——agreement 会骗人」。**这条洞察本身就值一星。**
4. **隔离做得对**：每条用例独占 workspace 与 `DSH_HOME`，可并发（`concurrency`）
5. **报告带 `dshVersion`**：排障时能直接区分「dsh 变了」还是「模型变了」
6. **有 12 条真实用例可参考**（`cases/real/`）

**上面 1–3 条已被自建 runner 吸收**：断言集实现了 §3.4 的 9 类机械断言，`pass@k`/`pass^k` 用同一个无偏估计；`output_judge` 显式拒绝而不是静默忽略（§3.6 表）。

### 3.2 ⚠️ `dsh-eval-harness` 的兼容性风险（**`T3-00` 实测结论：不兼容**）

`dsh-eval-harness` v0.4.0 的 `package.json` 把 DSH 内部包放在 **`dependencies`** 而非 `peerDependencies`：

```json
"dependencies": {
  "@deepseek-ai/dsh-tools": "0.0.1-rc.1",
  "@deepseek-ai/dsh-session": "0.0.1-rc.1",
  ...
}
```

我核查了 npm registry 的实际版本：

| 包 | `latest` | `next` | `alpha` |
|---|---|---|---|
| `@deepseek-ai/dsh` | **0.1.5-rc.1** | 0.1.5-rc.2 | 0.1.6-alpha.1 |
| `@deepseek-ai/dsh-tools` | **0.0.1-rc.1** | 0.1.5-rc.2 | 0.1.6-alpha.1 |

`dsh-tools@0.0.1-rc.1` 确实是 `latest`，所以**能装上**。但 DSH 的约定是 *"`@deepseek-ai/cordis` 是每个 harness 包的 peerDependency (+ dev)"*，而把 `dsh-*` 放进 `dependencies` 会引入**进程内两份 `dsh-tools`** 的风险——这正是 DSH discussion **#572 / #783** 记录的事故：*双份 `@deepseek-ai/dsh-tools` → Symbol key 不匹配 → 调度器静默返回 undefined*。

**`T3-00` 实测**（`docs/m3-eval-harness-check.md` 有完整原始输出）：插件可以安装、可以装载（`--dump-config` 里出现 `dsh-eval-harness` 层），但跑 `cases/real/01-bash-tool.yml` 得到 `summary: total 1 / passed 0 / failed 0 / errored 1`，报错是 `no session log (session.jsonl / session.jsonl.zstd)`——该版本 0.4.0 的 trace 采集器只认 v0 文件名，而本机 DSH 落盘 `session.v3.jsonl.zstd`。**判定不兼容**，因此按 §3.6 的自建路线实施。

### 3.3 A/B 怎么配

两组的差异**只有"有没有挂上本项目的 bundle"**，用 `scripts/ab_eval.py run --group` 记录组名：

```sh
# A 组（基线）：eval-baseline profile，不挂本项目 bundle
# B 组（词法）：eval-coderag profile，挂上本项目 bundle
./scripts/dsh plugin --profile eval-coderag add .        # 加上我们的 bundle
```

| 组 | profile | 检索工具 | 用途 |
|---|---|---|---|
| **A · 基线** | `eval-baseline` | 无（模型只有 grep/glob/read） | 对照 |
| **B · 词法** | `eval-coderag` | `code_search` / `code_outline` | 本项目的效果 |
| C · 混合 | `eval-coderag` + 向量 | （仅当 R2 触发后） | 第二轮对比 |

### 3.4 用例怎么写（12–15 条）

**写少一点，写准一点。** L2 每条都要真跑一次 Agent，比 L1 贵一个数量级。

`cases/*.json` 示例（**格式说明见 §3.6：自建 runner 用 JSON，不用 YAML**）：

```json
{
  "name": "locate-token-validation",
  "prompt": "用户令牌是在哪里校验的？给我文件路径和函数名就行。",
  "tags": ["locate", "fast"],
  "assert": {
    "turn_end": "completed",
    "output_contains": ["token"],
    "max_steps": 6
  }
}
```

```json
{
  "name": "crossfile-error-code",
  "prompt": "CONTEXT_WINDOW_EXCEEDED 这个错误码定义在哪、在哪里被抛出、在哪里被处理？",
  "tags": ["crossfile"],
  "assert": {
    "turn_end": "completed",
    "tools_called": ["code_search"],
    "output_matches": ["(?i)token"],
    "max_steps": 8,
    "no_tool_errors": true
  }
}
```

**三条设计要领**：

1. **用 `tools_called: [code_search]` 断言工具被调用**。这一条同时测两件事：检索质量 + 模型**愿不愿意用**新工具。如果工具从没被调用（R5 风险），这条会失败。
2. **`output_contains` 要宽松**。端到端任务的输出是自然语言，写死字符串会让测试极脆。用 `output_matches` 的正则，或者直接靠 `expected.check` 脚本。
3. **`no_tool_errors: true` 拦住"假通过"**。README 自己举了例子：工具报错但 Agent 兜底答对，不加这条就会误判为通过。

### 3.5 判分与门禁

> ⚠️ 原始方案写的是 `dsh-eval-harness` 的 `eval_run` / `eval_gate`（该方案**已被 `T3-00` 判定不兼容并否决**，
> 见 §3.1/§3.2）。下面给出的是**实际可执行**的自建 runner 命令，实现见 §3.6。

```sh
# B 组跑一次，产出报告（--patch 把本项目 bundle 挂上）
python scripts/ab_eval.py run --cases cases --group eval-coderag \
    --out eval/runs/b-v1 --profile headless --patch cordis.patch.yml \
    --workspace <已索引的语料副本> --trials 3

# A 组跑一次（不带 --patch，模型只有 grep/glob/read）
python scripts/ab_eval.py run --cases cases --group eval-baseline \
    --out eval/runs/a-v1 --profile headless \
    --workspace <已索引的语料副本> --trials 3

# 与基线对比出门禁判定；退出码 0 = 无回归，1 = 有回归
python scripts/ab_eval.py gate --baseline eval/runs/a-v1/report.json \
    --current eval/runs/b-v1/report.json --markdown eval/runs/gate.md
```

**注意 `--trials 3`**：LLM 有随机性，单次结果不可信。runner 输出 `pass@k` / `pass^k`（`C(c,k)/C(n,k)` 无偏估计，不是 plug-in 的 `(c/n)^k`），门禁**看回归条数**而不只看均值（§2.7）。

**S3 的判定**：比较 A 组与 B 组的用例通过率。**S3 成立 = B 组比 A 组高 ≥ 10 个百分点。**

### 3.6 降级方案（**已被 T3-00 触发并落地**）

> **状态：已实现。** `T3-00` 实测 `dsh-eval-harness` 0.4.0 的 trace 采集器只认
> `session.jsonl(.zstd)`，而本机 DSH 写的是 `session.v3.jsonl.zstd`，因此按本节走自建路线。
> 实现见 `src/dsh_coderag/eval/ab.py`（全部逻辑）与 `scripts/ab_eval.py`（CLI），
> 测试见 `tests/test_ab_eval.py`。**本节的原始骨架已被下面的实际实现取代。**

实际实现与骨架的差异（都是**有意**的，不是简化）：

| 骨架 | 实际实现 | 为什么 |
|---|---|---|
| 读落盘的 `session.jsonl` | 读 `session.v{version}.jsonl`（**未压缩**） | 文件名带格式代际（T3-00）；runner 通过 overlay 把 `session-persistence-jsonl` 配成 `compression: none`，**因此不需要任何 zstd 解码依赖**。日志格式 = 首行 header + 逐行 `{type, seq, time, data}` |
| `cases/*.yml`（YAML） | `cases/*.json`（JSON） | 本项目**未声明且测试环境没有** YAML 依赖；为了一个用例格式引入依赖不划算（`AGENTS.md` §9：新增依赖先问）。JSON 同样是纯数据，且 `json` 在标准库 |
| “用同一套断言” | 实现 §3.4 的 **9 类**机械断言 | `output_judge` 需要模型评审，**runner 直接报错拒绝**而不是静默忽略——静默忽略会让用例看起来更严、实际更松 |
| 提取 tool/最终文本/token | 另加：步数、`turn_end` 原因、`interrupted`、tool 结果错误 | §3.4/§3.5 的 `max_steps`、`turn_end`、`no_tool_errors` 需要它们 |

两处骨架未规定、但实现已固定下来的行为（均由 `T3-05` 冒烟暴露；成因与修复见 `PROJECT.md` §6.7 的 `T3-15` 备注）：

- **工具名先按 DSH 的 MCP 命名空间归一化，再参与断言。** DSH 把 MCP 工具记为 `mcp__<serverName>__<toolName>`（如 `mcp__coderag__code_search`），而用例按工具自身的名字写 `code_search`。匹配时折叠 `mcp__<server>__` 前缀，**原始名字仍保留在 trace 与报告里**（可追溯）。不折叠的后果不是"断言变松"，而是**任何 MCP 工具断言恒为假**——用例看起来更严，实际把已经成功的 attempt 判成失败。
- **所有路径先按调用目录解析为绝对路径，再 fork 子进程。** 每次 attempt 都用 `cwd=workspace` 启动 DSH（这是必须的：`cordis.patch.yml` 的 `CODERAG_ROOT` 和 DSH 自己的工作区都取自 `process.cwd()`），所以相对形式的 `--dsh` / `--patch` / `--out` 会被重新基准化到 workspace 上而静默失败。`run_group` 入口统一 `resolve()`；**裸命令**（`dsh` / `npx`）保持原样以便走 `PATH`；启动器、patch、workspace 缺失时**明确报错**，而不是让子进程抛出不可操作的 `[Errno 2]`。

**保持不变的口径**：`trials` 与 `pass@k` / `pass^k`（`C(c,k)/C(n,k)` 无偏估计，不是 `(c/n)^k`）；
门禁**看回归条数**而不只看均值（§2.7）；每条用例 ≥3 trials。

用法：

```sh
python scripts/ab_eval.py run --cases cases --group eval-coderag \
    --out eval/runs/b-v1 --profile headless --patch cordis.patch.yml \
    --workspace <已索引的语料副本> --trials 3
python scripts/ab_eval.py gate --baseline eval/runs/a-v1/report.json \
    --current eval/runs/b-v1/report.json --markdown eval/runs/gate.md
```

**这个降级方案是有意保留的**：它不依赖任何第三方插件，只依赖 DSH 自己的会话日志格式（`packages/session/session-format-*`）。**如果你打算长期维护这个项目，自己写反而更可控。** 用现成工具是为了省 M3 那两天的时间，不是因为它更好。

### 3.6.1 离线验证（**不需要 API key**）

runner 的每一次 fork 都由测试用**假 dsh** 替代：它按真实格式写一份 `session.v3.jsonl`，
于是 会话发现 → 日志解析 → 断言判定 → `pass@k` → 报告 → 门禁 全链路都能在**无网络、无模型**
的条件下跑（`TESTING.md` T-02）。真实 A/B 才需要 key，那是 `T3-05`/`T3-06` 的事。

---

### 3.7 C 组（混合）与天花板探针：**可执行方法**

> 本节把 `ADR-14` §10.4 的 **V1–V4** 从判据变成**命令**（`ADR-16` §7.2 冻结了同一套判据）。§3.1–§3.6 讲 A/B 两组；这里讲 **C 组**（B + 向量 + RRF）以及它之前的**探针**。

#### 3.7.1 先跑天花板探针（`T5-14`）——它决定值不值得实施

**探针在写实现之前跑**（`ADR-15` §3.2、`ADR-16` §1.8）。它回答的是"向量**最多**能把这 30 条抬到哪"：

| 项 | 规定 |
|---|---|
| 目标 | 对 **30 条 query 与全量 chunk** 做一次 embedding，测 `natural` / `crossfile` 两个桶的 `S@5` / `MRR` **上限** |
| 语料 | 已索引的语料副本（`/tmp/dsh-coderag-t3-03-corpus`），与 L1 同源同版本 |
| 脚本落点 | **一次性脚本，不进 `src/`**（它不是生产路径，也就不该有测试与覆盖率义务）；结论写进 `docs/m5-vector-probe.md` |
| 必须记录 | 后端 / 模型 / 维度 / 耗时 / 两桶的四项指标 / **明确的 go-no-go 结论** |
| 判定 | `natural` 的 `S@5` **上限都低于 `S5` 的 0.40** → **no-go**，按 `ADR-16` §7.3 直接走 V4：全量实施没有意义 |

```sh
# 探针自备，放在仓库之外（它不进 src/，也不进 scripts/）
CODERAG_SEMANTIC=on CODERAG_SEMANTIC_URL=http://127.0.0.1:11434 \
  python /tmp/m5-vector-probe.py --corpus /tmp/dsh-coderag-t3-03-corpus \
  --tasks eval/tasks.jsonl --out docs/m5-vector-probe.md
```

> **探针与 C 组的区别**：探针用的是**全量向量的理论上限**（把 30 条 query 与所有 chunk 直接算余弦），它回答"天花板够不够高"；C 组走的是**真实检索链路**（RRF 融合、top-k、预算裁剪），它回答"落地之后还剩多少"。**先看天花板，是因为天花板不够就不必看落地。**

#### 3.7.2 C 组怎么跑，以及**配对**的前提

C 组 = B 组 + 可选后端。**唯一的差异是环境变量**，其余逐项相同——这是"配对"的全部含义：

```sh
CODERAG_SEMANTIC=on python scripts/ab_eval.py run --cases cases \
    --group eval-coderag-vector --out eval/runs/c-v1 \
    --profile headless --patch cordis.patch.yml \
    --workspace <已索引的语料副本> --trials 3
```

（这就是 `T3-11` 的验收命令。`CODERAG_SEMANTIC=on` 由 `ADR-16` §4 冻结；**未设即关闭**，关闭时输出与纯 BM25 逐条一致。）

| 配对要求 | 规定 | 违反的后果 |
|---|---|---|
| 同一批用例 | `cases/` 的 **13 条**，一条不增不减 | 增加/减少 case 会让 `pass@k` 不可比 |
| 同一工作区 | 两次 run 的 `--workspace` 指向**同一份副本**（内容与索引都相同） | 语料不同 = 测的不是同一个检索问题 |
| 同一 trials | 都是 **3**（§2.9 陷阱 6） | 不同 trials 的 `pass@k` 分母不同 |
| 同一 profile / patch | 都是 `headless` + `cordis.patch.yml` | 多挂一个 patch 就多一个变量 |
| **逐条对比** | 用 `cases[].successes` 逐条比，**不只看** `task_success_rate` | 均值涨了但关键 case 崩掉，看均值看不出来（§2.7） |

#### 3.7.3 V1–V4 逐条落到命令

**V1 与 V2 在 L1 侧判定**（`natural` 桶与 `exact` 桶都属于 L1 指标）：

```sh
# 在 C 配置下跑一次 L1，并与 B 基线做逐 query 门禁（gate 会自己跑一遍 eval）
CODERAG_SEMANTIC=on python -m dsh_coderag.eval gate \
    --tasks eval/tasks.jsonl --root <已索引的语料副本> \
    --baseline eval/runs/l1-baseline.json \
    --out eval/runs/l1-c.json --gate-out eval/runs/l1-c-gate.json \
    --markdown eval/runs/l1-c-gate.md

# V2：exact 桶必须仍是满分，且零单条回归
python -c "import json;g=json.load(open('eval/runs/l1-c-gate.json'));m=g['metrics'];print('exact@5 =',m['exact']['success']['5'],'regressions =',g['regression_count'])"
# V1：natural 桶的 S@5（B 组基线是 0.000）
python -c "import json;print('natural@5 =',json.load(open('eval/runs/l1-c-gate.json'))['metrics']['natural']['success']['5'])"
```

| # | 判据 | PASS 条件 |
|---|---|---|
| **V1** | 主判据是 **`natural` 桶 `S@5` 的提升**，不是端到端（`ADR-14` §10.4） | `natural@5 ≥ 0.40`（`S5`）**且** > B 组的 0.000 |
| **V2** | `exact` 必须保持 **1.000**，任何单条回归即失败 | `exact@5 == 1.0` **且** `regressions == 0` |

**V3 在 L2 侧判定**（端到端、配对、**第二轮口径 α = 0.025**）：

```sh
# 配对符号检验：只数"方向不一致"的用例（better / worse），n = better + worse
python - <<'PY'
import json, math
b = json.load(open("eval/runs/b-v1/report.json"))
c = json.load(open("eval/runs/c-v1/report.json"))
bs = {x["name"]: x["successes"] for x in b["cases"]}
cs = {x["name"]: x["successes"] for x in c["cases"]}
better = sum(1 for k in bs if cs[k] > bs[k])
worse  = sum(1 for k in bs if cs[k] < bs[k])
n = better + worse
p = 1.0 if n == 0 else sum(math.comb(n, i) for i in range(better, n + 1)) / 2 ** n
print(f"C better on {better}, worse on {worse}, discordant n={n}, one-sided p={p:.4f}")
print("V3:", "PASS" if p < 0.025 else "FAIL —— 未达 alpha=0.025（ADR-14 10.4 V3 / EVAL.md 2.6）")
PY
```

| 项 | 规定 |
|---|---|
| 检验 | **配对符号检验**（exact binomial），只统计 `successes` 不相等的用例 |
| 方向 | **单侧**（方向事先写在 `ADR-14` §10.4：C 优于 B）；若改用双侧，对应阈值是 0.05 |
| 阈值 | **α = 0.025**——这是**第二轮检验**，按 §2.6 的多重比较校正收紧（不是 0.05） |
| 报告 | 必须显式声明"这是第二次检验，α 已收紧到 0.025"，并同时给出 `better` / `worse` / `n` |

**V4 是发布决定，不是统计量**：

| 情形 | 结论 |
|---|---|
| V1 未达 `natural@5 ≥ 0.40` | **不发布**向量路径 |
| 或 V3 的 `p ≥ 0.025` | **不发布**向量路径 |
| V1 **与** V3 都过 | 可以发布；`S6`（默认路径零回归）仍须无条件成立 |

> **V4 的原文是"若 C 组不能显著优于 B 组，则不发布向量路径"**（`ADR-14` §10.4）。它的精神是：**不得为一个已达成的目标增加常驻复杂度**——端到端目标已由纯词法达成（`ADR-15` §2.1），所以向量必须**额外**证明自己在 L1 上值这个价，否则就留在仓库里不发布。

#### 3.7.4 判据**按后端独立判定**（`ADR-17` §1.6 / §7）

可选后端有**两条**——本地 `ollama`（`ADR-16`）与云端 `openai` 兼容（`ADR-17`）。**判据不共享**：

| 项 | 规定 |
|---|---|
| 判据按后端独立判定 | `S5` 与 `V1`–`V4` 由**实际启用的那个后端**独立满足。**本地后端的探针或 L1 结果不得给云端背书，反之亦然**（`ADR-17` §1.6） |
| 探针 | 每个后端各自重跑一次 §3.7.1 的天花板探针，结论分节写在各自的报告里 |
| 本地后端 | `_BACKEND=ollama`（默认），URL 必须是 loopback（`http://127.0.0.1:11434`）；`ALLOW_REMOTE` 对它不生效 |
| 云端后端 | `_BACKEND=openai`，URL 与 MODEL **必须显式给出**；URL 非 loopback 时**额外需要 `CODERAG_SEMANTIC_ALLOW_REMOTE=1`**（双重开关，`ADR-17` §1.3）；key 只从运行时环境读（`RL-02`） |
| 没有 key | 云端路径**不跑**，如实标注「已实现未验证」；**不得**用估算或转述的数字代替实测（`ADR-17` §7） |

§3.7.2 的 C 组命令**按后端加环境变量**即可；配对要求（同一批用例 / 同一工作区 / 同一 trials / 同一 profile）逐项不变：

```sh
# C 组 · 本地后端
CODERAG_SEMANTIC=on CODERAG_SEMANTIC_BACKEND=ollama \
CODERAG_SEMANTIC_URL=http://127.0.0.1:11434 CODERAG_SEMANTIC_MODEL=bge-m3 \
  python scripts/ab_eval.py run --cases cases \
    --group eval-coderag-vector-ollama --out eval/runs/c-ollama \
    --profile headless --patch cordis.patch.yml \
    --workspace <已索引的语料副本> --trials 3

# C 组 · 云端后端（双重开关；key 只从运行时环境读，仓库里只留变量名）
CODERAG_SEMANTIC=on CODERAG_SEMANTIC_BACKEND=openai \
CODERAG_SEMANTIC_URL=https://<provider>/v1 CODERAG_SEMANTIC_MODEL=<model> \
CODERAG_SEMANTIC_ALLOW_REMOTE=1 \
CODERAG_SEMANTIC_API_KEY="$CODERAG_SEMANTIC_API_KEY" \
  python scripts/ab_eval.py run --cases cases \
    --group eval-coderag-vector-cloud --out eval/runs/c-cloud \
    --profile headless --patch cordis.patch.yml \
    --workspace <已索引的语料副本> --trials 3
```

> **报告必须标明后端**：`c-ollama` 与 `c-cloud` 是**两份独立报告**，不能拼成一份"向量组"。把「哪个后端 / 哪个模型 / 哪个维度」写进报告头，否则 `V4` 的发布决定无法归因。

#### 3.7.5 云端后端的**失败注入**（离线优先，`ADR-17` §6 / §7）

云端后端的四种失败**都能离线注入**——用 **loopback 桩**（返回指定 HTTP 状态码）与**空/假 key**，不需要联网、不需要真 key（`T-02`）：

| 注入 | 怎么做（离线） | 期望的可观测结果 |
|---|---|---|
| **无 key** | `env -u CODERAG_SEMANTIC_API_KEY`（或设成空串——**空串 = 未设**，`ADR-17` §4） | `SEMANTIC_AUTH_MISSING`；**零请求**（桩上收到 0 次连接）；回退 BM25 |
| **401 / 403** | URL 指向 loopback 桩，桩返回 `401`（403 同理）；key 用假值 | `SEMANTIC_AUTH_REJECTED`；**不重试**（重试不会变好）；回退 BM25 |
| **429** | 桩返回 `429` | `SEMANTIC_RATE_LIMITED`；**重试上限仍为 2**；回退 BM25 |
| **超时** | 桩接受连接但不回包，且 `CODERAG_SEMANTIC_TIMEOUT=1` | `SEMANTIC_EMBED_FAILED`；不拖过 60 s 的工具预算（`E-01`）；回退 BM25 |

**四种失败共同的断言**（缺一不可）：

1. **干净回退**：逐条结果与「未启用」时完全一致（`S6`；`ADR-16` §2 的冻结含义）；
2. **结构化状态**：返回体带 `status` 与上述 code，**不 `isError`、不返回空列表**（`RL-06`/`RL-09`）；
3. **key 不入日志/状态/异常**：把假 key 设成一个可 grep 的哨兵串，跑完断言它在 **stdout / stderr / 返回 JSON / 异常文本**里**零命中**（`S-05`、`RL-02`）；
4. **未启用时零网络调用**：`CODERAG_SEMANTIC` 未设时，桩上收到 **0 次连接**（`S-01`）。

**双重开关的拒绝路径**也要有：URL 指向非 loopback 且**未**设 `CODERAG_SEMANTIC_ALLOW_REMOTE=1` → **拒绝启用**（本地后端报 `SEMANTIC_BACKEND_NOT_LOCAL`；云端后端按 `ADR-17` §1.3 一律拒绝），且回退 BM25。

---

## 4. L3：回归门禁

### 4.1 每次提交都跑（零成本）

```sh
# L1 是确定性的纯函数测试，毫秒级，进 pytest
python -m pytest -q
```

L1 的确定性回归由两部分组成，**都在 `pytest` 里**，都不需要网络与 API key：

| 部分 | 落点 | 覆盖什么 |
|---|---|---|
| golden 集本身 | `tests/test_eval.py`、`tests/test_metrics.py`、`tests/test_report_diff.py`、`tests/test_golden_version.py` | schema/路径校验、命中判定、分层指标、逐 query diff、`golden_version` 校验 |
| golden 集 × 真实语料 | `tests/test_eval.py::test_golden_set_runs_against_indexed_corpus`（**opt-in**） | 把 `eval/tasks.jsonl` **每一条**真的跑在**一份已索引的语料副本**上，断言条数与 golden 集文件一致（防静默截断）、每条 query 都有结果、报告可写 |

第二项要设 `CODERAG_EVAL_CORPUS` 指向已索引的语料副本才启用（`T-02`/`T-03`：默认套件保持离线、自足）：

```sh
CODERAG_EVAL_CORPUS=/tmp/dsh-coderag-t3-03-corpus python -m pytest tests/test_eval.py -q
```

> **它的条数断言锚在 golden 集文件上，不是字面量**：断言 `len(tasks) == 该文件非空行数`。早期版本写死 `== 10`（`T3-02b` 把集合从 10 扩到 30 时漏改），于是这条 opt-in 用例假红了两个里程碑；锚到文件后**集合再扩也不会漂**，而它真正要证的"每一条都被回放、不被截断"仍然成立。

**这个测试的价值**：它把「检索质量」变成了一个**每次提交都会跑的回归测试**。任何让检索命中率下降的改动会立刻变红。

⚠️ **注意**：`eval_corpus` fixture 自己建索引（`tmp_path`，小语料），所以默认套件不会因为评测语料而变慢；真实语料的索引由**外部副本**承担（`CODERAG_EVAL_CORPUS` 指向一份预先 `index` 过的拷贝），而不是每次重建。**索引不进仓库、也不写在工作区之外**（`S-03`）。

### 4.2 版本发布前跑（有成本）

```sh
bash scripts/eval-gate.sh          # 跑 L1 + L2，输出报告，退出码即门禁
```

---

## 5. 现成经验与来源

### 5.1 已经存在、可以直接复用的

| 资源 | 是什么 | 怎么用 |
|---|---|---|
| [**dsh-eval-harness**](https://github.com/BiBoyang/dsh-eval-harness) | DSH 插件回归评测门禁（YAML 用例 + headless 驱动 + trace 断言 + baseline 对比） | **未采用**——`T3-00` 实测与本机 DSH 的会话日志格式不兼容（§3.2）；L2 用自建 `scripts/ab_eval.py`（§3.6） |
| 它的 `cases/real/` | 12 条针对真实插件（bash/fs/search/todo/web_search/subagent/workflow）的实测用例 | **只借鉴用例形状**，见 3.4（我们用 JSON，不是 YAML） |
| 它的 `skills/eval` | 一个教模型帮你写评测用例的 Skill | 可以让你和 AI 一起写 cases |
| [hccccc01333/dsh-eval](https://github.com/hccccc01333/dsh-eval) | Agent 评测平台（paired A/B、keyless replay、跨 harness 导入） | L2 备选；**注意它 3★、创建与最后推送同为 2026-08-14，成熟度存疑** |
| [RAGAS](https://docs.ragas.io/) | RAG 评测指标库（faithfulness / context precision / recall） | **本项目第一版不引入**——它的指标针对文档问答，代码检索用不上。若 M3 之后做向量，再考虑 |

**检索评测的第一方工程实践（照抄它的**形状**，不用它的工具）**：

| 来源 | 可直接抄什么 |
|---|---|
| **Elastic `_rank_eval` API**（[官方文档源文件](https://github.com/elastic/elasticsearch/blob/main/docs/reference/elasticsearch/rest-apis/search-rank-eval.md)） | **① 三件套的构成**：文档集合 + 典型查询集合 + **每查询一组人工评分**——与我们的 `tasks.jsonl` 同构。<br>**② 报告结构**：整体 `metric_score` + **逐 query `details[].metric_score`** + `failures` 列表。**这就是"逐条断言 + 整体分数"的官方形态**，`T3-04c` 的 report schema 直接照它设计。<br>**③ 它存在的理由**（值得引用的原文）：*"This can only be done if the search result quality is **evaluated constantly across a representative test suite of typical user queries**, so that improvements in the rankings for one particular query don't negatively affect the ranking for other types of queries."* |
| **Elastic Search Labs — judgment lists**（[2025-12-11](https://www.elastic.co/search-labs/blog/judgment-lists-search-query-relevance-elasticsearch)） | **"Start small, but start."** —— 5–10 条最关键 query 起步（§2.4）；*"Make it part of the flow"* —— 融进开发流程而不是一次性活动 |
| **Vespa Testing 文档** | 系统测试的纪律：*"Each system test should be self-contained… should generally start by clearing all documents"* —— 对应我们的 `T-03`（用 `tmp_path`，不共享状态） |
| **`Software Engineering at Google` ch.11** | Google 自述搜索质量靠**真实查询 + 人工评分**，而不是靠覆盖率或指标堆砌 |

**⚠️ 不要引用这些来源**（本次调研确认读不到可验证正文）：Sourcegraph 关于 BM25F 的三篇博客（自动抓取返回 403，**网上转述的"Sourcegraph 用 BM25F"在本项目中没有一手依据**）、GitHub「The technology behind GitHub's new code search」（JS 渲染，正文未提取）。

### 5.2 关键实证（决策依据）

| 结论 | 数字 | 来源 |
|---|---|---|
| 检索经常不提升性能 | **最多 80% 的检索不提升性能**，仅约 20% 实例受益 | Repoformer, arXiv 2403.10059 |
| 代码检索里 BM25 打败纯向量 | RepoEval NDCG@10：**BM25 93.2 vs BGE-large 80.4** | CodeRAG-Bench, arXiv 2406.14497 |
| 代码专用 embedding 在真实任务上输给 BM25 | SWE-bench-Lite：voyage-code **29.1** vs BM25 **43.0** | 同上 |
| 文档全不含答案时模型仍作答 | 最好拒答率仅**中文 43.33%** | RGB, arXiv 2309.01431 |
| RAG 的健壮性是演化出来的 | *"validation of a RAG system is only feasible during operation"* / *"robustness evolves rather than designed in at the start"* | arXiv 2401.05856 |
| 顺序保持可显著提升答案质量 | 128 块场景 F1：按分数降序 **38.40** → 按原文顺序 **44.43** | NVIDIA, arXiv 2409.01666 |
| 塞满上下文不如检索 | 检索 16K 的 **44.43** > 塞满 196K 的 Gemini-1.5-Pro **43.08** | 同上 |
| 混合检索 + rerank 的收益 | 失败率 5.7% → +Contextual Embedding **3.7%**(−35%) → +BM25 **2.9%**(−49%) → +rerank **1.9%**(−67%) | Anthropic Contextual Retrieval |
| 检索把文件名与 chunk 序号带进上下文有帮助 | *"Adding the file name and chunk number into the retrieved context helped the reader extract the required information"* | arXiv 2401.05856 |

### 5.3 本方案中被否决的现成做法

| 做法 | 为什么否决 |
|---|---|
| **RAGAS `TestsetGenerator` 自动生成评测集** | 从代码反推问题会导致答案泄漏（问题里带上函数名）；且 LLM 不知道你的项目里什么是真问题 |
| **用 LLM-as-judge 判定检索相关性** | 三重理由：(1) **它偏袒"用了 LLM 的系统"**——Fröbe et al. SIGIR 2025 测得 LLM 评估器平均把这类系统**高估 9–17 名**；而你加向量时通常同时加 LLM rerank，等于自造虚假提升。(2) 它的证据只在**系统排名层面**成立（run 级 Kendall τ 0.89–0.94），**文档级 Cohen's κ 只有 0.38–0.62**——而你要报的是逐条 Success@5，消费的正是 per-item 质量。(3) 检索相关性是**机械可判定**的（路径是否在结果里），用 LLM 判是引入成本与噪声。**LLM judge 只用在 L2 的最终答案质量上**，且必须先经 `eval_judge_validate` 校准 |
| **TREC 式多人标注 + 一致性检验** | 30 条、单个标注者、二值相关性——这个规模下 Cohen's kappa 没有意义。**当评测集涨到 100+ 条且要对外发布时再引入** |
| **nDCG / 分级相关性** | 需要分级相关性表，而人工分级的一致率只有 fair。且 **Success@k 单条即 0/1，整套评测退化为独立伯努利试验，可直接算 Wilson 置信区间**——这是本方案能用 30 条就下结论的统计学基础 |
| **从 git commit / PR 反推 ground truth** | 需要仓库有高质量 commit message，且会把"改了哪些文件"当成"答案在哪"，这对**检索**任务是错位的标注（改动文件 ≠ 回答问题需要的文件）。**更是自我泄漏**——见 §2.9 陷阱 9 |

---

## 6. 修订记录（**理由存档，不定义任务**）

> **任务 ID、产出文件、验收命令不在本节定义**——它们唯一地定义在 [`PROJECT.md`](./PROJECT.md) §6.3。
> 本节只保留"为什么那样改"的理由，**避免同一个事实有两个家**。

下列修订**已经合并进 `PROJECT.md` §6.3**，实施时以那里为准：

| 改动 | 依据 |
|---|---|
| **新增 `T3-00`**：`dsh-eval-harness` 兼容性验证 | 该包把 DSH 内部包放在 `dependencies` 而非 `peerDependencies`（`dsh-tools@0.0.1-rc.1`），而 DSH 的约定是 peer。这有引入**进程内双份包**的风险，正是 discussion **#572/#783** 记录的事故形态。**必须先验证再依赖**，不通过则走 §3.6 的自建薄 runner |
| **评测集构造拆成 `T3-02a` / `T3-02b`** | Elastic Search Labs 第一方实践原文 *"Start small, but start."*（5–10 条起步）。它是本项目**唯一必须人工做**的任务，一次做 4–5 小时是 M3 开不了工的最大风险 |
| **新增 `T3-04b`**：失败归因 | 只报一个 Success 数字**没有诊断价值**。`A1`–`A4`/`A6`/`A7` 是**实现问题**，只有 `A5`（零词法重叠）支持"上向量"。没有归因表，R2/R3 无法机械判定 |
| **新增 `T3-04c`**：逐 query diff + 回归条数 | *"You'll routinely see a change that lifts the mean nDCG by 0.03 while **quietly tanking three head queries**."* 门禁必须看**回归条数**，不能只看均值 |
| **新增 `T3-04d`**：`golden_version` 校验 | 改了 golden 集却不改版本号 → 分数变化无法归因，原文称之为 *"a silent methodology break"*。**改 golden 集必须单独成一次提交**（`AGENTS.md` §7.0） |
| **`T3-05`/`T3-06` 改用 `dsh-eval-harness`**（**已撤销**） | 当时的理由：自建 A/B runner 要花掉 M3 两天。该工具已提供 `trials`（`pass@k`/`pass^k` 用**无偏估计**）、`no_tool_errors`（拦"工具报错但 Agent 兜底答对"的假通过）、14 种断言与 baseline 门禁。<br>**该改动已由 `T3-00` 撤销**：实测该插件与本机 DSH 的会话日志格式不兼容（§3.2）。L2 改走 §3.6 的自建 runner（`T3-15`），上面这些能力由它承担 |
| **`T3-07` 的 R2 条件精确化** | 原表述"失败案例中 ≥50% 是语义改写"**无法机械判定**。改为"`natural` 类失败中 **`A5` 占比 ≥50%**"，与 §2.8 的归因表对齐 |
| **`ADR-14` 取代原 `ADR-12` 的编号** | `PROJECT.md` §3.7 已用掉 ADR-12（`Success@k`）与 ADR-13（标点路由），语义检索的决策记录顺延为 **ADR-14** |

---

## 7. 一页纸速查

```
要造评测集？
  → 30 条：12 exact + 11 crossfile + 7 natural
  → 流程见 §2.4（4–5 小时）
  → 写完跑 `python -m dsh_coderag.eval validate --tasks eval/tasks.jsonl --root <已索引语料>`
  → 提交后冻结，新 case 进 tasks.next.jsonl

要跑评测？
  → L1（检索质量，零成本）  : python -m pytest -q
                              （再设 CODERAG_EVAL_CORPUS=<已索引语料> 可跑真实 30 条）
  → L2（端到端 A/B，需 key）: python scripts/ab_eval.py run × 2 组 → ab_eval.py gate
  → 一次跑完 L1 + L2        : bash scripts/eval-gate.sh

看到失败怎么办？
  → 先填归因码（§2.8 的 A1~A7）
  → A1~A4/A6/A7 → 修实现，不要上向量
  → A5 占 natural 类失败 ≥50% 且 Recall<0.80 → 才触发 R2，上向量

报告怎么写？
  → 分层指标，不是单一数字
  → Success@5 = 0.433 (13/30, 95% CI 0.274–0.608)
  → 附归因分布
```

---

## 8. 未能核实的事项

1. **`hccccc01333/dsh-eval` 的可用性** —— 该仓库 3★、创建与最后推送同为 2026-08-14、无后续提交，**未验证其是否真的能在当前 dsh 上运行**。
2. **30 条对本项目的具体统计功效（statistical power）** —— 有下界依据（Buckley & Voorhees 的"至少 25 条，50 条更好"；Anthropic 的"20-50 simple tasks"），但**没有针对"本项目这个效应量"的功效计算**。若你要写论文级报告，应在收集数据**之前**做一次 power analysis。
3. **OpenAI「停用 SWE-bench Verified」的原文** —— 英文原文返回 403，**无法直读**。流传的"约 59% 被审样例测试用例有缺陷"等数字全部来自二手转述（Latent Space 访谈与 HN 讨论）。**引用前请用可访问网络复核原文。**
4. **中文 2 字词在真实代码库中的占比** —— 本文件据此调整了分词方案，但**未量化统计**过真实项目里 2 字中文标识符/注释词的比例。
