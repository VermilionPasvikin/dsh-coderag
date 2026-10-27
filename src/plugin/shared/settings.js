/**
 * Field table and pure value rules shared by the Host plugin and the browser
 * settings form.
 *
 * Both bundles inline this module: the Host maps accepted settings to
 * `CODERAG_*` environment variables, while the browser half renders the same
 * fields and validates them before a write. Keeping the table here is what
 * guarantees the two halves cannot disagree about a field name, its type or the
 * environment variable it feeds.
 *
 * Not responsible for: reading Loader entries, calling DSH services, or
 * rendering anything. Every export is a pure function over plain JSON data.
 */

/** Settings namespace, row id and client slot key (see docs/settings-ui-plan.md). */
export const SETTINGS_NAMESPACE = 'coderag'
/** The npm package that ships both halves. */
export const BUNDLE_NAME = 'dsh-coderag'
/** The existing MCP row whose `config.env` this plugin keeps in sync. */
export const MCP_ROW_ID = 'mcp-coderag'
/** `plugins.row.config` key: `<package name>#<row id>`. */
export const ROW_CONFIG_KEY = `${BUNDLE_NAME}#${SETTINGS_NAMESPACE}`

/** Default values; also the values the schema declares. */
export const DEFAULT_VALUES = Object.freeze({
  root: '',
  maxFiles: 0,
  maxFileBytes: 0,
  extraExtensions: '',
  semantic: false,
  semanticBackend: '',
  semanticUrl: '',
  semanticModel: '',
  semanticTimeout: 0,
  semanticBatch: 0,
})

/** Backends accepted by the engine; the empty string means "engine default". */
export const SEMANTIC_BACKENDS = Object.freeze(['', 'ollama', 'openai'])

/** Engine defaults quoted in the form hints (see `config.py`). */
export const ENGINE_DEFAULTS = Object.freeze({
  maxFiles: 20000,
  maxFileBytes: 1048576,
  semanticTimeout: 30,
  semanticBatch: 16,
  semanticUrl: 'http://127.0.0.1:11434',
  semanticModel: 'bge-m3',
})

/**
 * The form's complete field table.
 *
 * `group` selects the form section; `kind` selects the control; `env` names the
 * environment variable this field owns on the MCP row (absent = not exported).
 * `integer` fields use `0` for "engine default".
 */
