# ADR-18：默认路径的工具采纳率（MCP `initialize` instructions）

- **状态**：已接受（2026-10-31，任务 `T8-12`）
- **关系**：细化 `ADR-01`（MCP 接入）与 `ADR-05`（结果顺序）；不改工具集（`ADR-03`）、不改安全过滤（`ADR-08`）
- **一句话**：工具已可用，但默认提示下模型不调用；在不修改 DSH 的前提下，通过 MCP `initialize` 发布**短、硬、带动作顺序**的 instructions，把默认路径的采纳率从 `0/13` 提升到 `10/13`，并把「工具在首个请求之后才挂载」记为宿主的已知限制。

## 1. 触发事实

2026-10-30 的 5 个默认提示评测组（13 条 L2；A 无工具、B 仅 BM25、C 云端向量）中，`code_search` 的调用次数**全部是 0/13**；同一批用例在「prompt 硬性要求先调用 `code_search`」的强制变体里可以 **13/13 通过**。因此不是工具坏了，而是默认路径下模型不采纳。

取证结果（本次未改 DSH 代码，只读其会话日志与源码）：

| 观察 | 事实 |
|---|---|
| 首请求工具数（CLI 评测会话） | **25 个内置工具，无 `mcp__coderag__*`**；第 2 步才变成 32 个（新增 4 个工具 + 3 个资源工具） |
| 首请求工具数（桌面会话） | **66 个，无 coderag**；第 3 个请求才 73 个（+7） |
| 我们的 MCP 服务启动耗时 | `initialize` **0.22 s**、`tools/list` **1 ms**（本地实测）→ 延迟不在服务端 |
| DSH 基座提示原文 | `Use the grep tool — not shell grep or rg — to search file contents. Use read on a matched file when you need surrounding context.` |
| instructions 是否送达 | 送达：`initialize` 的 `instructions` 在 step ≥ 2 的 system prompt 里渲染为 `### MCP server: coderag` 段 |
| 探针（3 条用例，无 instructions） | `0/3` 调用，`0/3` 通过 |
| 探针（3 条用例，第二版 instructions） | `2/3` 调用，`2/3` 通过 |
| 探针（3 条用例，当前「FIRST tool」措辞） | **3/3 调用，3/3 通过** |

结论：**工具在第一个模型请求时并不存在**，模型先用 `grep`/`read` 起步；等到工具挂载，它是否回头再调用 `code_search` 取决于提示的明确程度。这是采纳率问题的两个组成部分：宿主的挂载时机（不可由插件改变）+ 我们的提示强度（可改变）。

## 2. 决策

1. **发布 MCP `initialize` instructions**（`src/dsh_coderag/server.py` 的 `SERVER_INSTRUCTIONS`），措辞必须包含三件事：
   - 何时：任何「代码在哪 / 行为如何实现 / 涉及哪些文件」的问题；
   - 顺序：把 `mcp__coderag__code_search` 作为**第一个**工具，在 `bash`/`grep`/`read` 之前，即使已经跑过 `grep`；
   - 边界：`grep` 只用于精确字符串或正则，且应在 `code_search` 之后。
   同时保留一条 `code_outline` 与 `index_status` 的使用提示，避免只把模型引向 `code_search`。
2. **保持四个工具的描述不变**（`ADR-03`）；只把 `PROJECT.md` §3.5 里与代码不一致的旧文案同步为实际描述（文档漂移修正）。
3. **不修改 DSH**：首请求缺工具属于宿主行为（其 README 声称工具在首轮之前出现，实测不是）。本仓只记录，不绕道（不改基座 prompt、不做 prompt 注入、不重命名工具）。
4. **评测协议**：默认组必须同时报告 `code_search` 采纳数；强制变体继续用于「只看检索质量」的因果对比，不得再用强制变体的数字冒充默认路径。

## 3. 验收（2026-10-31，13 条 L2，云端 qwen3.7，`trials=1`）

命令（与 `T8-11` 的归档报告同口径）：

