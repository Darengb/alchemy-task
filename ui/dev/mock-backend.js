// In-memory backend for the preview harness. Same routes and response shapes as
// dashboard/plugin_api.py (tasks, settings) and the discovery API, with a little latency.
import { addDays } from '../src/lib/dates.js'
import { demoData } from './demo-data.js'

const LATENCY = [120, 320]
const sleep = () => new Promise((r) => setTimeout(r, LATENCY[0] + Math.random() * (LATENCY[1] - LATENCY[0])))
const clone = (x) => JSON.parse(JSON.stringify(x))

function nyToday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  return parts
}

class HttpError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.body = JSON.stringify({ ok: false, error: { code, message } }) }
}

export function createMockBackend({ today = nyToday() } = {}) {
  const db = demoData(today)
  let rev = 1
  for (const t of db.tasks) t.revision = `r${rev++}`
  const find = (id) => {
    const t = db.tasks.find((x) => x.task_id === id)
    if (!t) throw new HttpError(404, 'not_found', 'Task not found')
    return t
  }
  const bump = (t) => { t.revision = `r${rev++}` }
  const row = (t) => { const { body, ...rest } = t; return clone({ ...rest, date: t.scheduled || t.due }) }
  const full = (t) => clone({ ...t, date: t.scheduled || t.due })
  const closed = (t) => t.status === 'done' || t.status === 'cancelled'
  const log = (t, msg) => { t.body = t.body.replace(/(## Log\n\n)/, `$1- ${today}: ${msg}\n`) }

  const routes = [
    ['GET', /^\/meta$/, () => ({ ok: true, today, areas: db.areas, default_area: db.settings.tasks.default_area, configured: true,
      streams: Object.fromEntries(db.settings.streams.map((s) => [s.name, s.areas])) })],
    ['GET', /^\/tasks$/, (q) => {
      const from = q.get('from'); const to = q.get('to') || from
      const done = q.get('include_done') === '1'
      const tasks = db.tasks.filter((t) => { const d = t.scheduled || t.due; return d && d >= from && d <= to && (done || !closed(t)) })
      return { ok: true, today, tasks: tasks.map(row) }
    }],
    ['GET', /^\/overdue$/, () => {
      const tasks = db.tasks.filter((t) => !closed(t) && (t.scheduled || t.due) && (t.scheduled || t.due) < today)
      return { ok: true, today, count: tasks.length, tasks: tasks.map(row) }
    }],
    ['GET', /^\/tasks\/([^/]+)$/, (q, [id]) => ({ ok: true, task: full(find(id)) })],
    ['PATCH', /^\/tasks\/([^/]+)$/, (q, [id], body) => {
      const t = find(id)
      if (body.expected_revision && body.expected_revision !== t.revision && (body.title || body.summary !== undefined)) {
        throw new HttpError(409, 'stale_revision', 'The task changed since it was read')
      }
      if (body.date) { t.scheduled = body.date; t.due = body.date; log(t, `Moved to ${body.date}.`) }
      if (body.keep_separate) { if (body.due) t.due = body.due; if (body.scheduled) t.scheduled = body.scheduled }
      for (const k of ['title', 'summary', 'priority', 'area', 'status']) if (body[k] !== undefined) t[k] = body[k]
      if (body.status === 'done') t.completed = today
      bump(t)
      return { ok: true, task: full(t) }
    }],
    ['POST', /^\/tasks\/([^/]+)\/complete$/, (q, [id]) => { const t = find(id); t.status = 'done'; t.completed = today; log(t, 'Marked done.'); bump(t); return { ok: true, task: full(t) } }],
    ['POST', /^\/tasks\/([^/]+)\/reopen$/, (q, [id]) => { const t = find(id); t.status = 'open'; t.completed = null; log(t, 'Reopened.'); bump(t); return { ok: true, task: full(t) } }],
    ['POST', /^\/tasks\/([^/]+)\/research$/, (q, [id]) => {
      const t = find(id)
      if (t.research === 'pending' || t.research === 'running') throw new HttpError(409, 'research_busy', 'Research is already queued or running')
      t.research = 'pending'; log(t, 'Research requested in the Tasks view.'); bump(t)
      return { ok: true, queued: true, starts: 'within 30 minutes', message: 'Queued, starts within 30 minutes', task: full(t) }
    }],
    ['PUT', /^\/tasks\/([^/]+)\/body$/, (q, [id], body) => {
      const t = find(id)
      if (body.expected_revision !== t.revision) throw new HttpError(409, 'stale_revision', 'The task changed since it was read')
      t.body = body.body
      bump(t)
      return { ok: true, task: full(t) }
    }],
    ['POST', /^\/tasks$/, (q, m, body) => {
      if (!body.title) throw new HttpError(400, 'title', 'A task needs a title.')
      const t = { task_id: crypto.randomUUID(), title: body.title, area: body.area || db.settings.tasks.default_area, status: 'open', priority: 'normal',
        due: body.date || today, scheduled: body.date || today, research: 'pending', summary: null,
        body: `\n## Notes\n\nAdded from the Tasks view.\n\n## Log\n\n- ${today}: Created from the Tasks view.\n`, path: `areas/${body.area || 'work'}/tasks/new.md`, revision: `r${rev++}` }
      db.tasks.push(t)
      setTimeout(() => { t.research = 'complete'; bump(t) }, 8000)
      return { ok: true, task: full(t) }
    }],
    ['GET', /^\/runs$/, () => ({ ok: true, runs: clone(db.runs) })],
    ['POST', /^\/tasks\/([^/]+)\/handoff$/, (q, [id], body) => {
      const t = find(id)
      const text = `[Alchemy Task handoff]\nThe user pressed "Send to chat" on a task (demo).\nTask: ${t.title}\nTask ID: ${t.task_id}`
      if (body.surface === 'desktop') return { ok: true, mode: 'desktop', text }
      const h = { id: `h${rev++}`, task_id: t.task_id, route: 'chat', state: 'pending', target: { platform: 'telegram', chat_name: 'Home', reason: 'home' } }
      db.handoffs = db.handoffs || {}
      db.handoffs[h.id] = h
      setTimeout(() => { h.state = 'sent' }, 1200)
      return { ok: true, mode: 'chat', handoff: clone(h) }
    }],
    ['GET', /^\/handoffs\/([^/]+)$/, (q, [hid]) => ({ ok: true, handoff: clone(db.handoffs[hid]) })],
    ['POST', /^\/proposals\/([^/]+)\/approve$/, (q, [pid], body) => {
      const run = db.runs.find((r) => r.proposals.some((p) => p.proposal_id === pid))
      const p = run && run.proposals.find((x) => x.proposal_id === pid)
      if (!p) throw new HttpError(404, 'not_found', 'Unknown proposal')
      if (p.state !== 'pending') throw new HttpError(409, 'already_resolved', 'Proposal already resolved')
      let task
      if (body.choice === 'create') {
        if (!body.due) throw new HttpError(400, 'needs_due', 'Ask for a due date')
        if (!body.area) throw new HttpError(400, 'needs_area', 'Pick an area')
        task = { task_id: crypto.randomUUID(), title: body.title || p.title, area: body.area, status: 'open', priority: 'normal', due: body.due, scheduled: body.due,
          research: 'complete', summary: p.current_understanding || null, revision: `r${rev++}`, path: `areas/${body.area}/tasks/discovered.md`,
          body: `\n## Current state\n\n${p.current_understanding || ''}\n\nNext: ${p.substantive_next_action || ''}\n\n## Notes\n\nFound by the ${run.stream} discovery stream.\n\n## Log\n\n- ${today}: Created from discovery.\n` }
        db.tasks.push(task)
      } else {
        task = find(body.target_task_id)
        if (body.expected_revision && body.expected_revision !== task.revision && !body.expected_revision.startsWith('r')) throw new HttpError(409, 'stale_revision', 'Target changed')
        task.body = task.body.replace(/## Log/, `## From discovery (${today})\n\n${(p.new_information || []).map((x) => `- ${x}`).join('\n')}\n\n## Log`)
        log(task, 'Updated from discovery.')
        bump(task)
      }
      p.state = 'complete'
      p.result = { task_id: task.task_id, title: task.title, operation: body.choice === 'create' ? 'created' : 'updated', state: 'complete' }
      run.summary.pending -= 1
      run.summary.complete += 1
      return { ok: true, receipt: { state: 'complete', task_id: task.task_id } }
    }],
    ['POST', /^\/proposals\/([^/]+)\/dismiss$/, (q, [pid]) => {
      const run = db.runs.find((r) => r.proposals.some((p) => p.proposal_id === pid))
      const p = run.proposals.find((x) => x.proposal_id === pid)
      p.state = 'dismissed'
      run.summary.pending -= 1
      run.summary.dismissed += 1
      return { ok: true, proposal_id: pid, state: 'dismissed' }
    }],
    ['GET', /^\/settings$/, () => ({ ok: true, ...clone(db.settings) })],
    ['PATCH', /^\/settings\/streams\/([^/]+)$/, (q, [name], body) => {
      const s = db.settings.streams.find((x) => x.name === decodeURIComponent(name))
      Object.assign(s, body)
      s.when = `${s.frequency === 'weekdays' ? 'weekdays' : s.frequency === 'daily' ? 'daily' : s.frequency}${s.frequency === 'daily' || s.frequency === 'weekdays' ? ` at ${s.time}` : ''}`
      return { ok: true, stream: clone(s), message: `Updated ${s.name}: ${s.when}.` }
    }],
    ['POST', /^\/settings\/streams\/([^/]+)\/run$/, (q, [name]) => ({ ok: true, message: `The ${decodeURIComponent(name)} discovery run has started. Its proposals will appear here.` })],
    ['PATCH', /^\/settings\/tasks$/, (q, m, body) => { Object.assign(db.settings.tasks, body); if (body.default_area) db.settings.tasks.default_area = body.default_area; return { ok: true } }],
  ]

  async function send(method, path, body) {
    await sleep()
    const [p, query] = path.split('?')
    const q = new URLSearchParams(query || '')
    for (const [m, re, fn] of routes) {
      if (m !== method) continue
      const match = p.match(re)
      if (match) return fn(q, match.slice(1).map(decodeURIComponent), body || {})
    }
    throw new HttpError(404, 'not_found', `No mock route for ${method} ${p}`)
  }
  return { send, db, today, addDays }
}
