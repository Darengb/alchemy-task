// The task panel: read a task, edit its fields and notes, check subtasks. A side panel when there is
// room, a full-height sheet on phones. Every write carries the revision it was based on, so an edit
// never overwrites a newer version of the file.
import React from 'react'
import * as D from './lib/dates.js'
import { parseBlocks, renderBlocks, splitSections, toggleLine, managedTitle, extractManaged, rebuildBody } from './lib/markdown.js'
import { describeError } from './api.js'
import { useApp, useStore } from './store.js'
import { AreaDot, Button, Check, DatePicker, Disclosure, Icon, IconButton, Menu, Spinner, copyText, cx, taskHandoff, useOverlay, markScrolled, useSheetDismiss, useToast } from './ui.jsx'
import { isDone } from './tasks.jsx'
import { researchButton, researchStartedMessage } from './lib/research.js'

const PRIORITIES = ['urgent', 'high', 'normal', 'low']
const PLATFORMS = { gui: 'the Hermes app', desktop: 'Hermes Desktop', tui: 'the terminal', telegram: 'Telegram', discord: 'Discord', slack: 'Slack', whatsapp: 'WhatsApp', signal: 'Signal',
  photon: 'iMessage', bluebubbles: 'iMessage', matrix: 'Matrix', teams: 'Teams', email: 'email', sms: 'SMS' }
// "Telegram" for the home channel; "Telegram (Ops team)" for a named chat that worked on the task.
const chatLabel = (t) => {
  const app = PLATFORMS[(t && t.platform) || ''] || ((t && t.platform) ? t.platform[0].toUpperCase() + t.platform.slice(1) : 'chat')
  return t && t.reason === 'task' && t.chat_name ? `${app} (${t.chat_name})` : app
}
const STATUSES = [['open', 'Open'], ['in-progress', 'In progress'], ['waiting', 'Waiting']]

