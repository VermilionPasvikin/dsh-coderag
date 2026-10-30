/**
 * Tests for the built browser artifact and its two configuration entries.
 *
 * `lib/client.js` is evaluated the way DSH's client module loader does it
 * (banner + factory with a `require` over the shell module table), then the
 * registered components are server-rendered with the owner props the Plugins
 * page passes. No DOM is needed; user interaction rules are covered separately
 * by `client-form.test.mjs` and the live-runtime host probe.
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

const REPO_ROOT = fileURLToPath(new URL('../../', import.meta.url))
const nodeRequire = createRequire(import.meta.url)
const React = nodeRequire('react')
const { renderToStaticMarkup } = nodeRequire('react-dom/server')

const BANNER = 'window.__ModuleLoader__.load({ id: "dsh-coderag", factory: (require) => {'

const FIELD_LABELS = [
  '工作区根', '文件数量上限', '单文件字节上限', '检索 token 预算', '额外文件扩展名',
  '启用语义检索', '语义后端', '语义服务 URL', '语义模型', '语义查询超时（秒）',
  '语义批量大小', '向量化 chunk 上限', '允许非 loopback 云端地址',
]

const READY_VALUES = {
  root: 'F:\\repo',
  maxFiles: 100,
  maxFileBytes: 0,
  maxTokens: 5000,
  extraExtensions: '.mxml',
  semantic: true,
  semanticBackend: 'ollama',
  semanticUrl: 'http://127.0.0.1:11434',
  semanticModel: 'bge-m3',
  semanticQueryTimeout: 0,
  semanticBatch: 0,
  semanticMaxChunks: 50000,
  semanticAllowRemote: false,
}

const form = {
  state: {
    status: 'ready',
    value: READY_VALUES,
    base: {
      root: '', maxFiles: 0, maxFileBytes: 0, maxTokens: 0, extraExtensions: '', semantic: false,
      semanticBackend: '', semanticUrl: '', semanticModel: '', semanticQueryTimeout: 0, semanticBatch: 0,
      semanticMaxChunks: 0, semanticAllowRemote: false,
    },
    user: { root: 'F:\\repo' },
    revision: 3,
    writable: true,
  },
  mutate: async () => true,
}

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

/** Capture all three slot contributions, with the shared configForms service stubbed. */
function contribute(module) {
  const registrations = new Map()
  const observable = {
    getSnapshot: () => form.state,
    subscribe: () => () => {},
    mutate: async () => true,
  }
  const ctx = {
    configForms: {
      get: id => {
        assert.equal(id, 'coderag')
        return observable
      },
    },
    remote: {
      credentials: {
        describe: async () => ({ ok: true, value: { CODERAG_SEMANTIC_API_KEY: { configured: false, writable: true } } }),
        set: async () => ({ ok: true }),
        unset: async () => ({ ok: true }),
      },
    },
    slots: {
      inject: (name, callback) => {
        assert.ok(
          name === 'settings.section' || name === 'plugins.row.config' || name === 'plugins.bundle.config',
          name,
        )
        callback()
      },
      register: (options, component) => {
        registrations.set(options.name, { options, component })
        return () => {}
      },
    },
  }
  module.apply(ctx)
  return registrations
}

/** Render one contribution with owner props. */
function render(registrations, slot, props) {
  const markup = renderToStaticMarkup(React.createElement(registrations.get(slot).component, props))
  return { markup, text: markup.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ') }
}

test('the browser artifact is a lazy-CJS ModuleLoader factory', () => {
  const { loaded, source, module } = loadClient()
  assert.equal(source.split(/\r?\n/, 1)[0], BANNER)
  assert.equal(loaded.id, 'dsh-coderag')
  assert.match(source.trimEnd(), /return module\.exports; \} \}\);$/)
  assert.deepEqual(Object.keys(module).sort(), ['apply', 'inject'])
  assert.deepEqual(module.inject, ['slots', 'configForms', 'remote', 'remote.credentials'])
})

