/**
 * Behavior tests for the browser-side admin helpers: envelope handling, job
 * projection, progress arithmetic, and the credential reference.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  fetchAdminJob,
  formatCount,
  formatGeneratedAt,
  jobActive,
  jobLabel,
  jobPercent,
  normalizeJob,
  runAdminAction,
} from '../../src/plugin/shared/admin-client.js'
import { SEMANTIC_KEY_REF } from '../../src/plugin/shared/admin-protocol.js'

/** Run `body` with a stubbed global fetch, restoring it afterwards. */
async function withFetch(handler, body) {
  const original = globalThis.fetch
  globalThis.fetch = handler
  try {
    return await body()
  } finally {
    globalThis.fetch = original
  }
}

test('the credential reference is the documented environment name', () => {
  assert.equal(SEMANTIC_KEY_REF, 'CODERAG_SEMANTIC_API_KEY')
})

test('adminRequest unwraps ok envelopes and surfaces Host messages', async () => {
  await withFetch(async () => new Response(JSON.stringify({ ok: true, value: { status: 'idle' } }), { status: 200 }), async () => {
    const value = await fetchAdminJob()
    assert.deepEqual(value, { status: 'idle' })
  })
  await withFetch(async () => new Response(JSON.stringify({ ok: false, error: { code: 'root-unset', message: '请先保存根目录' } }), { status: 200 }), async () => {
    await assert.rejects(() => fetchAdminJob(), /请先保存根目录/)
  })
  await withFetch(async () => new Response('<html>', { status: 502 }), async () => {
    await assert.rejects(() => fetchAdminJob(), /非 JSON/)
  })
})

test('runAdminAction posts the action and optional backend as JSON', async () => {
  let captured
  await withFetch(async (url, init) => {
    captured = { url, init }
    return new Response(JSON.stringify({ ok: true, value: { ok: true, backend: 'openai' } }), { status: 200 })
  }, async () => {
    const value = await runAdminAction('health', { backend: 'openai' })
    assert.equal(value.backend, 'openai')
  })
  assert.equal(captured.url, '/coderag-admin/action')
  assert.equal(captured.init.method, 'POST')
  assert.equal(captured.init.credentials, 'same-origin')
  assert.deepEqual(JSON.parse(captured.init.body), { action: 'health', backend: 'openai' })
})

test('normalizeJob keeps the documented fields and drops unknown ones', () => {
  const job = normalizeJob({
    status: 'running', total: 10, embedded: 3, pending: 7, model: 'm',
    generatedAt: '2026-10-28T00:00:00Z', startedAt: 1, finishedAt: null,
    error: { code: 'X', message: 'boom' }, secret: 'sk-hidden',
  })
  assert.equal(job.status, 'running')
  assert.equal(job.total, 10)
  assert.equal(job.embedded, 3)
  assert.equal(job.pending, 7)
  assert.deepEqual(job.error, { code: 'X', message: 'boom' })
  assert.equal('secret' in job, false)
  assert.equal(normalizeJob(undefined).status, 'idle')
})

test('progress and labels follow the job lifecycle', () => {
  const running = normalizeJob({ status: 'running', total: 10, pending: 4 })
  assert.equal(jobPercent(running), 60)
  assert.equal(jobActive(running), true)
  assert.equal(jobLabel('running'), '向量化进行中')
  assert.equal(jobLabel('stopped'), '已停止（检查点保留）')
  assert.equal(jobActive(normalizeJob({ status: 'done' })), false)
  assert.equal(jobPercent(normalizeJob({ status: 'idle' })), null)
  assert.equal(jobPercent(normalizeJob({ status: 'running', total: 0 })), null)
})

test('counts and timestamps format for the status grid', () => {
  assert.equal(formatCount(12345), '12,345')
  assert.equal(formatCount(null), '—')
  assert.equal(formatGeneratedAt('2026-10-28T12:34:56.000Z'), '2026-10-28 12:34:56')
  assert.equal(formatGeneratedAt(null), '—')
})
