/**
 * Behavior tests for the Host admin service: launcher/cwd hardening, private
 * child cwd, key marker vs key env, streaming jobs, stop/dispose, local Ollama
 * startup, and the credential states that decide whether a row key is kept.
 */

import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { tmpdir } from 'node:os'
import { PassThrough } from 'node:stream'
import { test } from 'node:test'
import {
  ADMIN_LAUNCHER,
  adminEnvironment,
  createAdminService,
  parseJsonOutput,
} from '../../src/plugin/host/admin.js'
import { SEMANTIC_KEY_PRESENT_ENV } from '../../src/plugin/shared/admin-protocol.js'

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
  semanticQueryTimeout: 0,
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
    resolveKey: async () => ({ available: true, value: 'sk-test-secret' }),
    python: () => 'python-test',
    logger: { warn() {}, info() {} },
    spawn: recorder.spawn,
    privateDir: 'F:\\private-admin-cwd',
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

test('adminEnvironment separates the key from the status marker', () => {
  const withKey = adminEnvironment(VALUES, { apiKey: 'sk-test-secret', backend: 'openai', forceSemantic: true })
  assert.equal(withKey.CODERAG_SEMANTIC, 'on')
  assert.equal(withKey.CODERAG_SEMANTIC_BACKEND, 'openai')
  assert.equal(withKey.CODERAG_SEMANTIC_API_KEY, 'sk-test-secret')
  assert.equal(withKey[SEMANTIC_KEY_PRESENT_ENV], '1')
  assert.equal(withKey.CODERAG_ROOT, 'F:\\workspace')
  assert.equal(withKey.PYTHONIOENCODING, 'utf-8')

  const status = adminEnvironment(VALUES, { keyPresent: true })
  assert.equal(status.CODERAG_SEMANTIC_API_KEY, undefined, 'status must never receive the key')
  assert.equal(status[SEMANTIC_KEY_PRESENT_ENV], '1')

  const absent = adminEnvironment(VALUES, { keyPresent: false })
  assert.equal(absent.CODERAG_SEMANTIC_API_KEY, undefined)
  assert.equal(absent[SEMANTIC_KEY_PRESENT_ENV], undefined)
})

test('status observes the saved switch instead of forcing it on', () => {
  const saved = process.env.CODERAG_SEMANTIC
  delete process.env.CODERAG_SEMANTIC
  try {
    const env = adminEnvironment({ ...VALUES, semantic: false })
    assert.equal(env.CODERAG_SEMANTIC, undefined)
  } finally {
    if (saved !== undefined) process.env.CODERAG_SEMANTIC = saved
  }
})

test('state runs the -c launcher with the private cwd and no key', async () => {
  const { value, recorder } = service()
  const pending = value.state()
  await tick()
  finish(recorder.calls[0], { stdout: JSON.stringify({ index_exists: true, total_chunks: 7, config: { key_present: true } }) })
  const result = await pending
  const call = recorder.calls[0]
  assert.equal(call.command, 'python-test')
  assert.deepEqual(call.args.slice(0, 4), ['-c', ADMIN_LAUNCHER, 'status', '--root'])
  assert.equal(call.args[4], 'F:\\workspace')
  assert.equal(call.options.cwd, 'F:\\private-admin-cwd')
  assert.notEqual(call.options.cwd, tmpdir())
  assert.equal(call.options.env.CODERAG_SEMANTIC_API_KEY, undefined)
  assert.equal(call.options.env[SEMANTIC_KEY_PRESENT_ENV], '1')
  assert.equal(result.ok, true)
  assert.equal(result.value.index_exists, true)
  assert.equal(result.value.total_chunks, 7)
  assert.equal(result.value.config.key_present, true)
  assert.equal(JSON.stringify(result).includes('sk-test-secret'), false)
})

test('state marks an explicitly unconfigured key without injecting one', async () => {
  const { value, recorder } = service({ resolveKey: async () => ({ available: true }) })
  const pending = value.state()
  await tick()
  finish(recorder.calls[0], { stdout: JSON.stringify({ index_exists: true }) })
  await pending
  assert.equal(recorder.calls[0].options.env.SEMANTIC_KEY_PRESENT_ENV, undefined)
  assert.equal(recorder.calls[0].options.env.CODERAG_SEMANTIC_API_KEY, undefined)
})

test('state asks for a saved root instead of guessing one', async () => {
  const { value } = service({ readValues: () => ({ ...VALUES, root: '' }) })
  const result = await value.state()
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'root-unset')
})

test('a relative root is resolved once in the Host', async () => {
  const { value, recorder } = service({ readValues: () => ({ ...VALUES, root: 'relative\\ws' }) })
  const pending = value.state()
  await tick()
  finish(recorder.calls[0], { stdout: JSON.stringify({ index_exists: true }) })
  await pending
  assert.equal(recorder.calls[0].args[4].startsWith('F:\\') || recorder.calls[0].args[4].includes(':'), true)
  assert.equal(recorder.calls[0].args[4].includes('relative\\ws'), true)
})

test('health failures are structured and scrub the resolved key', async () => {
  const { value, recorder } = service()
  const pending = value.health('ollama')
  await tick()
  finish(recorder.calls[0], { stderr: 'boom sk-test-secret leaked', code: 1 })
  const result = await pending
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'admin-failed')
  assert.equal(result.error.message.includes('sk-test-secret'), false)
  assert.match(result.error.message, /\[redacted\]/)
})

