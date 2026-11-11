// Short proposal fields, same rule as core/digest_text.py. Research writes authored 1 to 2 sentence
// digest_* fields; older bundles fall back to the first whole sentence of the long field. No mid-sentence cuts.
export const DIGEST_FIELDS = {
  digest_current_state: 'current_understanding',
  digest_next_action: 'substantive_next_action',
  digest_addition: 'new_information',
}

// A sentence ends at . ! or ? (plus closing quotes/brackets) before whitespace and a capital, digit or
// opening quote. URLs hold no whitespace, so the split never lands inside one.
const SENTENCE_END = /[.!?]["')\]]*(?=\s+["'(\[]?[A-Z0-9])/

export function firstSentence(text) {
  const flat = String(text ?? '').split(/\s+/).filter(Boolean).join(' ')
  const m = SENTENCE_END.exec(flat)
  return m ? flat.slice(0, m.index + m[0].length) : flat
}

export function digestField(p, key) {
  const authored = String(p?.[key] ?? '').split(/\s+/).filter(Boolean).join(' ')
  if (authored) return authored
  let long = p?.[DIGEST_FIELDS[key]]
  if (Array.isArray(long)) long = long.find((x) => String(x ?? '').trim()) || ''
  return firstSentence(long)
}

// The full research sections behind the "Full research" disclosure; empty when the short text already says it all.
export function fullResearch(p) {
  const additions = [].concat(p?.new_information || []).filter(Boolean)
  const out = []
  if (p?.current_understanding) out.push({ label: 'Current state', text: p.current_understanding })
  if (p?.substantive_next_action) out.push({ label: 'Next action', text: p.substantive_next_action })
  if (additions.length) out.push({ label: 'New information', items: additions })
  const shown = [digestField(p, 'digest_current_state'), digestField(p, 'digest_next_action'), digestField(p, 'digest_addition')]
  const same = out.every((s) => s.items ? s.items.length === 1 && shown.includes(String(s.items[0]).trim()) : shown.includes(String(s.text).split(/\s+/).join(' ')))
  return same ? [] : out
}