```bash
CODERAG_SEMANTIC=on CODERAG_SEMANTIC_BACKEND=openai \
CODERAG_SEMANTIC_URL=... CODERAG_SEMANTIC_MODEL=qwen3.7-text-embedding \
CODERAG_SEMANTIC_ALLOW_REMOTE=1 CODERAG_SEMANTIC_API_KEY=... \
CODERAG_ROOT=/Users/vermi/projects/dsh CODERAG_PYTHON=$PWD/.venv/bin/python \
.venv/bin/python scripts/ab_eval.py run --cases cases --group cloud-c-instructions \
  --out eval/runs/cloud-c-instructions --workspace /Users/vermi/projects/dsh \
  --profile eval-coderag --patch "$PWD/cordis.patch.yml" \
  --trials 1 --timeout 420 --dsh "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"
```

| 指标 | 基线（无 instructions） | 本次（有 instructions） |
|---|---|---|
| 任务成功 | 4/13（30.8%） | **10/13（76.9%）** |
| 调用过 `code_search` 的用例 | 0/13 | **10/13**（共 12 次调用） |
| 要求调用 `code_search` 的 9 条用例中的采纳 | 0/9 | **7/9** |
| token 总量 / 中位 | 2,632,790 / 75,212 | 4,221,598 / 110,413 |
| 超时 | 0 | 0 |

未采纳的两条：`locate-repeat-tool-reminder`（3 步、0 调用）、`locate-tool-timeout-default`（5 步、0 调用）。另有一条 `crossfile-todo-snapshot` 虽调用了 2 次 `code_search`，但跑到 43 步（2.34M tokens）后超过 `max_steps=16` 失败——这是 agent 的循环问题，不属于采纳问题，已单独记录。

## 4. 被否决的方案

| 方案 | 否决理由 |
|---|---|
| 改 DSH 基座的 grep 指令，让它先提 MCP | 本仓不修改 DSH（`RL-01`、`R6`）；且这是所有 MCP 服务共有的问题，应由宿主解决 |
| 重命名/新增工具（如 `grep`、`search_code`） | `RL-05` 固定四个工具；重名还会与宿主工具冲突 |
| prompt 注入或 `ctx.systemPrompt.section()` | `E-03` 明确禁止 system-prompt 型注入（会被静默丢弃）；MCP instructions 是协议内、宿主支持的通道 |
| 删除标点查询的 grep 路由（`ADR-13`） | 会破坏 `(`、`::`、`->` 的可用路径 |
| 在默认评测里保留「强制先调用」的 prompt | 会把「模型自己会不会用」这个事实抹掉；强制变体只能作为检索质量的对照 |
| 等宿主修好首请求挂载再动手 | 采纳率可部分改善（实测 0→10/13），不值得等；且修好后本决策仍成立 |

## 5. 回滚

删除 `SERVER_INSTRUCTIONS` 常量与 `Server(instructions=...)` 参数、回退测试快照即可；不涉及数据库、索引格式或对外 API，回滚无迁移成本。

## 6. 未验证 / 诚实限制

- **单模型**：只测了 `deepseek-flash`（`reasoningEffort: high`）；其他模型/provider 的采纳率未知。
- **单语料**：只测 `/Users/vermi/projects/dsh`（3,967 文件 / 63,046 chunks）。
- **样本量**：13 条 × 1 trial；强、弱提示之间的差异不能当作统计显著结论。
- **宿主差异**：桌面会话的首请求工具数（66）与 CLI（25）不同，说明挂载时机受启动路径影响；未来 DSH 版本若修正「首请求即含 MCP 工具」，本 ADR 的验收数字需重测。
- **副作用**：instructions 增加了 system prompt 的固定开销（约 490 字符）；token 总量上升主要来自更多成功检索与一次 43 步失控用例，不是 instructions 本身。
- **未验证的替代措辞**：更短的版本、只保留一句「先 code_search」的版本，可能同样有效但更省 token；未逐一对比。
