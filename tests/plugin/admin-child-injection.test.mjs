/**
 * Real-subprocess regression for the admin child hardening:
 * the child cwd contains a shadow `dsh_coderag` package, and the launcher must
 * import the real package from PYTHONPATH (not the shadow), while `status`
 * receives the key-present marker but never the key itself.
 *
 * The test skips when the test runner cannot spawn piped children (the DSH
 * workspace sandbox denies that) or when no Python interpreter is available.
 */

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { delimiter, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'
import { createAdminService } from '../../src/plugin/host/admin.js'

const REPO_ROOT = fileURLToPath(new URL('../../', import.meta.url))

/** Minimal package used as the "real" admin module. */
const REAL_ADMIN = `
import json, os, sys

def main():
    print(json.dumps({
        "ok": True,
        "index_exists": os.environ.get("CODERAG_SEMANTIC_API_KEY") is None,
        "vector_exists": False,
        "model": "real",
        "dim": 1,
        "total_chunks": 4242,
        "pending_chunks": 0,
        "config": {
            "enabled": True,
            "backend": "ollama",
            "url": "",
            "model": "real",
            "allow_remote": False,
            "key_present": os.environ.get("CODERAG_SEMANTIC_KEY_PRESENT") == "1",
        },
    }))
`

/** A hijack attempt that would answer if cwd were ever importable. */
const SHADOW_ADMIN = `
import json
print(json.dumps({"ok": True, "index_exists": False, "total_chunks": 9999, "config": {"key_present": False}}))
`

/** Write one package directory with an admin module. */
function writePackage(base, body) {
  const dir = join(base, 'dsh_coderag')
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, '__init__.py'), '')
  writeFileSync(join(dir, 'admin.py'), body)
  return base
}

test('the admin child ignores a shadow package in its cwd and status has no key', async t => {
  const python = process.env.CODERAG_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
  let probe
  try {
    probe = spawnSync(python, ['--version'], { encoding: 'utf8', timeout: 5000 })
  } catch (error) {
    t.skip(`no Python interpreter for the real-child test: ${error.message}`)
    return
  }
  if (probe.error !== undefined || probe.status !== 0) {
    t.skip(`no Python interpreter for the real-child test: ${probe.error?.message ?? probe.stderr ?? python}`)
    return
  }
  const savedPath = process.env.PYTHONPATH
  const base = mkdtempSync(join(process.cwd(), '.tmp-admin-injection-'))
  const realDir = writePackage(join(base, 'real'), REAL_ADMIN)
  const privateDir = join(base, 'private')
  mkdirSync(privateDir, { recursive: true })
  writePackage(privateDir, SHADOW_ADMIN)
  const repoSource = join(REPO_ROOT, 'src')
  process.env.PYTHONPATH = [realDir, repoSource, savedPath].filter(part => typeof part === 'string' && part !== '').join(delimiter)
  const service = createAdminService({
    readValues: () => ({ root: base, semanticBackend: 'ollama' }),
    resolveKey: async () => ({ available: true, value: 'sk-inject-secret' }),
    python: () => python,
    privateDir,
    logger: { warn() {}, info() {} },
  })
  try {
    const result = await service.state()
    if (result.ok === false && result.error.code === 'admin-spawn-failed') {
      t.skip(`cannot spawn a Python child here: ${result.error.message}`)
      return
    }
    assert.equal(result.ok, true, JSON.stringify(result))
    assert.equal(result.value.index_exists, true, 'the real module must answer, not the cwd shadow')
    assert.equal(result.value.total_chunks, 4242)
    assert.equal(result.value.config.key_present, true, 'the marker must reach status')
  } finally {
    service.dispose()
    if (savedPath === undefined) delete process.env.PYTHONPATH
    else process.env.PYTHONPATH = savedPath
    try {
      rmSync(base, { recursive: true, force: true })
    } catch {
      // Sandboxed temp cleanup can fail; the directory is under .tmp-* and ignored.
    }
  }
})
