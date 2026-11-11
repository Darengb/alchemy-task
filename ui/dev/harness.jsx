// Standalone preview: mounts the real UI with the in-memory demo backend.
// Query options: ?theme=dark, ?host=desktop, ?empty=discovery
import React from 'react'
import { createRoot } from 'react-dom/client'
import { App } from '../src/App.jsx'
import { makeTransport } from '../src/api.js'
import { createMockBackend } from './mock-backend.js'
import css from '../src/styles.css'

const params = new URLSearchParams(location.search)
document.documentElement.dataset.theme = params.get('theme') || 'light'
const style = document.createElement('style')
style.textContent = css
document.head.appendChild(style)

const backend = createMockBackend()
if (params.get('empty') === 'discovery') { backend.db.runs.length = 0; backend.db.settings.streams.length = 0 }
// ?video=story: today's work run shows the Venice pricing proposal first (story launch video).
if (params.get('video') === 'story') {
  const run = backend.db.runs.find((r) => r.run_id === 'run-work-today')
  run.proposals.unshift({
    proposal_id: 'p_pricing_video', unit_id: 'pv', ref: 'A1', number: 1, kind: 'new', day: run.day, expires: run.day, state: 'pending', expired: false,
    title: 'Update every price and move subscriptions from 20 to 30 days', area: 'work',
    current_understanding: 'The team agreed in #pricing (112 messages) to raise every price about 8% and move subscriptions from 20 to 30 days from December 1. All 1,312 existing subscribers need to be migrated.',
    substantive_next_action: 'Update 48 prices in Shopify, change the Recharge interval, and migrate existing subscribers.',
    source_links: ['https://lumenleaf.slack.com/archives/C0PRICING/p1794426000112233'],
    research_disposition: 'confident', targets: [],
  })
  // README: put an existing-task match second so the screenshot shows both kinds of proposal
  const sem = run.proposals.findIndex((p) => p.kind === 'semantic')
  if (sem > 1) run.proposals.splice(1, 0, run.proposals.splice(sem, 1)[0])
  run.proposals.forEach((p, i) => { p.number = i + 1; p.ref = `A${i + 1}` })
  run.coverage = [{ source_key: 'Slack #pricing', status: 'complete' }, ...run.coverage]
  const ws = backend.db.settings.streams.find((x) => x.name === 'work')
  if (ws) ws.sources.splice(1, 0, { name: 'Slack #pricing', type: 'chat', scope: '#pricing' })
  run.summary.pending += 1
}
// ?video=pending: today's work run also shows the Winter Spice Chai ask as a pending proposal (launch-video stills).
if (params.get('video') === 'pending') {
  const run = backend.db.runs.find((r) => r.run_id === 'run-work-today')
  const chai = backend.db.tasks.find((t) => t.title.startsWith('Answer "when is it back?"'))
  run.proposals.unshift({
    proposal_id: 'p_chai_video', unit_id: 'cv', ref: 'A1', number: 1, kind: 'new', day: run.day, expires: run.day, state: 'pending', expired: false,
    title: chai.title, area: 'work',
    current_understanding: 'Customers keep emailing support to ask when the sold-out Winter Spice Chai is back. Jordan asked for back-in-stock alerts, and Michael said at Monday\u2019s standup that he would set it up before the restock.',
    substantive_next_action: 'Tell customers when it is back and let them sign up to be notified.',
    source_links: ['https://example.slack.com/archives/C0SUPPORT/p3', 'https://mail.google.com/mail/u/0/#inbox/demo-standup'],
    research_disposition: 'confident', targets: [],
  })
  run.proposals.forEach((p, i) => { p.number = i + 1; p.ref = `A${i + 1}` })
  run.summary.pending += 1
}
window.__demo = backend
const transport = makeTransport(backend.send)

createRoot(document.getElementById('root')).render(<App transport={transport} host={params.get('host') || 'dashboard'} />)
