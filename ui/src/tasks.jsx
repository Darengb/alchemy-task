// Task views: rows, day lists (with the overdue section on today), month, week, day and the
// phone "scroll of days", plus the toolbar that switches between them.
import React from 'react'
import * as D from './lib/dates.js'
import { fittingRows } from './lib/month.js'
import { useDrag } from './lib/dnd.js'
import { useApp, useStore } from './store.js'
import { AreaDot, Button, Check, DatePicker, Disclosure, Icon, IconButton, Menu, Segmented, Spinner, cx, quickDates, useOverlay } from './ui.jsx'

const PRIO = { urgent: 0, high: 1, normal: 2, low: 3 }
export const isDone = (t) => t.status === 'done' || t.status === 'cancelled'
const byPriority = (a, b) => (PRIO[a.priority] ?? 2) - (PRIO[b.priority] ?? 2) || a.title.localeCompare(b.title)

// ------------------------------------------------------------------ selectors

/** Group the loaded tasks by the day they sit on, applying the area filter. */
export function useTaskIndex() {
  const { store, prefs } = useApp()
  const byId = useStore(store, selById)
  const today = useStore(store, selToday)
  return React.useMemo(() => {
    const days = {}
    const overdue = []
    for (const t of Object.values(byId)) {
      if (prefs.area && t.area !== prefs.area) continue
      const d = D.taskDate(t)
      if (!d) continue
      if (!isDone(t) && today && d < today) overdue.push(t)
      ;(days[d] || (days[d] = [])).push(t)
    }
    for (const k of Object.keys(days)) days[k].sort((a, b) => Number(isDone(a)) - Number(isDone(b)) || byPriority(a, b))
    overdue.sort((a, b) => D.taskDate(b).localeCompare(D.taskDate(a)) || byPriority(a, b))
    return { days, overdue, today }
  }, [byId, today, prefs.area])
}
const selById = (s) => s.byId
const selToday = (s) => s.today

// ------------------------------------------------------------------ row

export function TaskRow({ task, from, compact, showDate, selected }) {
  const { actions, today } = useApp()
  const { bind } = useDrag()
  const overlay = useOverlay()
  const done = isDone(task)
  const overdue = !done && D.taskDate(task) && D.taskDate(task) < today
  const dueDiffers = task.due && task.scheduled && task.due !== task.scheduled
  const researching = task.research === 'pending' || task.research === 'running'
  const openMenu = (e) => {
    e.stopPropagation()
    overlay.open(e.currentTarget, (close) => <RowMenu task={task} close={close} />, { width: 236, align: 'end' })
  }
  return (
    <div className={cx('at-row', compact && 'is-compact', done && 'is-done', selected && 'is-selected', overdue && 'is-late')}
         {...bind(task, from)} onClick={() => { overlay.close(); actions.open(task.task_id) }}
         onKeyDown={(e) => {
           if (e.key === 'Enter') { overlay.close(); actions.open(task.task_id) }
           if (e.key === ' ' && e.target === e.currentTarget) { e.preventDefault(); actions.toggle(task) }
         }}
         tabIndex={0} role="button" aria-label={task.title} data-task={task.task_id}>
      <Check checked={done} onChange={() => actions.toggle(task)} label={done ? 'Mark not done' : 'Mark done'}
             size={compact ? 'sm' : 'md'} tone={overdue || task.priority === 'urgent' || task.priority === 'high' ? 'high' : undefined} />
      <div className="at-row-main">
        <div className="at-row-title" title={compact ? task.title : undefined}>{task.title}</div>
        {compact ? null : (
          <div className="at-row-meta">
            {task.area ? <span className="at-meta-area"><AreaDot area={task.area} />{task.area}</span> : null}
            {showDate ? <span className={cx('at-meta-date', overdue && 'is-late')}>{D.relativeDay(D.taskDate(task), today)}</span> : null}
            {dueDiffers ? <span className="at-meta-due">due {D.relativeDay(task.due, today)}</span> : null}
            {task.priority === 'urgent' || task.priority === 'high' ? <span className="at-meta-prio">{task.priority}</span> : null}
            {task.status === 'waiting' ? <span className="at-meta-status">waiting</span> : null}
            {task.status === 'in-progress' ? <span className="at-meta-status is-active">in progress</span> : null}
            {researching ? <span className="at-meta-research"><Icon name="spark" size={12} />researching</span> : null}
          </div>
        )}
      </div>
      {compact ? null : <IconButton icon="more" label="Task actions" className="at-row-more" onClick={openMenu} data-no-drag="" />}
    </div>
  )
}

