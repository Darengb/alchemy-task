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
if (params.get('empty') === 'discovery') backend.db.runs.length = 0
window.__demo = backend
const transport = makeTransport(backend.send)

createRoot(document.getElementById('root')).render(<App transport={transport} host={params.get('host') || 'dashboard'} />)
