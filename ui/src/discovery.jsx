// Discovery: each run, its proposals and what it changed on its own. One click turns a proposal into
// a task, applies it to the existing task it matched, or dismisses it.
import React from 'react'
import * as D from './lib/dates.js'
import { describeError } from './api.js'
import { useApp } from './store.js'
import { AreaDot, Button, DatePicker, Disclosure, Icon, IconButton, Menu, Segmented, Spinner, cx, useOverlay, useToast } from './ui.jsx'

export const pendingCount = (runs) => (runs || []).reduce((n, r) =>
  n + (r.proposals || []).filter((p) => p.state === 'pending' && !p.expired).length, 0)

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

export function DiscoveryView({ runs, error, loading, reload }) {
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
  if (!all.length) {
    return <Empty icon="spark" title="No discovery runs yet"
                  text={<>Discovery reads the sources you choose and proposes tasks. To start one, ask Hermes:<br /><q>Set up a daily digest from my email and Slack at 7 AM.</q></>} />
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

function Empty({ icon, title, text, action }) {
  return (
    <div className="at-scroll at-disco">
      <div className="at-emptystate">
        <span className="at-emptystate-icon"><Icon name={icon} size={22} /></span>
        <h2>{title}</h2>
        <p>{text}</p>
        {action}
      </div>
    </div>
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
  const targets = p.targets || []
  const multi = p.kind === 'selection' || targets.length > 1
  const [mode, setMode] = React.useState(p.kind === 'new' || !targets.length ? 'create' : 'update')
  const [target, setTarget] = React.useState(targets.length === 1 ? targets[0].task_id : null)
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

  const additions = [].concat(p.new_information || []).filter(Boolean)
  const links = [].concat(p.source_links || []).filter(Boolean)
  const uncertain = p.research_disposition === 'uncertain'
  return (
    <div className={cx('at-prop', p.expired && 'is-expired')}>
      <div className="at-prop-head">
        <span className="at-prop-ref">{p.ref}</span>
        <h3 className="at-prop-title">{p.title}</h3>
        <IconButton icon="x" label="Dismiss" className="at-prop-dismiss" onClick={dismiss} disabled={!!busy || readOnly} />
      </div>
      {p.current_understanding ? <p className="at-prop-text">{p.current_understanding}</p> : null}
      {p.substantive_next_action ? (
        <div className="at-prop-next"><span className="at-prop-label">Next</span><span>{p.substantive_next_action}</span></div>
      ) : null}
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
                <span className="at-target-title">{t.title}</span>
                <span className="at-target-meta">
                  {t.area ? <><AreaDot area={t.area} />{t.area}</> : null}
                  {D.taskDate(t) ? <span>{D.relativeDay(D.taskDate(t), today)}</span> : null}
                  {t.status && t.status !== 'open' ? <span>{t.status}</span> : null}
                </span>
              </span>
              <button type="button" className="at-link" onClick={(e) => { e.preventDefault(); actions.open(t.task_id) }}>Open</button>
            </label>
          ))}
          {additions.length ? (
            <div className="at-prop-addition"><span className="at-prop-label">Would add</span>
              <ul>{additions.map((a, i) => <li key={i}>{a}</li>)}</ul></div>
          ) : null}
        </div>
      ) : additions.length ? (
        <ul className="at-prop-list">{additions.map((a, i) => <li key={i}>{a}</li>)}</ul>
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
