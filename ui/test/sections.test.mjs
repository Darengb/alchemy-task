// Managed blocks in a task body, including discovery dossiers whose markers carry an id. Run: node --test ui/test/
import test from 'node:test'
import assert from 'node:assert/strict'
import { splitSections, extractManaged, rebuildBody, managedTitle, groupManaged } from '../src/lib/sections.js'

const TASK_DOSSIER = '<!-- task-research-dossier:start -->\n### Research\nTask findings.\n<!-- task-research-dossier:end -->'
const DISC_A = '<!-- discovery-dossier:start dos-abc -->\nDiscovery A findings.\n<!-- discovery-dossier:end dos-abc -->'
const DISC_B = '<!-- discovery-dossier:start dos-b.2 -->\nDiscovery B findings.\n<!-- discovery-dossier:end dos-b.2 -->'
const body = `\n## Notes\n\nMy notes.\n\n## Log\n\n- 2026-11-10: made\n\n${TASK_DOSSIER}\n\n${DISC_A}\n\n${DISC_B}\n`

test('discovery dossiers with ids are lifted out of the body text', () => {
  const { sections, managed } = splitSections(body)
  assert.deepEqual(managed.map((m) => m.name), ['task-research-dossier', 'discovery-dossier', 'discovery-dossier'])
  assert.equal(managed[1].text, 'Discovery A findings.')
  for (const s of sections) assert.doesNotMatch(s.text, /discovery-dossier|Discovery A|Discovery B/)
})

test('all research blocks appear under one Research entry in body order', () => {
  assert.equal(managedTitle('discovery-dossier'), 'Research')
  assert.equal(managedTitle('task-research-dossier'), 'Research')
  const groups = groupManaged(splitSections(body).managed)
  assert.equal(groups.length, 1)
  assert.equal(groups[0].title, 'Research')
  const t = groups[0].text
  assert.ok(t.indexOf('Task findings') < t.indexOf('Discovery A') && t.indexOf('Discovery A') < t.indexOf('Discovery B'), t)
  const onlyDisc = groupManaged(splitSections(`## Notes\n\nx\n\n${DISC_A}\n`).managed)
  assert.deepEqual(onlyDisc.map((g) => g.title), ['Research'])
})

test('an end marker closes a block only when name and id match', () => {
  const mixed = '<!-- discovery-dossier:start dos-a -->\nA\n<!-- discovery-dossier:end dos-x -->\nstill A\n<!-- discovery-dossier:end dos-a -->\n'
  const { managed } = splitSections(mixed)
  assert.equal(managed.length, 1)
  assert.match(managed[0].text, /still A/)
  const open = '## Notes\n\n<!-- discovery-dossier:start dos-a -->\nunterminated\n<!-- discovery-dossier:end dos-b -->\n'
  assert.equal(splitSections(open).managed.length, 0)
})

test('editing the body keeps every dossier verbatim', () => {
  const parts = extractManaged(body)
  assert.doesNotMatch(parts.editable, /dossier|findings/)
  assert.deepEqual(parts.bottom, [TASK_DOSSIER, DISC_A, DISC_B])
  const edited = parts.editable.replace('My notes.', 'My edited notes.')
  const out = rebuildBody(edited, parts.top, parts.bottom)
  for (const block of [TASK_DOSSIER, DISC_A, DISC_B]) assert.ok(out.includes(block), block)
  assert.match(out, /My edited notes\./)
  // round trip with no edit is stable
  const again = extractManaged(out)
  assert.deepEqual(again.bottom, parts.bottom)
  assert.equal(again.editable, edited)
})

test('blocks with two ids (discovery context) round trip too', () => {
  const ctx = '<!-- discovery-context:start dos-a 3 -->\nctx\n<!-- discovery-context:end dos-a 3 -->'
  const parts = extractManaged(`## Notes\n\nx\n\n${ctx}\n`)
  assert.deepEqual(parts.bottom, [])
  assert.ok(parts.editable.includes(ctx))
})

test('a discovery context block inside Notes keeps its place through an edit; dossiers still lift out', () => {
  const ctx = '<!-- discovery-context:start dos-a sha256:ab12 -->\n### Discovery context\n\n- new fact\n<!-- discovery-context:end dos-a sha256:ab12 -->'
  const dossier = '<!-- discovery-dossier:start dos-a -->\nD\n<!-- discovery-dossier:end dos-a -->'
  const body = `\n## Notes\n\nmine\n\n${ctx}\n\n## Plan\n\n1. x\n\n## Log\n\n- 2026-11-10: made\n\n${dossier}\n`
  const parts = extractManaged(body)
  assert.deepEqual(parts.bottom, [dossier])
  const out = rebuildBody(parts.editable.replace('mine', 'mine edited'), parts.top, parts.bottom)
  const at = (s) => out.indexOf(s)
  assert.ok(at('mine edited') < at(ctx) && at(ctx) < at('## Plan') && at('## Plan') < at('## Log') && at('## Log') < at(dossier), out)
  // display still folds the context block out of the Notes text
  const { sections, managed } = splitSections(out)
  assert.ok(managed.some((m) => m.name === 'discovery-context'))
  assert.doesNotMatch(sections.find((x) => x.title === 'Notes').text, /discovery-context|new fact/)
})
