# T5-01 · CodeRAG 原生参数设置页：方案验证

- 状态：已完成（2026-10-27）
- 负责人：coderag-ui
- 分支：`feat/settings-ui`
- 目标仓库版本：`dsh-coderag` 2.1.1
- 实测对象：本机安装的 DeepSeek Harness 桌面版 **0.2.1-rc.3**
  （`F:\dsh\resources\app.asar`，内嵌 cordis 4.0.5 / cordis-plugin-loader 1.0.6 /
  schemastery 3.18.5 / dsh-settings 0.2.1-rc.3 / dsh-mcp-client 0.2.1-rc.3）

本文件是 T5-01 的产出：在写任何插件代码之前，先实测 DSH 的 Loader 条目更新接口、
volatile Config 行为、设置页数据通路，并据此定稿同步机制。T5-02 起的所有实现都以本文结论为准。

---

## 1. 取证方式

DSH 的运行时打包在 `app.asar` 里（不是可读源码目录），所以证据不能只靠阅读仓库源码。
本任务写了一个**可复现的探针**，把探针需要的 5 个运行时包从 `app.asar` 解出来、
用普通 Node 运行，并逐条断言接口行为：

```powershell
& 'F:\dsh\resources\runtime\primary-runtime\dependencies\node\bin\node.exe' `
  scripts/experiments/loader-volatile-probe.mjs `
  --asar 'F:\dsh\resources\app.asar' --out .tmp-asar/probe-run --keep
```

实际输出（完整，2026-10-27）：

```text
extracted 184 files (1919 KiB) from F:\dsh\resources\app.asar
PASS initial apply ran once actual=1 expected=1
PASS create() return names the entry id actual="3997ecd8" expected="3997ecd8"
PASS volatile-only update does not remount actual=1 expected=1
PASS the running config object is kept actual=true expected=true
PASS the volatile reference sees the new value actual="/new" expected="/new"
PASS the owning fiber receives the changed path actual=[["root"]] expected=[["root"]]
PASS the event handler already sees the committed value actual="/new" expected="/new"
PASS an ordinary env change remounts the plugin actual=2 expected=2
PASS the remount receives the new env actual="/new" expected="/new"
PASS an ordinary change emits no volatile event actual=1 expected=1
PASS ctx.loader.update(id, ...) commits volatile config actual=1 expected=1
PASS ctx.loader.update(id, ...) keeps the live reference current actual="b" expected="b"
PASS ctx.loader.root.update is the entry-list API (1 argument) actual=1 expected=1
PASS ctx.loader.root.update is not the Entry config patch actual=false expected=false
PASS the settings row lives inside a file-backed tree actual=true expected=true
PASS entry.update leaves the include file untouched actual=true expected=true
PASS volatile references are identified across module copies actual=true expected=true
PASS the host copy can read the bundled copy reference actual="/x" expected="/x"
PASS the schema JSON keeps meta.volatile for every editable field actual={"root":true,"maxFiles":true} expected={"root":true,"maxFiles":true}
PASS volatileEntries finds the nested references actual=["maxFiles","root"] expected=["maxFiles","root"]

SUMMARY: 20/20 checks passed
```

---

## 2. Loader 条目更新接口（实测）

### 2.1 三个容易混淆的接口

| 接口 | 实际签名（0.2.1-rc.3） | 作用 | 能否用来改 mcp 行 config |
|---|---|---|---|
| `entry.update(options, create = false, force = false)` | `Entry` 实例方法 | 合并 options 并重启/重载该行 | **能，首选**（本方案用它） |
| `ctx.loader.update(id, options, parent?, position?)` | `EntryTree` 方法（`Loader` 继承） | `resolve(id)` + `entry.update(options, false, true)`，**force = true** | 能，但强制走更新流程 |
| `ctx.loader.resolve(id).update(...)` | 同上 | 先按完整 id 解析（嵌套树里是 `include:<id>`） | 能 |
| `ctx.loader.root.update(entries)` | `EntryGroup` 方法，参数是 **`EntryOptions[]`** | 整表替换/增删该组的**行列表** | **不能**。它不是“更新某一行 config”的 API |

