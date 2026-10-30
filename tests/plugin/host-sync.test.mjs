/**
 * Behavior tests for the MCP-row synchronization.
 *
 * A fake Loader entry stands in for `mcp-coderag`: the real row uses the same
 * `entry.update({ config })` contract, which the live-runtime probe in
 * `scripts/experiments/host-settings-sync-probe.mjs` exercises against the DSH
 * build installed on this machine.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { findMCPEntry, ownedEnvMismatch, syncMCPRow } from '../../src/plugin/sync.js'
import { mergeOwnedEnv, envPlan } from '../../src/plugin/shared/settings.js'

const SETTINGS = {
  root: '/workspace',
  maxFiles: 100,
  maxFileBytes: 0,
  maxTokens: 5000,
  extraExtensions: '',
  semantic: true,
  semanticBackend: 'ollama',
  semanticUrl: '',
  semanticModel: '',
  semanticQueryTimeout: 0,
  semanticBatch: 0,
  semanticMaxChunks: 50000,
  semanticAllowRemote: false,
}

/** Build one fake Loader with one row. */
function fakeLoader(rows) {
  return {
    entries() {
      return rows.values()
    },
  }
}

/** Build one fake entry; `apply` records the resolved env of every mount. */
function fakeEntry({ env = {}, register } = {}) {
  const applies = []
  const entry = {
    options: { id: 'mcp-coderag', config: { serverName: 'coderag', env } },
    applies,
    updates: 0,
    fiberUpdates: [],
    async update({ config }) {
      this.updates += 1
      this.options.config = config
      this.fiber = this.createFiber(config)
    },
    createFiber(config) {
      const fiber = {
        config: { env: { ...config.env } },
        async await() {},
        update(next) {
          entry.fiberUpdates.push(next)
          fiber.config = { env: { ...next.env } }
        },
      }
      return fiber
    },
  }
  if (register !== undefined) register(entry)
  return entry
}

test('findMCPEntry finds the row by its local id, nested trees included', () => {
  const mcp = fakeEntry()
  const loader = fakeLoader(new Map([['coderag', { options: { id: 'coderag' } }], ['mcp-coderag', mcp]]))
  assert.equal(findMCPEntry(loader), mcp)
  assert.equal(findMCPEntry(fakeLoader(new Map())), undefined)
  assert.equal(findMCPEntry(undefined), undefined)
})

test('ownedEnvMismatch ignores variables the plugin does not own', () => {
  const plan = envPlan(SETTINGS)
  assert.equal(ownedEnvMismatch({ CODERAG_MAX_TOKENS: '4000' }, plan), true)
  assert.equal(ownedEnvMismatch({
    CODERAG_ROOT: '/workspace', CODERAG_MAX_FILES: '100', CODERAG_MAX_TOKENS: '5000',
    CODERAG_SEMANTIC: 'on', CODERAG_SEMANTIC_BACKEND: 'ollama', CODERAG_SEMANTIC_MAX_CHUNKS: '50000',
    CODERAG_SEMANTIC_API_KEY: 'secret', KEEP: '1',
  }, plan), false)
  assert.equal(ownedEnvMismatch({
    CODERAG_ROOT: '/workspace', CODERAG_MAX_FILES: '100', CODERAG_MAX_TOKENS: '5000',
    CODERAG_SEMANTIC: 'on', CODERAG_SEMANTIC_BACKEND: 'ollama', CODERAG_SEMANTIC_MAX_CHUNKS: '50000',
    CODERAG_EXTRA_EXTENSIONS: 'stale',
  }, plan), true)
  assert.equal(ownedEnvMismatch({
    CODERAG_ROOT: '/workspace', CODERAG_MAX_FILES: '100', CODERAG_MAX_TOKENS: '5000',
    CODERAG_SEMANTIC: 'on', CODERAG_SEMANTIC_BACKEND: 'ollama', CODERAG_SEMANTIC_MAX_CHUNKS: '50000',
    CODERAG_SEMANTIC_ALLOW_REMOTE: '1',
  }, plan), true)
})

test('an unchanged row is not restarted', async () => {
  const entry = fakeEntry({ env: mergeOwnedEnv({}, SETTINGS) })
  const outcome = await syncMCPRow(entry, SETTINGS)
  assert.equal(outcome, 'unchanged')
  assert.equal(entry.updates, 0)
})

