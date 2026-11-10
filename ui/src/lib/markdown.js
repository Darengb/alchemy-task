// A small Markdown renderer for task bodies: headings, paragraphs, lists (with task checkboxes),
// tables, code, quotes, links, bold, italic and inline code. It returns React elements (never HTML
// strings), so task content cannot inject markup. Checkbox lines carry their source line number so
// the UI can toggle exactly that line.
import React from 'react'

const h = React.createElement

const SAFE_URL = /^(https?:|mailto:|obsidian:|#)/i

function inline(text, keyBase = 'i') {
  const out = []
  let rest = String(text)
  let k = 0
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(\[\[[^\]]+\]\])|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/
  while (rest) {
    const m = rest.match(pattern)
    if (!m) { out.push(rest); break }
    if (m.index) out.push(rest.slice(0, m.index))
    const tok = m[0]
    const key = `${keyBase}-${k++}`
    if (m[1]) out.push(h('code', { key }, tok.slice(1, -1)))
    else if (m[2]) out.push(h('strong', { key }, inline(tok.slice(2, -2), key)))
    else if (m[3]) out.push(h('em', { key }, inline(tok.slice(1, -1), key)))
    else if (m[4]) {
      const inner = tok.slice(2, -2)
      const label = inner.includes('|') ? inner.split('|').pop() : inner.split('/').pop()
      out.push(h('span', { key, className: 'at-md-wikilink', title: inner.split('|')[0] }, label))
    } else if (m[5]) {
      const lm = tok.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/)
      const href = lm[2]
      out.push(SAFE_URL.test(href)
        ? h('a', { key, href, target: '_blank', rel: 'noreferrer noopener' }, inline(lm[1], key))
        : lm[1])
    } else if (m[6]) {
      out.push(h('a', { key, href: tok, target: '_blank', rel: 'noreferrer noopener' }, shortUrl(tok)))
    }
    rest = rest.slice(m.index + tok.length)
  }
  return out
}

