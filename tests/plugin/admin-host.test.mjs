/**
 * Behavior tests for the Host admin service: CLI invocation, streaming job
 * parsing, stop, local Ollama startup, and the invariant that the resolved key
 * reaches only child environments and never a browser-visible payload.
 */

import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'
import { test } from 'node:test'
import {
  adminEnvironment,
  createAdminService,
  parseJsonOutput,
} from '../../src/plugin/host/admin.js'

const tick = () => new Promise(resolve => setImmediate(resolve))

const VALUES = {
  root: 'F:\\workspace',
  maxFiles: 100,
  maxFileBytes: 0,
  maxTokens: 0,
  extraExtensions: '',
  semantic: true,
  semanticBackend: 'ollama',
  semanticUrl: '',
  semanticModel: '',
  semanticTimeout: 0,
  semanticBatch: 0,
  semanticMaxChunks: 0,
  semanticAllowRemote: false,
}

/** Spawn replacement that records each call and hands back a controllable child. */
function spawnRecorder() {
  const calls = []
  const spawn = (command, args, options) => {
    const child = new EventEmitter()
    child.stdout = new PassThrough()
    child.stderr = new PassThrough()
    child.killed = false
    child.kill = () => { child.killed = true }
    child.unref = () => {}
    calls.push({ command, args, options, child })
    return child
  }
  return { spawn, calls }
}

/** Build a service over recorded spawns and a fixed key. */
function service(overrides = {}) {
  const recorder = spawnRecorder()
  const value = createAdminService({
    readValues: () => VALUES,
    resolveApiKey: async () => 'sk-test-secret',
    python: () => 'python-test',
    logger: { warn() {}, info() {} },
    spawn: recorder.spawn,
    ...overrides,
  })
  return { value, recorder }
}

/** Complete one recorded command with stdout, stderr and exit code. */
function finish(record, { stdout = '', stderr = '', code = 0 } = {}) {
  record.child.stdout.write(stdout)
  record.child.stdout.end()
  record.child.stderr.write(stderr)
  record.child.stderr.end()
  setImmediate(() => record.child.emit('close', code))
}

test('parseJsonOutput accepts one object and tolerates a log prefix', () => {
  assert.deepEqual(parseJsonOutput('{"ok":true}'), { ok: true })
  assert.deepEqual(parseJsonOutput('warning\n{"ok":false,"detail":"x"}\n'), { ok: false, detail: 'x' })
  assert.equal(parseJsonOutput('not json'), undefined)
})

test('adminEnvironment carries settings and the resolved key into the child only', () => {
  const env = adminEnvironment(VALUES, 'sk-test-secret', 'openai')
  assert.equal(env.CODERAG_SEMANTIC, 'on')
  assert.equal(env.CODERAG_SEMANTIC_BACKEND, 'openai')
  assert.equal(env.CODERAG_SEMANTIC_API_KEY, 'sk-test-secret')
  assert.equal(env.CODERAG_ROOT, 'F:\\workspace')
  assert.equal(env.PYTHONIOENCODING, 'utf-8')
})

test('state runs the admin CLI with the saved root and never returns the key', async () => {
  const { value, recorder } = service()
  const pending = value.state()
  await tick()
  finish(recorder.calls[0], { stdout: JSON.stringify({ index_exists: true, total_chunks: 7, config: { key_present: true } }) })
  const result = await pending
  assert.equal(recorder.calls[0].command, 'python-test')
  assert.deepEqual(recorder.calls[0].args.slice(0, 4), ['-m', 'dsh_coderag.admin', 'status', '--root'])
  assert.equal(recorder.calls[0].args[4], 'F:\\workspace')
  assert.equal(recorder.calls[0].options.env.CODERAG_SEMANTIC_API_KEY, 'sk-test-secret')
  assert.equal(result.ok, true)
  assert.equal(result.value.index_exists, true)
  assert.equal(result.value.total_chunks, 7)
  assert.equal(result.value.config.key_present, true)
  assert.equal(JSON.stringify(result).includes('sk-test-secret'), false)
})

test('state asks for a saved root instead of guessing one', async () => {
  const { value } = service({ readValues: () => ({ ...VALUES, root: '' }) })
  const result = await value.state()
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'root-unset')
})

test('admin failures are structured and scrub the resolved key', async () => {
  const { value, recorder } = service()
  const pending = value.state()
  await tick()
  finish(recorder.calls[0], { stderr: 'boom sk-test-secret leaked', code: 1 })
  const result = await pending
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'admin-failed')
  assert.equal(result.error.message.includes('sk-test-secret'), false)
  assert.match(result.error.message, /\[redacted\]/)
})

