// Unit tests for the UI's date and Markdown helpers. Run: node --test ui/test/
import test from 'node:test'
import assert from 'node:assert/strict'
import * as D from '../src/lib/dates.js'
import { extractManaged, rebuildBody, splitSections, toggleLine, parseBlocks } from '../src/lib/markdown.js'

test('day math crosses month and year ends', () => {
  assert.equal(D.addDays('2026-12-31', 1), '2027-01-01')
  assert.equal(D.addDays('2026-03-01', -1), '2026-02-28')
  assert.equal(D.addMonths('2026-01-31', 1), '2026-02-28')
  assert.equal(D.startOfWeek('2026-11-08'), '2026-11-02') // Sunday belongs to the week starting Monday
  assert.equal(D.weekday('2026-11-09'), 0)
})

test('month grid covers whole weeks, Monday first', () => {
  const g = D.monthGrid('2026-11-15')
  assert.equal(g[0][0], '2026-10-26')
  assert.ok(g.every((w) => w.length === 7))
  assert.equal(g.at(-1)[6], '2026-12-06')
})

test('relative day labels', () => {
  assert.equal(D.relativeDay('2026-11-09', '2026-11-09'), 'Today')
  assert.equal(D.relativeDay('2026-11-10', '2026-11-09'), 'Tomorrow')
  assert.equal(D.relativeDay('2026-11-08', '2026-11-09'), 'Yesterday')
  assert.equal(D.relativeDay('2026-11-12', '2026-11-09'), 'Thursday')
  assert.equal(D.nextWeekday('2026-11-09', 0), '2026-11-16') // next Monday from a Monday is a week out
})

test('task date is scheduled, else due', () => {
  assert.equal(D.taskDate({ scheduled: '2026-11-10', due: '2026-11-12' }), '2026-11-10')
  assert.equal(D.taskDate({ due: '2026-11-12' }), '2026-11-12')
})

const BODY = `<!-- task-current-state:start -->
State text
<!-- task-current-state:end -->

## Notes

Some notes.

## Subtasks

- [ ] one
- [x] two

## Log

- 2026-11-08: Created.

<!-- task-research-dossier:start -->
## Research

Findings.
<!-- task-research-dossier:end -->
`

test('sections keep original line numbers so checkbox toggles hit the right line', () => {
  const { sections, managed } = splitSections(BODY)
  assert.deepEqual(managed.map((m) => m.name), ['task-current-state', 'task-research-dossier'])
  const sub = sections.find((s) => s.title === 'Subtasks')
  const list = parseBlocks(sub.text).find((b) => b.type === 'list')
  const first = list.items[0]
  const toggled = toggleLine(BODY, sub.start + first.line, true)
  assert.match(toggled, /- \[x\] one/)
  assert.equal(toggled.split('\n').length, BODY.split('\n').length)
  assert.ok(sections.find((s) => s.title === 'Log').folded)
})

test('editor round trip keeps managed blocks verbatim and in place', () => {
  const { editable, top, bottom } = extractManaged(BODY)
  assert.ok(!editable.includes('task-research-dossier') && !editable.includes('State text'))
  assert.equal(top.length, 1)
  assert.equal(bottom.length, 1)
  const rebuilt = rebuildBody(editable.replace('Some notes.', 'Edited notes.'), top, bottom)
  assert.ok(rebuilt.indexOf('task-current-state:start') < rebuilt.indexOf('Edited notes.'))
  assert.ok(rebuilt.indexOf('Edited notes.') < rebuilt.indexOf('task-research-dossier:start'))
  assert.ok(rebuilt.includes('Findings.'))
})

test('tables and fenced code parse', () => {
  const blocks = parseBlocks('| a | b |\n|---|---|\n| 1 | 2 |\n\n```\ncode\n```')
  assert.equal(blocks[0].type, 'table')
  assert.deepEqual(blocks[0].rows, [['1', '2']])
  assert.equal(blocks[1].type, 'code')
})