test('a changed row is updated in memory and keeps unrelated env and expressions', async () => {
  const expression = { __jsExpr: "'from-env'" }
  const entry = fakeEntry({ env: { KEEP: '1', CODERAG_SEMANTIC_API_KEY: expression, CODERAG_ROOT: '/old' } })
  const outcome = await syncMCPRow(entry, SETTINGS)
  assert.equal(outcome, 'synced')
  assert.equal(entry.updates, 1)
  assert.deepEqual(entry.options.config.env, {
    KEEP: '1',
    CODERAG_SEMANTIC_API_KEY: expression,
    CODERAG_ROOT: '/workspace',
    CODERAG_MAX_FILES: '100',
    CODERAG_MAX_TOKENS: '5000',
    CODERAG_SEMANTIC: 'on',
    CODERAG_SEMANTIC_BACKEND: 'ollama',
    CODERAG_SEMANTIC_MAX_CHUNKS: '50000',
  })
  assert.deepEqual(entry.fiberUpdates, [])
})

test('a row that missed the first update is force-restarted with the accepted config', async () => {
  const entry = fakeEntry({ env: { KEEP: '1' } })
  // Simulate a mount that ignored the config handed to entry.update.
  entry.update = async function update({ config }) {
    this.updates += 1
    this.options.config = config
    this.fiber = {
      config: { env: { KEEP: '1' } },
      async await() {},
      update(next) {
        entry.fiberUpdates.push(next)
        this.config = { env: { ...next.env } }
      },
    }
  }
  const outcome = await syncMCPRow(entry, SETTINGS)
  assert.equal(outcome, 'forced')
  assert.equal(entry.updates, 1)
  assert.equal(entry.fiberUpdates.length, 1)
  assert.equal(entry.fiberUpdates[0].env.CODERAG_ROOT, '/workspace')
  assert.equal(entry.fiber.config.env.CODERAG_MAX_FILES, '100')
})

test('a cleared setting removes exactly its owned variable', async () => {
  const entry = fakeEntry({ env: { CODERAG_ROOT: '/old', CODERAG_MAX_FILES: '100', CODERAG_MAX_TOKENS: '5000', KEEP: '1' } })
  const outcome = await syncMCPRow(entry, { ...SETTINGS, maxFiles: 0 })
  assert.equal(outcome, 'synced')
  assert.equal(entry.options.config.env.CODERAG_MAX_FILES, undefined)
  assert.equal(entry.options.config.env.KEEP, '1')
  assert.equal(entry.options.config.env.serverName, undefined)
})

test('the remote opt-in reaches the row only when it is enabled', async () => {
  const withRemote = fakeEntry({ env: {} })
  await syncMCPRow(withRemote, { ...SETTINGS, semanticAllowRemote: true })
  assert.equal(withRemote.options.config.env.CODERAG_SEMANTIC_ALLOW_REMOTE, '1')
  const withoutRemote = fakeEntry({ env: { CODERAG_SEMANTIC_ALLOW_REMOTE: '1' } })
  await syncMCPRow(withoutRemote, SETTINGS)
  assert.equal(withoutRemote.options.config.env.CODERAG_SEMANTIC_ALLOW_REMOTE, undefined)
})

test('the resolved cloud key is merged into the MCP env', async () => {
  const entry = fakeEntry({ env: { KEEP: '1' } })
  const outcome = await syncMCPRow(entry, SETTINGS, { apiKey: 'sk-test-secret' })
  assert.equal(outcome, 'synced')
  assert.equal(entry.options.config.env.CODERAG_SEMANTIC_API_KEY, 'sk-test-secret')
  assert.equal(entry.options.config.env.KEEP, '1')
})

test('a provider that is unavailable keeps the row key the child already has', async () => {
  const entry = fakeEntry({ env: { CODERAG_SEMANTIC_API_KEY: 'sk-existing' } })
  const outcome = await syncMCPRow(entry, { ...SETTINGS, maxFiles: 0 })
  assert.equal(outcome, 'synced')
  assert.equal(entry.options.config.env.CODERAG_SEMANTIC_API_KEY, 'sk-existing')
  assert.equal(entry.options.config.env.CODERAG_MAX_FILES, undefined)
})

test('a provider that reports the key unset clears the stale row key', async () => {
  const entry = fakeEntry({ env: { CODERAG_SEMANTIC_API_KEY: 'sk-deleted', KEEP: '1' } })
  const outcome = await syncMCPRow(entry, SETTINGS, { clearKey: true })
  assert.equal(outcome, 'synced')
  assert.equal(entry.options.config.env.CODERAG_SEMANTIC_API_KEY, undefined)
  assert.equal(entry.options.config.env.KEEP, '1')
  // The live fiber must observe the removal too, not just the entry options.
  assert.equal(entry.fiber.config.env.CODERAG_SEMANTIC_API_KEY, undefined)
})

test('a rotated key alone restarts the row', async () => {
  const entry = fakeEntry({ env: { CODERAG_SEMANTIC_API_KEY: 'sk-old' } })
  const outcome = await syncMCPRow(entry, SETTINGS, { apiKey: 'sk-new' })
  assert.equal(outcome, 'synced')
  assert.equal(entry.options.config.env.CODERAG_SEMANTIC_API_KEY, 'sk-new')
})
