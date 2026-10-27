# PR 描述草稿：DSH 原生 CodeRAG 参数设置页

> 目标分支：`feat/settings-ui` → `main`（等用户黑盒检查通过后再推送，见 `docs/settings-ui-plan.md` §6）
> 建议标题：`feat(dsh): add the native CodeRAG settings page`
> 建议标签：`kind/feature`、`area/plugin`、`area/settings`

## 这个 PR 做什么

给 `dsh-coderag` 增加一个 **DSH 原生参数设置页**：在 Plugins → `dsh-coderag` → `coderag` 行点
**配置**，就能编辑工作区根、索引上限、扩展名白名单与可选语义检索参数。保存后：

1. 设置写进当前 profile 的 `cordis.patch.yml`（`coderag` 行），由 DSH 的 settings 服务持久化；
2. Host 半侧在 `loader/volatile-update` 里把 10 个字段映射成 `CODERAG_*`，合并进既有
   `mcp-coderag` 行的 `config.env`；
3. `env` 是 MCP 行的普通（非 volatile）字段，Loader 重挂载该行，
   **Python 子进程以新环境重启**——`index_status` 立刻反映新的工作区根。

之前用户只能手工编辑 YAML；本 PR 不改变 Python 运行时行为。

## 改动清单

| 文件 | 内容 |
|---|---|
| `src/plugin/index.js` | Host 插件：`coderag` 行的 Config（10 字段全部 `.volatile()`）、`apply` / `loader/volatile-update` 同步、空设置不覆盖旧配置 |
| `src/plugin/sync.js` | `mcp-coderag` 行查找、env 合并、更新/复核/必要时以 `fiber.update(config, true)` 强制重启 |
| `src/plugin/client/index.jsx` | 浏览器半侧：注册 `plugins.row.config`（key `dsh-coderag#coderag`），React 分组表单，调用 `form.state` / `form.mutate` |
| `src/plugin/shared/settings.js` | 双端共享的字段表、env 映射、校验、摘要 |
| `src/plugin/shared/client-form.js` | draft ↔ JSON 值、保存 op 构造（双端共用的纯函数） |
| `scripts/build-plugin.mjs` | esbuild 构建：host 内联 schemastery；client 打成 lazy-CJS factory（banner/footer/intro），只 external `react` / `react/jsx-runtime`；沙箱里回退 CLI |
| `lib/index.js` / `lib/client.js` | 构建产物（`lib/client.js` 首行必须是 `window.__ModuleLoader__.load({ id: "dsh-coderag", ...`） |
| `package.json` | `type/main/exports/files/dsh.client/scripts/devDependencies`；无 `dependencies`、无 install script |
| `cordis.patch.yml` | 新增 `coderag` 设置行；`mcp-coderag` 只保留解释器 + 4 个非纳管 env |
| `tests/plugin/*.test.mjs` | settings 映射、MCP 行同步、表单 draft/ops、client 产物 + server-render slot 测试、bundle 清单契约 |
| `scripts/experiments/*.mjs` | 两个可复现探针（真实 `app.asar` 的 Loader 行为 / 构建后 Host 插件端到端） |
| `docs/settings-ui-plan.md` | 方案、API 实测结论、T5 证据 |
| `README.md` / `CHANGELOG.md` | 设置页章节、配置入口表、已知限制、变更记录 |

## 兼容性与边界

- 需要 DSH 支持 `plugins.row.config`（0.1.7-rc.1 起；本 PR 在 **0.2.1-rc.3** 实测）。
  旧版 DSH 不显示页面，env / patch 配置路径不变。
- **不管理**：`CODERAG_MAX_TOKENS`、`CODERAG_SEMANTIC_MAX_CHUNKS`、
  `CODERAG_SEMANTIC_ALLOW_REMOTE`、`CODERAG_SEMANTIC_API_KEY`。设置页没有 key 字段（`RL-02`/`S-05`）。
- **首次保存前**，profile 里已有 `mcp-coderag` env 不受影响（设置全空时不做启动同步）；
  **首次保存后**，10 个纳管变量以设置页为唯一来源。
- 启动时若设置来自 shell 环境变量，MCP 子进程可能先以旧环境启动一次、再被同步重启一次；
  之后的保存都是即时重启。
- Host 半侧**不改变** Python 代码；`pytest` 全绿（仅文档/JS 改动）。

## 验证（实际执行过的命令与输出）

```text
$ node scripts/build-plugin.mjs
esbuild path: cli        # 本会话沙箱禁止管道子进程；正常机器走 JS API
built lib/index.js (46.2 KiB) and lib/client.js (18.1 KiB)

$ node scripts/experiments/loader-volatile-probe.mjs --asar <app.asar> --out .tmp-asar/probe-run --keep
SUMMARY: 20/20 checks passed

$ node scripts/experiments/host-settings-sync-probe.mjs
SUMMARY: 18/18 checks passed

$ node --test --test-isolation=none "tests/plugin/*.test.mjs"
ℹ tests 34 / ℹ pass 34 / ℹ fail 0

$ python -m pytest
629 passed, 17 skipped in 52.48s

$ dsh --profile probe --patch ./cordis.patch.yml --dump-config   # 全新 DSH_HOME
exit 0；1261 行；`- id: coderag` 1 行、`- id: mcp-coderag` 1 行；
mcp 行保留 4 个非纳管 env；`CODERAG_ROOT:`（env 键）0 行
```

## 审阅者手工验收

1. 重启 DSH → Plugins → `dsh-coderag` → `coderag` 行出现 **配置** 按钮。
2. 填工作区根 → 保存 → 提示「已保存」；profile 的 `cordis.patch.yml` 出现 `- id: coderag`。
3. 模型调 `mcp__coderag__index_status` → `root` 变成新目录（不再是 `WORKSPACE_INVALID`）。
4. 输入 `-1` 上限 / `a.b` 扩展名 / cloud 缺 URL → 页面就地报错，保存被拒。
5. 点「恢复默认」→ 保存 → `coderag` 行 config 被移除，行为回到环境变量默认。

## 不做的事 / 后续

- 不推送、不建 PR、不打 tag：等用户黑盒检查通过（`T5-07` 由用户 + Lead 执行）。
- 不把 API key / ALLOW_REMOTE 放进表单（安全红线）。
- 设置页目前只服务 `coderag` 行；MCP 行自身的 `serverName` / `command` 等仍通过 profile patch 配置。
