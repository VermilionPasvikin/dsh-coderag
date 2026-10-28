# PR 描述草稿：DSH 原生 CodeRAG 参数设置页

> 目标分支：`feat/settings-ui` → `main`（等用户黑盒检查通过后再推送，见 `docs/settings-ui-plan.md` §6）
> 建议标题：`feat(dsh): add the native CodeRAG settings page`
> 建议标签：`kind/feature`、`area/plugin`、`area/settings`

## 这个 PR 做什么

给 `dsh-coderag` 增加 **DSH 原生参数设置页**，三个入口渲染同一个 13 字段表单：
**设置 → CodeRAG**（`settings.section`，主入口）、Plugins → `dsh-coderag` 详情页
（`plugins.bundle.config`）、以及 `coderag` 行的 **配置**（`plugins.row.config`）。保存后：

1. 设置写进当前 profile 的 `cordis.patch.yml`（`coderag` 行），由 DSH 的 settings 服务持久化；
2. Host 半侧在 `loader/volatile-update` 里把 13 个字段映射成 `CODERAG_*`，合并进既有
   `mcp-coderag` 行的 `config.env`；
3. `env` 是 MCP 行的普通（非 volatile）字段，Loader 重挂载该行，
   **Python 子进程以新环境重启**。
4. **热重载已在真实 DeepForge 实例实测**：改 `root` 后 1.5 秒内会话里的
   `mcp__coderag__index_status` 返回新 root；改回后约 2 秒恢复。浏览器提示为
   「已保存，MCP 已按新环境热重载」。

之前用户只能手工编辑 YAML；本 PR 不改变 Python 运行时行为。

## 改动清单

| 文件 | 内容 |
|---|---|
| `src/plugin/index.js` | Host 插件：`coderag` 行的 Config（13 字段全部 `.volatile()`）、`apply` / `loader/volatile-update` 同步、空设置不覆盖旧配置 |
| `src/plugin/sync.js` | `mcp-coderag` 行查找、env 合并、更新/复核/必要时以 `fiber.update(config, true)` 强制重启 |
| `src/plugin/client/index.jsx` | 浏览器半侧：注册 `settings.section`（id `coderag`，order 30）、`plugins.row.config`（key `dsh-coderag#coderag`）与 `plugins.bundle.config`（key `dsh-coderag`）；后两者用 `ctx.configForms.get('coderag')` + `useSyncExternalStore`，React 分组表单 |
| `src/plugin/shared/settings.js` | 双端共享的字段表、env 映射、校验（含 `semanticAllowRemote` 跨字段校验）、摘要 |
| `src/plugin/shared/client-form.js` | draft ↔ JSON 值、保存 op 构造（双端共用的纯函数） |
| `scripts/build-plugin.mjs` | esbuild 构建：host 内联 schemastery；client 打成 lazy-CJS factory（banner/footer/intro），只 external `react` / `react/jsx-runtime`；沙箱里回退 CLI |
| `lib/index.js` / `lib/client.js` | 构建产物（`lib/client.js` 首行必须是 `window.__ModuleLoader__.load({ id: "dsh-coderag", ...`） |
| `package.json` | `type/main/exports/files/dsh.client/scripts/devDependencies`；无 `dependencies`、无 install script |
| `cordis.patch.yml` | 新增 `coderag` 设置行（13 个 `!!js` 默认值）；`mcp-coderag` 只保留解释器 + `CODERAG_SEMANTIC_API_KEY` |
| `tests/plugin/*.test.mjs` | settings 映射、MCP 行同步、表单 draft/ops、client 产物 + 三个 slot 的 server-render 测试、bundle 清单契约 |
| `scripts/experiments/*.mjs` | 两个可复现探针（真实 `app.asar` 的 Loader 行为 / 构建后 Host 插件端到端） |
| `docs/settings-ui-plan.md` | 方案、API 实测结论、T5 证据（含热重载实测） |
| `README.md` / `CHANGELOG.md` | 设置页章节、配置入口表、已知限制、变更记录 |