> ⚠️ 任务书里写的 “`ctx.loader.root.update`” 需要更正：`root` 是 `EntryGroup`，
> 它的 `update(list)` 接收**整张行列表**；只改一行 config 必须走 `entry.update({ config })`。
> 探针第 13–14 条专门钉住这一点（`root.update.length === 1` 且与 `loader.update` 不是同一个函数）。
>
> 另外：嵌套在 `cordis:include` 子树里的行，`ctx.loader.resolve()` 需要**完整路径**
> （`include:mcp-coderag`），而 `entry.options.id` 仍是本地 id（`mcp-coderag`）。
> 插件内按本地 id 在 `ctx.loader.entries()` 里查找目标行，避免拼路径。

### 2.2 volatile 更新语义（实测）

`entry.update({ config })` 的判定来自 Loader 的 `_commitVolatile()`：

- **只有 volatile 字段变化**（`equalExceptVolatile` 为真）→ 不重挂载：
  - `fiber.config` **保持同一个对象引用**；
  - 字段的 `Volatile.get()` 已更新为新值；
  - 在**该行自己的 fiber** 上 emit `loader/volatile-update(paths)`，
    `paths` 是变化字段的 key 数组（整棵 Config 都 `.volatile()` 时是 `[[]]`；
    `Config = z.object({...})` 且逐字段 `.volatile()` 时是 `[['root']]` 这种）；
  - 监听器在该事件里读 `.get()` 已经是新值（先提交、后派发）；
  - **不写回任何配置文件**（`_patchContext` 用 `fiber.update(config, noSave = true)`）。
- **有普通字段变化**（混合或纯普通，例如 mcp-client 行的 `env`）→ 走普通生命周期：
  插件重挂载（`apply` 再跑一次），**不发** volatile 事件。
- **非法候选值** → 记录 warning，运行中的引用不变，原始 config 留给下次激活；
  事件不发。
- 直接 `fiber.update(config, true)` 是 `noSave` 语义，能重启但不更新 `entry.options`；
  本方案只在“必须强制以新 env 重启一次”时使用。

### 2.3 结论：同步机制可行

设置页保存 → Host 把新值写进 `coderag` 行的 config → Loader 以 volatile-only 方式提交
→ 本插件在 `loader/volatile-update` 里把参数映射成 env → `entry.update()` 更新
`mcp-coderag` 行的 `config.env` → 因为 `env` 是**普通字段**，mcp-client 重挂载、
Python 子进程以新 env 重新拉起。**不需要退化为“保存后提示重启”。**

---

## 3. 设置页数据通路（实测 + 源码核对）

### 3.1 客户端 `plugins.row.config`

- slot 是 **keyed** 类型，key 规则为 `<npm 包名>#<patch 里的行 id>`
  （`dsh-client-ui-plugin-manager` 的 `rowConfigKey()`）。
- 行详情页的渲染代码是 `form={formFor(openRow.rowId)}`：
  `formFor(id)` 只有在 settings 镜像里存在 `ns === id` 的命名空间时才返回表单。
  **也就是说：`plugins.row.config` 的 key 里的行 id 必须同时是设置命名空间 id。**
- `plugins.row.config` 的条目会拿到 `{ view: 'summary' | 'page', form?: ConfigPageForm }`：
  - `view: 'page'` → 渲染带自己“保存”控件的表单；
  - `view: 'summary'` → 行描述缺省时的一行说明；
  - `form.state` 是快照：`{ status: 'loading'|'ready'|'unavailable', value, base, user, revision, writable }`；
  - `form.mutate(ops, revision)` 提交一组有序 op：`{op:'set', path:[field], value}` /
    `{op:'unset', path:[field]}`；返回 `Promise<boolean>`（Host 接受与否）。

### 3.2 Host 侧设置服务

`dsh-settings`（0.2.1-rc.3）的行为（源码核对）：

- `describe()` 扫描**所有已激活的 Loader 行**，只保留
  `fiber.runtime.Config` 是 schemastery schema、且至少有一个 volatile 字段的行；
  **命名空间 id = `entry.options.id`**（本地 id，不含 `include:` 前缀）。
- `mutate(ns, ops, expectedRevision)` → 校验 revision → 用 `ctx.configEditor.edit`
  把**完整下一版 config** 写进 profile 的 `cordis.patch.yml`（原子写、权限 600）
  → `reconcileProfilePatches` 重新组合该行 → `entry.update` → volatile 提交。
- 只有 `.volatile()` 字段可编辑；写普通字段会被拒绝（`not volatile`）。
- `volatileForm()` 会把 schema `toJSON()` 后用 **Host 自己的 schemastery**
  重新水合（`new z(json)`），因此插件打包进来的 schemastery 副本不影响识别
  （探针第 19–20 条证明 `meta.volatile` 能往返，且跨模块副本的 volatile 引用
  通过 `Symbol.for('cosmokit.volatile.write')` 识别）。

