// Discovery: each run, its proposals and what it changed on its own. One click turns a proposal into
// a task, applies it to the existing task it matched, or dismisses it.
import React from 'react'
import * as D from './lib/dates.js'
import { describeError } from './api.js'
import { useApp } from './store.js'
import { AreaDot, Button, DatePicker, Disclosure, Icon, IconButton, Menu, Segmented, Spinner, copyText, cx, useOverlay, useToast } from './ui.jsx'

export { pendingCount, discoveryBadge } from './lib/discovery.js'
import { nextRunLabel } from './lib/discovery.js'
import { digestField, fullResearch } from './lib/digestText.js'
import { elapsedLabel, runProgressLabel } from './lib/runProgress.js'

const titleCase = (s) => String(s || '').replace(/[-_]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

function runTime(r) {
  const t = r.time
  const d = typeof t === 'number' ? new Date(t * (t < 1e12 ? 1000 : 1)) : new Date(t)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

function sourcesLine(r) {
  const cov = r.coverage || []
  if (!cov.length) return r.sources_checked && r.sources_checked.length ? `${r.sources_checked.length} sources` : ''
  const ok = cov.filter((c) => c.status === 'complete').length
  return ok === cov.length ? `${ok} ${ok === 1 ? 'source' : 'sources'} checked` : `${ok} of ${cov.length} sources checked`
}

export function DiscoveryView({ runs, streams, error, loading, reload }) {
  const { today } = useApp()
  const [filter, setFilter] = React.useState('waiting')
  if (error && error.code === 'not_found') {
    return <Empty icon="inbox" title="Discovery is not available yet"
                  text="This version of Alchemy Task has no discovery runs to show. Update the plugin to review discovery here." />
  }
  if (!runs && loading) return <div className="at-loading"><Spinner size={18} /></div>
  if (error && !runs) {
    return <Empty icon="alert" title="Could not load discovery" text={describeError(error)} action={<Button onClick={reload}>Try again</Button>} />
  }
  const all = runs || []
  const configured = Array.isArray(streams) && streams.length > 0
  if (!all.length && configured) {
    // Set up but not run yet: show what it will read and when, not the setup prompt.
    return (
      <div className="at-scroll at-disco">
        <div className="at-disco-inner">
          <div className="at-disco-bar"><h1 className="at-period">Discovery</h1><span className="at-flex" />
            <IconButton icon="refresh" label="Refresh" onClick={reload} /></div>
          <SourcesBar streams={streams} reload={reload} />
          <RunningCards streams={streams} />
          <div className="at-caughtup">
            <Icon name="clock" size={18} />
            <div>
              <div className="at-caughtup-title">Waiting for the first run</div>
              <div className="at-muted">{streams.map((s) => `${titleCase(s.name)}: ${s.when || 'scheduled'}`).join(' · ')}</div>
            </div>
          </div>
        </div>
      </div>
    )
  }
  if (!all.length) {
    return <Empty icon="spark" title="No discovery runs yet"
                  text="Discovery reads the sources you choose and proposes tasks. Setup takes a few minutes in chat."
                  action={<SetupPrompt />} after={<DiscoveryExplainer />} />
  }
  const needs = (r) => (r.summary ? r.summary.pending : (r.proposals || []).filter((p) => p.state === 'pending').length) > 0
    || (r.conflicts || []).length || (r.failures || []).length
  const shown = filter === 'waiting' ? all.filter(needs) : all
  const latest = all[0]
  return (
    <div className="at-scroll at-disco">
      <div className="at-disco-inner">
        <div className="at-disco-bar">
          <h1 className="at-period">Discovery</h1>
          <span className="at-flex" />
          <Segmented label="Show" value={filter} onChange={setFilter}
                     options={[{ value: 'waiting', label: 'Waiting for you' }, { value: 'all', label: 'All runs' }]} />
          <IconButton icon="refresh" label="Refresh" onClick={reload} />
        </div>
        {configured ? <SourcesBar streams={streams} reload={reload} /> : null}
        {configured ? <RunningCards streams={streams} /> : null}
        {!shown.length ? (
          <div className="at-caughtup">
            <Icon name="check" size={18} />
            <div>
              <div className="at-caughtup-title">All caught up</div>
              <div className="at-muted">Last run: {titleCase(latest.stream)}, {D.relativeDay(latest.day, today)} {runTime(latest)}</div>
            </div>
          </div>
        ) : null}
        {shown.map((r) => <RunCard key={r.run_id} run={r} filter={filter} reload={reload} />)}
      </div>
    </div>
  )
}

export const SETUP_PROMPT = 'Set up task discovery'
export const ADD_SOURCE_PROMPT = 'I want to add a new source to task discovery'

const SOURCE_ICONS = { email: 'inbox', chat: 'chat', transcript: 'list', meeting_notes: 'list', document: 'edit', tracker: 'check' }

// What discovery reads: one row per stream, each source with an icon for its type. "Add a source" reveals
// the message to send Hermes, with a copy button (sources are connected in chat, not here).
function SourcesBar({ streams, reload }) {
  const [adding, setAdding] = React.useState(false)
  const [starting, setStarting] = React.useState(null)
  // Streams started from here, until the server reports the run (or a few minutes pass without it).
  const [started, setStarted] = React.useState({})
  const { api } = useApp()
  const toast = useToast()
  const now = Date.now()
  const busy = (s) => s.running || starting === s.name || (started[s.name] && now - started[s.name] < 3 * 60 * 1000)
  const anyRunning = streams.some((s) => s.running) || Object.keys(started).length > 0
  React.useEffect(() => {
    // Poll while a run is in progress so the indicator clears (and new proposals appear) when it ends.
    if (!anyRunning || !reload) return undefined
    const id = setInterval(() => reload(), 20000)
    return () => clearInterval(id)
  }, [anyRunning, reload])
  React.useEffect(() => {
    // Once the server reports a started stream as running, it owns the indicator.
    const next = { ...started }
    let changed = false
    for (const s of streams) {
      if (next[s.name] && (s.running || Date.now() - next[s.name] > 3 * 60 * 1000)) { delete next[s.name]; changed = true }
    }
    if (changed) setStarted(next)
  }, [streams])
  const runNow = async (s) => {
    setStarting(s.name)
    try {
      const res = await api.runStream(s.name)
      toast(res.message || 'Discovery run started')
      setStarted((cur) => ({ ...cur, [s.name]: Date.now() }))
      if (reload) setTimeout(() => reload(), 3000)
    } catch (err) { toast(describeError(err), { tone: 'error' }) }
    setStarting(null)
  }
  const many = streams.length > 1
  return (
    <div className="at-sources">
      <div className="at-sources-rows">
        {streams.map((s) => (
          <div key={s.name} className="at-sources-row">
            <span className="at-sources-head">
              <span className="at-sources-label">{many ? `${titleCase(s.name)} reads` : 'Reads'}</span>
              {nextRunLabel(s.next_run_at) ? <span className="at-sources-next" title="Next scheduled run">// Next {nextRunLabel(s.next_run_at)}</span> : null}
            </span>
            <div className="at-sources-chips">
              {(s.sources || []).length ? (s.sources || []).map((src, i) => (
                <span key={`${src.name}-${i}`} className="at-source-chip" title={src.scope || src.name}>
                  <Icon name={SOURCE_ICONS[src.type] || 'dot'} size={12} />{src.name}
                </span>
              )) : <span className="at-muted">No sources yet</span>}
            </div>
            {busy(s) ? (
              <Button size="sm" className="at-sources-run is-running" disabled
                      title={`${titleCase(s.name)} discovery is running. Its digest posts to the stream's chat when it finishes.`}>
                <Spinner size={12} />{starting === s.name ? 'Starting…' : 'Running…'}
              </Button>
            ) : (
              <Button size="sm" icon="play" className="at-sources-run" disabled={!!starting}
                      onClick={() => runNow(s)} title={`Run ${titleCase(s.name)} discovery now`}>
                Run now
              </Button>
            )}
          </div>
        ))}
      </div>
      <Button size="sm" icon="plus" className="at-sources-add" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>Add a source</Button>
      {adding ? <CopyPrompt className="is-compact" text={ADD_SOURCE_PROMPT} /> : null}
    </div>
  )
}

// One card per stream with a run in progress: where it is (reading sources, researching, writing the
// digest) and how long it has run. The list polls while anything runs, so the card updates and then gives
// way to the finished run's card.
function RunningCards({ streams }) {
  const running = (streams || []).filter((s) => s.running && s.progress)
  const [, tick] = React.useState(0)
  React.useEffect(() => {
    if (!running.length) return undefined
    const id = setInterval(() => tick((n) => n + 1), 30000)
    return () => clearInterval(id)
  }, [running.length])
  return running.map((s) => {
    const { label, fraction } = runProgressLabel(s.progress)
    const elapsed = elapsedLabel(s.progress.started_at)
    const pct = fraction == null ? null : Math.round(fraction * 100)
    return (
      <article key={s.name} className="at-run at-run-live" aria-live="polite">
        <header className="at-run-head">
          <div>
            <div className="at-run-title">{titleCase(s.name)} discovery</div>
            <div className="at-run-sub"><span>Running now</span>{elapsed ? <span>{elapsed}</span> : null}</div>
          </div>
        </header>
        <div className="at-runbar-wrap">
          <div className={cx('at-runbar', pct == null && 'is-indeterminate')} role="progressbar" aria-label={label}
               aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct == null ? undefined : pct}>
            <span className="at-runbar-fill" style={pct == null ? undefined : { width: `${Math.max(3, pct)}%` }} />
          </div>
          <div className="at-runbar-label">{label}</div>
        </div>
      </article>
    )
  })
}

export function CopyPrompt({ text, className }) {
  const toast = useToast()
  const copy = async () => toast((await copyText(text)) ? 'Copied. Paste it into a chat with Hermes.' : 'Could not copy')
  return (
    <div className={cx('at-copy-prompt', className)}>
      <span className="at-setup-prompt-label"><Icon name="chat" size={15} /> Tell Hermes in chat</span>
      <div className="at-copy-prompt-row">
        <q className="at-copy-prompt-text">{text}</q>
        <Button size="sm" icon="clipboard" onClick={copy}>Copy</Button>
      </div>
    </div>
  )
}

// The one message that starts discovery setup, shown big enough that it cannot be missed. Click to copy.
export function SetupPrompt({ text = SETUP_PROMPT }) {
  const toast = useToast()
  const copy = async () => toast((await copyText(text)) ? 'Copied. Paste it into a chat with Hermes.' : 'Could not copy')
  return (
    <button type="button" className="at-setup-prompt" onClick={copy} title="Copy">
      <span className="at-setup-prompt-label"><Icon name="chat" size={17} /> Tell Hermes in chat</span>
      <span className="at-setup-prompt-text">{text}</span>
      <span className="at-setup-prompt-copy"><Icon name="clipboard" size={15} /> Copy</span>
    </button>
  )
}

function Empty({ icon, title, text, action, after }) {
  return (
    <div className="at-scroll at-disco">
      <div className="at-emptystate">
        <span className="at-emptystate-icon"><Icon name={icon} size={22} /></span>
        <h2>{title}</h2>
        <p>{text}</p>
        {action}
      </div>
      {after}
    </div>
  )
}

// Why set up discovery: what it is, how it works and what it catches. Shown only before setup.
const DISCO_STEPS = [
  { icon: 'inbox', title: 'It reads your sources', text: 'On the schedule you pick, it checks the email, chat, meeting transcripts and shared docs you approve.' },
  { icon: 'spark', title: 'It researches each ask', text: 'It works out what is being asked of you, whether a task already covers it, and what doing it will take.' },
  { icon: 'check', title: 'You decide', text: <>A short numbered digest lands in your chat. Reply <q>2 create, 4 skip</q> and the tasks appear, already researched.</> },
]

const DISCO_CATCHES = [
  { icon: 'inbox', source: 'Email', title: 'The reply you meant to send',
    quote: 'Could you send the updated rate sheet before Friday?', where: 'Arrived at 11:48 PM, under 40 other emails',
    task: 'Send the updated rate sheet to Harbor Market', due: 'Friday' },
  { icon: 'chat', source: 'Slack', title: 'Buried in a long thread',
    quote: 'Can you check the tin dimensions before we approve the proof?', where: 'Message 63 of 90 in #packaging',
    task: 'Check the tin dimensions before approving the proof', due: 'Today' },
  { icon: 'list', source: 'Meeting transcript', title: 'One ask among twenty',
    quote: ['Maya: Can someone own the vendor follow-up?', 'You: Sure, I will take it.'], where: 'From the transcript emailed after Tuesday\'s sync',
    task: 'Follow up with the vendor about the November order', due: 'Thursday' },
  { icon: 'edit', source: 'Shared doc', title: 'A comment that tagged you',
    quote: 'Please confirm the launch date in this section.', where: 'Comment in the spring launch plan',
    task: 'Confirm the launch date in the spring plan', due: 'Next week' },
]

function DiscoveryExplainer() {
  return (
    <section className="at-explainer" aria-label="What discovery does">
      <div className="at-explainer-head">
        <span className="at-explainer-kicker">Why set it up</span>
        <h3>A safety net for the asks that slip through</h3>
        <p>
          Every day, small requests get buried: a reply you meant to send, a favor asked halfway through a long
          thread, one ask among twenty in a meeting. Discovery finds the ones meant for you and offers them as tasks,
          so nothing quietly falls through the cracks.
        </p>
      </div>

      <ol className="at-explainer-steps">
        {DISCO_STEPS.map((s, i) => (
          <li key={s.title} className="at-explainer-step">
            <span className="at-explainer-num">{i + 1}</span>
            <span className="at-explainer-step-icon"><Icon name={s.icon} size={16} /></span>
            <strong>{s.title}</strong>
            <span className="at-explainer-step-text">{s.text}</span>
          </li>
        ))}
      </ol>

      <div className="at-explainer-sub">What it catches</div>
      <div className="at-explainer-grid">
        {DISCO_CATCHES.map((c) => (
          <article key={c.source} className="at-catch">
            <div className="at-catch-source"><Icon name={c.icon} size={14} /> {c.source}</div>
            <h4>{c.title}</h4>
            <blockquote>{[].concat(c.quote).map((line) => <span key={line}>{line}</span>)}</blockquote>
            <div className="at-catch-where">{c.where}</div>
            <div className="at-catch-task">
              <span className="at-catch-check" aria-hidden="true" />
              <span className="at-catch-task-text">{c.task}</span>
              <span className="at-catch-due">{c.due}</span>
            </div>
          </article>
        ))}
      </div>

      <p className="at-explainer-foot">
        <Icon name="check" size={14} /> Nothing becomes a task until you reply. Discovery only reads your sources: it never
        replies to anyone or changes anything in your email, chat or documents.
      </p>
    </section>
  )
}

function RunCard({ run, filter, reload }) {
  const { today } = useApp()
  const proposals = run.proposals || []
  const visible = filter === 'waiting' ? proposals.filter((p) => p.state === 'pending') : proposals
  const outcomes = (run.outcomes || []).filter((o) => o.status !== 'noop')
  const attention = [...(run.conflicts || []).map((c) => ({ ...c, kind: 'conflict' })), ...(run.failures || [])]
  const test = run.mode && run.mode !== 'production'
  return (
    <article className="at-run">
      <header className="at-run-head">
        <div>
          <div className="at-run-title">{titleCase(run.stream)}</div>
          <div className="at-run-sub">
            <span>{D.relativeDay(run.day, today)}{runTime(run) ? ` · ${runTime(run)}` : ''}</span>
            {sourcesLine(run) ? <span className={cx(run.degraded && 'is-late')}>{sourcesLine(run)}</span> : null}
            {test ? <span className="at-badge">Test run</span> : null}
          </div>
        </div>
        <span className="at-flex" />
        {run.summary && run.summary.pending ? <span className="at-count is-accent">{run.summary.pending} waiting</span> : null}
      </header>
      {visible.length ? (
        <div className="at-proposals">
          {visible.map((p) => <ProposalCard key={p.proposal_id} p={p} run={run} reload={reload} readOnly={test} />)}
        </div>
      ) : filter === 'all' && !proposals.length ? <div className="at-run-none">No new proposals in this run.</div> : null}
      {outcomes.length ? (
        <Disclosure title="Updated automatically" count={outcomes.length} className="at-run-fold">
          {outcomes.map((o) => <Outcome key={o.unit_id} o={o} run={run} reload={reload} />)}
        </Disclosure>
      ) : null}
      {attention.length ? (
        <Disclosure title="Needs attention" count={attention.length} tone="late" className="at-run-fold" defaultOpen>
          {attention.map((a, i) => (
            <div key={i} className="at-attn">
              <Icon name="alert" size={14} />
              <div>
                <div className="at-attn-title">{a.title || (a.kind === 'conflict' ? 'Several tasks match one item' : 'Research follow-up')}</div>
                <div className="at-muted">{a.kind === 'conflict' ? 'Nothing was changed. Ask Hermes which task this belongs to.' : a.reason}</div>
              </div>
            </div>
          ))}
        </Disclosure>
      ) : null}
      <Disclosure title="Run details" className="at-run-fold is-quiet">
        <div className="at-details">
          {(run.coverage || []).map((c, i) => (
            <div key={i} className="at-detail-row">
              <span className={cx('at-statusdot', c.status === 'complete' ? 'is-ok' : 'is-late')} />
              <span className="at-flex">{c.source_key || c.source || 'Source'}</span>
              <span className="at-muted">{c.status === 'complete' ? 'Checked' : c.status || 'Unknown'}</span>
            </div>
          ))}
          <div className="at-detail-row"><span className="at-muted">Run</span><span className="at-flex" /><span className="at-mono">{String(run.run_id).slice(0, 12)}</span></div>
          {run.delivery && run.delivery.state ? <div className="at-detail-row"><span className="at-muted">Digest</span><span className="at-flex" /><span>{deliveryLabel(run.delivery.state)}</span></div> : null}
        </div>
      </Disclosure>
    </article>
  )
}

const deliveryLabel = (s) => ({ delivered: 'Sent', host_pending: 'Sent by Hermes', prepared: 'Prepared', not_prepared: 'Not sent', unknown: 'Unknown', inflight: 'Sending' }[s] || s)

function Outcome({ o, run, reload }) {
  const { actions, api } = useApp()
  const toast = useToast()
  const [busy, setBusy] = React.useState(false)
  const resume = async () => {
    setBusy(true)
    try { await api.resume(run.run_id, o.unit_id); await reload() } catch (err) { toast(describeError(err), { tone: 'error' }) }
    setBusy(false)
  }
  const done = o.status === 'complete'
  return (
    <div className="at-outcome">
      <span className={cx('at-statusdot', done ? 'is-ok' : 'is-late')} />
      <button type="button" className="at-outcome-title" onClick={() => o.task_id && actions.open(o.task_id)}>{o.title}</button>
      <span className="at-flex" />
      {done ? <span className="at-muted">Updated</span> : o.resume_action ? (
        <Button size="sm" onClick={resume} disabled={busy}>{busy ? 'Finishing…' : 'Finish update'}</Button>
      ) : <span className="at-muted">{o.status}</span>}
    </div>
  )
}

// ------------------------------------------------------------------ proposal

function ProposalCard({ p, run, reload, readOnly }) {
  const { api, actions, today, meta, store } = useApp()
  const toast = useToast()
  const overlay = useOverlay()
  // Research order is kept; a recommended target (if any) is listed first and preselected.
  const targets = [...(p.targets || [])].sort((a, b) => (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0))
  const multi = p.kind === 'selection' || targets.length > 1
  const [mode, setMode] = React.useState(p.kind === 'new' || !targets.length ? 'create' : 'update')
  const recommended = targets.find((x) => x.recommended)
  const [target, setTarget] = React.useState(targets.length === 1 ? targets[0].task_id : recommended ? recommended.task_id : null)
  const streamAreas = (meta.streams || {})[run.stream] || []
  const [date, setDate] = React.useState(p.due || p.due_hint || today)
  const [area, setArea] = React.useState(p.area || (streamAreas.length === 1 ? streamAreas[0] : meta.default_area) || '')
  const [busy, setBusy] = React.useState(null)
  const [gone, setGone] = React.useState(false)

  if (p.state === 'approved' || p.state === 'complete') {
    const r = p.result || {}
    const finished = p.state === 'complete' || r.state === 'complete'
    return (
      <div className="at-prop is-resolved">
        <span className={cx('at-statusdot', finished ? 'is-ok' : 'is-late')} />
        <span className="at-prop-resolved">
          {r.operation === 'updated' ? 'Updated' : 'Created'}{' '}
          <button type="button" className="at-linkish" onClick={() => r.task_id && actions.open(r.task_id)}>{r.title || p.title}</button>
        </span>
        <span className="at-flex" />
        {finished ? <span className="at-muted">{p.ref}</span> : <span className="at-muted">Saving…</span>}
      </div>
    )
  }
  if (p.state === 'dismissed' || gone) {
    return <div className="at-prop is-resolved is-dismissed"><span className="at-prop-resolved">{p.title}</span><span className="at-flex" /><span className="at-muted">Dismissed</span></div>
  }

  const approve = async (choice) => {
    if (choice === 'create' && !area) { toast('Pick an area first.', { tone: 'error' }); return }
    const t = targets.find((x) => x.task_id === target)
    if (choice === 'update' && !t) { toast('Pick the task to update.', { tone: 'error' }); return }
    const body = choice === 'create' ? { choice, due: date, area } : { choice, target_task_id: t.task_id, expected_revision: t.revision }
    if (p.expired) body.allow_expired = true
    setBusy(choice)
    try {
      const res = await api.approve(p.proposal_id, body)
      const receipt = res.receipt || {}
      toast(choice === 'create' ? 'Task created' : 'Task updated', receipt.task_id ? { action: { label: 'Open', run: () => actions.open(receipt.task_id) } } : {})
      await reload()
      store.refresh()
    } catch (err) {
      toast(describeError(err), { tone: 'error' })
      if (err.code === 'already_resolved' || err.code === 'stale_revision') reload()
    }
    setBusy(null)
  }
  const dismiss = async () => {
    setBusy('dismiss')
    try {
      await api.dismiss(p.proposal_id)
      setGone(true)
      toast('Proposal dismissed')
      reload()
    } catch (err) { toast(describeError(err), { tone: 'error' }) }
    setBusy(null)
  }
  const pickDate = (e) => overlay.open(e.currentTarget, (close) => <DatePicker value={date} today={today} onPick={setDate} close={close} />, { width: 300 })
  const pickArea = (e) => overlay.open(e.currentTarget, (close) => (
    <Menu close={close} items={(meta.areas || []).map((ar) => ({ label: ar, icon: ar === area ? 'check' : undefined, run: () => setArea(ar) }))} />
  ), { width: 200 })

  const addition = digestField(p, 'digest_addition')
  const state = digestField(p, 'digest_current_state')
  const next = digestField(p, 'digest_next_action')
  const full = fullResearch(p)
  const subtasks = [].concat(p.subtasks || []).filter((x) => typeof x === 'string' && x.trim())
  const links = [].concat(p.source_links || []).filter(Boolean)
  const uncertain = p.research_disposition === 'uncertain'
  return (
    <div className={cx('at-prop', p.expired && 'is-expired')}>
      <div className="at-prop-head">
        <span className="at-prop-ref">{p.ref}</span>
        <h3 className="at-prop-title">{p.title}</h3>
        <IconButton icon="x" label="Dismiss" className="at-prop-dismiss" onClick={dismiss} disabled={!!busy || readOnly} />
      </div>
      {state ? <p className="at-prop-text">{state}</p> : null}
      {next ? (
        <div className="at-prop-next"><span className="at-prop-label">Next</span><span>{next}</span></div>
      ) : null}
      {subtasks.length ? (
        <ul className="at-prop-subtasks" style={{ margin: '6px 0 0 40px', paddingLeft: 18, fontSize: 13, lineHeight: 1.5, color: 'var(--at-fg2)' }}>
          {subtasks.slice(0, 5).map((x, i) => <li key={i}>{x}</li>)}
          {subtasks.length > 5 ? <li className="at-muted">+{subtasks.length - 5} more</li> : null}
        </ul>
      ) : null}
      {p.not_proposed_line ? <p className="at-prop-text at-muted" style={{ fontSize: 13 }}>{p.not_proposed_line}</p> : null}
      {uncertain ? (
        <div className="at-prop-uncertain"><Icon name="alert" size={14} />
          <span>{[].concat(p.uncertainty || []).join(' ') || 'Hermes was not sure about this one. Check it before you add it.'}</span></div>
      ) : null}
      {links.length ? (
        <div className="at-prop-links">{links.slice(0, 4).map((l, i) => <SourceLink key={i} href={l} />)}</div>
      ) : null}

      {targets.length ? (
        <div className={cx('at-prop-targets', mode === 'create' && 'is-muted')}>
          <div className="at-prop-label">{multi ? 'Could update one of these tasks' : 'May update an existing task'}</div>
          {targets.map((t) => (
            <label key={t.task_id} className={cx('at-target', target === t.task_id && mode === 'update' && 'is-on')}>
              {multi ? <input type="radio" name={p.proposal_id} checked={target === t.task_id && mode === 'update'}
                              onChange={() => { setTarget(t.task_id); setMode('update') }} /> : <Icon name="arrowR" size={14} />}
              <span className="at-target-main">
                <span className="at-target-title">{t.title}{t.recommended && multi ? <span className="at-chip" style={{ marginLeft: 6 }}>Recommended</span> : null}</span>
                <span className="at-target-meta">
                  {t.area ? <><AreaDot area={t.area} />{t.area}</> : null}
                  {D.taskDate(t) ? <span>{D.relativeDay(D.taskDate(t), today)}</span> : null}
                  {t.status && t.status !== 'open' ? <span>{t.status}</span> : null}
                </span>
              </span>
              <button type="button" className="at-link" onClick={(e) => { e.preventDefault(); actions.open(t.task_id) }}>Open</button>
            </label>
          ))}
          {addition ? (
            <div className="at-prop-addition"><span className="at-prop-label">Would add</span>
              <p>{addition}</p></div>
          ) : null}
        </div>
      ) : null}

      {full.length ? (
        <Disclosure title="Full research" className="at-prop-full is-quiet">
          {full.map((sec) => (
            <div key={sec.label} className="at-prop-full-sec">
              <div className="at-prop-label">{sec.label}</div>
              {sec.items ? <ul>{sec.items.map((a, i) => <li key={i}>{a}</li>)}</ul> : <p>{sec.text}</p>}
            </div>
          ))}
        </Disclosure>
      ) : null}

      <div className="at-prop-actions">
        {mode === 'create' ? (
          <>
            <button type="button" className="at-field" onClick={pickDate}><Icon name="cal" size={14} /><span>{D.relativeDay(date, today)}</span></button>
            <button type="button" className={cx('at-field', !area && 'is-late')} onClick={pickArea}><AreaDot area={area} /><span>{area || 'Pick area'}</span></button>
            <span className="at-flex" />
            {targets.length ? <Button variant="ghost" size="sm" onClick={() => setMode('update')} disabled={!!busy}>Update instead</Button> : null}
            <Button variant="primary" size="sm" icon="plus" onClick={() => approve('create')} disabled={!!busy || readOnly}>
              {busy === 'create' ? 'Creating…' : 'Create task'}
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" size="sm" onClick={() => setMode('create')} disabled={!!busy}>Create new instead</Button>
            <span className="at-flex" />
            <Button variant="primary" size="sm" icon="check" onClick={() => approve('update')} disabled={!!busy || !target || readOnly}>
              {busy === 'update' ? 'Updating…' : multi ? 'Update selected' : 'Update task'}
            </Button>
          </>
        )}
      </div>
      {p.expired ? <div className="at-prop-foot at-muted">Expired {D.relativeDay(p.expires, today).toLowerCase()}. You can still add it.</div> : null}
    </div>
  )
}

function SourceLink({ href }) {
  let label = href
  try {
    const u = new URL(href)
    const host = u.host.replace(/^www\./, '')
    label = /slack/.test(host) ? 'Slack' : /mail\.google|gmail/.test(host) ? 'Gmail' : /notion/.test(host) ? 'Notion' : /github/.test(host) ? 'GitHub' : host
  } catch { /* plain text */ }
  return <a className="at-srclink" href={href} target="_blank" rel="noreferrer noopener"><Icon name="link" size={12} />{label}</a>
}