export const FIELDS = Object.freeze([
  Object.freeze({
    key: 'root',
    group: 'workspace',
    kind: 'text',
    label: '工作区根',
    env: 'CODERAG_ROOT',
    placeholder: '例如 F:\\Projects\\my-repo',
    hint: '引擎要索引的目录。留空时引擎以 WORKSPACE_INVALID 明确报错，不会猜目录。',
  }),
  Object.freeze({
    key: 'maxFiles',
    group: 'index',
    kind: 'integer',
    label: '文件数量上限',
    env: 'CODERAG_MAX_FILES',
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.maxFiles}）。达到上限会显式失败并报告实际数量，不静默截断。`,
  }),
  Object.freeze({
    key: 'maxFileBytes',
    group: 'index',
    kind: 'integer',
    label: '单文件字节上限',
    env: 'CODERAG_MAX_FILE_BYTES',
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.maxFileBytes}）。超过上限的文件计入 skipped.too_large。`,
  }),
  Object.freeze({
    key: 'extraExtensions',
    group: 'index',
    kind: 'text',
    label: '额外文件扩展名',
    env: 'CODERAG_EXTRA_EXTENSIONS',
    placeholder: '例如 .mxml,.as',
    hint: '逗号或空格分隔，只增不减：内置白名单不能移除，密钥文件黑名单仍然生效。',
  }),
  Object.freeze({
    key: 'semantic',
    group: 'semantic',
    kind: 'boolean',
    label: '启用语义检索',
    env: 'CODERAG_SEMANTIC',
    hint: '默认关闭，关闭时完全走 BM25，不联网、不读向量 sidecar。',
  }),
  Object.freeze({
    key: 'semanticBackend',
    group: 'semantic',
    kind: 'select',
    label: '语义后端',
    env: 'CODERAG_SEMANTIC_BACKEND',
    options: Object.freeze([
      Object.freeze({ value: '', label: '未设置（引擎默认 ollama）' }),
      Object.freeze({ value: 'ollama', label: 'ollama（本地，仅 loopback）' }),
      Object.freeze({ value: 'openai', label: 'openai（云端，需显式 URL/模型）' }),
    ]),
    hint: '云端后端会把已入库 chunk 文本（含工作区相对路径与符号名）发往所配服务。',
  }),
  Object.freeze({
    key: 'semanticUrl',
    group: 'semantic',
    kind: 'text',
    label: '语义服务 URL',
    env: 'CODERAG_SEMANTIC_URL',
    placeholder: ENGINE_DEFAULTS.semanticUrl,
    hint: '本地后端只允许 loopback；云端后端建议 https。',
  }),
  Object.freeze({
    key: 'semanticModel',
    group: 'semantic',
    kind: 'text',
    label: '语义模型',
    env: 'CODERAG_SEMANTIC_MODEL',
    placeholder: ENGINE_DEFAULTS.semanticModel,
    hint: '本地默认 bge-m3；云端后端必须显式给出。',
  }),
  Object.freeze({
    key: 'semanticTimeout',
    group: 'semantic',
    kind: 'integer',
    label: '语义请求超时（秒）',
    env: 'CODERAG_SEMANTIC_TIMEOUT',
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.semanticTimeout} 秒）。`,
  }),
  Object.freeze({
    key: 'semanticBatch',
    group: 'semantic',
    kind: 'integer',
    label: '语义批量大小',
    env: 'CODERAG_SEMANTIC_BATCH',
    hint: `0 = 引擎默认（${ENGINE_DEFAULTS.semanticBatch}）。`,
  }),
])

/** Form sections in render order. */
export const GROUPS = Object.freeze([
  Object.freeze({ id: 'workspace', title: '工作区', description: '决定索引哪个目录。' }),
  Object.freeze({ id: 'index', title: '索引范围', description: '控制收录哪些文件、最多收录多少。' }),
  Object.freeze({ id: 'semantic', title: '语义检索（可选）', description: '默认关闭；关闭时完全走 BM25。' }),
])

/** The extension-token grammar the Python engine enforces (`config.EXTENSION_TOKEN`). */
const EXTENSION_TOKEN = /^[A-Za-z0-9][A-Za-z0-9_+-]*$/

const INTEGER_KEYS = new Set(['maxFiles', 'maxFileBytes', 'semanticTimeout', 'semanticBatch'])

/**
 * Coerce one accepted Host value into the shape this module and env mapping use.
 * @param {string} key - field key from {@link FIELDS}.
 * @param {unknown} value - raw value from the settings snapshot or schema.
 * @returns {unknown} the normalized value (string, boolean or non-negative integer).
 */
function normalizeValue(key, value) {
  if (key === 'semantic') return value === true
  if (INTEGER_KEYS.has(key)) {
    const number = Math.floor(Number(value))
    return Number.isFinite(number) && number > 0 ? number : 0
  }
  if (typeof value === 'string') return value.trim()
  return value === undefined || value === null ? '' : String(value)
}

/**
 * Normalize a whole settings object.
 * @param {Record<string, unknown>} values - raw values (settings value or draft).
 * @returns {Record<string, unknown>} all ten fields, normalized.
 */
export function normalizeValues(values = {}) {
  const source = values !== null && typeof values === 'object' ? values : {}
  const result = {}
  for (const field of FIELDS) {
    const raw = Object.hasOwn(source, field.key) ? source[field.key] : DEFAULT_VALUES[field.key]
    result[field.key] = normalizeValue(field.key, raw)
  }
  return result
}

/**
 * Read a plugin Config whose fields are schemastery volatile references.
 * @param {Record<string, { get(): unknown } | unknown>} config - parsed Config.
 * @returns {Record<string, unknown>} all ten fields, normalized.
 */
export function valuesFromConfig(config) {
  const values = {}
  for (const field of FIELDS) {
    const slot = config?.[field.key]
    values[field.key] = typeof slot?.get === 'function' ? slot.get() : slot
  }
  return normalizeValues(values)
}

/**
 * Whether a settings object carries nothing worth exporting.
 * @param {Record<string, unknown>} values - normalized values.
 * @returns {boolean} true when every field is empty/false/zero.
 */
export function isEmptySettings(values) {
  const normalized = normalizeValues(values)
  return normalized.root === ''
    && normalized.extraExtensions === ''
    && !normalized.semantic
    && normalized.maxFiles === 0
    && normalized.maxFileBytes === 0
    && normalized.semanticBackend === ''
    && normalized.semanticUrl === ''
    && normalized.semanticModel === ''
    && normalized.semanticTimeout === 0
    && normalized.semanticBatch === 0
}

/**
 * Map settings onto the owned `CODERAG_*` variables.
 * @param {Record<string, unknown>} values - normalized values.
 * @returns {{ set: Record<string, string>, remove: string[] }} desired env additions and removals.
 */
export function envPlan(values) {
  const normalized = normalizeValues(values)
  const set = {}
  const remove = []
  for (const field of FIELDS) {
    if (field.env === undefined) continue
    const value = normalized[field.key]
    const text = field.kind === 'boolean' ? (value === true ? 'on' : '') : String(value)
    if (text === '' || value === 0) remove.push(field.env)
    else set[field.env] = text
  }
  return { set, remove }
}

/**
 * Merge the owned variables into an existing MCP row environment.
 * Every variable this plugin does not own is preserved verbatim.
 * @param {Record<string, string>} currentEnv - the MCP row's current env.
 * @param {Record<string, unknown>} values - normalized settings values.
 * @returns {Record<string, string>} the next env object.
 */
export function mergeOwnedEnv(currentEnv, values) {
  const next = currentEnv !== null && typeof currentEnv === 'object' ? { ...currentEnv } : {}
  const plan = envPlan(values)
  for (const name of plan.remove) delete next[name]
  for (const [name, value] of Object.entries(plan.set)) next[name] = value
  return next
}

/**
 * Validate a settings draft before it reaches the Host.
 * @param {Record<string, unknown>} values - possibly stringly-typed draft.
 * @returns {Array<{ field: string, message: string }>} one entry per rejected field.
 */
export function validateValues(values) {
  const draft = values !== null && typeof values === 'object' ? values : {}
  const errors = []
  const reject = (field, message) => errors.push({ field, message })

  for (const key of ['maxFiles', 'maxFileBytes', 'semanticTimeout', 'semanticBatch']) {
    const raw = Object.hasOwn(draft, key) ? draft[key] : DEFAULT_VALUES[key]
    const text = typeof raw === 'string' ? raw.trim() : String(raw)
    if (!/^(0|[1-9][0-9]*)$/.test(text)) reject(key, '需要 0 或正整数（0 = 引擎默认）。')
  }

  const extensions = String(draft.extraExtensions ?? '').trim()
  if (extensions !== '') {
    for (const token of extensions.split(/[\s,]+/).filter(Boolean)) {
      const bare = token.startsWith('.') ? token.slice(1) : token
      if (!EXTENSION_TOKEN.test(bare)) {
        reject('extraExtensions', `"${token}" 不是简单扩展名：不能含点、路径分隔符或通配符（例如 .mxml,.as）。`)
        break
      }
    }
  }

  const backend = String(draft.semanticBackend ?? '').trim()
  if (!SEMANTIC_BACKENDS.includes(backend)) reject('semanticBackend', '只支持 未设置 / ollama / openai。')

  const url = String(draft.semanticUrl ?? '').trim()
  if (url !== '' && !/^https?:\/\/[^\s]+$/i.test(url)) reject('semanticUrl', '需要以 http:// 或 https:// 开头的地址。')
  if (url !== '') {
    const loopback = /^https?:\/\/(?:127(?:\.\d+){3}|localhost|\[::1\])(?::\d+)?(?:\/|$)/i.test(url)
    if (backend === 'ollama' && !loopback) {
      reject('semanticUrl', 'ollama 后端只允许 loopback 地址（127.0.0.1 / localhost / [::1]）。')
    }
  }

  if (draft.semantic === true) {
    if (backend === 'openai') {
      if (url === '') reject('semanticUrl', '云端 openai 后端必须显式给出 URL。')
      if (String(draft.semanticModel ?? '').trim() === '') {
        reject('semanticModel', '云端 openai 后端必须显式给出模型名。')
      }
    }
  }
  return errors
}

/**
 * One-line description rendered for the row's `view: 'summary'`.
 * @param {Record<string, unknown>} values - normalized values.
 * @returns {string} the summary text.
 */
export function summarizeValues(values) {
  const normalized = normalizeValues(values)
  const workspace = normalized.root === '' ? '工作区未设置' : `工作区 ${normalized.root}`
  const semantic = normalized.semantic
    ? `语义检索 ${normalized.semanticBackend === '' ? 'ollama' : normalized.semanticBackend}`
    : '语义检索关闭'
  const files = normalized.maxFiles === 0 ? '文件上限默认' : `文件上限 ${normalized.maxFiles}`
  return `${workspace} · ${files} · ${semantic}`
}

/**
 * Stable comparison key for an env plan, used to skip redundant MCP restarts.
 * @param {{ set: Record<string, string>, remove: string[] }} plan - env plan.
 * @returns {string} the desired owned variables as sorted JSON.
 */
export function planKey(plan) {
  const keys = Object.keys(plan.set).sort()
  const remove = [...plan.remove].sort()
  return JSON.stringify([keys.map(key => [key, plan.set[key]]), remove])
}
