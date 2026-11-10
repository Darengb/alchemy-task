// App shell shared by the dashboard and the desktop app: navigation (Tasks, Discovery, settings gear),
// task actions with undo, live refresh, and the providers every view uses.
import React from 'react'
import * as D from './lib/dates.js'
import { DragProvider } from './lib/dnd.js'
import { describeError } from './api.js'
import { AppContext, createTaskStore, usePref, useStore, useWidth } from './store.js'
import { TasksView } from './tasks.jsx'
import { TaskPanel } from './panel.jsx'
import { DiscoveryView, discoveryBadge } from './discovery.jsx'
import { SettingsPanel } from './settings.jsx'
import { Icon, IconButton, OverlayHost, Spinner, ToastHost, ToastOutlet, cx, useToast } from './ui.jsx'

const NARROW = 720
const POLL_MS = 30000

export function App(props) {
  return (
    <ToastHost>
      <AppInner {...props} />
    </ToastHost>
  )
}

function AppInner({ transport, host, initialView, settingsOnly, chat }) {
  const api = transport
  const toast = useToast()
  const rootRef = React.useRef(null)
  const width = useWidth(rootRef)
  const narrow = width < NARROW
  const store = React.useMemo(() => createTaskStore(api), [api])
  const today = useStore(store, selToday)
  const busy = useStore(store, selLoading)
  const [meta, setMeta] = React.useState(null)
  const [metaError, setMetaError] = React.useState(null)
  const [tab, setTab] = React.useState(initialView === 'discovery' ? 'discovery' : 'tasks')
  const [settingsOpen, setSettingsOpen] = React.useState(initialView === 'settings')
  const [selectedId, setSelectedId] = React.useState(null)
  const [prefsRaw, setPrefsRaw] = usePref('prefs', { view: null, area: '', hideDone: false })
  const prefs = prefsRaw
  const setPrefs = React.useCallback((p) => setPrefsRaw((cur) => ({ ...cur, ...p })), [setPrefsRaw])
  const [runs, setRuns] = React.useState(null)
  const [runsError, setRunsError] = React.useState(null)
  const [runsLoading, setRunsLoading] = React.useState(false)
  const [streams, setStreams] = React.useState(null)

  // ---- loading
  const loadMeta = React.useCallback(() => api.meta().then((m) => { setMeta(m); setMetaError(null); store.setToday(m.today) }, setMetaError), [api, store])
  const loadRuns = React.useCallback(async () => {
    setRunsLoading(true)
    try { const res = await api.runs(); setRuns(res.runs || []); setRunsError(null) } catch (err) { setRunsError(err) }
    setRunsLoading(false)
    // Streams only matter for the setup badge before the first run, so skip the call once runs exist.
    try { const s = await api.settings(); setStreams(Array.isArray(s.streams) ? s.streams : null) } catch { setStreams(null) }
  }, [api])
  React.useEffect(() => { loadMeta(); loadRuns() }, [loadMeta, loadRuns])

  React.useEffect(() => {
    const refresh = () => { loadMeta(); store.refresh(); loadRuns() }
    const id = setInterval(() => { if (document.visibilityState === 'visible') refresh() }, POLL_MS)
    window.addEventListener('focus', refresh)
    return () => { clearInterval(id); window.removeEventListener('focus', refresh) }
  }, [loadMeta, loadRuns, store])

  React.useEffect(() => {
    const open = (e) => {
      const v = e.detail
      if (v === 'discovery' || v === 'tasks') setTab(v)
      if (v === 'settings') setSettingsOpen(true)
    }
    window.addEventListener('alchemy-task:open', open)
    return () => window.removeEventListener('alchemy-task:open', open)
  }, [])

  // ---- actions
  const actions = React.useMemo(() => {
    const done = (t) => t.status === 'done' || t.status === 'cancelled'
    const fail = (err) => toast(describeError(err), { tone: 'error' })
    const complete = (t) => store.mutate(t.task_id, { status: 'done', completed: store.getState().today }, () => api.complete(t.task_id))
    const reopen = (t) => store.mutate(t.task_id, { status: 'open', completed: null }, () => api.reopen(t.task_id))
    const setDates = (t, scheduled, due) => store.mutate(t.task_id, { scheduled, due },
      () => api.patch(t.task_id, scheduled === due ? { date: scheduled } : { scheduled, due, keep_separate: true }))
    const a = {
      open: (id) => setSelectedId(id),
      async toggle(t) {
        try {
          if (done(t)) {
            await reopen(t)
            toast('Marked not done', { undo: () => complete(t).catch(fail) })
          } else {
            await complete(t)
            toast(`Done: ${t.title}`, { undo: () => reopen(t).catch(fail) })
          }
        } catch (err) { fail(err) }
      },
      async move(t, date) {
        const before = { scheduled: t.scheduled || null, due: t.due || null }
        if (D.taskDate(t) === date && (!t.due || t.due === date)) return
        try {
          await setDates(t, date, date)
          toast(`Moved to ${D.relativeDay(date, store.getState().today)}`, {
            undo: () => setDates({ ...t, scheduled: date, due: date }, before.scheduled || before.due, before.due || before.scheduled).catch(fail),
          })
        } catch (err) { fail(err) }
      },
      async moveMany(tasks, date) {
        const list = tasks.slice()
        let moved = 0
        for (const t of list) {
          try { await setDates(t, date, date); moved++ } catch (err) { fail(err); break }
        }
        if (moved) {
          toast(`Moved ${moved} ${moved === 1 ? 'task' : 'tasks'} to ${D.relativeDay(date, store.getState().today).toLowerCase()}`, {
            undo: async () => {
              for (const t of list.slice(0, moved)) {
                try { await setDates({ ...t, scheduled: date, due: date }, t.scheduled || t.due, t.due || t.scheduled) } catch (err) { fail(err); break }
              }
            },
          })
        }
      },
      async create({ title, date, area }) {
        try {
          const res = await api.create({ title, date, area })
          if (res.task) store.put(res.task)
          toast(res.task && res.task.research === 'pending' ? 'Added. Hermes is researching it.' : 'Added', {
            action: res.task ? { label: 'Open', run: () => setSelectedId(res.task.task_id) } : undefined,
          })
          return true
        } catch (err) { fail(err); return false }
      },
    }
    return a
  }, [api, store, toast])

  const onDrop = React.useCallback((task, date) => actions.move(task, date), [actions])
  const pending = discoveryBadge(runs, streams)
  const ctx = React.useMemo(() => ({
    api, store, meta: meta || {}, today: today || (meta && meta.today), prefs, setPrefs, actions, selectedId, narrow, host, chat,
  }), [api, store, meta, today, prefs, setPrefs, actions, selectedId, narrow, host, chat])

  // Fill the space the host gives us: the desktop page has a fixed height; the dashboard scrolls the page.
  const [height, setHeight] = React.useState(null)
  React.useLayoutEffect(() => {
    const el = rootRef.current
    if (!el || settingsOnly) return undefined
    const fit = () => {
      const parent = el.parentElement
      const ph = parent ? parent.getBoundingClientRect().height : 0
      if (host === 'desktop' && ph > 300) { setHeight(null); return }
      const top = el.getBoundingClientRect().top
      const vh = (window.visualViewport && window.visualViewport.height) || window.innerHeight
      setHeight(Math.max(420, Math.round(vh - Math.max(0, top) - 8)))
    }
    fit()
    window.addEventListener('resize', fit)
    if (window.visualViewport) window.visualViewport.addEventListener('resize', fit)
    return () => { window.removeEventListener('resize', fit); if (window.visualViewport) window.visualViewport.removeEventListener('resize', fit) }
  }, [host, settingsOnly])

  const content = (() => {
    if (!meta && metaError) {
      return <Centered icon="alert" title="Alchemy Task is not responding" text={describeError(metaError)} />
    }
    if (!meta || !ctx.today) return <div className="at-loading"><Spinner size={18} /></div>
    if (meta.configured === false) {
      return <Centered icon="list" title="Set up your tasks" text={<>Alchemy Task is installed but not set up yet. In chat, ask Hermes: <q>Set up my tasks.</q></>} />
    }
    if (settingsOnly) return <SettingsPanel inline narrow={narrow} />
    return (
      <>
        <nav className="at-appbar">
          {narrow ? null : <span className="at-brand"><i className="at-brand-mark" aria-hidden="true" />Alchemy Task</span>}
          <div className="at-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === 'tasks'} className={cx('at-tab', tab === 'tasks' && 'is-on')} onClick={() => setTab('tasks')}>Tasks</button>
            <button type="button" role="tab" aria-selected={tab === 'discovery'} className={cx('at-tab', tab === 'discovery' && 'is-on')} onClick={() => setTab('discovery')}>
              Discovery{pending ? <span className="at-badge-dot">{pending}</span> : null}
            </button>
          </div>
          <span className="at-flex" />
          {busy ? <Spinner size={12} /> : null}
          <IconButton icon="gear" label="Settings" className={cx(settingsOpen && 'is-on')} onClick={() => { setSelectedId(null); setSettingsOpen((v) => !v) }} />
        </nav>
        <div className={cx('at-main', selectedId && !narrow && 'has-panel', settingsOpen && !narrow && 'has-panel')}>
          {tab === 'tasks' ? <TasksView narrow={narrow} /> : (
            <DiscoveryView runs={runs} error={runsError} loading={runsLoading} reload={loadRuns} />
          )}
        </div>
        {selectedId ? <TaskPanel id={selectedId} narrow={narrow} onClose={() => setSelectedId(null)} /> : null}
        {settingsOpen && !selectedId ? <SettingsPanel narrow={narrow} onClose={() => setSettingsOpen(false)} /> : null}
      </>
    )
  })()

  return (
    <AppContext.Provider value={ctx}>
      <div ref={rootRef} className={cx('at-root at-vars', narrow && 'is-narrow', `host-${host}`, settingsOnly && 'is-settings-only')}
           style={height ? { height } : undefined}>
        <DragProvider onDrop={onDrop}>
          <OverlayHost rootRef={rootRef}>{content}</OverlayHost>
        </DragProvider>
        <ToastOutlet />
      </div>
    </AppContext.Provider>
  )
}

const selToday = (s) => s.today
const selLoading = (s) => s.loading > 0

function Centered({ icon, title, text }) {
  return (
    <div className="at-emptystate is-full">
      <span className="at-emptystate-icon"><Icon name={icon} size={22} /></span>
      <h2>{title}</h2>
      <p>{text}</p>
    </div>
  )
}