### 3.3 行 id 与字段名的对齐（Lead 指定）

- 设置行 Loader entry id：**`coderag`**（`cordis.patch.yml` 的 `id: coderag`）。
- 客户端注册 key：**`dsh-coderag#coderag`**。
- 设置命名空间：`coderag`，即 `ctx.configForms.get('coderag')` 可用（工作台摘要）。
- Config 字段至少含 `root`、`maxFiles`、`semantic`；`semantic` 用 boolean
  （工作台兼容 `'on' | 'off'` 字符串或 boolean，这里选 boolean，映射到 env 时写 `'on'`/省略）。
- 行 id **不再改名**；若以后要改，必须先同步 Lead 和 DeepForge 工作台。

---

## 4. 方案定稿

### 4.1 文件与构建

```text
dsh-coderag/
  src/plugin/index.js             host：Config(全部 .volatile()) + env 映射 + mcp 行同步
  src/plugin/shared/settings.js   双端共享的字段表/映射/校验/摘要（纯 JS，无 Node API）
  src/plugin/client/index.jsx     client：plugins.row.config 表单（React，内联样式）
  scripts/build-plugin.mjs        esbuild 构建脚本
  scripts/experiments/loader-volatile-probe.mjs  T5-01 探针（本文证据）
  lib/index.js                    host 产物（ESM，内联 schemastery，无运行时 npm 依赖）
  lib/client.js                   client 产物（lazy-CJS factory）
  package.json                    main/exports/files/dsh.client/scripts/devDependencies
  cordis.patch.yml                新增 coderag 设置行；mcp 行保留执行器与未纳管 env
```

client 产物必须是 lazy-CJS factory（DSH 0.2.1-rc.3 的模块表约定）：

```js
window.__ModuleLoader__.load({ id: "dsh-coderag", factory: (require) => {
var module = { exports: {} }; var exports = module.exports;
/* esbuild 内联的业务代码；只把 react / react/jsx-runtime 留给 require */
return module.exports; } });
```

- externals 只有 `react`、`react/jsx-runtime`（模块表里的基线模块），其余全部内联；
- 不用 CSS Modules / tsdown 预设：所有样式走内联 `style` 对象或运行时 `<style>` 注入；
- host 产物把 `@deepseek-ai/schemastery` 内联（探针第 17–20 条已证明跨副本兼容），
  因此 **运行时零 npm 依赖**，`dependencies` 保持为空，避免 E-05 的 install script 风险。
  构建期的 `esbuild` / `schemastery` 只进 `devDependencies`，消费者拿到的是已构建的 `lib/`。
- `.gitignore` 已加 `.npm-cache/`、`.tmp-*/`（构建缓存与探针落点）。

### 4.2 Config 字段 → `CODERAG_*` env 映射

| Config 字段（全部 `.volatile()`） | 类型/默认 | env | 空值语义 |
|---|---|---|---|
| `root` | string `''` | `CODERAG_ROOT` | 省略（引擎报 `WORKSPACE_INVALID`，符合 T6-26） |
| `maxFiles` | natural `0` | `CODERAG_MAX_FILES` | 0 = 省略，用引擎默认 20000 |
| `maxFileBytes` | natural `0` | `CODERAG_MAX_FILE_BYTES` | 0 = 省略，用引擎默认 1048576 |
| `maxTokens` | natural `0` | `CODERAG_MAX_TOKENS` | 0 = 省略，用引擎默认 4000（名字含 `TOKEN`，只能显式投递） |
| `extraExtensions` | string `''` | `CODERAG_EXTRA_EXTENSIONS` | 省略 |
| `semantic` | boolean `false` | `CODERAG_SEMANTIC` | false = 省略；true = `'on'` |
| `semanticBackend` | `'' \| 'ollama' \| 'openai'` | `CODERAG_SEMANTIC_BACKEND` | 省略（引擎默认 ollama） |
| `semanticUrl` | string `''` | `CODERAG_SEMANTIC_URL` | 省略 |
| `semanticModel` | string `''` | `CODERAG_SEMANTIC_MODEL` | 省略 |
| `semanticTimeout` | natural `0` | `CODERAG_SEMANTIC_TIMEOUT` | 0 = 省略，默认 30 |
| `semanticBatch` | natural `0` | `CODERAG_SEMANTIC_BATCH` | 0 = 省略，默认 16 |
| `semanticMaxChunks` | natural `0` | `CODERAG_SEMANTIC_MAX_CHUNKS` | 0 = 省略，默认 100000 |
| `semanticAllowRemote` | boolean `false` | `CODERAG_SEMANTIC_ALLOW_REMOTE` | false = 省略；true = `'1'` |

