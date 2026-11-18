import test from 'node:test'
import assert from 'node:assert/strict'
import { createTaskStore } from '../src/store.js'

const row = (revision, body) => ({ task_id: 't1', title: 'A', status: 'open', due: '2026-11-17', revision, ...(body === undefined ? {} : { body }) })

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

test('a list refresh that started before a save cannot roll the task back', async () => {
  const list = deferred()
  const api = { tasks: () => list.promise, overdue: async () => ({ tasks: [] }), task: async () => ({ task: row('r1', 'old') }) }
  const store = createTaskStore(api)
  await store.loadTask('t1')

  const refresh = store.loadRange('2026-11-01', '2026-11-30') // reads the file at r1, answers late
  store.put(row('r2', 'new')) // the autosave lands first
  list.resolve({ tasks: [row('r1')] })
  await refresh

  const t = store.getState().byId.t1
  assert.equal(t.revision, 'r2')
  assert.equal(t.body, 'new')
})

test('a refresh that started after the save still brings in outside changes', async () => {
  const api = { tasks: async () => ({ tasks: [row('r3')] }), overdue: async () => ({ tasks: [] }), task: async () => ({ task: row('r1', 'old') }) }
  const store = createTaskStore(api)
  await store.loadTask('t1')
  store.put(row('r2', 'new'))
  await store.loadRange('2026-11-01', '2026-11-30')
  const t = store.getState().byId.t1
  assert.equal(t.revision, 'r3')
  assert.equal(t.body, undefined) // body is refetched for a changed file
})

test('a late list does not drop a task that a save just moved into its range', async () => {
  const list = deferred()
  const api = { tasks: () => list.promise, overdue: async () => ({ tasks: [] }), task: async () => ({ task: row('r1', 'x') }) }
  const store = createTaskStore(api)
  const refresh = store.loadRange('2026-11-01', '2026-11-30')
  store.put(row('r2', 'x'))
  list.resolve({ tasks: [] })
  await refresh
  assert.equal(store.getState().byId.t1.revision, 'r2')
})
