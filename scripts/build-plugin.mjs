#!/usr/bin/env node
/**
 * Build the two halves of the dsh-coderag JS plugin.
 *
 * - `src/plugin/index.js`  → `lib/index.js`  (ESM, Node): the Host half. It is
 *   bundled with `@deepseek-ai/schemastery` inlined, so an installed bundle has
 *   no runtime npm dependency and therefore no install script (E-05).
 * - `src/plugin/client/index.jsx` → `lib/client.js` (lazy-CJS factory): the
 *   browser half. DSH's client module loader hands the factory a `require` over
 *   the shell module table, so `react` and `react/jsx-runtime` stay external and
 *   everything else is inlined. The artifact is wrapped exactly like the
 *   published client bundles:
 *
 *       window.__ModuleLoader__.load({ id: "dsh-coderag", factory: (require) => {
 *       var module = { exports: {} }; var exports = module.exports;
 *       /* app code *\/
 *       return module.exports; } });
 *
 * The esbuild JS API spawns a service process over pipes. A DSH workspace
 * sandbox denies piped child processes (`spawn EPERM`), so the script falls
 * back to the same esbuild binary through its CLI with inherited stdio; the
 * artifact is identical because both paths share the definitions below.
 *
 * Usage: `node scripts/build-plugin.mjs` (or `pnpm run build`).
 */

import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const LIB = join(ROOT, 'lib')

/** Browser bundle identity: must match `package.json` `name`. */
const PLUGIN_ID = 'dsh-coderag'
/** Module-table specifiers the browser half is allowed to require. */
const CLIENT_EXTERNALS = ['react', 'react/jsx-runtime']

const banner = `window.__ModuleLoader__.load({ id: ${JSON.stringify(PLUGIN_ID)}, factory: (require) => {`
const intro = 'var module = { exports: {} }; var exports = module.exports;'
const footer = 'return module.exports; } });'

const clientOptions = {
  entryPoints: [join(ROOT, 'src/plugin/client/index.jsx')],
  outfile: join(LIB, 'client.js'),
  bundle: true,
  format: 'cjs',
  platform: 'browser',
  target: 'es2022',
  jsx: 'automatic',
  loader: { '.jsx': 'jsx' },
  external: CLIENT_EXTERNALS,
  charset: 'utf8',
  logLevel: 'warning',
  banner: { js: `${banner}\n${intro}` },
  footer: { js: footer },
}

const hostOptions = {
  entryPoints: [join(ROOT, 'src/plugin/index.js')],
  outfile: join(LIB, 'index.js'),
  bundle: true,
  format: 'esm',
  platform: 'node',
  target: 'node20',
  charset: 'utf8',
  logLevel: 'warning',
}

/** Locate the esbuild CLI shipped beside the JS package. */
function esbuildCli() {
  const platform = `${process.platform}-${process.arch}`
  const candidates = [
    join(ROOT, 'node_modules', '@esbuild', platform, process.platform === 'win32' ? 'esbuild.exe' : 'bin/esbuild'),
    join(ROOT, 'node_modules', '.bin', process.platform === 'win32' ? 'esbuild.cmd' : 'esbuild'),
  ]
  const found = candidates.find(candidate => existsSync(candidate))
  if (found === undefined) throw new Error('esbuild CLI not found; run `npm install` first')
  return found
}

/** Path relative to the repository root, slash-separated for esbuild's CLI. */
function repoRelative(target) {
  return relative(ROOT, target).split(sep).join('/')
}

/** Render CLI arguments that mirror one options object. */
function cliArgs(options) {
  const args = [
    ...options.entryPoints.map(repoRelative),
    '--bundle',
    `--format=${options.format}`,
    `--platform=${options.platform}`,
    `--target=${options.target}`,
    `--outfile=${repoRelative(options.outfile)}`,
    '--charset=utf8',
    '--log-level=warning',
  ]
  if (options.jsx === 'automatic') args.push('--jsx=automatic')
  if (options.loader !== undefined) {
    for (const [extension, loader] of Object.entries(options.loader)) args.push(`--loader:${extension}=${loader}`)
  }
  for (const external of options.external ?? []) args.push(`--external:${external}`)
  if (options.banner?.js !== undefined) args.push(`--banner:js=${options.banner.js}`)
  if (options.footer?.js !== undefined) args.push(`--footer:js=${options.footer.js}`)
  return args
}

/** Build through the esbuild JS API (the normal path). */
async function buildWithApi() {
  const { build } = await import('esbuild')
  for (const options of [clientOptions, hostOptions]) await build(options)
  return 'js-api'
}

/**
 * Build through the esbuild CLI with inherited stdio.
 * @returns {string} the path actually used.
 */
function buildWithCli() {
  const binary = esbuildCli()
  for (const options of [clientOptions, hostOptions]) {
    const result = spawnSync(binary, cliArgs(options), { cwd: ROOT, stdio: 'inherit' })
    if (result.error !== undefined) throw result.error
    if (result.status !== 0) throw new Error(`esbuild exited with status ${String(result.status)}`)
  }
  return 'cli'
}

/** Fail loudly if the emitted artifacts lost their contract. */
function verify() {
  const client = readFileSync(join(LIB, 'client.js'), 'utf8')
  const firstLine = client.split(/\r?\n/, 1)[0]
  if (!firstLine.startsWith(banner)) {
    throw new Error(`lib/client.js must start with the ModuleLoader banner, got: ${firstLine.slice(0, 120)}`)
  }
  if (!client.includes(footer)) throw new Error('lib/client.js is missing the factory footer')
  if (!client.includes(intro)) throw new Error('lib/client.js is missing the CommonJS intro')
  const host = readFileSync(join(LIB, 'index.js'), 'utf8')
  if (!/export\s*\{[^}]*\bapply\b/.test(host)) throw new Error('lib/index.js must export apply')
  if (!host.includes('coderag')) throw new Error('lib/index.js does not look like the coderag host half')
  console.log(`built lib/index.js (${(host.length / 1024).toFixed(1)} KiB) and lib/client.js (${(client.length / 1024).toFixed(1)} KiB)`)
}

mkdirSync(LIB, { recursive: true })
let path
try {
  path = await buildWithApi()
} catch (error) {
  if (error?.code !== 'EPERM' && !/spawn EPERM/.test(String(error?.message))) throw error
  console.warn('esbuild JS API is unavailable here (spawn EPERM); using the esbuild CLI with inherited stdio')
  path = buildWithCli()
}
console.log(`esbuild path: ${path}`)
verify()