**唯一不纳管**：`CODERAG_SEMANTIC_API_KEY`（`!!js process.env.…` 表达式，仓库内不留值，RL-02）。
**任何 key 都不进设置表单、不进设置 Config、不进日志。**

### 4.3 同步策略（避免误伤既有配置）

- **`apply` 时**：读 13 个字段的当前值；**全部为空就不动 mcp 行**。
  这保护了已有用户：他们的 `mcp-coderag` 行可能写在 profile 的
  `cordis.patch.yml` 里（id 定向 patch 会整体替换 config），旧 env 继续生效。
- **`loader/volatile-update` 时**：总是同步（这是用户显式保存）。
- 同步只碰**纳管的 13 个 env key**：有值则写字符串，空值则从 env 删除；
  `CODERAG_SEMANTIC_API_KEY` 原样保留。
- 找到 mcp 行的方法：`[...ctx.loader.entries()].find(e => e.options.id === 'mcp-coderag')`。
- 更新前比较 env；相同则不动（避免无谓重启）。
- 更新用 `entry.update({ config: { ...entry.options.config, env } })`：
  传入的是**原始 config**，`!!js` 表达式不被求值、不写盘（探针第 15–16 条），
  所以 API key 不会被烘焙进 profile patch。
- 竞态：mcp 行可能还在首次 `init()` 中。同步前等它的 fiber 就绪
  （有界轮询 + `fiber.await()`）；更新后用 `entry.fiber.config.env` 复核，
  若仍不一致则 `entry.fiber.update(desiredConfig, true)`（noSave）强制重启一次。
- 启动时若设置来自 shell/env，mcp 子进程可能先以旧 env 启动一次、随后被重启一次；
  这是一次可接受的额外启动，文档里写明。
- 错误只 `logger.warn`，绝不让同步失败冒泡成行加载失败。

### 4.4 bundle patch

- 新增 `id: coderag`（`name: dsh-coderag`），config 用 13 个 `!!js` 表达式把
  **同名 shell 环境变量**作为默认值（`CODERAG_ROOT ?? ''`、`Number(CODERAG_MAX_FILES ?? 0)` …），
  这样“以前 export 环境变量”的用法仍然生效，且设置页首次打开就能看到这些值。
- `mcp-coderag` 行**保留**：`command` / `args` / 服务名，以及唯一未纳管的
  `CODERAG_SEMANTIC_API_KEY`；其余 13 个 env 由 `coderag` 行接管
  （`CODERAG_ROOT` 本来就不在 bundle 里，`test_bundle_patch.py` 会继续钉住这一点）。
- 设置行放 mcp 行之前，注释说明“设置行是参数入口，mcp 行是执行器”。

### 4.5 client UI

- **三个入口共用同一个 `SettingsPage`**：
  - `settings.section`（id `coderag`，order 30，label `CodeRAG`）→ **设置 → CodeRAG**，主入口；
  - `plugins.bundle.config`（key `dsh-coderag`）→ Plugins 详情页，附加入口；
  - `plugins.row.config`（key `dsh-coderag#coderag`）→ 行内「配置」。
  - 后两者不传 form，组件用 `ctx.configForms.get('coderag')` + `useSyncExternalStore`
    订阅快照；row 入口仍使用 DSH 传入的 `form`。
- 三个分组：工作区（`root`）、索引范围（`maxFiles` / `maxFileBytes` / `maxTokens` /
  `extraExtensions`）、语义检索（开关 + backend + url + model + timeout + batch +
  `semanticMaxChunks` + `semanticAllowRemote`）。页面顶部有「CodeRAG 参数设置」标题与入口说明。
- 显示 `loading` / `unavailable` / 只读 / 已保存 / 保存失败 / 字段级校验错误。
- 保存：把**全部 13 个字段**作为 `set` op 提交（首次保存即把当前生效值固化进 profile patch，
  避免 bundle 表达式在“保存任意一项后整体替换”的语义下丢失）；`恢复默认`
  会把表单恢复成 `state.base` 再随保存写回。
- 校验在客户端先做（整数 ≥ 0、backend 枚举、cloud 需要 URL+model、URL 形态、
  云端非 loopback 必须 `semanticAllowRemote`），Host 的 schemastery 是第二道闸；
  非法值不会到达 mcp 行。
