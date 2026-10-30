#!/usr/bin/env node
/**
 * T5-03 probe: run the built host plugin against the Loader code shipped in
 * this machine's DSH build, with a stand-in MCP row, and prove the settings →
 * env → remount chain end to end.
 *
 * Prerequisite: `loader-volatile-probe.mjs --out .tmp-asar/probe-run --keep`
 * has extracted the live packages (the default `--live` path).
 *
 * Usage:
 *   node scripts/experiments/host-settings-sync-probe.mjs [--live <dir>]
 *
 * Checks:
 *   1. all thirteen Config fields are volatile in the schema JSON the Host
 *      settings service rehydrates;
 *   2. an all-empty settings row does not touch the MCP row at boot (legacy
 *      profile overrides survive);
 *   3. non-empty settings at boot are synced into the MCP env, preserving
 *      unrelated variables and `!!js` expression entries;
 *   4. a volatile-only settings save restarts the MCP row with the new env and
 *      removes variables whose settings were cleared;
 *   5. the row stays active when no `settings` service is composed.
 */
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const REPO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const args = process.argv.slice(2)
const liveIndex = args.indexOf('--live')
const liveDir = liveIndex >= 0 ? args[liveIndex + 1] : join(REPO_ROOT, '.tmp-asar', 'probe-run', 'node_modules')
if (!existsSync(liveDir)) throw new Error(`live packages not found at ${liveDir}; run loader-volatile-probe.mjs --out first`)
const packages = join(liveDir, '@deepseek-ai')
const importModule = specifier => import(pathToFileURL(specifier).href)
const { Context } = await importModule(join(packages, 'cordis', 'lib', 'index.js'))
const { default: Loader } = await importModule(join(packages, 'cordis-plugin-loader', 'lib', 'index.js'))
const z = (await importModule(join(packages, 'schemastery', 'lib', 'index.mjs'))).default
const host = await importModule(join(REPO_ROOT, 'lib', 'index.js'))

const results = []
const log = (...values) => console.log(...values)
function check(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  results.push({ label, ok, actual, expected })
  log(`${ok ? 'PASS' : 'FAIL'} ${label} actual=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`)
}
async function waitFor(predicate, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await predicate()) return true
    await new Promise(resolve => setTimeout(resolve, 25))
  }
  return false
}

const MCP_CONFIG = z.object({
  serverName: z.string().default('coderag'),
  transport: z.string().default('stdio'),
  command: z.string().default('python'),
  args: z.array(z.string()).default([]),
  cwd: z.string().default(''),
  env: z.dict(z.string()).default({}),
})

/** Mount one composition with a fake MCP row and return its observables. */
async function mount({ coderagConfig, mcpEnv }) {
  const ctx = new Context()
  await ctx.plugin(Loader)
  const applies = []
  ctx.loader.builtins.coderag = host
  ctx.loader.builtins['mcp-like'] = {
    Config: MCP_CONFIG,
    apply(_owner, config) {
      applies.push({ ...config.env })
    },
  }
  const mcpId = await ctx.loader.create({ id: 'mcp-coderag', name: 'cordis:mcp-like', config: { env: mcpEnv } })
  const settingsId = await ctx.loader.create({ id: 'coderag', name: 'cordis:coderag', config: coderagConfig })
  await ctx.loader.await()
  return { ctx, applies, settings: ctx.loader.resolve(settingsId), mcp: ctx.loader.resolve(mcpId) }
}

// --- 1. every editable field is volatile -----------------------------------
const schemaJson = host.Config.toJSON()
const rehydrated = new z(schemaJson)
const volatileFields = Object.entries(rehydrated.dict).filter(([, schema]) => schema.meta.volatile === true).map(([key]) => key)
check('all thirteen setting fields are volatile in the schema JSON', volatileFields.sort(), [
  'extraExtensions', 'maxFileBytes', 'maxFiles', 'maxTokens', 'root', 'semantic',
  'semanticAllowRemote', 'semanticBackend', 'semanticBatch', 'semanticMaxChunks',
  'semanticModel', 'semanticQueryTimeout', 'semanticUrl',
])
check('the settings namespace is the row id', host.inject, ['loader'])
check('the plugin exports the row name', host.name, 'dsh-coderag')

