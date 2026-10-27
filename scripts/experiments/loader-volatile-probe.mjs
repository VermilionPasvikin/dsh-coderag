#!/usr/bin/env node
/**
 * T5-01 probe: prove the Loader entry-update and volatile-config contract that
 * the CodeRAG settings page relies on, against the DSH build installed here.
 *
 * DSH ships its runtime inside `app.asar`; this script extracts only the
 * packages the probe needs into `--out` and runs them with plain Node, so the
 * evidence comes from the shipped implementation rather than from repository
 * sources that may have drifted from it.
 *
 * Contracts under test:
 *   1. `entry.update({ config })` with volatile-only changes commits the values
 *      into the running fiber in place (same config object, `.get()` updated),
 *      emits `loader/volatile-update` on the owning fiber with the changed
 *      paths, and does NOT remount the plugin.
 *   2. A mixed change (volatile + ordinary, or an ordinary-only field such as
 *      the MCP row's `env`) takes the ordinary lifecycle: the plugin remounts,
 *      and no volatile event fires.
 *   3. `ctx.loader.resolve(id).update(...)` and `ctx.loader.update(id, ...)`
 *      are the per-entry APIs; `ctx.loader.root.update(...)` is the entry-list
 *      API (`EntryOptions[]`), not a per-entry config patch.
 *   4. Updating a child entry inside a file-backed `cordis:include` tree does
 *      not rewrite the include file: the settings sync stays in memory.
 *   5. Volatile references are identified through `Symbol.for`, so a plugin
 *      that bundles its own `@deepseek-ai/schemastery` copy is still seen by the
 *      Host's Loader (this is what lets the bundle carry no runtime npm deps).
 *
 * Usage:
 *   node scripts/experiments/loader-volatile-probe.mjs --asar "F:\dsh\resources\app.asar"
 *   node scripts/experiments/loader-volatile-probe.mjs --asar <asar> --out .tmp-asar/probe --keep
 *
 * Exits 0 when every check passes, 1 otherwise.
 */
import { closeSync, existsSync, mkdirSync, mkdtempSync, openSync, readFileSync, readSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const REPO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const PACKAGES = ['cordis', 'cosmokit', 'schemastery', 'cordis-plugin-loader', 'cordis-plugin-include']
const TOP_LEVEL = ['js-yaml', 'argparse', '@standard-schema/spec']

function parseArgs(argv) {
  const options = {}
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--keep') options.keep = true
    else if (arg === '--asar') options.asar = argv[++index]
    else if (arg === '--out') options.out = argv[++index]
    else throw new Error(`unknown argument: ${arg}`)
  }
  if (!options.asar) throw new Error('--asar <path to app.asar> is required')
  if (!existsSync(options.asar)) throw new Error(`app.asar not found: ${options.asar}`)
  return options
}

/** Read the asar directory header (Pickle framing: u32 size, u32 payload size, JSON). */
function readAsarHeader(file) {
  const fd = openSync(file, 'r')
  try {
    const sizes = Buffer.alloc(8)
    readSync(fd, sizes, 0, 8, 0)
    const headerSize = sizes.readUInt32LE(4)
    const header = Buffer.alloc(headerSize)
    readSync(fd, header, 0, headerSize, 8)
    const jsonLength = header.readUInt32LE(4)
    return { base: 8 + headerSize, files: JSON.parse(header.toString('utf8', 8, 8 + jsonLength)) }
  } finally {
    closeSync(fd)
  }
}

function walk(node, prefix, out) {
  if (node?.files) {
    for (const [name, child] of Object.entries(node.files)) walk(child, `${prefix}/${name}`, out)
  } else if (node) {
    out.set(prefix, node)
  }
  return out
}