- 使用 `settings.configure({auto:false})`（与 dsh-free-search 相同）抑制设置页的自动生成表单，
  改由本插件的 `settings.section` 页面提供唯一正式设置页。
- `view: 'summary'` 渲染一行静态摘要（工作区 + 语义开关），作为行描述缺省。

---

## 5. 风险与退化方案

| 风险 | 现状/对策 |
|---|---|
| Loader 没有可用的单行更新接口 | **不成立**：`entry.update({config})` 实测可用，普通字段变化会重挂载 |
| volatile Config 不能免重载更新 | **不成立**：实测同引用提交 + 本行事件 |
| 插件自带 schemastery 副本导致 Host 认不出 volatile | **不成立**：`Symbol.for` 协议 + schema JSON 往返，探针 17–20 条 |
| `root.update` 误用 | 已更正：它是整表 API；实现里只用 `entry.update` |
| 旧用户的 profile patch 里已有 mcp 行 env | `apply` 时“全空不同步”；用户首次保存后以设置行为准（README 写明） |
| 保存把 `!!js` 表达式求值后写盘、泄露 key | 同步只改内存中的 `entry.options.config`；持久化只发生在设置服务的 `coderag` 行，且该行没有 key 字段 |
| GUI 页面无法由 Agent 黑盒验证 | T5-01..06 只验证构建/接口/host 行为；最终页面由用户黑盒测试（见交接清单） |
| 环境沙箱阻止 esbuild JS API 的管道子进程 | 构建脚本优先 JS API，检测到 `spawn EPERM` 时退回同版本 esbuild CLI（`stdio: 'inherit'`）；两条路径使用同一份 banner/footer/intro 定义 |

## 6. 验证状态（2026-10-28 增量）

最初由用户黑盒确认「bundle 页只看到 README、看不到表单」，因此追加了独立设置页并重做验证：

1. ✅ **设置 → CodeRAG** 页面（`settings.section`）已在真实 DeepForge 实例出现，13 字段全部可见；
   截图 `deliverables/screenshots/S09-coderag-settings-page.png`。
2. ✅ bundle 详情页的附加入口同样可见；截图 `deliverables/screenshots/S07-coderag-plugin-page.png`。
3. ✅ **热重载实测**：改 `root` 后 1.5 秒内 `mcp__coderag__index_status` 返回新 root；改回后约 2 秒恢复。
4. ✅ 保存后写进 profile 的 `coderag` 行（`settings/mutate` 的 revision 变化 + `describe` 读回确认）。
5. ⏳ 非法值在 UI 上的逐字段提示仍以 Node 测试 + 纯函数校验覆盖，未逐项截图。

---

## 7. 实现与证据（T5-02 … T5-06）

### 7.1 提交列表

| 任务 | 提交 | 主题 |
|---|---|---|
| T5-01 | `32f5a97` | `docs(plan): design the native settings page` |
| T5-02 | `24b2911` | `build(bundle): add the client plugin build` |
| T5-03 | `316675d` | `feat(plugin): own coderag settings and sync the mcp row` |
| T5-04 | `fa37c51` | `feat(ui): render the coderag settings form` |
| T5-05 | `38ba0c7` | `test(plugin): cover settings mapping and form behavior` |
| T5-06 | 本次提交 | `docs(readme): document the native settings page` |

每次提交前 `pytest` 全绿、提交后 `git status --short` 为空。

### 7.2 T5-02 构建管线

```text
$ node scripts/build-plugin.mjs
esbuild path: cli
built lib/index.js (46.2 KiB) and lib/client.js (18.1 KiB)

$ head -1 lib/client.js
window.__ModuleLoader__.load({ id: "dsh-coderag", factory: (require) => {

$ tail -1 lib/client.js
return module.exports; } });
```

- `lib/index.js` 是由 esbuild 打出的 ESM，`@deepseek-ai/schemastery` 内联；`package.json`
  无 `dependencies`，安装时不会执行任何 install script。
- 本会话沙箱禁止 Node 的管道子进程（esbuild JS API `spawn EPERM`，且提权不可用），
  构建脚本自动回退到同版本 esbuild CLI（`stdio: 'inherit'`）；两条路径共用同一份
  banner/footer/intro 定义。正常终端里走 JS API。

### 7.3 T5-03 Host 行为（真实 Loader）

