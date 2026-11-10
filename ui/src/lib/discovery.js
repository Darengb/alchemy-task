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
