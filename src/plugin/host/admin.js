/**
 * Host side of the CodeRAG operations panel.
 *
 * Runs the Python admin CLI (`python -m dsh_coderag.admin`, T7-01) for vector
 * index status, embedding-backend health, and resumable vectorization, and owns
 * the one in-memory job the browser polls. The browser never talks to Python
 * directly: every call goes through an authenticated Host route.
 *
 * The API key is read from DSH's credentials service at call time and reaches
 * only the admin child environment. It is never returned, logged, or embedded
 * in an error message; captured output is scrubbed against the resolved value.
 *
 * Not responsible for HTTP framing or authentication (routes.js) or rendering.
 */

import { spawn as nodeSpawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import {
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

/** Default local embeddings URL; adjusted from the settings row when present. */
const DEFAULT_OLLAMA_URL = 'http://127.0.0.1:11434'

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

/** Replace a resolved secret in a diagnostic even if a child echoed it. */
function scrub(value, secret) {
  if (secret === undefined || secret === '') return value
  return value.split(secret).join('[redacted]')
}

/** Truncate child output into a single-line diagnostic. */
function excerpt(value) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  return text.length > ERROR_EXCERPT ? `${text.slice(0, ERROR_EXCERPT)}…` : text
}

/**
 * Build the environment handed to one admin child.
 * Settings values win over the ambient environment for every owned variable.
 * Only the health probe forces the semantic switch on; status/vectorize must
 * observe the saved switch so their answers match the GUI.
 * @param {Record<string, unknown>} values - normalized settings.
 * @param {string | undefined} apiKey - resolved cloud key.
 * @param {string | undefined} backend - backend override for a probe.
 * @param {boolean} [forceSemantic] - force `CODERAG_SEMANTIC=on`.
 * @returns {NodeJS.ProcessEnv} the child environment.
 */
export function adminEnvironment(values, apiKey, backend, forceSemantic = false) {
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
  if (forceSemantic) env.CODERAG_SEMANTIC = 'on'
  if (backend !== undefined && HEALTH_BACKENDS.includes(backend)) {
    env.CODERAG_SEMANTIC_BACKEND = backend
  }
  if (apiKey !== undefined && apiKey !== '') env[SEMANTIC_KEY_REF] = apiKey
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
 * @param {() => Promise<string | undefined>} options.resolveApiKey - credentials lookup.
 * @param {() => string | undefined} options.python - configured interpreter, when known.
 * @param {object} [options.logger] - cordis logger.
 * @param {Function} [options.spawn] - child_process.spawn replacement.
 * @param {Function} [options.fetch] - fetch replacement.
 * @param {Function} [options.sleep] - delay replacement.
 * @param {Function} [options.now] - clock replacement.
 * @returns {object} state/health/startLocal/vectorize/stop/job.
 */
export function createAdminService(options) {
  const spawn = options.spawn ?? nodeSpawn
  const fetchImpl = options.fetch ?? globalThis.fetch
  const sleep = options.sleep ?? (ms => new Promise(resolve => setTimeout(resolve, ms)))
  const now = options.now ?? (() => Date.now())
  const logger = options.logger

  /** One in-memory job; only this service mutates it. */
  let job = emptyJob()
  /** The running vectorize child, when there is one. */
  let active

  const rootOf = () => {
    const root = options.readValues().root
    return typeof root === 'string' ? root.trim() : ''
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

  /**
   * Run one admin command to completion and parse its JSON object.
   * @param {string[]} args - CLI arguments after the module name.
   * @param {{ timeoutMs: number, apiKey?: string, backend?: string }} config - invocation facts.
   * @returns {Promise<{ ok: true, value: unknown } | { ok: false, error: object }>}
   */
  async function runOnce(args, config) {
    const command = pythonOf()
    const env = adminEnvironment(options.readValues(), config.apiKey, config.backend, config.forceSemantic === true)
    return new Promise(resolve => {
      let settled = false
      let stdout = ''
      let stderr = ''
      let child
      const finish = result => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        if (result.ok === false) {
          const message = scrub(result.error.message, config.apiKey)
          resolve({ ok: false, error: adminError(result.error.code, excerpt(message)) })
          return
        }
        const parsed = parseJsonOutput(stdout)
        resolve(parsed === undefined
          ? { ok: false, error: adminError('admin-output-invalid', 'admin 输出不是 JSON') }
          : { ok: true, value: parsed })
      }
      const timer = setTimeout(() => {
        child?.kill('SIGTERM')
        finish({ ok: false, error: { code: 'admin-timeout', message: `admin 命令超过 ${config.timeoutMs}ms` } })
      }, config.timeoutMs)
      try {
        child = spawn(command, ['-m', 'dsh_coderag.admin', ...args], {
          cwd: tmpdir(),
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
        if (code === 0) finish({ ok: true })
        else finish({ ok: false, error: { code: 'admin-failed', message: stderr || `admin 退出码 ${String(code)}` } })
      })
    })
  }

  /** Resolve the API key once per call; a missing provider is not an error. */
  async function currentKey() {
    try {
      return await options.resolveApiKey()
    } catch (error) {
      logger?.warn?.('coderag: credentials lookup failed')
      logger?.warn?.(error)
      return undefined
    }
  }

  /** Require a saved root or report what the browser should tell the user. */
  function requireRoot() {
    const root = rootOf()
    return root === ''
      ? { ok: false, error: adminError('root-unset', '请先在设置里填写工作区根并保存') }
      : { ok: true, root }
  }

  return {
    /** Current job snapshot (no child handle). */
    job: () => snapshot(),

    /** Read index/vector facts for the saved root. */
    async state() {
      const required = requireRoot()
      if (required.ok === false) return required
      const key = await currentKey()
      const result = await runOnce(['status', '--root', required.root], { timeoutMs: COMMAND_TIMEOUT_MS, apiKey: key })
      if (result.ok === false) return result
      return { ok: true, value: normalizeAdminStatus(result.value) }
    },

    /** Probe the embedding backend; `backend` overrides the saved one. */
    async health(backend) {
      const root = rootOf()
      const key = await currentKey()
      const result = await runOnce(['health', '--root', root], {
        timeoutMs: COMMAND_TIMEOUT_MS,
        apiKey: key,
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
      // start-local is specifically Ollama: never poll a configured cloud URL.
      const url = configuredUrl !== '' && values.semanticBackend !== 'openai' ? configuredUrl : DEFAULT_OLLAMA_URL
      let child
      try {
        child = spawn('ollama', ['serve'], {
          detached: true,
          stdio: 'ignore',
          windowsHide: true,
          env: process.env,
        })
        child.on('error', () => {})
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
      if (job.status === 'running' || job.status === 'stopping') {
        return { ok: false, error: adminError('job-running', '已有向量化任务在运行') }
      }
      const key = await currentKey()
      const command = pythonOf()
      const env = adminEnvironment(options.readValues(), key)
      job = {
        ...emptyJob(),
        status: 'running',
        startedAt: now(),
      }
      let child
      try {
        child = spawn(command, ['-m', 'dsh_coderag.admin', 'vectorize', '--root', required.root], {
          cwd: tmpdir(),
          env,
          stdio: ['ignore', 'pipe', 'pipe'],
          windowsHide: true,
        })
      } catch (error) {
        job = { ...job, status: 'error', finishedAt: now(), error: adminError('admin-spawn-failed', excerpt(error?.message ?? error)) }
        return { ok: true, value: snapshot() }
      }
      active = { child, stopRequested: false, key }
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
              scrub(typeof event.message === 'string' ? event.message : '向量化失败', key),
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
        if (job.status === 'done') return
        job = {
          ...job,
          status: 'error',
          finishedAt: now(),
          error: adminError('admin-spawn-failed', scrub(excerpt(error?.message ?? error), key)),
        }
      })
      child.on('close', code => {
        const stopped = active?.stopRequested === true
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
            error: job.error ?? adminError('vectorize-failed', scrub(stderr || `admin 退出码 ${String(code)}`, key)),
          }
      })
      return { ok: true, value: snapshot() }
    },

    /** Ask the running build to stop; the CLI's checkpoint stays on disk. */
    stop() {
      if (active === undefined || job.status !== 'running' && job.status !== 'stopping') {
        return { ok: true, value: snapshot() }
      }
      active.stopRequested = true
      job = { ...job, status: 'stopping' }
      try {
        active.child.kill('SIGTERM')
      } catch (error) {
        logger?.warn?.('coderag: could not stop the vectorize child')
        logger?.warn?.(error)
      }
      // A child that ignores SIGTERM must not leave the job 'stopping' forever.
      const force = setTimeout(() => {
        try {
          active?.child.kill('SIGKILL')
        } catch {
          // The child already exited; nothing left to terminate.
        }
      }, 5000)
      force.unref?.()
      return { ok: true, value: snapshot() }
    },
  }
}
