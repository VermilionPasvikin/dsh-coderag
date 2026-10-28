/**
 * Behavior tests for the authenticated admin routes: method/content-type
 * guards, action dispatch, refresh hook, and the connection trust fence.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  createAdminHttp,
  parseActionBody,
  registerAdminRoutes,
} from '../../src/plugin/host/routes.js'

/** Fake admin service; each method records its calls. */
function fakeAdmin() {
  const calls = []
  return {
    calls,
    state: async () => { calls.push(['state']); return { ok: true, value: { index_exists: true } } },
    job: () => { calls.push(['job']); return { status: 'idle', embedded: 0 } },
    health: async backend => { calls.push(['health', backend]); return { ok: true, value: { ok: true, backend } } },
    startLocal: async () => { calls.push(['start-local']); return { ok: true, value: { url: 'http://127.0.0.1:11434' } } },
    vectorize: async () => { calls.push(['vectorize']); return { ok: true, value: { status: 'running' } } },
    stop: () => { calls.push(['stop']); return { ok: true, value: { status: 'stopped' } } },
  }
}

/** Minimal request; `body` is streamed once when present. */
function request({ method = 'GET', headers = {}, body = undefined } = {}) {
  return {
    method,
    headers,
    resume() {},
    async *[Symbol.asyncIterator]() {
      if (body !== undefined) yield Buffer.from(body)
    },
  }
}

/** Minimal response capturing status, headers and body. */
function response() {
  return {
    statusCode: 0,
    headers: {},
    body: '',
    setHeader(name, value) { this.headers[name] = value },
    end(value = '') { this.body = String(value) },
  }
}

const jsonBody = value => ({ headers: { 'content-type': 'application/json' }, body: JSON.stringify(value) })

test('parseActionBody accepts the allowed actions and optional backend', () => {
  assert.deepEqual(parseActionBody('{"action":"health","backend":"ollama"}'), { action: 'health', backend: 'ollama' })
  assert.deepEqual(parseActionBody('{"action":"stop"}'), { action: 'stop' })
  assert.equal(parseActionBody('{"action":"delete-everything"}'), undefined)
  assert.equal(parseActionBody('{"action":"health","backend":"local"}'), undefined)
  assert.equal(parseActionBody('not json'), undefined)
})

test('state and job answer GET and refuse other methods', async () => {
  const admin = fakeAdmin()
  const http = createAdminHttp(admin)
  const state = response()
  await http.state(request(), state)
  assert.equal(state.statusCode, 200)
  assert.equal(JSON.parse(state.body).value.index_exists, true)
  assert.equal(state.headers['cache-control'], 'no-store')

  const wrong = response()
  await http.state(request({ method: 'POST' }), wrong)
  assert.equal(wrong.statusCode, 405)
  assert.equal(wrong.headers.allow, 'GET')

  const job = response()
  await http.job(request(), job)
  assert.equal(JSON.parse(job.body).value.status, 'idle')
})

test('action dispatch covers health, start-local, vectorize, stop and refresh', async () => {
  const admin = fakeAdmin()
  let synced = 0
  const http = createAdminHttp(admin, { syncNow: async () => { synced += 1 } })
  for (const [body, expected] of [
    [{ action: 'health', backend: 'openai' }, ['health', 'openai']],
    [{ action: 'start-local' }, ['start-local']],
    [{ action: 'vectorize' }, ['vectorize']],
    [{ action: 'stop' }, ['stop']],
  ]) {
    const res = response()
    await http.action(request({ method: 'POST', ...jsonBody(body) }), res)
    assert.equal(res.statusCode, 200)
    assert.deepEqual(admin.calls.at(-1), expected)
  }
  const refresh = response()
  await http.action(request({ method: 'POST', ...jsonBody({ action: 'refresh' }) }), refresh)
  assert.equal(refresh.statusCode, 200)
  assert.equal(synced, 1)
})

test('action refuses a wrong media type or an unknown action', async () => {
  const http = createAdminHttp(fakeAdmin())
  const media = response()
  await http.action(request({ method: 'POST', headers: { 'content-type': 'text/plain' }, body: '{}' }), media)
  assert.equal(media.statusCode, 415)

  const bad = response()
  await http.action(request({ method: 'POST', ...jsonBody({ action: 'drop-tables' }) }), bad)
  assert.equal(bad.statusCode, 400)
  assert.equal(JSON.parse(bad.body).error.code, 'bad-action')
})

test('routes register behind the connection trust fence', async () => {
  const admin = fakeAdmin()
  const handlers = []
  const fakeCtx = {
    inject: (deps, callback) => {
      assert.deepEqual(deps, ['webServer', 'connection'])
      callback({
        effect: effect => effect(),
        webServer: {
          register: route => {
            handlers.push(route)
            return () => {}
          },
        },
        connection: { requestRejection: () => 401 },
      })
    },
    effect: callback => callback(),
  }
  registerAdminRoutes(fakeCtx, { admin, syncNow: async () => {} })
  assert.deepEqual(handlers.map(route => route.path).sort(), [
    '/coderag-admin/action', '/coderag-admin/job', '/coderag-admin/state',
  ])
  const res = response()
  await handlers[0].handler(request(), res)
  assert.equal(res.statusCode, 401)
  assert.deepEqual(admin.calls, [])
})

test('routes serve when the fence admits the request', async () => {
  const admin = fakeAdmin()
  const handlers = []
  const fakeCtx = {
    inject: (_deps, callback) => callback({
      effect: effect => effect(),
      webServer: { register: route => { handlers.push(route); return () => {} } },
      connection: { requestRejection: () => undefined },
    }),
    effect: callback => callback(),
  }
  registerAdminRoutes(fakeCtx, { admin, syncNow: async () => {} })
  const state = handlers.find(route => route.path.endsWith('/state'))
  const res = response()
  await state.handler(request(), res)
  assert.equal(res.statusCode, 200)
  assert.equal(JSON.parse(res.body).ok, true)
})
