// Calendar-day math on 'YYYY-MM-DD' strings. Days are plain dates (no time zone): the backend
// tells us what "today" is in the user's time zone, and every comparison is a string compare.

const pad = (n) => String(n).padStart(2, '0')

export function toISO(d) {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
}

export function parseISO(s) {
  const [y, m, d] = String(s).split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

export function addDays(s, n) {
  const d = parseISO(s)
  d.setUTCDate(d.getUTCDate() + n)
  return toISO(d)
}

export function addMonths(s, n) {
  const d = parseISO(s)
  const day = d.getUTCDate()
  d.setUTCDate(1)
  d.setUTCMonth(d.getUTCMonth() + n)
  const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()
  d.setUTCDate(Math.min(day, last))
  return toISO(d)
}

export const weekday = (s) => (parseISO(s).getUTCDay() + 6) % 7 // Monday = 0

export function startOfWeek(s) {
  return addDays(s, -weekday(s))
}

export function startOfMonth(s) {
  return s.slice(0, 8) + '01'
}

export function endOfMonth(s) {
  const d = parseISO(startOfMonth(s))
  return toISO(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)))
}

export function daysBetween(a, b) {
  return Math.round((parseISO(b) - parseISO(a)) / 86400000)
}

export function range(start, end) {
  const out = []
  for (let d = start; d <= end; d = addDays(d, 1)) out.push(d)
  return out
}

/** The 6×7 (or 5×7) grid of days covering a month, weeks starting Monday. */
export function monthGrid(s) {
  const first = startOfWeek(startOfMonth(s))
  const last = addDays(startOfWeek(endOfMonth(s)), 6)
  const days = range(first, last)
  const weeks = []
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7))
  return weeks
}

const fmt = (s, opts) => parseISO(s).toLocaleDateString(undefined, { timeZone: 'UTC', ...opts })

export const dayName = (s, style = 'short') => fmt(s, { weekday: style })
export const monthName = (s, style = 'long') => fmt(s, { month: style })
export const dayNum = (s) => parseISO(s).getUTCDate()

export function longDate(s) {
  return fmt(s, { weekday: 'long', month: 'long', day: 'numeric' })
}

export function shortDate(s, today) {
  const sameYear = !today || s.slice(0, 4) === today.slice(0, 4)
  return fmt(s, { weekday: 'short', month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) })
}

/** "Today", "Tomorrow", "Yesterday", a weekday within the coming week, or a short date. */
export function relativeDay(s, today) {
  if (!s) return ''
  const diff = daysBetween(today, s)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Tomorrow'
  if (diff === -1) return 'Yesterday'
  if (diff > 1 && diff < 7) return dayName(s, 'long')
  return shortDate(s, today)
}

export function nextWeekday(today, target) { // target: 0 = Monday
  const diff = (target - weekday(today) + 7) % 7 || 7
  return addDays(today, diff)
}

export function periodLabel(view, anchor, today) {
  if (view === 'month') {
    return fmt(anchor, { month: 'long', ...(anchor.slice(0, 4) !== today.slice(0, 4) ? { year: 'numeric' } : {}) })
  }
  if (view === 'week') {
    const a = startOfWeek(anchor)
    const b = addDays(a, 6)
    const sameMonth = a.slice(0, 7) === b.slice(0, 7)
    const left = fmt(a, { month: 'short', day: 'numeric' })
    const right = sameMonth ? String(dayNum(b)) : fmt(b, { month: 'short', day: 'numeric' })
    return `${left} – ${right}`
  }
  return relativeDay(anchor, today) === 'Today' ? 'Today' : fmt(anchor, { weekday: 'long', month: 'short', day: 'numeric' })
}

/** The date a task sits on: its scheduled date, else its due date (the plugin's overdue rule). */
export const taskDate = (t) => t.scheduled || t.due || null