/** Extract a flat subset of `node_modules` entries from the archive. */
function extract(asar, outRoot) {
  const { base, files } = readAsarHeader(asar)
  const wanted = new Set([...PACKAGES.map(name => `@deepseek-ai/${name}`), ...TOP_LEVEL])
  const fd = openSync(asar, 'r')
  let copied = 0
  let bytes = 0
  try {
    for (const [archivePath, entry] of walk(files, '', new Map())) {
      const marker = archivePath.indexOf('/node_modules/')
      if (marker < 0 || archivePath.indexOf('/node_modules/', marker + 1) >= 0) continue
      const relative = archivePath.slice(marker + '/node_modules/'.length)
      const name = relative.startsWith('@') ? relative.split('/').slice(0, 2).join('/') : relative.split('/')[0]
      if (!wanted.has(name)) continue
      const target = join(outRoot, 'node_modules', ...relative.split('/'))
      mkdirSync(dirname(target), { recursive: true })
      const buffer = Buffer.alloc(entry.size)
      readSync(fd, buffer, 0, entry.size, base + Number(entry.offset))
      writeFileSync(target, buffer)
      copied += 1
      bytes += entry.size
    }
  } finally {
    closeSync(fd)
  }
  return { copied, bytes }
}

const options = parseArgs(process.argv.slice(2))
const outRoot = options.out ? join(REPO_ROOT, options.out) : mkdtempSync(join(tmpdir(), 'dsh-volatile-probe-'))
rmSync(outRoot, { recursive: true, force: true })
mkdirSync(outRoot, { recursive: true })
const extraction = extract(options.asar, outRoot)
console.log(`extracted ${extraction.copied} files (${Math.round(extraction.bytes / 1024)} KiB) from ${options.asar}`)

const importModule = specifier => import(pathToFileURL(specifier).href)
const libDir = join(outRoot, 'node_modules', '@deepseek-ai')
const { Context } = await importModule(join(libDir, 'cordis', 'lib', 'index.js'))
const { default: Loader } = await importModule(join(libDir, 'cordis-plugin-loader', 'lib', 'index.js'))
const { default: Include } = await importModule(join(libDir, 'cordis-plugin-include', 'lib', 'index.js'))
const schemasteryPath = join(libDir, 'schemastery', 'lib', 'index.mjs')
const z = (await importModule(schemasteryPath)).default

const results = []
const log = (...args) => console.log(...args)
function check(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  results.push({ label, ok, actual, expected })
  log(`${ok ? 'PASS' : 'FAIL'} ${label} actual=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`)
}

// --- volatile-only vs ordinary updates through a Loader builtin -------------
const ctx = new Context()
await ctx.plugin(Loader)
const Config = z.object({
  root: z.string().default('').volatile(),
  maxFiles: z.natural().default(0).volatile(),
  env: z.dict(z.string()).default({}),
})
const applies = []
const volatileEvents = []
ctx.loader.builtins['mcp-like'] = {
  Config,
  apply(owner, config) {
    applies.push({ root: config.root.get(), env: { ...config.env } })
    owner.on('loader/volatile-update', paths => {
      volatileEvents.push({ paths: paths.map(path => path.join('.')), root: config.root.get() })
    })
  },
}
const id = await ctx.loader.create({
  name: 'cordis:mcp-like',
  config: { root: '/old', maxFiles: 10, env: { CODERAG_ROOT: '/old' } },
})
const entry = ctx.loader.resolve(id)
await entry.fiber.await()
const initialConfig = entry.fiber.config
check('initial apply ran once', applies.length, 1)
check('create() return names the entry id', entry.options.id, id)
await entry.update({ config: { root: '/new', maxFiles: 10, env: { CODERAG_ROOT: '/old' } } })
await entry.fiber.await()
check('volatile-only update does not remount', applies.length, 1)
check('the running config object is kept', entry.fiber.config === initialConfig, true)
check('the volatile reference sees the new value', initialConfig.root.get(), '/new')
check('the owning fiber receives the changed path', volatileEvents.map(event => event.paths), [['root']])
check('the event handler already sees the committed value', volatileEvents[0]?.root, '/new')
await entry.update({ config: { root: '/new', maxFiles: 10, env: { CODERAG_ROOT: '/new' } } })
await entry.fiber.await()
check('an ordinary env change remounts the plugin', applies.length, 2)
check('the remount receives the new env', applies[1].env.CODERAG_ROOT, '/new')
check('an ordinary change emits no volatile event', volatileEvents.length, 1)
await ctx.fiber.dispose()

