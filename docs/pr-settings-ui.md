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
4. **热重载已在真实 DSH Web 实例实测**：改 `root` 后 1.5 秒内会话里的
   `mcp__coderag__index_status` 返回新 root；改回后约 2 秒恢复。浏览器提示为
   「已保存，MCP 已按新环境热重载」。
5. 运维面板（T7-02）：云端 key 写入 **DSH credentials**（`CODERAG_SEMANTIC_API_KEY`，
   只写不读、不落 profile）、本地/云端后端连通性检查与一键拉起 `ollama serve`、
   向量库状态/增量向量化/停止/进度。Host 提供三条经过 `connection.requestRejection`
   鉴权的 `/coderag-admin/*` 路由，admin CLI 由 T7-01 提供。

之前用户只能手工编辑 YAML；本 PR 不改变 Python 运行时行为（admin CLI 是新增模块，
不改变 `code_search` / `code_index` 等既有工具）。

## 改动清单

| 文件 | 内容 |
|---|---|
| `src/plugin/index.js` | Host 插件：`coderag` 行的 Config（13 字段全部 `.volatile()`）、`apply` / `loader/volatile-update` 同步、空设置不覆盖旧配置；创建 admin 服务并注册运维路由 |
| `src/plugin/sync.js` | `mcp-coderag` 行查找、env 合并（含 credentials 解析出的 key）、更新/复核/必要时以 `fiber.update(config, true)` 强制重启 |
| `src/plugin/host/admin.js` | admin CLI 子进程：status/health/vectorize 流式 JSON、ollama detached 启动与轮询、内存 job、stop、key 只进 env 且错误消息 scrub |
| `src/plugin/host/credentials.js` | `credentials.resolve('CODERAG_SEMANTIC_API_KEY')`；provider 缺失时返回 undefined（保留现状） |
| `src/plugin/host/routes.js` | 三条鉴权路由、请求体大小/媒体类型校验、action 分发、refresh 钩子 |
| `src/plugin/shared/admin-protocol.js` | 路径/action/key reference/状态与 job 白名单投影 |
| `src/plugin/shared/admin-client.js` | 浏览器 fetch 封装、envelope 解包、job 归一化、进度/格式化 |
| `src/plugin/client/index.jsx` | 浏览器半侧：注册 `settings.section`（id `coderag`，order 30）、`plugins.row.config`、`plugins.bundle.config`；inject `remote` / `remote.credentials`；共享 13 字段表单 + 运维面板 |
| `src/plugin/client/admin-panels.jsx` | 云端 Key（密码框/保存/删除确认）、语义后端（双后端检查/一键启动/错误弹窗）、向量库（状态卡/增量/停止/进度/自动刷新） |
| `src/plugin/shared/settings.js` | 双端共享的字段表、env 映射、校验（含 `semanticAllowRemote` 跨字段校验）、摘要 |
| `src/plugin/shared/client-form.js` | draft ↔ JSON 值、保存 op 构造（双端共用的纯函数） |
| `scripts/build-plugin.mjs` | esbuild 构建：host 内联 schemastery；client 打成 lazy-CJS factory（banner/footer/intro），只 external `react` / `react/jsx-runtime`；沙箱里回退 CLI |
| `lib/index.js` / `lib/client.js` | 构建产物（`lib/client.js` 首行必须是 `window.__ModuleLoader__.load({ id: "dsh-coderag", ...`） |
| `package.json` | `type/main/exports/files/dsh.client/scripts/devDependencies`；无 `dependencies`、无 install script |
| `cordis.patch.yml` | 新增 `coderag` 设置行（13 个 `!!js` 默认值）；`mcp-coderag` 只保留解释器 + `CODERAG_SEMANTIC_API_KEY` |
| `tests/plugin/*.test.mjs` | settings 映射、MCP 行同步（含 key 合并/保留）、admin 服务（流式 job/stop/ollama/密钥 scrub）、路由鉴权与 action 分发、浏览器 helpers、三个 slot 的 server-render 测试、bundle 契约（66 项） |
| `scripts/experiments/*.mjs` | 两个可复现探针（真实 `app.asar` 的 Loader 行为 / 构建后 Host 插件端到端） |
| `docs/settings-ui-plan.md` | 方案、API 实测结论、T5/T7 证据 |
| `README.md` / `CHANGELOG.md` | 设置页与运维面板章节、key 边界、已知限制、变更记录 |

## 兼容性与边界

- 需要 DSH 支持 `settings.section` / `plugins.row.config` / `plugins.bundle.config`
  （0.1.7-rc.1 起；本 PR 在 **0.2.1-rc.3** 实测）。旧版 DSH 不显示页面，env / patch 配置路径不变。
- **云端 key**：只写入 DSH credentials（reference `CODERAG_SEMANTIC_API_KEY`），
  表单不显示值、不回读、不写 profile patch；Host 解析后只放进 MCP/admin 子进程 env，
  state/错误/日志中永远没有 key 值（`RL-02`/`S-05`）。
- **运维路由只在 Web profile 注册**（需要 `webServer` + `connection`，并用
  `connection.requestRejection` 鉴权）；headless 仍可用 env / patch。
- **admin CLI 依赖**：向量库/健康检查需要 T7-01 的 `dsh_coderag.admin`
  在 MCP 同一解释器可用（Host 以私有 0700 cwd + `-c` 启动器调用，防 cwd 影子模块）；
  缺失或失败时面板显示可关闭的结构化错误。
- **首次保存前**，profile 里已有 `mcp-coderag` env 不受影响（设置全空时不做启动同步）；
  **首次保存后**，13 个纳管变量以设置页为唯一来源；credentials 缺失时保留行里已有的 key。
- 启动时若设置来自 shell 环境变量，MCP 子进程可能先以旧环境启动一次、再被同步重启一次；
  之后的保存都是即时热重载。