function RowMenu({ task, close }) {
  const { actions, today } = useApp()
  const [picking, setPicking] = React.useState(false)
  if (picking) {
    return <DatePicker value={D.taskDate(task)} today={today} onPick={(d) => actions.move(task, d)} close={close} />
  }
  const items = quickDates(today).slice(0, 3).map((q) => ({
    label: q.label, hint: q.hint, icon: 'cal', run: () => actions.move(task, q.date),
  })).filter((it, i) => quickDates(today)[i].date !== D.taskDate(task))
  return (
    <div className="at-menu" role="menu">
      <div className="at-menu-label">Move to</div>
      <Menu items={items} close={close} />
      <button type="button" className="at-menu-item" onClick={() => setPicking(true)}>
        <Icon name="cal" size={15} /><span className="at-flex">Pick a date…</span>
      </button>
      <div className="at-menu-sep" />
      <Menu close={close} items={[
        { label: isDone(task) ? 'Mark not done' : 'Mark done', icon: 'check', run: () => actions.toggle(task) },
        { label: 'Open', icon: 'arrowR', run: () => actions.open(task.task_id) },
      ]} />
    </div>
  )
}

// ------------------------------------------------------------------ day list

export function DayList({ date, tasks = [], overdue = [], compact, empty = 'Nothing planned', showAdd }) {
  const { today, prefs, selectedId } = useApp()
  const { drag } = useDrag()
  const isToday = date === today
  const visible = prefs.hideDone ? tasks.filter((t) => !isDone(t)) : tasks
  const doneHidden = tasks.length - visible.length
  return (
    <div className={cx('at-daylist', drag && drag.over === date && 'is-over')} data-at-drop={date}>
      {isToday && overdue.length ? <OverdueSection tasks={overdue} /> : null}
      {visible.map((t) => <TaskRow key={t.task_id} task={t} from={date} compact={compact} selected={selectedId === t.task_id} />)}
      {!visible.length && !(isToday && overdue.length) ? (
        <div className="at-empty-day">{doneHidden ? `${doneHidden} done` : empty}</div>
      ) : null}
      {showAdd ? <QuickAdd date={date} /> : null}
      {drag && drag.over === date && drag.from !== date ? <div className="at-drop-hint">Move to {D.relativeDay(date, today)}</div> : null}
    </div>
  )
}

export function OverdueSection({ tasks, defaultOpen = false }) {
  const { actions, today, selectedId } = useApp()
  return (
    <Disclosure className="at-overdue" tone="late" title="Overdue" count={tasks.length} defaultOpen={defaultOpen}
                right={<span className="at-link" role="button" tabIndex={0} data-no-drag=""
                             onClick={(e) => { e.stopPropagation(); actions.moveMany(tasks, today) }}>Move all to today</span>}>
      {tasks.map((t) => <TaskRow key={t.task_id} task={t} from={D.taskDate(t)} showDate selected={selectedId === t.task_id} />)}
    </Disclosure>
  )
}

export function QuickAdd({ date, autoFocus, onDone }) {
  const { actions, meta, prefs } = useApp()
  const [title, setTitle] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [open, setOpen] = React.useState(!!autoFocus)
  const ref = React.useRef(null)
  React.useEffect(() => { if (open && ref.current) ref.current.focus() }, [open])
  if (!open) {
    return (
      <button type="button" className="at-add" onClick={() => setOpen(true)} data-no-drag="">
        <Icon name="plus" size={14} /> Add a task
      </button>
    )
  }
  const submit = async () => {
    const t = title.trim()
    if (!t) { setOpen(false); onDone && onDone(); return }
    setBusy(true)
    const ok = await actions.create({ title: t, date, area: prefs.area || meta.default_area || undefined })
    setBusy(false)
    if (ok) { setTitle(''); if (ref.current) ref.current.focus() }
  }
  return (
    <form className="at-add-form" data-no-drag="" onSubmit={(e) => { e.preventDefault(); submit() }}>
      <span className="at-check at-check-md is-ghost" aria-hidden="true" />
      <input ref={ref} className="at-add-input" value={title} placeholder="New task" disabled={busy}
             onChange={(e) => setTitle(e.target.value)}
             onKeyDown={(e) => { if (e.key === 'Escape') { setTitle(''); setOpen(false); onDone && onDone() } }}
             onBlur={() => { if (!title.trim()) { setOpen(false); onDone && onDone() } }} />
      {busy ? <Spinner /> : null}
    </form>
  )
}