// Apply special wrapping only to columns whose headers identify time values.
export function tableColumnClass(header) {
  const label = String(header).replace(/[*_`]/g, '').trim()
  return /^(time|duration|estimate|estimated time|time estimate)$/i.test(label) ? 'at-md-time' : undefined
}

function shortUrl(url) {
  try {
    const u = new URL(url)
    const p = u.pathname.length > 24 ? u.pathname.slice(0, 22) + '…' : u.pathname
    return u.host.replace(/^www\./, '') + (p === '/' ? '' : p)
  } catch { return url }
}

const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(\[( |x|X)\]\s+)?(.*)$/

/** Parse a Markdown body into blocks: { type, ... , line } where line is the 0-based source line. */
export function parseBlocks(src) {
  const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }
    const fence = line.match(/^\s*(```|~~~)/)
    if (fence) {
      const body = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++])
      i++
      blocks.push({ type: 'code', text: body.join('\n') })
      continue
    }
    const hm = line.match(/^(#{1,6})\s+(.*)$/)
    if (hm) { blocks.push({ type: 'heading', level: hm[1].length, text: hm[2].trim(), line: i }); i++; continue }
    if (/^\s*<!--.*-->\s*$/.test(line)) { i++; continue }
    if (/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(line)) { blocks.push({ type: 'hr' }); i++; continue }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      const head = cells(line)
      const rows = []
      i += 2
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]))
      blocks.push({ type: 'table', head, rows })
      continue
    }
    if (/^\s*>/.test(line)) {
      const body = []
      while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ''))
      blocks.push({ type: 'quote', text: body.join(' ') })
      continue
    }
    if (LIST_RE.test(line)) {
      const items = []
      while (i < lines.length && (LIST_RE.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        const m = lines[i].match(LIST_RE)
        if (m) {
          items.push({ indent: Math.floor(m[1].replace(/\t/g, '  ').length / 2), ordered: /\d/.test(m[2]),
                       checkbox: m[3] ? m[4].toLowerCase() === 'x' : null, text: m[5], line: i })
        } else {
          items[items.length - 1].text += ' ' + lines[i].trim()
        }
        i++
      }
      blocks.push({ type: 'list', items })
      continue
    }
    const para = []
    while (i < lines.length && lines[i].trim() && !LIST_RE.test(lines[i]) && !/^(#{1,6})\s/.test(lines[i])
           && !/^\s*(```|~~~|>|\|)/.test(lines[i])) para.push(lines[i++].trim())
    if (para.length) blocks.push({ type: 'p', text: para.join(' ') })
    else i++
  }
  return blocks
}

/** Render blocks. onToggle(line, checked) makes task checkboxes clickable. */
export function renderBlocks(blocks, { onToggle } = {}) {
  return blocks.map((b, n) => {
    const key = `b${n}`
    switch (b.type) {
      case 'heading':
        return h(`h${Math.min(6, b.level + 2)}`, { key, className: 'at-md-h' }, inline(b.text, key))
      case 'p':
        return h('p', { key }, inline(b.text, key))
      case 'hr':
        return h('hr', { key })
      case 'code':
        return h('pre', { key }, h('code', null, b.text))
      case 'quote':
        return h('blockquote', { key }, inline(b.text, key))
      case 'table':
        return h('div', { key, className: 'at-md-table' },
          h('table', null,
            h('thead', null, h('tr', null, b.head.map((c, j) => h('th', { key: j, className: tableColumnClass(c) }, inline(c, `${key}h${j}`))))),
            h('tbody', null, b.rows.map((r, j) => h('tr', { key: j }, r.map((c, x) => h('td', { key: x, className: tableColumnClass(b.head[x]) }, inline(c, `${key}r${j}${x}`))))))))
      case 'list': {
        const ordered = b.items[0] && b.items[0].ordered
        return h(ordered ? 'ol' : 'ul', { key, className: 'at-md-list' }, b.items.map((it, j) => {
          const style = it.indent ? { marginLeft: `${it.indent * 1.25}em` } : undefined
          if (it.checkbox === null) return h('li', { key: j, style }, inline(it.text, `${key}${j}`))
          return h('li', { key: j, style, className: 'at-md-check' + (it.checkbox ? ' is-done' : '') },
            h('label', null,
              h('input', { type: 'checkbox', checked: it.checkbox, disabled: !onToggle,
                           onChange: (e) => onToggle && onToggle(it.line, e.target.checked) }),
              h('span', null, inline(it.text, `${key}${j}`))))
        }))
      }
      default:
        return null
    }
  })
}

/** Set the checkbox on one source line. Returns the new body (unchanged if that line has no box). */
export function toggleLine(src, line, checked) {
  const lines = String(src).split('\n')
  const m = lines[line] && lines[line].match(/^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\](.*)$/)
  if (!m) return src
  lines[line] = `${m[1]}[${checked ? 'x' : ' '}]${m[3]}`
  return lines.join('\n')
}

// ------------------------------------------------------------------ sections

const START_RE = /^\s*<!--\s*([\w-]+):start\s*-->\s*$/
const END_RE = /^\s*<!--\s*([\w-]+):end\s*-->\s*$/

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
    let j = i + 1
    while (j < lines.length && !(END_RE.test(lines[j]) && lines[j].match(END_RE)[1] === m[1])) j++
    if (j >= lines.length) continue // unterminated: leave it visible
    managed.push({ name: m[1], text: lines.slice(i + 1, j).join('\n').trim() })
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
  if (/dossier|research/i.test(name)) return 'Research'
  if (/state/i.test(name)) return 'Current state'
  return name.replace(/[-_]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

/** Split a body into the text people edit and the managed blocks Hermes owns (kept verbatim).
 *  Blocks before any other content stay on top; the rest go back at the end, in order. */
export function extractManaged(body) {
  const lines = String(body || '').replace(/\r\n?/g, '\n').split('\n')
  const keep = []
  const top = []
  const bottom = []
  let seenContent = false
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(START_RE)
    if (m) {
      let j = i + 1
      while (j < lines.length && !(END_RE.test(lines[j]) && lines[j].match(END_RE)[1] === m[1])) j++
      if (j < lines.length) {
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
