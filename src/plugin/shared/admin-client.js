/**
 * Browser-side helpers for the CodeRAG operations panel.
 *
 * Plain functions only: the React panels and the Node tests share them, so the
 * route vocabulary, the job projection, and the user-facing formatting cannot
 * drift from the Host.
 */

import {
  ADMIN_ACTION_PATH,
  ADMIN_JOB_PATH,
  ADMIN_STATE_PATH,
  emptyJob,
} from './admin-protocol.js'

/**
 * Call one admin route and unwrap the `{ok, value}` envelope.
 * @param {string} path - route path.
 * @param {RequestInit} [init] - fetch options.
 * @returns {Promise<unknown>} the unwrapped value.
 */
export async function adminRequest(path, init = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...init,
  })
  let body
  try {
    body = await response.json()
  } catch {
    throw new Error(`运维接口返回了非 JSON 响应（HTTP ${String(response.status)}）`)
  }
  if (response.ok && body?.ok === true) return body.value
  const message = typeof body?.error?.message === 'string'
    ? body.error.message
    : `运维接口失败（HTTP ${String(response.status)}）`
  throw new Error(message)
}

/** Read the vector index status for the saved root. */
export function fetchAdminState() {
  return adminRequest(ADMIN_STATE_PATH)
}

/** Read the in-memory vectorize job. */
export function fetchAdminJob() {
  return adminRequest(ADMIN_JOB_PATH)
}

/**
 * Run one admin action.
 * @param {string} action - one of the protocol's actions.
 * @param {Record<string, unknown>} [extra] - e.g. `{ backend: 'ollama' }`.
 * @returns {Promise<unknown>} the action's value.
 */
export function runAdminAction(action, extra = {}) {
  return adminRequest(ADMIN_ACTION_PATH, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action, ...extra }),
  })
}

/** Coerce an unknown job payload into the documented snapshot. */
export function normalizeJob(raw) {
  const source = raw !== null && typeof raw === 'object' ? raw : {}
  const base = emptyJob()
  const numeric = value => (typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : null)
  return {
    ...base,
    status: typeof source.status === 'string' ? source.status : base.status,
    total: numeric(source.total),
    embedded: numeric(source.embedded) ?? 0,
    pending: numeric(source.pending),
    model: typeof source.model === 'string' ? source.model : null,
    generatedAt: typeof source.generatedAt === 'string' ? source.generatedAt : null,
    startedAt: numeric(source.startedAt),
    finishedAt: numeric(source.finishedAt),
    error: source.error !== null && typeof source.error === 'object' && typeof source.error.message === 'string'
      ? { code: String(source.error.code ?? 'unknown'), message: source.error.message }
      : null,
  }
}

/** Format a count for display; null/missing shows an em dash. */
export function formatCount(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-US') : '—'
}

/** Human label for a job state. */
export function jobLabel(status) {
  switch (status) {
    case 'running': return '向量化进行中'
    case 'stopping': return '正在停止…'
    case 'stopped': return '已停止（检查点保留）'
    case 'done': return '向量化完成'
    case 'error': return '向量化失败'
    default: return '空闲'
  }
}

/**
 * Progress percentage for the bar; null when no total is known yet.
 * @param {object} job - normalized job.
 * @returns {number | null} 0–100, or null.
 */
export function jobPercent(job) {
  const total = job.total
  if (typeof total !== 'number' || total <= 0) return null
  const done = total - (typeof job.pending === 'number' ? job.pending : Math.max(0, total - job.embedded))
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)))
}

/** Whether a job still needs polling. */
export function jobActive(job) {
  return job.status === 'running' || job.status === 'stopping'
}

/** Shorten a timestamp for a status line. */
export function formatGeneratedAt(value) {
  if (typeof value !== 'string' || value === '') return '—'
  return value.replace('T', ' ').replace(/\.\d+Z?$/, '').replace(/Z$/, '')
}
