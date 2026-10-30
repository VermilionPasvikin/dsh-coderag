/**
 * Host side of the CodeRAG operations panel.
 *
 * Runs the Python admin CLI (`python -c <launcher>`) for vector index status,
 * embedding-backend health, and resumable vectorization, and owns the one
 * in-memory job the browser polls. The browser never talks to Python directly:
 * every call goes through an authenticated Host route.
 *
 * Security boundaries:
 * - the child runs in a private directory created with 0700 permissions, never
 *   in the shared OS temp directory; `-m` is deliberately not used because it
 *   would put that directory on `sys.path[0]` and allow a shadow module to
 *   hijack the process and read the injected key;
 * - the launcher also removes `''`/cwd from `sys.path` before importing;
 * - the status command receives only a `KEY_PRESENT` marker, never the key;
 *   health/vectorize receive the key only through their environment.
 *
 * The key is resolved from DSH's credentials service at call time and is never
 * returned, logged, or embedded in an error message; captured output is
 * scrubbed against the resolved value and the ambient key.
 *
 * Not responsible for HTTP framing or authentication (routes.js) or rendering.
 */

import { spawn as nodeSpawn } from 'node:child_process'
import { chmodSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import {
  SEMANTIC_KEY_PRESENT_ENV,
  SEMANTIC_KEY_REF,
  adminError,
  emptyJob,
  normalizeAdminStatus,
  normalizeHealth,
  HEALTH_BACKENDS,
} from '../shared/admin-protocol.js'
import { envPlan } from '../shared/settings.js'

/** Bounded wait for one status/health invocation. */
const COMMAND_TIMEOUT_MS = 30_000
/** Bounded wait for a full lexical index build (large repositories take minutes). */
const INDEX_TIMEOUT_MS = 10 * 60_000
/** Bounded wait for `ollama serve` to answer /api/tags. */
const LOCAL_START_TIMEOUT_MS = 15_000
/** Poll cadence while waiting for ollama. */
const LOCAL_POLL_INTERVAL_MS = 500
/** Per-request deadline while polling ollama. */
const LOCAL_PROBE_TIMEOUT_MS = 1_500
/** Captured stderr kept only to build a bounded error message. */
const STDERR_LIMIT = 8 * 1024
/** Number of trailing characters of child output exposed in an error. */
const ERROR_EXCERPT = 400
/** Default local embeddings URL. */
const DEFAULT_OLLAMA_URL = 'http://127.0.0.1:11434'

/**
 * The launcher handed to `python -c`. It removes the empty entry and the
 * process cwd from `sys.path` before importing the admin module, so a file
 * dropped into the child's cwd can never shadow `dsh_coderag`.
 */
export const ADMIN_LAUNCHER = "import sys, os; sys.path[:] = [p for p in sys.path if p not in ('', os.getcwd())]; import dsh_coderag.admin as a; raise SystemExit(a.main())"

/**
 * Last JSON object printed by a command. The CLI contract says one object per
 * invocation; scanning lines keeps a stray blank line or log prefix harmless.
 * @param {string} text - captured stdout.
 * @returns {unknown} the parsed object, or undefined.
 */
export function parseJsonOutput(text) {
  const trimmed = text.trim()
  if (trimmed === '') return undefined
  try {
    return JSON.parse(trimmed)
  } catch {
    const lines = trimmed.split(/\r?\n/)
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const line = lines[index].trim()
      if (!line.startsWith('{')) continue
      try {
        return JSON.parse(line)
      } catch {
        // Not a JSON line; keep walking towards earlier output.
      }
    }
    return undefined
  }
}

/** Collect possibly chunked JSON lines from one stream. */
function lineReader(onLine) {
  let buffer = ''
  return {
    push(chunk) {
      buffer += chunk.toString('utf8')
      for (;;) {
        const newline = buffer.indexOf('\n')
        if (newline < 0) return
        const line = buffer.slice(0, newline).trim()
        buffer = buffer.slice(newline + 1)
        if (line !== '') onLine(line)
      }
    },
  }
}

