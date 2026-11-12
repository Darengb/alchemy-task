// Progress of a running discovery stream, from the /settings payload's `progress`
// ({stage, done, total, started_at}). Pure, so the card and tests share it.

// { label, fraction } where fraction is null for an indeterminate bar.
export function runProgressLabel(progress) {
  const p = progress || {}
  const done = Math.max(0, Number(p.done) || 0)
  const total = Math.max(0, Number(p.total) || 0)
  if (p.stage === 'research' && total > 0) {
    const current = Math.min(total, done + 1)
    return { label: `Researching ${current} of ${total}`, fraction: Math.min(1, done / total) }
  }
  if (p.stage === 'digest') return { label: 'Writing the digest…', fraction: 0.95 }
  return { label: 'Reading sources…', fraction: null }
}

// "N min" since the run started, or '' when the start is unknown.
export function elapsedLabel(startedAt, now = Date.now()) {
  if (!startedAt) return ''
  const t = new Date(startedAt).getTime()
  if (Number.isNaN(t)) return ''
  const min = Math.max(0, Math.floor((now - t) / 60000))
  return min < 1 ? 'Under 1 min' : `${min} min`
}
