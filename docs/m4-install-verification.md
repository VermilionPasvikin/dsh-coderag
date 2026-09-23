# M4 安装验证

> 本文件归 `PROJECT.md` §6.4 的 **T4-06** 与 **T4-08** 共用：
> **T4-06** 验证「干净 profile 首次 `add` 不触发 pnpm 10+ 的 install-script 坑」（§2–§4）；
> **T4-08** 验证「在一个从未装过本项目的环境里从零安装，并跑通一次检索」（§5）。
>
> 验证环境：macOS、DSH `0.1.5-rc.1`、Node `v24.14.0`、pnpm `12.4.2`、Python `3.10.21`（forBSH）。
> 所有 dsh 命令均通过 `./scripts/dsh` 包装脚本执行（`AGENTS.md` E-07）。

## 1. 结论（T4-06：干净 profile 装载）

| 检查项 | 结果 | 依据 |
|---|---|---|
| 干净 profile 首次 `add .` 成功 | ✅ | 退出码 `0`，`Done in 5.3s using pnpm v12.4.2` |
| 输出里没有 install-script 相关报错 | ✅ | 无 `ERR_PNPM_*`、无 `allowBuilds`、无 `build script`、无 `prepare` |
| **不需要**给 pnpm 配 `allowBuilds` | ✅ | 干净 profile 的 `pnpm-workspace.yaml` 只有 `packages` / `nodeLinker` / `autoInstallPeers` 三项 |
| bundle 被登记为 profile 层 | ✅ | `dsh.profile.bundles` = `["@deepseek-ai/dsh-base", "dsh-coderag"]` |
| 该层能被组合进配置 | ✅ | `--dump-config` 出现 `# == dsh-coderag`（第 333 行）与 `- id: mcp-coderag`（第 334 行） |
| 从零（干净 `DSH_HOME`）开始 | ✅ | 用 `/tmp/dsh-coderag-t4-06`，profile `clean-test` 此前不存在 |

## 2. 方法：为什么用临时 `DSH_HOME`

坑是否触发，取决于 profile 目录下的 `pnpm-workspace.yaml` 里**有没有** `allowBuilds` 条目。
在开发者主目录里测没有意义——那里的 profile（`web` / `headless` / `coderag-dev`）可能早就配过。
所以本任务用一个**全新的 `DSH_HOME`**，profile 从模板新初始化：

```sh
rm -rf /tmp/dsh-coderag-t4-06
DSH_HOME=/tmp/dsh-coderag-t4-06 ./scripts/dsh plugin --profile clean-test add .
```

## 3. 实际输出

```text
dsh: initialized profile clean-test at /tmp/dsh-coderag-t4-06/profiles/clean-test
Already up to date

dependencies:
+ dsh-coderag link:../../../../../Users/vermi/个人项目/python/dsh-coderag

Update available! 12.4.2 → 12.5.1.
Changelog: https://pnpm.io/v/12.5.1
To update, run: curl -fsSL https://get.pnpm.io/install.sh | sh -
Done in 5.3s using pnpm v12.4.2
```

退出码 `0`。**没有** `ERR_PNPM_...`，**没有**任何关于 build script 的提示。

干净 profile 的 `pnpm-workspace.yaml`（`/tmp/dsh-coderag-t4-06/profiles/clean-test/pnpm-workspace.yaml`），
**没有任何 `allowBuilds`**：

```yaml
packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false
```

登记结果（同一 profile 的 `package.json`，节选）：

```json
{
  "dependencies": { "dsh-coderag": "link:/Users/vermi/个人项目/python/dsh-coderag" },
  "dsh": { "profile": { "bundles": ["@deepseek-ai/dsh-base", "dsh-coderag"], "patchReload": "live" } }
}
```

组合配置自检：

```sh
DSH_HOME=/tmp/dsh-coderag-t4-06 ./scripts/dsh --profile clean-test --dump-config | grep -n -A6 '^# == dsh-coderag'
```

