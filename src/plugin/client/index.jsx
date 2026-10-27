/**
 * dsh-coderag — browser half of the native settings page.
 *
 * Registers one `plugins.row.config` entry for the `coderag` Loader row. DSH
 * hands the entry the Host-owned form (`form.state` snapshot + `form.mutate`
 * write queue); this module renders the grouped form, validates the draft in
 * the browser, and submits one `set` operation per field.
 *
 * Every write goes through `form.mutate`, so the Host validates it against the
 * plugin Config, persists the profile patch, and delivers a volatile-only
 * update to the Host half — which maps it onto the MCP row's environment.
 *
 * Not responsible for: reading the settings namespace, persistence, or the MCP
 * row (see docs/settings-ui-plan.md).
 */

import * as React from 'react'
import {
  DEFAULT_VALUES,
  FIELDS,
  GROUPS,
  ROW_CONFIG_KEY,
  validateValues,
} from '../shared/settings.js'
import { buildSetOps, draftKey, toDraft } from '../shared/client-form.js'

/** Browser services used by this plugin. */
export const inject = ['slots']

const { useCallback, useEffect, useMemo, useRef, useState } = React

/** How long the saved confirmation stays visible. */
const SAVED_NOTICE_MS = 4000

/** Inline styles: the bundle must not depend on a CSS build pipeline. */
const styles = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    color: 'var(--dsw-alias-label-primary, #1f2328)',
    fontSize: '13px',
    lineHeight: 1.5,
  },
  group: {
    border: '1px solid var(--dsw-alias-border-secondary, #d0d7de)',
    borderRadius: '8px',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    margin: 0,
  },
  legend: { fontWeight: 600, padding: '0 4px' },
  description: { margin: 0, opacity: 0.75 },
  field: { display: 'flex', flexDirection: 'column', gap: '4px' },
  labelRow: { display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 500 },
  control: {
    boxSizing: 'border-box',
    width: '100%',
    padding: '6px 8px',
    borderRadius: '6px',
    border: '1px solid var(--dsw-alias-border-secondary, #d0d7de)',
    background: 'var(--dsw-alias-bg-primary, #ffffff)',
    color: 'inherit',
    fontSize: '13px',
  },
  hint: { margin: 0, fontSize: '12px', opacity: 0.72 },
  error: { margin: 0, fontSize: '12px', color: 'var(--dsw-alias-label-danger, #cf222e)' },
  actions: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' },
  button: {
    padding: '6px 14px',
    borderRadius: '6px',
    border: '1px solid var(--dsw-alias-border-secondary, #d0d7de)',
    background: 'var(--dsw-alias-bg-primary, #ffffff)',
    color: 'inherit',
    fontSize: '13px',
    cursor: 'pointer',
  },
  primary: {
    padding: '6px 14px',
    borderRadius: '6px',
    border: '1px solid transparent',
    background: 'var(--dsw-alias-brand-primary, #0969da)',
    color: '#ffffff',
    fontSize: '13px',
    cursor: 'pointer',
  },
  notice: { margin: 0, fontSize: '12px' },
  checkboxRow: { display: 'flex', alignItems: 'center', gap: '8px' },
}

