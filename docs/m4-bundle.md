# M4 bundle：可分发的 DSH 插件层

> 对应 `PROJECT.md` §6.4 的 **T4-02**——把 `T1-14` 的 `cordis.patch.yml` 从"本地开发 overlay"
> 升级为"可分发 bundle patch"。本文件记录**实际执行结果**，不是预期。
>
> 验证环境：DSH `0.1.5-rc.1`、Node `v24.14.0`、pnpm `12.4.2`、Python `3.10.21`（forBSH）。
> 所有 dsh 命令均通过 `./scripts/dsh` 包装脚本执行（`AGENTS.md` E-07）。
> 未发布到任何 registry；本任务验证的是**本地路径安装**（`add .`）。

## 1. 结论摘要

| 检查项 | 结果 | 证据 |
|---|---|---|
| `dsh plugin --profile coderag-dev add .` 能把本仓库登记为 profile 层 | ✅ | pnpm 退出 0，无 install script 报错；`dsh.profile.bundles` 由 `["@deepseek-ai/dsh-base"]` 变为 `["@deepseek-ai/dsh-base", "dsh-coderag"]` |
| `dsh --profile coderag-dev --dump-config` 输出本插件的层 | ✅ | 出现 `# == dsh-coderag` 分组 |
| 该层里的 MCP 行正确 | ✅ | 出现 `- id: mcp-coderag` / `name: '@deepseek-ai/dsh-mcp-client'`，`serverName: coderag`，`transport: stdio` |
| 分发内容不依赖 install script（`AGENTS.md` E-05 / C11） | ✅ | 仓库无 `scripts` 段，tarball 只有 `LICENSE` / `README.md` / `cordis.patch.yml` / `package.json`（`T4-01` 实测） |
| 分发内容不含 JS 入口 | ✅ | `package.json` 的 `main` / `bin` / `scripts` 全为 `undefined`；patch 只引用内置包 `@deepseek-ai/dsh-mcp-client` |
| 干净 profile 的端到端验证 | ⏳ 属 `T4-08` | 本任务用 `coderag-dev`；`T4-08` 在一个从未装过本项目的 profile 中复验 |
| 从 registry 安装 | ⏳ 未发布 | 本任务只证明本地路径可装载 |

## 2. 分发形态

两个文件构成一个完整的 DSH bundle：

| 文件 | 作用 |
|---|---|
| `package.json` | npm 清单。`dsh.bundle.patch: "./cordis.patch.yml"` 声明这是 bundle；`files: ["cordis.patch.yml"]` 只放行 patch |
| `cordis.patch.yml` | 唯一的装载内容。一个 `insert` 条目，插入 `mcp-coderag`（引用内置包 `@deepseek-ai/dsh-mcp-client`） |

同一个 `cordis.patch.yml` 也充当本地开发 overlay（`./scripts/dsh web --patch ./cordis.patch.yml`）。
两种用法指向同一份配置，不存在"开发版 / 分发版"两份文件的漂移。

DSH 侧的两段行为（已在安装的 `0.1.5-rc.1` 源码中核实）：

1. **解析 patch 路径**：`dsh-app-boot` 按 `join(packageDir, declared)` 解析，即相对**包目录**，
   不是相对 CWD。
2. **登记为层**：`dsh plugin` 是一条 pnpm 转发器——它先初始化 profile，再在 profile 目录里跑
   `pnpm add <参数>`，然后**按已安装状态**（而不是按依赖 diff）重建 `dsh.profile.bundles`：
   解析出的包只要声明了 `dsh.bundle` 就加入层列表。因此命令行上的 `path` / `link:` / `file:` /
   git 规格都会以其**真实包名**（`dsh-coderag`）被登记。

## 3. 验收（T4-02）

### 3.1 登记插件

```sh
./scripts/dsh plugin --profile coderag-dev add .
```

实际输出（完整）：

```text
dsh: initialized profile coderag-dev at /Users/vermi/.dsh/profiles/coderag-dev
Already up to date

dependencies:
+ dsh-coderag link:../../../个人项目/python/dsh-coderag

Update available! 12.4.2 → 12.5.1.
Changelog: https://pnpm.io/v/12.5.1
To update, run: curl -fsSL https://get.pnpm.io/install.sh | sh -
Done in 1.7s using pnpm v12.4.2
```