test('a non-zero exit preserves the CLI structured error', async () => {
  const { value, recorder } = service()
  const pending = value.state()
  await tick()
  finish(recorder.calls[0], {
    stdout: JSON.stringify({ ok: false, code: 'CONFIG_INVALID', message: '缺少 CODERAG_ROOT' }),
    code: 1,
  })
  const result = await pending
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'CONFIG_INVALID')
  assert.match(result.error.message, /CODERAG_ROOT/)
})

test('health overrides the backend and keeps the structured code', async () => {
  const { value, recorder } = service()
  const pending = value.health('openai')
  await tick()
  const env = recorder.calls[0].options.env
  assert.equal(env.CODERAG_SEMANTIC, 'on')
  assert.equal(env.CODERAG_SEMANTIC_BACKEND, 'openai')
  assert.equal(env.CODERAG_SEMANTIC_API_KEY, 'sk-test-secret')
  finish(recorder.calls[0], {
    stdout: JSON.stringify({
      ok: false, backend: 'openai', url: 'https://x', model: 'm', model_present: false,
      detail: 'missing model', code: 'MODEL_MISSING', models: [],
    }),
  })
  const result = await pending
  assert.equal(result.ok, true)
  assert.equal(result.value.backend, 'openai')
  assert.equal(result.value.code, 'MODEL_MISSING')
  assert.equal(result.value.model_present, false)
})

test('vectorize reports streaming progress and a completed job', async () => {
  const { value, recorder } = service()
  const started = await value.vectorize()
  assert.equal(started.ok, true)
  assert.equal(started.value.status, 'running')
  assert.equal(recorder.calls[0].args[0], '-c')
  assert.equal(recorder.calls[0].args[2], 'vectorize')
  assert.equal(recorder.calls[0].options.cwd, 'F:\\private-admin-cwd')
  const child = recorder.calls[0].child
  child.stdout.write('{"event":"start","total_chunks":10,"pending_chunks":6,"checkpoint_vectors":2}\n')
  child.stdout.write('{"event":"progress","embedded":4,"pending":2}\n')
  child.stdout.write('{"event":"done","chunks":4,"model":"m","generated_at":"2026-10-28T00:00:00Z"}\n')
  child.stdout.end()
  child.stderr.end()
  setImmediate(() => child.emit('close', 0))
  await tick()
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
  await tick()
  const job = value.job()
  assert.equal(job.status, 'error')
  assert.equal(job.error.code, 'EMBED_FAILED')
  assert.equal(job.error.message.includes('sk-test-secret'), false)
})

test('concurrent vectorize calls cannot both pass the pre-spawn window', async () => {
  let release
  const gate = new Promise(resolve => { release = resolve })
  const { value, recorder } = service({
    resolveKey: async () => {
      await gate
      return { available: true, value: 'sk-test-secret' }
    },
  })
  const first = value.vectorize()
  const second = await value.vectorize()
  assert.equal(second.ok, false)
  assert.equal(second.error.code, 'job-running')
  release()
  const started = await first
  assert.equal(started.ok, true)
  assert.equal(recorder.calls.length, 1)
  value.dispose()
})

test('late exits from a stopped job cannot clobber the next job', async () => {
  const { value, recorder } = service()
  await value.vectorize()
  const first = recorder.calls[0].child
  assert.equal((await value.vectorize()).ok, false, 'a second job is refused while the first handle lives')
  value.stop()
  first.emit('close', 0)
  await tick()
  assert.equal(value.job().status, 'stopped')

  const second = await value.vectorize()
  assert.equal(second.ok, true)
  assert.equal(recorder.calls.length, 2)
  const current = recorder.calls[1].child
  // The old child reports a late error/close after the new job is active.
  first.emit('error', new Error('late stop noise'))
  first.emit('close', 1)
  await tick()
  assert.equal(value.job().status, 'running')
  assert.equal(value.job().error, null)

  value.stop()
  assert.equal(current.killed, true)
  current.stdout.write('{"event":"done","chunks":1,"model":"m","generated_at":"x"}\n')
  current.stdout.end()
  current.stderr.end()
  current.emit('close', 0)
  await tick()
  assert.equal(value.job().status, 'done')
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
  await tick()
  const job = value.job()
  assert.equal(job.status, 'stopped')
  assert.equal(job.error, null)
})

test('dispose kills the active child and clears the private cwd', async () => {
  const { value, recorder } = service()
  await value.vectorize()
  const child = recorder.calls[0].child
  value.dispose()
  assert.equal(child.killed, true)
  assert.equal(value.privateDirectory(), undefined)
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

test('a non-loopback configured URL is ignored by start-local', async () => {
  const urls = []
  const fetch = async url => {
    urls.push(url)
    return { ok: true, json: async () => ({ models: [] }) }
  }
  const { value } = service({
    fetch,
    sleep: async () => {},
    readValues: () => ({ ...VALUES, semanticUrl: 'https://api.example.com/v1' }),
  })
  const result = await value.startLocal()
  assert.equal(result.ok, true)
  assert.equal(result.value.url, 'http://127.0.0.1:11434')
  assert.ok(urls.every(url => url.startsWith('http://127.0.0.1:11434/')))
})

test('start-local fails fast when ollama is missing', async () => {
  let polls = 0
  const fetch = async () => { polls += 1; throw new Error('refused') }
  const recorder = spawnRecorder()
  const spawn = (command, args, options) => {
    const child = recorder.spawn(command, args, options)
    setImmediate(() => {
      const error = new Error('spawn ollama ENOENT')
      error.code = 'ENOENT'
      child.emit('error', error)
    })
    return child
  }
  const { value } = service({ fetch, sleep: () => new Promise(resolve => setImmediate(resolve)), spawn })
  const result = await value.startLocal()
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'ollama-missing')
  assert.ok(polls <= 1, `the ENOENT path must not keep polling (ran ${polls} times)`)
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