```text
$ node scripts/experiments/host-settings-sync-probe.mjs
...
PASS all ten setting fields are volatile in the schema JSON ...
PASS empty settings do not restart the MCP row actual=1 expected=1
PASS empty settings keep the legacy env actual={"CODERAG_ROOT":"/legacy","KEEP":"1"} ...
PASS the settings row stays active without a settings service actual=2 expected=2
PASS boot settings restart the MCP row actual=true expected=true
PASS boot settings export numeric fields as strings actual=["100","2048","5"] ...
PASS an unevaluated !!js env entry is resolved by the Loader and survives actual="from-env" ...
PASS the MCP row keeps the expression in its raw config actual={"__jsExpr":"'from-env'"} ...
PASS a volatile-only save restarts the MCP row actual=true expected=true
PASS the save removes settings that were cleared actual=[null,null,null,null] ...
PASS the volatile-only save did not remount the settings row actual=2 expected=2

SUMMARY: 18/18 checks passed
```

探针用 T5-01 解出的**真实 Loader**挂载构建后的 `lib/index.js`，用假 MCP 行观察
“设置 → env → 重挂载”。它同时证明：不纳管的 env（含 `!!js` 表达式）在同步前后原样保留；
设置行在 volatile 保存时不重挂载。

### 7.4 T5-04 设置页 UI 与 patch 装载

client 产物按 DSH 的模块表协议加载（`window.__ModuleLoader__.load` → factory(require)），
再用 `react-dom/server` 渲染实际注册的组件：

```text
loaded id: dsh-coderag
first line: window.__ModuleLoader__.load({ id: "dsh-coderag", factory: (require) => {
exports: [ 'apply', 'inject' ] inject: [ 'slots' ]
registrations: [ { name: 'plugins.row.config', key: 'dsh-coderag#coderag' } ]
page has root value: true
page labels present: true
page inputs: 12        # 10 个控件 + 2 个按钮
required externals only: [ 'react', 'react/jsx-runtime' ]
```

`cordis.patch.yml` 用**真实 DSH** 装载一次（全新 `DSH_HOME` 在仓库内，`--patch` 叠加）：

```text
$ dsh --profile probe --patch ./cordis.patch.yml --dump-config
exit=0；lines=1261
- id: coderag        → 1
- id: mcp-coderag    → 1
CODERAG_ROOT:（env 键）→ 0
非纳管 env 键（MAX_TOKENS / MAX_CHUNKS / ALLOW_REMOTE / API_KEY）→ 4
```

这同时验证了 YAML 的 `!!js` 方言、行顺序与“不猜工作区”约束（T6-15/T6-26 的教训）。

### 7.5 T5-05 测试

```text
$ node --test --test-isolation=none "tests/plugin/*.test.mjs"
ℹ tests 34
ℹ pass 34
ℹ fail 0

$ python -m pytest
629 passed, 17 skipped in 52.48s
```

Node 测试覆盖：字段表/env 映射/校验、MCP 行同步（含竞态强制重启路径）、表单 draft↔JSON 与
保存 op、构建产物契约（首行 banner、footer、仅 React externals、slot key）、bundle 清单
（无 install script、无运行时依赖、patch 不重复纳管 env、不猜 root）。

### 7.6 T5-06 文档

```text
$ python scripts/verify-plan.py .
计划完备性：通过 ✅   （29 项检查全部实际执行，无空过）

$ python -m pytest
629 passed, 17 skipped in 52.70s

$ node --test --test-isolation=none "tests/plugin/*.test.mjs"
ℹ tests 34
ℹ pass 34
ℹ fail 0

$ git status --short
（空输出）
```

文档改动（人工检查，稳定锚点而非全文计数）：

- `README.md` 新增 `### 原生设置页（推荐）`，含三个入口、13 字段/env 对照表、
  保存/恢复默认/非法值行为、热重载实测、首次保存前后的老配置语义、5 步黑盒验收；
  配置入口表、安装期望行、`CODERAG_ROOT` 说明与已知限制同步更新；文档表新增本文件与 PR 草稿。
- `PROJECT.md` §1.6.1 的 bundle 形态由「没有 JavaScript」更新为「Host/Client 两个已构建产物 +
  `coderag` 设置行，仍无运行时依赖、无 install script」；§6.7 注明 DeepForge M5 支线的证据位置。
- `CHANGELOG.md` 的 `[Unreleased]` 增加设置页、构建产物、探针、Node 测试与 patch 调整。
- 本文件 §7 记录 T5-02…T5-06 的命令与实际输出。