export function TaskPanel({ id, narrow, onClose }) {
  const { store, api, actions, today, meta, host, chat } = useApp()
  const toast = useToast()
  const overlay = useOverlay()
  const sel = React.useCallback((s) => s.byId[id], [id])
  const task = useStore(store, sel)
  const [loadError, setLoadError] = React.useState(null)
  const [editing, setEditing] = React.useState(false)
  const [stale, setStale] = React.useState(false)
  // The "Copied" tooltip under the title stays until the next tap, click or key press anywhere.
  const [copied, setCopied] = React.useState(false)
  React.useEffect(() => {
    if (!copied) return undefined
    const hide = () => setCopied(false)
    document.addEventListener('pointerdown', hide, true)
    document.addEventListener('keydown', hide, true)
    return () => { document.removeEventListener('pointerdown', hide, true); document.removeEventListener('keydown', hide, true) }
  }, [copied])
  React.useEffect(() => setCopied(false), [id])
  const [sending, setSending] = React.useState(false)

  const load = React.useCallback(() => {
    setLoadError(null)
    setStale(false)
    return store.loadTask(id).catch((err) => setLoadError(err))
  }, [id, store])
  React.useEffect(() => { setEditing(false); load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps
  // A refresh after an outside change replaces the row without its body; fetch the body again.
  const bodyMissing = !!task && task.body === undefined
  React.useEffect(() => { if (bodyMissing && !loadError) load() }, [bodyMissing]) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the open task current (it may sit outside every loaded date range), except while editing notes.
  React.useEffect(() => {
    if (editing) return undefined
    const load = () => store.loadTask(id).catch(() => {})
    const t = setInterval(() => { if (document.visibilityState === 'visible') load() }, 30000)
    window.addEventListener('focus', load)
    return () => { clearInterval(t); window.removeEventListener('focus', load) }
  }, [id, editing, store])

  React.useEffect(() => {
    const key = (e) => { if (e.key === 'Escape' && !e.defaultPrevented && !editing) onClose() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose, editing])

  // Field changes made while the notes editor is open: save the notes first and close the editor, so the
  // editor never holds text built from an older version of the file.
  const flushRef = React.useRef(null)
  const settle = async () => {
    if (!editing || !flushRef.current) return true
    const ok = await flushRef.current()
    if (ok) setEditing(false)
    return ok
  }
  const patch = async (changes, local) => {
    if (!(await settle())) return
    try {
      await store.mutate(id, local || changes, () => api.patch(id, { ...changes, expected_revision: (store.getState().byId[id] || task || {}).revision }))
    } catch (err) {
      if (err.code === 'stale_revision' || err.code === 'retry') setStale(true)
      toast(describeError(err), { tone: 'error' })
    }
  }

  // Body writes always name the revision they were built from (never the store's latest), and run one at a time.
  const saveBody = async (body, baseRevision) => {
    const res = await api.putBody(id, body, baseRevision)
    store.put(res.task)
    return res.task
  }
  const toggleQueue = React.useRef(Promise.resolve())
  const toggle = (line, checked) => {
    toggleQueue.current = toggleQueue.current.then(async () => {
      const cur = store.getState().byId[id]
      if (!cur || cur.body === undefined) return
      try { await saveBody(toggleLine(cur.body, line, checked), cur.revision) } catch (err) {
        if (err.code === 'stale_revision') setStale(true)
        toast(describeError(err), { tone: 'error' })
      }
    })
  }

  if (!task && loadError) {
    return (
      <PanelShell narrow={narrow} onClose={onClose}>
        <div className="at-panel-empty"><Icon name="alert" size={20} /><p>{describeError(loadError)}</p>
          <Button onClick={load}>Try again</Button></div>
      </PanelShell>
    )
  }
  if (!task) return <PanelShell narrow={narrow} onClose={onClose}><div className="at-panel-empty"><Spinner size={18} /></div></PanelShell>

  const date = D.taskDate(task)
  const separateDue = task.due && task.scheduled && task.due !== task.scheduled
  const pickDate = (e) => overlay.open(e.currentTarget, (close) => (
    <DatePicker value={date} today={today} close={close} onPick={async (d) => { if (await settle()) actions.move(store.getState().byId[id] || task, d) }} />
  ), { width: 300 })
  const pickDue = (e) => overlay.open(e.currentTarget, (close) => (
    <DatePicker value={task.due} today={today} close={close}
                onPick={(d) => patch({ due: d, keep_separate: true }, { due: d })} />
  ), { width: 300 })
  const pickArea = (e) => overlay.open(e.currentTarget, (close) => (
    <Menu close={close} items={(meta.areas || []).map((ar) => ({
      label: ar, icon: ar === task.area ? 'check' : undefined, run: () => patch({ area: ar }),
    }))} />
  ), { width: 200 })
  const pickPriority = (e) => overlay.open(e.currentTarget, (close) => (
    <Menu close={close} items={PRIORITIES.map((p) => ({
      label: p[0].toUpperCase() + p.slice(1), icon: p === (task.priority || 'normal') ? 'check' : undefined, run: () => patch({ priority: p }),
    }))} />
  ), { width: 180 })
  const pickStatus = (e) => overlay.open(e.currentTarget, (close) => (
    <Menu close={close} items={STATUSES.map(([v, l]) => ({
      label: l, icon: v === task.status ? 'check' : undefined, run: () => patch({ status: v, ...(v === 'waiting' ? { reason: 'Marked waiting from the Tasks UI' } : {}) }),
    }))} />
  ), { width: 180 })

  // Hand the task to chat: copies its title and ID. Runs inside the tap or release that triggers it.
  // Success shows a "Copied" tooltip under the title; a failure hides it and shows a toast.
  const copyForChat = async () => {
    const cur = store.getState().byId[id] || task
    const ok = await copyText(taskHandoff(cur))
    if (ok) setCopied(true)
    else { setCopied(false); toast('Could not copy. Your browser blocked the clipboard.', { tone: 'error' }) }
    return ok
  }
  // The hold shows "Copied" the moment it registers. Browsers only allow the clipboard write in a tap or
  // release, so the write itself happens when the finger lifts (copyForChat via onLongPress).
  const holdRegistered = () => { if (navigator.vibrate) navigator.vibrate(12); setCopied(true) }

  // Send to chat. Desktop: a new chat with the handoff note, so the agent replies there. Elsewhere: the gateway
  // hands the note to the agent in a messaging chat, and the agent messages the user there.
  const sendToChat = async () => {
    if (sending) return
    setSending(true)
    try {
      if (host === 'desktop' && chat) {
        const res = await api.handoff(id, 'desktop')
        if (!(await chat.startChat(res.text))) toast('Could not open a new chat. Update Hermes Desktop and try again.', { tone: 'error' })
        return
      }
      // Route 1 (a messaging chat) answers in seconds; route 2 (a new session) through the scheduler in about
      // a minute. A messaging handoff the gateway does not take within ~10 s becomes a new session.
      const newChat = 'Starting a new chat for this task. Hermes will message you there in about a minute.'
      const res = await api.handoff(id, narrow ? 'phone' : 'dashboard')
      const h = res.handoff
      if (h.route === 'session') { toast(newChat, { duration: 7000 }); return }
      const where = chatLabel(h.target)
      toast(`Sending to ${where}…`)
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 1000))
        const st = (await api.handoffStatus(h.id)).handoff
        if (st.state === 'sent') { toast(`Sent. Hermes will message you on ${where}.`); return }
        if (st.route === 'session' && st.state === 'started') {
          toast(`${where} did not respond, so Hermes is starting a new chat instead. It will message you there in about a minute.`,
            { duration: 8000 })
          return
        }
        if (st.state === 'failed') { toast(st.error || 'Could not send it to chat.', { tone: 'error' }); return }
      }
      toast('Still sending. Hermes will message you when it picks this up.', { tone: 'error' })
    } catch (err) {
      if (err.code === 'permission') {
        const cmd = 'hermes config set plugins.entries.alchemy-task.allow_gateway_injection true'
        toast('Alchemy Task needs permission to message you in chat. Ask Hermes to allow it, or run the command.',
          { tone: 'error', duration: 12000, action: { label: 'Copy command', run: () => copyText(cmd) } })
      } else toast(describeError(err), { tone: 'error', duration: 9000 })
    } finally {
      setSending(false)
    }
  }

  return (
    <PanelShell narrow={narrow} onClose={onClose} footer={isDone(task) ? null : (
      <button type="button" className={cx('at-cta', sending && 'is-busy')} onClick={sendToChat} disabled={sending}>
        <Icon name="chat" size={19} strokeWidth={2} /><span>{sending ? 'Starting…' : 'Start in chat'}</span>
      </button>
    )} actions={
      <>
        {task.loading ? <Spinner /> : null}
        <IconButton icon="clipboard" label="Copy title and ID for chat" onClick={copyForChat} />
        <IconButton icon="refresh" label="Reload" onClick={load} />
      </>
    }>
      {stale ? (
        <div className="at-banner at-tone-late">
          <Icon name="alert" size={15} /><span className="at-flex">This task changed somewhere else.</span>
          <Button size="sm" onClick={load}>Reload</Button>
        </div>
      ) : null}
      <div className="at-panel-titlerow">
        <Check checked={isDone(task)} onChange={async () => { if (await settle()) actions.toggle(store.getState().byId[id] || task) }} label={isDone(task) ? 'Mark not done' : 'Mark done'} size="lg" />
        <TitleField value={task.title} done={isDone(task)} onSave={(title) => patch({ title })}
                    onHold={holdRegistered} onLongPress={copyForChat} copied={copied} />
      </div>
      <div className="at-fields">
        <button type="button" className={cx('at-field', date && date < today && !isDone(task) && 'is-late')} onClick={pickDate}>
          <Icon name="cal" size={15} /><span>{date ? D.relativeDay(date, today) : 'No date'}</span>
        </button>
        <button type="button" className="at-field" onClick={pickArea}>
          <AreaDot area={task.area} /><span>{task.area || 'No area'}</span>
        </button>
        {isDone(task) ? (
          <span className="at-field at-status is-static" data-s={task.status}>
            <span className="at-status-dot" /><span>{task.status === 'cancelled' ? 'Cancelled' : 'Done'}</span>
          </span>
        ) : (
          <button type="button" className="at-field at-status" data-s={task.status || 'open'} onClick={pickStatus}>
            <span className="at-status-dot" /><span>{(STATUSES.find(([v]) => v === task.status) || [0, 'Open'])[1]}</span>
          </button>
        )}
        {separateDue ? (
          <button type="button" className="at-field" onClick={pickDue}><span className="at-muted">Due</span><span>{D.relativeDay(task.due, today)}</span></button>
        ) : null}
      </div>

      <SummaryField value={task.summary || ''} onSave={(summary) => patch({ summary })} />
      {isDone(task) ? null : <ResearchBar task={task} />}

      {editing ? (
        <BodyEditor task={task} onSave={saveBody} onDone={() => setEditing(false)} onStale={() => setStale(true)} flushRef={flushRef} />
      ) : task.body === undefined ? <div className="at-panel-loading"><Spinner /></div> : (
        <BodyView task={task} onEdit={() => setEditing(true)} onToggle={toggle} />
      )}

      <Disclosure title="More" className="at-more">
        <div className="at-more-grid">
          <span className="at-muted">Priority</span>
          <span>
            <button type="button" className={cx('at-field is-plain', (task.priority === 'high' || task.priority === 'urgent') && 'is-high')} onClick={pickPriority}>
              <span className="at-prio-glyph" data-p={task.priority || 'normal'} /><span>{(task.priority || 'normal').replace(/^\w/, (c) => c.toUpperCase())}</span>
            </button>
          </span>
          <span className="at-muted">Due date</span>
          <span>
            {separateDue ? <button type="button" className="at-field is-plain" onClick={pickDue}>{D.shortDate(task.due, today)}</button>
              : <button type="button" className="at-link" onClick={pickDue}>Set a separate due date</button>}
          </span>
          {task.completed ? <><span className="at-muted">Completed</span><span>{D.shortDate(task.completed, today)}</span></> : null}
          {task.project ? <><span className="at-muted">Project</span><span className="at-mono">{String(task.project).replace(/^\[\[|\]\]$/g, '').split('/').slice(-2, -1)[0] || task.project}</span></> : null}
          <span className="at-muted">File</span><span className="at-mono at-break">{task.path}</span>
        </div>
      </Disclosure>
    </PanelShell>
  )
}

