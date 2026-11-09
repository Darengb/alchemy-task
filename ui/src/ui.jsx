// Small UI kit shared by both hosts. Overlays (menus, pickers) render at the app root through
// the overlay host, so no scroll container can clip them and no portal API is needed.
import React from 'react'
import * as D from './lib/dates.js'

// ------------------------------------------------------------------ icons
const P = {
  check: 'M5 12.5l4.2 4.2L19 7',
  chevL: 'M15 18l-6-6 6-6',
  chevR: 'M9 6l6 6-6 6',
  chevD: 'M6 9l6 6 6-6',
  gear: 'M12 15.2a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4z M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z',
  x: 'M6 6l12 12M18 6L6 18',
  plus: 'M12 5v14M5 12h14',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  cal: 'M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z',
  spark: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z',
  link: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5',
  alert: 'M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  refresh: 'M20 11a8 8 0 10-2.3 5.7M20 5v6h-6',
  inbox: 'M4 13l2.5-7h11L20 13M4 13v5a1 1 0 001 1h14a1 1 0 001-1v-5M4 13h4l1.5 2.5h5L16 13h4',
  edit: 'M4 20h4L19 9l-4-4L4 16v4z M13.5 6.5l4 4',
  grip: 'M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01',
  arrowR: 'M5 12h14M13 6l6 6-6 6',
  undo: 'M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11',
  dot: 'M12 12h.01',
  list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
  clock: 'M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z',
  play: 'M7 5l12 7-12 7z',
}

export function Icon({ name, size = 16, className = '', strokeWidth = 1.8 }) {
  return (
    <svg className={'at-icon ' + className} width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={P[name] || P.dot} />
    </svg>
  )
}

export const cx = (...xs) => xs.filter(Boolean).join(' ')

// ------------------------------------------------------------------ basics
export function Button({ variant = 'default', size, icon, children, className, ...rest }) {
  return (
    <button type="button" className={cx('at-btn', `at-btn-${variant}`, size && `at-btn-${size}`, className)} {...rest}>
      {icon ? <Icon name={icon} size={size === 'sm' ? 14 : 16} /> : null}
      {children ? <span>{children}</span> : null}
    </button>
  )
}

export function IconButton({ icon, label, className, size = 16, ...rest }) {
  return (
    <button type="button" className={cx('at-iconbtn', className)} aria-label={label} title={label} {...rest}>
      <Icon name={icon} size={size} />
    </button>
  )
}

export function Check({ checked, onChange, label, size = 'md', tone }) {
  return (
    <button type="button" role="checkbox" aria-checked={!!checked} aria-label={label}
            className={cx('at-check', `at-check-${size}`, checked && 'is-on', tone && `at-tone-${tone}`)}
            data-no-drag="" onClick={(e) => { e.stopPropagation(); onChange(!checked) }}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={P.check} /></svg>
    </button>
  )
}

export function Segmented({ value, options, onChange, label }) {
  return (
    <div className="at-seg" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={value === o.value}
                className={cx('at-seg-item', value === o.value && 'is-on')} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Spinner({ size = 14 }) {
  return <span className="at-spinner" style={{ width: size, height: size }} aria-label="Loading" />
}

export function Disclosure({ title, count, defaultOpen = false, tone, children, right, className }) {
  const [open, setOpen] = React.useState(defaultOpen)
  return (
    <section className={cx('at-disc', open && 'is-open', tone && `at-tone-${tone}`, className)}>
      <button type="button" className="at-disc-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="chevR" size={14} className="at-disc-chev" />
        <span className="at-disc-title">{title}</span>
        {count !== undefined ? <span className="at-count">{count}</span> : null}
        <span className="at-flex" />
        {right}
      </button>
      {open ? <div className="at-disc-body">{children}</div> : null}
    </section>
  )
}

export function AreaDot({ area }) {
  return <span className="at-areadot" style={{ '--at-area': areaColor(area) }} title={area} />
}

const AREA_HUES = [212, 152, 28, 280, 340, 188, 48, 252]
export function areaColor(area) {
  if (!area) return 'var(--at-faint)'
  let h = 0
  for (const c of String(area)) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return `hsl(${AREA_HUES[h % AREA_HUES.length]} 62% 56%)`
}

// ------------------------------------------------------------------ overlays
export const OverlayCtx = React.createContext(null)
export const useOverlay = () => React.useContext(OverlayCtx)

/** Overlay host: one popover at a time, placed against its anchor in root coordinates. */
export function OverlayHost({ rootRef, children }) {
  const [ov, setOv] = React.useState(null)
  const close = React.useCallback(() => setOv((cur) => { if (cur && cur.onClose) cur.onClose(); return null }), [])
  const open = React.useCallback((anchor, render, opts = {}) => setOv({ anchor, render, ...opts }), [])
  const api = React.useMemo(() => ({ open, close }), [open, close])
  return (
    <OverlayCtx.Provider value={api}>
      {children}
      {ov ? <Popover rootRef={rootRef} {...ov} close={close} /> : null}
    </OverlayCtx.Provider>
  )
}

function Popover({ rootRef, anchor, render, close, align = 'start', width }) {
  const ref = React.useRef(null)
  const [pos, setPos] = React.useState(null)
  React.useLayoutEffect(() => {
    const root = rootRef.current
    const el = ref.current
    if (!root || !el || !anchor) return
    const place = () => {
      const r = root.getBoundingClientRect()
      const a = anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : anchor
      const w = el.offsetWidth
      const hgt = el.offsetHeight
      let left = (align === 'end' ? a.right - w : a.left) - r.left
      left = Math.max(8, Math.min(left, r.width - w - 8))
      let top = a.bottom - r.top + 6
      if (top + hgt > r.height - 8 && a.top - r.top - hgt - 6 > 8) top = a.top - r.top - hgt - 6
      top = Math.max(8, Math.min(top, r.height - hgt - 8))
      setPos({ left, top })
    }
    place()
    const ro = new ResizeObserver(place)
    ro.observe(el)
    return () => ro.disconnect()
  }, [anchor, rootRef, align])
  React.useEffect(() => {
    const down = (e) => {
      if (ref.current && !ref.current.contains(e.target) && !(anchor && anchor.contains && anchor.contains(e.target))) close()
    }
    const key = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close() } }
    document.addEventListener('pointerdown', down, true)
    document.addEventListener('keydown', key, true)
    return () => { document.removeEventListener('pointerdown', down, true); document.removeEventListener('keydown', key, true) }
  }, [anchor, close])
  return (
    <div ref={ref} className="at-pop" role="dialog" style={{ left: pos ? pos.left : -9999, top: pos ? pos.top : -9999, width }}>
      {render(close)}
    </div>
  )
}