### 7.7 环境限制（不影响交付）

- 本会话的 Windows 沙箱拒绝 `os.chmod` / 0o700 目录，pytest 需要把 `TEMP`/`TMP` 指到仓库内
  并用**仓库之外**的 `sitecustomize.py` 临时修正（不改项目代码）。正常终端直接
  `python -m pytest` 即可。
- 该沙箱尝试还在仓库根留下 5 个**空**目录 `pytest-cache-files-*`（不可读、不可删、未跟踪）。
  用户可在正常终端里直接删除；它们不属于任何提交。
- GUI 页面已由用户在真实 DeepForge 实例上确认（§6、§8），截图见 `deliverables/screenshots/`。

---

## 8. M5 增量：独立设置页、13 字段与热重载实测（2026-10-28）

用户黑盒反馈「bundle 页第一屏仍是 README」后追加的改动（都在 `feat/settings-ui`）：

| 内容 | 提交 |
|---|---|
| 13 字段（新增 `maxTokens` / `semanticMaxChunks` / `semanticAllowRemote`）+ bundle 页表单 | `a4e4cf0` `feat(ui): expose all coderag settings on the bundle page` |
| 13 字段测试 | `1f86856` `test(plugin): cover the thirteen settings fields` |
| `settings.section` 独立设置页（主入口）+ 页面标题 + 热重载成功文案 | 见本次 `feat(ui): add a dedic…` 提交 |
| settings.section 注册测试与 39 用例 | 见本次 `test(plugin): cover the settings section…` 提交 |
| README/CHANGELOG/PR/本文件 | 见本次 `docs(readme): record the settings section…` 提交 |

### 8.1 13 字段与入口

- `settings.section`：id `coderag`、order 30、label `CodeRAG`，**设置 → CodeRAG**；
- `plugins.bundle.config`：key `dsh-coderag`，Plugins 详情页；
- `plugins.row.config`：key `dsh-coderag#coderag`，行内「配置」；
- 三个入口共用 `SettingsPage`；无 form 的两个入口用
  `ctx.configForms.get('coderag')` + `useSyncExternalStore` 读快照。
- `semanticAllowRemote` 的跨字段校验：语义开启 + `openai` + 非 loopback URL 时必须打开，
  与引擎的 `CODERAG_SEMANTIC_ALLOW_REMOTE=1` 双重开关一致；映射时 true→`'1'`。
- API key 仍**不暴露**：唯一不在表单里的变量，继续走环境变量 / 本机 profile。

### 8.2 热重载实测（真实实例，DSH 0.2.1-rc.3）

通过 `/connect?token=…` 换 API cookie，调用 `/api/settings/describe` 与
`/api/settings/mutate`（这就是设置页保存走的同一条 settings Remote）：

```text
baseline  root = F:\PersonalProjects\python\unname\dsh-coderag   revision 0
mutate    root = F:\PersonalProjects\python\unname\demo-project revision 1
会话模型调用 mcp__coderag__index_status（同一进程，未重启 DSH）：
  status: error / code: INDEX_NOT_FOUND
  root: F:\PersonalProjects\python\unname\demo-project        ← prompt 后 1.5 秒
mutate    恢复 root = F:\PersonalProjects\python\unname\dsh-coderag  revision 4
  {"status": "ready", "root": "F:\\PersonalProjects\\python\\unname\\dsh-coderag", ...}
                                                              ← prompt 后 2.0 秒
```

- 测量方式：会话日志里 `agent/inbox/spliced`（prompt 入队）→ `tool/result`（工具返回）的
  事件时间差；工具结果从会话 JSONL（多帧 zstd）解出。
- 结论：**保存即热重载，无需重启 DSH**。保存提示据此定稿为
  「已保存，MCP 已按新环境热重载」。
- 测试结束后 `settings/describe` 复核：root 仍为 `dsh-coderag`，已恢复。

### 8.3 截图（用户从真实实例抓取）

| 文件 | 内容 |
|---|---|
| `F:\PersonalProjects\python\unname\deliverables\screenshots\S09-coderag-settings-page.png` | **设置 → CodeRAG** 首屏，13 字段 |
| `F:\PersonalProjects\python\unname\deliverables\screenshots\S07-coderag-plugin-page.png` | Plugins → dsh-coderag 详情页（附加入口） |

### 8.4 本次验证输出

