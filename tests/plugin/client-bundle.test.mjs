/**
 * Tests for the built browser artifact and its `plugins.row.config` entry.
 *
 * `lib/client.js` is evaluated the way DSH's client module loader does it
 * (banner + factory with a `require` over the shell module table), then the
 * registered component is server-rendered with the owner props the Plugins page
 * passes. No DOM is needed; user interaction rules are covered separately by
 * `client-form.test.mjs` and the live-runtime host probe.
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { test } from 'node:test'

const REPO_ROOT = fileURLToPath(new URL('../../', import.meta.url))
const nodeRequire = createRequire(import.meta.url)
const React = nodeRequire('react')
const { renderToStaticMarkup } = nodeRequire('react-dom/server')

const BANNER = 'window.__ModuleLoader__.load({ id: "dsh-coderag", factory: (require) => {'

/** Load the artifact through a fake module table. */
function loadClient() {
  const requested = []
  const requireStub = specifier => {
    requested.push(specifier)
    if (specifier === 'react') return React
    if (specifier === 'react/jsx-runtime') return nodeRequire('react/jsx-runtime')
    throw new Error(`the bundle requested an undeclared external: ${specifier}`)
  }
  let loaded
  const window = { __ModuleLoader__: { load: entry => { loaded = entry } } }
  const source = readFileSync(`${REPO_ROOT}lib/client.js`, 'utf8')
  new Function('window', source)(window)
  return { loaded, module: loaded.factory(requireStub), requested, source }
}

/** Capture the row-config contribution. */
function contribute(module) {
  const registrations = []
  const ctx = {
    slots: {
      inject: (name, callback) => {
        assert.equal(name, 'plugins.row.config')
        callback()
      },
      register: (options, component) => {
        registrations.push({ options, component })
        return () => {}
      },
    },
  }
  module.apply(ctx)
  return registrations
}

const form = {
  state: {
    status: 'ready',
    value: {
      root: 'F:\\repo',
      maxFiles: 100,
      maxFileBytes: 0,
      extraExtensions: '.mxml',
      semantic: true,
      semanticBackend: 'ollama',
      semanticUrl: 'http://127.0.0.1:11434',
      semanticModel: 'bge-m3',
      semanticTimeout: 0,
      semanticBatch: 0,
    },
    base: {
      root: '', maxFiles: 0, maxFileBytes: 0, extraExtensions: '', semantic: false,
      semanticBackend: '', semanticUrl: '', semanticModel: '', semanticTimeout: 0, semanticBatch: 0,
    },
    user: { root: 'F:\\repo' },
    revision: 3,
    writable: true,
  },
  mutate: async () => true,
}

/** Render the registered contribution with owner props. */
function render(registrations, props) {
  const markup = renderToStaticMarkup(React.createElement(registrations[0].component, props))
  return { markup, text: markup.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ') }
}

test('the browser artifact is a lazy-CJS ModuleLoader factory', () => {
  const { loaded, source, module } = loadClient()
  assert.equal(source.split(/\r?\n/, 1)[0], BANNER)
  assert.equal(loaded.id, 'dsh-coderag')
  assert.match(source.trimEnd(), /return module\.exports; \} \}\);$/)
  assert.deepEqual(Object.keys(module).sort(), ['apply', 'inject'])
  assert.deepEqual(module.inject, ['slots'])
})

test('only React is requested from the shell module table', () => {
  const { requested } = loadClient()
  assert.deepEqual([...new Set(requested)].sort(), ['react', 'react/jsx-runtime'])
})

test('the contribution registers under dsh-coderag#coderag', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  assert.equal(registrations.length, 1)
  assert.deepEqual(registrations[0].options, { name: 'plugins.row.config', key: 'dsh-coderag#coderag' })
})

test('the summary view describes the row without a form', () => {
  const { module } = loadClient()
  const { text } = render(contribute(module), { view: 'summary' })
  assert.match(text, /CodeRAG/)
  assert.match(text, /同步到 MCP 行/)
})

test('the page view renders every field and the accepted values', () => {
  const { module } = loadClient()
  const { markup, text } = render(contribute(module), { view: 'page', form })
  for (const label of ['工作区根', '文件数量上限', '单文件字节上限', '额外文件扩展名', '启用语义检索', '语义后端', '语义服务 URL', '语义模型', '语义请求超时（秒）', '语义批量大小']) {
    assert.match(text, new RegExp(label), `missing field label: ${label}`)
  }
  assert.match(markup, /value="F:\\repo"/)
  assert.match(markup, /value="100"/)
  assert.match(markup, /<select/)
  assert.match(markup, /type="checkbox"/)
  assert.match(text, /保存/)
  assert.match(text, /恢复默认/)
})

test('loading and unavailable states explain themselves instead of rendering a form', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  const loading = render(registrations, { view: 'page', form: undefined })
  assert.match(loading.text, /正在读取 CodeRAG 设置/)
  const unavailable = render(registrations, {
    view: 'page',
    form: { state: { status: 'unavailable', writable: false }, mutate: async () => false },
  })
  assert.match(unavailable.text, /未提供 CodeRAG 设置/)
})

test('a read-only Host disables saving and says so', () => {
  const { module } = loadClient()
  const { markup, text } = render(contribute(module), {
    view: 'page',
    form: { ...form, state: { ...form.state, writable: false } },
  })
  assert.match(text, /只读/)
  assert.match(markup, /disabled=""/)
})
