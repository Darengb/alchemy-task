// The research button at the top of a task's research section. Research workers only start inside an
// agent turn, so the button queues research; the server says whether the sweep starts now or later.

const BUSY = new Set(['pending', 'running', 'promoted'])
export const RESEARCHING = 'Hermes is researching this task. Findings will appear here.'

/** Label, disabled flag and status line for a research state. ``click`` is the button's local state:
 *  ``{phase: 'sending'}`` right after a click, ``{phase: 'done', message}`` once the server answered. */
export function researchButton(status, click = null) {
  const s = String(status || 'none').toLowerCase()
  if (click && click.phase === 'sending') return { label: 'Queued', disabled: true, note: null }
  const label = s === 'complete' ? 'Refresh research' : 'Start research'
  if (click && click.phase === 'done') return { label: 'Queued', disabled: true, note: click.message || null }
  if (BUSY.has(s)) return { label, disabled: true, note: RESEARCHING }
  return { label, disabled: false, note: null }
}

/** The plain message for the route's answer. */
export function researchStartedMessage(res) {
  if (res && typeof res.message === 'string' && res.message) return res.message
  if (res && res.starts === 'now') return 'Starting now'
  return `Queued, starts ${(res && res.starts) || 'within 30 minutes'}`
}