// ------------------------------------------------------------------ month

export function MonthView({ anchor, narrow }) {
  const { today, selectedId } = useApp()
  const { days, overdue } = useTaskIndex()
  const overlay = useOverlay()
  const { drag } = useDrag()
  const weeks = D.monthGrid(anchor)
  const month = anchor.slice(0, 7)
  const [picked, setPicked] = React.useState(null)
  if (narrow) {
    const sel = picked && picked.slice(0, 7) === month ? picked : (today.slice(0, 7) === month ? today : D.startOfMonth(anchor))
    return (
      <div className="at-scroll at-mmonth">
        <div className="at-mmonth-dows">{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((x, i) => <span key={i}>{x}</span>)}</div>
        <div className="at-mmonth-grid">
          {weeks.flat().map((d) => {
            const list = days[d] || []
            const open = list.filter((t) => !isDone(t)).length
            return (
              <button key={d} type="button" data-at-drop={d} onClick={() => setPicked(d)}
                      className={cx('at-mcell', d.slice(0, 7) !== month && 'is-out', d === today && 'is-today', d === sel && 'is-on',
                        drag && drag.over === d && 'is-over')}>
                <span className="at-mcell-num">{D.dayNum(d)}</span>
                <span className="at-mcell-dots">
                  {list.slice(0, 3).map((t) => <i key={t.task_id} className={isDone(t) ? 'is-done' : ''} />)}
                  {d === today && overdue.length ? <i className="is-late" /> : null}
                </span>
                {open > 3 ? <span className="at-mcell-more">+{open - 3}</span> : null}
              </button>
            )
          })}
        </div>
        <DaySection date={sel} tasks={days[sel] || []} overdue={sel === today ? overdue : []} />
      </div>
    )
  }
  return <DesktopMonth weeks={weeks} month={month} days={days} overdue={overdue} today={today} selectedId={selectedId} drag={drag} overlay={overlay} />
}