test('health overrides the backend and normalizes the probe result', async () => {
  const { value, recorder } = service()
  const pending = value.health('openai')
  await tick()
  const env = recorder.calls[0].options.env
  assert.equal(env.CODERAG_SEMANTIC, 'on')
  assert.equal(env.CODERAG_SEMANTIC_BACKEND, 'openai')
  finish(recorder.calls[0], {
    stdout: JSON.stringify({ ok: true, backend: 'openai', url: 'https://x', model: 'm', model_present: true, detail: '', models: [{ name: 'm' }] }),
  })
  const result = await pending
  assert.equal(result.ok, true)
  assert.equal(result.value.backend, 'openai')
  assert.deepEqual(result.value.models, ['m'])
})

test('vectorize reports streaming progress and a completed job', async () => {
  const { value, recorder } = service()
  const started = await value.vectorize()
  assert.equal(started.ok, true)
  assert.equal(started.value.status, 'running')
  const child = recorder.calls[0].child
  child.stdout.write('{"event":"start","total_chunks":10,"pending_chunks":6,"checkpoint_vectors":2}\n')
  child.stdout.write('{"event":"progress","embedded":4,"pending":2}\n')
  child.stdout.write('{"event":"done","chunks":4,"model":"m","generated_at":"2026-10-28T00:00:00Z"}\n')
  child.stdout.end()
  child.stderr.end()
  setImmediate(() => child.emit('close', 0))
  await new Promise(resolve => setImmediate(resolve))
  const job = value.job()
  assert.equal(job.status, 'done')
  assert.equal(job.total, 10)
  assert.equal(job.embedded, 4)
  assert.equal(job.pending, 0)
  assert.equal(job.model, 'm')
  assert.equal(JSON.stringify(job).includes('sk-test-secret'), false)
  assert.equal(recorder.calls[0].options.env.CODERAG_SEMANTIC_API_KEY, 'sk-test-secret')
})

test('a vectorize error event stays structured and scrubbed', async () => {
  const { value, recorder } = service()
  await value.vectorize()
  const child = recorder.calls[0].child
  child.stdout.write('{"event":"error","code":"EMBED_FAILED","message":"bad sk-test-secret"}\n')
  child.stdout.end()
  child.stderr.end()
  setImmediate(() => child.emit('close', 1))
  await new Promise(resolve => setImmediate(resolve))
  const job = value.job()
  assert.equal(job.status, 'error')
  assert.equal(job.error.code, 'EMBED_FAILED')
  assert.equal(job.error.message.includes('sk-test-secret'), false)
})

test('stop asks the child to terminate and keeps the checkpoint state', async () => {
  const { value, recorder } = service()
  await value.vectorize()
  const child = recorder.calls[0].child
  const stopped = value.stop()
  assert.equal(stopped.value.status, 'stopping')
  assert.equal(child.killed, true)
  child.stdout.end()
  child.stderr.end()
  setImmediate(() => child.emit('close', 0))
  await new Promise(resolve => setImmediate(resolve))
  const job = value.job()
  assert.equal(job.status, 'stopped')
  assert.equal(job.error, null)
})

test('start-local polls /api/tags until the server answers', async () => {
  const urls = []
  let attempts = 0
  const fetch = async url => {
    urls.push(url)
    attempts += 1
    if (attempts === 1) throw new Error('ECONNREFUSED')
    return { ok: true, json: async () => ({ models: [{ name: 'bge-m3' }] }) }
  }
  const { value, recorder } = service({ fetch, sleep: async () => {} })
  const result = await value.startLocal()
  assert.equal(result.ok, true)
  assert.equal(result.value.url, 'http://127.0.0.1:11434')
  assert.deepEqual(result.value.models, ['bge-m3'])
  assert.equal(recorder.calls[0].command, 'ollama')
  assert.deepEqual(recorder.calls[0].args, ['serve'])
  assert.ok(urls.every(url => url.endsWith('/api/tags')))
})

test('start-local reports a displayable error when the server never answers', async () => {
  let clock = 0
  const fetch = async () => { throw new Error('refused') }
  const { value, recorder } = service({
    fetch,
    now: () => clock,
    sleep: async ms => { clock += ms },
  })
  const result = await value.startLocal()
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'ollama-unreachable')
  assert.match(result.error.message, /15 秒/)
  assert.equal(recorder.calls[0].child.killed, true)
})