```text
333:# == dsh-coderag
334:- id: mcp-coderag
335-  name: '@deepseek-ai/dsh-mcp-client'
336-  config:
337-    serverName: coderag
338-    transport: stdio
339-    command: !!js process.env.CODERAG_PYTHON ?? '/opt/anaconda3/envs/forBSH/bin/python'
```

（退出码 `0`，stderr `0` 字节。）

## 4. 那个坑本身：pnpm 10+ 与 `allowBuilds`

pnpm 10+ **默认拒绝执行依赖的 install / build script**。装到带 script 的插件（典型是 git-hosted
且带 `prepare` 的包）时，pnpm 直接失败，本项目在 `T3-00` 实测到的报错原文是：

```text
Error: ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED

  × adding a new package
  ╰─▶ The git-hosted package "dsh-eval-harness@0.4.0" needs to execute build scripts but is not in the "allowBuilds" allowlist.
  help: Add the package to "allowBuilds" in your project's pnpm-workspace.yaml to allow it to run scripts. For example:
        allowBuilds:
          dsh-eval-harness@https://codeload.github.com/.../tar.gz/<commit>: true
```

**这个坑对本项目不适用**：本 bundle 不含任何 install script，`package.json` 连 `scripts` 段都没有，
打包出来的 tarball 只有 `LICENSE` / `README.md` / `cordis.patch.yml` / `package.json`（`T4-01` 实测）。
没有 script，pnpm 就没有可拒绝的东西——所以上面干净 profile 的首次 `add` 直接通过，
**不需要预先配置 `allowBuilds`**。

**为什么要在这里写它**：`dsh plugin add` 在 pnpm 非零退出时会**跳过 bundle 登记**（`AGENTS.md` E-05）——
插件看起来装上了，但永远不会加载。用户如果因为**其它**带 script 的插件踩过这个坑，会先去怀疑本项目，
所以 README 的「安装故障排查」把这个坑写清楚：它长什么样、怎么绕过、以及怎么确认自己的 bundle
**真的被登记了**（`--dump-config` 里有没有属于自己的那一层）。

## 5. T4-08：从零安装并跑通一次检索

### 5.1 结论

| 检查项 | 结果 | 依据 |
|---|---|---|
| 全新 `DSH_HOME` + 全新 profile 从零安装 | ✅ | `/tmp/dsh-coderag-t4-08`；profile `clean-test` 此前不存在；`add .` 退出码 `0` |
| MCP 握手成功 | ✅ | `serverInfo {name: coderag, version: 0.1.0}` |
| 4 个工具可见 | ✅ | `tools [code_search, code_outline, code_index, index_status]` |
| 在**零索引**工作区索引成功 | ✅ | `code_index` 立刻返回 `taskId`；`index_status` 走到 `ready`（3 files / 7 chunks） |
| `code_search` 返回可用结果 | ✅ | `status: ready`、`hits: 1`，命中 `src/auth/token.py:1-6 [module]` |
| stdout 只有协议内容 | ✅ | 每一行 stdout 都能 `json.loads`；日志 2 行落在 stderr（`AGENTS.md` RL-04） |
| 索引写在**工作区内** | ✅ | `/tmp/dsh-coderag-t4-08-ws/.coderag/index.sqlite3`（`S-03`） |
| 工具不返回 `isError` | ✅ | 4 次 `tools/call` 的 `isError` 全为 `false`（RL-09） |

### 5.2 方法

**零状态**：先删掉 `/tmp/dsh-coderag-t4-08*`；把 `examples/demo-workspace` 的**源码**复制成新工作区
（`rsync --exclude .coderag`），因此工作区里**没有任何索引**；DSH 侧是全新的 `DSH_HOME`。

**驱动方式：不经过模型。** 按 `--dump-config` 里那一行**原样**启动子进程，再把工作区通过
`config.env` 传进去（E-02）：

```sh
# patch 的 config.command + config.args
/opt/anaconda3/envs/forBSH/bin/python -c 'import dsh_coderag.server as s; s.run()'
# patch 的 config.env
CODERAG_ROOT=/tmp/dsh-coderag-t4-08-ws
```

