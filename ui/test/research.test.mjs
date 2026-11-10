// Research button labels by research state. Run: node --test ui/test/
import test from 'node:test'
import assert from 'node:assert/strict'
import { researchButton, researchStartedMessage } from '../src/lib/research.js'

test('Start research when there is none, it was skipped or it failed', () => {
  for (const s of [undefined, null, '', 'none', 'skipped', 'failed', 'exhausted']) {
    const b = researchButton(s)
    assert.equal(b.label, 'Start research', String(s))
    assert.equal(b.disabled, false)
    assert.equal(b.note, null)
  }
})

test('Refresh research when it is complete', () => {
  assert.deepEqual(researchButton('complete'), { label: 'Refresh research', disabled: false, note: null })
})

test('pending or running shows the status line and a disabled button', () => {
  for (const s of ['pending', 'running', 'promoted']) {
    const b = researchButton(s)
    assert.equal(b.disabled, true, s)
    assert.match(b.note, /researching this task/)
  }
})

test('a click shows Queued at once, then the server message', () => {
  const b = researchButton('none', { phase: 'sending' })
  assert.equal(b.label, 'Queued')
  assert.equal(b.disabled, true)
  const after = researchButton('pending', { phase: 'done', message: 'Starting now' })
  assert.equal(after.disabled, true)
  assert.equal(after.note, 'Starting now')
  assert.equal(researchStartedMessage({ starts: 'now' }), 'Starting now')
  assert.equal(researchStartedMessage({ starts: 'within 30 minutes' }), 'Queued, starts within 30 minutes')
  assert.equal(researchStartedMessage({}), 'Queued, starts within 30 minutes')
})

test('the server message wins, so a paused or missing sweep job is never shown as Starting now', () => {
  const paused = { starts: 'when the research sweep job is resumed',
    message: 'Queued. Research starts when the research sweep job is resumed.' }
  assert.equal(researchStartedMessage(paused), paused.message)
  assert.equal(researchStartedMessage({ starts: 'when the research sweep job is resumed' }),
    'Queued, starts when the research sweep job is resumed')
})
