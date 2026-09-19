# M3 T3-00：dsh-eval-harness 兼容性验证

> 依据 `PROJECT.md` §6.3 的 T3-00 与 `EVAL.md` §3.2 的兼容性风险清单。
> 本文件记录**实际执行结果**，不是预期。结论是：**安装/装载层可以通过，但运行用例层不兼容当前 DSH，M3 应改走 `EVAL.md` §3.6 的自建薄 runner。**
>
> 验证环境：DSH `0.1.5-rc.1`、Node `v24.14.0`、`dsh-eval-harness` `0.4.0`（GitHub commit `bccfc67aa72380950fb2062e00289ab83f78b60a`）。
> 所有 dsh 命令均通过 `./scripts/dsh` 包装脚本执行（AGENTS.md E-07）。
> 为满足“干净 profile”且不污染开发者主目录，使用临时 `DSH_HOME=/tmp/dsh-coderag-t3-00`；`HOME`、`PNPM_HOME`、npm/pnpm cache 也指向该临时目录。

## 结论摘要

| 检查项 | 结果 | 证据 |
|---|---|---|
| `./scripts/dsh plugin --profile eval-coderag add github:BiBoyang/dsh-eval-harness` 能安装 | ✅（需先允许 pnpm build） | 首次报 `ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED`；按报错把精确 key 写进 `pnpm-workspace.yaml` 的 `allowBuilds` 后，`pnpm` 安装成功 |
| 插件层能被 profile 装载 | ✅ | `--dump-config` 出现 `# == dsh-eval-harness` 层；stderr 为空 |
| 跑通 `cases/real/` 一条用例 | ❌ | `cases/real/01-bash-tool.yml` 结果是 `error`：harness 0.4.0 只递归查找 `session.jsonl` / `session.jsonl.zstd`，而 DSH `0.1.5-rc.1` 实际写的是 `session.v3.jsonl.zstd` |
| 按 T3-00 规定处理失败 | ✅ | **改用 `EVAL.md` §3.6 的自建薄 runner**；M3 的 `T3-05` / `T3-06` 不依赖 `dsh-eval-harness` |

**重要区分**：本次失败的**直接 blocker 是会话文件格式版本不匹配**，不是 `dsh-eval-harness` 把 `dsh-*` 包放在 `dependencies` 导致的双份包崩溃（DSH discussion #572/#783 的形态）。因此不能把它当作“双份包已验证安全”。

## 1. 安装：首次失败与 allowBuilds 绕过

命令（首次）：

```sh
./scripts/dsh plugin --profile eval-coderag add github:BiBoyang/dsh-eval-harness
```

实际输出（关键段）：

```text
dsh: initialized profile eval-coderag at /tmp/dsh-coderag-t3-00/profiles/eval-coderag
Progress: resolved 0, reused 0, downloaded 1, added 0
Error: ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED

  × adding a new package
  ╰─▶ The git-hosted package "dsh-eval-harness@0.4.0" needs to execute build scripts but is not in the "allowBuilds" allowlist.
  help: Add the package to "allowBuilds" in your project's pnpm-workspace.yaml to allow it to run scripts. For example:
        allowBuilds:
          dsh-eval-harness@https://codeload.github.com/BiBoyang/dsh-eval-harness/tar.gz/bccfc67aa72380950fb2062e00289ab83f78b60a: true
```

这正是 `PROJECT.md` §4.1 C11 / `AGENTS.md` E-05 记录的 pnpm 10+ 行为：git-hosted 插件需要执行 `prepare` 构建脚本，pnpm 默认拒绝。
按报错把**精确 key**写入（只改临时 profile，不进入本仓库）：

```yaml
allowBuilds:
  dsh-eval-harness@https://codeload.github.com/BiBoyang/dsh-eval-harness/tar.gz/bccfc67aa72380950fb2062e00289ab83f78b60a: true
```

当时的第二次尝试还撞到 `pnpm` 试图写 `/Users/vermi/Library/pnpm/global/v11` 被沙箱拒绝；把 `HOME` / `PNPM_HOME` / npm cache 也指向 `/tmp` 后通过。该报错是验证环境的写权限问题，不改变兼容性结论。

成功安装后的验收命令输出：

