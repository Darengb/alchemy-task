import test from 'node:test'
import assert from 'node:assert/strict'
import { elapsedLabel, runProgressLabel } from '../src/lib/runProgress.js'

test('each stage has its own label and bar', () => {
  assert.deepEqual(runProgressLabel({ stage: 'sources', done: 0, total: 0 }), { label: 'Reading sources…', fraction: null })
  assert.deepEqual(runProgressLabel({ stage: 'research', done: 8, total: 16 }), { label: 'Researching 9 of 16', fraction: 0.5 })
  assert.deepEqual(runProgressLabel({ stage: 'digest', done: 16, total: 16 }), { label: 'Writing the digest…', fraction: 0.95 })
})

test('missing or odd progress reads as the first stage, and the count never passes the total', () => {
  assert.equal(runProgressLabel(null).label, 'Reading sources…')
  assert.equal(runProgressLabel({ stage: 'research', done: 0, total: 0 }).fraction, null)
  assert.equal(runProgressLabel({ stage: 'research', done: 16, total: 16 }).label, 'Researching 16 of 16')
})

test('elapsed minutes since the run started', () => {
  const start = '2026-11-11T15:00:00Z'
  const at = (m) => new Date(start).getTime() + m * 60000
  assert.equal(elapsedLabel(start, at(0.5)), 'Under 1 min')
  assert.equal(elapsedLabel(start, at(12.9)), '12 min')
  assert.equal(elapsedLabel(null), '')
  assert.equal(elapsedLabel('not a date'), '')
})
