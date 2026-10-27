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
  extraExtensions: '.mxml,.as',
  semantic: true,
  semanticBackend: 'ollama',
  semanticUrl: 'http://127.0.0.1:11434',
  semanticModel: 'bge-m3',
  semanticTimeout: 5,
  semanticBatch: 4,
}

test('the settings namespace and row key follow the documented contract', () => {
  assert.equal(SETTINGS_NAMESPACE, 'coderag')
  assert.equal(MCP_ROW_ID, 'mcp-coderag')
  assert.equal(ROW_CONFIG_KEY, 'dsh-coderag#coderag')
})

test('the field table covers exactly the owned environment variables', () => {
  assert.deepEqual(FIELDS.map(field => field.key), Object.keys(DEFAULT_VALUES))
  assert.deepEqual(
    FIELDS.filter(field => field.env !== undefined).map(field => field.env),
    [
      'CODERAG_ROOT', 'CODERAG_MAX_FILES', 'CODERAG_MAX_FILE_BYTES', 'CODERAG_EXTRA_EXTENSIONS',
      'CODERAG_SEMANTIC', 'CODERAG_SEMANTIC_BACKEND', 'CODERAG_SEMANTIC_URL',
      'CODERAG_SEMANTIC_MODEL', 'CODERAG_SEMANTIC_TIMEOUT', 'CODERAG_SEMANTIC_BATCH',
    ],
  )
})

test('normalization trims strings and clamps bad numbers to the engine default', () => {
  const values = normalizeValues({
    root: '  /workspace  ', maxFiles: '12', maxFileBytes: -1,
    extraExtensions: ' .mxml ', semantic: 1, semanticTimeout: Number.NaN,
  })
  assert.equal(values.root, '/workspace')
  assert.equal(values.maxFiles, 12)
  assert.equal(values.maxFileBytes, 0)
  assert.equal(values.extraExtensions, '.mxml')
  assert.equal(values.semantic, false)
  assert.equal(values.semanticTimeout, 0)
  assert.equal(values.semanticModel, '')
})

test('an entirely empty settings object is recognized as "nothing to say"', () => {
  assert.equal(isEmptySettings({}), true)
  assert.equal(isEmptySettings(DEFAULT_VALUES), true)
  assert.equal(isEmptySettings({ semantic: false, semanticBackend: '', semanticUrl: ' ' }), true)
  assert.equal(isEmptySettings({ root: '/workspace' }), false)
  assert.equal(isEmptySettings({ semantic: true }), false)
})

test('the env plan exports strings and marks cleared fields for removal', () => {
  const plan = envPlan(OLLAMA)
  assert.deepEqual(plan.set, {
    CODERAG_ROOT: '/workspace',
    CODERAG_MAX_FILES: '100',
    CODERAG_MAX_FILE_BYTES: '2048',
    CODERAG_EXTRA_EXTENSIONS: '.mxml,.as',
    CODERAG_SEMANTIC: 'on',
    CODERAG_SEMANTIC_BACKEND: 'ollama',
    CODERAG_SEMANTIC_URL: 'http://127.0.0.1:11434',
    CODERAG_SEMANTIC_MODEL: 'bge-m3',
    CODERAG_SEMANTIC_TIMEOUT: '5',
    CODERAG_SEMANTIC_BATCH: '4',
  })
  assert.deepEqual(plan.remove, [])
  const cleared = envPlan({ ...OLLAMA, maxFiles: 0, semantic: false, extraExtensions: '' })
  assert.equal(cleared.set.CODERAG_MAX_FILES, undefined)
  assert.equal(cleared.set.CODERAG_SEMANTIC, undefined)
  assert.deepEqual(cleared.remove.sort(), ['CODERAG_EXTRA_EXTENSIONS', 'CODERAG_MAX_FILES', 'CODERAG_SEMANTIC'])
})

test('merging preserves variables this plugin does not own', () => {
  const current = {
    CODERAG_MAX_TOKENS: '4000',
    CODERAG_SEMANTIC_API_KEY: 'secret',
    CODERAG_ROOT: '/old',
    UNRELATED: 'kept',
  }
  const next = mergeOwnedEnv(current, { ...OLLAMA, root: '' })
  assert.equal(next.CODERAG_MAX_TOKENS, '4000')
  assert.equal(next.CODERAG_SEMANTIC_API_KEY, 'secret')
  assert.equal(next.UNRELATED, 'kept')
  assert.equal(next.CODERAG_ROOT, undefined)
  assert.equal(next.CODERAG_SEMANTIC, 'on')
  assert.equal(current.CODERAG_ROOT, '/old', 'the input env must not be mutated')
})

test('validation accepts the documented values and the empty integer shorthand', () => {
  assert.deepEqual(validateValues(OLLAMA), [])
  assert.deepEqual(validateValues({ ...OLLAMA, maxFiles: '', semanticTimeout: '0', semanticBatch: '2048' }), [])
})

test('validation rejects malformed numbers, extensions, backends and URLs', () => {
  const fields = values => validateValues({ ...OLLAMA, ...values }).map(error => error.field)
  assert.deepEqual(fields({ maxFiles: '1.5' }), ['maxFiles'])
  assert.deepEqual(fields({ maxFiles: '-1' }), ['maxFiles'])
  assert.deepEqual(fields({ extraExtensions: 'a.b' }), ['extraExtensions'])
  assert.deepEqual(fields({ extraExtensions: '.mxml,*/x' }), ['extraExtensions'])
  assert.deepEqual(fields({ semanticBackend: 'local' }), ['semanticBackend'])
  assert.deepEqual(fields({ semanticUrl: 'ftp://example.com' }), ['semanticUrl'])
  assert.deepEqual(fields({ semanticBackend: 'ollama', semanticUrl: 'http://example.com:11434' }), ['semanticUrl'])
})

test('the cloud backend requires an explicit URL and model', () => {
  const cloud = { ...OLLAMA, semanticBackend: 'openai', semanticUrl: '', semanticModel: '' }
  assert.deepEqual(validateValues(cloud).map(error => error.field).sort(), ['semanticModel', 'semanticUrl'])
  assert.deepEqual(validateValues({ ...cloud, semanticUrl: 'https://api.example.com/v1', semanticModel: 'm' }), [])
})

test('the row summary names the workspace, file cap and semantic state', () => {
  const summary = summarizeValues(OLLAMA)
  assert.match(summary, /工作区 \/workspace/)
  assert.match(summary, /文件上限 100/)
  assert.match(summary, /语义检索 ollama/)
  assert.match(summarizeValues(DEFAULT_VALUES), /工作区未设置/)
  assert.match(summarizeValues(DEFAULT_VALUES), /语义检索关闭/)
})
