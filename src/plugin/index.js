/**
 * Host half of the dsh-coderag settings page.
 *
 * Owns the `coderag` Loader row's editable Config (every field is a schemastery
 * volatile reference, which is what makes the row configurable in the native
 * Plugins page without a remount) and keeps the existing `mcp-coderag` row's
 * `config.env` in sync with it.
 *
 * The MCP row is the only component that can start the Python engine, so a
 * settings change becomes effective by updating that row: `env` is an ordinary
 * (non-volatile) field of `@deepseek-ai/dsh-mcp-client`, so the Loader remounts
 * the row and DSH restarts the stdio child with the new environment.
 *
 * Not responsible for: the Python engine, index storage, or the browser form.
 * See docs/settings-ui-plan.md for the measured Loader contract.
 */

import z from '@deepseek-ai/schemastery'
import {
  DEFAULT_VALUES,
  MCP_ROW_ID,
  isEmptySettings,
  validateValues,
  valuesFromConfig,
} from './shared/settings.js'
import { findMCPEntry, syncMCPRow } from './sync.js'
import { createAdminService } from './host/admin.js'
import { resolveCredential } from './host/credentials.js'
import { registerAdminRoutes } from './host/routes.js'

/** Loader row id and browser plugin id must stay the package name. */
export const name = 'dsh-coderag'
/** The MCP row is looked up through the Loader service. */
export const inject = ['loader']

/**
 * Editable settings. Every field must be `.volatile()`:
 * the settings service only exposes entries whose schema has volatile fields,
 * and only volatile-only edits are committed without a remount.
 */
export const Config = z.object({
  root: z.string().default(DEFAULT_VALUES.root).description('Workspace root the engine indexes.').volatile(),
  maxFiles: z.natural().default(DEFAULT_VALUES.maxFiles).description('File cap; 0 uses the engine default.').volatile(),
  maxFileBytes: z.natural().default(DEFAULT_VALUES.maxFileBytes).description('Per-file byte cap; 0 uses the engine default.').volatile(),
  maxTokens: z.natural().default(DEFAULT_VALUES.maxTokens).description('Search token budget; 0 uses the engine default (4000).').volatile(),
  extraExtensions: z.string().default(DEFAULT_VALUES.extraExtensions).description('Extra extensions, comma or space separated.').volatile(),
  semantic: z.boolean().default(DEFAULT_VALUES.semantic).description('Enable the optional semantic backend.').volatile(),
  semanticBackend: z.union([z.const(''), z.const('ollama'), z.const('openai')])
    .default(DEFAULT_VALUES.semanticBackend)
    .description('Embedding backend; empty uses the engine default (ollama).')
    .volatile(),
  semanticUrl: z.string().default(DEFAULT_VALUES.semanticUrl).description('Embedding service URL.').volatile(),
  semanticModel: z.string().default(DEFAULT_VALUES.semanticModel).description('Embedding model name.').volatile(),
  semanticQueryTimeout: z.natural().default(DEFAULT_VALUES.semanticQueryTimeout).description('Query wall-clock budget in seconds; 0 uses the default (10).').volatile(),
  semanticBatch: z.natural().default(DEFAULT_VALUES.semanticBatch).description('Embedding batch size; 0 uses the default.').volatile(),
  semanticMaxChunks: z.natural().default(DEFAULT_VALUES.semanticMaxChunks).description('Embedding chunk cap; 0 uses the engine default.').volatile(),
  semanticAllowRemote: z.boolean().default(DEFAULT_VALUES.semanticAllowRemote)
    .description('Allow a non-loopback cloud embedding URL (second opt-in).')
    .volatile(),
})

/** How long a boot-time sync waits for the MCP row to finish its first start. */
const INITIAL_SYNC_ATTEMPTS = 40
/** Delay between boot-time sync attempts, in milliseconds. */
const INITIAL_SYNC_INTERVAL_MS = 100

/**
 * Serialize every sync through one chain so two quick saves cannot interleave
 * two MCP row updates. Each run resolves the cloud key from the credentials
 * service, because a key write is a separate Host event (the browser calls the
 * `refresh` action) and is never part of the volatile Config.
 * @param {import('@deepseek-ai/cordis').Context} ctx - Host plugin context.
 * @param {() => Record<string, unknown>} read - current normalized settings.
 * @returns {{ run: () => Promise<string> }} the serialized runner.
 */