/** One labelled form control. */
function Field({ field, draft, disabled, errors, onChange }) {
  const error = errors.find(item => item.field === field.key)
  const id = `coderag-setting-${field.key}`
  const common = {
    id,
    style: styles.control,
    disabled,
    'aria-invalid': error !== undefined,
  }
  if (field.kind === 'boolean') {
    return (
      <div style={styles.field}>
        <div style={styles.checkboxRow}>
          <input
            id={id}
            type="checkbox"
            checked={draft[field.key] === true}
            disabled={disabled}
            onChange={event => onChange(field.key, event.target.checked)}
          />
          <label htmlFor={id}>{field.label}</label>
        </div>
        <p style={styles.hint}>{field.hint}</p>
        {error === undefined ? null : <p style={styles.error} role="alert">{error.message}</p>}
      </div>
    )
  }
  return (
    <div style={styles.field}>
      <label style={styles.labelRow} htmlFor={id}>{field.label}</label>
      {field.kind === 'select' ? (
        <select {...common} value={String(draft[field.key] ?? '')} onChange={event => onChange(field.key, event.target.value)}>
          {field.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      ) : (
        <input
          {...common}
          type="text"
          inputMode={field.kind === 'integer' ? 'numeric' : undefined}
          placeholder={field.placeholder}
          value={String(draft[field.key] ?? '')}
          onChange={event => onChange(field.key, event.target.value)}
        />
      )}
      <p style={styles.hint}>{field.hint}</p>
      {error === undefined ? null : <p style={styles.error} role="alert">{error.message}</p>}
    </div>
  )
}

/**
 * The page rendered for `view: 'page'`.
 * @param {{ form: { state: object, mutate: Function } | undefined }} props - slot owner props.
 */
function SettingsPage({ form }) {
  const state = form?.state
  const acceptedDraft = useMemo(() => toDraft(state?.value ?? DEFAULT_VALUES), [state?.value])
  const baseDraft = useMemo(() => toDraft(state?.base ?? DEFAULT_VALUES), [state?.base])
  const [draft, setDraft] = useState(acceptedDraft)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [showErrors, setShowErrors] = useState(false)
  const dirtyRef = useRef(false)
  const acceptNextEcho = useRef(false)
  const noticeTimer = useRef(undefined)

  dirtyRef.current = draftKey(draft) !== draftKey(acceptedDraft)

  // A Host echo (save, another editor, project reload) replaces the accepted
  // values; follow it unless this form holds unsaved edits. A successful save
  // opts the next echo in even while the draft still differs from the old view.
  useEffect(() => {
    if (acceptNextEcho.current || !dirtyRef.current) {
      acceptNextEcho.current = false
      setDraft(acceptedDraft)
    }
  }, [acceptedDraft])

  useEffect(() => () => {
    clearTimeout(noticeTimer.current)
  }, [])

  const showNotice = useCallback(next => {
    setNotice(next)
    clearTimeout(noticeTimer.current)
    if (next?.kind === 'saved') {
      noticeTimer.current = setTimeout(() => setNotice(null), SAVED_NOTICE_MS)
    }
  }, [])

  const onChange = useCallback((key, value) => {
    setDraft(previous => ({ ...previous, [key]: value }))
    setShowErrors(false)
  }, [])

  const errors = useMemo(() => validateValues(draft), [draft])
  const errorList = showErrors || dirtyRef.current ? errors : []
  const status = state?.status ?? 'loading'
  const writable = state?.writable !== false
  const disabled = !writable || saving || status !== 'ready'
  const dirty = draftKey(draft) !== draftKey(acceptedDraft)

  const onSave = useCallback(async () => {
    if (form === undefined) return
    setShowErrors(true)
    const validation = validateValues(draft)
    if (validation.length > 0) return
    setSaving(true)
    setNotice(null)
    try {
      const acceptedByHost = await form.mutate(buildSetOps(draft), state?.revision)
      if (acceptedByHost) {
        acceptNextEcho.current = true
        showNotice({ kind: 'saved' })
      } else {
        showNotice({ kind: 'failed', message: '宿主拒绝了这次修改：请检查取值，或配置已被其它地方改写。' })
      }
    } catch (error) {
      showNotice({ kind: 'failed', message: `保存失败：${error instanceof Error ? error.message : String(error)}` })
    } finally {
      setSaving(false)
    }
  }, [draft, form, showNotice, state?.revision])

  const onReset = useCallback(() => {
    setDraft(baseDraft)
    setShowErrors(false)
    showNotice({ kind: 'reset' })
  }, [baseDraft, showNotice])

  if (status === 'loading') return <p style={styles.hint}>正在读取 CodeRAG 设置…</p>
  if (status === 'unavailable') return <p style={styles.hint}>当前 profile 未提供 CodeRAG 设置（coderag 行未激活）。</p>

  return (
    <div style={styles.root}>
      {writable ? null : <p style={styles.notice}>当前 profile 是只读的，不能保存设置。</p>}
      {GROUPS.map(group => (
        <fieldset key={group.id} style={styles.group}>
          <legend style={styles.legend}>{group.title}</legend>
          <p style={styles.description}>{group.description}</p>
          {FIELDS.filter(field => field.group === group.id).map(field => (
            <Field
              key={field.key}
              field={field}
              draft={draft}
              disabled={disabled}
              errors={errorList}
              onChange={onChange}
            />
          ))}
        </fieldset>
      ))}
      <div style={styles.actions}>
        <button type="button" style={styles.primary} disabled={disabled} onClick={onSave}>
          {saving ? '保存中…' : '保存'}
        </button>
        <button type="button" style={styles.button} disabled={disabled} onClick={onReset}>
          恢复默认
        </button>
        {dirty ? <span style={styles.hint}>有未保存的修改</span> : null}
        {notice?.kind === 'saved' ? <span style={styles.hint} role="status">已保存，MCP 行将按新环境重启。</span> : null}
        {notice?.kind === 'reset' ? <span style={styles.hint} role="status">已恢复默认值，点击保存生效。</span> : null}
        {notice?.kind === 'failed' ? <span style={styles.error} role="alert">{notice.message}</span> : null}
      </div>
      <p style={styles.hint}>
        保存会写入当前 profile 的 cordis.patch.yml，并把纳管的 CODERAG_* 环境变量同步到 mcp-coderag 行；
        MAX_TOKENS / MAX_CHUNKS / ALLOW_REMOTE / API_KEY 不在此页管理。
      </p>
    </div>
  )
}

/** One-line row description for `view: 'summary'`. */
function SettingsSummary() {
  return <span>CodeRAG：索引工作区、文件上限、扩展名与可选语义检索；打开配置后保存即可同步到 MCP 行。</span>
}

/**
 * Register the row configuration page.
 * @param {import('@deepseek-ai/cordis').Context} ctx - browser plugin context.
 */
export function apply(ctx) {
  ctx.slots.inject('plugins.row.config', () => ctx.slots.register(
    { name: 'plugins.row.config', key: ROW_CONFIG_KEY },
    props => (props?.view === 'summary'
      ? <SettingsSummary />
      : <SettingsPage form={props?.form} />),
  ))
}
