// Short proposal fields: authored digest_* text first, else the first whole sentence. Run: node --test ui/test/
import test from 'node:test'
import assert from 'node:assert/strict'
import { firstSentence, digestField, fullResearch } from '../src/lib/digestText.js'

test('first sentence keeps the whole sentence and never splits a URL', () => {
  assert.equal(firstSentence('Ailsa asked about the film. Daren does not know.'), 'Ailsa asked about the film.')
  assert.equal(firstSentence('See https://x.example/a.b?c=1. Then reply.'), 'See https://x.example/a.b?c=1.')
  assert.equal(firstSentence('Version 2.5 ships soon'), 'Version 2.5 ships soon')
  assert.equal(firstSentence(''), '')
})

test('authored digest fields win over the long research', () => {
  const p = { digest_current_state: 'Short state.', current_understanding: 'Long one. Two.', new_information: ['First add. More.', 'Second'] }
  assert.equal(digestField(p, 'digest_current_state'), 'Short state.')
  assert.equal(digestField(p, 'digest_addition'), 'First add.')
  assert.equal(digestField({}, 'digest_next_action'), '')
})

test('full research lists long fields only when they say more', () => {
  const long = { current_understanding: 'A. B.', substantive_next_action: 'Do it.', new_information: ['X', 'Y'] }
  assert.deepEqual(fullResearch(long).map((s) => s.label), ['Current state', 'Next action', 'New information'])
  assert.deepEqual(fullResearch({ current_understanding: 'Only this.', substantive_next_action: 'Do it.' }), [])
})