// Top of the research section: start, retry or refresh research. Workers only start inside an agent turn,
// so the button queues research and shows when it starts.
function ResearchBar({ task }) {
  const { store, api } = useApp()
  const toast = useToast()
  const [click, setClick] = React.useState(null)
  React.useEffect(() => setClick(null), [task.task_id])
  // Once research leaves the queue (finished or failed), the button shows the new state again.
  React.useEffect(() => {
    if (click && click.phase === 'done' && !['pending', 'running', 'promoted'].includes(task.research)) setClick(null)
  }, [task.research])
  const b = researchButton(task.research, click)
  const start = async () => {
    setClick({ phase: 'sending' })
    try {
      const res = await api.research(task.task_id)
      if (res.task) store.put(res.task)
      setClick({ phase: 'done', message: researchStartedMessage(res) })
    } catch (err) {
      setClick(null)
      toast(err.code === 'research_busy' ? 'Research is already queued or running.' : describeError(err), { tone: 'error' })
    }
  }
  return (
    <div className="at-research-bar">
      <Button size="sm" icon={task.research === 'complete' ? 'refresh' : 'spark'} disabled={b.disabled} onClick={start}>{b.label}</Button>
      {b.note ? <span className="at-research-status"><Icon name="spark" size={14} /> {b.note}</span> : null}
    </div>
  )
}

