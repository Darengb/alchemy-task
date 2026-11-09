// Desktop app host: a Tasks page with a sidebar entry and palette commands, backed by ctx.rest.
import React from 'react'
import { host, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA } from '@hermes/plugin-sdk'
import { App } from '../src/App.jsx'
import { makeTransport } from '../src/api.js'
import css from '../src/styles.css'

const STYLE_ID = 'alchemy-task-ui-styles'

export default {
  id: 'alchemy-task',
  name: 'Alchemy Task',
  register(ctx) {
    if (!document.getElementById(STYLE_ID)) {
      const style = document.createElement('style')
      style.id = STYLE_ID
      style.textContent = css
      document.head.appendChild(style)
      ctx.onDispose(() => style.remove())
    }
    const transport = makeTransport((method, path, body) =>
      ctx.rest(path, body === undefined ? { method } : { method, body }))
    let pending = null // a view to open next ('tasks' | 'discovery' | 'settings')
    const openWith = (view) => { pending = view; host.navigate('/alchemy-task'); window.dispatchEvent(new CustomEvent('alchemy-task:open', { detail: view })) }

    const Page = () => <App transport={transport} host="desktop" initialView={pending} />
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/alchemy-task' }, render: () => <Page /> },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/alchemy-task', label: 'Tasks', codicon: 'checklist' } },
      { id: 'open-tasks', area: PALETTE_AREA,
        data: { id: 'alchemy-task-open', label: 'Open tasks', keywords: ['tasks', 'today', 'calendar', 'alchemy'], run: () => openWith('tasks') } },
      { id: 'open-discovery', area: PALETTE_AREA,
        data: { id: 'alchemy-task-discovery', label: 'Review discovery proposals', keywords: ['discovery', 'digest', 'proposals', 'alchemy'], run: () => openWith('discovery') } },
    ])
    if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({
        id: 'settings',
        title: 'Alchemy Task',
        icon: 'checklist',
        render: () => <App transport={transport} host="desktop" settingsOnly />,
      })
    }
  },
}