function createSyncQueue(ctx, read) {
  let tail = Promise.resolve()
  const run = () => {
    tail = tail.then(async () => {
      const loader = ctx.get('loader')
      const entry = findMCPEntry(loader)
      if (entry === undefined) return 'missing'
      // Three credential states: configured (set), provider answered "unset"
      // (clear the stale row key), provider unavailable (leave it alone).
      const credential = await resolveCredential(ctx)
      const apiKey = credential.available ? credential.value : undefined
      const clearKey = credential.available && credential.value === undefined
      const outcome = await syncMCPRow(entry, read(), { apiKey, clearKey })
      if (outcome !== 'unchanged') {
        ctx.logger?.info('coderag: settings synced to the mcp-coderag row (%s)', outcome)
      }
      return outcome
    }).catch(error => {
      ctx.logger?.warn('coderag: failed to sync the mcp-coderag row')
      ctx.logger?.warn(error)
      return 'failed'
    })
    return tail
  }
  return { run }
}

/** Resolve the interpreter the MCP row actually runs, when it is mounted. */
function interpreterOf(ctx) {
  const entry = findMCPEntry(ctx.get('loader'))
  const command = entry?.fiber?.config?.command
  return typeof command === 'string' && command.trim() !== '' ? command.trim() : undefined
}

/**
 * Apply the host half.
 * @param {import('@deepseek-ai/cordis').Context} ctx - the entry's context.
 * @param {ReturnType<typeof Config>} config - parsed volatile Config.
 */
export function apply(ctx, config) {
  const read = () => valuesFromConfig(config)
  const queue = createSyncQueue(ctx, read)

  // The operations panel: Python admin CLI + one in-memory job. Routes are
  // registered only when the Web composition provides both services, and every
  // request passes the same trust fence as the rest of the Web UI.
  const admin = createAdminService({
    readValues: read,
    resolveKey: () => resolveCredential(ctx),
    python: () => interpreterOf(ctx),
    logger: ctx.logger,
  })
  // HMR/unload must not leave a vectorize child (or its private cwd) behind.
  ctx.effect(() => () => admin.dispose(), 'coderag: dispose admin service')
  registerAdminRoutes(ctx, { admin, syncNow: () => queue.run() })

  // A saved settings row arrives as a volatile-only commit: no remount, and the
  // owning fiber (us) is told exactly which paths changed.
  ctx.on('loader/volatile-update', () => {
    void queue.run()
  })

  // A row enabled after boot (or a late import) still gets the current values.
  ctx.on('loader/entry-init', entry => {
    if (entry?.options?.id !== MCP_ROW_ID) return
    queueMicrotask(() => {
      void queue.run()
    })
  })

  // Boot path: the MCP row may still be importing when this plugin applies, so
  // wait for it in the background instead of blocking the Loader.
  const initial = read()
  if (!isEmptySettings(initial)) {
    ctx.effect(() => {
      let attempts = 0
      let timer
      let disposed = false
      const tick = async () => {
        if (disposed) return
        try {
          const entry = findMCPEntry(ctx.get('loader'))
          if (entry !== undefined) {
            if (entry.fiber !== undefined) await entry.fiber.await()
            const outcome = await queue.run()
            if (outcome !== 'missing') return
          }
        } catch (error) {
          // A row that failed to mount must not turn into an unhandled
          // rejection; report once and stop retrying.
          ctx.logger?.warn('coderag: initial settings sync stopped after an error')
          ctx.logger?.warn(error)
          return
        }
        attempts += 1
        if (attempts >= INITIAL_SYNC_ATTEMPTS) {
          ctx.logger?.warn('coderag: mcp-coderag row was not found; settings cannot reach the engine')
          return
        }
        timer = setTimeout(() => {
          void tick()
        }, INITIAL_SYNC_INTERVAL_MS)
      }
      timer = setTimeout(() => {
        void tick()
      }, 0)
      return () => {
        disposed = true
        clearTimeout(timer)
      }
    }, 'coderag: initial settings sync')
  }

  // The generated schema form in Settings would duplicate this plugin's own row
  // page; keep a single editor. `settings` is optional so headless compositions
  // without a settings service still mount this plugin.
  ctx.inject(['settings'], sctx => sctx.effect(
    () => sctx.settings.configure({ auto: false }, ctx.fiber),
    'coderag: own the settings page',
  ))

  // Schema-level validation is the Host's first gate; this cross-field gate
  // covers cloud combinations the flat schema cannot express.
  ctx.effect(() => {
    if (!validateValues(read()).length) return
    ctx.logger?.warn('coderag: current settings would be rejected by the browser form (cloud backend needs URL and model)')
  }, 'coderag: cross-field settings check')
}