function PanelShell({ narrow, onClose, actions, footer, children }) {
  const ref = React.useRef(null)
  useSheetDismiss(ref, narrow, onClose)
  return (
    <aside ref={ref} className={cx('at-panel', narrow ? 'is-sheet' : 'is-side')} aria-label="Task">
      <div className="at-panel-bar">
        {narrow ? <span className="at-grabber" /> : null}
        <span className="at-flex" />
        {actions}
        <IconButton icon="x" label="Close" onClick={onClose} />
      </div>
      <div className={cx('at-panel-body at-scroll', footer && 'has-foot')} onScroll={markScrolled}>{children}</div>
      {footer ? <div className="at-panel-foot">{footer}</div> : null}
    </aside>
  )
}

// The title edits in place on a tap. Pressing and holding it (while it is not being edited) copies the task
// for chat instead: "Copied" shows as soon as the hold registers, and the clipboard write runs on release,
// because browsers only allow clipboard writes in a tap or release.
function TitleField({ value, done, onSave, onHold, onLongPress, copied }) {
  const [v, setV] = React.useState(value)
  const [editing, setEditing] = React.useState(false)
  const [armed, setArmed] = React.useState(false)
  const ref = React.useRef(null)
  const press = React.useRef(null)
  React.useEffect(() => setV(value), [value])
  React.useLayoutEffect(() => {
    const el = ref.current
    if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' }
  }, [v])
  const commit = () => { const t = v.replace(/\s+/g, ' ').trim(); if (t && t !== value) onSave(t); else setV(value) }

  const cancelPress = () => {
    if (press.current) clearTimeout(press.current.timer)
    press.current = null
    setArmed(false)
  }
  const down = (e) => {
    if (editing || (e.pointerType === 'mouse' && e.button !== 0)) return
    const p = { x: e.clientX, y: e.clientY, armed: false, timer: 0 }
    p.timer = setTimeout(() => { p.armed = true; setArmed(true); onHold() }, 450)
    press.current = p
  }
  // Once the hold registers, small finger movement no longer cancels it.
  const move = (e) => {
    const p = press.current
    if (p && !p.armed && Math.hypot(e.clientX - p.x, e.clientY - p.y) > 8) cancelPress()
  }
  // If the browser takes over the touch after the hold registered, keep it so touchend can still copy.
  const pointerCancel = () => { if (!(press.current && press.current.armed)) cancelPress() }
  const release = (e) => {
    const p = press.current
    if (!p) return
    const fire = p.armed
    cancelPress()
    if (fire) {
      e.preventDefault()
      press.current = { swallowClick: true }
      onLongPress()
    }
  }
  // A tap starts editing. Focus happens here, inside the tap, so phones open the keyboard.
  const click = (e) => {
    if (press.current && press.current.swallowClick) { press.current = null; e.preventDefault(); return }
    if (editing) return
    const el = e.currentTarget
    el.readOnly = false
    el.focus()
    setEditing(true)
  }
  return (
    <div className="at-title-wrap">
    <textarea ref={ref} rows={1} className={cx('at-title-input', done && 'is-done', armed && 'is-armed', !editing && 'is-idle')}
              value={v} aria-label="Title" readOnly={!editing}
              title={editing ? undefined : 'Tap to edit. Press and hold to copy for chat.'}
              onChange={(e) => setV(e.target.value)}
              onFocus={() => { if (!editing && !press.current) setEditing(true) }}
              onBlur={() => { setEditing(false); commit() }}
              onPointerDown={down} onPointerMove={move} onPointerUp={release} onPointerCancel={pointerCancel}
              onTouchEnd={(e) => { if (press.current && press.current.armed) release(e) }}
              onClick={click}
              onContextMenu={(e) => { if (!editing) e.preventDefault() }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() }
                if (e.key === 'Escape') { e.preventDefault(); setV(value); e.currentTarget.blur() }
              }} />
      {copied ? <span className="at-copied" role="status"><Icon name="check" size={13} strokeWidth={2.4} />Copied</span> : null}
    </div>
  )
}

