// Advanced settings: discovery stream schedules and a few task defaults. Anything that needs approval
// in chat (sources, accounts, areas) is shown read-only with the phrase to ask Hermes.
import React from 'react'
import { describeError } from './api.js'
import { useApp } from './store.js'
import { AreaDot, Button, Icon, IconButton, Menu, Spinner, cx, useOverlay, useSheetDismiss, useToast } from './ui.jsx'

const FREQUENCIES = [
  ['daily', 'Every day'], ['weekdays', 'Weekdays'], ['every 4 hours', 'Every 4 hours'],
  ['every 3 hours', 'Every 3 hours'], ['every 2 hours', 'Every 2 hours'], ['hourly', 'Every hour'],
]
const timed = (f) => f === 'daily' || f === 'weekdays'

function to24(t) {
  const m = String(t || '').trim().toLowerCase().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/)
  if (!m) return '07:00'
  let h = Number(m[1]) % 24
  if (m[3] === 'pm' && h < 12) h += 12
  if (m[3] === 'am' && h === 12) h = 0
  return `${String(h).padStart(2, '0')}:${m[2] || '00'}`
}
function to12(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

export function SettingsPanel({ onClose, inline, narrow }) {
  const { api } = useApp()
  const [data, setData] = React.useState(null)
  const [error, setError] = React.useState(null)
  const sheetRef = React.useRef(null)
  useSheetDismiss(sheetRef, narrow && !inline, onClose)
  const load = React.useCallback(() => {
    setError(null)
    return api.settings().then(setData, setError)
  }, [api])
  React.useEffect(() => { load() }, [load])
  const body = !data ? (
    error ? <div className="at-panel-empty"><Icon name="alert" size={20} /><p>{describeError(error)}</p><Button onClick={load}>Try again</Button></div>
      : <div className="at-panel-empty"><Spinner size={18} /></div>
  ) : <SettingsBody data={data} reload={load} />
  if (inline) return <div className="at-settings-inline">{body}</div>
  return (
    <aside ref={sheetRef} className={cx('at-panel', narrow ? 'is-sheet' : 'is-side', 'at-settings')} aria-label="Settings">
      <div className="at-panel-bar">
        {narrow ? <span className="at-grabber" /> : null}
        <span className="at-panel-heading">Settings</span>
        <span className="at-flex" />
        <IconButton icon="x" label="Close" onClick={onClose} />
      </div>
      <div className="at-panel-body at-scroll">{body}</div>
    </aside>
  )
}

function SettingsBody({ data, reload }) {
  const streams = data.streams || []
  const t = data.tasks || {}
  return (
    <div className="at-settings-body">
      <section className="at-set-sec">
        <h3>Discovery</h3>
        <p className="at-muted">When each discovery stream reads its sources and proposes tasks.</p>
        {streams.length ? streams.map((s) => <StreamRow key={s.name} s={s} reload={reload} />) : (
          <div className="at-set-empty">No streams yet. Ask Hermes: <q>Set up a daily digest from my email at 7 AM.</q></div>
        )}
      </section>
      <section className="at-set-sec">
        <h3>Tasks</h3>
        <TaskDefaults t={t} reload={reload} />
      </section>
      <section className="at-set-sec">
        <h3>Sync and storage</h3>
        <div className="at-set-grid">
          <span className="at-muted">Workspace</span><span className="at-mono at-break">{t.workspace_root || 'Not set up'}</span>
          <span className="at-muted">Time zone</span><span>{t.timezone || 'Hermes default'}</span>
          {data.sync && data.sync.git ? <><span className="at-muted">Git</span><span>{data.sync.git}</span></> : null}
          {data.sync && data.sync.reminders ? <><span className="at-muted">iOS Reminders</span><span>{data.sync.reminders}</span></> : null}
        </div>
        <p className="at-muted at-set-hint">To change sources, accounts or areas, ask Hermes in chat, for example <q>add my team Slack channel to the work digest</q>.</p>
      </section>
    </div>
  )
}

function StreamRow({ s, reload }) {
  const { api } = useApp()
  const toast = useToast()
  const overlay = useOverlay()
  const [freq, setFreq] = React.useState(s.frequency || 'daily')
  const [time, setTime] = React.useState(to24(s.time || '7 AM'))
  const [busy, setBusy] = React.useState(null)
  const dirty = freq !== (s.frequency || 'daily') || (timed(freq) && time !== to24(s.time || '7 AM'))
  const save = async () => {
    setBusy('save')
    try {
      const res = await api.patchStream(s.name, timed(freq) ? { frequency: freq, time: to12(time) } : { frequency: freq })
      toast(res.message || 'Schedule updated')
      await reload()
    } catch (err) { toast(describeError(err), { tone: 'error' }) }
    setBusy(null)
  }
  const runNow = async () => {
    setBusy('run')
    try { const res = await api.runStream(s.name); toast(res.message || 'Discovery run started') } catch (err) { toast(describeError(err), { tone: 'error' }) }
    setBusy(null)
  }
  const pickFreq = (e) => overlay.open(e.currentTarget, (close) => (
    <Menu close={close} items={FREQUENCIES.map(([v, l]) => ({ label: l, icon: v === freq ? 'check' : undefined, run: () => setFreq(v) }))} />
  ), { width: 200 })
  const blocked = s.setup_blocked_reason || (s.activation_state && !/active|ok|ready/i.test(s.activation_state) ? s.activation_state : '')
  return (
    <div className="at-stream">
      <div className="at-stream-head">
        <div>
          <div className="at-stream-name">{String(s.name).replace(/\b\w/g, (c) => c.toUpperCase())}</div>
          <div className="at-muted">
            {(s.areas || []).map((a) => <span key={a} className="at-inline-area"><AreaDot area={a} />{a}</span>)}
            {s.last_run ? <span> · last ran {lastRun(s.last_run)}</span> : null}
          </div>
        </div>
        <span className="at-flex" />
        <Button size="sm" variant="ghost" icon="play" onClick={runNow} disabled={!!busy}>{busy === 'run' ? 'Starting…' : 'Run now'}</Button>
      </div>
      <div className="at-stream-sched">
        <button type="button" className="at-field" onClick={pickFreq}><Icon name="clock" size={14} /><span>{(FREQUENCIES.find(([v]) => v === freq) || [0, freq])[1]}</span><Icon name="chevD" size={13} /></button>
        {timed(freq) ? (
          <label className="at-field at-timefield"><span className="at-muted">at</span>
            <input type="time" value={time} step={300} onChange={(e) => setTime(e.target.value || time)} />
          </label>
        ) : null}
        {s.timezone ? <span className="at-muted at-tz">{s.timezone.replace(/_/g, ' ')}</span> : null}
        <span className="at-flex" />
        {dirty ? <Button size="sm" variant="primary" onClick={save} disabled={!!busy}>{busy === 'save' ? 'Saving…' : 'Save'}</Button> : null}
      </div>
      {(s.sources || []).length ? (
        <div className="at-stream-sources">
          {(s.sources || []).map((src) => <span key={src.name} className="at-chip" title={src.scope}>{src.name}</span>)}
        </div>
      ) : null}
      {blocked ? <div className="at-banner at-tone-late"><Icon name="alert" size={14} /><span>{blocked}</span></div> : null}
    </div>
  )
}

function lastRun(v) {
  const d = typeof v === 'number' ? new Date(v * (v < 1e12 ? 1000 : 1)) : new Date(v)
  if (Number.isNaN(d.getTime())) return ''
  const mins = Math.round((Date.now() - d.getTime()) / 60000)
  if (mins < 60) return `${Math.max(1, mins)} min ago`
  if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function TaskDefaults({ t, reload }) {
  const { api, meta } = useApp()
  const toast = useToast()
  const overlay = useOverlay()
  const set = async (changes) => {
    try { await api.patchTaskSettings(changes); toast('Saved'); await reload() } catch (err) { toast(describeError(err), { tone: 'error' }) }
  }
  const pickArea = (e) => overlay.open(e.currentTarget, (close) => (
    <Menu close={close} items={(meta.areas || []).map((a) => ({ label: a, icon: a === t.default_area ? 'check' : undefined, run: () => set({ default_area: a }) }))} />
  ), { width: 200 })
  return (
    <div className="at-set-grid">
      <span className="at-muted">Default area</span>
      <span><button type="button" className="at-field" onClick={pickArea}><AreaDot area={t.default_area} /><span>{t.default_area || 'None'}</span><Icon name="chevD" size={13} /></button></span>
      <span className="at-muted">Research new tasks</span>
      <span>
        <button type="button" role="switch" aria-checked={!!t.research_by_default} className={cx('at-switch', t.research_by_default && 'is-on')}
                onClick={() => set({ research_by_default: !t.research_by_default })}><i /></button>
      </span>
    </div>
  )
}