// --- 2. an all-empty settings row leaves legacy env alone ------------------
const empty = await mount({
  coderagConfig: {},
  mcpEnv: { CODERAG_ROOT: '/legacy', KEEP: '1' },
})
await new Promise(resolve => setTimeout(resolve, 300))
check('empty settings do not restart the MCP row', empty.applies.length, 1)
check('empty settings keep the legacy env', empty.applies[0], { CODERAG_ROOT: '/legacy', KEEP: '1' })
check('the settings row stays active without a settings service', empty.settings.fiber?.state, 2)
await empty.ctx.fiber.dispose()

// --- 3. boot settings are synced, unrelated env and expressions survive ----
const boot = await mount({
  coderagConfig: {
    root: '/ws-one', maxFiles: 100, maxFileBytes: 2048, maxTokens: 6000,
    extraExtensions: '.mxml,.as',
    semantic: true, semanticBackend: 'ollama', semanticUrl: 'http://127.0.0.1:11434',
    semanticModel: 'bge-m3', semanticQueryTimeout: 5, semanticBatch: 4,
    semanticMaxChunks: 30000, semanticAllowRemote: true,
  },
  mcpEnv: {
    KEEP: '1',
    CODERAG_SEMANTIC_API_KEY: { __jsExpr: "'from-env'" },
  },
})
check('boot settings restart the MCP row', await waitFor(() => boot.applies.length >= 2), true)
const bootEnv = boot.applies.at(-1)
check('boot settings export root', bootEnv.CODERAG_ROOT, '/ws-one')
check('boot settings export numeric fields as strings', [
  bootEnv.CODERAG_MAX_FILES, bootEnv.CODERAG_MAX_FILE_BYTES, bootEnv.CODERAG_MAX_TOKENS,
  bootEnv.CODERAG_SEMANTIC_QUERY_TIMEOUT, bootEnv.CODERAG_SEMANTIC_MAX_CHUNKS,
], ['100', '2048', '6000', '5', '30000'])
check('boot settings export the semantic switch as on', bootEnv.CODERAG_SEMANTIC, 'on')
check('boot settings export the remote opt-in as 1', bootEnv.CODERAG_SEMANTIC_ALLOW_REMOTE, '1')
check('unrelated env survives', bootEnv.KEEP, '1')
check('an unevaluated !!js env entry is resolved by the Loader and survives', bootEnv.CODERAG_SEMANTIC_API_KEY, 'from-env')
check('the MCP row keeps the expression in its raw config', boot.mcp.options.config.env.CODERAG_SEMANTIC_API_KEY, { __jsExpr: "'from-env'" })

// --- 4. a volatile-only save restarts the row and clears removed keys ------
await boot.settings.update({
  config: {
    ...boot.settings.options.config,
    root: '/ws-two', maxFiles: 0, maxFileBytes: 0, maxTokens: 0, extraExtensions: '',
    semantic: false, semanticBackend: '', semanticUrl: '', semanticModel: '',
    semanticQueryTimeout: 0, semanticBatch: 0, semanticMaxChunks: 0, semanticAllowRemote: false,
  },
})
const restarted = await waitFor(() => {
  const env = boot.applies.at(-1)
  return boot.applies.length >= 3 && env.CODERAG_ROOT === '/ws-two'
})
check('a volatile-only save restarts the MCP row', restarted, true)
const savedEnv = boot.applies.at(-1)
check('the save removes settings that were cleared', [
  savedEnv.CODERAG_MAX_FILES, savedEnv.CODERAG_MAX_TOKENS, savedEnv.CODERAG_SEMANTIC,
  savedEnv.CODERAG_SEMANTIC_QUERY_TIMEOUT, savedEnv.CODERAG_SEMANTIC_MAX_CHUNKS,
  savedEnv.CODERAG_SEMANTIC_ALLOW_REMOTE, savedEnv.CODERAG_EXTRA_EXTENSIONS,
], [undefined, undefined, undefined, undefined, undefined, undefined, undefined])
check('the save keeps unrelated env', savedEnv.KEEP, '1')
check('the save keeps the !!js expression entry', savedEnv.CODERAG_SEMANTIC_API_KEY, 'from-env')
check('the volatile-only save did not remount the settings row', boot.settings.fiber?.state, 2)
await boot.ctx.fiber.dispose()

const failed = results.filter(result => !result.ok)
log(`\nSUMMARY: ${results.length - failed.length}/${results.length} checks passed`)
if (failed.length > 0) {
  log(JSON.stringify(failed, null, 2))
  process.exitCode = 1
}