```text
$ node scripts/build-plugin.mjs
built lib/index.js (48.0 KiB) and lib/client.js (21.1 KiB)

$ node --test --test-isolation=none "tests/plugin/*.test.mjs"
ℹ tests 39 / ℹ pass 39 / ℹ fail 0

$ node scripts/experiments/host-settings-sync-probe.mjs
SUMMARY: 19/19 checks passed

$ python -m pytest
629 passed, 17 skipped
```

---

## 9. M5+ 增量：API key、后端健康与向量库运维（T7-02，2026-10-28）

设置页在 13 字段表单下新增三块运维区。数据面由 T7-01 的
`python -m dsh_coderag.admin` 提供；控制面是 Host 插件，浏览器只经过鉴权路由。

### 9.1 凭据边界

| 方向 | 路径 |
|---|---|
| 写 | 浏览器 `ctx.remote.credentials.set('CODERAG_SEMANTIC_API_KEY', key)` → DSH credentials 服务（**不写 profile patch**） |
| 读状态 | `remote.credentials.describe([ref])` → 只拿 `{configured, source?, writable}`；输入框保存后立即清空 |
| 读值 | 仅 Host `ctx.get('credentials').resolve(ref)`；结果只进 MCP 行 env 与 admin 子进程 env |
| 删除 | `remote.credentials.unset(ref)`，页面二次确认 |
| 不出现 | state/job/health 响应、错误消息、日志、凭据值回显 |

key 变更后页面 POST `{action:'refresh'}`，Host 解析凭据并重同步 `mcp-coderag` env；
解析不到（provider 缺失/未配置）时**保留行里已有的值**，不删除。

### 9.2 Host 路由

| 路由 | 行为 |
|---|---|
| `GET /coderag-admin/state` | `admin status --root <当前 Config.root>`，投影为白名单状态 |
| `POST /coderag-admin/action` | `health`（可带 `backend`，覆盖 admin env 里的后端）/ `start-local` / `vectorize` / `stop` / `refresh` |
| `GET /coderag-admin/job` | 内存 job `{status,total,embedded,pending,model,generatedAt,error,...}` |

- 只在 Web profile 注册（`ctx.inject(['webServer','connection'])`）；每个请求先过
  `connection.requestRejection`，拒绝时返回 401/403。
- 请求体 ≤64 KiB、必须 `application/json`；action 必须在固定列表内。
- `start-local`：detached `ollama serve`，轮询 `http://127.0.0.1:11434/api/tags`
  ≤15 秒（每 500ms 一次，单次 1.5s 超时），失败返回可展示的 `ollama-unreachable` 错误。
- `vectorize`：`spawn` admin CLI，逐行解析 `start`/`progress`/`done`/`error` JSON；
  job 只存内存。`stop` 发 SIGTERM（5 秒后 SIGKILL 兜底），检查点保留；
  退出码非 0 或 `error` 事件 → job `error`，消息用解析出的 key 做 scrub。

### 9.3 页面模块

1. **云端 API Key**：状态（已配置/未配置）、密码输入、保存/删除（确认）。
2. **语义后端**：本地/云端两个检查按钮（health 用已保存配置，可覆盖 backend）、
   一键启动本地 ollama、失败弹窗（可关闭，显示 `message`）。
3. **向量数据库**：存在性/模型/维度/总 chunk/已向量化/待向量化/过期/检查点/生成时间；
   刷新、增量向量化、开始/停止、进度条；运行中每秒轮询 job，完成后自动刷新状态；
   有未保存参数时提示先保存。

### 9.4 测试与构建

```text
$ node scripts/build-plugin.mjs
built lib/index.js (68.6 KiB) and lib/client.js (46.4 KiB)

$ node --test --test-isolation=none "tests/plugin/*.test.mjs"
ℹ tests 66 / ℹ pass 66 / ℹ fail 0
```

新增覆盖：`admin-host.test.mjs`（CLI 调用/流式 job/stop/ollama 轮询/密钥 scrub）、
`admin-routes.test.mjs`（方法/媒体类型/action/refresh/信任围栏）、
`admin-client.test.mjs`（envelope/job 归一化/进度/格式化）、host-sync 的 key 合并与保留、
client-bundle 的运维面板渲染。

### 9.5 联调状态

- 本会话沙箱禁止带管道的子进程，因此**无法在会话内**真实 spawn Python/admin；
  admin 服务的行为由注入式单测覆盖（真实子进程、流式事件、SIGTERM 均可模拟）。
- 真实 DeepForge 实例联调需要重启加载新 host bundle；截图与路由响应在联调后补入本节。