export function Menu({ items, close }) {
  return (
    <div className="at-menu" role="menu">
      {items.filter(Boolean).map((it, i) => it === '-' ? <div key={i} className="at-menu-sep" /> : (
        <button key={i} type="button" role="menuitem" className={cx('at-menu-item', it.danger && 'is-danger')}
                onClick={() => { close(); it.run() }}>
          {it.icon ? <Icon name={it.icon} size={15} /> : <span className="at-menu-pad" />}
          <span className="at-flex">{it.label}</span>
          {it.hint ? <span className="at-menu-hint">{it.hint}</span> : null}
        </button>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ date picker
export function quickDates(today) {
  return [
    { label: 'Today', date: today, hint: D.dayName(today) },
    { label: 'Tomorrow', date: D.addDays(today, 1), hint: D.dayName(D.addDays(today, 1)) },
    { label: 'Next Monday', date: D.nextWeekday(today, 0), hint: D.shortDate(D.nextWeekday(today, 0), today).replace(/^\w+,\s*/, '') },
    { label: 'In a week', date: D.addDays(today, 7), hint: D.shortDate(D.addDays(today, 7), today).replace(/^\w+,\s*/, '') },
  ]
}

export function DatePicker({ value, today, onPick, onClear, close, extra }) {
  const [month, setMonth] = React.useState(D.startOfMonth(value || today))
  const weeks = D.monthGrid(month)
  const pick = (d) => { onPick(d); close && close() }
  return (
    <div className="at-dp">
      <div className="at-dp-quick">
        {quickDates(today).map((q) => (
          <button key={q.label} type="button" className={cx('at-dp-q', value === q.date && 'is-on')} onClick={() => pick(q.date)}>
            <span>{q.label}</span><span className="at-muted">{q.hint}</span>
          </button>
        ))}
      </div>
      <div className="at-dp-head">
        <span className="at-dp-title">{D.monthName(month)} {month.slice(0, 4) !== today.slice(0, 4) ? month.slice(0, 4) : ''}</span>
        <IconButton icon="chevL" label="Previous month" onClick={() => setMonth(D.addMonths(month, -1))} />
        <IconButton icon="chevR" label="Next month" onClick={() => setMonth(D.addMonths(month, 1))} />
      </div>
      <div className="at-dp-grid" role="grid">
        {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => <span key={i} className="at-dp-dow">{d}</span>)}
        {weeks.flat().map((d) => (
          <button key={d} type="button" onClick={() => pick(d)}
                  className={cx('at-dp-day', d.slice(0, 7) !== month.slice(0, 7) && 'is-out', d === today && 'is-today', d === value && 'is-on')}>
            {D.dayNum(d)}
          </button>
        ))}
      </div>
      {onClear || extra ? (
        <div className="at-dp-foot">
          {extra}
          <span className="at-flex" />
          {onClear ? <Button size="sm" variant="ghost" onClick={() => { onClear(); close && close() }}>Clear</Button> : null}
        </div>
      ) : null}
    </div>
  )
}

// ------------------------------------------------------------------ toasts
export const ToastCtx = React.createContext(null)
export const useToast = () => React.useContext(ToastCtx)

export function ToastHost({ children }) {
  const [toasts, setToasts] = React.useState([])
  const seq = React.useRef(0)
  const dismiss = React.useCallback((id) => setToasts((ts) => ts.filter((t) => t.id !== id)), [])
  const show = React.useCallback((message, opts = {}) => {
    const id = ++seq.current
    setToasts((ts) => [...ts.slice(-2), { id, message, ...opts }])
    setTimeout(() => dismiss(id), opts.duration || (opts.undo ? 6500 : opts.tone === 'error' ? 7000 : 3500))
    return id
  }, [dismiss])
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div className="at-toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={cx('at-toast', t.tone && `at-tone-${t.tone}`)}>
            {t.tone === 'error' ? <Icon name="alert" size={15} /> : null}
            <span className="at-flex">{t.message}</span>
            {t.undo ? <button type="button" className="at-toast-act" onClick={() => { dismiss(t.id); t.undo() }}>Undo</button> : null}
            {t.action ? <button type="button" className="at-toast-act" onClick={() => { dismiss(t.id); t.action.run() }}>{t.action.label}</button> : null}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