然后在 stdin/stdout 上说换行分隔的 JSON-RPC（与内置包 `@deepseek-ai/dsh-mcp-client` 的 stdio
传输同一套协议），依次：`initialize` → `notifications/initialized` → `tools/list` →
`tools/call code_index` → 轮询 `tools/call index_status` → `tools/call code_search`。

### 5.3 实际输出（原始报文，长响应以 `…` 省略）

```text
>>> {"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t4-08-probe", "version": "0.1.0"}}}
<<< {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"experimental":{},"tools":{"listChanged":false}},"serverInfo":{"name":"coderag","version":"0.1.0"}}}

>>> {"jsonrpc": "2.0", "method": "notifications/initialized"}
>>> {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
<<< {"jsonrpc":"2.0","id":2,"result":{"tools":[ … 4 条 … ]}}
--- tools --- ['code_search', 'code_outline', 'code_index', 'index_status']

>>> {"jsonrpc": "2.0", "method": "tools/call", "id": 3, "params": {"name": "code_index", "arguments": {}}}
<<< … "text":"{\"taskId\": \"idx-20260923-5fc3\", \"state\": \"pending\", \"hint\": \"Poll index_status with this taskId.\"}" … "isError":false}

>>> {"jsonrpc": "2.0", "method": "tools/call", "id": 4, "params": {"name": "index_status", "arguments": {"task_id": "idx-20260923-5fc3"}}}
<<< … "text":"{\"taskId\": \"idx-20260923-5fc3\", \"state\": \"running\", \"total_files\": 0, …}" … "isError":false}

>>> {"jsonrpc": "2.0", "method": "tools/call", "id": 5, "params": {"name": "index_status", "arguments": {"task_id": "idx-20260923-5fc3"}}}
<<< … "text":"{\"taskId\": \"idx-20260923-5fc3\", \"state\": \"ready\", \"total_files\": 3, \"done_files\": 3, \"total_chunks\": 7, \"done_chunks\": 7, \"message\": null}" … "isError":false}

>>> {"jsonrpc": "2.0", "method": "tools/call", "id": 6, "params": {"name": "code_search", "arguments": {"query": "用户令牌在哪里校验", "limit": 5}}}
<<< … "isError":false}

!! child exit code: 0
```

`code_search` 交给模型的文本：

```text
status: ready
query: "用户令牌在哪里校验"
scanned: 3 files / 7 chunks
hits: 1 (sorted by source order)
skipped: 0

── src/auth/token.py:1-6  [module]  (chunk 0)
"""Token verification for the demo workspace.

用户令牌在哪里校验？答案就在本模块的 verify_token。
"""

from __future__ import annotations
```

子进程 stderr（日志，纯 JSON-Lines；stdout 侧一行都没有）：

```text
{"ts": 1790143305.225813, "level": "info", "event": "index_start", "task_id": null, "duration_ms": null, "root": "/private/tmp/dsh-coderag-t4-08-ws"}
{"ts": 1790143305.229207, "level": "info", "event": "index_done", "task_id": null, "duration_ms": 3.290792000143483, "files": 3, "chunks": 7, "skipped": 0, "redacted": 0}
```

### 5.4 这次验证**不**覆盖什么

- **没有经过模型**：探针直接调工具，证明的是「装完之后工具真的可用、返回结构化结果」，
  **不**证明「模型会用得好」。后者是 L2 A/B 的范畴（`docs/eval-report-m3.md`）。
- **命中是易例**：`用户令牌在哪里校验` 在这个刻意构造的 demo 工作区里与 `token.py` 的 docstring
  有 bigram 重叠，属于"有词法线索"的情形。**纯中文自然语言在大仓库上仍是 `S@5 = 0.000`**
  （L1 的 `natural` 桶）——这条限制没有因为本任务而改变。
- **从 registry 安装**：只验证了 `add .`（本地路径）；npm 包尚未发布。
- **非 macOS / 非 conda**：Python 侧只在 forBSH（conda，Python 3.10.21）上实测过。
