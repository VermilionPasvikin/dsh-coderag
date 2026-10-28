/**
 * Operations panels rendered below the CodeRAG parameter form:
 * the cloud API key (credentials), embedding-backend health, and the vector
 * index automation. Every action goes through the authenticated Host routes;
 * the browser never talks to Python and never sees a stored key.
 *
 * Rendered on all three settings surfaces because they share SettingsPage.
 */

import * as React from 'react'
import { HEALTH_BACKENDS, SEMANTIC_KEY_REF, normalizeAdminStatus } from '../shared/admin-protocol.js'
import {
  fetchAdminJob,
  fetchAdminState,
  formatCount,
  formatGeneratedAt,
  jobActive,
  jobLabel,
  jobPercent,
  normalizeJob,
  runAdminAction,
} from '../shared/admin-client.js'

const { useCallback, useEffect, useRef, useState } = React

const styles = {
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    borderTop: '1px solid var(--dsw-alias-border-l2, #d0d7de)',
    paddingTop: '16px',
    marginTop: '4px',
  },
  heading: { margin: 0, fontSize: '15px', fontWeight: 600 },
  card: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    border: '1px solid var(--dsw-alias-border-l2, #d0d7de)',
    borderRadius: '8px',
    padding: '12px 14px',
  },
  cardTitle: { margin: 0, fontSize: '13px', fontWeight: 600 },
  row: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' },
  column: { display: 'flex', flexDirection: 'column', gap: '4px' },
  hint: { margin: 0, fontSize: '12px', opacity: 0.72 },
  status: { margin: 0, fontSize: '12px' },
  ok: { color: 'var(--dsw-alias-state-success-primary, #1a7f37)' },
  bad: { color: 'var(--dsw-alias-state-error-primary, #cf222e)' },
  input: {
    boxSizing: 'border-box',
    flex: '1 1 220px',
    minWidth: '160px',
    padding: '6px 8px',
    borderRadius: '6px',
    border: '1px solid var(--dsw-alias-border-l2, #d0d7de)',
    background: 'var(--dsw-alias-bg-base, #ffffff)',
    color: 'var(--dsw-alias-label-primary, #1f2328)',
    fontSize: '13px',
  },
  button: {
    padding: '6px 14px',
    borderRadius: '6px',
    border: '1px solid var(--dsw-alias-border-l2, #d0d7de)',
    background: 'var(--dsw-alias-bg-layer-2, transparent)',
    color: 'var(--dsw-alias-label-primary, #1f2328)',
    fontSize: '13px',
    cursor: 'pointer',
  },
  primary: {
    padding: '6px 14px',
    borderRadius: '6px',
    border: '1px solid transparent',
    background: 'var(--dsw-alias-button-primary-fill, #0969da)',
    color: 'var(--dsw-alias-label-primary-inverted, #ffffff)',
    fontSize: '13px',
    cursor: 'pointer',
  },
  danger: {
    padding: '6px 14px',
    borderRadius: '6px',
    border: '1px solid transparent',
    background: 'var(--dsw-alias-state-error-primary, #cf222e)',
    color: '#ffffff',
    fontSize: '13px',
    cursor: 'pointer',
  },
  bar: {
    height: '6px',
    borderRadius: '999px',
    background: 'var(--dsw-alias-bg-layer-2, #f0f0f0)',
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    background: 'var(--dsw-alias-button-primary-fill, #0969da)',
    transition: 'width .3s ease',
  },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '6px 16px' },
  stat: { margin: 0, fontSize: '12px' },
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgb(0 0 0 / 45%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  dialog: {
    maxWidth: '520px',
    width: 'calc(100% - 48px)',
    background: 'var(--dsw-alias-bg-layer-2, #ffffff)',
    color: 'var(--dsw-alias-label-primary, #1f2328)',
    border: '1px solid var(--dsw-alias-border-l2, #d0d7de)',
    borderRadius: '10px',
    padding: '16px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    boxShadow: '0 16px 48px rgb(0 0 0 / 28%)',
  },
  dialogTitle: { margin: 0, fontSize: '14px', fontWeight: 600 },
  dialogBody: { margin: 0, fontSize: '13px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
}

/** Closable error dialog: the Host's message verbatim. */
function ErrorDialog({ error, onClose }) {
  if (error === null) return null
  return (
    <div style={styles.overlay} role="presentation" onClick={event => { if (event.target === event.currentTarget) onClose() }}>
      <div style={styles.dialog} role="dialog" aria-modal="true" aria-label="CodeRAG 运维错误">
        <h4 style={styles.dialogTitle}>操作失败</h4>
        <p style={styles.dialogBody}>{error}</p>
        <div style={styles.row}>
          <button type="button" style={styles.primary} onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}

/** A titled card with a description line. */
function Panel({ title, description, children }) {
  return (
    <section style={styles.card}>
      <h4 style={styles.cardTitle}>{title}</h4>
      {description === undefined ? null : <p style={styles.hint}>{description}</p>}
      {children}
    </section>
  )
}

/**
 * Cloud key card. The value is write-only by construction: the Host never
 * returns it, so the input is cleared after a save and only `configured` is read
 * back through `remote.credentials.describe`.
 */
export function CredentialPanel({ remote }) {
  const [status, setStatus] = useState({ phase: 'loading' })
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (remote?.credentials === undefined) {
      setStatus({ phase: 'unavailable' })
      return
    }
    setStatus({ phase: 'loading' })
    let response
    try {
      response = await remote.credentials.describe([SEMANTIC_KEY_REF])
    } catch (failure) {
      setStatus({ phase: 'error', message: failure instanceof Error ? failure.message : String(failure) })
      return
    }
    if (!response?.ok) {
      setStatus({ phase: 'error', message: response?.error?.message ?? '读取凭据状态失败' })
      return
    }
    const info = response.value?.[SEMANTIC_KEY_REF]
    setStatus({
      phase: 'ready',
      configured: info?.configured === true,
      writable: info?.writable !== false,
      source: typeof info?.source === 'string' ? info.source : null,
    })
  }, [remote])

  useEffect(() => { void load() }, [load])

  const refreshHostEnv = useCallback(async () => {
    try {
      await runAdminAction('refresh')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    }
  }, [])

  const save = useCallback(async () => {
    if (remote?.credentials === undefined || draft.trim() === '' || busy) return
    setBusy(true)
    setNotice(null)
    try {
      const response = await remote.credentials.set(SEMANTIC_KEY_REF, draft)
      if (!response?.ok) {
        setError(response?.error?.message ?? '保存 API Key 失败')
        return
      }
      setDraft('')
      setNotice('已配置，不可查看。')
      await load()
      // Clearing the spinner before the Host refresh keeps the card responsive
      // even when the MCP row restart takes a moment; the refresh still runs.
      setBusy(false)
      await refreshHostEnv()
      setNotice('已配置，不可查看。Host 已把新 key 同步到 mcp-coderag 行。')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setBusy(false)
    }
  }, [busy, draft, load, refreshHostEnv, remote])

  const remove = useCallback(async () => {
    if (remote?.credentials === undefined || busy) return
    setBusy(true)
    setNotice(null)
    try {
      const response = await remote.credentials.unset(SEMANTIC_KEY_REF)
      if (!response?.ok) {
        setError(response?.error?.message ?? '删除 API Key 失败')
        return
      }
      setConfirming(false)
      setNotice('已删除云端 API Key。')
      await load()
      setBusy(false)
      await refreshHostEnv()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setBusy(false)
    }
  }, [busy, load, refreshHostEnv, remote])

  const unavailable = status.phase === 'unavailable'
  const configured = status.phase === 'ready' && status.configured === true
  return (
    <Panel
      title="云端 API Key"
      description="只写入 DSH credentials 服务，不写 profile patch、不回读、不显示。Host 在同步 MCP 行与运维子进程时用它。"
    >
      <p style={styles.status}>
        状态：{status.phase === 'loading'
          ? '读取中…'
          : unavailable
            ? '当前 profile 没有 credentials 服务'
            : configured
              ? <span style={styles.ok}>已配置（不可查看）{status.source === undefined ? '' : `，来源 ${status.source}`}</span>
              : <span style={styles.bad}>未配置</span>}
      </p>
      <div style={styles.row}>
        <input
          style={styles.input}
          type="password"
          autoComplete="new-password"
          placeholder={configured ? '输入新 key 以轮换' : '粘贴云端 embedding API key'}
          value={draft}
          disabled={busy || unavailable}
          onChange={event => setDraft(event.target.value)}
        />
        <button type="button" style={styles.primary} disabled={busy || unavailable || draft.trim() === ''} onClick={save}>
          {busy ? '保存中…' : '保存'}
        </button>
        {configured ? (
          confirming
            ? (
              <span style={styles.row}>
                <span style={styles.hint}>确认删除已配置的 key？</span>
                <button type="button" style={styles.danger} disabled={busy} onClick={remove}>确认删除</button>
                <button type="button" style={styles.button} disabled={busy} onClick={() => setConfirming(false)}>取消</button>
              </span>
            )
            : <button type="button" style={styles.button} disabled={busy} onClick={() => setConfirming(true)}>删除</button>
        ) : null}
      </div>
      {notice === null ? null : <p style={{ ...styles.status, ...styles.ok }} role="status">{notice}</p>}
      {status.phase === 'error' ? <p style={{ ...styles.status, ...styles.bad }}>{status.message}</p> : null}
      <ErrorDialog error={error} onClose={() => setError(null)} />
    </Panel>
  )
}

