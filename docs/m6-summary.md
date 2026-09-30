# M6 结项记录：跨平台支持（v2.1.0 / v2.1.1）

> **本文是 M6 的当前状态**。M6 的其他三份文档各有分工：
> [`m6-crossplatform-baseline.md`](m6-crossplatform-baseline.md) 是 `T6-01` 的**当时快照**
> （它按平台列出「已核实 / 未验证」，并把未验证项**移交**给后续任务），
> [`m6-macos-verification.md`](m6-macos-verification.md) 与
> [`m6-windows-smoke.md`](m6-windows-smoke.md) 是两平台的实跑记录。
> **快照里的读数不改写**；要问「M6 最终确认了什么」，看本文。

**收尾日期**：2026-09-30 ｜ **任务**：`T6-01` … `T6-12`（全部已完成）
**发布物**：`v2.1.0`（tag → `7ea1823`）、`v2.1.1`（tag → `6b88e20`），**都只发布在 GitHub**，
PyPI 与 npm 上没有任何版本。

---

## 1. 出口判据逐条对账（`PROJECT.md` §6.0）

| 判据 | 状态 | 证据（实测读数 / 指针） |
|---|---|---|
| `T6-01` 基线审计把「已核实 / 未验证」**按平台分开**记录 | ✅ | [`m6-crossplatform-baseline.md`](m6-crossplatform-baseline.md)：四项事实（wheel / FTS5 / 离线 grammar / MCP 子进程）逐平台成表，未验证项逐条写明归哪个任务 |
| `T6-02` Python CLI 成为**唯一跨平台入口**（两份 shell 脚本退为薄包装） | ✅ | `dsh-coderag doctor` 与 `install-deps` 承接原 `install.sh` 的 239 行逻辑；`scripts/install.sh` 38 行、`scripts/dsh` 31 行，只做「找解释器 → 转发」；退出码 `0` / `1`（操作失败）/ `2`（环境不可用），失败一律是**结构化 JSON** |
| `T6-05` 实测结论对齐进 README，且**未实测的平台不得声称支持** | ✅ | README 的安装章节分 `macOS / Linux` 与 `Windows` 两段；平台状态 = **实测清单**（macOS 26.4 + Windows 10 26100）；**Linux 明写「未实测、不声称支持」**；`docs/architecture.md` 同步 |
| `T6-06` v2.1.0 打 tag 发布（仅 GitHub） | ✅ | `dsh-coderag 2.1.0`；`git ls-remote` 得 `refs/tags/v2.1.0`；`CHANGELOG` 的 `[2.1.0]` 条目；**无 PyPI / npm 动作** |
| 附加：**不放宽 `RL-10`** | ✅ | `dependencies` 仍为 `mcp` / `tree-sitter` / `tree-sitter-language-pack` / `pathspec` **四个**，不含 numpy；numpy 只作可选 extra `semantic` 的声明住所 |
| 附加：**不降低 macOS 的既有验收** | ✅ | `T6-03b` 在 macOS 上全量复跑 `567 passed, 5 skipped`，**0 failed / 0 xfail**；`T6-08` 在含 `T6-07` 修复的 `98186cf` 上复跑 `570 passed, 5 skipped` |

## 2. 最终平台矩阵（**只写实跑过的**）

| 平台 | 被声称支持？ | 依据的实跑 | 读数 |
|---|---|---|---|
| **Windows 10（26100，`win_amd64`）** | ✅ 是 | `T6-03a` / `T6-03b` / `T6-04` / `T6-07` / `T6-10` / `T6-11` 与本地多次复跑 | 全量 `576 passed, 2 skipped`（收集总数 **578**）；`doctor` / `install-deps` 可用；端到端冒烟（全新解释器 + 全新 `DSH_HOME` + `dsh plugin add` + 真实 `code_search` 命中 `src/auth/token.py`）通过 |
| **macOS 26.4** | ✅ 是 | `T6-03b`（`e9dcb2f`）、`T6-08`（`98186cf`） | `T6-03b`：`567 passed, 5 skipped`；`T6-08`：`570 passed, 5 skipped`；两者均 **0 failed / 0 xfail** |
| **Linux** | ❌ **不声称** | **没有任何实跑** | — |

**两平台读数为什么相差 3**：`tests/test_path_filter.py` 的
`test_path_filter_accepts_windows_style_separators` 是**平台守卫的参数化用例**（3 个参数）。
Windows 跑这 3 条、macOS 跳过这 3 条，另有 2 条语料 opt-in 用例两侧相同。
因此 `T6-08` 那次是 `573 + 2 = 575`（Windows）与 `570 + 5 = 575`（macOS），**收集总数一致** ——
这是「同一份逻辑跨平台」在测试层面可验证的形式。

## 3. 仍未验证的边界（**M6 收尾后依然成立**）

