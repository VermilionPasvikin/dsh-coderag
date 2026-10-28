/**
 * Wire contract shared by the Host admin routes and the browser panels.
 *
 * The Python admin CLI (`python -m dsh_coderag.admin`, T7-01) owns the vector
 * index facts; this module only fixes the HTTP paths, the action vocabulary,
 * the credential reference, and the field whitelist each side may see.
 *
 * Not responsible for running commands or rendering: the Host service and the
 * client panels import these constants so a typo cannot silently split them.
 */

/** The credential the settings page stores the cloud API key under. */
export const SEMANTIC_KEY_REF = 'CODERAG_SEMANTIC_API_KEY'

/**
 * Environment marker for commands that must know whether a key exists without
 * receiving it. The admin CLI reads this instead of the key for `status`.
 */
export const SEMANTIC_KEY_PRESENT_ENV = 'CODERAG_SEMANTIC_KEY_PRESENT'

/** Host admin route paths, relative to the Web origin. */
export const ADMIN_STATE_PATH = '/coderag-admin/state'
export const ADMIN_ACTION_PATH = '/coderag-admin/action'
export const ADMIN_JOB_PATH = '/coderag-admin/job'

/** Every action the POST route accepts. */
export const ADMIN_ACTIONS = Object.freeze(['health', 'start-local', 'vectorize', 'stop', 'refresh'])

/** Backends a health check can target (the form's own vocabulary). */
export const HEALTH_BACKENDS = Object.freeze(['ollama', 'openai'])

/** Job lifecycle states. `stopping` is transient between stop and the exit event. */
export const JOB_STATES = Object.freeze(['idle', 'running', 'stopping', 'stopped', 'done', 'error'])

/** Empty job snapshot rendered before the first run. */
export function emptyJob() {
  return {
    status: 'idle',
    total: null,
    embedded: 0,
    pending: null,
    model: null,
    generatedAt: null,
    startedAt: null,
    finishedAt: null,
    error: null,
  }
}

/** Coerce a finite non-negative integer, else the fallback. */
function count(value, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : fallback
}

/** Coerce an optional string, else null. */
function text(value) {
  return typeof value === 'string' && value.length > 0 ? value : null
}

/**
 * Project the admin `status` JSON onto the fields the browser may see.
 * The whitelist is deliberate: the CLI output is untrusted input here, and a
 * future field must not silently reach a response that could expose a secret.
 * @param {unknown} raw - parsed JSON from `admin status`.
 * @returns {object} normalized status with no credential value.
 */
export function normalizeAdminStatus(raw) {
  const source = raw !== null && typeof raw === 'object' ? raw : {}
  const config = source.config !== null && typeof source.config === 'object' ? source.config : {}
  return {
    index_exists: source.index_exists === true,
    vector_exists: source.vector_exists === true,
    model: text(source.model),
    dim: typeof source.dim === 'number' && Number.isFinite(source.dim) ? Math.floor(source.dim) : null,
    total_chunks: count(source.total_chunks),
    vectorized_chunks: count(source.vectorized_chunks),
    pending_chunks: count(source.pending_chunks),
    stale_chunks: count(source.stale_chunks),
    generated_at: text(source.generated_at),
    checkpoint_vectors: count(source.checkpoint_vectors),
    config: {
      enabled: config.enabled === true,
      backend: text(config.backend) ?? '',
      url: text(config.url) ?? '',
      model: text(config.model) ?? '',
      allow_remote: config.allow_remote === true,
      key_present: config.key_present === true,
    },
  }
}

/**
 * Project the admin `health` JSON onto the browser fields.
 * @param {unknown} raw - parsed JSON from `admin health`.
 * @returns {object} normalized health result.
 */
export function normalizeHealth(raw) {
  const source = raw !== null && typeof raw === 'object' ? raw : {}
  return {
    ok: source.ok === true,
    backend: text(source.backend) ?? '',
    url: text(source.url) ?? '',
    model: text(source.model) ?? '',
    model_present: source.model_present === true,
    detail: text(source.detail) ?? '',
    code: text(source.code) ?? '',
    models: Array.isArray(source.models)
      ? source.models.flatMap(entry =>
        typeof entry === 'string' && entry.length > 0
          ? [entry]
          : entry !== null && typeof entry === 'object' && typeof entry.name === 'string' && entry.name.length > 0
            ? [entry.name]
            : [])
      : [],
  }
}

/**
 * One error the browser can render verbatim.
 * @param {string} code - stable machine code.
 * @param {string} message - human-readable, already free of secrets.
 * @returns {{ code: string, message: string }} the error envelope.
 */
export function adminError(code, message) {
  return { code, message }
}
