// Drag a task onto a day. Mouse: starts after a few pixels of movement. Touch: starts after a long
// press (so ordinary scrolling still works), then blocks scrolling while dragging. Drop targets are
// elements with data-at-drop="YYYY-MM-DD". Lists scroll automatically near their edges.
import React from 'react'

const DragCtx = React.createContext(null)
export const useDrag = () => React.useContext(DragCtx)

const LONG_PRESS_MS = 380
const MOVE_SLOP = 6

function dropDateAt(x, y) {
  const el = document.elementFromPoint(x, y)
  const target = el && el.closest('[data-at-drop]')
  return target ? target.getAttribute('data-at-drop') : null
}

function scrollParent(el) {
  for (let n = el; n && n !== document.body; n = n.parentElement) {
    const s = getComputedStyle(n)
    if (/(auto|scroll)/.test(s.overflowY) && n.scrollHeight > n.clientHeight) return n
  }
  return document.scrollingElement
}

export function DragProvider({ onDrop, children }) {
  const [drag, setDrag] = React.useState(null) // { task, x, y, over, w }
  const dragRef = React.useRef(null)
  const suppressClick = React.useRef(false)
  const raf = React.useRef(0)

  const ghost = React.useRef(null)
  const update = (patch) => {
    const prevOver = dragRef.current && dragRef.current.over
    dragRef.current = dragRef.current ? { ...dragRef.current, ...patch } : null
    const d = dragRef.current
    if (d && ghost.current) ghost.current.style.transform = `translate(${d.x + 12}px, ${d.y - 20}px)`
    if (d && d.over !== prevOver) setDrag(d) // re-render only when the hovered day changes
  }

  const autoScroll = (x, y) => {
    cancelAnimationFrame(raf.current)
    const el = document.elementFromPoint(x, y)
    const sc = el && scrollParent(el)
    if (!sc) return
    const r = sc === document.scrollingElement ? { top: 0, bottom: window.innerHeight } : sc.getBoundingClientRect()
    const edge = 56
    const dy = y < r.top + edge ? -Math.ceil((r.top + edge - y) / 4) : y > r.bottom - edge ? Math.ceil((y - (r.bottom - edge)) / 4) : 0
    if (!dy) return
    const step = () => {
      if (!dragRef.current) return
      sc.scrollTop += dy
      raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
  }

  const finish = (x, y, cancelled) => {
    cancelAnimationFrame(raf.current)
    const d = dragRef.current
    dragRef.current = null
    setDrag(null)
    if (ghost.current) { ghost.current.remove(); ghost.current = null }
    document.documentElement.classList.remove('at-dragging')
    if (!d) return
    suppressClick.current = true
    setTimeout(() => { suppressClick.current = false }, 50)
    const date = cancelled ? null : dropDateAt(x, y)
    if (date && date !== d.from) onDrop(d.task, date)
  }

  const begin = (task, from, x, y, w) => {
    dragRef.current = { task, from, x, y, over: from, w }
    setDrag(dragRef.current)
    const g = document.createElement('div')
    g.className = 'at-drag-ghost at-vars'
    g.textContent = task.title
    g.style.width = `${Math.min(w || 260, 300)}px`
    g.style.transform = `translate(${x + 12}px, ${y - 20}px)`
    document.body.appendChild(g)
    ghost.current = g
    document.documentElement.classList.add('at-dragging')
    if (navigator.vibrate) { try { navigator.vibrate(8) } catch { /* not allowed */ } }
  }

  /** Spread onto a draggable row: {...bind(task, fromDate)} */
  const bind = React.useCallback((task, from) => ({
    onPointerDown: (e) => {
      if (e.pointerType !== 'mouse' || e.button !== 0) return
      if (e.target.closest('button, input, textarea, a, [data-no-drag]')) return
      const sx = e.clientX
      const sy = e.clientY
      const w = e.currentTarget.getBoundingClientRect().width
      const move = (ev) => {
        if (!dragRef.current) {
          if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < MOVE_SLOP) return
          begin(task, from, ev.clientX, ev.clientY, w)
        }
        update({ x: ev.clientX, y: ev.clientY, over: dropDateAt(ev.clientX, ev.clientY) })
        autoScroll(ev.clientX, ev.clientY)
      }
      const up = (ev) => {
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', up)
        window.removeEventListener('keydown', key)
        if (dragRef.current) finish(ev.clientX, ev.clientY, false)
      }
      const key = (ev) => { if (ev.key === 'Escape') { up({ clientX: -1, clientY: -1 }); finish(-1, -1, true) } }
      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', up)
      window.addEventListener('keydown', key)
    },
    onTouchStart: (e) => {
      if (e.target.closest('button, input, textarea, a, [data-no-drag]')) return
      const t0 = e.touches[0]
      const sx = t0.clientX
      const sy = t0.clientY
      const w = e.currentTarget.getBoundingClientRect().width
      let last = { x: sx, y: sy }
      let timer = setTimeout(() => { timer = null; begin(task, from, last.x, last.y, w) }, LONG_PRESS_MS)
      const move = (ev) => {
        const t = ev.touches[0]
        last = { x: t.clientX, y: t.clientY }
        if (!dragRef.current) {
          if (timer && Math.hypot(t.clientX - sx, t.clientY - sy) > MOVE_SLOP) { clearTimeout(timer); timer = null; cleanup() }
          return
        }
        ev.preventDefault()
        update({ x: t.clientX, y: t.clientY, over: dropDateAt(t.clientX, t.clientY) })
        autoScroll(t.clientX, t.clientY)
      }
      const end = (ev) => {
        if (timer) clearTimeout(timer)
        cleanup()
        if (dragRef.current) {
          ev.preventDefault()
          finish(last.x, last.y, ev.type === 'touchcancel')
        }
      }
      const cleanup = () => {
        document.removeEventListener('touchmove', move)
        document.removeEventListener('touchend', end)
        document.removeEventListener('touchcancel', end)
      }
      document.addEventListener('touchmove', move, { passive: false })
      document.addEventListener('touchend', end)
      document.addEventListener('touchcancel', end)
    },
    onClickCapture: (e) => { if (suppressClick.current) { e.stopPropagation(); e.preventDefault() } },
    onContextMenu: (e) => { if (dragRef.current) e.preventDefault() },
  }), [])

  const value = React.useMemo(() => ({ drag, bind }), [drag, bind])
  React.useEffect(() => () => { if (ghost.current) ghost.current.remove() }, [])
  return React.createElement(DragCtx.Provider, { value }, children)
}
