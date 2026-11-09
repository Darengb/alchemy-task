// Client task store: every task the UI has loaded, keyed by task_id. Views derive their lists from it,
// so a change made in one view (or an optimistic move) shows everywhere at once. Fetches replace what
// they cover; tasks with a change in flight are left alone until the server answers.
import React from 'react'
import { taskDate } from './lib/dates.js'

export function createTaskStore(api) {
  let state = { byId: {}, today: null, loading: 0, error: null, version: 0 }
  const listeners = new Set()
  const pending = new Map() // task_id -> number of changes in flight
  const loaded = new Map() // range key -> { from, to }

  const emit = () => { state = { ...state, version: state.version + 1 }; listeners.forEach((l) => l()) }
  const set = (patch) => { state = { ...state, ...patch }; emit() }

  function upsert(tasks, coveredFn) {
    const byId = { ...state.byId }
    const seen = new Set()
    for (const t of tasks) {
      seen.add(t.task_id)
      if (pending.has(t.task_id)) continue
      const prev = byId[t.task_id] || {}
      // List rows carry no body; keep a body loaded earlier unless the file changed since.
      const body = t.body !== undefined ? t.body : (prev.revision === t.revision ? prev.body : undefined)
      byId[t.task_id] = { ...prev, ...t, body }
    }
    if (coveredFn) {
      for (const [id, t] of Object.entries(byId)) {
        if (!seen.has(id) && !pending.has(id) && coveredFn(t)) delete byId[id]
      }
    }
    state = { ...state, byId }
  }

  async function track(promise) {
    set({ loading: state.loading + 1 })
    try { return await promise } finally { set({ loading: Math.max(0, state.loading - 1) }) }
  }

  const store = {
    getState: () => state,
    subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn) },
    setToday: (today) => { if (today !== state.today) set({ today }) },

    async loadRange(from, to) {
      loaded.set(`${from}:${to}`, { from, to })
      const res = await track(api.tasks(from, to))
      if (res.today) state = { ...state, today: res.today }
      upsert(res.tasks || [], (t) => { const d = taskDate(t); return d && d >= from && d <= to })
      set({ error: null })
      return res
    },

    async loadOverdue() {
      const res = await track(api.overdue())
      const today = res.today || state.today
      if (res.today) state = { ...state, today: res.today }
      upsert(res.tasks || [], (t) => { const d = taskDate(t); return t.status !== 'done' && t.status !== 'cancelled' && d && d < today })
      set({ error: null })
      return res
    },

    /** Refetch every range loaded so far (focus, polling, after agent changes). */
    async refresh() {
      const ranges = [...loaded.values()].slice(-4)
      try {
        await Promise.all([...ranges.map((r) => store.loadRange(r.from, r.to)), store.loadOverdue()])
      } catch (err) {
        set({ error: err })
      }
    },

    async loadTask(id) {
      const res = await api.task(id)
      upsert([res.task])
      emit()
      return res.task
    },

    put(task) { upsert([task]); emit() },

    /** Apply a local change now, run the server call, then take the server's version (or roll back). */
    async mutate(id, localPatch, run) {
      const before = state.byId[id]
      pending.set(id, (pending.get(id) || 0) + 1)
      if (before && localPatch) {
        state = { ...state, byId: { ...state.byId, [id]: { ...before, ...localPatch } } }
        emit()
      }
      try {
        const res = await run()
        const left = (pending.get(id) || 1) - 1
        if (left) pending.set(id, left); else pending.delete(id)
        if (res && res.task) { upsert([res.task]); emit() }
        return res
      } catch (err) {
        const left = (pending.get(id) || 1) - 1
        if (left) pending.set(id, left); else pending.delete(id)
        if (before) { state = { ...state, byId: { ...state.byId, [id]: before } }; emit() }
        throw err
      }
    },
  }
  return store
}

export function useStore(store, selector) {
  const get = React.useCallback(() => selector(store.getState()), [store, selector])
  const [value, setValue] = React.useState(get)
  React.useEffect(() => {
    setValue(get())
    return store.subscribe(() => setValue(get()))
  }, [store, get])
  return value
}

export const AppContext = React.createContext(null)
export const useApp = () => React.useContext(AppContext)

/** Persist a small UI preference in localStorage (per browser). */
export function usePref(key, initial) {
  const full = `alchemy-task.${key}`
  const [value, setValue] = React.useState(() => {
    try {
      const raw = window.localStorage.getItem(full)
      return raw === null ? initial : JSON.parse(raw)
    } catch { return initial }
  })
  const update = React.useCallback((v) => {
    setValue((prev) => {
      const next = typeof v === 'function' ? v(prev) : v
      try { window.localStorage.setItem(full, JSON.stringify(next)) } catch { /* private mode */ }
      return next
    })
  }, [full])
  return [value, update]
}

/** Width of an element, for layouts that follow the space they get (desktop panes, phones). */
export function useWidth(ref) {
  const [w, setW] = React.useState(() => (typeof window !== 'undefined' ? window.innerWidth : 1200))
  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    setW(el.getBoundingClientRect().width)
    const ro = new ResizeObserver((entries) => setW(entries[0].contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return w
}
