/**
 * Behavior tests for the settings → environment mapping shared by both halves.
 *
 * These are the rules the Host applies on every save: which variables the
 * plugin owns, when a value means "unset", and which drafts the browser must
 * reject before the write reaches the Host.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  DEFAULT_VALUES,
  FIELDS,
  MCP_ROW_ID,
  ROW_CONFIG_KEY,
  SETTINGS_NAMESPACE,
  envPlan,
  isEmptySettings,
  mergeOwnedEnv,
  normalizeValues,
  summarizeValues,
  validateValues,
} from '../../src/plugin/shared/settings.js'

const OLLAMA = {
  root: '/workspace',
  maxFiles: 100,
  maxFileBytes: 2048,
  maxTokens: 5000,
  extraExtensions: '.mxml,.as',
  semantic: true,
  semanticBackend: 'ollama',
  semanticUrl: 'http://127.0.0.1:11434',
  semanticModel: 'bge-m3',
  semanticQueryTimeout: 5,
  semanticBatch: 4,
  semanticMaxChunks: 50000,
  semanticAllowRemote: false,
}

test('the settings namespace and row key follow the documented contract', () => {
  assert.equal(SETTINGS_NAMESPACE, 'coderag')
  assert.equal(MCP_ROW_ID, 'mcp-coderag')
  assert.equal(ROW_CONFIG_KEY, 'dsh-coderag#coderag')
})

test('the field table covers all thirteen owned environment variables', () => {
  assert.deepEqual(FIELDS.map(field => field.key), Object.keys(DEFAULT_VALUES))
  assert.deepEqual(
    FIELDS.filter(field => field.env !== undefined).map(field => field.env),
    [
      'CODERAG_ROOT', 'CODERAG_MAX_FILES', 'CODERAG_MAX_FILE_BYTES', 'CODERAG_MAX_TOKENS',
      'CODERAG_EXTRA_EXTENSIONS', 'CODERAG_SEMANTIC', 'CODERAG_SEMANTIC_BACKEND',
      'CODERAG_SEMANTIC_URL', 'CODERAG_SEMANTIC_MODEL', 'CODERAG_SEMANTIC_QUERY_TIMEOUT',
      'CODERAG_SEMANTIC_BATCH', 'CODERAG_SEMANTIC_MAX_CHUNKS', 'CODERAG_SEMANTIC_ALLOW_REMOTE',
    ],
  )
})

test('every field carries a label and a one-line hint', () => {
  for (const field of FIELDS) {
    assert.equal(typeof field.label, 'string')
    assert.ok(field.label.length > 0)
    assert.equal(typeof field.hint, 'string')
    assert.ok(field.hint.length > 0)
  }
})

test('normalization trims strings and clamps bad numbers to the engine default', () => {
  const values = normalizeValues({
    root: '  /workspace  ', maxFiles: '12', maxFileBytes: -1, maxTokens: 'abc',
    extraExtensions: ' .mxml ', semantic: 1, semanticQueryTimeout: Number.NaN,
    semanticMaxChunks: '9000', semanticAllowRemote: 1,
  })
  assert.equal(values.root, '/workspace')
  assert.equal(values.maxFiles, 12)
  assert.equal(values.maxFileBytes, 0)
  assert.equal(values.maxTokens, 0)
  assert.equal(values.extraExtensions, '.mxml')
  assert.equal(values.semantic, false)
  assert.equal(values.semanticQueryTimeout, 0)
  assert.equal(values.semanticModel, '')
  assert.equal(values.semanticMaxChunks, 9000)
  assert.equal(values.semanticAllowRemote, false)
})

test('an entirely empty settings object is recognized as "nothing to say"', () => {
  assert.equal(isEmptySettings({}), true)
  assert.equal(isEmptySettings(DEFAULT_VALUES), true)
  assert.equal(isEmptySettings({ semantic: false, semanticBackend: '', semanticUrl: ' ' }), true)
  assert.equal(isEmptySettings({ root: '/workspace' }), false)
  assert.equal(isEmptySettings({ semantic: true }), false)
  assert.equal(isEmptySettings({ maxTokens: 4000 }), false)
  assert.equal(isEmptySettings({ semanticMaxChunks: 100000 }), false)
  assert.equal(isEmptySettings({ semanticAllowRemote: true }), false)
})

test('the env plan exports strings and marks cleared fields for removal', () => {
  const plan = envPlan(OLLAMA)
  assert.deepEqual(plan.set, {
    CODERAG_ROOT: '/workspace',
    CODERAG_MAX_FILES: '100',
    CODERAG_MAX_FILE_BYTES: '2048',
    CODERAG_MAX_TOKENS: '5000',
    CODERAG_EXTRA_EXTENSIONS: '.mxml,.as',
    CODERAG_SEMANTIC: 'on',
    CODERAG_SEMANTIC_BACKEND: 'ollama',
    CODERAG_SEMANTIC_URL: 'http://127.0.0.1:11434',
    CODERAG_SEMANTIC_MODEL: 'bge-m3',
    CODERAG_SEMANTIC_QUERY_TIMEOUT: '5',
    CODERAG_SEMANTIC_BATCH: '4',
    CODERAG_SEMANTIC_MAX_CHUNKS: '50000',
  })
  assert.deepEqual(plan.remove, ['CODERAG_SEMANTIC_ALLOW_REMOTE'])
  const cleared = envPlan({ ...OLLAMA, maxFiles: 0, maxTokens: 0, semantic: false, extraExtensions: '', semanticMaxChunks: 0 })
  assert.equal(cleared.set.CODERAG_MAX_FILES, undefined)
  assert.equal(cleared.set.CODERAG_SEMANTIC, undefined)
  assert.equal(cleared.set.CODERAG_MAX_TOKENS, undefined)
  assert.equal(cleared.set.CODERAG_SEMANTIC_MAX_CHUNKS, undefined)
  assert.deepEqual(cleared.remove.sort(), [
    'CODERAG_EXTRA_EXTENSIONS', 'CODERAG_MAX_FILES', 'CODERAG_MAX_TOKENS',
    'CODERAG_SEMANTIC', 'CODERAG_SEMANTIC_ALLOW_REMOTE', 'CODERAG_SEMANTIC_MAX_CHUNKS',
  ])
})

test('the remote opt-in uses the "1" spelling the engine compares against', () => {
  const plan = envPlan({ ...OLLAMA, semanticBackend: 'openai', semanticUrl: 'https://api.example.com/v1', semanticAllowRemote: true })
  assert.equal(plan.set.CODERAG_SEMANTIC_ALLOW_REMOTE, '1')
  const off = envPlan({ ...OLLAMA, semanticAllowRemote: false })
  assert.deepEqual(off.remove, ['CODERAG_SEMANTIC_ALLOW_REMOTE'])
})

test('merging preserves the API key and unrelated variables', () => {
  const current = {
    CODERAG_SEMANTIC_API_KEY: 'secret',
    CODERAG_ROOT: '/old',
    CODERAG_MAX_TOKENS: '8000',
    UNRELATED: 'kept',
  }
  const next = mergeOwnedEnv(current, { ...OLLAMA, root: '', maxTokens: 0 })
  assert.equal(next.CODERAG_SEMANTIC_API_KEY, 'secret')
  assert.equal(next.UNRELATED, 'kept')
  assert.equal(next.CODERAG_ROOT, undefined)
  assert.equal(next.CODERAG_MAX_TOKENS, undefined)
  assert.equal(next.CODERAG_SEMANTIC, 'on')
  assert.equal(current.CODERAG_ROOT, '/old', 'the input env must not be mutated')
})

test('validation accepts the documented values and the empty integer shorthand', () => {
  assert.deepEqual(validateValues(OLLAMA), [])
  assert.deepEqual(validateValues({
    ...OLLAMA, maxFiles: '', maxTokens: '', semanticQueryTimeout: '0', semanticBatch: '2048', semanticMaxChunks: '',
  }), [])
})

test('validation rejects malformed numbers, extensions, backends and URLs', () => {
  const fields = values => validateValues({ ...OLLAMA, ...values }).map(error => error.field)
  assert.deepEqual(fields({ maxFiles: '1.5' }), ['maxFiles'])
  assert.deepEqual(fields({ maxFiles: '-1' }), ['maxFiles'])
  assert.deepEqual(fields({ maxTokens: '-1' }), ['maxTokens'])
  assert.deepEqual(fields({ semanticMaxChunks: 'x' }), ['semanticMaxChunks'])
  assert.deepEqual(fields({ extraExtensions: 'a.b' }), ['extraExtensions'])
  assert.deepEqual(fields({ extraExtensions: '.mxml,*/x' }), ['extraExtensions'])
  assert.deepEqual(fields({ semanticBackend: 'local' }), ['semanticBackend'])
  assert.deepEqual(fields({ semanticUrl: 'ftp://example.com' }), ['semanticUrl'])
  assert.deepEqual(fields({ semanticBackend: 'ollama', semanticUrl: 'http://example.com:11434' }), ['semanticUrl'])
})

