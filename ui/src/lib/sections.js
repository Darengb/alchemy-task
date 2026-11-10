// Task body sections and Hermes-managed blocks. Pure functions, no React, so node tests import them.

// Markers may carry ids after start/end, e.g. '<!-- discovery-dossier:start dos-abc -->'. An end marker closes
// a block only when both its name and its ids match the start marker.
const START_RE = /^\s*<!--\s*([\w-]+):start((?:\s+[\w.:-]+)*)\s*-->\s*$/
const END_RE = /^\s*<!--\s*([\w-]+):end((?:\s+[\w.:-]+)*)\s*-->\s*$/

const ids = (s) => String(s || '').trim().split(/\s+/).join(' ')

/** Index of the end marker closing the block that starts at line i (matching name and ids), or -1. */
function blockEnd(lines, i) {
  const m = lines[i].match(START_RE)
  if (!m) return -1
  for (let j = i + 1; j < lines.length; j++) {
    const e = lines[j].match(END_RE)
    if (e && e[1] === m[1] && ids(e[2]) === ids(m[2])) return j
  }
  return -1
}

/** Split a task body into display sections, keeping original line numbers so checkbox toggles edit
 *  the right line. Managed blocks (research dossier and similar) are lifted out and folded; the Log
 *  section is folded. Each section's text has managed lines blanked, so local line n is body line start+n. */
export function splitSections(body) {
  const lines = String(body || '').replace(/\r\n?/g, '\n').split('\n')
  const visible = lines.slice()
  const managed = []
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(START_RE)
    if (!m) continue
    const j = blockEnd(lines, i)
    if (j < 0) continue // unterminated: leave it visible
    managed.push({ name: m[1], id: ids(m[2]), text: lines.slice(i + 1, j).join('\n').trim() })
    for (let k = i; k <= j; k++) visible[k] = ''
    i = j
  }
  const sections = []
  let cur = { title: '', start: 0, lines: [] }
  visible.forEach((l, idx) => {
    const m = l.match(/^##\s+(.*)$/)
    if (m) {
      sections.push(cur)
      cur = { title: m[1].trim(), start: idx + 1, lines: [] }
    } else cur.lines.push(l)
  })
  sections.push(cur)
  return {
    sections: sections.filter((x) => x.title || x.lines.join('').trim()).map((x) => ({
      title: x.title, text: x.lines.join('\n'), start: x.start,
      folded: /^(log|history|activity)$/i.test(x.title),
    })),
    managed,
  }
}

export function managedTitle(name) {
  if (/dossier|research|discovery/i.test(name)) return 'Research'
  if (/state/i.test(name)) return 'Current state'
  return name.replace(/[-_]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

/** Split a body into the text people edit and the managed blocks Hermes owns (kept verbatim).
 *  Blocks before any other content stay on top. Dossier blocks after content go back at the end, in order;
 *  any other block inside a section (such as discovery context in Notes) stays in the editable text at its
 *  place, so an edit never moves it under a later section. */
export function extractManaged(body) {
  const lines = String(body || '').replace(/\r\n?/g, '\n').split('\n')
  const keep = []
  const top = []
  const bottom = []
  let seenContent = false
  for (let i = 0; i < lines.length; i++) {
    if (START_RE.test(lines[i])) {
      const j = blockEnd(lines, i)
      if (j >= 0 && (!seenContent || /-dossier$/.test(lines[i].match(START_RE)[1]))) {
        ;(seenContent ? bottom : top).push(lines.slice(i, j + 1).join('\n'))
        i = j
        continue
      }
    }
    if (lines[i].trim()) seenContent = true
    keep.push(lines[i])
  }
  const editable = keep.join('\n').replace(/\n{3,}/g, '\n\n').replace(/^\n+/, '').replace(/\s+$/, '') + '\n'
  return { editable, top, bottom }
}

export function rebuildBody(editable, top, bottom) {
  const parts = []
  if (top.length) parts.push(top.join('\n\n'))
  parts.push(String(editable).replace(/\s+$/, ''))
  if (bottom.length) parts.push(bottom.join('\n\n'))
  return '\n' + parts.filter((x) => x.trim()).join('\n\n') + '\n'
}

/** Managed blocks for display: every Research block (task research dossier and discovery dossiers) merged into
 *  one entry in body order, each other block kept as its own entry. */
export function groupManaged(managed) {
  const out = []
  let research = null
  for (const m of managed || []) {
    const title = managedTitle(m.name)
    if (title !== 'Research') { out.push({ title, text: m.text, names: [m.name] }); continue }
    if (!research) { research = { title, text: m.text, names: [m.name] }; out.push(research); continue }
    research.text = [research.text, m.text].filter((x) => x).join('\n\n---\n\n')
    research.names.push(m.name)
  }
  return out
}