// --- tree-level and group-level APIs ---------------------------------------
const ctx2 = new Context()
await ctx2.plugin(Loader)
const applies2 = []
ctx2.loader.builtins.probe = { Config, apply(owner, config) { applies2.push(config.root.get()) } }
const id2 = await ctx2.loader.create({ name: 'cordis:probe', config: { root: 'a', maxFiles: 1, env: {} } })
await ctx2.loader.resolve(id2).fiber.await()
await ctx2.loader.update(id2, { config: { root: 'b', maxFiles: 1, env: {} } })
await ctx2.loader.await()
check('ctx.loader.update(id, ...) commits volatile config', applies2.length, 1)
check('ctx.loader.update(id, ...) keeps the live reference current', ctx2.loader.resolve(id2).fiber.config.root.get(), 'b')
check('ctx.loader.root.update is the entry-list API (1 argument)', ctx2.loader.root.update.length, 1)
check('ctx.loader.root.update is not the Entry config patch', ctx2.loader.root.update === ctx2.loader.update, false)
await ctx2.fiber.dispose()

// --- a file-backed Include is not rewritten by a child entry update --------
const scratch = join(outRoot, 'include-scratch')
mkdirSync(scratch, { recursive: true })
const ctx3 = new Context()
await ctx3.plugin(Loader)
ctx3.baseUrl = pathToFileURL(scratch).href + '/'
ctx3.loader.builtins.include = Include
ctx3.loader.builtins.child = { Config, apply() {} }
const childFile = join(scratch, 'child.yml')
const original = [
  '- id: child',
  '  name: cordis:child',
  '  config:',
  '    root: file-root',
  '    env:',
  '      K: file',
  '',
].join('\n')
writeFileSync(childFile, original)
const includeId = await ctx3.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(childFile).href } })
await ctx3.loader.await()
const includeTree = ctx3.loader.resolve(includeId).subtree
const child = [...ctx3.loader.entries()].find(candidate => candidate.options.id === 'child')
check('the settings row lives inside a file-backed tree', child.parent.tree === includeTree, true)
await child.update({ config: { root: 'memory-root', env: { K: 'memory' } } })
await ctx3.loader.await()
check('entry.update leaves the include file untouched', readFileSync(childFile, 'utf8') === original, true)
await ctx3.fiber.dispose()

// --- cross-copy volatile protocol (bundled schemastery) --------------------
const cosmokitPath = join(libDir, 'cosmokit', 'lib', 'index.js')
const cosmokitHost = await importModule(cosmokitPath)
// A distinct module instance stands in for the copy a plugin bundles itself.
const cosmokitCopy = await import(new URL('?copy=2', pathToFileURL(cosmokitPath)).href)
const reference = cosmokitCopy.createVolatile({ root: '/x' })
check('volatile references are identified across module copies', cosmokitHost.isVolatile(reference), true)
check('the host copy can read the bundled copy reference', reference.get().root, '/x')
const rehydrated = new z(Config.toJSON())
check('the schema JSON keeps meta.volatile for every editable field', {
  root: rehydrated.dict.root.meta.volatile,
  maxFiles: rehydrated.dict.maxFiles.meta.volatile,
}, { root: true, maxFiles: true })
const parsed = rehydrated({ root: '/r', maxFiles: 3, env: {} })
check('volatileEntries finds the nested references', cosmokitHost.volatileEntries(parsed).map(item => item.path.join('.')).sort(), ['maxFiles', 'root'])

const failed = results.filter(result => !result.ok)
log(`\nSUMMARY: ${results.length - failed.length}/${results.length} checks passed`)
if (failed.length > 0) {
  log(JSON.stringify(failed, null, 2))
  process.exitCode = 1
}
if (!options.out) rmSync(outRoot, { recursive: true, force: true })
else if (!options.keep) log(`kept extracted tree at ${outRoot}`)