- Host 半侧**不改变** Python 工具行为；`pytest` 全绿。

## 验证（实际执行过的命令与输出）

```text
$ node scripts/build-plugin.mjs
esbuild path: cli        # 本会话沙箱禁止管道子进程；正常机器走 JS API
built lib/index.js (69.5 KiB) and lib/client.js (46.8 KiB)

$ node scripts/experiments/loader-volatile-probe.mjs --asar <app.asar> --out .tmp-asar/probe-run --keep
SUMMARY: 20/20 checks passed

$ node scripts/experiments/host-settings-sync-probe.mjs
SUMMARY: 19/19 checks passed

$ node --test --test-isolation=none "tests/plugin/*.test.mjs"
ℹ tests 69 / ℹ pass 69 / ℹ fail 0

$ python -m pytest
671 tests, 0 failures, 0 errors, 17 skipped

$ dsh --profile probe --patch ./cordis.patch.yml --dump-config   # 全新 DSH_HOME
exit 0；`- id: coderag` 1 行、`- id: mcp-coderag` 1 行；
mcp 行只剩 `CODERAG_SEMANTIC_API_KEY`；`CODERAG_ROOT:`（env 键）0 行
```

**真实实例热重载实测**（DSH Web（本地实例），DSH 0.2.1-rc.3）：
通过 `/connect` 换 API cookie → `settings/mutate` 把 `root` 改为 `demo-project`
（revision 0→1）→ 会话模型调 `mcp__coderag__index_status`，**1.5 秒**后返回
`root: <workspace>/demo-project`；再改回
`dsh-coderag`（revision 4）后约 **2 秒**返回 `root: <workspace>/dsh-coderag`、
`status: ready`。截图：本地验证截图（未随仓库提交）
（设置 → CodeRAG 的 13 字段首屏）与另一张本地验证截图（bundle 入口）。

**运维路由实测**（同一实例，PYTHONPATH 指向本仓库 `src`）：

```text
GET  /coderag-admin/state   → 200，index_exists=true、total_chunks=1526、pending=1526
POST /coderag-admin/action {action:"health",backend:"ollama"}
                            → 200，{"ok":true,"model_present":true,"models":[4 个]}
credentials/set(fake)       → ok；describe configured=true, source=file
POST action refresh         → ok；state.config.key_present=true（Host resolve 生效）
credentials/unset(fake)     → ok；describe configured=false；state.key_present=false
```

- 所有响应、仓库文件、profile patch 都不含假 key；唯一落点是仓库外的
  `C:\Users\15349\.dsh\.credentials.yaml`。
- 子进程 env 的直接读取被本会话沙箱拒绝（WMI/psutil 不可用）；MCP env 合并由
  `host-sync.test.mjs` 单测钉住，未把“读不到”写成“已验证”。
- 向量化停止/恢复：1526 pending → embed 16 → stop（checkpoint 16）→ resume → embed 32 →
  stop（checkpoint 32）；未跑完，root 与 key 均已恢复。
- 竞态修复：停止后立刻启动第二个 job 时，旧 child 迟到的 close/error 不再改写新 job
  （每次运行独立 handle + `active === handle` 闸门）；回归测试覆盖。修复后复测：
  `S16-vector-running-fixed.png`、`S14b-vector-stopped-fixed.png`、
  `S17-vector-done-fixed.png`（276/276 完成、无 error）。
- UI（Playwright + 276 chunk 的 `vector-demo`）：key 保存后「已配置（不可查看），来源 file」、
  输入框清空、页面无 key；删除后未配置且 `state.key_present=false`；本地 ollama 连通 bge-m3；
  云端缺 URL 返回可展示错误。截图：`S10-coderag-key-configured.png`、
  `S11-coderag-health-local.png`、`S12-vector-ready.png`、`S13-vector-running.png`、
  `S14-vector-stopped.png`、`S15-vector-done.png`、`S16-coderag-start-local-error.png`、
  `S18-vector-incremental-ready.png`、`S19-vector-incremental-done.png`。


## 审阅者手工验收

1. 重启 DSH → 打开 **设置 → CodeRAG**（或 Plugins → `dsh-coderag`），第一屏可见 13 字段。
2. 填工作区根 → 保存 → 提示「已保存，MCP 已按新环境热重载」；profile 的
   `cordis.patch.yml` 出现 `- id: coderag`。
3. 让模型调 `mcp__coderag__index_status` → 无需重启 DSH，`root` 已变成新目录。
4. 输入 `-1` 上限 / `a.b` 扩展名 / cloud 缺 URL → 页面就地报错，保存被拒。
5. 点「恢复默认」→ 保存 → `coderag` 行 config 被移除，行为回到环境变量默认。
6. 运维区：粘贴云端 key → 保存后输入框为空、状态变「已配置（不可查看）」；刷新页面后
   仍是已配置且无值回显。删除需确认。
7. 「检查本地连通性」在 ollama 未启动时显示结构化失败；点「一键启动本地后端」后
   ≤15 秒内变连通（本机需装 ollama）。
8. 「向量数据库」刷新显示状态卡；`pending > 0` 时按钮为「向量化增量」，运行中显示进度并可
   「停止」；停止后检查点数量保留，再跑从检查点恢复。

## 不做的事 / 后续

- 不推送、不建 PR、不打 tag：等用户黑盒检查通过（`T5-07` / `T7-02` 由用户 + Lead 执行）。
- 云端 key 只存 DSH credentials；表单不回读、不显示（安全红线）。
- 设置页只服务 `coderag` 行；MCP 行自身的 `serverName` / `command` 等仍通过 profile patch 配置。
- admin CLI 由 T7-01 单独维护；本 PR 只调用其 JSON 行协议。