function SummaryField({ value, onSave }) {
  const [v, setV] = React.useState(value)
  const ref = React.useRef(null)
  React.useEffect(() => setV(value), [value])
  React.useLayoutEffect(() => {
    const el = ref.current
    if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' }
  }, [v])
  return (
    <textarea ref={ref} rows={1} className="at-summary-input" value={v} placeholder="Add a short summary"
              aria-label="Summary" onChange={(e) => setV(e.target.value)}
              onBlur={() => { const t = v.trim(); if (t !== value.trim()) onSave(t) }}
              onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); setV(value); e.currentTarget.blur() } }} />
  )
}

function BodyView({ task, onEdit, onToggle }) {
  const { sections, managed: allManaged } = React.useMemo(() => splitSections(task.body || ''), [task.body])
  // The plugin keeps "Current state" in a managed block; older or hand-made tasks use a heading.
  const stateBlock = allManaged.find((m) => /current-state/.test(m.name))
  const managed = allManaged.filter((m) => m !== stateBlock)
  const state = stateBlock ? { title: 'Current state', text: stateBlock.text, start: 0, managed: true }
    : sections.find((s) => /^current state$/i.test(s.title))
  const rest = sections.filter((s) => s !== state)
  // Research (and other Hermes-managed blocks) sit just above the Log, which stays last.
  const logAt = rest.findIndex((s) => /^log$/i.test((s.title || '').trim()))
  const before = logAt >= 0 ? rest.slice(0, logAt) : rest
  const after = logAt >= 0 ? rest.slice(logAt) : []
  const renderSection = (s) => renderBlocks(parseBlocks(s.text), { onToggle: (line, checked) => onToggle(s.start + line, checked) })
  const hasContent = sections.some((s) => s.text.trim())
  return (
    <div className="at-body">
      <div className="at-body-bar">
        <span className="at-body-label">Notes</span>
        <span className="at-flex" />
        <Button size="sm" variant="ghost" icon="edit" onClick={onEdit}>Edit</Button>
      </div>
      {state && state.text.trim() ? (
        <div className="at-state">
          <div className="at-state-label">Current state</div>
          <div className="at-md">{state.managed ? renderBlocks(parseBlocks(state.text)) : renderSection(state)}</div>
        </div>
      ) : null}
      {!hasContent && !managed.length ? <button type="button" className="at-empty-notes" onClick={onEdit}>Add notes</button> : null}
      {before.map((s, i) => <BodySection key={`b${i}`} s={s} render={renderSection} />)}
      {managed.map((m, i) => (
        <Disclosure key={`m${i}`} title={managedTitle(m.name)} defaultOpen={managedTitle(m.name) === 'Research'} className="at-fold" right={<Icon name="spark" size={13} />}>
          <div className="at-md">{renderBlocks(parseBlocks(m.text))}</div>
        </Disclosure>
      ))}
      {after.map((s, i) => <BodySection key={`a${i}`} s={s} render={renderSection} />)}
    </div>
  )
}

