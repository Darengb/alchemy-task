// Pure discovery helpers (no React), shared by the app shell and tests.
export const pendingCount = (runs) => (runs || []).reduce((n, r) =>
  n + (typeof r.pending === 'number' ? r.pending : (r.proposals || []).filter((p) => p.state === 'pending' && !p.expired).length), 0)

// Tab badge from GET /badge: pending proposals, or 1 while discovery has never been set up (no runs and no
// stream configured), so the setup step reads as waiting work. An unknown state never adds a badge.
export const discoveryBadge = (badge) => {
  if (!badge) return 0
  if (badge.pending) return badge.pending
  return badge.has_runs === false && badge.streams_configured === false ? 1 : 0
}

// Wrap an async call so it is never sent again while an earlier one is still unanswered: a caller that
// arrives meanwhile gets the pending answer. Slow answers then cannot pile up behind the poll timer.
export function singleFlight(fn) {
  let pending = null
  return (...args) => {
    if (pending) return pending
    pending = Promise.resolve().then(() => fn(...args)).finally(() => { pending = null })
    return pending
  }
}

// Next run, read after "Next": "at 6:00 PM" (today), "tomorrow at 6:00 PM", "Thu at 6:00 PM" within a week,
// else "Nov 20 at 6:00 PM".
export function nextRunLabel(iso, now = new Date()) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const time = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((day(d) - day(now)) / 86400000)
  if (diff <= 0) return `at ${time}`
  if (diff === 1) return `tomorrow at ${time}`
  if (diff < 7) return `${d.toLocaleDateString(undefined, { weekday: 'short' })} at ${time}`
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} at ${time}`
}
