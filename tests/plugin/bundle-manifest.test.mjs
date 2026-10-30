/**
 * Tests for the shipped bundle manifest and the built Host artifact.
 *
 * The bundle is installed by `dsh plugin add`, so its manifest must describe
 * both halves and must not ask pnpm to run anything at install time (E-05).
 * The Host bundle must stay dependency-free: `@deepseek-ai/schemastery` is
 * inlined at build time.
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { test } from 'node:test'

const REPO_ROOT = fileURLToPath(new URL('../../', import.meta.url))
const manifest = JSON.parse(readFileSync(`${REPO_ROOT}package.json`, 'utf8'))
const patch = readFileSync(`${REPO_ROOT}cordis.patch.yml`, 'utf8')

test('the package declares a Host entry, a Client entry and the bundle patch', () => {
  assert.equal(manifest.name, 'dsh-coderag')
  assert.equal(manifest.type, 'module')
  assert.equal(manifest.main, 'lib/index.js')
  assert.equal(manifest.exports['.'], './lib/index.js')
  assert.equal(manifest.exports['./client'], './lib/client.js')
  assert.equal(manifest.dsh.bundle.patch, './cordis.patch.yml')
  assert.equal(manifest.dsh.client.platform, 'web')
  assert.ok(manifest.files.includes('lib/index.js'))
  assert.ok(manifest.files.includes('lib/client.js'))
  assert.ok(manifest.files.includes('cordis.patch.yml'))
})

test('installing the bundle never runs a build script', () => {
  const lifecycle = ['preinstall', 'install', 'postinstall', 'prepare', 'prepublishOnly']
  for (const name of lifecycle) assert.equal(manifest.scripts?.[name], undefined, `${name} must stay unset`)
  assert.equal(manifest.dependencies, undefined, 'the built bundle has no runtime npm dependencies')
  assert.ok(manifest.devDependencies.esbuild, 'esbuild is a maintainer-only build input')
  assert.ok(manifest.devDependencies['@deepseek-ai/schemastery'], 'schemastery is inlined at build time')
})

test('the patch inserts the settings row and keeps the MCP executor row', () => {
  assert.match(patch, /^\s+- id: coderag$/m)
  assert.match(patch, /^\s+name: dsh-coderag$/m)
  assert.match(patch, /^\s+- id: mcp-coderag$/m)
  assert.match(patch, /@deepseek-ai\/dsh-mcp-client/)
  assert.match(patch, /CODERAG_MAX_TOKENS/)
  assert.match(patch, /CODERAG_SEMANTIC_ALLOW_REMOTE/)
  assert.match(patch, /CODERAG_SEMANTIC_API_KEY/)
  assert.match(patch, /SECURITY WARNING/)
})

test('the settings row reads the shell environment as its defaults', () => {
  for (const variable of [
    'CODERAG_ROOT', 'CODERAG_MAX_FILES', 'CODERAG_MAX_FILE_BYTES', 'CODERAG_MAX_TOKENS',
    'CODERAG_EXTRA_EXTENSIONS', 'CODERAG_SEMANTIC', 'CODERAG_SEMANTIC_BACKEND',
    'CODERAG_SEMANTIC_URL', 'CODERAG_SEMANTIC_MODEL', 'CODERAG_SEMANTIC_QUERY_TIMEOUT',
    'CODERAG_SEMANTIC_BATCH', 'CODERAG_SEMANTIC_MAX_CHUNKS', 'CODERAG_SEMANTIC_ALLOW_REMOTE',
  ]) {
    assert.match(patch, new RegExp(`!!js[^\\n]*process\\.env\\.${variable}`), `missing default expression for ${variable}`)
  }
})

test('numeric defaults clamp bad shell values instead of failing Config mounting', () => {
  const expression = key => {
    const match = patch.match(new RegExp(`^\\s+${key}: !!js "(.+)"$`, 'm'))
    assert.ok(match, `missing default expression for ${key}`)
    return match[1]
  }
  const evaluate = (key, env) => new Function('process', `return (${expression(key)})`)({ env })
  for (const key of ['maxFiles', 'maxFileBytes', 'maxTokens', 'semanticQueryTimeout', 'semanticBatch', 'semanticMaxChunks']) {
    const variable = {
      maxFiles: 'CODERAG_MAX_FILES',
      maxFileBytes: 'CODERAG_MAX_FILE_BYTES',
      maxTokens: 'CODERAG_MAX_TOKENS',
      semanticQueryTimeout: 'CODERAG_SEMANTIC_QUERY_TIMEOUT',
      semanticBatch: 'CODERAG_SEMANTIC_BATCH',
      semanticMaxChunks: 'CODERAG_SEMANTIC_MAX_CHUNKS',
    }[key]
    assert.equal(evaluate(key, { [variable]: '-5' }), 0, `${key} must clamp negatives`)
    assert.equal(evaluate(key, { [variable]: '3.9' }), 3, `${key} must truncate fractions`)
    assert.equal(evaluate(key, { [variable]: 'many' }), 0, `${key} must fall back for NaN`)
    assert.equal(evaluate(key, { [variable]: 'Infinity' }), 0, `${key} must reject non-finite values`)
  }
})

test('the backend default is restricted to the form vocabulary', () => {
  const match = patch.match(/^\s+semanticBackend: !!js "(.+)"$/m)
  assert.ok(match)
  const evaluate = env => new Function('process', `return (${match[1]})`)({ env })
  assert.equal(evaluate({ CODERAG_SEMANTIC_BACKEND: 'ollama' }), 'ollama')
  assert.equal(evaluate({ CODERAG_SEMANTIC_BACKEND: 'openai' }), 'openai')
  assert.equal(evaluate({ CODERAG_SEMANTIC_BACKEND: 'weird' }), '')
  assert.equal(evaluate({}), '')
})

test('owned variables are not duplicated on the MCP row', () => {
  const mcpRow = patch.slice(patch.indexOf('- id: mcp-coderag'))
    // Comments carry the security warning and mention the removed names; only
    // YAML keys count as duplication.
    .split(/\r?\n/)
    .filter(line => !line.trimStart().startsWith('#'))
    .join('\n')
  for (const owned of [
    'CODERAG_ROOT', 'CODERAG_MAX_FILES', 'CODERAG_MAX_FILE_BYTES', 'CODERAG_MAX_TOKENS',
    'CODERAG_EXTRA_EXTENSIONS', 'CODERAG_SEMANTIC:', 'CODERAG_SEMANTIC_BACKEND',
    'CODERAG_SEMANTIC_URL', 'CODERAG_SEMANTIC_MODEL', 'CODERAG_SEMANTIC_QUERY_TIMEOUT',
    'CODERAG_SEMANTIC_BATCH', 'CODERAG_SEMANTIC_MAX_CHUNKS', 'CODERAG_SEMANTIC_ALLOW_REMOTE',
  ]) {
    assert.equal(mcpRow.includes(owned), false, `the MCP row must not set ${owned}`)
  }
  // The key is the only variable that stays on the MCP row on purpose.
  const envKeys = [...mcpRow.matchAll(/^\s+(CODERAG_[A-Z_]+):/gm)].map(match => match[1])
  assert.deepEqual(envKeys, ['CODERAG_SEMANTIC_API_KEY'])
})

test('the shipped bundle bakes in no interpreter path and no workspace guess', () => {
  assert.doesNotMatch(patch, /\/opt\/anaconda3/)
  assert.doesNotMatch(patch, /F:\\+conda/)
  assert.doesNotMatch(patch, /process\.cwd\(\)/)
  assert.doesNotMatch(patch, /^\s+CODERAG_ROOT:/m)
})

test('the built Host bundle exports a function plugin with an all-volatile Config', async () => {
  const host = await import(pathToFileURL(`${REPO_ROOT}lib/index.js`).href)
  assert.equal(host.name, 'dsh-coderag')
  assert.deepEqual(host.inject, ['loader'])
  assert.equal(typeof host.apply, 'function')
  // schemastery's JSON form is a reference graph: `uid` names the root node and
  // `refs` holds every node once. The settings service rehydrates it the same way.
  const graph = host.Config.toJSON()
  const root = graph.refs[graph.uid]
  assert.equal(root.type, 'object')
  const expected = [
    'root', 'maxFiles', 'maxFileBytes', 'maxTokens', 'extraExtensions', 'semantic',
    'semanticBackend', 'semanticUrl', 'semanticModel', 'semanticQueryTimeout', 'semanticBatch',
    'semanticMaxChunks', 'semanticAllowRemote',
  ]
  assert.deepEqual(Object.keys(root.dict).sort(), expected.sort())
  for (const field of expected) {
    assert.equal(graph.refs[root.dict[field]].meta.volatile, true, `${field} must be volatile`)
  }
})