function BodySection({ s, render }) {
  return s.folded ? (
    <Disclosure title={s.title} className="at-fold">
      <div className="at-md">{render(s)}</div>
    </Disclosure>
  ) : (
    <div className="at-section">
      {s.title && !/^notes$/i.test(s.title) ? <h3 className="at-section-title">{s.title}</h3> : null}
      <div className="at-md">{render(s)}</div>
    </div>
  )
}

function BodyEditor({ task, onSave, onDone, onStale, flushRef }) {
  const toast = useToast()
  const parts = React.useMemo(() => extractManaged(task.body || ''), []) // eslint-disable-line react-hooks/exhaustive-deps
  const baseRev = React.useRef(task.revision) // the file version this editor's text was built from
  const inFlight = React.useRef(Promise.resolve(true))
  const [text, setText] = React.useState(parts.editable)
  const [status, setStatus] = React.useState('saved') // saved | dirty | saving | error
  const latest = React.useRef(text)
  const saved = React.useRef(parts.editable)
  const timer = React.useRef(null)
  const ref = React.useRef(null)

  const save = React.useCallback(() => {
    clearTimeout(timer.current)
    // Chain onto any save still running, so each one uses the revision the previous one produced.
    inFlight.current = inFlight.current.then(async () => {
      const body = latest.current
      if (body === saved.current) { setStatus((st) => (st === 'error' ? st : 'saved')); return true }
      setStatus('saving')
      try {
        const t = await onSave(rebuildBody(body, parts.top, parts.bottom), baseRev.current)
        baseRev.current = t.revision
        saved.current = body
        setStatus(latest.current === body ? 'saved' : 'dirty')
        return true
      } catch (err) {
        setStatus('error')
        if (err.code === 'stale_revision') onStale()
        toast(describeError(err), { tone: 'error' })
        return false
      }
    })
    return inFlight.current
  }, [onSave, onStale, toast, parts])
  React.useEffect(() => {
    if (!flushRef) return undefined
    flushRef.current = save
    return () => { flushRef.current = null }
  }, [flushRef, save])
  const changedElsewhere = task.revision && baseRev.current && task.revision !== baseRev.current && status !== 'saving'

  React.useEffect(() => { if (ref.current) ref.current.focus() }, [])
  React.useEffect(() => () => clearTimeout(timer.current), [])

  const change = (v) => {
    setText(v)
    latest.current = v
    setStatus('dirty')
    clearTimeout(timer.current)
    timer.current = setTimeout(save, 1500)
  }
  const done = async () => { if (await save()) onDone() }
  return (
    <div className="at-body is-editing">
      <div className="at-body-bar">
        <span className="at-body-label">Notes</span>
        <span className={cx('at-save', `is-${status}`)}>
          {status === 'saving' ? 'Saving…' : status === 'saved' ? 'Saved' : status === 'error' ? 'Not saved' : 'Editing'}
        </span>
        <span className="at-flex" />
        {status === 'error' ? <Button size="sm" variant="ghost" onClick={onDone}>Discard changes</Button> : null}
        {status === 'error' && !changedElsewhere ? <Button size="sm" onClick={save}>Retry</Button> : null}
        <Button size="sm" variant="primary" onClick={done}>Done</Button>
      </div>
      {changedElsewhere ? (
        <div className="at-banner at-tone-late"><Icon name="alert" size={15} />
          <span className="at-flex">This task changed while you were editing. Your text is kept here and will not overwrite it. Copy what you need, then choose Discard changes to see the latest version.</span></div>
      ) : null}
      <textarea ref={ref} className="at-editor" value={text} spellCheck
                onChange={(e) => change(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save() }
                  if (e.key === 'Escape') { e.preventDefault(); done() }
                }} />
      <div className="at-editor-hint">Markdown. Saves as you type.{parts.top.length + parts.bottom.length ? ' Research added by Hermes is kept as it is.' : ''}</div>
    </div>
  )
}
