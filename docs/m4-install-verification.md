# M4 安装验证

> 本文件归 `PROJECT.md` §6.4 的 **T4-06** 与 **T4-08** 共用：
> **T4-06**（本文件当前内容）验证「干净 profile 首次 `add` 不触发 pnpm 10+ 的 install-script 坑」；
> **T4-08** 之后会把「从零安装并跑通一次检索」的端到端记录追加到这里。
>
> 验证环境：macOS、DSH `0.1.5-rc.1`、Node `v24.14.0`、pnpm `12.4.2`、Python `3.10.21`（forBSH）。
> 所有 dsh 命令均通过 `./scripts/dsh` 包装脚本执行（`AGENTS.md` E-07）。

## 1. 结论

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

## 5. 尚未验证的部分（属 T4-08）

- **从未装过本项目的机器上跑通一次检索**：本文件只证明"层能被装载"，没有拉起 MCP 子进程、没有提问。
- **从 registry 安装**：目前只能 `add .`（本地路径）；npm 包尚未发布。
- **非 macOS / 非 conda 的解释器**：Python 侧安装由 `scripts/install.sh`（`T4-03`）覆盖，
  但只在 forBSH（conda，Python 3.10.21）上实测过。
