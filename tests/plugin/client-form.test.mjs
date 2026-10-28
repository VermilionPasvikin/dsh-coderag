/**
 * Behavior tests for the browser form's design-time helpers: the draft the
 * inputs hold, the JSON values submitted to the Host, and the write set.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { FIELDS } from '../../src/plugin/shared/settings.js'
import { buildSetOps, draftKey, toDraft, toValue } from '../../src/plugin/shared/client-form.js'

const ACCEPTED = {
  root: '/workspace',
  maxFiles: 100,
  maxFileBytes: 0,
  maxTokens: 5000,
  extraExtensions: '.mxml',
  semantic: true,
  semanticBackend: 'ollama',
  semanticUrl: 'http://127.0.0.1:11434',
  semanticModel: 'bge-m3',
  semanticTimeout: 0,
  semanticBatch: 0,
  semanticMaxChunks: 50000,
  semanticAllowRemote: true,
}

test('a draft strings every number and keeps the switches boolean', () => {
  const draft = toDraft(ACCEPTED)
  assert.equal(draft.maxFiles, '100')
  assert.equal(draft.maxFileBytes, '0')
  assert.equal(draft.maxTokens, '5000')
  assert.equal(draft.semanticMaxChunks, '50000')
  assert.equal(draft.semantic, true)
  assert.equal(draft.semanticAllowRemote, true)
  assert.equal(draft.root, '/workspace')
  assert.deepEqual(Object.keys(draft), FIELDS.map(field => field.key))
  assert.deepEqual(toDraft(undefined), toDraft({
    root: '', maxFiles: 0, maxFileBytes: 0, maxTokens: 0, extraExtensions: '', semantic: false,
    semanticBackend: '', semanticUrl: '', semanticModel: '', semanticTimeout: 0, semanticBatch: 0,
    semanticMaxChunks: 0, semanticAllowRemote: false,
  }))
})

test('input text converts to the JSON types the Config schema accepts', () => {
  const field = key => FIELDS.find(candidate => candidate.key === key)
  assert.equal(toValue(field('maxFiles'), '12'), 12)
  assert.equal(toValue(field('maxFiles'), ''), 0)
  assert.equal(toValue(field('maxFiles'), '0'), 0)
  assert.equal(toValue(field('maxFiles'), '1.9'), 1)
  assert.equal(toValue(field('root'), ' /workspace '), ' /workspace ')
  assert.equal(toValue(field('semantic'), true), true)
  assert.equal(toValue(field('semantic'), 'false'), false)
})

test('draftKey changes exactly when an input changes', () => {
  const draft = toDraft(ACCEPTED)
  assert.equal(draftKey({ ...draft }), draftKey(draft))
  assert.notEqual(draftKey({ ...draft, maxFiles: '101' }), draftKey(draft))
})

test('a save writes every field so bootstrap defaults are not lost on reload', () => {
  const draft = toDraft(ACCEPTED)
  const ops = buildSetOps(draft)
  assert.deepEqual(ops.map(op => op.path[0]), FIELDS.map(field => field.key))
  assert.equal(ops.length, 13)
  assert.equal(ops.every(op => op.op === 'set'), true)
  assert.deepEqual(ops.find(op => op.path[0] === 'semanticBackend').value, 'ollama')
  assert.deepEqual(ops.find(op => op.path[0] === 'semantic').value, true)
  assert.deepEqual(ops.find(op => op.path[0] === 'maxFiles').value, 100)
  assert.deepEqual(ops.find(op => op.path[0] === 'maxTokens').value, 5000)
  assert.deepEqual(ops.find(op => op.path[0] === 'semanticMaxChunks').value, 50000)
  assert.deepEqual(ops.find(op => op.path[0] === 'semanticAllowRemote').value, true)
})