/**
 * Embedding-backend card: probe either backend, and start a local Ollama when
 * it is not running. The health command is called with the saved settings.
 */
export function BackendPanel({ values }) {
  const [busy, setBusy] = useState(null)
  const [health, setHealth] = useState({})
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)

  const check = useCallback(async backend => {
    if (busy !== null) return
    setBusy(backend)
    setNotice(null)
    try {
      const value = await runAdminAction('health', { backend })
      setHealth(previous => ({ ...previous, [backend]: value }))
      if (value?.ok !== true) setError(value?.detail || `${backend} 后端不可用`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setBusy(null)
    }
  }, [busy])

  const startLocal = useCallback(async () => {
    if (busy !== null) return
    setBusy('start-local')
    setNotice(null)
    try {
      const value = await runAdminAction('start-local')
      setNotice(`本地后端已就绪：${value?.url ?? ''}`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setBusy(null)
    }
  }, [busy])

  const backendLine = backend => {
    const result = health[backend]
    if (result === undefined) return <p style={styles.status}>{backend === 'ollama' ? '本地 ollama' : '云端 openai'}：未检查</p>
    return (
      <p style={styles.status}>
        {backend === 'ollama' ? '本地 ollama' : '云端 openai'}：
        <span style={result.ok ? styles.ok : styles.bad}>{result.ok ? ' 连通' : ' 不可用'}</span>
        {result.url === undefined || result.url === '' ? '' : ` · ${result.url}`}
        {result.model === undefined || result.model === '' ? '' : ` · 模型 ${result.model_present ? `${result.model}（已就绪）` : `${result.model}（缺失）`}`}
        {result.detail === undefined || result.detail === '' ? '' : ` · ${result.detail}`}
      </p>
    )
  }

  return (
    <Panel
      title="语义后端"
      description={`当前保存值：后端 ${values?.semanticBackend || '默认 ollama'} · URL ${values?.semanticUrl || '默认'} · 模型 ${values?.semanticModel || '默认'}。检查使用已保存的配置。`}
    >
      <div style={styles.row}>
        {HEALTH_BACKENDS.map(backend => (
          <button
            key={backend}
            type="button"
            style={styles.button}
            disabled={busy !== null}
            onClick={() => { void check(backend) }}
          >
            {busy === backend ? '检查中…' : backend === 'ollama' ? '检查本地连通性' : '检查云端连通性'}
          </button>
        ))}
        <button type="button" style={styles.button} disabled={busy !== null} onClick={() => { void startLocal() }}>
          {busy === 'start-local' ? '启动中…' : '一键启动本地后端'}
        </button>
      </div>
      {backendLine('ollama')}
      {backendLine('openai')}
      {notice === null ? null : <p style={{ ...styles.status, ...styles.ok }} role="status">{notice}</p>}
      <ErrorDialog error={error} onClose={() => setError(null)} />
    </Panel>
  )
}

/**
 * Vector index card: status, incremental build, stop, and live progress.
 * `dirty` warns that the form has unsaved edits — actions use the saved root.
 */
export function VectorPanel({ dirty }) {
  const [state, setState] = useState({ phase: 'loading' })
  const [job, setJob] = useState(normalizeJob(undefined))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const previousStatus = useRef(job.status)

  const refresh = useCallback(async () => {
    setState({ phase: 'loading' })
    try {
      const raw = await fetchAdminState()
      setState({ phase: 'ready', value: normalizeAdminStatus(raw) })
    } catch (failure) {
      setState({ phase: 'error', message: failure instanceof Error ? failure.message : String(failure) })
    }
  }, [])

  const loadJob = useCallback(async () => {
    try {
      const next = normalizeJob(await fetchAdminJob())
      setJob(next)
      return next
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
      return undefined
    }
  }, [])

  useEffect(() => { void refresh(); void loadJob() }, [loadJob, refresh])

  // Poll the in-memory job while a build runs; a completed build refreshes the
  // state card so the pending counters settle without another click.
  useEffect(() => {
    if (!jobActive(job)) return
    const timer = setInterval(() => {
      void (async () => {
        const next = await loadJob()
        if (next !== undefined && !jobActive(next)) await refresh()
      })()
    }, 1000)
    return () => clearInterval(timer)
  }, [job, loadJob, refresh])

  useEffect(() => {
    if (previousStatus.current !== 'done' && job.status === 'done') void refresh()
    previousStatus.current = job.status
  }, [job.status, refresh])

  const act = useCallback(async action => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const value = await runAdminAction(action)
      if (action === 'stop') setJob(normalizeJob(value))
      else if (action === 'vectorize') setJob(normalizeJob(value))
      else await refresh()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setBusy(false)
    }
  }, [busy, refresh])

  const value = state.phase === 'ready' ? state.value : undefined
  const running = jobActive(job)
  const percent = jobPercent(job)
  const actionDisabled = dirty || busy
  const primaryLabel = running
    ? null
    : value?.vector_exists === true && value?.pending_chunks > 0
      ? '向量化增量'
      : '开始向量化'
  return (
    <Panel
      title="向量数据库"
      description="使用已保存的工作区根；索引与检查点都在 <root>/.coderag/ 下，停止不会删除检查点。"
    >
      {dirty ? <p style={{ ...styles.status, ...styles.bad }}>有未保存的设置改动，请先保存再操作向量库（避免用旧根跑任务）。</p> : null}
      {state.phase === 'loading' ? <p style={styles.hint}>正在读取向量库状态…</p> : null}
      {state.phase === 'error' ? <p style={{ ...styles.status, ...styles.bad }}>{state.message}</p> : null}
      {value === undefined ? null : (
        <div style={styles.grid}>
          <p style={styles.stat}>索引：{value.index_exists ? '存在' : '不存在'}</p>
          <p style={styles.stat}>向量库：{value.vector_exists ? '存在' : '不存在'}</p>
          <p style={styles.stat}>模型：{value.model ?? '—'}{value.dim === null ? '' : `（${value.dim} 维）`}</p>
          <p style={styles.stat}>总 chunk：{formatCount(value.total_chunks)}</p>
          <p style={styles.stat}>已向量化：{formatCount(value.vectorized_chunks)}</p>
          <p style={styles.stat}>待向量化：{formatCount(value.pending_chunks)}</p>
          <p style={styles.stat}>过期 chunk：{formatCount(value.stale_chunks)}</p>
          <p style={styles.stat}>检查点：{formatCount(value.checkpoint_vectors)}</p>
          <p style={styles.stat}>生成时间：{formatGeneratedAt(value.generated_at)}</p>
        </div>
      )}
      <div style={styles.row}>
        <button type="button" style={styles.button} disabled={busy} onClick={() => { void refresh(); void loadJob() }}>刷新</button>
        {running ? (
          <button type="button" style={styles.danger} disabled={busy} onClick={() => { void act('stop') }}>停止</button>
        ) : (
          <button type="button" style={styles.primary} disabled={actionDisabled} onClick={() => { void act('vectorize') }}>
            {primaryLabel}
          </button>
        )}
        <span style={styles.hint}>{jobLabel(job.status)}</span>
      </div>
      {running || job.embedded > 0 || job.status === 'done' ? (
        <div style={styles.column}>
          <div style={styles.bar}><div style={{ ...styles.barFill, width: `${percent ?? 5}%` }} /></div>
          <p style={styles.stat}>
            {formatCount(job.embedded)} / {formatCount(job.total)} 已处理
            {job.pending === null ? '' : ` · 待处理 ${formatCount(job.pending)}`}
            {percent === null ? '' : ` · ${percent}%`}
          </p>
        </div>
      ) : null}
      {job.error === null ? null : <p style={{ ...styles.status, ...styles.bad }}>{job.error.message}</p>}
      <ErrorDialog error={error} onClose={() => setError(null)} />
    </Panel>
  )
}

/**
 * The operations block: key, backends, vector database.
 * @param {{ remote?: object, values?: object, dirty?: boolean }} props - browser services and current draft facts.
 */
export function AdminPanels({ remote, values, dirty }) {
  return (
    <div style={styles.section}>
      <h3 style={styles.heading}>CodeRAG 运维</h3>
      <CredentialPanel remote={remote} />
      <BackendPanel values={values} />
      <VectorPanel dirty={dirty === true} />
    </div>
  )
}