```text
$ ./scripts/dsh plugin --profile eval-coderag add github:BiBoyang/dsh-eval-harness
✓ Lockfile passes supply-chain policies (verified 5m ago)
Lockfile is up to date, resolution step is skipped
Done in 2.3s using pnpm v12.4.2
```

## 2. 插件装载验证

命令：

```sh
./scripts/dsh --profile eval-coderag --dump-config | sed -n '/# == dsh-eval-harness/,+6p'
```

实际输出：

```text
# == dsh-eval-harness
- id: dsh-eval-harness
  name: dsh-eval-harness
```

该命令 stderr 为 0 字节。

## 3. 跑一条真实用例：失败

`dsh-eval-harness` 的 `eval_run` 会 fork `dsh --profile headless --patch <overlay> <prompt>`。
因此验证时另外在临时 home 中按 pin 版本安装了 headless profile：

```sh
./scripts/dsh plugin --profile headless add @deepseek-ai/dsh-headless@0.1.5-rc.1
```

输出：

```text
dsh: initialized profile headless at /tmp/dsh-coderag-t3-00/profiles/headless
...
dependencies:
+ @deepseek-ai/dsh-headless 0.1.5-rc.1

Done in 1.1s using pnpm v12.4.2
```

然后直接调用 harness 的 `runEval`，只跑 `cases/real/01-bash-tool.yml`，`profile="headless"`，`timeoutMs=240000`。实际结果：

```json
{
  "summary": {
    "total": 1,
    "passed": 0,
    "failed": 0,
    "errored": 1
  },
  "dshVersion": "0.1.5-rc.1",
  "cases": [
    {
      "name": "bash-tool",
      "status": "error",
      "failures": [],
      "error": "no session log (session.jsonl / session.jsonl.zstd) found under '/tmp/dsh-coderag-t3-00/run-one-headless/out/.sessions/000-bash-tool/attempt-1'",
      "steps": 0,
      "toolsCalled": [],
      "finalText": "",
      "exitCode": 0
    }
  ]
}
```

子进程**已经正常退出**（`exitCode: 0`），但 harness 收集不到 trace。实际落盘的会话文件是：

```text
/tmp/dsh-coderag-t3-00/run-one-headless/out/.sessions/000-bash-tool/attempt-1/
  --private-tmp-dsh-coderag-t3-00-run-one-headless-out-.workspace-000-bash-tool--/
    session-3edcdbd7-ba2d-4d5a-9bb8-0825865e851b/
      session.v3.jsonl.zstd
```

而 `dsh-eval-harness@0.4.0` 的收集器只匹配：

```ts
entry.name === 'session.jsonl' || entry.name === 'session.jsonl.zstd'
```

根因：DSH 的 session-persistence-jsonl 已有格式代际，当前版本写 `session.v3.jsonl.zstd`；harness 0.4.0 没有跟上这个文件名变化。**这不是断言失败，而是 trace 采集器与当前 DSH 版本不兼容。**

补充：同一用例第一次尝试用 `profile="eval-coderag"` 时，子进程 180 s 超时且没有 session 文件。原因是 `eval-coderag` 只含 `dsh-base` + harness，没有 headless app；`eval_run` 必须跑在 `headless` profile 上。这进一步说明 harness 的 profile 约定需要和本项目 M3 的 profile 计划对齐。

## 4. 决策

按 `PROJECT.md` §6.3 T3-00 的期望结果，兼容性验证失败时**改用 `EVAL.md` §3.6 的自建薄 runner**。本项目的后续决策：

1. `T3-05` / `T3-06` 不依赖 `dsh-eval-harness`；用自建 runner fork `./scripts/dsh --profile ...`，直接读取 DSH 会话日志。
2. 自建 runner 的 session 发现逻辑必须支持版本化文件名（至少 `session.v*.jsonl.zstd`），不能硬编码 `session.jsonl.zstd`。
3. 仍然复用 `EVAL.md` §3.4 的用例断言形状与 §3.5 的 `trials` / `pass@k` 口径，不因为换 runner 而放宽评测标准。
4. `T4-06` 的 pnpm `allowBuilds` 文档已有现实样本：如果将来仍要安装该 git-hosted 插件，必须写精确 key；本项目自己的 bundle 继续坚持零 install script。
