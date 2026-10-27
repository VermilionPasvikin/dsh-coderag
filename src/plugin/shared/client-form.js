/**
 * Draft-value rules for the browser settings form.
 *
 * React-free on purpose: the component imports these helpers, and the Node
 * tests exercise them directly. A "draft" is what the inputs hold — integers as
 * strings, the switch as a boolean — while the Host accepts typed JSON values.
 */

import { FIELDS, normalizeValues } from './settings.js'

/**
 * Turn accepted values into the string/boolean draft the inputs edit.
 * @param {Record<string, unknown>} values - accepted or schema-default values.
 * @returns {Record<string, string | boolean>} draft values for every field.
 */
export function toDraft(values) {
  const normalized = normalizeValues(values)
  const draft = {}
  for (const field of FIELDS) {
    draft[field.key] = field.kind === 'boolean' ? normalized[field.key] === true : String(normalized[field.key])
  }
  return draft
}

/**
 * Convert one input value into the JSON value submitted to the Host.
 * @param {{ key: string, kind: string }} field - field descriptor.
 * @param {unknown} raw - draft value.
 * @returns {unknown} typed value (string, boolean or non-negative integer).
 */
export function toValue(field, raw) {
  if (field.kind === 'boolean') return raw === true
  if (field.kind === 'integer') {
    const number = Math.floor(Number(raw))
    return Number.isFinite(number) && number > 0 ? number : 0
  }
  return String(raw ?? '')
}

/** Stable key for one draft, used to detect unsaved edits. */
export function draftKey(draft) {
  return JSON.stringify(FIELDS.map(field => [field.key, draft[field.key]]))
}

/**
 * Build the write operations for a save.
 * Every field is written, so the profile's id-targeted row keeps the values the
 * bundle's `!!js` defaults resolved to when the row was first saved.
 * @param {Record<string, unknown>} draft - current draft.
 * @returns {Array<{ op: 'set', path: string[], value: unknown }>} ordered operations.
 */
export function buildSetOps(draft) {
  return FIELDS.map(field => ({ op: 'set', path: [field.key], value: toValue(field, draft[field.key]) }))
}
