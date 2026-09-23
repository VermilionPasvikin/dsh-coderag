# M1 结项记录：DSH 端到端观察

> 依据 PROJECT.md 的 T1-16。记录在 DSH Web（dsh 0.1.5-rc.1，forBSH 环境）上对
> dsh-coderag MCP 服务器的实际观察。下列条目都是**实际发生**的现象，不是预期。
>
> 环境：DSH Web http://127.0.0.1:3099，通过 --patch ./cordis.patch.yml 加载；被测工作区
> examples/demo-workspace（3 个文件 / 3 个 chunk）；模型侧工具名 mcp__coderag__code_search。
> 下面引用的返回文本均由该工具实际产生。

## 具体观察

### 观察 1：已知确切标识符时，模型优先 grep，而不是 code_search
- 工作区：dsh-coderag 自身；模式：创造模式。
- 输入：「to_bigrams 在哪个文件实现，行号是多少」。
- 模型行为：只调用了 grep，未调用 code_search。
- 结果：grep 找到 src/dsh_coderag/text.py 第 18 行。
- 结论：对「已知标识符的精确定位」，模型走它更熟的 grep；说明检索不是模型的默认入口。

### 观察 2：目标仓库没有答案时，code_search 返回 empty 而不是编造
- 工作区：dsh-coderag 自身（不含任何令牌校验业务代码）。
- 输入：「用户令牌在哪里校验」。
- 返回（原文）：
    status: empty
    message: Search did not return results.
    hint: No matches. Try different keywords, or use grep for exact identifiers.
- 对照组：同一工具、同一索引下，query=令牌 与 query=verify_token 都返回 status: ready、
  5 条命中（命中的是样例文本，不是业务代码）。
- 结论：RL-06 的结构化状态生效；整句失败可归因于两点——目标仓库无该内容，以及精度模式
  把整句 bigram 当作连续匹配。

### 观察 3：工具可被发现，但「首轮」未必被选中
- 工作区：examples/demo-workspace；模式：创造模式。
- 输入：「用户令牌在哪里校验」。
- 模型行为：先调用两次 grep，之后才发现并调用 code_search。
- 返回（原文节选）：
    status: ready
    query: "用户令牌 token 校验 verify"
    scanned: 3 files / 3 chunks
    hits: 1 (sorted by source order)

    ── src/auth/token.py:1-20  (chunk 0)
- 结论：工具确实在列表中且可被调用，但首轮未首发；R5（模型不使用新工具）只是部分缓解。

### 观察 4：对「行为型」问题，修正描述后模型首发 code_search
- 工作区：examples/demo-workspace；模式：创造模式（新会话）。
- 输入：「连接池代码在哪？」。
- 模型行为：第一步就调用 code_search，参数为 {"query":"连接池 connection pool","limit":10}。
- 返回（原文节选）：
    status: ready
    query: "连接池 connection pool"
    scanned: 3 files / 3 chunks
    hits: 1 (sorted by source order)

    ── src/db/pool.py:1-8  (chunk 0)
- 结论：§3.5 描述里的 Prefer this over grep when you do not know the exact identifier, or
  when searching for behaviour across multiple files 起了作用；与观察 1 对照，模型在
  「不知道确切标识符 / 找行为」时才优先检索。

### 观察 5：模型会改写、扩写查询以补足词法召回
- 两次成功的调用里，模型把用户问题改写为 "用户令牌 token 校验 verify" 与
  "连接池 connection pool"，主动补充英文同义标识符。
- 结论：模型把 code_search 当自然语言入口，BM25 命中依赖这种改写；这印证了 M3 之前
  不需要向量，同时也提示查询改写（T2-19）值得做。

### 观察 6：返回的路径与行号被直接采用
- 观察 3、4 的回答都直接引用了返回中的 src/auth/token.py:1-20 与 src/db/pool.py:1-8；
  返回头 scanned: 3 files / 3 chunks 与 index_status 报告一致。
- 结论：结果被采用，M1 出口判据「工具被调用 + 返回含正确文件与行号」成立。

### 观察 7：返回协议按工具分工
- code_search 的 READY 返回是纯文本：status / query / scanned / hits / ── path:lines。
- index_status 的成功返回是 JSON：{"status":"ready","db_schema":1}；模型在会话中多次调用它。
- 结论：与 PROJECT.md §3.5 的分工一致——code_search 文本，code_index / index_status JSON；
  状态与错误路径统一为纯文本（见「开发期发现并修复的缺陷」第 2 条）。

### 观察 8：整个验收过程中 stdout 无污染、错误不冒泡
- 会话未出现协议中断；内部失败（缺 CODERAG_ROOT、无索引）在自动化测试中都转为结构化
  状态而非 isError。
- 结论：RL-04（stdout 洁净）与 RL-09（异常不冒泡）的机制在真实连接下生效。

## 开发期发现并修复的缺陷

1. __main__.py 在 T1-08 重写时丢失 if __name__ == "__main__" 守卫，导致
   python -m dsh_coderag 静默无操作（控制台脚本不受影响）。修复：f0ca245。
2. code_search 的非就绪 / 错误返回是 JSON，与 PROJECT.md §3.5 的纯文本契约冲突。已统一为
   纯文本，并把动态值压成一行以防伪造 status 字段。修复：5ac9e1c。
3. code_search 的 description 与 §3.5 不一致（缺 Prefer this over grep…），这很可能是
   观察 1、3 里模型不首发检索的原因。修复：5ac9e1c。

## 已知限制与未验证事项

- 整句自然语言中文查询在精度模式下可能 empty（观察 2）；召回模式、查询改写与标点路由
  属 T2-19。
- code_search 的 path 与 max_tokens 参数尚未生效（T2 范围）。
- R5 只是部分缓解：已知确切标识符时模型仍可能先 grep（观察 1、3）。
- 本记录依赖人工在 DSH Web 上的观察，无法由 pytest 自动复现；工具调用细节来自会话回放。
- 观察来自单一模型与单机环境，样本量小，不能外推为普遍结论。

> **后续状态（2026-09-23）**：上面"已知限制与未验证事项"里两条**已不成立**——
> (a) `code_search` 的 `path` 与 `max_tokens` **已生效**（契约见 `PROJECT.md` §3.5，覆盖在
> `tests/test_path_filter.py` / `tests/test_token_budget.py`，属 T2 范围，已完成）；
> (b) 召回模式、查询改写与**标点路由已落地**：纯标点按 `ADR-13`（`PROJECT.md` §3.7）显式路由到
> `grep` 并返回结构化提示，**未使用 `porter`**、停用词可检索（`T2-19`，`5f02646`，16 例全绿），
> 精度/召回双模式与 2 字中文词召回由 `T3-13` 补齐（`e7d7624`，`tests/test_cjk_recall.py`）。
> **注意这不等于"中文自然语言检索已可用"**：纯中文原问句在大仓库上的 `natural` 桶 `S@5` 仍是
> **0.000**（L1，失败 100% 归因 `A5` 零词法重叠）——那是 M5 可选向量后端的目标，见 `ADR-14`/`ADR-15`。
> **本文件的其余限制仍然有效**（尤其"R5 只是部分缓解"与"单模型单机、样本量小"）。