/** Replace every resolved/ambient secret in a diagnostic. */
function scrub(value, ...secrets) {
  let text = String(value ?? '')
  for (const secret of secrets) {
    if (typeof secret === 'string' && secret !== '') text = text.split(secret).join('[redacted]')
  }
  return text
}

/** Truncate child output into a single-line diagnostic. */
function excerpt(value) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  return text.length > ERROR_EXCERPT ? `${text.slice(0, ERROR_EXCERPT)}…` : text
}

/** Whether a URL points at the local machine. */
function isLoopbackUrl(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
      ? ['localhost', '127.0.0.1', '::1', '[::1]'].includes(url.hostname)
      : false
  } catch {
    return false
  }
}

/**
 * Build the environment handed to one admin child.
 *
 * The ambient key is removed first, so a status child can never inherit it.
 * Only callers that actually need the secret (`health`, `vectorize`) pass
 * `apiKey`; `status` passes `keyPresent` and receives the marker only.
 *
 * @param {Record<string, unknown>} values - normalized settings.
 * @param {{ apiKey?: string, backend?: string, forceSemantic?: boolean, keyPresent?: boolean }} config - invocation facts.
 * @returns {NodeJS.ProcessEnv} the child environment.
 */
export function adminEnvironment(values, config = {}) {
  const plan = envPlan(values)
  const env = {
    ...process.env,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    ...plan.set,
  }
  // Clear owned variables the settings explicitly left empty; otherwise an
  // ambient value exported for an unrelated session would silently win.
  for (const name of plan.remove) delete env[name]
  // Never inherit the key: only the explicit argument may add it.
  delete env[SEMANTIC_KEY_REF]
  delete env[SEMANTIC_KEY_PRESENT_ENV]
  if (config.forceSemantic === true) env.CODERAG_SEMANTIC = 'on'
  if (config.backend !== undefined && HEALTH_BACKENDS.includes(config.backend)) {
    env.CODERAG_SEMANTIC_BACKEND = config.backend
  }
  if (config.keyPresent === true) env[SEMANTIC_KEY_PRESENT_ENV] = '1'
  if (typeof config.apiKey === 'string' && config.apiKey !== '') {
    env[SEMANTIC_KEY_REF] = config.apiKey
    env[SEMANTIC_KEY_PRESENT_ENV] = '1'
  }
  return env
}

/**
 * Create the operations service for one plugin instance.
 *
 * Every dependency that touches the outside world is injectable so the Node
 * tests can drive streaming jobs, failing spawns, and slow polling without
 * starting Python or ollama.
 *
 * @param {object} options - service dependencies.
 * @param {() => Record<string, unknown>} options.readValues - current normalized settings.
 * @param {() => Promise<{ available: boolean, value?: string }>} options.resolveKey - credentials lookup.
 * @param {() => string | undefined} options.python - configured interpreter, when known.
 * @param {object} [options.logger] - cordis logger.
 * @param {Function} [options.spawn] - child_process.spawn replacement.
 * @param {Function} [options.fetch] - fetch replacement.
 * @param {Function} [options.sleep] - delay replacement.
 * @param {Function} [options.now] - clock replacement.
 * @param {string} [options.privateDir] - test seam: use this directory instead of creating one.
 * @returns {object} state/health/startLocal/vectorize/stop/job/dispose.
 */