test('the cloud backend requires an explicit URL, model and remote opt-in', () => {
  const cloud = { ...OLLAMA, semanticBackend: 'openai', semanticUrl: '', semanticModel: '' }
  assert.deepEqual(validateValues(cloud).map(error => error.field).sort(), ['semanticModel', 'semanticUrl'])
  const remote = { ...OLLAMA, semanticBackend: 'openai', semanticUrl: 'https://api.example.com/v1', semanticModel: 'm' }
  assert.deepEqual(validateValues(remote).map(error => error.field), ['semanticAllowRemote'])
  assert.deepEqual(validateValues({ ...remote, semanticAllowRemote: true }), [])
  const loopback = { ...remote, semanticUrl: 'http://127.0.0.1:8080/v1', semanticAllowRemote: false }
  assert.deepEqual(validateValues(loopback), [])
})

test('the row summary names the workspace, file cap and semantic state', () => {
  const summary = summarizeValues(OLLAMA)
  assert.match(summary, /工作区 \/workspace/)
  assert.match(summary, /文件上限 100/)
  assert.match(summary, /语义检索 ollama/)
  assert.match(summarizeValues(DEFAULT_VALUES), /工作区未设置/)
  assert.match(summarizeValues(DEFAULT_VALUES), /语义检索关闭/)
})