退出码 `0`。**没有** `ERR_PNPM_...`、**没有** install script 被拦截的警告——因为本 bundle
不含任何 `scripts`（`AGENTS.md` E-05 / C11 从根上不适用）。

登记后 profile 清单（`~/.dsh/profiles/coderag-dev/package.json`，节选）：

```json
{
  "dependencies": { "dsh-coderag": "link:/Users/vermi/个人项目/python/dsh-coderag" },
  "dsh": { "profile": { "bundles": ["@deepseek-ai/dsh-base", "dsh-coderag"], "patchReload": "live" } }
}
```

`dsh-coderag` 已由 pnpm 写入 `dependencies`，并被 reconciler 追加进 `bundles`。

### 3.2 组合配置

```sh
./scripts/dsh --profile coderag-dev --dump-config
```

实际输出：先 `# == @deepseek-ai/dsh-base`（约 120 条内置行），随后本插件自成一层。关键段：

```yaml
# == dsh-coderag
- id: mcp-coderag
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: coderag
    transport: stdio
    command: !!js process.env.CODERAG_PYTHON ?? '/opt/anaconda3/envs/forBSH/bin/python'
    args:
      - '-c'
      - import dsh_coderag.server as s; s.run()
    env:
      CODERAG_ROOT: !!js process.env.CODERAG_ROOT ?? process.cwd()
```

退出码 `0`，stderr 无输出（没有 patch 应用警告）。

**期望结果的逐项对应**：

- "输出中出现本插件的层" → `# == dsh-coderag`（层标签取自**包名**，不是文件名）。
- "出现 `mcp-coderag` 行" → `- id: mcp-coderag`。
- 两条必须同时出现才算通过：只有层、没有 `mcp-coderag` 说明 patch 未展开；
  只有 `mcp-coderag`、没有层说明它来自 `--patch` overlay 而不是 bundle。

## 4. 自检清单

| # | 检查 | 依据 | 状态 |
|---|---|---|---|
| 1 | patch 只引用**内置包**，bundle 内无自研 JS | `PROJECT.md` §1.6.1 | ✅ `@deepseek-ai/dsh-mcp-client` |
| 2 | 无 install script（pnpm 10+ 拒绝执行会导致"装了不加载"） | `E-05` / C11 | ✅ `scripts` 为 `undefined` |
| 3 | 解释器路径可被环境变量覆盖 | `E-06` | ✅ `CODERAG_PYTHON` |
| 4 | 需要传给子进程的配置走 `config.env`（stdio 环境被清洗） | `E-02` | ✅ `CODERAG_ROOT` |
| 5 | bundle 不向 stdout 写任何非协议内容 | `RL-04` | ✅ 由 Python 侧保证，本层不注入 |
| 6 | 不新增/删除 MCP 工具 | `RL-05` | ✅ 4 个，本层只挂载服务器 |
| 7 | 不写工作区之外的索引文件 | `S-03` | ✅ 索引固定 `<root>/.coderag/index.sqlite3` |
| 8 | patch 解析相对包目录，与 CWD 无关 | `T4-01` 源码核实 | ✅ `join(packageDir, declared)` |

## 5. 复现与已知边界

复现（需要写 `~/.dsh`，若在沙箱内运行可能被拒绝）：

```sh
./scripts/dsh plugin --profile coderag-dev add .
./scripts/dsh --profile coderag-dev --dump-config | grep -n -A7 '== dsh-coderag'
```

已知边界：

- **本地 `add .` 建立的是 `link:` 依赖**，指向本仓库的工作副本；改代码即生效，适合开发自检，
  **不代表 registry 安装路径**。真正的"一条命令安装"要到 `T4-03`（安装脚本）与
  `T4-08`（干净 profile 端到端）才闭合。
- **本任务只验证"层被组合进配置"**，没有 boot profile、没有拉起 MCP 子进程；
  "工具真正可用"属 `T4-08`。
- `coderag-dev` 是**自定义 profile**（无内置模板），初始化时用 `DEFAULT_PROFILE_BUNDLES`
  即只有 `@deepseek-ai/dsh-base`；因此它没有 Web 应用层，只适合 `--dump-config` 这类组合自检。