export function createAdminService(options) {
  const spawn = options.spawn ?? nodeSpawn
  const fetchImpl = options.fetch ?? globalThis.fetch
  const sleep = options.sleep ?? (ms => new Promise(resolveTimer => setTimeout(resolveTimer, ms)))
  const now = options.now ?? (() => Date.now())
  const logger = options.logger

  /** One in-memory job; only this service mutates it. */
  let job = emptyJob()
  /** The running vectorize child, when there is one. */
  let active
  /** True between accepting a vectorize call and spawning its child. */
  let starting = false
  /** Force-kill timers owned by this service. */
  const forceTimers = new Set()
  /** Private cwd; created on first use and removed by dispose. */
  let privateDir = options.privateDir

  const ensurePrivateDir = () => {
    if (privateDir !== undefined) return privateDir
    privateDir = mkdtempSync(join(tmpdir(), 'coderag-admin-'))
    try {
      chmodSync(privateDir, 0o700)
    } catch (error) {
      logger?.warn?.('coderag: could not mark the admin cwd 0700')
      logger?.warn?.(error)
    }
    return privateDir
  }

  const rootOf = () => {
    const root = options.readValues().root
    if (typeof root !== 'string' || root.trim() === '') return ''
    // A relative root would resolve against the admin child's cwd, not the MCP
    // child's cwd; make the meaning explicit once, in the Host.
    return resolve(root.trim())
  }

  const pythonOf = () => {
    const configured = options.python?.()
    if (typeof configured === 'string' && configured.trim() !== '') return configured.trim()
    return process.platform === 'win32' ? 'python' : 'python3'
  }

  const snapshot = () => ({
    ...job,
    error: job.error === null ? null : { ...job.error },
  })

  /** Resolve the key fact without ever logging the value. */
  async function currentCredential() {
    try {
      const result = await options.resolveKey()
      if (result === null || typeof result !== 'object' || result.available !== true) return { available: false }
      return {
        available: true,
        value: typeof result.value === 'string' && result.value !== '' ? result.value : undefined,
      }
    } catch (error) {
      logger?.warn?.('coderag: credentials lookup failed')
      logger?.warn?.(error)
      return { available: false }
    }
  }

  /** Require a saved root or report what the browser should tell the user. */
  function requireRoot() {
    const root = rootOf()
    return root === ''
      ? { ok: false, error: adminError('root-unset', '请先在设置里填写工作区根并保存') }
      : { ok: true, root }
  }

  /**
   * Whether a vectorize child (or the window where one is being started) owns
   * the workspace. Index/write actions must not race it: a rebuild would swap
   * chunks under the embedding job that is reading them.
   */
  const jobBusy = () =>
    active !== undefined || starting || job.status === 'running' || job.status === 'stopping'

  /**
   * Run one admin command to completion and parse its JSON object.
   * @param {string[]} args - CLI arguments after the launcher.
   * @param {{ timeoutMs: number, apiKey?: string, backend?: string, forceSemantic?: boolean, keyPresent?: boolean }} config - invocation facts.
   * @returns {Promise<{ ok: true, value: unknown } | { ok: false, error: object }>}
   */
  async function runOnce(args, config) {
    const command = pythonOf()
    const env = adminEnvironment(options.readValues(), config)
    return new Promise(resolveRun => {
      let settled = false
      let stdout = ''
      let stderr = ''
      let child
      const finish = result => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        if (result.ok === false) {
          const message = scrub(result.error.message, config.apiKey, process.env[SEMANTIC_KEY_REF])
          resolveRun({ ok: false, error: adminError(result.error.code, excerpt(message)) })
          return
        }
        const parsed = parseJsonOutput(stdout)
        resolveRun(parsed === undefined
          ? { ok: false, error: adminError('admin-output-invalid', 'admin 输出不是 JSON') }
          : { ok: true, value: parsed })
      }
      const timer = setTimeout(() => {
        child?.kill('SIGTERM')
        finish({ ok: false, error: { code: 'admin-timeout', message: `admin 命令超过 ${config.timeoutMs}ms` } })
      }, config.timeoutMs)
      try {
        child = spawn(command, ['-c', ADMIN_LAUNCHER, ...args], {
          cwd: ensurePrivateDir(),
          env,
          stdio: ['ignore', 'pipe', 'pipe'],
          windowsHide: true,
        })
      } catch (error) {
        finish({ ok: false, error: { code: 'admin-spawn-failed', message: String(error?.message ?? error) } })
        return
      }
      child.on('error', error => {
        finish({ ok: false, error: { code: 'admin-spawn-failed', message: String(error?.message ?? error) } })
      })
      child.stdout.on('data', chunk => { stdout += chunk.toString('utf8') })
      child.stderr.on('data', chunk => {
        if (stderr.length < STDERR_LIMIT) stderr += chunk.toString('utf8')
      })
      child.on('close', code => {
        if (code === 0) {
          finish({ ok: true })
          return
        }
        // The CLI reports domain failures as one JSON object on stdout with a
        // non-zero exit; preserve its code/message instead of a generic exit.
        const reported = parseJsonOutput(stdout)
        if (reported !== null && typeof reported === 'object' && reported.ok === false) {
          finish({
            ok: false,
            error: {
              code: typeof reported.code === 'string' ? reported.code : 'admin-failed',
              message: typeof reported.message === 'string' ? reported.message : (stderr || `admin 退出码 ${String(code)}`),
            },
          })
          return
        }
        finish({ ok: false, error: { code: 'admin-failed', message: stderr || `admin 退出码 ${String(code)}` } })
      })
    })
  }

  return {
    /** Current job snapshot (no child handle). */
    job: () => snapshot(),

    /** Read index/vector facts for the saved root (key never enters this env). */
    async state() {
      const required = requireRoot()
      if (required.ok === false) return required
      const credential = await currentCredential()
      const result = await runOnce(['status', '--root', required.root], {
        timeoutMs: COMMAND_TIMEOUT_MS,
        keyPresent: credential.available && credential.value !== undefined,
      })
      if (result.ok === false) return result
      return { ok: true, value: normalizeAdminStatus(result.value) }
    },

    /**
     * Build or refresh the lexical index without touching the vector store.
     * The Python command passes `build_vectors=False`, so it never contacts the
     * embedding backend even when the semantic switch is on (T8-08).
     */
    async buildIndex() {
      const required = requireRoot()
      if (required.ok === false) return required
      if (jobBusy()) return { ok: false, error: adminError('job-running', '已有向量化任务在运行') }
      return runOnce(['index', '--root', required.root], { timeoutMs: INDEX_TIMEOUT_MS })
    },

    /**
     * Delete `<root>/.coderag/vectors` and keep the lexical index. The Python
     * command owns the path checks (symlink, containment, missing store) and
     * reports `removed` accordingly.
     */
    async removeVectors() {
      const required = requireRoot()
      if (required.ok === false) return required
      if (jobBusy()) return { ok: false, error: adminError('job-running', '已有向量化任务在运行') }
      const result = await runOnce(['remove-vectors', '--root', required.root], {
        timeoutMs: COMMAND_TIMEOUT_MS,
      })
      if (result.ok === false) return result
      const value = result.value !== null && typeof result.value === 'object' ? result.value : {}
      return {
        ok: true,
        value: {
          removed: value.removed === true,
          path: typeof value.path === 'string' ? value.path : '',
        },
      }
    },

    /** Probe the embedding backend; `backend` overrides the saved one. */
    async health(backend) {
      const root = rootOf()
      const credential = await currentCredential()
      const result = await runOnce(['health', '--root', root], {
        timeoutMs: COMMAND_TIMEOUT_MS,
        apiKey: credential.value,
        backend: HEALTH_BACKENDS.includes(backend) ? backend : undefined,
        forceSemantic: true,
      })
      if (result.ok === false) return result
      return { ok: true, value: normalizeHealth(result.value) }
    },

    /**
     * Start `ollama serve` detached and wait until its API answers.
     * An already-running server makes the poll succeed immediately.
     */
    async startLocal() {
      const values = options.readValues()
      const configuredUrl = typeof values.semanticUrl === 'string' ? values.semanticUrl.trim().replace(/\/+$/, '') : ''
      // start-local is specifically Ollama on this machine: never poll a cloud
      // or non-loopback URL, even if the settings point at one.
      const url = configuredUrl !== '' && values.semanticBackend !== 'openai' && isLoopbackUrl(configuredUrl)
        ? configuredUrl
        : DEFAULT_OLLAMA_URL
      let child
      let spawnError
      try {
        child = spawn('ollama', ['serve'], {
          detached: true,
          stdio: 'ignore',
          windowsHide: true,
          env: process.env,
        })
        child.once?.('error', error => { spawnError = error })
        child.unref()
      } catch (error) {
        return {
          ok: false,
          error: adminError('ollama-missing', `无法启动 ollama serve：${excerpt(error?.message ?? error)}`),
        }
      }
      const deadline = now() + LOCAL_START_TIMEOUT_MS
      let lastDetail = ''
      while (now() < deadline) {
        // ENOENT arrives asynchronously; fail fast instead of polling for 15s.
        if (spawnError !== undefined) {
          const code = spawnError?.code === 'ENOENT' ? 'ollama-missing' : 'ollama-start-failed'
          return {
            ok: false,
            error: adminError(code, `无法启动 ollama serve：${excerpt(spawnError?.message ?? spawnError)}`),
          }
        }
        try {
          const response = await fetchImpl(`${url}/api/tags`, { signal: AbortSignal.timeout(LOCAL_PROBE_TIMEOUT_MS) })
          if (response.ok) {
            const body = await response.json().catch(() => undefined)
            const models = Array.isArray(body?.models)
              ? body.models.flatMap(entry => typeof entry?.name === 'string' ? [entry.name] : [])
              : []
            return { ok: true, value: { url, models } }
          }
          lastDetail = `HTTP ${String(response.status)}`
        } catch (error) {
          lastDetail = excerpt(error?.message ?? error)
        }
        await sleep(LOCAL_POLL_INTERVAL_MS)
      }
      child?.kill?.('SIGTERM')
      return {
        ok: false,
        error: adminError(
          'ollama-unreachable',
          `已启动 ollama serve，但 ${String(Math.round(LOCAL_START_TIMEOUT_MS / 1000))} 秒内 ${url}/api/tags 未就绪${lastDetail === '' ? '' : `（最后错误：${lastDetail}）`}`,
        ),
      }
    },

    /** Start a resumable vector build; progress is reported through `job()`. */
    async vectorize() {
      const required = requireRoot()
      if (required.ok === false) return required
      // A stopped job's child may still be closing; never let a new job start
      // while a previous handle is alive. The `starting` flag closes the same
      // window while the credentials lookup is in flight, before a spawn
      // exists — otherwise two concurrent calls both spawn a child.
      if (jobBusy()) {
        return { ok: false, error: adminError('job-running', '已有向量化任务在运行') }
      }
      starting = true
      try {
        const credential = await currentCredential()
        const key = credential.value
        const command = pythonOf()
        const env = adminEnvironment(options.readValues(), { apiKey: key })
        job = {
          ...emptyJob(),
          status: 'running',
          startedAt: now(),
        }
        let child
        try {
          child = spawn(command, ['-c', ADMIN_LAUNCHER, 'vectorize', '--root', required.root], {
            cwd: ensurePrivateDir(),
            env,
            stdio: ['ignore', 'pipe', 'pipe'],
            windowsHide: true,
          })
        } catch (error) {
          job = { ...job, status: 'error', finishedAt: now(), error: adminError('admin-spawn-failed', excerpt(error?.message ?? error)) }
          return { ok: true, value: snapshot() }
        }
        const handle = { child, stopRequested: false, key }
        active = handle
        let stderr = ''
        const applyEvent = line => {
          let event
          try {
            event = JSON.parse(line)
          } catch {
            return
          }
          if (event === null || typeof event !== 'object') return
          if (event.event === 'start') {
            job = {
              ...job,
              total: typeof event.total_chunks === 'number' ? event.total_chunks : job.total,
              pending: typeof event.pending_chunks === 'number' ? event.pending_chunks : job.pending,
            }
            return
          }
          if (event.event === 'progress') {
            job = {
              ...job,
              status: 'running',
              embedded: typeof event.embedded === 'number' ? event.embedded : job.embedded,
              pending: typeof event.pending === 'number' ? event.pending : job.pending,
            }
            return
          }
          if (event.event === 'done') {
            job = {
              ...job,
              status: 'done',
              embedded: typeof event.chunks === 'number' ? event.chunks : job.embedded,
              pending: 0,
              model: typeof event.model === 'string' ? event.model : job.model,
              generatedAt: typeof event.generated_at === 'string' ? event.generated_at : job.generatedAt,
              finishedAt: now(),
            }
            return
          }
          if (event.event === 'error') {
            job = {
              ...job,
              status: 'error',
              error: adminError(
                typeof event.code === 'string' ? event.code : 'vectorize-failed',
                scrub(typeof event.message === 'string' ? event.message : '向量化失败', key, process.env[SEMANTIC_KEY_REF]),
              ),
            }
          }
        }
        const out = lineReader(applyEvent)
        child.stdout.on('data', chunk => out.push(chunk))
        child.stderr.on('data', chunk => {
          if (stderr.length < STDERR_LIMIT) stderr += chunk.toString('utf8')
        })
        child.on('error', error => {
          // A late error from a stopped handle must not touch the current job.
          if (active !== handle) return
          if (job.status === 'done') return
          job = {
            ...job,
            status: 'error',
            finishedAt: now(),
            error: adminError('admin-spawn-failed', scrub(excerpt(error?.message ?? error), key, process.env[SEMANTIC_KEY_REF])),
          }
        })
        child.on('close', code => {
          // Identity guard: a previous child's close may arrive after a new job
          // has started. It owns neither the job nor the active handle anymore.
          if (active !== handle) return
          const stopped = handle.stopRequested
          active = undefined
          if (job.status === 'done') return
          if (stopped) {
            job = { ...job, status: 'stopped', finishedAt: now(), error: null }
            return
          }
          job = code === 0
            ? { ...job, status: 'done', pending: 0, finishedAt: now() }
            : {
              ...job,
              status: 'error',
              finishedAt: now(),
              error: job.error ?? adminError('vectorize-failed', scrub(stderr || `admin 退出码 ${String(code)}`, key, process.env[SEMANTIC_KEY_REF])),
            }
        })
        return { ok: true, value: snapshot() }
      } finally {
        starting = false
      }
    },

    /** Ask the running build to stop; the CLI's checkpoint stays on disk. */
    stop() {
      if (active === undefined || job.status !== 'running' && job.status !== 'stopping') {
        return { ok: true, value: snapshot() }
      }
      const handle = active
      handle.stopRequested = true
      job = { ...job, status: 'stopping' }
      try {
        handle.child.kill('SIGTERM')
      } catch (error) {
        logger?.warn?.('coderag: could not stop the vectorize child')
        logger?.warn?.(error)
      }
      // A child that ignores SIGTERM must not leave the job 'stopping' forever.
      // The timer only touches the handle it was created for.
      const force = setTimeout(() => {
        forceTimers.delete(force)
        if (active !== handle) return
        try {
          handle.child.kill('SIGKILL')
        } catch {
          // The child already exited; nothing left to terminate.
        }
      }, 5000)
      force.unref?.()
      forceTimers.add(force)
      return { ok: true, value: snapshot() }
    },

    /** Stop the child and remove the private cwd when the plugin unloads. */
    dispose() {
      if (active !== undefined) {
        active.stopRequested = true
        try {
          active.child.kill('SIGTERM')
        } catch {
          // Already gone.
        }
        active = undefined
      }
      for (const timer of forceTimers) clearTimeout(timer)
      forceTimers.clear()
      if (privateDir !== undefined) {
        try {
          rmSync(privateDir, { recursive: true, force: true })
        } catch (error) {
          logger?.warn?.('coderag: could not remove the private admin cwd')
          logger?.warn?.(error)
        }
        privateDir = undefined
      }
    },

    /** Test/diagnostic access to the private directory (never the key). */
    privateDirectory: () => privateDir,
  }
}
