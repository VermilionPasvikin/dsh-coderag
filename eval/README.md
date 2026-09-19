# 检索质量评测集格式

> 依据 `EVAL.md` §2.2（字段格式）、§2.3（三类任务与配比）、§2.4（构造流程）、
> §2.9（答案泄漏陷阱）与 `PROJECT.md` §6.3 的 T3-01。
>
> 本目录从 T3-01 开始只放**纯数据与说明**。后续 `T3-03` 会在
> `src/dsh_coderag/eval/` 实现读取、校验、运行与报告；评测逻辑本身不放在这里。

## 文件

| 文件 | 作用 |
|---|---|
| `eval/schema.json` | 单条评测任务的 JSON Schema（Draft 2020-12） |
| `eval/tasks.jsonl` | 冻结的 golden 评测集；每行一个 JSON 对象，由 T3-02a 创建 |
| `eval/tasks.next.jsonl` | 调参期间发现、但本轮不允许修改 golden 集时的新 case 暂存区（EVAL.md §2.9 陷阱 3） |
| `eval/tasks.meta.json` | 文件级元数据（含 `golden_version`）；由 `T3-04d` 落地版本校验时创建 |

## `tasks.jsonl` 的每行字段

字段约束由 `eval/schema.json` 强制；`scripts/verify-tasks.py`（T3-02a 产出）还要额外校验
路径存在性与“无答案泄漏”。

| 字段 | 必填 | Schema 约束 | 语义 |
|---|---|---|---|
| `id` | ✅ | `^L-[0-9]{3}$` | 稳定 ID；在 golden 集内唯一 |
| `class` | ✅ | `exact` \| `crossfile` \| `natural` | 诊断桶，必须分桶报告 |
| `query` | ✅ | 非空字符串 | 用户会真实输入的查询 |
| `expect_paths` | ✅ | 非空、去重的工作区相对路径数组 | 前 k 条命中其中任意一个即 Success@k |
| `expect_symbols` | ❌ | 非空、去重字符串数组 | 可选符号级约束；不要用文件名冒充符号 |
| `must_not_paths` | ❌ | 非空、去重的工作区相对路径数组 | 精度保护；命中即该条判 0 |
| `notes` | ❌ | 字符串 | 设计理由，不参与自动判分 |
| `added` | ✅ | `YYYY-MM-DD` | 进入 golden 集的日期 |

JSONL 示例：

```json
{"id":"L-001","class":"exact","query":"retry_call","expect_paths":["src/net/retry.py"],"expect_symbols":["retry_call"],"must_not_paths":[],"notes":"直接搜精确标识符，作为 regression 桶","added":"2026-09-19"}
```

**不要**把 `golden_version` 塞进每一行。它描述整份文件，重复 30 次只会制造漂移风险；
按 `EVAL.md` §2.7，`T3-04d` 将把它放在 `eval/tasks.meta.json` 中，并在版本不匹配时直接失败，
除非显式 `--rebaseline`。

## 配比

第一批 A 批（`T3-02a`）只做 10 条：

| class | A 批条数 | 最终 30 条目标 |
|---|---:|---:|
| `exact` | 4 | 12 |
| `crossfile` | 4 | 11 |
| `natural` | 2 | 7 |
| **合计** | **10** | **30** |

比例按**诊断价值**而不是真实使用频率确定。`exact` 是 regression 桶，应接近满分；
`natural` 才是向量价值的判定桶。不要为了好看的均值调整配比。

## 构造硬规则

1. `query` 里绝对不能出现 `expect_paths` 的文件名、路径片段或 `expect_symbols` 的符号名。
2. `exact` 类的标识符必须真实存在于 `expect_paths` 指向的代码中。
3. `natural` 类的 query 描述“行为/意图”，一个标识符都不要有。
4. 每条都必须是“我确实想知道答案”的问题；不要从 commit / PR 反推 ground truth。
5. 不要只挑好找的。评测集的价值来自它抓到的失败。
6. `expect_paths` 必须是工作区相对路径、真实存在，并且用 `/` 分隔。
7. 新 case 先进 `tasks.next.jsonl`；冻结的 `tasks.jsonl` 在调参期间禁止修改（`EVAL.md` §2.9）。

## 校验

Schema 本身：

```sh
python3 -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('eval/schema.json'))); print('schema OK')"
```

A 批任务数据（由 T3-02a 提供脚本）：

```sh
python3 scripts/verify-tasks.py eval/tasks.jsonl <被评测仓库>
```

该脚本除 schema 外还会检查：

- `expect_paths` / `must_not_paths` 指向的文件是否真实存在；
- `query` 是否泄漏 `expect_paths` 路径片段或符号名；
- `id` 是否重复；
- 批次 class 配比是否符合 T3-02a 的约定。