## 兼容性与边界

- 需要 DSH 支持 `settings.section` / `plugins.row.config` / `plugins.bundle.config`
  （0.1.7-rc.1 起；本 PR 在 **0.2.1-rc.3** 实测）。旧版 DSH 不显示页面，env / patch 配置路径不变。
- **不管理**：只有 `CODERAG_SEMANTIC_API_KEY`。设置页没有也不会有 key 字段（`RL-02`/`S-05`）。
- **首次保存前**，profile 里已有 `mcp-coderag` env 不受影响（设置全空时不做启动同步）；
  **首次保存后**，13 个纳管变量以设置页为唯一来源。
- 启动时若设置来自 shell 环境变量，MCP 子进程可能先以旧环境启动一次、再被同步重启一次；
  之后的保存都是即时热重载。
- Host 半侧**不改变** Python 代码；`pytest` 全绿（仅文档/JS 改动）。

## 验证（实际执行过的命令与输出）

```text
$ node scripts/build-plugin.mjs
esbuild path: cli        # 本会话沙箱禁止管道子进程；正常机器走 JS API
built lib/index.js (48.0 KiB) and lib/client.js (21.1 KiB)

$ node scripts/experiments/loader-volatile-probe.mjs --asar <app.asar> --out .tmp-asar/probe-run --keep
SUMMARY: 20/20 checks passed

$ node scripts/experiments/host-settings-sync-probe.mjs
SUMMARY: 19/19 checks passed

$ node --test --test-isolation=none "tests/plugin/*.test.mjs"
ℹ tests 39 / ℹ pass 39 / ℹ fail 0

$ python -m pytest
629 passed, 17 skipped

$ dsh --profile probe --patch ./cordis.patch.yml --dump-config   # 全新 DSH_HOME
exit 0；`- id: coderag` 1 行、`- id: mcp-coderag` 1 行；
mcp 行只剩 `CODERAG_SEMANTIC_API_KEY`；`CODERAG_ROOT:`（env 键）0 行
```

**真实实例热重载实测**（DeepForge `http://127.0.0.1:3099`，DSH 0.2.1-rc.3）：
通过 `/connect` 换 API cookie → `settings/mutate` 把 `root` 改为 `demo-project`
（revision 0→1）→ 会话模型调 `mcp__coderag__index_status`，**1.5 秒**后返回
`root: F:\PersonalProjects\python\unname\demo-project`；再改回
`dsh-coderag`（revision 4）后约 **2 秒**返回 `root: F:\PersonalProjects\python\unname\dsh-coderag`、
`status: ready`。截图：`deliverables/screenshots/settings-coderag.png`
（设置 → CodeRAG 的 13 字段首屏）。

## 审阅者手工验收

1. 重启 DSH → 打开 **设置 → CodeRAG**（或 Plugins → `dsh-coderag`），第一屏可见 13 字段。
2. 填工作区根 → 保存 → 提示「已保存，MCP 已按新环境热重载」；profile 的
   `cordis.patch.yml` 出现 `- id: coderag`。
3. 让模型调 `mcp__coderag__index_status` → 无需重启 DSH，`root` 已变成新目录。
4. 输入 `-1` 上限 / `a.b` 扩展名 / cloud 缺 URL → 页面就地报错，保存被拒。
5. 点「恢复默认」→ 保存 → `coderag` 行 config 被移除，行为回到环境变量默认。

## 不做的事 / 后续

- 不推送、不建 PR、不打 tag：等用户黑盒检查通过（`T5-07` 由用户 + Lead 执行）。
- 不把 `CODERAG_SEMANTIC_API_KEY` 放进表单（安全红线）。
- 设置页目前只服务 `coderag` 行；MCP 行自身的 `serverName` / `command` 等仍通过 profile patch 配置。
