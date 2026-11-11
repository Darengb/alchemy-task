// Pure discovery helpers (no React), shared by the app shell and tests.
export const pendingCount = (runs) => (runs || []).reduce((n, r) =>
  n + (r.proposals || []).filter((p) => p.state === 'pending' && !p.expired).length, 0)

// Tab badge: pending proposals, or 1 while discovery has never been set up (runs loaded, none yet, and no
// stream configured), so the setup step reads as waiting work. Unknown stream state never adds a badge.
export const discoveryBadge = (runs, streams) => {
  const pending = pendingCount(runs)
  if (pending) return pending
  return Array.isArray(runs) && !runs.length && Array.isArray(streams) && !streams.length ? 1 : 0
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