| # | 边界 | 说明 |
|---|---|---|
| 1 | **Linux 四项全未实测** | 实际安装、FTS5、离线 grammar、MCP 子进程拉起——没有 Linux 机器，**一项都没跑过**，因此 README 与 `docs/architecture.md` 都不声称支持 |
| 2 | **macOS 的全量实跑停在 `98186cf`** | 其后的 `T6-10`（改开发工具 `scripts/verify-plan.py`、`tests/test_server.py` 无关）与 `T6-11`（加 `.gitattributes` + 一条仓库卫生测试）**未在 macOS 上复跑**。判断依据（不是实测）：新增的是**开发工具与仓库属性**，`scripts/` 与 `tests/` **不进分发物**（`pip show -f dsh-coderag` 只列包内文件；bundle 的 `files` 只有 `cordis.patch.yml`），且 `.gitattributes` 把脚本钉成 LF 在 POSIX 上本来就是 LF——但**这一条按 `AGENTS.md` §5.1 只能说「未验证」** |
| 3 | **`RL-10` 的「默认安装不装 numpy」只有 Windows 证据** | macOS 侧用的是 forBSH 环境，里面**装着** numpy（那是跑向量用例的前提），所以 macOS 不提供这条证据 |
| 4 | **没有任何一个 DSH 版本被两平台都跑过** | macOS 实测用 DSH `0.1.5-rc.1`（项目钉的），Windows 用本机自带 `0.2.0-rc.2`；「插件登记 + `dump-config` + 拉起」这一环在两平台上各自通过，但**不是同一版本** |
| 5 | **Windows 上无 `pwsh`** | 本机只有 Windows PowerShell 5.1.26100.5074，因此 PowerShell 7 与 5.1 的差异没有对照；README 的 Windows 命令只保证在 5.1 上实跑过 |
| 6 | **模型侧的工具采纳未复跑** | `T1-15` 那一环（模型是否调用、是否采用检索结果）在 M6 里没有重测；M6 的改动都在入口与配置面，`EVAL.md` 的 L2 结论仍来自 M5 那次 |
| 7 | **`--dump-config` 不求值 `!!js`** | 因此它不能直接证明 `CODERAG_PYTHON` 覆盖已生效；覆盖的作用改由**端到端实跑**证明（`T6-04` 的真实 `code_search` 走的正是被覆盖的解释器） |

## 4. 交付物

| 交付物 | 位置 | 说明 |
|---|---|---|
| 跨平台入口 CLI | `src/dsh_coderag/__main__.py` | `doctor`（探测解释器、按 `requires-python` 校验版本、预检 FTS5、打印可复制的 `CODERAG_PYTHON`）与 `install-deps`（安装 + 装后自检：FTS5 可用 + 中文 bigram 往返） |
| 薄包装 | `scripts/install.sh`（38 行）/ `scripts/dsh`（31 行） | 只做「找到解释器 → 转发」；三个平台因此走**同一条代码路径**，而这条路径被 `pytest` 直接覆盖 |
| 依赖wheel 齐备 | `pyproject.toml` | 4 个直接依赖 + 完整传递闭包在 `win_amd64` 上**零源码编译**（`T6-01` 实测） |
| 惰性导入 | `src/dsh_coderag/__init__.py` | PEP 562：`index_sync` / `search` 按需导入，使 `doctor` / `install-deps` 在**第三方 wheel 尚未安装**时也能跑 |
| 计划门禁 | `scripts/verify-plan.py` / `scripts/test-verify-plan.py` | 新增 **`G1`**（§6.7 每行必须 5 列，按未转义竖线计数）与对应变异用例；两者现在**都能在 Windows 上跑**（后者此前会因 cp936 解码崩溃）；共 **29 项检查 / 20 个变异** |
| LF 保证 | `.gitattributes` + `tests/test_script_eol.py` | `*.sh` 与 `scripts/dsh` 钉成 `eol=lf`；保证从「写文件的人恰好写了 LF」变成**仓库的属性** |
| 文档 | `README.md` / `docs/architecture.md` / 本目录四份 `m6-*.md` | README 的安装与配置**按平台**给出可照抄的命令（含 Windows 的 `$py` / `$dsh` 取法与 Store 占位符陷阱）；配置表标明**每个变量是否真的生效** |

## 5. 发布状态

| tag | 指向 | 内容 |
|---|---|---|
| `v2.0.0` | `620767d` | 默认路径的实测提升；可选向量路径按 `V4` 不发布 |
| `v2.1.0` | `7ea1823` | 跨平台支持：Python CLI 成为唯一入口；实测平台 = macOS + Windows。**该版本的 README 如实把 5 个受影响的配置变量标注为「未生效」** |
| `v2.1.1` | `6b88e20` | 补丁：把 `CODERAG_MAX_FILES` / `_MAX_TOKENS` / `_MAX_FILE_BYTES` / `_BATCH_SIZE` / `_MAX_WORKERS` 真正接进 MCP 路径（`T6-07`），并补 3 条**在修复前会红**的测试 |

**没有任何一个版本发布到 PyPI 或 npm**；安装方式始终是「克隆 + 装 Python 包 + `--patch` / `plugin add`」。

## 6. 结项后仍然开着的条目（`docs/backlog.md`）

以下条目**不影响 M6 的出口判据**，只是如实列出：

- **分块器**：gap 块没有 `MAX_CHUNK_LINES` 上限；TS `type` 别名与 `const` / 箭头函数未纳入声明（`T2-18` 抽检发现）。
- **检索**：`index_status` 每次重新遍历工作区（`T2-17`）；仅共享一个通用词的 query 会被误判成 `A1`（`T3-14` 复测）。
- **文档结构**：README 与 `AGENTS.md` `D-03` / `D-05` 的偏离（有无 `## 已知限制` 小节）——**等所有者裁决**，M6 未擅自改。
- **出范围任务**：`T5-15` / `T5-16` / `T5-20` / `T5-22` 仍按 2026-09-25 的裁决留在 2.0.0 范围之外。
- **`pwsh` 缺失**（见 §3 第 5 条）：本机无法对照 PowerShell 7。

## 7. 一句话

M6 确认的是：**同一份入口逻辑在 Windows 与 macOS 上都装得上、跑得起来、也能被 DSH 拉起**，
且两平台的测试收集总数一致；**Linux 完全没有实测，因此不在支持声明里**。
`v2.1.1` 之后 `main` 上再有的改动都只涉及开发工具与仓库属性，**不影响发布物**。
