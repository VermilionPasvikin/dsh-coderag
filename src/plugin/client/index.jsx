/**
 * dsh-coderag — browser half of the native settings page.
 *
 * Registers three contributions that render the same form:
 *
 * - `settings.section` (`coderag`, label `CodeRAG`): the primary entry point —
 *   Settings → CodeRAG shows the parameters directly, without the plugin README.
 * - `plugins.row.config` (`dsh-coderag#coderag`): the row-level Configure page;
 *   DSH hands the form in as an owner prop.
 * - `plugins.bundle.config` (`dsh-coderag`): the bundle detail page, as a
 *   secondary entry point below the README.
 *
 * The two non-row slots pass no form, so those components read the Host-owned
 * form themselves through `ctx.configForms.get('coderag')` and subscribe with
 * `useSyncExternalStore`.
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
  BUNDLE_NAME,
  DEFAULT_VALUES,
  FIELDS,
  GROUPS,
  ROW_CONFIG_KEY,
  validateValues,
} from '../shared/settings.js'
import { buildSetOps, draftKey, toDraft } from '../shared/client-form.js'

/** Browser services used by this plugin. */
export const inject = ['slots', 'configForms']

const { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } = React

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
  header: { display: 'flex', flexDirection: 'column', gap: '4px' },
  title: { margin: 0, fontSize: '15px', fontWeight: 600 },
  group: {
    border: '1px solid var(--dsw-alias-border-l2, #d0d7de)',
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
    border: '1px solid var(--dsw-alias-border-l2, #d0d7de)',
    background: 'var(--dsw-alias-bg-base, #ffffff)',
    color: 'var(--dsw-alias-label-primary, #1f2328)',
    fontSize: '13px',
  },
  hint: { margin: 0, fontSize: '12px', opacity: 0.72 },
  error: { margin: 0, fontSize: '12px', color: 'var(--dsw-alias-state-error-primary, #cf222e)' },
  actions: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' },
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
      <div style={styles.header}>
        <h3 style={styles.title}>CodeRAG 参数设置</h3>
        <p style={styles.description}>
          保存后同步到 mcp-coderag 行；也可在 设置 → CodeRAG、Plugins → dsh-coderag，或该行的“配置”里打开。
        </p>
      </div>
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
        {notice?.kind === 'saved' ? <span style={styles.hint} role="status">已保存，MCP 已按新环境热重载</span> : null}
        {notice?.kind === 'reset' ? <span style={styles.hint} role="status">已恢复默认值，点击保存生效。</span> : null}
        {notice?.kind === 'failed' ? <span style={styles.error} role="alert">{notice.message}</span> : null}
      </div>
      <p style={styles.hint}>
        保存会写入当前 profile 的 cordis.patch.yml，并把纳管的 CODERAG_* 环境变量同步到 mcp-coderag 行；
        只有 CODERAG_SEMANTIC_API_KEY 不在此页出现（请按 README 走环境变量或本机 profile）。
      </p>
    </div>
  )
}

/** One-line row description for `view: 'summary'`. */
function SettingsSummary() {
  return <span>CodeRAG：索引工作区、文件上限、扩展名与可选语义检索；打开配置后保存即可同步到 MCP 行。</span>
}

/**
 * Form page for slots that supply no form (the bundle page and the Settings
 * section): read the Host-owned `coderag` namespace through the shared
 * `configForms` service and re-render on every settings snapshot change.
 * @param {{ configForms: { get(id: string): { getSnapshot: Function, subscribe: Function, mutate: Function } } }} props
 */
function ConfigFormPage({ configForms }) {
  const form = useMemo(() => configForms.get('coderag'), [configForms])
  const subscribe = useCallback(listener => form.subscribe(listener), [form])
  const getSnapshot = useCallback(() => form.getSnapshot(), [form])
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  const mutate = useCallback((ops, revision) => form.mutate(ops, revision), [form])
  const pageForm = useMemo(() => ({ state: snapshot, mutate }), [snapshot, mutate])
  return <SettingsPage form={pageForm} />
}

/**
 * Register the three configuration surfaces.
 * @param {import('@deepseek-ai/cordis').Context} ctx - browser plugin context.
 */
export function apply(ctx) {
  const configForms = ctx.configForms ?? ctx.get('configForms')
  ctx.slots.inject('settings.section', () => ctx.slots.register(
    {
      name: 'settings.section',
      id: 'coderag',
      order: 30,
      label: () => 'CodeRAG',
    },
    () => <ConfigFormPage configForms={configForms} />,
  ))
  ctx.slots.inject('plugins.row.config', () => ctx.slots.register(
    { name: 'plugins.row.config', key: ROW_CONFIG_KEY },
    props => (props?.view === 'summary'
      ? <SettingsSummary />
      : <SettingsPage form={props?.form} />),
  ))
  ctx.slots.inject('plugins.bundle.config', () => ctx.slots.register(
    { name: 'plugins.bundle.config', key: BUNDLE_NAME },
    props => (props?.view === 'summary'
      ? <SettingsSummary />
      : <ConfigFormPage configForms={configForms} />),
  ))
}