function DesktopMonth({ weeks, month, days, overdue, today, selectedId, drag, overlay, picked, onPick }) {
  const expand = (date, el) => onPick ? onPick(date) : overlay.open(el, (close) => <DayPopover date={date} close={close} />, { width: 360 })
  const gridRef = React.useRef(null)
  const [cellW, setCellW] = React.useState(160)
  React.useLayoutEffect(() => {
    const el = gridRef.current
    if (!el) return undefined
    const ro = new ResizeObserver(() => setCellW(el.clientWidth / 7))
    ro.observe(el)
    return () => ro.disconnect()
  }, [weeks.length])
  return (
    <div className={cx("at-month", onPick && "at-week-strip")}>
      <div className="at-month-dows">{weeks[0].map((d) => <div key={d}>{D.dayName(d)}</div>)}</div>
      <div ref={gridRef} className="at-month-grid">
        {weeks.flat().map((d) => {
          const list = days[d] || []
          const isToday = d === today
          return (
            <div key={d} data-at-drop={d}
                 className={cx('at-cell', month && d.slice(0, 7) !== month && 'is-out', isToday && 'is-today', d < today && 'is-past',
                   drag && drag.over === d && 'is-over', picked === d && 'is-picked')}
                 tabIndex={onPick ? 0 : undefined} role={onPick ? 'button' : undefined}
                 aria-label={onPick ? `Select ${D.longDate(d)}` : undefined} aria-pressed={onPick ? picked === d : undefined}
                 onKeyDown={(e) => { if (onPick && e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onPick(d) } }}
                 onClick={(e) => { if (!e.target.closest('.at-row')) { if (onPick) onPick(d); else expand(d, e.currentTarget) } }}>
              <div className="at-cell-head">
                <span className="at-cell-num">{D.dayNum(d) === 1 ? `${D.monthName(d, 'short')} 1` : D.dayNum(d)}</span>
                {isToday && overdue.length ? (
                  <button type="button" className="at-chip at-tone-late" data-no-drag="" title={`${overdue.length} overdue`}
                          onClick={(e) => { e.stopPropagation(); expand(d, e.currentTarget.closest('.at-cell')) }}>
                    {cellW < 140 ? `${overdue.length} late` : `${overdue.length} overdue`}
                  </button>
                ) : null}
              </div>
              <MonthTasks tasks={list} date={d} selectedId={selectedId} expand={expand} />
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Measure the actual list box and rendered controls, including when a sidebar changes its width.
function MonthTasks({ tasks, date, selectedId, expand }) {
  const ref = React.useRef(null)
  const [fit, setFit] = React.useState(1)
  React.useLayoutEffect(() => {
    const el = ref.current
    const measure = () => {
      const row = el.querySelector('.at-row')
      const more = el.querySelector('.at-cell-more')
      const gap = parseFloat(getComputedStyle(el).rowGap) || 0
      setFit(fittingRows(tasks.length, el.getBoundingClientRect().height, row?.getBoundingClientRect().height || 24,
        more.getBoundingClientRect().height, gap))
    }
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    measure()
    return () => ro.disconnect()
  }, [tasks.length])
  const more = Math.max(0, tasks.length - fit)
  return <div ref={ref} className="at-cell-list is-tight">
    {tasks.slice(0, fit).map((t) => <TaskRow key={t.task_id} task={t} from={date} compact selected={selectedId === t.task_id} />)}
    <button type="button" className="at-cell-more" data-no-drag="" style={{ visibility: more ? 'visible' : 'hidden' }}
      tabIndex={more ? 0 : -1} aria-hidden={!more}
      onClick={(e) => { e.stopPropagation(); expand(date, e.currentTarget.closest('.at-cell')) }}>+{more} more</button>
  </div>
}

function DayPopover({ date, close }) {
  const { today } = useApp()
  const { days, overdue } = useTaskIndex()
  return (
    <div className="at-daypop">
      <div className="at-daypop-head">
        <div>
          <div className="at-daypop-title">{D.relativeDay(date, today) === 'Today' ? 'Today' : D.dayName(date, 'long')}</div>
          <div className="at-muted">{D.longDate(date)}</div>
        </div>
        <IconButton icon="x" label="Close" onClick={close} />
      </div>
      <div className="at-daypop-body">
        <DayList date={date} tasks={days[date] || []} overdue={date === today ? overdue : []} showAdd />
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ week

export function WeekView({ anchor, narrow, onStep }) {
  const { today } = useApp()
  const { days, overdue } = useTaskIndex()
  const start = D.startOfWeek(anchor)
  const dates = D.range(start, D.addDays(start, 6))
  if (narrow) {
    return <PhoneWeek dates={dates} days={days} overdue={overdue} today={today} onStep={onStep} />
  }
  return <DesktopWeek dates={dates} days={days} overdue={overdue} today={today} />
}

function DesktopWeek({ dates, days, overdue, today }) {
  const { selectedId } = useApp()
  const { drag } = useDrag()
  const overlay = useOverlay()
  const [picked, setPicked] = React.useState(null)
  const sel = picked && dates.includes(picked) ? picked : (dates.includes(today) ? today : dates[0])
  return <div className="at-desktop-week at-scroll">
    <DesktopMonth weeks={[dates]} month={null} days={days} overdue={overdue} today={today}
      selectedId={selectedId} drag={drag} overlay={overlay} picked={sel} onPick={setPicked} />
    <DayView anchor={sel} />
  </div>
}

// Phone week: a strip of 7 day tiles (the phone month's tiles), the picked day's tasks below. Swipe the
// strip sideways, or use the toolbar arrows, to change the week.
function PhoneWeek({ dates, days, overdue, today, onStep }) {
  const { drag } = useDrag()
  const [picked, setPicked] = React.useState(null)
  const sel = picked && dates.includes(picked) ? picked : (dates.includes(today) ? today : dates[0])
  const swipe = React.useRef(null)
  return (
    <div className="at-scroll at-mmonth at-mweek">
      <div className="at-mmonth-dows">{dates.map((d) => <span key={d}>{D.dayName(d).slice(0, 1)}</span>)}</div>
      <div className="at-mmonth-grid"
           onTouchStart={(e) => { const t = e.touches[0]; swipe.current = { x: t.clientX, y: t.clientY } }}
           onTouchEnd={(e) => {
             const s0 = swipe.current; swipe.current = null
             if (!s0 || !onStep) return
             const t = e.changedTouches[0]
             const dx = t.clientX - s0.x
             if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(t.clientY - s0.y)) onStep(dx < 0 ? 1 : -1)
           }}>
        {dates.map((d) => {
          const list = days[d] || []
          const open = list.filter((t) => !isDone(t)).length
          return (
            <button key={d} type="button" data-at-drop={d} onClick={() => setPicked(d)}
                    className={cx('at-mcell', d === today && 'is-today', d === sel && 'is-on', drag && drag.over === d && 'is-over')}>
              <span className="at-mcell-num">{D.dayNum(d)}</span>
              <span className="at-mcell-dots">
                {list.slice(0, 3).map((t) => <i key={t.task_id} className={isDone(t) ? 'is-done' : ''} />)}
                {d === today && overdue.length ? <i className="is-late" /> : null}
              </span>
              {open > 3 ? <span className="at-mcell-more">+{open - 3}</span> : null}
            </button>
          )
        })}
      </div>
      <DaySection date={sel} tasks={days[sel] || []} overdue={sel === today ? overdue : []} />
    </div>
  )
}

// ------------------------------------------------------------------ day and scroll of days

export function DayView({ anchor }) {
  const { today } = useApp()
  const { days, overdue } = useTaskIndex()
  return (
    <div className="at-scroll at-dayview">
      <div className="at-dayview-inner">
        <header className="at-dayview-head">
          <h2>{D.relativeDay(anchor, today) === 'Today' ? 'Today' : D.dayName(anchor, 'long')}</h2>
          <div className="at-muted">{D.longDate(anchor)}</div>
        </header>
        <DayList date={anchor} tasks={days[anchor] || []} overdue={anchor === today ? overdue : []} showAdd />
      </div>
    </div>
  )
}

function DaySection({ date, tasks, overdue }) {
  const { today } = useApp()
  const rel = D.relativeDay(date, today)
  const named = rel === 'Today' || rel === 'Tomorrow' || rel === 'Yesterday'
  const empty = !tasks.length && !overdue.length
  return (
    <section className={cx('at-daysec', date === today && 'is-today', empty && 'is-empty')}>
      <header className="at-daysec-head">
        <span className="at-daysec-title">{named ? rel : D.dayName(date, 'long')}</span>
        <span className="at-muted">{D.shortDate(date, today).replace(/^\w+,\s*/, '')}</span>
      </header>
      <DayList date={date} tasks={tasks} overdue={overdue} showAdd={!empty || date === today} />
    </section>
  )
}

export function DayScroll({ anchor, onReachEnd, length }) {
  const { today } = useApp()
  const { days, overdue } = useTaskIndex()
  const dates = D.range(anchor, D.addDays(anchor, length - 1))
  const sentinel = React.useRef(null)
  React.useEffect(() => {
    const el = sentinel.current
    if (!el) return undefined
    const io = new IntersectionObserver((es) => { if (es[0].isIntersecting) onReachEnd() }, { rootMargin: '400px' })
    io.observe(el)
    return () => io.disconnect()
  }, [onReachEnd])
  return (
    <div className="at-scroll at-days">
      {dates.map((d) => <DaySection key={d} date={d} tasks={days[d] || []} overdue={d === today ? overdue : []} />)}
      <div ref={sentinel} className="at-sentinel" />
    </div>
  )
}

// ------------------------------------------------------------------ toolbar + view switch

export function TasksView({ narrow }) {
  const { store, prefs, setPrefs, meta, today } = useApp()
  const overlay = useOverlay()
  const view = prefs.view || (narrow ? 'day' : 'week')
  const [anchor, setAnchor] = React.useState(today)
  const [scrollLen, setScrollLen] = React.useState(21)
  const growScroll = React.useCallback(() => setScrollLen((n) => Math.min(n + 14, 120)), [])
  React.useEffect(() => { if (!anchor && today) setAnchor(today) }, [today, anchor])
  const a = anchor || today

  const range = React.useMemo(() => {
    if (!a) return null
    if (view === 'month') { const w = D.monthGrid(a); return [w[0][0], w[w.length - 1][6]] }
    if (view === 'week') { const s = D.startOfWeek(a); return [s, D.addDays(s, 6)] }
    if (narrow) return [a, D.addDays(a, scrollLen - 1)]
    return [a, a]
  }, [a, view, narrow, scrollLen])

  React.useEffect(() => {
    if (!range) return
    store.loadRange(range[0], range[1]).catch(() => {})
    store.loadOverdue().catch(() => {})
  }, [range && range[0], range && range[1]]) // eslint-disable-line react-hooks/exhaustive-deps

  const step = (n) => {
    if (view === 'month') setAnchor(D.addMonths(a, n))
    else if (view === 'week') setAnchor(D.addDays(a, 7 * n))
    else setAnchor(D.addDays(a, n))
  }
  React.useEffect(() => {
    const key = (e) => {
      if (e.target.closest && e.target.closest('input, textarea, [contenteditable]')) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (k === 't') setAnchor(today)
      else if (k === 'd') setPrefs({ view: 'day' })
      else if (k === 'w') setPrefs({ view: 'week' })
      else if (k === 'm') setPrefs({ view: 'month' })
      else if (e.key === 'ArrowLeft') step(-1)
      else if (e.key === 'ArrowRight') step(1)
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })

  if (!a) return <div className="at-loading"><Spinner size={18} /></div>
  const periodText = view === 'day' ? D.periodLabel('month', a, today) : D.periodLabel(view, a, today)
  const areas = meta.areas || []
  const areaMenu = (e) => overlay.open(e.currentTarget, (close) => (
    <Menu close={close} items={[
      { label: 'All areas', icon: prefs.area ? undefined : 'check', run: () => setPrefs({ area: '' }) },
      '-',
      ...areas.map((ar) => ({ label: ar, icon: prefs.area === ar ? 'check' : undefined, run: () => setPrefs({ area: ar }) })),
      '-',
      { label: prefs.hideDone ? 'Show completed' : 'Hide completed', run: () => setPrefs({ hideDone: !prefs.hideDone }) },
    ]} />
  ), { width: 200, align: 'end' })
  const addMenu = (e) => overlay.open(e.currentTarget, (close) => (
    <div className="at-pop-add"><QuickAdd date={view === 'day' ? a : today} autoFocus onDone={close} /></div>
  ), { width: 320, align: 'end' })

  return (
    <div className={cx('at-tasks', `is-${view}`)}>
      <div className="at-toolbar">
        <div className="at-toolbar-nav">
          <Button variant="ghost" size="sm" onClick={() => setAnchor(today)} disabled={a === today && view !== 'month'}>Today</Button>
          <IconButton icon="chevL" label="Previous" onClick={() => step(-1)} />
          <IconButton icon="chevR" label="Next" onClick={() => step(1)} />
          <h1 className="at-period">
            {periodText}
            {view !== 'week' && !periodText.includes(a.slice(0, 4)) ? <span className="at-period-year">{a.slice(0, 4)}</span> : null}
          </h1>
        </div>
        <div className="at-toolbar-right">
          <Segmented label="View" value={view} onChange={(v) => setPrefs({ view: v })}
                     options={[{ value: 'day', label: 'Day' }, { value: 'week', label: 'Week' }, { value: 'month', label: 'Month' }]} />
          <button type="button" className={cx('at-filter', prefs.area && 'is-on')} onClick={areaMenu}>
            {prefs.area ? <AreaDot area={prefs.area} /> : null}
            <span>{prefs.area || 'All areas'}</span>
            <Icon name="chevD" size={14} />
          </button>
          {narrow ? null : <Button variant="primary" size="sm" icon="plus" onClick={addMenu}>Add</Button>}
        </div>
      </div>
      <div className="at-viewport">
        {view === 'month' ? <MonthView anchor={a} narrow={narrow} /> : null}
        {view === 'week' ? <WeekView anchor={a} narrow={narrow} onStep={step} /> : null}
        {view === 'day' && narrow ? <DayScroll anchor={a} length={scrollLen} onReachEnd={growScroll} /> : null}
        {view === 'day' && !narrow ? <DayView anchor={a} /> : null}
      </div>
      {narrow ? <PhoneComposer date={view === 'day' ? a : today} /> : null}
    </div>
  )
}

// ------------------------------------------------------------------ phone composer

/**
 * The phone's add button and the composer it opens. The composer sits above the keyboard. Its input is
 * always in the page, so the button can focus it during the tap itself: iOS only opens the keyboard for
 * focus that happens inside the user's gesture.
 */
function PhoneComposer({ date: initialDate }) {
  const { actions, meta, prefs, today } = useApp()
  const overlay = useOverlay()
  const [open, setOpen] = React.useState(false)
  const [title, setTitle] = React.useState('')
  const [date, setDate] = React.useState(initialDate)
  const [area, setArea] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [lift, setLift] = React.useState(0)
  const input = React.useRef(null)

  // Keep the composer above the on-screen keyboard.
  React.useEffect(() => {
    const vv = window.visualViewport
    if (!open || !vv) { setLift(0); return undefined }
    const place = () => setLift(Math.max(0, Math.round(window.innerHeight - (vv.offsetTop + vv.height))))
    place()
    vv.addEventListener('resize', place)
    vv.addEventListener('scroll', place)
    return () => { vv.removeEventListener('resize', place); vv.removeEventListener('scroll', place) }
  }, [open])

  const start = () => {
    if (input.current) input.current.focus() // synchronously, inside the tap
    setDate(initialDate)
    setArea(prefs.area || meta.default_area || '')
    setOpen(true)
  }
  const close = () => {
    overlay.close()
    setOpen(false)
    setTitle('')
    if (input.current) input.current.blur()
  }
  const submit = async () => {
    const t = title.trim()
    if (!t || busy) return
    setBusy(true)
    const ok = await actions.create({ title: t, date, area: area || undefined })
    setBusy(false)
    if (ok) { setTitle(''); if (input.current) input.current.focus() }
  }
  const refocus = () => { if (input.current) input.current.focus() }
  const pickDate = (e) => overlay.open(e.currentTarget, (closePop) => (
    <DatePicker value={date} today={today} close={closePop} onPick={(d) => { setDate(d); refocus() }} />
  ), { width: 300 })
  const pickArea = (e) => overlay.open(e.currentTarget, (closePop) => (
    <Menu close={closePop} items={(meta.areas || []).map((ar) => ({
      label: ar, icon: ar === area ? 'check' : undefined, run: () => { setArea(ar); refocus() },
    }))} />
  ), { width: 220 })

  return (
    <>
      <button type="button" className={cx('at-fab', open && 'is-hidden')} aria-label="Add a task" onClick={start}>
        <Icon name="plus" size={24} />
      </button>
      {open ? <div className="at-composer-scrim" onClick={close} /> : null}
      <form className={cx('at-composer', open && 'is-open')} style={{ bottom: lift }} aria-hidden={!open} data-no-drag=""
            onSubmit={(e) => { e.preventDefault(); submit() }}>
        <div className="at-composer-row">
          <span className="at-check is-ghost" aria-hidden="true" />
          <input ref={input} className="at-composer-input" value={title} placeholder="New task" enterKeyHint="done"
                 tabIndex={open ? 0 : -1} readOnly={busy} aria-label="New task title"
                 onChange={(e) => setTitle(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Escape') close() }} />
          {busy ? <Spinner /> : null}
        </div>
        <div className="at-composer-bar">
          <button type="button" className="at-field" onClick={pickDate} tabIndex={open ? 0 : -1}>
            <Icon name="cal" size={15} /><span>{D.relativeDay(date, today)}</span>
          </button>
          {(meta.areas || []).length ? (
            <button type="button" className="at-field" onClick={pickArea} tabIndex={open ? 0 : -1}>
              <AreaDot area={area} /><span>{area || 'No area'}</span>
            </button>
          ) : null}
          <span className="at-flex" />
          <Button variant="ghost" size="sm" onClick={close} tabIndex={open ? 0 : -1}>Done</Button>
          <button type="submit" className="at-composer-send" aria-label="Add task" disabled={!title.trim() || busy} tabIndex={open ? 0 : -1}>
            <Icon name="arrowR" size={18} strokeWidth={2.2} />
          </button>
        </div>
      </form>
    </>
  )
}
