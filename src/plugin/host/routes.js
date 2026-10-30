/**
 * Authenticated HTTP routes for the CodeRAG operations panel.
 *
 * The browser posts actions and reads state/job through these endpoints; every
 * handler runs behind the same connection trust fence as the rest of the Web
 * UI, so a page that cannot call the API also cannot start subprocesses.
 *
 * Responses are JSON envelopes: `{ ok: true, value }` or
 * `{ ok: false, error: { code, message } }`. No handler ever includes a
 * credential value; the admin service returns only whitelisted fields.
 *
 * Not responsible for the admin process model (admin.js) or rendering.
 */

import {
  ADMIN_ACTION_PATH,
  ADMIN_ACTIONS,
  ADMIN_JOB_PATH,
  ADMIN_STATE_PATH,
  HEALTH_BACKENDS,
  adminError,
} from '../shared/admin-protocol.js'

/** Request bodies are tiny JSON objects; anything larger is hostile. */
const MAX_BODY_BYTES = 64 * 1024

/** JSON response with live facts; never cached. */
export function sendJson(res, status, payload) {
  res.statusCode = status
  res.setHeader('content-type', 'application/json; charset=utf-8')
  res.setHeader('cache-control', 'no-store')
  res.end(JSON.stringify(payload))
}

/** 405 naming the route's one supported method. */
function methodNotAllowed(res, allow) {
  res.statusCode = 405
  res.setHeader('allow', allow)
  res.end()
}

/** Collect a bounded request body as UTF-8 text; null past the ceiling. */
export async function readBoundedBody(req) {
  const chunks = []
  let size = 0
  for await (const chunk of req) {
    size += chunk.byteLength
    if (size > MAX_BODY_BYTES) {
      req.resume()
      return null
    }
    chunks.push(chunk)
  }
  return Buffer.concat(chunks, size).toString('utf8')
}

/**
 * Validate one action body at the wire.
 * @param {string} text - request body.
 * @returns {{ action: string, backend?: string } | undefined} parsed action, or undefined.
 */
export function parseActionBody(text) {
  let body
  try {
    body = JSON.parse(text)
  } catch {
    return undefined
  }
  if (body === null || typeof body !== 'object') return undefined
  const { action, backend } = body
  if (typeof action !== 'string' || !ADMIN_ACTIONS.includes(action)) return undefined
  if (backend !== undefined && (typeof backend !== 'string' || !HEALTH_BACKENDS.includes(backend))) return undefined
  return backend === undefined ? { action } : { action, backend }
}

/**
 * Build the three request handlers around one admin service.
 * @param {object} admin - service created by `createAdminService`.
 * @param {{ syncNow?: () => Promise<unknown> }} [hooks] - extra work some actions need.
 * @returns {{ state: Function, action: Function, job: Function }} handlers.
 */
export function createAdminHttp(admin, hooks = {}) {
  return {
    async state(req, res) {
      if (req.method !== 'GET') {
        methodNotAllowed(res, 'GET')
        return
      }
      sendJson(res, 200, await admin.state())
    },

    async job(req, res) {
      if (req.method !== 'GET') {
        methodNotAllowed(res, 'GET')
        return
      }
      sendJson(res, 200, { ok: true, value: admin.job() })
    },

    async action(req, res) {
      if (req.method !== 'POST') {
        methodNotAllowed(res, 'POST')
        return
      }
      const essence = String(req.headers['content-type']).split(';', 1)[0]?.trim().toLowerCase()
      if (essence !== 'application/json') {
        sendJson(res, 415, { ok: false, error: adminError('unsupported-media-type', 'content-type must be application/json') })
        return
      }
      let text
      try {
        text = await readBoundedBody(req)
      } catch (error) {
        sendJson(res, 400, { ok: false, error: adminError('body-unreadable', String(error?.message ?? error)) })
        return
      }
      const parsed = text === null ? undefined : parseActionBody(text)
      if (parsed === undefined) {
        sendJson(res, 400, { ok: false, error: adminError('bad-action', '请求体必须是 {action} 且 action 在允许列表内') })
        return
      }
      try {
        switch (parsed.action) {
          case 'health':
            sendJson(res, 200, await admin.health(parsed.backend))
            return
          case 'start-local':
            sendJson(res, 200, await admin.startLocal())
            return
          case 'vectorize':
            sendJson(res, 200, await admin.vectorize())
            return
          case 'index':
            sendJson(res, 200, await admin.buildIndex())
            return
          case 'remove-vectors':
            sendJson(res, 200, await admin.removeVectors())
            return
          case 'stop':
            sendJson(res, 200, admin.stop())
            return
          case 'refresh':
            await hooks.syncNow?.()
            sendJson(res, 200, { ok: true, value: admin.job() })
            return
          default:
            sendJson(res, 400, { ok: false, error: adminError('bad-action', `unsupported action ${String(parsed.action)}`) })
        }
      } catch (error) {
        sendJson(res, 500, { ok: false, error: adminError('admin-internal', String(error?.message ?? error)) })
      }
    },
  }
}

/** Answer one untrusted request; true when it was rejected. */
function rejected(connection, req, res) {
  const rejection = connection.requestRejection(req)
  if (rejection === undefined) return false
  res.statusCode = rejection
  res.end()
  return true
}

/**
 * Register the routes once the Web server and connection services exist.
 * A headless composition has neither, so nothing is registered.
 * @param {import('@deepseek-ai/cordis').Context} ctx - the Host plugin context.
 * @param {{ admin: object, syncNow: () => Promise<unknown> }} deps - service and refresh hook.
 */
export function registerAdminRoutes(ctx, deps) {
  ctx.inject(['webServer', 'connection'], sctx => {
    const http = createAdminHttp(deps.admin, { syncNow: deps.syncNow })
    const connection = sctx.connection
    const routes = [
      { path: ADMIN_STATE_PATH, handler: http.state, label: 'GET' },
      { path: ADMIN_ACTION_PATH, handler: http.action, label: 'POST' },
      { path: ADMIN_JOB_PATH, handler: http.job, label: 'GET' },
    ]
    for (const route of routes) {
      sctx.effect(() => sctx.webServer.register({
        kind: 'exact',
        path: route.path,
        handler: (req, res) => {
          if (rejected(connection, req, res)) return
          return route.handler(req, res)
        },
      }), `coderag: ${route.label} ${route.path}`)
    }
  })
}
