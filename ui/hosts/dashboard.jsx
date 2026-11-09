// Web dashboard host: registers the Tasks tab and talks to /api/plugins/alchemy-task through the SDK.
import React from 'react'
import { App } from '../src/App.jsx'
import { makeTransport } from '../src/api.js'

const SDK = window.__HERMES_PLUGIN_SDK__
const BASE = '/api/plugins/alchemy-task'

const transport = makeTransport(async (method, path, body) => {
  const init = { method, headers: {} }
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  return SDK.fetchJSON(BASE + path, init)
})

function DashboardTasks() {
  return <App transport={transport} host="dashboard" />
}

window.__HERMES_PLUGINS__.register('alchemy-task', DashboardTasks)