test('only React is requested from the shell module table', () => {
  const { requested } = loadClient()
  assert.deepEqual([...new Set(requested)].sort(), ['react', 'react/jsx-runtime'])
})

test('the settings section, row page and bundle page are all registered', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  assert.deepEqual([...registrations.keys()].sort(), [
    'plugins.bundle.config', 'plugins.row.config', 'settings.section',
  ])
  assert.deepEqual(registrations.get('settings.section').options, {
    name: 'settings.section', id: 'coderag', order: 30, label: registrations.get('settings.section').options.label,
  })
  assert.equal(registrations.get('settings.section').options.label(), 'CodeRAG')
  assert.deepEqual(registrations.get('plugins.row.config').options, {
    name: 'plugins.row.config', key: 'dsh-coderag#coderag',
  })
  assert.deepEqual(registrations.get('plugins.bundle.config').options, {
    name: 'plugins.bundle.config', key: 'dsh-coderag',
  })
})

test('the summary view describes the row without a form', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  for (const slot of ['plugins.row.config', 'plugins.bundle.config']) {
    const { text } = render(registrations, slot, { view: 'summary' })
    assert.match(text, /CodeRAG/)
    assert.match(text, /同步到 MCP 行/)
  }
})

test('the Settings section renders the form from configForms', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  const { markup, text } = render(registrations, 'settings.section', { close: () => {} })
  for (const label of FIELD_LABELS) {
    assert.match(text, new RegExp(label), `missing settings-page field label: ${label}`)
  }
  assert.match(text, /CodeRAG 参数设置/)
  assert.match(text, /设置 → CodeRAG/)
  assert.match(markup, /value="F:\\repo"/)
  assert.match(markup, /value="5000"/)
  assert.match(text, /保存/)
})

test('the Settings section renders the operations panels', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  const { text } = render(registrations, 'settings.section', { close: () => {} })
  assert.match(text, /CodeRAG 运维/)
  assert.match(text, /云端 API Key/)
  assert.match(text, /语义后端/)
  assert.match(text, /向量数据库/)
  assert.match(text, /已配置（不可查看）|未配置|读取中/)
  assert.match(text, /检查本地连通性/)
  assert.match(text, /一键启动本地后端/)
})

test('the bundle page renders the form from configForms without an owner form', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  const { markup, text } = render(registrations, 'plugins.bundle.config', { view: 'page' })
  for (const label of FIELD_LABELS) {
    assert.match(text, new RegExp(label), `missing bundle-page field label: ${label}`)
  }
  assert.match(markup, /value="F:\\repo"/)
  assert.match(markup, /value="5000"/)
  assert.match(markup, /value="50000"/)
  assert.match(text, /保存/)
})

test('the row page still renders the owner-supplied form', () => {
  const { module } = loadClient()
  const { markup, text } = render(contribute(module), 'plugins.row.config', { view: 'page', form })
  for (const label of FIELD_LABELS) {
    assert.match(text, new RegExp(label), `missing row-page field label: ${label}`)
  }
  assert.match(markup, /value="F:\\repo"/)
  assert.match(markup, /value="5000"/)
  assert.match(markup, /<select/)
  assert.match(markup, /type="checkbox"/)
  assert.match(text, /保存/)
  assert.match(text, /恢复默认/)
})

test('loading and unavailable states explain themselves instead of rendering a form', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  const loading = render(registrations, 'plugins.row.config', { view: 'page', form: undefined })
  assert.match(loading.text, /正在读取 CodeRAG 设置/)
  const unavailable = render(registrations, 'plugins.row.config', {
    view: 'page',
    form: { state: { status: 'unavailable', writable: false }, mutate: async () => false },
  })
  assert.match(unavailable.text, /未提供 CodeRAG 设置/)
})

test('a read-only Host disables saving and says so', () => {
  const { module } = loadClient()
  const registrations = contribute(module)
  const { markup, text } = render(registrations, 'plugins.row.config', {
    view: 'page',
    form: { ...form, state: { ...form.state, writable: false } },
  })
  assert.match(text, /只读/)
  assert.match(markup, /disabled=""/)
})
