// One client for both hosts. A host supplies send(method, path, body) -> parsed JSON (or throws);
// everything else (errors, routes, query strings) lives here so a backend rename is a one-file change.

export class ApiError extends Error {
  constructor(code, message, status = 0) {
    super(message || code)
    this.code = code || 'error'
    this.status = status
  }
}

function parseErrorBody(err) {
  const raw = err && (err.body || err.responseText || err.message || '')
  if (raw && typeof raw === 'object') return raw
  const text = String(raw)
  const at = text.indexOf('{')
  if (at >= 0) {
    try { return JSON.parse(text.slice(at)) } catch { /* not JSON */ }
  }
  return null
}

function toApiError(err) {
  if (err instanceof ApiError) return err
  const body = parseErrorBody(err)
  const e = body && (body.error || body.detail)
  const status = (err && err.status) || 0
  if (e && typeof e === 'object') return new ApiError(e.code, e.message, status)
  if (typeof e === 'string') return new ApiError(status === 404 ? 'not_found' : 'error', e, status)
  if (status === 404) return new ApiError('not_found', 'Not found', 404)
  if (status === 0 || /network|failed to fetch|unreachable/i.test(String(err && err.message))) {
    return new ApiError('offline', 'Hermes is not reachable right now.', status)
  }
  return new ApiError('error', (err && err.message) || 'Something went wrong', status)
}

const qs = (params) => {
  const parts = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '' && v !== false)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v === true ? '1' : v)}`)
  return parts.length ? `?${parts.join('&')}` : ''
}
const enc = encodeURIComponent

export function makeTransport(send) {
  async function call(method, path, body) {
    let res
    try {
      res = await send(method, path, body)
    } catch (err) {
      throw toApiError(err)
    }
    if (res && res.ok === false) {
      const e = res.error || {}
      throw new ApiError(e.code || res.needs || 'error', e.message || res.message, 200)
    }
    return res
  }

  return {
    // ---- tasks
    meta: () => call('GET', '/meta'),
    tasks: (from, to, { area, includeDone = true } = {}) =>
      call('GET', '/tasks' + qs({ from, to, area, include_done: includeDone })),
    overdue: ({ area } = {}) => call('GET', '/overdue' + qs({ area })),
    task: (id) => call('GET', `/tasks/${enc(id)}`),
    patch: (id, changes) => call('PATCH', `/tasks/${enc(id)}`, changes),
    complete: (id) => call('POST', `/tasks/${enc(id)}/complete`, {}),
    reopen: (id) => call('POST', `/tasks/${enc(id)}/reopen`, {}),
    putBody: (id, body, expectedRevision) =>
      call('PUT', `/tasks/${enc(id)}/body`, { body, expected_revision: expectedRevision }),
    create: (fields) => call('POST', '/tasks', fields),

    // ---- discovery (routes owned by the discovery backend; see docs/discovery-backend-contract.md)
    runs: (params = {}) => call('GET', '/runs' + qs(params)),
    run: (runId) => call('GET', `/runs/${enc(runId)}`),
    approve: (proposalId, body) => call('POST', `/proposals/${enc(proposalId)}/approve`, body),
    dismiss: (proposalId) => call('POST', `/proposals/${enc(proposalId)}/dismiss`, {}),
    resume: (runId, unitId) => call('POST', `/runs/${enc(runId)}/units/${enc(unitId)}/resume`, {}),

    // ---- settings
    settings: () => call('GET', '/settings'),
    patchStream: (name, changes) => call('PATCH', `/settings/streams/${enc(name)}`, changes),
    runStream: (name) => call('POST', `/settings/streams/${enc(name)}/run`, {}),
    patchTaskSettings: (changes) => call('PATCH', '/settings/tasks', changes),
  }
}

/** Plain-language message for an error, for toasts and inline notes. */
export function describeError(err) {
  const code = err && err.code
  switch (code) {
    case 'stale_revision':
    case 'retry':
      return 'This task changed somewhere else. Reload it to see the latest version.'
    case 'offline':
      return 'Hermes is not reachable right now. Your change was not saved.'
    case 'needs_due':
    case 'due':
      return 'Pick a date first.'
    case 'needs_area':
    case 'area':
      return 'Pick an area first.'
    case 'already_resolved':
      return 'This proposal was already handled.'
    case 'expired':
      return 'This proposal expired.'
    case 'not_production':
      return 'This was a test run, so it cannot change tasks.'
    case 'not_found':
      return 'It is no longer there. It may have been moved or deleted.'
    default:
      return (err && err.message) || 'Something went wrong.'
  }
}
