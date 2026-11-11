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
