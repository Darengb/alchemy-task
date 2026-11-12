// ui/hosts/desktop.jsx
import React10 from "react";
import { host, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA } from "@hermes/plugin-sdk";

// ui/src/App.jsx
import React9 from "react";

// ui/src/lib/dates.js
var pad = (n) => String(n).padStart(2, "0");
function toISO(d) {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}
function parseISO(s) {
  const [y, m, d] = String(s).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function addDays(s, n) {
  const d = parseISO(s);
  d.setUTCDate(d.getUTCDate() + n);
  return toISO(d);
}
function addMonths(s, n) {
  const d = parseISO(s);
  const day = d.getUTCDate();
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + n);
  const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
  d.setUTCDate(Math.min(day, last));
  return toISO(d);
}
var weekday = (s) => (parseISO(s).getUTCDay() + 6) % 7;
function startOfWeek(s) {
  return addDays(s, -weekday(s));
}
function startOfMonth(s) {
  return s.slice(0, 8) + "01";
}
function endOfMonth(s) {
  const d = parseISO(startOfMonth(s));
  return toISO(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)));
}
function daysBetween(a, b) {
  return Math.round((parseISO(b) - parseISO(a)) / 864e5);
}
function range(start, end) {
  const out = [];
  for (let d = start; d <= end; d = addDays(d, 1)) out.push(d);
  return out;
}
function monthGrid(s) {
  const first = startOfWeek(startOfMonth(s));
  const last = addDays(startOfWeek(endOfMonth(s)), 6);
  const days = range(first, last);
  const weeks = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  return weeks;
}
var fmt = (s, opts) => parseISO(s).toLocaleDateString(void 0, { timeZone: "UTC", ...opts });
var dayName = (s, style = "short") => fmt(s, { weekday: style });
var monthName = (s, style = "long") => fmt(s, { month: style });
var dayNum = (s) => parseISO(s).getUTCDate();
function longDate(s) {
  return fmt(s, { weekday: "long", month: "long", day: "numeric" });
}
function shortDate(s, today) {
  const sameYear = !today || s.slice(0, 4) === today.slice(0, 4);
  return fmt(s, { weekday: "short", month: "short", day: "numeric", ...sameYear ? {} : { year: "numeric" } });
}
function relativeDay(s, today) {
  if (!s) return "";
  const diff = daysBetween(today, s);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  if (diff > 1 && diff < 7) return dayName(s, "long");
  return shortDate(s, today);
}
function nextWeekday(today, target) {
  const diff = (target - weekday(today) + 7) % 7 || 7;
  return addDays(today, diff);
}
function periodLabel(view, anchor, today) {
  if (view === "month") {
    return fmt(anchor, { month: "long", ...anchor.slice(0, 4) !== today.slice(0, 4) ? { year: "numeric" } : {} });
  }
  if (view === "week") {
    const a = startOfWeek(anchor);
    const b = addDays(a, 6);
    const sameMonth = a.slice(0, 7) === b.slice(0, 7);
    const left = fmt(a, { month: "short", day: "numeric" });
    const right = sameMonth ? String(dayNum(b)) : fmt(b, { month: "short", day: "numeric" });
    return `${left} \u2013 ${right}`;
  }
  return relativeDay(anchor, today) === "Today" ? "Today" : fmt(anchor, { weekday: "long", month: "short", day: "numeric" });
}
var taskDate = (t) => t.scheduled || t.due || null;

// ui/src/lib/dnd.js
import React from "react";
var DragCtx = React.createContext(null);
var useDrag = () => React.useContext(DragCtx);
var LONG_PRESS_MS = 380;
var MOVE_SLOP = 6;
function dropDateAt(x, y) {
  const el = document.elementFromPoint(x, y);
  const target = el && el.closest("[data-at-drop]");
  return target ? target.getAttribute("data-at-drop") : null;
}
function scrollParent(el) {
  for (let n = el; n && n !== document.body; n = n.parentElement) {
    const s = getComputedStyle(n);
    if (/(auto|scroll)/.test(s.overflowY) && n.scrollHeight > n.clientHeight) return n;
  }
  return document.scrollingElement;
}
function DragProvider({ onDrop, children }) {
  const [drag, setDrag] = React.useState(null);
  const dragRef = React.useRef(null);
  const suppressClick = React.useRef(false);
  const raf = React.useRef(0);
  const ghost = React.useRef(null);
  const update = (patch) => {
    const prevOver = dragRef.current && dragRef.current.over;
    dragRef.current = dragRef.current ? { ...dragRef.current, ...patch } : null;
    const d = dragRef.current;
    if (d && ghost.current) ghost.current.style.transform = `translate(${d.x + 12}px, ${d.y - 20}px)`;
    if (d && d.over !== prevOver) setDrag(d);
  };
  const autoScroll = (x, y) => {
    cancelAnimationFrame(raf.current);
    const el = document.elementFromPoint(x, y);
    const sc = el && scrollParent(el);
    if (!sc) return;
    const r = sc === document.scrollingElement ? { top: 0, bottom: window.innerHeight } : sc.getBoundingClientRect();
    const edge = 56;
    const dy = y < r.top + edge ? -Math.ceil((r.top + edge - y) / 4) : y > r.bottom - edge ? Math.ceil((y - (r.bottom - edge)) / 4) : 0;
    if (!dy) return;
    const step = () => {
      if (!dragRef.current) return;
      sc.scrollTop += dy;
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  };
  const finish = (x, y, cancelled) => {
    cancelAnimationFrame(raf.current);
    const d = dragRef.current;
    dragRef.current = null;
    setDrag(null);
    if (ghost.current) {
      ghost.current.remove();
      ghost.current = null;
    }
    document.documentElement.classList.remove("at-dragging");
    if (!d) return;
    suppressClick.current = true;
    setTimeout(() => {
      suppressClick.current = false;
    }, 50);
    const date = cancelled ? null : dropDateAt(x, y);
    if (date && date !== d.from) onDrop(d.task, date);
  };
  const begin = (task, from, x, y, w) => {
    dragRef.current = { task, from, x, y, over: from, w };
    setDrag(dragRef.current);
    const g = document.createElement("div");
    g.className = "at-drag-ghost at-vars";
    g.textContent = task.title;
    g.style.transform = `translate(${x + 12}px, ${y - 20}px)`;
    document.body.appendChild(g);
    ghost.current = g;
    document.documentElement.classList.add("at-dragging");
    if (navigator.vibrate) {
      try {
        navigator.vibrate(8);
      } catch {
      }
    }
  };
  const bind = React.useCallback((task, from) => ({
    onPointerDown: (e) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return;
      if (e.target.closest("button, input, textarea, a, [data-no-drag]")) return;
      const sx = e.clientX;
      const sy = e.clientY;
      const w = e.currentTarget.getBoundingClientRect().width;
      const move = (ev) => {
        if (!dragRef.current) {
          if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < MOVE_SLOP) return;
          begin(task, from, ev.clientX, ev.clientY, w);
        }
        update({ x: ev.clientX, y: ev.clientY, over: dropDateAt(ev.clientX, ev.clientY) });
        autoScroll(ev.clientX, ev.clientY);
      };
      const up = (ev) => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        window.removeEventListener("keydown", key);
        if (dragRef.current) finish(ev.clientX, ev.clientY, false);
      };
      const key = (ev) => {
        if (ev.key === "Escape") {
          up({ clientX: -1, clientY: -1 });
          finish(-1, -1, true);
        }
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
      window.addEventListener("keydown", key);
    },
    onTouchStart: (e) => {
      if (e.target.closest("button, input, textarea, a, [data-no-drag]")) return;
      const t0 = e.touches[0];
      const sx = t0.clientX;
      const sy = t0.clientY;
      const w = e.currentTarget.getBoundingClientRect().width;
      let last = { x: sx, y: sy };
      let timer = setTimeout(() => {
        timer = null;
        begin(task, from, last.x, last.y, w);
      }, LONG_PRESS_MS);
      const move = (ev) => {
        const t = ev.touches[0];
        last = { x: t.clientX, y: t.clientY };
        if (!dragRef.current) {
          if (timer && Math.hypot(t.clientX - sx, t.clientY - sy) > MOVE_SLOP) {
            clearTimeout(timer);
            timer = null;
            cleanup();
          }
          return;
        }
        ev.preventDefault();
        update({ x: t.clientX, y: t.clientY, over: dropDateAt(t.clientX, t.clientY) });
        autoScroll(t.clientX, t.clientY);
      };
      const end = (ev) => {
        if (timer) clearTimeout(timer);
        cleanup();
        if (dragRef.current) {
          ev.preventDefault();
          finish(last.x, last.y, ev.type === "touchcancel");
        }
      };
      const cleanup = () => {
        document.removeEventListener("touchmove", move);
        document.removeEventListener("touchend", end);
        document.removeEventListener("touchcancel", end);
      };
      document.addEventListener("touchmove", move, { passive: false });
      document.addEventListener("touchend", end);
      document.addEventListener("touchcancel", end);
    },
    onClickCapture: (e) => {
      if (suppressClick.current) {
        e.stopPropagation();
        e.preventDefault();
      }
    },
    onContextMenu: (e) => {
      if (dragRef.current) e.preventDefault();
    }
  }), []);
  const value = React.useMemo(() => ({ drag, bind }), [drag, bind]);
  React.useEffect(() => () => {
    if (ghost.current) ghost.current.remove();
  }, []);
  return React.createElement(DragCtx.Provider, { value }, children);
}

// ui/src/api.js
var ApiError = class extends Error {
  constructor(code, message, status = 0) {
    super(message || code);
    this.code = code || "error";
    this.status = status;
  }
};
function parseErrorBody(err) {
  const raw = err && (err.body || err.responseText || err.message || "");
  if (raw && typeof raw === "object") return raw;
  const text = String(raw);
  const at = text.indexOf("{");
  if (at >= 0) {
    try {
      return JSON.parse(text.slice(at));
    } catch {
    }
  }
  return null;
}
function toApiError(err) {
  if (err instanceof ApiError) return err;
  const body = parseErrorBody(err);
  const e = body && (body.error || body.detail);
  const status = err && err.status || 0;
  if (e && typeof e === "object") return new ApiError(e.code, e.message, status);
  if (typeof e === "string") return new ApiError(status === 404 ? "not_found" : "error", e, status);
  if (status === 404) return new ApiError("not_found", "Not found", 404);
  if (status === 0 || /network|failed to fetch|unreachable/i.test(String(err && err.message))) {
    return new ApiError("offline", "Hermes is not reachable right now.", status);
  }
  return new ApiError("error", err && err.message || "Something went wrong", status);
}
var qs = (params) => {
  const parts = Object.entries(params).filter(([, v]) => v !== void 0 && v !== null && v !== "" && v !== false).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v === true ? "1" : v)}`);
  return parts.length ? `?${parts.join("&")}` : "";
};
var enc = encodeURIComponent;
function makeTransport(send) {
  async function call(method, path, body) {
    let res;
    try {
      res = await send(method, path, body);
    } catch (err) {
      throw toApiError(err);
    }
    if (res && res.ok === false) {
      const e = res.error || {};
      throw new ApiError(e.code || res.needs || "error", e.message || res.message, 200);
    }
    return res;
  }
  return {
    // ---- tasks
    meta: () => call("GET", "/meta"),
    tasks: (from, to, { area, includeDone = true } = {}) => call("GET", "/tasks" + qs({ from, to, area, include_done: includeDone })),
    overdue: ({ area } = {}) => call("GET", "/overdue" + qs({ area })),
    task: (id) => call("GET", `/tasks/${enc(id)}`),
    patch: (id, changes) => call("PATCH", `/tasks/${enc(id)}`, changes),
    complete: (id) => call("POST", `/tasks/${enc(id)}/complete`, {}),
    reopen: (id) => call("POST", `/tasks/${enc(id)}/reopen`, {}),
    putBody: (id, body, expectedRevision) => call("PUT", `/tasks/${enc(id)}/body`, { body, expected_revision: expectedRevision }),
    create: (fields) => call("POST", "/tasks", fields),
    // Queue research (start, retry or refresh); the answer says whether the sweep starts now or later.
    research: (id) => call("POST", `/tasks/${enc(id)}/research`, {}),
    // Send to chat: desktop gets the note back to send in a new chat; other surfaces queue it for the gateway.
    handoff: (id, surface) => call("POST", `/tasks/${enc(id)}/handoff`, { surface }),
    handoffStatus: (handoffId) => call("GET", `/handoffs/${enc(handoffId)}`),
    // ---- discovery (routes owned by the discovery backend; see docs/discovery-backend-contract.md)
    runs: (params = {}) => call("GET", "/runs" + qs(params)),
    run: (runId) => call("GET", `/runs/${enc(runId)}`),
    approve: (proposalId, body) => call("POST", `/proposals/${enc(proposalId)}/approve`, body),
    dismiss: (proposalId) => call("POST", `/proposals/${enc(proposalId)}/dismiss`, {}),
    resume: (runId, unitId) => call("POST", `/runs/${enc(runId)}/units/${enc(unitId)}/resume`, {}),
    // ---- settings
    settings: () => call("GET", "/settings"),
    patchStream: (name, changes) => call("PATCH", `/settings/streams/${enc(name)}`, changes),
    runStream: (name) => call("POST", `/settings/streams/${enc(name)}/run`, {}),
    patchTaskSettings: (changes) => call("PATCH", "/settings/tasks", changes)
  };
}
function describeError(err) {
  const code = err && err.code;
  switch (code) {
    case "stale_revision":
    case "retry":
      return "This task changed somewhere else. Reload it to see the latest version.";
    case "offline":
      return "Hermes is not reachable right now. Your change was not saved.";
    case "needs_due":
    case "due":
      return "Pick a date first.";
    case "needs_area":
    case "area":
      return "Pick an area first.";
    case "already_resolved":
      return "This proposal was already handled.";
    case "expired":
      return "This proposal expired.";
    case "not_production":
      return "This was a test run, so it cannot change tasks.";
    case "not_found":
      return "It is no longer there. It may have been moved or deleted.";
    default:
      return err && err.message || "Something went wrong.";
  }
}

// ui/src/store.js
import React2 from "react";
function createTaskStore(api) {
  let state = { byId: {}, today: null, loading: 0, error: null, version: 0 };
  const listeners = /* @__PURE__ */ new Set();
  const pending = /* @__PURE__ */ new Map();
  const loaded = /* @__PURE__ */ new Map();
  const emit = () => {
    state = { ...state, version: state.version + 1 };
    listeners.forEach((l) => l());
  };
  const set = (patch) => {
    state = { ...state, ...patch };
    emit();
  };
  function upsert(tasks, coveredFn) {
    const byId = { ...state.byId };
    const seen = /* @__PURE__ */ new Set();
    for (const t of tasks) {
      seen.add(t.task_id);
      if (pending.has(t.task_id)) continue;
      const prev = byId[t.task_id] || {};
      const body = t.body !== void 0 ? t.body : prev.revision === t.revision ? prev.body : void 0;
      byId[t.task_id] = { ...prev, ...t, body };
    }
    if (coveredFn) {
      for (const [id, t] of Object.entries(byId)) {
        if (!seen.has(id) && !pending.has(id) && coveredFn(t)) delete byId[id];
      }
    }
    state = { ...state, byId };
  }
  async function track(promise) {
    set({ loading: state.loading + 1 });
    try {
      return await promise;
    } finally {
      set({ loading: Math.max(0, state.loading - 1) });
    }
  }
  const store = {
    getState: () => state,
    subscribe: (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    setToday: (today) => {
      if (today !== state.today) set({ today });
    },
    async loadRange(from, to) {
      loaded.set(`${from}:${to}`, { from, to });
      const res = await track(api.tasks(from, to));
      if (res.today) state = { ...state, today: res.today };
      upsert(res.tasks || [], (t) => {
        const d = taskDate(t);
        return d && d >= from && d <= to;
      });
      set({ error: null });
      return res;
    },
    async loadOverdue() {
      const res = await track(api.overdue());
      const today = res.today || state.today;
      if (res.today) state = { ...state, today: res.today };
      upsert(res.tasks || [], (t) => {
        const d = taskDate(t);
        return t.status !== "done" && t.status !== "cancelled" && d && d < today;
      });
      set({ error: null });
      return res;
    },
    /** Refetch every range loaded so far (focus, polling, after agent changes). */
    async refresh() {
      const ranges = [...loaded.values()].slice(-4);
      try {
        await Promise.all([...ranges.map((r) => store.loadRange(r.from, r.to)), store.loadOverdue()]);
      } catch (err) {
        set({ error: err });
      }
    },
    async loadTask(id) {
      const res = await api.task(id);
      upsert([res.task]);
      emit();
      return res.task;
    },
    put(task) {
      upsert([task]);
      emit();
    },
    /** Apply a local change now, run the server call, then take the server's version (or roll back). */
    async mutate(id, localPatch, run) {
      const before = state.byId[id];
      pending.set(id, (pending.get(id) || 0) + 1);
      if (before && localPatch) {
        state = { ...state, byId: { ...state.byId, [id]: { ...before, ...localPatch } } };
        emit();
      }
      try {
        const res = await run();
        const left = (pending.get(id) || 1) - 1;
        if (left) pending.set(id, left);
        else pending.delete(id);
        if (res && res.task) {
          upsert([res.task]);
          emit();
        }
        return res;
      } catch (err) {
        const left = (pending.get(id) || 1) - 1;
        if (left) pending.set(id, left);
        else pending.delete(id);
        if (before) {
          state = { ...state, byId: { ...state.byId, [id]: before } };
          emit();
        }
        throw err;
      }
    }
  };
  return store;
}
function useStore(store, selector) {
  const get = React2.useCallback(() => selector(store.getState()), [store, selector]);
  const [value, setValue] = React2.useState(get);
  React2.useEffect(() => {
    setValue(get());
    return store.subscribe(() => setValue(get()));
  }, [store, get]);
  return value;
}
var AppContext = React2.createContext(null);
var useApp = () => React2.useContext(AppContext);
function usePref(key, initial) {
  const full = `alchemy-task.${key}`;
  const [value, setValue] = React2.useState(() => {
    try {
      const raw = window.localStorage.getItem(full);
      return raw === null ? initial : JSON.parse(raw);
    } catch {
      return initial;
    }
  });
  const update = React2.useCallback((v) => {
    setValue((prev) => {
      const next = typeof v === "function" ? v(prev) : v;
      try {
        window.localStorage.setItem(full, JSON.stringify(next));
      } catch {
      }
      return next;
    });
  }, [full]);
  return [value, update];
}
function useWidth(ref) {
  const [w, setW] = React2.useState(() => typeof window !== "undefined" ? window.innerWidth : 1200);
  React2.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return void 0;
    setW(el.getBoundingClientRect().width);
    const ro = new ResizeObserver((entries) => setW(entries[0].contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

// ui/src/tasks.jsx
import React4 from "react";

// ui/src/lib/month.js
function fittingRows(total, height, rowHeight, moreHeight, gap = 0) {
  if (total * (rowHeight + gap) - gap <= height) return total;
  return Math.min(total, Math.max(0, Math.floor((height - moreHeight) / (rowHeight + gap))));
}

// ui/src/ui.jsx
import React3 from "react";
var P = {
  check: "M5 12.5l4.2 4.2L19 7",
  chevL: "M15 18l-6-6 6-6",
  chevR: "M9 6l6 6-6 6",
  chevD: "M6 9l6 6 6-6",
  gear: "M12 15.2a3.2 3.2 0 100-6.4 3.2 3.2 0 000 6.4z M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  x: "M6 6l12 12M18 6L6 18",
  plus: "M12 5v14M5 12h14",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  cal: "M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z",
  link: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5",
  alert: "M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  refresh: "M20 11a8 8 0 10-2.3 5.7M20 5v6h-6",
  inbox: "M4 13l2.5-7h11L20 13M4 13v5a1 1 0 001 1h14a1 1 0 001-1v-5M4 13h4l1.5 2.5h5L16 13h4",
  edit: "M4 20h4L19 9l-4-4L4 16v4z M13.5 6.5l4 4",
  grip: "M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",
  arrowR: "M5 12h14M13 6l6 6-6 6",
  undo: "M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11",
  dot: "M12 12h.01",
  list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
  clock: "M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z",
  play: "M7 5l12 7-12 7z",
  clipboard: "M9 4.5h6a1 1 0 011 1V7H8V5.5a1 1 0 011-1z M8 6H6.5A1.5 1.5 0 005 7.5v11A1.5 1.5 0 006.5 20h11a1.5 1.5 0 001.5-1.5v-11A1.5 1.5 0 0017.5 6H16",
  chat: "M5 5.5h14a1.5 1.5 0 011.5 1.5v8a1.5 1.5 0 01-1.5 1.5h-7.5L7 20v-3.5H5A1.5 1.5 0 013.5 15V7A1.5 1.5 0 015 5.5z M8 10h8 M8 13h5"
};
var markSeq = 0;
function BrandMark({ size = 20, className = "" }) {
  const id = React3.useMemo(() => `at-mark-${++markSeq}`, []);
  return /* @__PURE__ */ React3.createElement(
    "svg",
    {
      className: "at-brand-mark " + className,
      width: size,
      height: size,
      viewBox: "0 0 96 96",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "7.4",
      strokeLinejoin: "miter",
      strokeMiterlimit: "10",
      "aria-hidden": "true"
    },
    /* @__PURE__ */ React3.createElement("clipPath", { id }, /* @__PURE__ */ React3.createElement("polygon", { points: "0.59,85.70 48.00,3.60 95.41,85.70" })),
    /* @__PURE__ */ React3.createElement("polygon", { points: "7.00,82.00 48.00,11.00 89.00,82.00" }),
    /* @__PURE__ */ React3.createElement("polyline", { clipPath: `url(#${id})`, strokeLinecap: "butt", points: "14.87,48.48 39.80,66.38 72.84,34.60" })
  );
}
function Icon({ name, size = 16, className = "", strokeWidth = 1.8 }) {
  return /* @__PURE__ */ React3.createElement(
    "svg",
    {
      className: "at-icon " + className,
      width: size,
      height: size,
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": "true"
    },
    /* @__PURE__ */ React3.createElement("path", { d: P[name] || P.dot })
  );
}
var cx = (...xs) => xs.filter(Boolean).join(" ");
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;font-size:16px";
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}
var taskHandoff = (task) => `${task.title} (task ID: ${task.task_id})`;
function Button({ variant = "default", size, icon, children, className, ...rest }) {
  return /* @__PURE__ */ React3.createElement("button", { type: "button", className: cx("at-btn", `at-btn-${variant}`, size && `at-btn-${size}`, className), ...rest }, icon ? /* @__PURE__ */ React3.createElement(Icon, { name: icon, size: size === "sm" ? 14 : 16 }) : null, children ? /* @__PURE__ */ React3.createElement("span", null, children) : null);
}
function IconButton({ icon, label, className, size = 16, ...rest }) {
  return /* @__PURE__ */ React3.createElement("button", { type: "button", className: cx("at-iconbtn", className), "aria-label": label, title: label, ...rest }, /* @__PURE__ */ React3.createElement(Icon, { name: icon, size }));
}
function Check({ checked, onChange, label, size = "md", tone }) {
  return /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      role: "checkbox",
      "aria-checked": !!checked,
      "aria-label": label,
      className: cx("at-check", `at-check-${size}`, checked && "is-on", tone && `at-tone-${tone}`),
      "data-no-drag": "",
      onClick: (e) => {
        e.stopPropagation();
        onChange(!checked);
      }
    },
    /* @__PURE__ */ React3.createElement("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, /* @__PURE__ */ React3.createElement("path", { d: P.check }))
  );
}
function Segmented({ value, options, onChange, label }) {
  return /* @__PURE__ */ React3.createElement("div", { className: "at-seg", role: "tablist", "aria-label": label }, options.map((o) => /* @__PURE__ */ React3.createElement(
    "button",
    {
      key: o.value,
      type: "button",
      role: "tab",
      "aria-selected": value === o.value,
      className: cx("at-seg-item", value === o.value && "is-on"),
      onClick: () => onChange(o.value)
    },
    o.label
  )));
}
function Spinner({ size = 14 }) {
  return /* @__PURE__ */ React3.createElement("span", { className: "at-spinner", style: { width: size, height: size }, "aria-label": "Loading" });
}
function Disclosure({ title, count, defaultOpen = false, tone, children, right, className }) {
  const [open, setOpen] = React3.useState(defaultOpen);
  return /* @__PURE__ */ React3.createElement("section", { className: cx("at-disc", open && "is-open", tone && `at-tone-${tone}`, className) }, /* @__PURE__ */ React3.createElement("button", { type: "button", className: "at-disc-head", "aria-expanded": open, onClick: () => setOpen(!open) }, /* @__PURE__ */ React3.createElement(Icon, { name: "chevR", size: 14, className: "at-disc-chev" }), /* @__PURE__ */ React3.createElement("span", { className: "at-disc-title" }, title), count !== void 0 ? /* @__PURE__ */ React3.createElement("span", { className: "at-count" }, count) : null, /* @__PURE__ */ React3.createElement("span", { className: "at-flex" }), right), open ? /* @__PURE__ */ React3.createElement("div", { className: "at-disc-body" }, children) : null);
}
function AreaDot({ area }) {
  return /* @__PURE__ */ React3.createElement("span", { className: "at-areadot", style: { "--at-area": areaColor(area) }, title: area });
}
var AREA_HUES = [212, 152, 28, 280, 340, 188, 48, 252];
function areaColor(area) {
  if (!area) return "var(--at-faint)";
  let h2 = 0;
  for (const c of String(area)) h2 = h2 * 31 + c.codePointAt(0) >>> 0;
  return `hsl(${AREA_HUES[h2 % AREA_HUES.length]} 78% 68%)`;
}
var markScrolled = (e) => {
  const el = e.currentTarget;
  if (el.parentElement) el.parentElement.classList.toggle("is-scrolled", el.scrollTop > 2);
};
function useSheetDismiss(ref, enabled, onClose) {
  const closeRef = React3.useRef(onClose);
  closeRef.current = onClose;
  React3.useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return void 0;
    let start = null;
    let dy = 0;
    let dragging = false;
    const scrollerOf = (target) => target.closest && target.closest(".at-scroll");
    const onStart = (e) => {
      if (e.touches.length !== 1) return;
      const t = e.target;
      if (t.closest && t.closest("textarea, input, [contenteditable], .at-pop")) {
        start = null;
        return;
      }
      start = { y: e.touches[0].clientY, t: Date.now(), fromBar: !!(t.closest && t.closest(".at-panel-bar")), scroller: scrollerOf(t) };
      dy = 0;
      dragging = false;
    };
    const onMove = (e) => {
      if (!start) return;
      const d = e.touches[0].clientY - start.y;
      if (!dragging) {
        const atTop = !start.scroller || start.scroller.scrollTop <= 0;
        if (d > 6 && (start.fromBar || atTop)) {
          dragging = true;
          start.y = e.touches[0].clientY;
          el.style.transition = "none";
          el.style.animation = "none";
        } else if (Math.abs(d) > 6) {
          start = null;
          return;
        }
      }
      if (dragging) {
        e.preventDefault();
        dy = Math.max(0, e.touches[0].clientY - start.y);
        el.style.transform = `translateY(${dy}px)`;
      }
    };
    const onEnd = () => {
      if (!start) return;
      const wasDragging = dragging;
      const speed = dy / Math.max(1, Date.now() - start.t);
      start = null;
      dragging = false;
      if (!wasDragging) return;
      el.style.transition = "transform .24s cubic-bezier(.2, .8, .2, 1)";
      if (dy > 110 || speed > 0.6) {
        el.style.transform = "translateY(100%)";
        setTimeout(() => closeRef.current(), 200);
      } else {
        el.style.transform = "";
      }
    };
    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: false });
    el.addEventListener("touchend", onEnd);
    el.addEventListener("touchcancel", onEnd);
    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onEnd);
    };
  }, [ref, enabled]);
}
var OverlayCtx = React3.createContext(null);
var useOverlay = () => React3.useContext(OverlayCtx);
function OverlayHost({ rootRef, children }) {
  const [ov, setOv] = React3.useState(null);
  const close = React3.useCallback(() => setOv((cur) => {
    if (cur && cur.onClose) cur.onClose();
    return null;
  }), []);
  const open = React3.useCallback((anchor, render, opts = {}) => setOv({ anchor, render, ...opts }), []);
  const api = React3.useMemo(() => ({ open, close }), [open, close]);
  return /* @__PURE__ */ React3.createElement(OverlayCtx.Provider, { value: api }, children, ov ? /* @__PURE__ */ React3.createElement(Popover, { rootRef, ...ov, close }) : null);
}
function Popover({ rootRef, anchor, render, close, align = "start", width }) {
  const ref = React3.useRef(null);
  const [pos, setPos] = React3.useState(null);
  React3.useLayoutEffect(() => {
    const root = rootRef.current;
    const el = ref.current;
    if (!root || !el || !anchor) return;
    const place = () => {
      const r = root.getBoundingClientRect();
      const a = anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : anchor;
      const w = el.offsetWidth;
      const hgt = el.offsetHeight;
      let left = (align === "end" ? a.right - w : a.left) - r.left;
      left = Math.max(8, Math.min(left, r.width - w - 8));
      let top = a.bottom - r.top + 6;
      if (top + hgt > r.height - 8 && a.top - r.top - hgt - 6 > 8) top = a.top - r.top - hgt - 6;
      top = Math.max(8, Math.min(top, r.height - hgt - 8));
      setPos({ left, top });
    };
    place();
    const ro = new ResizeObserver(place);
    ro.observe(el);
    return () => ro.disconnect();
  }, [anchor, rootRef, align]);
  React3.useEffect(() => {
    const down = (e) => {
      if (ref.current && !ref.current.contains(e.target) && !(anchor && anchor.contains && anchor.contains(e.target))) close();
    };
    const key = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("keydown", key, true);
    return () => {
      document.removeEventListener("pointerdown", down, true);
      document.removeEventListener("keydown", key, true);
    };
  }, [anchor, close]);
  return /* @__PURE__ */ React3.createElement("div", { ref, className: "at-pop", role: "dialog", style: { left: pos ? pos.left : -9999, top: pos ? pos.top : -9999, width } }, render(close));
}
function Menu({ items, close }) {
  return /* @__PURE__ */ React3.createElement("div", { className: "at-menu", role: "menu" }, items.filter(Boolean).map((it, i) => it === "-" ? /* @__PURE__ */ React3.createElement("div", { key: i, className: "at-menu-sep" }) : /* @__PURE__ */ React3.createElement(
    "button",
    {
      key: i,
      type: "button",
      role: "menuitem",
      className: cx("at-menu-item", it.danger && "is-danger"),
      onClick: () => {
        close();
        it.run();
      }
    },
    it.icon ? /* @__PURE__ */ React3.createElement(Icon, { name: it.icon, size: 15 }) : /* @__PURE__ */ React3.createElement("span", { className: "at-menu-pad" }),
    /* @__PURE__ */ React3.createElement("span", { className: "at-flex" }, it.label),
    it.hint ? /* @__PURE__ */ React3.createElement("span", { className: "at-menu-hint" }, it.hint) : null
  )));
}
function quickDates(today) {
  return [
    { label: "Today", date: today, hint: dayName(today) },
    { label: "Tomorrow", date: addDays(today, 1), hint: dayName(addDays(today, 1)) },
    { label: "Next Monday", date: nextWeekday(today, 0), hint: shortDate(nextWeekday(today, 0), today).replace(/^\w+,\s*/, "") },
    { label: "In a week", date: addDays(today, 7), hint: shortDate(addDays(today, 7), today).replace(/^\w+,\s*/, "") }
  ];
}
function DatePicker({ value, today, onPick, onClear, close, extra }) {
  const [month, setMonth] = React3.useState(startOfMonth(value || today));
  const weeks = monthGrid(month);
  const pick = (d) => {
    onPick(d);
    close && close();
  };
  return /* @__PURE__ */ React3.createElement("div", { className: "at-dp" }, /* @__PURE__ */ React3.createElement("div", { className: "at-dp-quick" }, quickDates(today).map((q) => /* @__PURE__ */ React3.createElement("button", { key: q.label, type: "button", className: cx("at-dp-q", value === q.date && "is-on"), onClick: () => pick(q.date) }, /* @__PURE__ */ React3.createElement("span", null, q.label), /* @__PURE__ */ React3.createElement("span", { className: "at-muted" }, q.hint)))), /* @__PURE__ */ React3.createElement("div", { className: "at-dp-head" }, /* @__PURE__ */ React3.createElement("span", { className: "at-dp-title" }, monthName(month), " ", month.slice(0, 4) !== today.slice(0, 4) ? month.slice(0, 4) : ""), /* @__PURE__ */ React3.createElement(IconButton, { icon: "chevL", label: "Previous month", onClick: () => setMonth(addMonths(month, -1)) }), /* @__PURE__ */ React3.createElement(IconButton, { icon: "chevR", label: "Next month", onClick: () => setMonth(addMonths(month, 1)) })), /* @__PURE__ */ React3.createElement("div", { className: "at-dp-grid", role: "grid" }, ["M", "T", "W", "T", "F", "S", "S"].map((d, i) => /* @__PURE__ */ React3.createElement("span", { key: i, className: "at-dp-dow" }, d)), weeks.flat().map((d) => /* @__PURE__ */ React3.createElement(
    "button",
    {
      key: d,
      type: "button",
      onClick: () => pick(d),
      className: cx("at-dp-day", d.slice(0, 7) !== month.slice(0, 7) && "is-out", d === today && "is-today", d === value && "is-on")
    },
    dayNum(d)
  ))), onClear || extra ? /* @__PURE__ */ React3.createElement("div", { className: "at-dp-foot" }, extra, /* @__PURE__ */ React3.createElement("span", { className: "at-flex" }), onClear ? /* @__PURE__ */ React3.createElement(Button, { size: "sm", variant: "ghost", onClick: () => {
    onClear();
    close && close();
  } }, "Clear") : null) : null);
}
var ToastCtx = React3.createContext(null);
var ToastListCtx = React3.createContext(null);
var useToast = () => React3.useContext(ToastCtx);
function ToastHost({ children }) {
  const [toasts, setToasts] = React3.useState([]);
  const seq = React3.useRef(0);
  const dismiss = React3.useCallback((id) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const show = React3.useCallback((message, opts = {}) => {
    const id = ++seq.current;
    setToasts((ts) => [...ts.slice(-2), { id, message, ...opts }]);
    setTimeout(() => dismiss(id), opts.duration || (opts.undo ? 6500 : opts.tone === "error" ? 7e3 : 3500));
    return id;
  }, [dismiss]);
  const list = React3.useMemo(() => ({ toasts, dismiss }), [toasts, dismiss]);
  return /* @__PURE__ */ React3.createElement(ToastCtx.Provider, { value: show }, /* @__PURE__ */ React3.createElement(ToastListCtx.Provider, { value: list }, children));
}
function ToastOutlet() {
  const { toasts, dismiss } = React3.useContext(ToastListCtx);
  return /* @__PURE__ */ React3.createElement("div", { className: "at-toasts", "aria-live": "polite" }, toasts.map((t) => /* @__PURE__ */ React3.createElement("div", { key: t.id, className: cx("at-toast", t.tone && `at-tone-${t.tone}`) }, t.tone === "error" ? /* @__PURE__ */ React3.createElement(Icon, { name: "alert", size: 15 }) : null, /* @__PURE__ */ React3.createElement("span", { className: "at-flex" }, t.message), t.undo ? /* @__PURE__ */ React3.createElement("button", { type: "button", className: "at-toast-act", onClick: () => {
    dismiss(t.id);
    t.undo();
  } }, "Undo") : null, t.action ? /* @__PURE__ */ React3.createElement("button", { type: "button", className: "at-toast-act", onClick: () => {
    dismiss(t.id);
    t.action.run();
  } }, t.action.label) : null)));
}

// ui/src/tasks.jsx
var PRIO = { urgent: 0, high: 1, normal: 2, low: 3 };
var isDone = (t) => t.status === "done" || t.status === "cancelled";
var byPriority = (a, b) => (PRIO[a.priority] ?? 2) - (PRIO[b.priority] ?? 2) || a.title.localeCompare(b.title);
function useTaskIndex() {
  const { store, prefs } = useApp();
  const byId = useStore(store, selById);
  const today = useStore(store, selToday);
  return React4.useMemo(() => {
    const days = {};
    const overdue = [];
    for (const t of Object.values(byId)) {
      if (prefs.area && t.area !== prefs.area) continue;
      const d = taskDate(t);
      if (!d) continue;
      if (!isDone(t) && today && d < today) overdue.push(t);
      (days[d] || (days[d] = [])).push(t);
    }
    for (const k of Object.keys(days)) days[k].sort((a, b) => Number(isDone(a)) - Number(isDone(b)) || byPriority(a, b));
    overdue.sort((a, b) => taskDate(b).localeCompare(taskDate(a)) || byPriority(a, b));
    return { days, overdue, today };
  }, [byId, today, prefs.area]);
}
var selById = (s) => s.byId;
var selToday = (s) => s.today;
function TaskRow({ task, from, compact, showDate, selected }) {
  const { actions, today } = useApp();
  const { bind } = useDrag();
  const overlay = useOverlay();
  const done = isDone(task);
  const overdue = !done && taskDate(task) && taskDate(task) < today;
  const dueDiffers = task.due && task.scheduled && task.due !== task.scheduled;
  const researching = task.research === "pending" || task.research === "running";
  const openMenu = (e) => {
    e.stopPropagation();
    overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React4.createElement(RowMenu, { task, close }), { width: 236, align: "end" });
  };
  return /* @__PURE__ */ React4.createElement(
    "div",
    {
      className: cx("at-row", compact && "is-compact", done && "is-done", selected && "is-selected", overdue && "is-late"),
      ...bind(task, from),
      onClick: () => {
        overlay.close();
        actions.open(task.task_id);
      },
      onKeyDown: (e) => {
        if (e.key === "Enter") {
          overlay.close();
          actions.open(task.task_id);
        }
        if (e.key === " " && e.target === e.currentTarget) {
          e.preventDefault();
          actions.toggle(task);
        }
      },
      tabIndex: 0,
      role: "button",
      "aria-label": task.title,
      "data-task": task.task_id
    },
    /* @__PURE__ */ React4.createElement(
      Check,
      {
        checked: done,
        onChange: () => actions.toggle(task),
        label: done ? "Mark not done" : "Mark done",
        size: compact ? "sm" : "md",
        tone: overdue || task.priority === "urgent" || task.priority === "high" ? "high" : void 0
      }
    ),
    /* @__PURE__ */ React4.createElement("div", { className: "at-row-main" }, /* @__PURE__ */ React4.createElement("div", { className: "at-row-title", title: compact ? task.title : void 0 }, task.title), compact ? null : /* @__PURE__ */ React4.createElement("div", { className: "at-row-meta" }, task.area ? /* @__PURE__ */ React4.createElement("span", { className: "at-meta-area" }, /* @__PURE__ */ React4.createElement(AreaDot, { area: task.area }), task.area) : null, showDate ? /* @__PURE__ */ React4.createElement("span", { className: cx("at-meta-date", overdue && "is-late") }, relativeDay(taskDate(task), today)) : null, dueDiffers ? /* @__PURE__ */ React4.createElement("span", { className: "at-meta-due" }, "due ", relativeDay(task.due, today)) : null, task.priority === "urgent" || task.priority === "high" ? /* @__PURE__ */ React4.createElement("span", { className: "at-meta-prio" }, task.priority) : null, task.status === "waiting" ? /* @__PURE__ */ React4.createElement("span", { className: "at-meta-status" }, "waiting") : null, task.status === "in-progress" ? /* @__PURE__ */ React4.createElement("span", { className: "at-meta-status is-active" }, "in progress") : null, researching ? /* @__PURE__ */ React4.createElement("span", { className: "at-meta-research" }, /* @__PURE__ */ React4.createElement(Icon, { name: "spark", size: 12 }), "researching") : null)),
    compact ? null : /* @__PURE__ */ React4.createElement(IconButton, { icon: "more", label: "Task actions", className: "at-row-more", onClick: openMenu, "data-no-drag": "" })
  );
}
function RowMenu({ task, close }) {
  const { actions, today } = useApp();
  const [picking, setPicking] = React4.useState(false);
  if (picking) {
    return /* @__PURE__ */ React4.createElement(DatePicker, { value: taskDate(task), today, onPick: (d) => actions.move(task, d), close });
  }
  const items = quickDates(today).slice(0, 3).map((q) => ({
    label: q.label,
    hint: q.hint,
    icon: "cal",
    run: () => actions.move(task, q.date)
  })).filter((it, i) => quickDates(today)[i].date !== taskDate(task));
  return /* @__PURE__ */ React4.createElement("div", { className: "at-menu", role: "menu" }, /* @__PURE__ */ React4.createElement("div", { className: "at-menu-label" }, "Move to"), /* @__PURE__ */ React4.createElement(Menu, { items, close }), /* @__PURE__ */ React4.createElement("button", { type: "button", className: "at-menu-item", onClick: () => setPicking(true) }, /* @__PURE__ */ React4.createElement(Icon, { name: "cal", size: 15 }), /* @__PURE__ */ React4.createElement("span", { className: "at-flex" }, "Pick a date\u2026")), /* @__PURE__ */ React4.createElement("div", { className: "at-menu-sep" }), /* @__PURE__ */ React4.createElement(Menu, { close, items: [
    { label: isDone(task) ? "Mark not done" : "Mark done", icon: "check", run: () => actions.toggle(task) },
    { label: "Open", icon: "arrowR", run: () => actions.open(task.task_id) }
  ] }));
}
function DayList({ date, tasks = [], overdue = [], compact, empty = "Nothing planned", showAdd }) {
  const { today, prefs, selectedId } = useApp();
  const { drag } = useDrag();
  const isToday = date === today;
  const visible = prefs.hideDone ? tasks.filter((t) => !isDone(t)) : tasks;
  const doneHidden = tasks.length - visible.length;
  return /* @__PURE__ */ React4.createElement("div", { className: cx("at-daylist", drag && drag.over === date && "is-over"), "data-at-drop": date }, isToday && overdue.length ? /* @__PURE__ */ React4.createElement(OverdueSection, { tasks: overdue }) : null, visible.map((t) => /* @__PURE__ */ React4.createElement(TaskRow, { key: t.task_id, task: t, from: date, compact, selected: selectedId === t.task_id })), !visible.length && !(isToday && overdue.length) ? /* @__PURE__ */ React4.createElement("div", { className: "at-empty-day" }, doneHidden ? `${doneHidden} done` : empty) : null, showAdd ? /* @__PURE__ */ React4.createElement(QuickAdd, { date }) : null, drag && drag.over === date && drag.from !== date ? /* @__PURE__ */ React4.createElement("div", { className: "at-drop-hint" }, "Move to ", relativeDay(date, today)) : null);
}
function OverdueSection({ tasks, defaultOpen = false }) {
  const { actions, today, selectedId } = useApp();
  return /* @__PURE__ */ React4.createElement(
    Disclosure,
    {
      className: "at-overdue",
      tone: "late",
      title: "Overdue",
      count: tasks.length,
      defaultOpen,
      right: /* @__PURE__ */ React4.createElement(
        "span",
        {
          className: "at-link",
          role: "button",
          tabIndex: 0,
          "data-no-drag": "",
          onClick: (e) => {
            e.stopPropagation();
            actions.moveMany(tasks, today);
          }
        },
        "Move all to today"
      )
    },
    tasks.map((t) => /* @__PURE__ */ React4.createElement(TaskRow, { key: t.task_id, task: t, from: taskDate(t), showDate: true, selected: selectedId === t.task_id }))
  );
}
function QuickAdd({ date, autoFocus, onDone }) {
  const { actions, meta, prefs } = useApp();
  const [title, setTitle] = React4.useState("");
  const [busy, setBusy] = React4.useState(false);
  const [open, setOpen] = React4.useState(!!autoFocus);
  const ref = React4.useRef(null);
  React4.useEffect(() => {
    if (open && ref.current) ref.current.focus();
  }, [open]);
  if (!open) {
    return /* @__PURE__ */ React4.createElement("button", { type: "button", className: "at-add", onClick: () => setOpen(true), "data-no-drag": "" }, /* @__PURE__ */ React4.createElement(Icon, { name: "plus", size: 14 }), " Add a task");
  }
  const submit = async () => {
    const t = title.trim();
    if (!t) {
      setOpen(false);
      onDone && onDone();
      return;
    }
    setBusy(true);
    const ok = await actions.create({ title: t, date, area: prefs.area || meta.default_area || void 0 });
    setBusy(false);
    if (ok) {
      setTitle("");
      if (ref.current) ref.current.focus();
    }
  };
  return /* @__PURE__ */ React4.createElement("form", { className: "at-add-form", "data-no-drag": "", onSubmit: (e) => {
    e.preventDefault();
    submit();
  } }, /* @__PURE__ */ React4.createElement("span", { className: "at-check at-check-md is-ghost", "aria-hidden": "true" }), /* @__PURE__ */ React4.createElement(
    "input",
    {
      ref,
      className: "at-add-input",
      value: title,
      placeholder: "New task",
      disabled: busy,
      onChange: (e) => setTitle(e.target.value),
      onKeyDown: (e) => {
        if (e.key === "Escape") {
          setTitle("");
          setOpen(false);
          onDone && onDone();
        }
      },
      onBlur: () => {
        if (!title.trim()) {
          setOpen(false);
          onDone && onDone();
        }
      }
    }
  ), busy ? /* @__PURE__ */ React4.createElement(Spinner, null) : null);
}
function MonthView({ anchor, narrow }) {
  const { today, selectedId } = useApp();
  const { days, overdue } = useTaskIndex();
  const overlay = useOverlay();
  const { drag } = useDrag();
  const weeks = monthGrid(anchor);
  const month = anchor.slice(0, 7);
  const [picked, setPicked] = React4.useState(null);
  if (narrow) {
    const sel = picked && picked.slice(0, 7) === month ? picked : today.slice(0, 7) === month ? today : startOfMonth(anchor);
    return /* @__PURE__ */ React4.createElement("div", { className: "at-scroll at-mmonth" }, /* @__PURE__ */ React4.createElement("div", { className: "at-mmonth-dows" }, ["M", "T", "W", "T", "F", "S", "S"].map((x, i) => /* @__PURE__ */ React4.createElement("span", { key: i }, x))), /* @__PURE__ */ React4.createElement("div", { className: "at-mmonth-grid" }, weeks.flat().map((d) => {
      const list = days[d] || [];
      const open = list.filter((t) => !isDone(t)).length;
      return /* @__PURE__ */ React4.createElement(
        "button",
        {
          key: d,
          type: "button",
          "data-at-drop": d,
          onClick: () => setPicked(d),
          className: cx(
            "at-mcell",
            d.slice(0, 7) !== month && "is-out",
            d === today && "is-today",
            d === sel && "is-on",
            drag && drag.over === d && "is-over"
          )
        },
        /* @__PURE__ */ React4.createElement("span", { className: "at-mcell-num" }, dayNum(d)),
        /* @__PURE__ */ React4.createElement("span", { className: "at-mcell-dots" }, list.slice(0, 3).map((t) => /* @__PURE__ */ React4.createElement("i", { key: t.task_id, className: isDone(t) ? "is-done" : "" })), d === today && overdue.length ? /* @__PURE__ */ React4.createElement("i", { className: "is-late" }) : null),
        open > 3 ? /* @__PURE__ */ React4.createElement("span", { className: "at-mcell-more" }, "+", open - 3) : null
      );
    })), /* @__PURE__ */ React4.createElement(DaySection, { date: sel, tasks: days[sel] || [], overdue: sel === today ? overdue : [] }));
  }
  return /* @__PURE__ */ React4.createElement(DesktopMonth, { weeks, month, days, overdue, today, selectedId, drag, overlay });
}
function DesktopMonth({ weeks, month, days, overdue, today, selectedId, drag, overlay, picked, onPick }) {
  const expand = (date, el) => onPick ? onPick(date) : overlay.open(el, (close) => /* @__PURE__ */ React4.createElement(DayPopover, { date, close }), { width: 360 });
  const gridRef = React4.useRef(null);
  const [cellW, setCellW] = React4.useState(160);
  React4.useLayoutEffect(() => {
    const el = gridRef.current;
    if (!el) return void 0;
    const ro = new ResizeObserver(() => setCellW(el.clientWidth / 7));
    ro.observe(el);
    return () => ro.disconnect();
  }, [weeks.length]);
  return /* @__PURE__ */ React4.createElement("div", { className: cx("at-month", onPick && "at-week-strip") }, /* @__PURE__ */ React4.createElement("div", { className: "at-month-dows" }, weeks[0].map((d) => /* @__PURE__ */ React4.createElement("div", { key: d }, dayName(d)))), /* @__PURE__ */ React4.createElement("div", { ref: gridRef, className: "at-month-grid" }, weeks.flat().map((d) => {
    const list = days[d] || [];
    const isToday = d === today;
    return /* @__PURE__ */ React4.createElement(
      "div",
      {
        key: d,
        "data-at-drop": d,
        className: cx(
          "at-cell",
          month && d.slice(0, 7) !== month && "is-out",
          isToday && "is-today",
          d < today && "is-past",
          drag && drag.over === d && "is-over",
          picked === d && "is-picked"
        ),
        tabIndex: onPick ? 0 : void 0,
        role: onPick ? "button" : void 0,
        "aria-label": onPick ? `Select ${longDate(d)}` : void 0,
        "aria-pressed": onPick ? picked === d : void 0,
        onKeyDown: (e) => {
          if (onPick && e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            onPick(d);
          }
        },
        onClick: (e) => {
          if (!e.target.closest(".at-row")) {
            if (onPick) onPick(d);
            else expand(d, e.currentTarget);
          }
        }
      },
      /* @__PURE__ */ React4.createElement("div", { className: "at-cell-head" }, /* @__PURE__ */ React4.createElement("span", { className: "at-cell-num" }, dayNum(d) === 1 ? `${monthName(d, "short")} 1` : dayNum(d)), isToday && overdue.length ? /* @__PURE__ */ React4.createElement(
        "button",
        {
          type: "button",
          className: "at-chip at-tone-late",
          "data-no-drag": "",
          title: `${overdue.length} overdue`,
          onClick: (e) => {
            e.stopPropagation();
            expand(d, e.currentTarget.closest(".at-cell"));
          }
        },
        cellW < 140 ? `${overdue.length} late` : `${overdue.length} overdue`
      ) : null),
      /* @__PURE__ */ React4.createElement(MonthTasks, { tasks: list, date: d, selectedId, expand }),
      /* @__PURE__ */ React4.createElement("div", { className: "at-cell-footer" }, /* @__PURE__ */ React4.createElement(
        "button",
        {
          type: "button",
          className: "at-cell-view",
          "data-no-drag": "",
          "aria-label": `View ${longDate(d)}`,
          title: "View day",
          onClick: (e) => {
            e.stopPropagation();
            expand(d, e.currentTarget.closest(".at-cell"));
          }
        },
        /* @__PURE__ */ React4.createElement(Icon, { name: "arrowR", size: 12 }),
        /* @__PURE__ */ React4.createElement("span", null, "View day")
      ))
    );
  })));
}
function MonthTasks({ tasks, date, selectedId, expand }) {
  const ref = React4.useRef(null);
  const [fit, setFit] = React4.useState(1);
  React4.useLayoutEffect(() => {
    const el = ref.current;
    const measure = () => {
      const row = el.querySelector(".at-row");
      const more2 = el.querySelector(".at-cell-more");
      const gap = parseFloat(getComputedStyle(el).rowGap) || 0;
      setFit(fittingRows(
        tasks.length,
        el.getBoundingClientRect().height,
        row?.getBoundingClientRect().height || 24,
        more2.getBoundingClientRect().height,
        gap
      ));
    };
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  }, [tasks.length]);
  const more = Math.max(0, tasks.length - fit);
  return /* @__PURE__ */ React4.createElement("div", { ref, className: "at-cell-list is-tight" }, tasks.slice(0, fit).map((t) => /* @__PURE__ */ React4.createElement(TaskRow, { key: t.task_id, task: t, from: date, compact: true, selected: selectedId === t.task_id })), /* @__PURE__ */ React4.createElement(
    "button",
    {
      type: "button",
      className: "at-cell-more",
      "data-no-drag": "",
      style: { visibility: more ? "visible" : "hidden" },
      tabIndex: more ? 0 : -1,
      "aria-hidden": !more,
      onClick: (e) => {
        e.stopPropagation();
        expand(date, e.currentTarget.closest(".at-cell"));
      }
    },
    "+",
    more,
    " more"
  ));
}
function DayPopover({ date, close }) {
  const { today } = useApp();
  const { days, overdue } = useTaskIndex();
  return /* @__PURE__ */ React4.createElement("div", { className: "at-daypop" }, /* @__PURE__ */ React4.createElement("div", { className: "at-daypop-head" }, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("div", { className: "at-daypop-title" }, relativeDay(date, today) === "Today" ? "Today" : dayName(date, "long")), /* @__PURE__ */ React4.createElement("div", { className: "at-muted" }, longDate(date))), /* @__PURE__ */ React4.createElement(IconButton, { icon: "x", label: "Close", onClick: close })), /* @__PURE__ */ React4.createElement("div", { className: "at-daypop-body" }, /* @__PURE__ */ React4.createElement(DayList, { date, tasks: days[date] || [], overdue: date === today ? overdue : [], showAdd: true })));
}
function WeekView({ anchor, narrow, onStep }) {
  const { today } = useApp();
  const { days, overdue } = useTaskIndex();
  const start = startOfWeek(anchor);
  const dates = range(start, addDays(start, 6));
  if (narrow) {
    return /* @__PURE__ */ React4.createElement(PhoneWeek, { dates, days, overdue, today, onStep });
  }
  return /* @__PURE__ */ React4.createElement(DesktopWeek, { dates, days, overdue, today });
}
function DesktopWeek({ dates, days, overdue, today }) {
  const { selectedId } = useApp();
  const { drag } = useDrag();
  const overlay = useOverlay();
  const [picked, setPicked] = React4.useState(null);
  const sel = picked && dates.includes(picked) ? picked : dates.includes(today) ? today : dates[0];
  return /* @__PURE__ */ React4.createElement("div", { className: "at-desktop-week at-scroll" }, /* @__PURE__ */ React4.createElement(
    DesktopMonth,
    {
      weeks: [dates],
      month: null,
      days,
      overdue,
      today,
      selectedId,
      drag,
      overlay,
      picked: sel,
      onPick: setPicked
    }
  ), /* @__PURE__ */ React4.createElement(DayView, { anchor: sel }));
}
function PhoneWeek({ dates, days, overdue, today, onStep }) {
  const { drag } = useDrag();
  const [picked, setPicked] = React4.useState(null);
  const sel = picked && dates.includes(picked) ? picked : dates.includes(today) ? today : dates[0];
  const swipe = React4.useRef(null);
  return /* @__PURE__ */ React4.createElement("div", { className: "at-scroll at-mmonth at-mweek" }, /* @__PURE__ */ React4.createElement("div", { className: "at-mmonth-dows" }, dates.map((d) => /* @__PURE__ */ React4.createElement("span", { key: d }, dayName(d).slice(0, 1)))), /* @__PURE__ */ React4.createElement(
    "div",
    {
      className: "at-mmonth-grid",
      onTouchStart: (e) => {
        const t = e.touches[0];
        swipe.current = { x: t.clientX, y: t.clientY };
      },
      onTouchEnd: (e) => {
        const s0 = swipe.current;
        swipe.current = null;
        if (!s0 || !onStep) return;
        const t = e.changedTouches[0];
        const dx = t.clientX - s0.x;
        if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(t.clientY - s0.y)) onStep(dx < 0 ? 1 : -1);
      }
    },
    dates.map((d) => {
      const list = days[d] || [];
      const open = list.filter((t) => !isDone(t)).length;
      return /* @__PURE__ */ React4.createElement(
        "button",
        {
          key: d,
          type: "button",
          "data-at-drop": d,
          onClick: () => setPicked(d),
          className: cx("at-mcell", d === today && "is-today", d === sel && "is-on", drag && drag.over === d && "is-over")
        },
        /* @__PURE__ */ React4.createElement("span", { className: "at-mcell-num" }, dayNum(d)),
        /* @__PURE__ */ React4.createElement("span", { className: "at-mcell-dots" }, list.slice(0, 3).map((t) => /* @__PURE__ */ React4.createElement("i", { key: t.task_id, className: isDone(t) ? "is-done" : "" })), d === today && overdue.length ? /* @__PURE__ */ React4.createElement("i", { className: "is-late" }) : null),
        open > 3 ? /* @__PURE__ */ React4.createElement("span", { className: "at-mcell-more" }, "+", open - 3) : null
      );
    })
  ), /* @__PURE__ */ React4.createElement(DaySection, { date: sel, tasks: days[sel] || [], overdue: sel === today ? overdue : [] }));
}
function DayView({ anchor }) {
  const { today } = useApp();
  const { days, overdue } = useTaskIndex();
  return /* @__PURE__ */ React4.createElement("div", { className: "at-scroll at-dayview" }, /* @__PURE__ */ React4.createElement("div", { className: "at-dayview-inner" }, /* @__PURE__ */ React4.createElement("header", { className: "at-dayview-head" }, /* @__PURE__ */ React4.createElement("h2", null, relativeDay(anchor, today) === "Today" ? "Today" : dayName(anchor, "long")), /* @__PURE__ */ React4.createElement("div", { className: "at-muted" }, longDate(anchor))), /* @__PURE__ */ React4.createElement(DayList, { date: anchor, tasks: days[anchor] || [], overdue: anchor === today ? overdue : [], showAdd: true })));
}
function DaySection({ date, tasks, overdue }) {
  const { today } = useApp();
  const rel = relativeDay(date, today);
  const named = rel === "Today" || rel === "Tomorrow" || rel === "Yesterday";
  const empty = !tasks.length && !overdue.length;
  return /* @__PURE__ */ React4.createElement("section", { className: cx("at-daysec", date === today && "is-today", empty && "is-empty") }, /* @__PURE__ */ React4.createElement("header", { className: "at-daysec-head" }, /* @__PURE__ */ React4.createElement("span", { className: "at-daysec-title" }, named ? rel : dayName(date, "long")), /* @__PURE__ */ React4.createElement("span", { className: "at-muted" }, shortDate(date, today).replace(/^\w+,\s*/, ""))), /* @__PURE__ */ React4.createElement(DayList, { date, tasks, overdue, showAdd: !empty || date === today }));
}
function DayScroll({ anchor, onReachEnd, length }) {
  const { today } = useApp();
  const { days, overdue } = useTaskIndex();
  const dates = range(anchor, addDays(anchor, length - 1));
  const sentinel = React4.useRef(null);
  React4.useEffect(() => {
    const el = sentinel.current;
    if (!el) return void 0;
    const io = new IntersectionObserver((es) => {
      if (es[0].isIntersecting) onReachEnd();
    }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [onReachEnd]);
  return /* @__PURE__ */ React4.createElement("div", { className: "at-scroll at-days" }, dates.map((d) => /* @__PURE__ */ React4.createElement(DaySection, { key: d, date: d, tasks: days[d] || [], overdue: d === today ? overdue : [] })), /* @__PURE__ */ React4.createElement("div", { ref: sentinel, className: "at-sentinel" }));
}
function TasksView({ narrow }) {
  const { store, prefs, setPrefs, meta, today } = useApp();
  const overlay = useOverlay();
  const view = prefs.view || (narrow ? "day" : "week");
  const [anchor, setAnchor] = React4.useState(today);
  const [scrollLen, setScrollLen] = React4.useState(21);
  const growScroll = React4.useCallback(() => setScrollLen((n) => Math.min(n + 14, 120)), []);
  React4.useEffect(() => {
    if (!anchor && today) setAnchor(today);
  }, [today, anchor]);
  const a = anchor || today;
  const range2 = React4.useMemo(() => {
    if (!a) return null;
    if (view === "month") {
      const w = monthGrid(a);
      return [w[0][0], w[w.length - 1][6]];
    }
    if (view === "week") {
      const s = startOfWeek(a);
      return [s, addDays(s, 6)];
    }
    if (narrow) return [a, addDays(a, scrollLen - 1)];
    return [a, a];
  }, [a, view, narrow, scrollLen]);
  React4.useEffect(() => {
    if (!range2) return;
    store.loadRange(range2[0], range2[1]).catch(() => {
    });
    store.loadOverdue().catch(() => {
    });
  }, [range2 && range2[0], range2 && range2[1]]);
  const step = (n) => {
    if (view === "month") setAnchor(addMonths(a, n));
    else if (view === "week") setAnchor(addDays(a, 7 * n));
    else setAnchor(addDays(a, n));
  };
  React4.useEffect(() => {
    const key = (e) => {
      if (e.target.closest && e.target.closest("input, textarea, [contenteditable]")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "t") setAnchor(today);
      else if (k === "d") setPrefs({ view: "day" });
      else if (k === "w") setPrefs({ view: "week" });
      else if (k === "m") setPrefs({ view: "month" });
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === "ArrowRight") step(1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  if (!a) return /* @__PURE__ */ React4.createElement("div", { className: "at-loading" }, /* @__PURE__ */ React4.createElement(Spinner, { size: 18 }));
  const periodText = view === "day" ? periodLabel("month", a, today) : periodLabel(view, a, today);
  const areas = meta.areas || [];
  const areaMenu = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React4.createElement(Menu, { close, items: [
    { label: "All areas", icon: prefs.area ? void 0 : "check", run: () => setPrefs({ area: "" }) },
    "-",
    ...areas.map((ar) => ({ label: ar, icon: prefs.area === ar ? "check" : void 0, run: () => setPrefs({ area: ar }) })),
    "-",
    { label: prefs.hideDone ? "Show completed" : "Hide completed", run: () => setPrefs({ hideDone: !prefs.hideDone }) }
  ] }), { width: 200, align: "end" });
  const addMenu = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React4.createElement("div", { className: "at-pop-add" }, /* @__PURE__ */ React4.createElement(QuickAdd, { date: view === "day" ? a : today, autoFocus: true, onDone: close })), { width: 320, align: "end" });
  return /* @__PURE__ */ React4.createElement("div", { className: cx("at-tasks", `is-${view}`) }, /* @__PURE__ */ React4.createElement("div", { className: "at-toolbar" }, /* @__PURE__ */ React4.createElement("div", { className: "at-toolbar-nav" }, /* @__PURE__ */ React4.createElement(Button, { variant: "ghost", size: "sm", onClick: () => setAnchor(today), disabled: a === today && view !== "month" }, "Today"), /* @__PURE__ */ React4.createElement(IconButton, { icon: "chevL", label: "Previous", onClick: () => step(-1) }), /* @__PURE__ */ React4.createElement(IconButton, { icon: "chevR", label: "Next", onClick: () => step(1) }), /* @__PURE__ */ React4.createElement("h1", { className: "at-period" }, periodText, view !== "week" && !periodText.includes(a.slice(0, 4)) ? /* @__PURE__ */ React4.createElement("span", { className: "at-period-year" }, a.slice(0, 4)) : null)), /* @__PURE__ */ React4.createElement("div", { className: "at-toolbar-right" }, /* @__PURE__ */ React4.createElement(
    Segmented,
    {
      label: "View",
      value: view,
      onChange: (v) => setPrefs({ view: v }),
      options: [{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]
    }
  ), /* @__PURE__ */ React4.createElement("button", { type: "button", className: cx("at-filter", prefs.area && "is-on"), onClick: areaMenu }, prefs.area ? /* @__PURE__ */ React4.createElement(AreaDot, { area: prefs.area }) : null, /* @__PURE__ */ React4.createElement("span", null, prefs.area || "All areas"), /* @__PURE__ */ React4.createElement(Icon, { name: "chevD", size: 14 })), narrow ? null : /* @__PURE__ */ React4.createElement(Button, { variant: "primary", size: "sm", icon: "plus", onClick: addMenu }, "Add"))), /* @__PURE__ */ React4.createElement("div", { className: "at-viewport" }, view === "month" ? /* @__PURE__ */ React4.createElement(MonthView, { anchor: a, narrow }) : null, view === "week" ? /* @__PURE__ */ React4.createElement(WeekView, { anchor: a, narrow, onStep: step }) : null, view === "day" && narrow ? /* @__PURE__ */ React4.createElement(DayScroll, { anchor: a, length: scrollLen, onReachEnd: growScroll }) : null, view === "day" && !narrow ? /* @__PURE__ */ React4.createElement(DayView, { anchor: a }) : null), narrow ? /* @__PURE__ */ React4.createElement(PhoneComposer, { date: view === "day" ? a : today }) : null);
}
function PhoneComposer({ date: initialDate }) {
  const { actions, meta, prefs, today } = useApp();
  const overlay = useOverlay();
  const [open, setOpen] = React4.useState(false);
  const [title, setTitle] = React4.useState("");
  const [date, setDate] = React4.useState(initialDate);
  const [area, setArea] = React4.useState("");
  const [busy, setBusy] = React4.useState(false);
  const [lift, setLift] = React4.useState(0);
  const input = React4.useRef(null);
  React4.useEffect(() => {
    const vv = window.visualViewport;
    if (!open || !vv) {
      setLift(0);
      return void 0;
    }
    const place = () => setLift(Math.max(0, Math.round(window.innerHeight - (vv.offsetTop + vv.height))));
    place();
    vv.addEventListener("resize", place);
    vv.addEventListener("scroll", place);
    return () => {
      vv.removeEventListener("resize", place);
      vv.removeEventListener("scroll", place);
    };
  }, [open]);
  const start = () => {
    if (input.current) input.current.focus();
    setDate(initialDate);
    setArea(prefs.area || meta.default_area || "");
    setOpen(true);
  };
  const close = () => {
    overlay.close();
    setOpen(false);
    setTitle("");
    if (input.current) input.current.blur();
  };
  const submit = async () => {
    const t = title.trim();
    if (!t || busy) return;
    setBusy(true);
    const ok = await actions.create({ title: t, date, area: area || void 0 });
    setBusy(false);
    if (ok) {
      setTitle("");
      if (input.current) input.current.focus();
    }
  };
  const refocus = () => {
    if (input.current) input.current.focus();
  };
  const pickDate = (e) => overlay.open(e.currentTarget, (closePop) => /* @__PURE__ */ React4.createElement(DatePicker, { value: date, today, close: closePop, onPick: (d) => {
    setDate(d);
    refocus();
  } }), { width: 300 });
  const pickArea = (e) => overlay.open(e.currentTarget, (closePop) => /* @__PURE__ */ React4.createElement(Menu, { close: closePop, items: (meta.areas || []).map((ar) => ({
    label: ar,
    icon: ar === area ? "check" : void 0,
    run: () => {
      setArea(ar);
      refocus();
    }
  })) }), { width: 220 });
  return /* @__PURE__ */ React4.createElement(React4.Fragment, null, /* @__PURE__ */ React4.createElement("button", { type: "button", className: cx("at-fab", open && "is-hidden"), "aria-label": "Add a task", onClick: start }, /* @__PURE__ */ React4.createElement(Icon, { name: "plus", size: 24 })), open ? /* @__PURE__ */ React4.createElement("div", { className: "at-composer-scrim", onClick: close }) : null, /* @__PURE__ */ React4.createElement(
    "form",
    {
      className: cx("at-composer", open && "is-open"),
      style: { bottom: lift },
      "aria-hidden": !open,
      "data-no-drag": "",
      onSubmit: (e) => {
        e.preventDefault();
        submit();
      }
    },
    /* @__PURE__ */ React4.createElement("div", { className: "at-composer-row" }, /* @__PURE__ */ React4.createElement("span", { className: "at-check is-ghost", "aria-hidden": "true" }), /* @__PURE__ */ React4.createElement(
      "input",
      {
        ref: input,
        className: "at-composer-input",
        value: title,
        placeholder: "New task",
        enterKeyHint: "done",
        tabIndex: open ? 0 : -1,
        readOnly: busy,
        "aria-label": "New task title",
        onChange: (e) => setTitle(e.target.value),
        onKeyDown: (e) => {
          if (e.key === "Escape") close();
        }
      }
    ), busy ? /* @__PURE__ */ React4.createElement(Spinner, null) : null),
    /* @__PURE__ */ React4.createElement("div", { className: "at-composer-bar" }, /* @__PURE__ */ React4.createElement("button", { type: "button", className: "at-field", onClick: pickDate, tabIndex: open ? 0 : -1 }, /* @__PURE__ */ React4.createElement(Icon, { name: "cal", size: 15 }), /* @__PURE__ */ React4.createElement("span", null, relativeDay(date, today))), (meta.areas || []).length ? /* @__PURE__ */ React4.createElement("button", { type: "button", className: "at-field", onClick: pickArea, tabIndex: open ? 0 : -1 }, /* @__PURE__ */ React4.createElement(AreaDot, { area }), /* @__PURE__ */ React4.createElement("span", null, area || "No area")) : null, /* @__PURE__ */ React4.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React4.createElement(Button, { variant: "ghost", size: "sm", onClick: close, tabIndex: open ? 0 : -1 }, "Done"), /* @__PURE__ */ React4.createElement("button", { type: "submit", className: "at-composer-send", "aria-label": "Add task", disabled: !title.trim() || busy, tabIndex: open ? 0 : -1 }, /* @__PURE__ */ React4.createElement(Icon, { name: "arrowR", size: 18, strokeWidth: 2.2 })))
  ));
}

// ui/src/panel.jsx
import React6 from "react";

// ui/src/lib/markdown.js
import React5 from "react";

// ui/src/lib/sections.js
var START_RE = /^\s*<!--\s*([\w-]+):start((?:\s+[\w.:-]+)*)\s*-->\s*$/;
var END_RE = /^\s*<!--\s*([\w-]+):end((?:\s+[\w.:-]+)*)\s*-->\s*$/;
var ids = (s) => String(s || "").trim().split(/\s+/).join(" ");
function blockEnd(lines, i) {
  const m = lines[i].match(START_RE);
  if (!m) return -1;
  for (let j = i + 1; j < lines.length; j++) {
    const e = lines[j].match(END_RE);
    if (e && e[1] === m[1] && ids(e[2]) === ids(m[2])) return j;
  }
  return -1;
}
function splitSections(body) {
  const lines = String(body || "").replace(/\r\n?/g, "\n").split("\n");
  const visible = lines.slice();
  const managed = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(START_RE);
    if (!m) continue;
    const j = blockEnd(lines, i);
    if (j < 0) continue;
    managed.push({ name: m[1], id: ids(m[2]), text: lines.slice(i + 1, j).join("\n").trim() });
    for (let k = i; k <= j; k++) visible[k] = "";
    i = j;
  }
  const sections = [];
  let cur = { title: "", start: 0, lines: [] };
  visible.forEach((l, idx) => {
    const m = l.match(/^##\s+(.*)$/);
    if (m) {
      sections.push(cur);
      cur = { title: m[1].trim(), start: idx + 1, lines: [] };
    } else cur.lines.push(l);
  });
  sections.push(cur);
  return {
    sections: sections.filter((x) => x.title || x.lines.join("").trim()).map((x) => ({
      title: x.title,
      text: x.lines.join("\n"),
      start: x.start,
      folded: /^(log|history|activity)$/i.test(x.title)
    })),
    managed
  };
}
function managedTitle(name) {
  if (/dossier|research|discovery/i.test(name)) return "Research";
  if (/state/i.test(name)) return "Current state";
  return name.replace(/[-_]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
function extractManaged(body) {
  const lines = String(body || "").replace(/\r\n?/g, "\n").split("\n");
  const keep = [];
  const top = [];
  const bottom = [];
  let seenContent = false;
  for (let i = 0; i < lines.length; i++) {
    if (START_RE.test(lines[i])) {
      const j = blockEnd(lines, i);
      if (j >= 0 && (!seenContent || /-dossier$/.test(lines[i].match(START_RE)[1]))) {
        ;
        (seenContent ? bottom : top).push(lines.slice(i, j + 1).join("\n"));
        i = j;
        continue;
      }
    }
    if (lines[i].trim()) seenContent = true;
    keep.push(lines[i]);
  }
  const editable = keep.join("\n").replace(/\n{3,}/g, "\n\n").replace(/^\n+/, "").replace(/\s+$/, "") + "\n";
  return { editable, top, bottom };
}
function rebuildBody(editable, top, bottom) {
  const parts = [];
  if (top.length) parts.push(top.join("\n\n"));
  parts.push(String(editable).replace(/\s+$/, ""));
  if (bottom.length) parts.push(bottom.join("\n\n"));
  return "\n" + parts.filter((x) => x.trim()).join("\n\n") + "\n";
}
function groupManaged(managed) {
  const out = [];
  let research = null;
  for (const m of managed || []) {
    const title = managedTitle(m.name);
    if (title !== "Research") {
      out.push({ title, text: m.text, names: [m.name] });
      continue;
    }
    if (!research) {
      research = { title, text: m.text, names: [m.name] };
      out.push(research);
      continue;
    }
    research.text = [research.text, m.text].filter((x) => x).join("\n\n---\n\n");
    research.names.push(m.name);
  }
  return out;
}

// ui/src/lib/markdown.js
var h = React5.createElement;
var SAFE_URL = /^(https?:|mailto:|obsidian:|#)/i;
function inline(text, keyBase = "i") {
  const out = [];
  let rest = String(text);
  let k = 0;
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(\[\[[^\]]+\]\])|(\[[^\]]+\]\([^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/;
  while (rest) {
    const m = rest.match(pattern);
    if (!m) {
      out.push(rest);
      break;
    }
    if (m.index) out.push(rest.slice(0, m.index));
    const tok = m[0];
    const key = `${keyBase}-${k++}`;
    if (m[1]) out.push(h("code", { key }, tok.slice(1, -1)));
    else if (m[2]) out.push(h("strong", { key }, inline(tok.slice(2, -2), key)));
    else if (m[3]) out.push(h("em", { key }, inline(tok.slice(1, -1), key)));
    else if (m[4]) {
      const inner = tok.slice(2, -2);
      const label = inner.includes("|") ? inner.split("|").pop() : inner.split("/").pop();
      out.push(h("span", { key, className: "at-md-wikilink", title: inner.split("|")[0] }, label));
    } else if (m[5]) {
      const lm = tok.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
      const href = lm[2];
      out.push(SAFE_URL.test(href) ? h("a", { key, href, target: "_blank", rel: "noreferrer noopener" }, inline(lm[1], key)) : lm[1]);
    } else if (m[6]) {
      out.push(h("a", { key, href: tok, target: "_blank", rel: "noreferrer noopener" }, shortUrl(tok)));
    }
    rest = rest.slice(m.index + tok.length);
  }
  return out;
}
function tableColumnClass(header) {
  const label = String(header).replace(/[*_`]/g, "").trim();
  return /^(time|duration|estimate|estimated time|time estimate)$/i.test(label) ? "at-md-time" : void 0;
}
function shortUrl(url) {
  try {
    const u = new URL(url);
    const p = u.pathname.length > 24 ? u.pathname.slice(0, 22) + "\u2026" : u.pathname;
    return u.host.replace(/^www\./, "") + (p === "/" ? "" : p);
  } catch {
    return url;
  }
}
var LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(\[( |x|X)\]\s+)?(.*)$/;
function parseBlocks(src) {
  const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = line.match(/^\s*(```|~~~)/);
    if (fence) {
      const body = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
      i++;
      blocks.push({ type: "code", text: body.join("\n") });
      continue;
    }
    const hm = line.match(/^(#{1,6})\s+(.*)$/);
    if (hm) {
      blocks.push({ type: "heading", level: hm[1].length, text: hm[2].trim(), line: i });
      i++;
      continue;
    }
    if (/^\s*<!--.*-->\s*$/.test(line)) {
      i++;
      continue;
    }
    if (/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(line)) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(line);
      const rows = [];
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      blocks.push({ type: "table", head, rows });
      continue;
    }
    if (/^\s*>/.test(line)) {
      const body = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push({ type: "quote", text: body.join(" ") });
      continue;
    }
    if (LIST_RE.test(line)) {
      const items = [];
      while (i < lines.length && (LIST_RE.test(lines[i]) || /^\s{2,}\S/.test(lines[i]) && items.length)) {
        const m = lines[i].match(LIST_RE);
        if (m) {
          items.push({
            indent: Math.floor(m[1].replace(/\t/g, "  ").length / 2),
            ordered: /\d/.test(m[2]),
            checkbox: m[3] ? m[4].toLowerCase() === "x" : null,
            text: m[5],
            line: i
          });
        } else {
          items[items.length - 1].text += " " + lines[i].trim();
        }
        i++;
      }
      blocks.push({ type: "list", items });
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !LIST_RE.test(lines[i]) && !/^(#{1,6})\s/.test(lines[i]) && !/^\s*(```|~~~|>|\|)/.test(lines[i])) para.push(lines[i++].trim());
    if (para.length) blocks.push({ type: "p", text: para.join(" ") });
    else i++;
  }
  return blocks;
}
function renderBlocks(blocks, { onToggle } = {}) {
  return blocks.map((b, n) => {
    const key = `b${n}`;
    switch (b.type) {
      case "heading":
        return h(`h${Math.min(6, b.level + 2)}`, { key, className: "at-md-h" }, inline(b.text, key));
      case "p":
        return h("p", { key }, inline(b.text, key));
      case "hr":
        return h("hr", { key });
      case "code":
        return h("pre", { key }, h("code", null, b.text));
      case "quote":
        return h("blockquote", { key }, inline(b.text, key));
      case "table":
        return h(
          "div",
          { key, className: "at-md-table" },
          h(
            "table",
            null,
            h("thead", null, h("tr", null, b.head.map((c, j) => h("th", { key: j, className: tableColumnClass(c) }, inline(c, `${key}h${j}`))))),
            h("tbody", null, b.rows.map((r, j) => h("tr", { key: j }, r.map((c, x) => h("td", { key: x, className: tableColumnClass(b.head[x]) }, inline(c, `${key}r${j}${x}`))))))
          )
        );
      case "list": {
        const ordered = b.items[0] && b.items[0].ordered;
        return h(ordered ? "ol" : "ul", { key, className: "at-md-list" }, b.items.map((it, j) => {
          const style = it.indent ? { marginLeft: `${it.indent * 1.25}em` } : void 0;
          if (it.checkbox === null) return h("li", { key: j, style }, inline(it.text, `${key}${j}`));
          return h(
            "li",
            { key: j, style, className: "at-md-check" + (it.checkbox ? " is-done" : "") },
            h(
              "label",
              null,
              h("input", {
                type: "checkbox",
                checked: it.checkbox,
                disabled: !onToggle,
                onChange: (e) => onToggle && onToggle(it.line, e.target.checked)
              }),
              h("span", null, inline(it.text, `${key}${j}`))
            )
          );
        }));
      }
      default:
        return null;
    }
  });
}
function toggleLine(src, line, checked) {
  const lines = String(src).split("\n");
  const m = lines[line] && lines[line].match(/^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\](.*)$/);
  if (!m) return src;
  lines[line] = `${m[1]}[${checked ? "x" : " "}]${m[3]}`;
  return lines.join("\n");
}

// ui/src/lib/research.js
var BUSY = /* @__PURE__ */ new Set(["pending", "running", "promoted"]);
var RESEARCHING = "Hermes is researching this task. Findings will appear here.";
function researchButton(status, click = null) {
  const s = String(status || "none").toLowerCase();
  if (click && click.phase === "sending") return { label: "Queued", disabled: true, note: null };
  const label = s === "complete" ? "Refresh research" : "Start research";
  if (click && click.phase === "done") return { label: "Queued", disabled: true, note: click.message || null };
  if (BUSY.has(s)) return { label, disabled: true, note: RESEARCHING };
  return { label, disabled: false, note: null };
}
function researchStartedMessage(res) {
  if (res && typeof res.message === "string" && res.message) return res.message;
  if (res && res.starts === "now") return "Starting now";
  return `Queued, starts ${res && res.starts || "within 30 minutes"}`;
}

// ui/src/panel.jsx
var PRIORITIES = ["urgent", "high", "normal", "low"];
var PLATFORMS = {
  gui: "the Hermes app",
  desktop: "Hermes Desktop",
  tui: "the terminal",
  telegram: "Telegram",
  discord: "Discord",
  slack: "Slack",
  whatsapp: "WhatsApp",
  signal: "Signal",
  photon: "iMessage",
  bluebubbles: "iMessage",
  matrix: "Matrix",
  teams: "Teams",
  email: "email",
  sms: "SMS"
};
var chatLabel = (t) => {
  const app = PLATFORMS[t && t.platform || ""] || (t && t.platform ? t.platform[0].toUpperCase() + t.platform.slice(1) : "chat");
  return t && t.reason === "task" && t.chat_name ? `${app} (${t.chat_name})` : app;
};
var STATUSES = [["open", "Open"], ["in-progress", "In progress"], ["waiting", "Waiting"]];
function TaskPanel({ id, narrow, onClose }) {
  const { store, api, actions, today, meta, host: host2, chat } = useApp();
  const toast = useToast();
  const overlay = useOverlay();
  const sel = React6.useCallback((s) => s.byId[id], [id]);
  const task = useStore(store, sel);
  const [loadError, setLoadError] = React6.useState(null);
  const [editing, setEditing] = React6.useState(false);
  const [stale, setStale] = React6.useState(false);
  const [copied, setCopied] = React6.useState(false);
  React6.useEffect(() => {
    if (!copied) return void 0;
    const hide = () => setCopied(false);
    document.addEventListener("pointerdown", hide, true);
    document.addEventListener("keydown", hide, true);
    return () => {
      document.removeEventListener("pointerdown", hide, true);
      document.removeEventListener("keydown", hide, true);
    };
  }, [copied]);
  React6.useEffect(() => setCopied(false), [id]);
  const [sending, setSending] = React6.useState(false);
  const load = React6.useCallback(() => {
    setLoadError(null);
    setStale(false);
    return store.loadTask(id).catch((err) => setLoadError(err));
  }, [id, store]);
  React6.useEffect(() => {
    setEditing(false);
    load();
  }, [id]);
  const bodyMissing = !!task && task.body === void 0;
  React6.useEffect(() => {
    if (bodyMissing && !loadError) load();
  }, [bodyMissing]);
  React6.useEffect(() => {
    if (editing) return void 0;
    const load2 = () => store.loadTask(id).catch(() => {
    });
    const t = setInterval(() => {
      if (document.visibilityState === "visible") load2();
    }, 3e4);
    window.addEventListener("focus", load2);
    return () => {
      clearInterval(t);
      window.removeEventListener("focus", load2);
    };
  }, [id, editing, store]);
  React6.useEffect(() => {
    const key = (e) => {
      if (e.key === "Escape" && !e.defaultPrevented && !editing) onClose();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose, editing]);
  const flushRef = React6.useRef(null);
  const settle = async () => {
    if (!editing || !flushRef.current) return true;
    const ok = await flushRef.current();
    if (ok) setEditing(false);
    return ok;
  };
  const patch = async (changes, local) => {
    if (!await settle()) return;
    try {
      await store.mutate(id, local || changes, () => api.patch(id, { ...changes, expected_revision: (store.getState().byId[id] || task || {}).revision }));
    } catch (err) {
      if (err.code === "stale_revision" || err.code === "retry") setStale(true);
      toast(describeError(err), { tone: "error" });
    }
  };
  const saveBody = async (body, baseRevision) => {
    const res = await api.putBody(id, body, baseRevision);
    store.put(res.task);
    return res.task;
  };
  const toggleQueue = React6.useRef(Promise.resolve());
  const toggle = (line, checked) => {
    toggleQueue.current = toggleQueue.current.then(async () => {
      const cur = store.getState().byId[id];
      if (!cur || cur.body === void 0) return;
      try {
        await saveBody(toggleLine(cur.body, line, checked), cur.revision);
      } catch (err) {
        if (err.code === "stale_revision") setStale(true);
        toast(describeError(err), { tone: "error" });
      }
    });
  };
  if (!task && loadError) {
    return /* @__PURE__ */ React6.createElement(PanelShell, { narrow, onClose }, /* @__PURE__ */ React6.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ React6.createElement(Icon, { name: "alert", size: 20 }), /* @__PURE__ */ React6.createElement("p", null, describeError(loadError)), /* @__PURE__ */ React6.createElement(Button, { onClick: load }, "Try again")));
  }
  if (!task) return /* @__PURE__ */ React6.createElement(PanelShell, { narrow, onClose }, /* @__PURE__ */ React6.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ React6.createElement(Spinner, { size: 18 })));
  const date = taskDate(task);
  const separateDue = task.due && task.scheduled && task.due !== task.scheduled;
  const pickDate = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React6.createElement(DatePicker, { value: date, today, close, onPick: async (d) => {
    if (await settle()) actions.move(store.getState().byId[id] || task, d);
  } }), { width: 300 });
  const pickDue = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React6.createElement(
    DatePicker,
    {
      value: task.due,
      today,
      close,
      onPick: (d) => patch({ due: d, keep_separate: true }, { due: d })
    }
  ), { width: 300 });
  const pickArea = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React6.createElement(Menu, { close, items: (meta.areas || []).map((ar) => ({
    label: ar,
    icon: ar === task.area ? "check" : void 0,
    run: () => patch({ area: ar })
  })) }), { width: 200 });
  const pickPriority = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React6.createElement(Menu, { close, items: PRIORITIES.map((p) => ({
    label: p[0].toUpperCase() + p.slice(1),
    icon: p === (task.priority || "normal") ? "check" : void 0,
    run: () => patch({ priority: p })
  })) }), { width: 180 });
  const pickStatus = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React6.createElement(Menu, { close, items: STATUSES.map(([v, l]) => ({
    label: l,
    icon: v === task.status ? "check" : void 0,
    run: () => patch({ status: v, ...v === "waiting" ? { reason: "Marked waiting from the Tasks UI" } : {} })
  })) }), { width: 180 });
  const copyForChat = async () => {
    const cur = store.getState().byId[id] || task;
    const ok = await copyText(taskHandoff(cur));
    if (ok) setCopied(true);
    else {
      setCopied(false);
      toast("Could not copy. Your browser blocked the clipboard.", { tone: "error" });
    }
    return ok;
  };
  const holdRegistered = () => {
    if (navigator.vibrate) navigator.vibrate(12);
    setCopied(true);
  };
  const sendToChat = async () => {
    if (sending) return;
    setSending(true);
    try {
      if (host2 === "desktop" && chat) {
        const res2 = await api.handoff(id, "desktop");
        if (!await chat.startChat(res2.text)) toast("Could not open a new chat. Update Hermes Desktop and try again.", { tone: "error" });
        return;
      }
      const newChat = "Starting a new chat for this task. Hermes will message you there in about a minute.";
      const res = await api.handoff(id, narrow ? "phone" : "dashboard");
      const h2 = res.handoff;
      if (h2.route === "session") {
        toast(newChat, { duration: 7e3 });
        return;
      }
      const where = chatLabel(h2.target);
      toast(`Sending to ${where}\u2026`);
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 1e3));
        const st = (await api.handoffStatus(h2.id)).handoff;
        if (st.state === "sent") {
          toast(`Sent. Hermes will message you on ${where}.`);
          return;
        }
        if (st.route === "session" && st.state === "started") {
          toast(
            `${where} did not respond, so Hermes is starting a new chat instead. It will message you there in about a minute.`,
            { duration: 8e3 }
          );
          return;
        }
        if (st.state === "failed") {
          toast(st.error || "Could not send it to chat.", { tone: "error" });
          return;
        }
      }
      toast("Still sending. Hermes will message you when it picks this up.", { tone: "error" });
    } catch (err) {
      if (err.code === "permission") {
        const cmd = "hermes config set plugins.entries.alchemy-task.allow_gateway_injection true";
        toast(
          "Alchemy Task needs permission to message you in chat. Ask Hermes to allow it, or run the command.",
          { tone: "error", duration: 12e3, action: { label: "Copy command", run: () => copyText(cmd) } }
        );
      } else toast(describeError(err), { tone: "error", duration: 9e3 });
    } finally {
      setSending(false);
    }
  };
  return /* @__PURE__ */ React6.createElement(PanelShell, { narrow, onClose, footer: isDone(task) ? null : /* @__PURE__ */ React6.createElement("button", { type: "button", className: cx("at-cta", sending && "is-busy"), onClick: sendToChat, disabled: sending }, /* @__PURE__ */ React6.createElement(Icon, { name: "chat", size: 19, strokeWidth: 2 }), /* @__PURE__ */ React6.createElement("span", null, sending ? "Starting\u2026" : "Start in chat")), actions: /* @__PURE__ */ React6.createElement(React6.Fragment, null, task.loading ? /* @__PURE__ */ React6.createElement(Spinner, null) : null, /* @__PURE__ */ React6.createElement(IconButton, { icon: "clipboard", label: "Copy title and ID for chat", onClick: copyForChat }), /* @__PURE__ */ React6.createElement(IconButton, { icon: "refresh", label: "Reload", onClick: load })) }, stale ? /* @__PURE__ */ React6.createElement("div", { className: "at-banner at-tone-late" }, /* @__PURE__ */ React6.createElement(Icon, { name: "alert", size: 15 }), /* @__PURE__ */ React6.createElement("span", { className: "at-flex" }, "This task changed somewhere else."), /* @__PURE__ */ React6.createElement(Button, { size: "sm", onClick: load }, "Reload")) : null, /* @__PURE__ */ React6.createElement("div", { className: "at-panel-titlerow" }, /* @__PURE__ */ React6.createElement(Check, { checked: isDone(task), onChange: async () => {
    if (await settle()) actions.toggle(store.getState().byId[id] || task);
  }, label: isDone(task) ? "Mark not done" : "Mark done", size: "lg" }), /* @__PURE__ */ React6.createElement(
    TitleField,
    {
      value: task.title,
      done: isDone(task),
      onSave: (title) => patch({ title }),
      onHold: holdRegistered,
      onLongPress: copyForChat,
      copied
    }
  )), /* @__PURE__ */ React6.createElement("div", { className: "at-fields" }, /* @__PURE__ */ React6.createElement("button", { type: "button", className: cx("at-field", date && date < today && !isDone(task) && "is-late"), onClick: pickDate }, /* @__PURE__ */ React6.createElement(Icon, { name: "cal", size: 15 }), /* @__PURE__ */ React6.createElement("span", null, date ? relativeDay(date, today) : "No date")), /* @__PURE__ */ React6.createElement("button", { type: "button", className: "at-field", onClick: pickArea }, /* @__PURE__ */ React6.createElement(AreaDot, { area: task.area }), /* @__PURE__ */ React6.createElement("span", null, task.area || "No area")), isDone(task) ? /* @__PURE__ */ React6.createElement("span", { className: "at-field at-status is-static", "data-s": task.status }, /* @__PURE__ */ React6.createElement("span", { className: "at-status-dot" }), /* @__PURE__ */ React6.createElement("span", null, task.status === "cancelled" ? "Cancelled" : "Done")) : /* @__PURE__ */ React6.createElement("button", { type: "button", className: "at-field at-status", "data-s": task.status || "open", onClick: pickStatus }, /* @__PURE__ */ React6.createElement("span", { className: "at-status-dot" }), /* @__PURE__ */ React6.createElement("span", null, (STATUSES.find(([v]) => v === task.status) || [0, "Open"])[1])), separateDue ? /* @__PURE__ */ React6.createElement("button", { type: "button", className: "at-field", onClick: pickDue }, /* @__PURE__ */ React6.createElement("span", { className: "at-muted" }, "Due"), /* @__PURE__ */ React6.createElement("span", null, relativeDay(task.due, today))) : null), /* @__PURE__ */ React6.createElement(SummaryField, { value: task.summary || "", onSave: (summary) => patch({ summary }) }), editing ? /* @__PURE__ */ React6.createElement(BodyEditor, { task, onSave: saveBody, onDone: () => setEditing(false), onStale: () => setStale(true), flushRef }) : task.body === void 0 ? /* @__PURE__ */ React6.createElement("div", { className: "at-panel-loading" }, /* @__PURE__ */ React6.createElement(Spinner, null)) : /* @__PURE__ */ React6.createElement(BodyView, { task, onEdit: () => setEditing(true), onToggle: toggle }), /* @__PURE__ */ React6.createElement(Disclosure, { title: "More", className: "at-more" }, /* @__PURE__ */ React6.createElement("div", { className: "at-more-grid" }, /* @__PURE__ */ React6.createElement("span", { className: "at-muted" }, "Priority"), /* @__PURE__ */ React6.createElement("span", null, /* @__PURE__ */ React6.createElement("button", { type: "button", className: cx("at-field is-plain", (task.priority === "high" || task.priority === "urgent") && "is-high"), onClick: pickPriority }, /* @__PURE__ */ React6.createElement("span", { className: "at-prio-glyph", "data-p": task.priority || "normal" }), /* @__PURE__ */ React6.createElement("span", null, (task.priority || "normal").replace(/^\w/, (c) => c.toUpperCase())))), /* @__PURE__ */ React6.createElement("span", { className: "at-muted" }, "Due date"), /* @__PURE__ */ React6.createElement("span", null, separateDue ? /* @__PURE__ */ React6.createElement("button", { type: "button", className: "at-field is-plain", onClick: pickDue }, shortDate(task.due, today)) : /* @__PURE__ */ React6.createElement("button", { type: "button", className: "at-link", onClick: pickDue }, "Set a separate due date")), task.completed ? /* @__PURE__ */ React6.createElement(React6.Fragment, null, /* @__PURE__ */ React6.createElement("span", { className: "at-muted" }, "Completed"), /* @__PURE__ */ React6.createElement("span", null, shortDate(task.completed, today))) : null, task.project ? /* @__PURE__ */ React6.createElement(React6.Fragment, null, /* @__PURE__ */ React6.createElement("span", { className: "at-muted" }, "Project"), /* @__PURE__ */ React6.createElement("span", { className: "at-mono" }, String(task.project).replace(/^\[\[|\]\]$/g, "").split("/").slice(-2, -1)[0] || task.project)) : null, /* @__PURE__ */ React6.createElement("span", { className: "at-muted" }, "File"), /* @__PURE__ */ React6.createElement("span", { className: "at-mono at-break" }, task.path))));
}
function ResearchBar({ task }) {
  const { store, api } = useApp();
  const toast = useToast();
  const [click, setClick] = React6.useState(null);
  React6.useEffect(() => setClick(null), [task.task_id]);
  React6.useEffect(() => {
    if (click && click.phase === "done" && !["pending", "running", "promoted"].includes(task.research)) setClick(null);
  }, [task.research]);
  const b = researchButton(task.research, click);
  const start = async () => {
    setClick({ phase: "sending" });
    try {
      const res = await api.research(task.task_id);
      if (res.task) store.put(res.task);
      setClick({ phase: "done", message: researchStartedMessage(res) });
    } catch (err) {
      setClick(null);
      toast(err.code === "research_busy" ? "Research is already queued or running." : describeError(err), { tone: "error" });
    }
  };
  return /* @__PURE__ */ React6.createElement("div", { className: "at-research-bar" }, /* @__PURE__ */ React6.createElement(Button, { size: "sm", icon: task.research === "complete" ? "refresh" : "spark", disabled: b.disabled, onClick: start }, b.label), b.note ? /* @__PURE__ */ React6.createElement("span", { className: "at-research-status" }, /* @__PURE__ */ React6.createElement(Icon, { name: "spark", size: 14 }), " ", b.note) : null);
}
function PanelShell({ narrow, onClose, actions, footer, children }) {
  const ref = React6.useRef(null);
  useSheetDismiss(ref, narrow, onClose);
  return /* @__PURE__ */ React6.createElement("aside", { ref, className: cx("at-panel", narrow ? "is-sheet" : "is-side"), "aria-label": "Task" }, /* @__PURE__ */ React6.createElement("div", { className: "at-panel-bar" }, narrow ? /* @__PURE__ */ React6.createElement("span", { className: "at-grabber" }) : null, /* @__PURE__ */ React6.createElement("span", { className: "at-flex" }), actions, /* @__PURE__ */ React6.createElement(IconButton, { icon: "x", label: "Close", onClick: onClose })), /* @__PURE__ */ React6.createElement("div", { className: cx("at-panel-body at-scroll", footer && "has-foot"), onScroll: markScrolled }, children), footer ? /* @__PURE__ */ React6.createElement("div", { className: "at-panel-foot" }, footer) : null);
}
function TitleField({ value, done, onSave, onHold, onLongPress, copied }) {
  const [v, setV] = React6.useState(value);
  const [editing, setEditing] = React6.useState(false);
  const [armed, setArmed] = React6.useState(false);
  const ref = React6.useRef(null);
  const press = React6.useRef(null);
  const pointer = React6.useRef("");
  React6.useEffect(() => setV(value), [value]);
  React6.useLayoutEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }
  }, [v]);
  const commit = () => {
    const t = v.replace(/\s+/g, " ").trim();
    if (t && t !== value) onSave(t);
    else setV(value);
  };
  const cancelPress = () => {
    if (press.current) clearTimeout(press.current.timer);
    press.current = null;
    setArmed(false);
  };
  const down = (e) => {
    pointer.current = e.pointerType;
    if (editing || e.pointerType === "mouse" && e.button !== 0) return;
    const p = { x: e.clientX, y: e.clientY, armed: false, timer: 0 };
    p.timer = setTimeout(() => {
      p.armed = true;
      setArmed(true);
      onHold();
    }, 450);
    press.current = p;
  };
  const move = (e) => {
    const p = press.current;
    if (p && !p.armed && Math.hypot(e.clientX - p.x, e.clientY - p.y) > 8) cancelPress();
  };
  const pointerCancel = () => {
    if (!(press.current && press.current.armed)) cancelPress();
  };
  const release = (e) => {
    const p = press.current;
    if (!p) return;
    const fire = p.armed;
    cancelPress();
    if (fire) {
      e.preventDefault();
      press.current = { swallowClick: true };
      onLongPress();
    }
  };
  const click = (e) => {
    if (press.current && press.current.swallowClick) {
      press.current = null;
      e.preventDefault();
      return;
    }
    if (editing) return;
    e.currentTarget.focus();
    setEditing(true);
  };
  return /* @__PURE__ */ React6.createElement("div", { className: "at-title-wrap" }, /* @__PURE__ */ React6.createElement(
    "textarea",
    {
      ref,
      rows: 1,
      className: cx("at-title-input", done && "is-done", armed && "is-armed", !editing && "is-idle"),
      value: v,
      "aria-label": "Title",
      title: editing ? void 0 : "Tap to edit. Press and hold to copy for chat.",
      onChange: (e) => setV(e.target.value),
      onFocus: () => {
        if (!editing && !press.current) setEditing(true);
      },
      onBlur: () => {
        setEditing(false);
        commit();
      },
      onPointerDown: down,
      onPointerMove: move,
      onPointerUp: release,
      onPointerCancel: pointerCancel,
      onTouchEnd: (e) => {
        if (press.current && press.current.armed) release(e);
      },
      onClick: click,
      onMouseDown: (e) => {
        if (!editing && pointer.current === "mouse") e.preventDefault();
      },
      onContextMenu: (e) => {
        if (!editing) e.preventDefault();
      },
      onKeyDown: (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          e.currentTarget.blur();
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setV(value);
          e.currentTarget.blur();
        }
      }
    }
  ), copied ? /* @__PURE__ */ React6.createElement("span", { className: "at-copied", role: "status" }, /* @__PURE__ */ React6.createElement(Icon, { name: "check", size: 13, strokeWidth: 2.4 }), "Copied") : null);
}
function SummaryField({ value, onSave }) {
  const [v, setV] = React6.useState(value);
  const ref = React6.useRef(null);
  React6.useEffect(() => setV(value), [value]);
  React6.useLayoutEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }
  }, [v]);
  return /* @__PURE__ */ React6.createElement(
    "textarea",
    {
      ref,
      rows: 1,
      className: "at-summary-input",
      value: v,
      placeholder: "Add a short summary",
      "aria-label": "Summary",
      onChange: (e) => setV(e.target.value),
      onBlur: () => {
        const t = v.trim();
        if (t !== value.trim()) onSave(t);
      },
      onKeyDown: (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          setV(value);
          e.currentTarget.blur();
        }
      }
    }
  );
}
function BodyView({ task, onEdit, onToggle }) {
  const { sections, managed: allManaged } = React6.useMemo(() => splitSections(task.body || ""), [task.body]);
  const stateBlock = allManaged.find((m) => /current-state/.test(m.name));
  const managed = allManaged.filter((m) => m !== stateBlock);
  const state = stateBlock ? { title: "Current state", text: stateBlock.text, start: 0, managed: true } : sections.find((s) => /^current state$/i.test(s.title));
  const rest = sections.filter((s) => s !== state);
  const logAt = rest.findIndex((s) => /^log$/i.test((s.title || "").trim()));
  const before = logAt >= 0 ? rest.slice(0, logAt) : rest;
  const after = logAt >= 0 ? rest.slice(logAt) : [];
  const renderSection = (s) => renderBlocks(parseBlocks(s.text), { onToggle: (line, checked) => onToggle(s.start + line, checked) });
  const hasContent = sections.some((s) => s.text.trim());
  return /* @__PURE__ */ React6.createElement("div", { className: "at-body" }, /* @__PURE__ */ React6.createElement("div", { className: "at-body-bar" }, /* @__PURE__ */ React6.createElement("span", { className: "at-body-label" }, "Notes"), /* @__PURE__ */ React6.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React6.createElement(Button, { size: "sm", variant: "ghost", icon: "edit", onClick: onEdit }, "Edit")), state && state.text.trim() ? /* @__PURE__ */ React6.createElement("div", { className: "at-state" }, /* @__PURE__ */ React6.createElement("div", { className: "at-state-label" }, "Current state"), /* @__PURE__ */ React6.createElement("div", { className: "at-md" }, state.managed ? renderBlocks(parseBlocks(state.text)) : renderSection(state))) : null, !hasContent && !managed.length ? /* @__PURE__ */ React6.createElement("button", { type: "button", className: "at-empty-notes", onClick: onEdit }, "Add notes") : null, before.map((s, i) => /* @__PURE__ */ React6.createElement(BodySection, { key: `b${i}`, s, render: renderSection })), groupManaged(managed).map((m, i) => /* @__PURE__ */ React6.createElement(Disclosure, { key: `m${i}`, title: m.title, defaultOpen: m.title === "Research", className: "at-fold", right: /* @__PURE__ */ React6.createElement(Icon, { name: "spark", size: 13 }) }, m.title === "Research" && !isDone(task) ? /* @__PURE__ */ React6.createElement(ResearchBar, { task }) : null, /* @__PURE__ */ React6.createElement("div", { className: "at-md" }, renderBlocks(parseBlocks(m.text))))), !isDone(task) && !groupManaged(managed).some((m) => m.title === "Research") ? /* @__PURE__ */ React6.createElement(Disclosure, { title: "Research", defaultOpen: true, className: "at-fold", right: /* @__PURE__ */ React6.createElement(Icon, { name: "spark", size: 13 }) }, /* @__PURE__ */ React6.createElement(ResearchBar, { task })) : null, after.map((s, i) => /* @__PURE__ */ React6.createElement(BodySection, { key: `a${i}`, s, render: renderSection })));
}
function BodySection({ s, render }) {
  return s.folded ? /* @__PURE__ */ React6.createElement(Disclosure, { title: s.title, className: "at-fold" }, /* @__PURE__ */ React6.createElement("div", { className: "at-md" }, render(s))) : /* @__PURE__ */ React6.createElement("div", { className: "at-section" }, s.title && !/^notes$/i.test(s.title) ? /* @__PURE__ */ React6.createElement("h3", { className: "at-section-title" }, s.title) : null, /* @__PURE__ */ React6.createElement("div", { className: "at-md" }, render(s)));
}
function BodyEditor({ task, onSave, onDone, onStale, flushRef }) {
  const toast = useToast();
  const parts = React6.useMemo(() => extractManaged(task.body || ""), []);
  const baseRev = React6.useRef(task.revision);
  const inFlight = React6.useRef(Promise.resolve(true));
  const [text, setText] = React6.useState(parts.editable);
  const [status, setStatus] = React6.useState("saved");
  const latest = React6.useRef(text);
  const saved = React6.useRef(parts.editable);
  const timer = React6.useRef(null);
  const ref = React6.useRef(null);
  const save = React6.useCallback(() => {
    clearTimeout(timer.current);
    inFlight.current = inFlight.current.then(async () => {
      const body = latest.current;
      if (body === saved.current) {
        setStatus((st) => st === "error" ? st : "saved");
        return true;
      }
      setStatus("saving");
      try {
        const t = await onSave(rebuildBody(body, parts.top, parts.bottom), baseRev.current);
        baseRev.current = t.revision;
        saved.current = body;
        setStatus(latest.current === body ? "saved" : "dirty");
        return true;
      } catch (err) {
        setStatus("error");
        if (err.code === "stale_revision") onStale();
        toast(describeError(err), { tone: "error" });
        return false;
      }
    });
    return inFlight.current;
  }, [onSave, onStale, toast, parts]);
  React6.useEffect(() => {
    if (!flushRef) return void 0;
    flushRef.current = save;
    return () => {
      flushRef.current = null;
    };
  }, [flushRef, save]);
  const changedElsewhere = task.revision && baseRev.current && task.revision !== baseRev.current && status !== "saving";
  React6.useEffect(() => {
    if (ref.current) ref.current.focus();
  }, []);
  React6.useEffect(() => () => clearTimeout(timer.current), []);
  const change = (v) => {
    setText(v);
    latest.current = v;
    setStatus("dirty");
    clearTimeout(timer.current);
    timer.current = setTimeout(save, 1500);
  };
  const done = async () => {
    if (await save()) onDone();
  };
  return /* @__PURE__ */ React6.createElement("div", { className: "at-body is-editing" }, /* @__PURE__ */ React6.createElement("div", { className: "at-body-bar" }, /* @__PURE__ */ React6.createElement("span", { className: "at-body-label" }, "Notes"), /* @__PURE__ */ React6.createElement("span", { className: cx("at-save", `is-${status}`) }, status === "saving" ? "Saving\u2026" : status === "saved" ? "Saved" : status === "error" ? "Not saved" : "Editing"), /* @__PURE__ */ React6.createElement("span", { className: "at-flex" }), status === "error" ? /* @__PURE__ */ React6.createElement(Button, { size: "sm", variant: "ghost", onClick: onDone }, "Discard changes") : null, status === "error" && !changedElsewhere ? /* @__PURE__ */ React6.createElement(Button, { size: "sm", onClick: save }, "Retry") : null, /* @__PURE__ */ React6.createElement(Button, { size: "sm", variant: "primary", onClick: done }, "Done")), changedElsewhere ? /* @__PURE__ */ React6.createElement("div", { className: "at-banner at-tone-late" }, /* @__PURE__ */ React6.createElement(Icon, { name: "alert", size: 15 }), /* @__PURE__ */ React6.createElement("span", { className: "at-flex" }, "This task changed while you were editing. Your text is kept here and will not overwrite it. Copy what you need, then choose Discard changes to see the latest version.")) : null, /* @__PURE__ */ React6.createElement(
    "textarea",
    {
      ref,
      className: "at-editor",
      value: text,
      spellCheck: true,
      onChange: (e) => change(e.target.value),
      onKeyDown: (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "s") {
          e.preventDefault();
          save();
        }
        if (e.key === "Escape") {
          e.preventDefault();
          done();
        }
      }
    }
  ), /* @__PURE__ */ React6.createElement("div", { className: "at-editor-hint" }, "Markdown. Saves as you type.", parts.top.length + parts.bottom.length ? " Research added by Hermes is kept as it is." : ""));
}

// ui/src/discovery.jsx
import React7 from "react";

// ui/src/lib/discovery.js
var pendingCount = (runs) => (runs || []).reduce((n, r) => n + (r.proposals || []).filter((p) => p.state === "pending" && !p.expired).length, 0);
var discoveryBadge = (runs, streams) => {
  const pending = pendingCount(runs);
  if (pending) return pending;
  return Array.isArray(runs) && !runs.length && Array.isArray(streams) && !streams.length ? 1 : 0;
};
function nextRunLabel(iso, now = /* @__PURE__ */ new Date()) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const time = d.toLocaleTimeString(void 0, { hour: "numeric", minute: "2-digit" });
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(d) - day(now)) / 864e5);
  if (diff <= 0) return `at ${time}`;
  if (diff === 1) return `tomorrow at ${time}`;
  if (diff < 7) return `${d.toLocaleDateString(void 0, { weekday: "short" })} at ${time}`;
  return `${d.toLocaleDateString(void 0, { month: "short", day: "numeric" })} at ${time}`;
}

// ui/src/lib/digestText.js
var DIGEST_FIELDS = {
  digest_current_state: "current_understanding",
  digest_next_action: "substantive_next_action",
  digest_addition: "new_information"
};
var SENTENCE_END = /[.!?]["')\]]*(?=\s+["'(\[]?[A-Z0-9])/;
function firstSentence(text) {
  const flat = String(text ?? "").split(/\s+/).filter(Boolean).join(" ");
  const m = SENTENCE_END.exec(flat);
  return m ? flat.slice(0, m.index + m[0].length) : flat;
}
function digestField(p, key) {
  const authored = String(p?.[key] ?? "").split(/\s+/).filter(Boolean).join(" ");
  if (authored) return authored;
  let long = p?.[DIGEST_FIELDS[key]];
  if (Array.isArray(long)) long = long.find((x) => String(x ?? "").trim()) || "";
  return firstSentence(long);
}
function fullResearch(p) {
  const additions = [].concat(p?.new_information || []).filter(Boolean);
  const out = [];
  if (p?.current_understanding) out.push({ label: "Current state", text: p.current_understanding });
  if (p?.substantive_next_action) out.push({ label: "Next action", text: p.substantive_next_action });
  if (additions.length) out.push({ label: "New information", items: additions });
  const shown = [digestField(p, "digest_current_state"), digestField(p, "digest_next_action"), digestField(p, "digest_addition")];
  const same = out.every((s) => s.items ? s.items.length === 1 && shown.includes(String(s.items[0]).trim()) : shown.includes(String(s.text).split(/\s+/).join(" ")));
  return same ? [] : out;
}

// ui/src/lib/runProgress.js
function runProgressLabel(progress) {
  const p = progress || {};
  const done = Math.max(0, Number(p.done) || 0);
  const total = Math.max(0, Number(p.total) || 0);
  if (p.stage === "research" && total > 0) {
    const current = Math.min(total, done + 1);
    return { label: `Researching ${current} of ${total}`, fraction: Math.min(1, done / total) };
  }
  if (p.stage === "digest") return { label: "Writing the digest\u2026", fraction: 0.95 };
  return { label: "Reading sources\u2026", fraction: null };
}
function elapsedLabel(startedAt, now = Date.now()) {
  if (!startedAt) return "";
  const t = new Date(startedAt).getTime();
  if (Number.isNaN(t)) return "";
  const min = Math.max(0, Math.floor((now - t) / 6e4));
  return min < 1 ? "Under 1 min" : `${min} min`;
}

// ui/src/discovery.jsx
var titleCase = (s) => String(s || "").replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
function runTime(r) {
  const t = r.time;
  const d = typeof t === "number" ? new Date(t * (t < 1e12 ? 1e3 : 1)) : new Date(t);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(void 0, { hour: "numeric", minute: "2-digit" });
}
function sourcesLine(r) {
  const cov = r.coverage || [];
  if (!cov.length) return r.sources_checked && r.sources_checked.length ? `${r.sources_checked.length} sources` : "";
  const ok = cov.filter((c) => c.status === "complete").length;
  return ok === cov.length ? `${ok} ${ok === 1 ? "source" : "sources"} checked` : `${ok} of ${cov.length} sources checked`;
}
function DiscoveryView({ runs, streams, error, loading, reload }) {
  const { today } = useApp();
  const [filter, setFilter] = React7.useState("waiting");
  if (error && error.code === "not_found") {
    return /* @__PURE__ */ React7.createElement(
      Empty,
      {
        icon: "inbox",
        title: "Discovery is not available yet",
        text: "This version of Alchemy Task has no discovery runs to show. Update the plugin to review discovery here."
      }
    );
  }
  if (!runs && loading) return /* @__PURE__ */ React7.createElement("div", { className: "at-loading" }, /* @__PURE__ */ React7.createElement(Spinner, { size: 18 }));
  if (error && !runs) {
    return /* @__PURE__ */ React7.createElement(Empty, { icon: "alert", title: "Could not load discovery", text: describeError(error), action: /* @__PURE__ */ React7.createElement(Button, { onClick: reload }, "Try again") });
  }
  const all = runs || [];
  const configured = Array.isArray(streams) && streams.length > 0;
  if (!all.length && configured) {
    return /* @__PURE__ */ React7.createElement("div", { className: "at-scroll at-disco" }, /* @__PURE__ */ React7.createElement("div", { className: "at-disco-inner" }, /* @__PURE__ */ React7.createElement("div", { className: "at-disco-bar" }, /* @__PURE__ */ React7.createElement("h1", { className: "at-period" }, "Discovery"), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React7.createElement(IconButton, { icon: "refresh", label: "Refresh", onClick: reload })), /* @__PURE__ */ React7.createElement(SourcesBar, { streams, reload }), /* @__PURE__ */ React7.createElement(RunningCards, { streams }), /* @__PURE__ */ React7.createElement("div", { className: "at-caughtup" }, /* @__PURE__ */ React7.createElement(Icon, { name: "clock", size: 18 }), /* @__PURE__ */ React7.createElement("div", null, /* @__PURE__ */ React7.createElement("div", { className: "at-caughtup-title" }, "Waiting for the first run"), /* @__PURE__ */ React7.createElement("div", { className: "at-muted" }, streams.map((s) => `${titleCase(s.name)}: ${s.when || "scheduled"}`).join(" \xB7 "))))));
  }
  if (!all.length) {
    return /* @__PURE__ */ React7.createElement(
      Empty,
      {
        icon: "spark",
        title: "No discovery runs yet",
        text: "Discovery reads the sources you choose and proposes tasks. Setup takes a few minutes in chat.",
        action: /* @__PURE__ */ React7.createElement(SetupPrompt, null),
        after: /* @__PURE__ */ React7.createElement(DiscoveryExplainer, null)
      }
    );
  }
  const needs = (r) => (r.summary ? r.summary.pending : (r.proposals || []).filter((p) => p.state === "pending").length) > 0 || (r.conflicts || []).length || (r.failures || []).length;
  const shown = filter === "waiting" ? all.filter(needs) : all;
  const latest = all[0];
  return /* @__PURE__ */ React7.createElement("div", { className: "at-scroll at-disco" }, /* @__PURE__ */ React7.createElement("div", { className: "at-disco-inner" }, /* @__PURE__ */ React7.createElement("div", { className: "at-disco-bar" }, /* @__PURE__ */ React7.createElement("h1", { className: "at-period" }, "Discovery"), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React7.createElement(
    Segmented,
    {
      label: "Show",
      value: filter,
      onChange: setFilter,
      options: [{ value: "waiting", label: "Waiting for you" }, { value: "all", label: "All runs" }]
    }
  ), /* @__PURE__ */ React7.createElement(IconButton, { icon: "refresh", label: "Refresh", onClick: reload })), configured ? /* @__PURE__ */ React7.createElement(SourcesBar, { streams, reload }) : null, configured ? /* @__PURE__ */ React7.createElement(RunningCards, { streams }) : null, !shown.length ? /* @__PURE__ */ React7.createElement("div", { className: "at-caughtup" }, /* @__PURE__ */ React7.createElement(Icon, { name: "check", size: 18 }), /* @__PURE__ */ React7.createElement("div", null, /* @__PURE__ */ React7.createElement("div", { className: "at-caughtup-title" }, "All caught up"), /* @__PURE__ */ React7.createElement("div", { className: "at-muted" }, "Last run: ", titleCase(latest.stream), ", ", relativeDay(latest.day, today), " ", runTime(latest)))) : null, shown.map((r) => /* @__PURE__ */ React7.createElement(RunCard, { key: r.run_id, run: r, filter, reload }))));
}
var SETUP_PROMPT = "Set up task discovery";
var ADD_SOURCE_PROMPT = "I want to add a new source to task discovery";
var SOURCE_ICONS = { email: "inbox", chat: "chat", transcript: "list", meeting_notes: "list", document: "edit", tracker: "check" };
function SourcesBar({ streams, reload }) {
  const [adding, setAdding] = React7.useState(false);
  const [starting, setStarting] = React7.useState(null);
  const [started, setStarted] = React7.useState({});
  const { api } = useApp();
  const toast = useToast();
  const now = Date.now();
  const busy = (s) => s.running || starting === s.name || started[s.name] && now - started[s.name] < 3 * 60 * 1e3;
  const anyRunning = streams.some((s) => s.running) || Object.keys(started).length > 0;
  React7.useEffect(() => {
    if (!anyRunning || !reload) return void 0;
    const id = setInterval(() => reload(), 2e4);
    return () => clearInterval(id);
  }, [anyRunning, reload]);
  React7.useEffect(() => {
    const next = { ...started };
    let changed = false;
    for (const s of streams) {
      if (next[s.name] && (s.running || Date.now() - next[s.name] > 3 * 60 * 1e3)) {
        delete next[s.name];
        changed = true;
      }
    }
    if (changed) setStarted(next);
  }, [streams]);
  const runNow = async (s) => {
    setStarting(s.name);
    try {
      const res = await api.runStream(s.name);
      toast(res.message || "Discovery run started");
      setStarted((cur) => ({ ...cur, [s.name]: Date.now() }));
      if (reload) setTimeout(() => reload(), 3e3);
    } catch (err) {
      toast(describeError(err), { tone: "error" });
    }
    setStarting(null);
  };
  const many = streams.length > 1;
  return /* @__PURE__ */ React7.createElement("div", { className: "at-sources" }, /* @__PURE__ */ React7.createElement("div", { className: "at-sources-rows" }, streams.map((s) => /* @__PURE__ */ React7.createElement("div", { key: s.name, className: "at-sources-row" }, /* @__PURE__ */ React7.createElement("span", { className: "at-sources-head" }, /* @__PURE__ */ React7.createElement("span", { className: "at-sources-label" }, many ? `${titleCase(s.name)} reads` : "Reads"), nextRunLabel(s.next_run_at) ? /* @__PURE__ */ React7.createElement("span", { className: "at-sources-next", title: "Next scheduled run" }, "// Next ", nextRunLabel(s.next_run_at)) : null), /* @__PURE__ */ React7.createElement("div", { className: "at-sources-chips" }, (s.sources || []).length ? (s.sources || []).map((src, i) => /* @__PURE__ */ React7.createElement("span", { key: `${src.name}-${i}`, className: "at-source-chip", title: src.scope || src.name }, /* @__PURE__ */ React7.createElement(Icon, { name: SOURCE_ICONS[src.type] || "dot", size: 12 }), src.name)) : /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, "No sources yet")), busy(s) ? /* @__PURE__ */ React7.createElement(
    Button,
    {
      size: "sm",
      className: "at-sources-run is-running",
      disabled: true,
      title: `${titleCase(s.name)} discovery is running. Its digest posts to the stream's chat when it finishes.`
    },
    /* @__PURE__ */ React7.createElement(Spinner, { size: 12 }),
    starting === s.name ? "Starting\u2026" : "Running\u2026"
  ) : /* @__PURE__ */ React7.createElement(
    Button,
    {
      size: "sm",
      icon: "play",
      className: "at-sources-run",
      disabled: !!starting,
      onClick: () => runNow(s),
      title: `Run ${titleCase(s.name)} discovery now`
    },
    "Run now"
  )))), /* @__PURE__ */ React7.createElement(Button, { size: "sm", icon: "plus", className: "at-sources-add", onClick: () => setAdding((v) => !v), "aria-expanded": adding }, "Add a source"), adding ? /* @__PURE__ */ React7.createElement(CopyPrompt, { className: "is-compact", text: ADD_SOURCE_PROMPT }) : null);
}
function RunningCards({ streams }) {
  const running = (streams || []).filter((s) => s.running && s.progress);
  const [, tick] = React7.useState(0);
  React7.useEffect(() => {
    if (!running.length) return void 0;
    const id = setInterval(() => tick((n) => n + 1), 3e4);
    return () => clearInterval(id);
  }, [running.length]);
  return running.map((s) => {
    const { label, fraction } = runProgressLabel(s.progress);
    const elapsed = elapsedLabel(s.progress.started_at);
    const pct = fraction == null ? null : Math.round(fraction * 100);
    return /* @__PURE__ */ React7.createElement("article", { key: s.name, className: "at-run at-run-live", "aria-live": "polite" }, /* @__PURE__ */ React7.createElement("header", { className: "at-run-head" }, /* @__PURE__ */ React7.createElement("div", null, /* @__PURE__ */ React7.createElement("div", { className: "at-run-title" }, titleCase(s.name), " discovery"), /* @__PURE__ */ React7.createElement("div", { className: "at-run-sub" }, /* @__PURE__ */ React7.createElement("span", null, "Running now"), elapsed ? /* @__PURE__ */ React7.createElement("span", null, elapsed) : null))), /* @__PURE__ */ React7.createElement("div", { className: "at-runbar-wrap" }, /* @__PURE__ */ React7.createElement(
      "div",
      {
        className: cx("at-runbar", pct == null && "is-indeterminate"),
        role: "progressbar",
        "aria-label": label,
        "aria-valuemin": 0,
        "aria-valuemax": 100,
        "aria-valuenow": pct == null ? void 0 : pct
      },
      /* @__PURE__ */ React7.createElement("span", { className: "at-runbar-fill", style: pct == null ? void 0 : { width: `${Math.max(3, pct)}%` } })
    ), /* @__PURE__ */ React7.createElement("div", { className: "at-runbar-label" }, label)));
  });
}
function CopyPrompt({ text, className }) {
  const toast = useToast();
  const copy = async () => toast(await copyText(text) ? "Copied. Paste it into a chat with Hermes." : "Could not copy");
  return /* @__PURE__ */ React7.createElement("div", { className: cx("at-copy-prompt", className) }, /* @__PURE__ */ React7.createElement("span", { className: "at-setup-prompt-label" }, /* @__PURE__ */ React7.createElement(Icon, { name: "chat", size: 15 }), " Tell Hermes in chat"), /* @__PURE__ */ React7.createElement("div", { className: "at-copy-prompt-row" }, /* @__PURE__ */ React7.createElement("q", { className: "at-copy-prompt-text" }, text), /* @__PURE__ */ React7.createElement(Button, { size: "sm", icon: "clipboard", onClick: copy }, "Copy")));
}
function SetupPrompt({ text = SETUP_PROMPT }) {
  const toast = useToast();
  const copy = async () => toast(await copyText(text) ? "Copied. Paste it into a chat with Hermes." : "Could not copy");
  return /* @__PURE__ */ React7.createElement("button", { type: "button", className: "at-setup-prompt", onClick: copy, title: "Copy" }, /* @__PURE__ */ React7.createElement("span", { className: "at-setup-prompt-label" }, /* @__PURE__ */ React7.createElement(Icon, { name: "chat", size: 17 }), " Tell Hermes in chat"), /* @__PURE__ */ React7.createElement("span", { className: "at-setup-prompt-text" }, text), /* @__PURE__ */ React7.createElement("span", { className: "at-setup-prompt-copy" }, /* @__PURE__ */ React7.createElement(Icon, { name: "clipboard", size: 15 }), " Copy"));
}
function Empty({ icon, title, text, action, after }) {
  return /* @__PURE__ */ React7.createElement("div", { className: "at-scroll at-disco" }, /* @__PURE__ */ React7.createElement("div", { className: "at-emptystate" }, /* @__PURE__ */ React7.createElement("span", { className: "at-emptystate-icon" }, /* @__PURE__ */ React7.createElement(Icon, { name: icon, size: 22 })), /* @__PURE__ */ React7.createElement("h2", null, title), /* @__PURE__ */ React7.createElement("p", null, text), action), after);
}
var DISCO_STEPS = [
  { icon: "inbox", title: "It reads your sources", text: "On the schedule you pick, it checks the email, chat, meeting transcripts and shared docs you approve." },
  { icon: "spark", title: "It researches each ask", text: "It works out what is being asked of you, whether a task already covers it, and what doing it will take." },
  { icon: "check", title: "You decide", text: /* @__PURE__ */ React7.createElement(React7.Fragment, null, "A short numbered digest lands in your chat. Reply ", /* @__PURE__ */ React7.createElement("q", null, "2 create, 4 skip"), " and the tasks appear, already researched.") }
];
var DISCO_CATCHES = [
  {
    icon: "inbox",
    source: "Email",
    title: "The reply you meant to send",
    quote: "Could you send the updated rate sheet before Friday?",
    where: "Arrived at 11:48 PM, under 40 other emails",
    task: "Send the updated rate sheet to Harbor Market",
    due: "Friday"
  },
  {
    icon: "chat",
    source: "Slack",
    title: "Buried in a long thread",
    quote: "Can you check the tin dimensions before we approve the proof?",
    where: "Message 63 of 90 in #packaging",
    task: "Check the tin dimensions before approving the proof",
    due: "Today"
  },
  {
    icon: "list",
    source: "Meeting transcript",
    title: "One ask among twenty",
    quote: ["Maya: Can someone own the vendor follow-up?", "You: Sure, I will take it."],
    where: "From the transcript emailed after Tuesday's sync",
    task: "Follow up with the vendor about the November order",
    due: "Thursday"
  },
  {
    icon: "edit",
    source: "Shared doc",
    title: "A comment that tagged you",
    quote: "Please confirm the launch date in this section.",
    where: "Comment in the spring launch plan",
    task: "Confirm the launch date in the spring plan",
    due: "Next week"
  }
];
function DiscoveryExplainer() {
  return /* @__PURE__ */ React7.createElement("section", { className: "at-explainer", "aria-label": "What discovery does" }, /* @__PURE__ */ React7.createElement("div", { className: "at-explainer-head" }, /* @__PURE__ */ React7.createElement("span", { className: "at-explainer-kicker" }, "Why set it up"), /* @__PURE__ */ React7.createElement("h3", null, "A safety net for the asks that slip through"), /* @__PURE__ */ React7.createElement("p", null, "Every day, small requests get buried: a reply you meant to send, a favor asked halfway through a long thread, one ask among twenty in a meeting. Discovery finds the ones meant for you and offers them as tasks, so nothing quietly falls through the cracks.")), /* @__PURE__ */ React7.createElement("ol", { className: "at-explainer-steps" }, DISCO_STEPS.map((s, i) => /* @__PURE__ */ React7.createElement("li", { key: s.title, className: "at-explainer-step" }, /* @__PURE__ */ React7.createElement("span", { className: "at-explainer-num" }, i + 1), /* @__PURE__ */ React7.createElement("span", { className: "at-explainer-step-icon" }, /* @__PURE__ */ React7.createElement(Icon, { name: s.icon, size: 16 })), /* @__PURE__ */ React7.createElement("strong", null, s.title), /* @__PURE__ */ React7.createElement("span", { className: "at-explainer-step-text" }, s.text)))), /* @__PURE__ */ React7.createElement("div", { className: "at-explainer-sub" }, "What it catches"), /* @__PURE__ */ React7.createElement("div", { className: "at-explainer-grid" }, DISCO_CATCHES.map((c) => /* @__PURE__ */ React7.createElement("article", { key: c.source, className: "at-catch" }, /* @__PURE__ */ React7.createElement("div", { className: "at-catch-source" }, /* @__PURE__ */ React7.createElement(Icon, { name: c.icon, size: 14 }), " ", c.source), /* @__PURE__ */ React7.createElement("h4", null, c.title), /* @__PURE__ */ React7.createElement("blockquote", null, [].concat(c.quote).map((line) => /* @__PURE__ */ React7.createElement("span", { key: line }, line))), /* @__PURE__ */ React7.createElement("div", { className: "at-catch-where" }, c.where), /* @__PURE__ */ React7.createElement("div", { className: "at-catch-task" }, /* @__PURE__ */ React7.createElement("span", { className: "at-catch-check", "aria-hidden": "true" }), /* @__PURE__ */ React7.createElement("span", { className: "at-catch-task-text" }, c.task), /* @__PURE__ */ React7.createElement("span", { className: "at-catch-due" }, c.due))))), /* @__PURE__ */ React7.createElement("p", { className: "at-explainer-foot" }, /* @__PURE__ */ React7.createElement(Icon, { name: "check", size: 14 }), " Nothing becomes a task until you reply. Discovery only reads your sources: it never replies to anyone or changes anything in your email, chat or documents."));
}
function RunCard({ run, filter, reload }) {
  const { today } = useApp();
  const proposals = run.proposals || [];
  const visible = filter === "waiting" ? proposals.filter((p) => p.state === "pending") : proposals;
  const outcomes = (run.outcomes || []).filter((o) => o.status !== "noop");
  const attention = [...(run.conflicts || []).map((c) => ({ ...c, kind: "conflict" })), ...run.failures || []];
  const test = run.mode && run.mode !== "production";
  return /* @__PURE__ */ React7.createElement("article", { className: "at-run" }, /* @__PURE__ */ React7.createElement("header", { className: "at-run-head" }, /* @__PURE__ */ React7.createElement("div", null, /* @__PURE__ */ React7.createElement("div", { className: "at-run-title" }, titleCase(run.stream)), /* @__PURE__ */ React7.createElement("div", { className: "at-run-sub" }, /* @__PURE__ */ React7.createElement("span", null, relativeDay(run.day, today), runTime(run) ? ` \xB7 ${runTime(run)}` : ""), sourcesLine(run) ? /* @__PURE__ */ React7.createElement("span", { className: cx(run.degraded && "is-late") }, sourcesLine(run)) : null, test ? /* @__PURE__ */ React7.createElement("span", { className: "at-badge" }, "Test run") : null)), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), run.summary && run.summary.pending ? /* @__PURE__ */ React7.createElement("span", { className: "at-count is-accent" }, run.summary.pending, " waiting") : null), visible.length ? /* @__PURE__ */ React7.createElement("div", { className: "at-proposals" }, visible.map((p) => /* @__PURE__ */ React7.createElement(ProposalCard, { key: p.proposal_id, p, run, reload, readOnly: test }))) : filter === "all" && !proposals.length ? /* @__PURE__ */ React7.createElement("div", { className: "at-run-none" }, "No new proposals in this run.") : null, outcomes.length ? /* @__PURE__ */ React7.createElement(Disclosure, { title: "Updated automatically", count: outcomes.length, className: "at-run-fold" }, outcomes.map((o) => /* @__PURE__ */ React7.createElement(Outcome, { key: o.unit_id, o, run, reload }))) : null, attention.length ? /* @__PURE__ */ React7.createElement(Disclosure, { title: "Needs attention", count: attention.length, tone: "late", className: "at-run-fold", defaultOpen: true }, attention.map((a, i) => /* @__PURE__ */ React7.createElement("div", { key: i, className: "at-attn" }, /* @__PURE__ */ React7.createElement(Icon, { name: "alert", size: 14 }), /* @__PURE__ */ React7.createElement("div", null, /* @__PURE__ */ React7.createElement("div", { className: "at-attn-title" }, a.title || (a.kind === "conflict" ? "Several tasks match one item" : "Research follow-up")), /* @__PURE__ */ React7.createElement("div", { className: "at-muted" }, a.kind === "conflict" ? "Nothing was changed. Ask Hermes which task this belongs to." : a.reason))))) : null, /* @__PURE__ */ React7.createElement(Disclosure, { title: "Run details", className: "at-run-fold is-quiet" }, /* @__PURE__ */ React7.createElement("div", { className: "at-details" }, (run.coverage || []).map((c, i) => /* @__PURE__ */ React7.createElement("div", { key: i, className: "at-detail-row" }, /* @__PURE__ */ React7.createElement("span", { className: cx("at-statusdot", c.status === "complete" ? "is-ok" : "is-late") }), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }, c.source_key || c.source || "Source"), /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, c.status === "complete" ? "Checked" : c.status || "Unknown"))), /* @__PURE__ */ React7.createElement("div", { className: "at-detail-row" }, /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, "Run"), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React7.createElement("span", { className: "at-mono" }, String(run.run_id).slice(0, 12))), run.delivery && run.delivery.state ? /* @__PURE__ */ React7.createElement("div", { className: "at-detail-row" }, /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, "Digest"), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React7.createElement("span", null, deliveryLabel(run.delivery.state))) : null)));
}
var deliveryLabel = (s) => ({ delivered: "Sent", host_pending: "Sent by Hermes", prepared: "Prepared", not_prepared: "Not sent", unknown: "Unknown", inflight: "Sending" })[s] || s;
function Outcome({ o, run, reload }) {
  const { actions, api } = useApp();
  const toast = useToast();
  const [busy, setBusy] = React7.useState(false);
  const resume = async () => {
    setBusy(true);
    try {
      await api.resume(run.run_id, o.unit_id);
      await reload();
    } catch (err) {
      toast(describeError(err), { tone: "error" });
    }
    setBusy(false);
  };
  const done = o.status === "complete";
  return /* @__PURE__ */ React7.createElement("div", { className: "at-outcome" }, /* @__PURE__ */ React7.createElement("span", { className: cx("at-statusdot", done ? "is-ok" : "is-late") }), /* @__PURE__ */ React7.createElement("button", { type: "button", className: "at-outcome-title", onClick: () => o.task_id && actions.open(o.task_id) }, o.title), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), done ? /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, "Updated") : o.resume_action ? /* @__PURE__ */ React7.createElement(Button, { size: "sm", onClick: resume, disabled: busy }, busy ? "Finishing\u2026" : "Finish update") : /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, o.status));
}
function ProposalCard({ p, run, reload, readOnly }) {
  const { api, actions, today, meta, store } = useApp();
  const toast = useToast();
  const overlay = useOverlay();
  const targets = [...p.targets || []].sort((a, b) => (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0));
  const multi = p.kind === "selection" || targets.length > 1;
  const [mode, setMode] = React7.useState(p.kind === "new" || !targets.length ? "create" : "update");
  const recommended = targets.find((x) => x.recommended);
  const [target, setTarget] = React7.useState(targets.length === 1 ? targets[0].task_id : recommended ? recommended.task_id : null);
  const streamAreas = (meta.streams || {})[run.stream] || [];
  const [date, setDate] = React7.useState(p.due || p.due_hint || today);
  const [area, setArea] = React7.useState(p.area || (streamAreas.length === 1 ? streamAreas[0] : meta.default_area) || "");
  const [busy, setBusy] = React7.useState(null);
  const [gone, setGone] = React7.useState(false);
  if (p.state === "approved" || p.state === "complete") {
    const r = p.result || {};
    const finished = p.state === "complete" || r.state === "complete";
    return /* @__PURE__ */ React7.createElement("div", { className: "at-prop is-resolved" }, /* @__PURE__ */ React7.createElement("span", { className: cx("at-statusdot", finished ? "is-ok" : "is-late") }), /* @__PURE__ */ React7.createElement("span", { className: "at-prop-resolved" }, r.operation === "updated" ? "Updated" : "Created", " ", /* @__PURE__ */ React7.createElement("button", { type: "button", className: "at-linkish", onClick: () => r.task_id && actions.open(r.task_id) }, r.title || p.title)), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), finished ? /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, p.ref) : /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, "Saving\u2026"));
  }
  if (p.state === "dismissed" || gone) {
    return /* @__PURE__ */ React7.createElement("div", { className: "at-prop is-resolved is-dismissed" }, /* @__PURE__ */ React7.createElement("span", { className: "at-prop-resolved" }, p.title), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React7.createElement("span", { className: "at-muted" }, "Dismissed"));
  }
  const approve = async (choice) => {
    if (choice === "create" && !area) {
      toast("Pick an area first.", { tone: "error" });
      return;
    }
    const t = targets.find((x) => x.task_id === target);
    if (choice === "update" && !t) {
      toast("Pick the task to update.", { tone: "error" });
      return;
    }
    const body = choice === "create" ? { choice, due: date, area } : { choice, target_task_id: t.task_id, expected_revision: t.revision };
    if (p.expired) body.allow_expired = true;
    setBusy(choice);
    try {
      const res = await api.approve(p.proposal_id, body);
      const receipt = res.receipt || {};
      toast(choice === "create" ? "Task created" : "Task updated", receipt.task_id ? { action: { label: "Open", run: () => actions.open(receipt.task_id) } } : {});
      await reload();
      store.refresh();
    } catch (err) {
      toast(describeError(err), { tone: "error" });
      if (err.code === "already_resolved" || err.code === "stale_revision") reload();
    }
    setBusy(null);
  };
  const dismiss = async () => {
    setBusy("dismiss");
    try {
      await api.dismiss(p.proposal_id);
      setGone(true);
      toast("Proposal dismissed");
      reload();
    } catch (err) {
      toast(describeError(err), { tone: "error" });
    }
    setBusy(null);
  };
  const pickDate = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React7.createElement(DatePicker, { value: date, today, onPick: setDate, close }), { width: 300 });
  const pickArea = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React7.createElement(Menu, { close, items: (meta.areas || []).map((ar) => ({ label: ar, icon: ar === area ? "check" : void 0, run: () => setArea(ar) })) }), { width: 200 });
  const addition = digestField(p, "digest_addition");
  const state = digestField(p, "digest_current_state");
  const next = digestField(p, "digest_next_action");
  const full = fullResearch(p);
  const links = [].concat(p.source_links || []).filter(Boolean);
  const uncertain = p.research_disposition === "uncertain";
  return /* @__PURE__ */ React7.createElement("div", { className: cx("at-prop", p.expired && "is-expired") }, /* @__PURE__ */ React7.createElement("div", { className: "at-prop-head" }, /* @__PURE__ */ React7.createElement("span", { className: "at-prop-ref" }, p.ref), /* @__PURE__ */ React7.createElement("h3", { className: "at-prop-title" }, p.title), /* @__PURE__ */ React7.createElement(IconButton, { icon: "x", label: "Dismiss", className: "at-prop-dismiss", onClick: dismiss, disabled: !!busy || readOnly })), state ? /* @__PURE__ */ React7.createElement("p", { className: "at-prop-text" }, state) : null, next ? /* @__PURE__ */ React7.createElement("div", { className: "at-prop-next" }, /* @__PURE__ */ React7.createElement("span", { className: "at-prop-label" }, "Next"), /* @__PURE__ */ React7.createElement("span", null, next)) : null, uncertain ? /* @__PURE__ */ React7.createElement("div", { className: "at-prop-uncertain" }, /* @__PURE__ */ React7.createElement(Icon, { name: "alert", size: 14 }), /* @__PURE__ */ React7.createElement("span", null, [].concat(p.uncertainty || []).join(" ") || "Hermes was not sure about this one. Check it before you add it.")) : null, links.length ? /* @__PURE__ */ React7.createElement("div", { className: "at-prop-links" }, links.slice(0, 4).map((l, i) => /* @__PURE__ */ React7.createElement(SourceLink, { key: i, href: l }))) : null, targets.length ? /* @__PURE__ */ React7.createElement("div", { className: cx("at-prop-targets", mode === "create" && "is-muted") }, /* @__PURE__ */ React7.createElement("div", { className: "at-prop-label" }, multi ? "Could update one of these tasks" : "May update an existing task"), targets.map((t) => /* @__PURE__ */ React7.createElement("label", { key: t.task_id, className: cx("at-target", target === t.task_id && mode === "update" && "is-on") }, multi ? /* @__PURE__ */ React7.createElement(
    "input",
    {
      type: "radio",
      name: p.proposal_id,
      checked: target === t.task_id && mode === "update",
      onChange: () => {
        setTarget(t.task_id);
        setMode("update");
      }
    }
  ) : /* @__PURE__ */ React7.createElement(Icon, { name: "arrowR", size: 14 }), /* @__PURE__ */ React7.createElement("span", { className: "at-target-main" }, /* @__PURE__ */ React7.createElement("span", { className: "at-target-title" }, t.title, t.recommended && multi ? /* @__PURE__ */ React7.createElement("span", { className: "at-chip", style: { marginLeft: 6 } }, "Recommended") : null), /* @__PURE__ */ React7.createElement("span", { className: "at-target-meta" }, t.area ? /* @__PURE__ */ React7.createElement(React7.Fragment, null, /* @__PURE__ */ React7.createElement(AreaDot, { area: t.area }), t.area) : null, taskDate(t) ? /* @__PURE__ */ React7.createElement("span", null, relativeDay(taskDate(t), today)) : null, t.status && t.status !== "open" ? /* @__PURE__ */ React7.createElement("span", null, t.status) : null)), /* @__PURE__ */ React7.createElement("button", { type: "button", className: "at-link", onClick: (e) => {
    e.preventDefault();
    actions.open(t.task_id);
  } }, "Open"))), addition ? /* @__PURE__ */ React7.createElement("div", { className: "at-prop-addition" }, /* @__PURE__ */ React7.createElement("span", { className: "at-prop-label" }, "Would add"), /* @__PURE__ */ React7.createElement("p", null, addition)) : null) : null, full.length ? /* @__PURE__ */ React7.createElement(Disclosure, { title: "Full research", className: "at-prop-full is-quiet" }, full.map((sec) => /* @__PURE__ */ React7.createElement("div", { key: sec.label, className: "at-prop-full-sec" }, /* @__PURE__ */ React7.createElement("div", { className: "at-prop-label" }, sec.label), sec.items ? /* @__PURE__ */ React7.createElement("ul", null, sec.items.map((a, i) => /* @__PURE__ */ React7.createElement("li", { key: i }, a))) : /* @__PURE__ */ React7.createElement("p", null, sec.text)))) : null, /* @__PURE__ */ React7.createElement("div", { className: "at-prop-actions" }, mode === "create" ? /* @__PURE__ */ React7.createElement(React7.Fragment, null, /* @__PURE__ */ React7.createElement("button", { type: "button", className: "at-field", onClick: pickDate }, /* @__PURE__ */ React7.createElement(Icon, { name: "cal", size: 14 }), /* @__PURE__ */ React7.createElement("span", null, relativeDay(date, today))), /* @__PURE__ */ React7.createElement("button", { type: "button", className: cx("at-field", !area && "is-late"), onClick: pickArea }, /* @__PURE__ */ React7.createElement(AreaDot, { area }), /* @__PURE__ */ React7.createElement("span", null, area || "Pick area")), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), targets.length ? /* @__PURE__ */ React7.createElement(Button, { variant: "ghost", size: "sm", onClick: () => setMode("update"), disabled: !!busy }, "Update instead") : null, /* @__PURE__ */ React7.createElement(Button, { variant: "primary", size: "sm", icon: "plus", onClick: () => approve("create"), disabled: !!busy || readOnly }, busy === "create" ? "Creating\u2026" : "Create task")) : /* @__PURE__ */ React7.createElement(React7.Fragment, null, /* @__PURE__ */ React7.createElement(Button, { variant: "ghost", size: "sm", onClick: () => setMode("create"), disabled: !!busy }, "Create new instead"), /* @__PURE__ */ React7.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React7.createElement(Button, { variant: "primary", size: "sm", icon: "check", onClick: () => approve("update"), disabled: !!busy || !target || readOnly }, busy === "update" ? "Updating\u2026" : multi ? "Update selected" : "Update task"))), p.expired ? /* @__PURE__ */ React7.createElement("div", { className: "at-prop-foot at-muted" }, "Expired ", relativeDay(p.expires, today).toLowerCase(), ". You can still add it.") : null);
}
function SourceLink({ href }) {
  let label = href;
  try {
    const u = new URL(href);
    const host2 = u.host.replace(/^www\./, "");
    label = /slack/.test(host2) ? "Slack" : /mail\.google|gmail/.test(host2) ? "Gmail" : /notion/.test(host2) ? "Notion" : /github/.test(host2) ? "GitHub" : host2;
  } catch {
  }
  return /* @__PURE__ */ React7.createElement("a", { className: "at-srclink", href, target: "_blank", rel: "noreferrer noopener" }, /* @__PURE__ */ React7.createElement(Icon, { name: "link", size: 12 }), label);
}

// ui/src/settings.jsx
import React8 from "react";
var FREQUENCIES = [
  ["daily", "Every day"],
  ["weekdays", "Weekdays"],
  ["every 4 hours", "Every 4 hours"],
  ["every 3 hours", "Every 3 hours"],
  ["every 2 hours", "Every 2 hours"],
  ["hourly", "Every hour"]
];
var RESEARCH_MODEL_PROMPT = "Help me pick a research model";
var timed = (f) => f === "daily" || f === "weekdays";
function to24(t) {
  const m = String(t || "").trim().toLowerCase().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/);
  if (!m) return "07:00";
  let h2 = Number(m[1]) % 24;
  if (m[3] === "pm" && h2 < 12) h2 += 12;
  if (m[3] === "am" && h2 === 12) h2 = 0;
  return `${String(h2).padStart(2, "0")}:${m[2] || "00"}`;
}
function to12(hhmm) {
  const [h2, m] = hhmm.split(":").map(Number);
  return `${(h2 + 11) % 12 + 1}:${String(m).padStart(2, "0")} ${h2 < 12 ? "AM" : "PM"}`;
}
function SettingsPanel({ onClose, inline: inline2, narrow }) {
  const { api } = useApp();
  const [data, setData] = React8.useState(null);
  const [error, setError] = React8.useState(null);
  const sheetRef = React8.useRef(null);
  useSheetDismiss(sheetRef, narrow && !inline2, onClose);
  const load = React8.useCallback(() => {
    setError(null);
    return api.settings().then(setData, setError);
  }, [api]);
  React8.useEffect(() => {
    load();
  }, [load]);
  const body = !data ? error ? /* @__PURE__ */ React8.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ React8.createElement(Icon, { name: "alert", size: 20 }), /* @__PURE__ */ React8.createElement("p", null, describeError(error)), /* @__PURE__ */ React8.createElement(Button, { onClick: load }, "Try again")) : /* @__PURE__ */ React8.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ React8.createElement(Spinner, { size: 18 })) : /* @__PURE__ */ React8.createElement(SettingsBody, { data, reload: load });
  if (inline2) return /* @__PURE__ */ React8.createElement("div", { className: "at-settings-inline" }, body);
  return /* @__PURE__ */ React8.createElement("aside", { ref: sheetRef, className: cx("at-panel", narrow ? "is-sheet" : "is-side", "at-settings"), "aria-label": "Settings" }, /* @__PURE__ */ React8.createElement("div", { className: "at-panel-bar" }, narrow ? /* @__PURE__ */ React8.createElement("span", { className: "at-grabber" }) : null, /* @__PURE__ */ React8.createElement("span", { className: "at-panel-heading" }, "Settings"), /* @__PURE__ */ React8.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React8.createElement(IconButton, { icon: "x", label: "Close", onClick: onClose })), /* @__PURE__ */ React8.createElement("div", { className: "at-panel-body at-scroll", onScroll: markScrolled }, body));
}
function SettingsBody({ data, reload }) {
  const streams = data.streams || [];
  const t = data.tasks || {};
  return /* @__PURE__ */ React8.createElement("div", { className: "at-settings-body" }, /* @__PURE__ */ React8.createElement("section", { className: "at-set-sec" }, /* @__PURE__ */ React8.createElement("h3", null, "Discovery"), /* @__PURE__ */ React8.createElement("p", { className: "at-muted" }, "When each discovery stream reads its sources and proposes tasks."), streams.length ? streams.map((s) => /* @__PURE__ */ React8.createElement(StreamRow, { key: s.name, s, reload })) : /* @__PURE__ */ React8.createElement("div", { className: "at-set-empty" }, "No streams yet. Ask Hermes: ", /* @__PURE__ */ React8.createElement("q", null, "Set up a daily digest from my email at 7 AM."))), /* @__PURE__ */ React8.createElement("section", { className: "at-set-sec" }, /* @__PURE__ */ React8.createElement("h3", null, "Tasks"), /* @__PURE__ */ React8.createElement(TaskDefaults, { t, reload })), /* @__PURE__ */ React8.createElement("section", { className: "at-set-sec" }, /* @__PURE__ */ React8.createElement("h3", null, "Sync and storage"), /* @__PURE__ */ React8.createElement("div", { className: "at-set-grid" }, /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "Workspace"), /* @__PURE__ */ React8.createElement("span", { className: "at-mono at-break" }, t.workspace_root || "Not set up"), /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "Time zone"), /* @__PURE__ */ React8.createElement("span", null, t.timezone || "Hermes default"), data.sync && data.sync.git ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "Git"), /* @__PURE__ */ React8.createElement("span", null, data.sync.git)) : null, data.sync && data.sync.reminders ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "iOS Reminders"), /* @__PURE__ */ React8.createElement("span", null, data.sync.reminders)) : null), /* @__PURE__ */ React8.createElement("p", { className: "at-muted at-set-hint" }, "To change sources, accounts or areas, ask Hermes in chat, for example ", /* @__PURE__ */ React8.createElement("q", null, "add my team Slack channel to the work digest"), ".")));
}
function StreamRow({ s, reload }) {
  const { api } = useApp();
  const toast = useToast();
  const overlay = useOverlay();
  const [freq, setFreq] = React8.useState(s.frequency || "daily");
  const [time, setTime] = React8.useState(to24(s.time || "7 AM"));
  const [busy, setBusy] = React8.useState(null);
  const dirty = freq !== (s.frequency || "daily") || timed(freq) && time !== to24(s.time || "7 AM");
  const save = async () => {
    setBusy("save");
    try {
      const res = await api.patchStream(s.name, timed(freq) ? { frequency: freq, time: to12(time) } : { frequency: freq });
      toast(res.message || "Schedule updated");
      await reload();
    } catch (err) {
      toast(describeError(err), { tone: "error" });
    }
    setBusy(null);
  };
  const runNow = async () => {
    setBusy("run");
    try {
      const res = await api.runStream(s.name);
      toast(res.message || "Discovery run started");
    } catch (err) {
      toast(describeError(err), { tone: "error" });
    }
    setBusy(null);
  };
  const pickFreq = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React8.createElement(Menu, { close, items: FREQUENCIES.map(([v, l]) => ({ label: l, icon: v === freq ? "check" : void 0, run: () => setFreq(v) })) }), { width: 200 });
  const blocked = s.setup_blocked_reason || (s.activation_state && !/active|ok|ready/i.test(s.activation_state) ? s.activation_state : "");
  return /* @__PURE__ */ React8.createElement("div", { className: "at-stream" }, /* @__PURE__ */ React8.createElement("div", { className: "at-stream-head" }, /* @__PURE__ */ React8.createElement("div", null, /* @__PURE__ */ React8.createElement("div", { className: "at-stream-name" }, String(s.name).replace(/\b\w/g, (c) => c.toUpperCase())), /* @__PURE__ */ React8.createElement("div", { className: "at-muted" }, (s.areas || []).map((a) => /* @__PURE__ */ React8.createElement("span", { key: a, className: "at-inline-area" }, /* @__PURE__ */ React8.createElement(AreaDot, { area: a }), a)), s.last_run ? /* @__PURE__ */ React8.createElement("span", null, " \xB7 last ran ", lastRun(s.last_run)) : null)), /* @__PURE__ */ React8.createElement("span", { className: "at-flex" }), /* @__PURE__ */ React8.createElement(Button, { size: "sm", variant: "ghost", icon: "play", onClick: runNow, disabled: !!busy }, busy === "run" ? "Starting\u2026" : "Run now")), /* @__PURE__ */ React8.createElement("div", { className: "at-stream-sched" }, /* @__PURE__ */ React8.createElement("button", { type: "button", className: "at-field", onClick: pickFreq }, /* @__PURE__ */ React8.createElement(Icon, { name: "clock", size: 14 }), /* @__PURE__ */ React8.createElement("span", null, (FREQUENCIES.find(([v]) => v === freq) || [0, freq])[1]), /* @__PURE__ */ React8.createElement(Icon, { name: "chevD", size: 13 })), timed(freq) ? /* @__PURE__ */ React8.createElement("label", { className: "at-field at-timefield" }, /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "at"), /* @__PURE__ */ React8.createElement("input", { type: "time", value: time, step: 300, onChange: (e) => setTime(e.target.value || time) })) : null, s.timezone ? /* @__PURE__ */ React8.createElement("span", { className: "at-muted at-tz" }, s.timezone.replace(/_/g, " ")) : null, /* @__PURE__ */ React8.createElement("span", { className: "at-flex" }), dirty ? /* @__PURE__ */ React8.createElement(Button, { size: "sm", variant: "primary", onClick: save, disabled: !!busy }, busy === "save" ? "Saving\u2026" : "Save") : null), (s.sources || []).length ? /* @__PURE__ */ React8.createElement("div", { className: "at-stream-sources" }, (s.sources || []).map((src) => /* @__PURE__ */ React8.createElement("span", { key: src.name, className: "at-chip", title: src.scope }, src.name))) : null, blocked ? /* @__PURE__ */ React8.createElement("div", { className: "at-banner at-tone-late" }, /* @__PURE__ */ React8.createElement(Icon, { name: "alert", size: 14 }), /* @__PURE__ */ React8.createElement("span", null, blocked)) : null);
}
function lastRun(v) {
  const d = typeof v === "number" ? new Date(v * (v < 1e12 ? 1e3 : 1)) : new Date(v);
  if (Number.isNaN(d.getTime())) return "";
  const mins = Math.round((Date.now() - d.getTime()) / 6e4);
  if (mins < 60) return `${Math.max(1, mins)} min ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`;
  return d.toLocaleDateString(void 0, { month: "short", day: "numeric" });
}
function TaskDefaults({ t, reload }) {
  const { api, meta } = useApp();
  const toast = useToast();
  const overlay = useOverlay();
  const set = async (changes) => {
    try {
      await api.patchTaskSettings(changes);
      toast("Saved");
      await reload();
    } catch (err) {
      toast(describeError(err), { tone: "error" });
    }
  };
  const pickArea = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ React8.createElement(Menu, { close, items: (meta.areas || []).map((a) => ({ label: a, icon: a === t.default_area ? "check" : void 0, run: () => set({ default_area: a }) })) }), { width: 200 });
  return /* @__PURE__ */ React8.createElement("div", { className: "at-set-grid" }, /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "Default area"), /* @__PURE__ */ React8.createElement("span", null, /* @__PURE__ */ React8.createElement("button", { type: "button", className: "at-field", onClick: pickArea }, /* @__PURE__ */ React8.createElement(AreaDot, { area: t.default_area }), /* @__PURE__ */ React8.createElement("span", null, t.default_area || "None"), /* @__PURE__ */ React8.createElement(Icon, { name: "chevD", size: 13 }))), /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "Research new tasks"), /* @__PURE__ */ React8.createElement("span", null, /* @__PURE__ */ React8.createElement(
    "button",
    {
      type: "button",
      role: "switch",
      "aria-checked": !!t.research_by_default,
      className: cx("at-switch", t.research_by_default && "is-on"),
      onClick: () => set({ research_by_default: !t.research_by_default })
    },
    /* @__PURE__ */ React8.createElement("i", null)
  )), /* @__PURE__ */ React8.createElement("span", { className: "at-muted" }, "Research model"), /* @__PURE__ */ React8.createElement("span", { className: "at-research-model" }, /* @__PURE__ */ React8.createElement(ModelInput, { label: "Research model", value: t.research_model, onSave: (v) => set({ research_model: v }) }), /* @__PURE__ */ React8.createElement(ModelInput, { label: "Research provider", value: t.research_provider, small: true, onSave: (v) => set({ research_provider: v }) }), /* @__PURE__ */ React8.createElement(CopyPrompt, { className: "is-compact", text: RESEARCH_MODEL_PROMPT })));
}
function ModelInput({ label, value, small, onSave }) {
  const [text, setText] = React8.useState(value || "");
  React8.useEffect(() => {
    setText(value || "");
  }, [value]);
  const commit = () => {
    const v = text.trim();
    if (v !== (value || "")) onSave(v);
  };
  return /* @__PURE__ */ React8.createElement(
    "input",
    {
      type: "text",
      className: cx("at-field at-model-input", small && "is-small"),
      "aria-label": label,
      value: text,
      placeholder: small ? "Provider (optional)" : "Use main model",
      maxLength: 200,
      spellCheck: false,
      onChange: (e) => setText(e.target.value),
      onBlur: commit,
      onKeyDown: (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          e.currentTarget.blur();
        }
      }
    }
  );
}

// ui/src/App.jsx
var NARROW = 720;
var POLL_MS = 3e4;
function App(props) {
  return /* @__PURE__ */ React9.createElement(ToastHost, null, /* @__PURE__ */ React9.createElement(AppInner, { ...props }));
}
function AppInner({ transport, host: host2, initialView, settingsOnly, chat }) {
  const api = transport;
  const toast = useToast();
  const rootRef = React9.useRef(null);
  const width = useWidth(rootRef);
  const narrow = width < NARROW;
  const store = React9.useMemo(() => createTaskStore(api), [api]);
  const today = useStore(store, selToday2);
  const busy = useStore(store, selLoading);
  const [meta, setMeta] = React9.useState(null);
  const [metaError, setMetaError] = React9.useState(null);
  const [tab, setTab] = React9.useState(initialView === "discovery" ? "discovery" : "tasks");
  const [settingsOpen, setSettingsOpen] = React9.useState(initialView === "settings");
  const [selectedId, setSelectedId] = React9.useState(null);
  const [prefsRaw, setPrefsRaw] = usePref("prefs", { view: null, area: "", hideDone: false });
  const prefs = prefsRaw;
  const setPrefs = React9.useCallback((p) => setPrefsRaw((cur) => ({ ...cur, ...p })), [setPrefsRaw]);
  const [runs, setRuns] = React9.useState(null);
  const [runsError, setRunsError] = React9.useState(null);
  const [runsLoading, setRunsLoading] = React9.useState(false);
  const [streams, setStreams] = React9.useState(null);
  const loadMeta = React9.useCallback(() => api.meta().then((m) => {
    setMeta(m);
    setMetaError(null);
    store.setToday(m.today);
  }, setMetaError), [api, store]);
  const loadRuns = React9.useCallback(async () => {
    setRunsLoading(true);
    try {
      const res = await api.runs();
      setRuns(res.runs || []);
      setRunsError(null);
    } catch (err) {
      setRunsError(err);
    }
    setRunsLoading(false);
    try {
      const s = await api.settings();
      setStreams(Array.isArray(s.streams) ? s.streams : null);
    } catch {
      setStreams(null);
    }
  }, [api]);
  React9.useEffect(() => {
    loadMeta();
    loadRuns();
  }, [loadMeta, loadRuns]);
  React9.useEffect(() => {
    const refresh = () => {
      loadMeta();
      store.refresh();
      loadRuns();
    };
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, POLL_MS);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", refresh);
    };
  }, [loadMeta, loadRuns, store]);
  React9.useEffect(() => {
    const open = (e) => {
      const v = e.detail;
      if (v === "discovery" || v === "tasks") setTab(v);
      if (v === "settings") setSettingsOpen(true);
    };
    window.addEventListener("alchemy-task:open", open);
    return () => window.removeEventListener("alchemy-task:open", open);
  }, []);
  const actions = React9.useMemo(() => {
    const done = (t) => t.status === "done" || t.status === "cancelled";
    const fail = (err) => toast(describeError(err), { tone: "error" });
    const complete = (t) => store.mutate(t.task_id, { status: "done", completed: store.getState().today }, () => api.complete(t.task_id));
    const reopen = (t) => store.mutate(t.task_id, { status: "open", completed: null }, () => api.reopen(t.task_id));
    const setDates = (t, scheduled, due) => store.mutate(
      t.task_id,
      { scheduled, due },
      () => api.patch(t.task_id, scheduled === due ? { date: scheduled } : { scheduled, due, keep_separate: true })
    );
    const a = {
      open: (id) => setSelectedId(id),
      async toggle(t) {
        try {
          if (done(t)) {
            await reopen(t);
            toast("Marked not done", { undo: () => complete(t).catch(fail) });
          } else {
            await complete(t);
            toast(`Done: ${t.title}`, { undo: () => reopen(t).catch(fail) });
          }
        } catch (err) {
          fail(err);
        }
      },
      async move(t, date) {
        const before = { scheduled: t.scheduled || null, due: t.due || null };
        if (taskDate(t) === date && (!t.due || t.due === date)) return;
        try {
          await setDates(t, date, date);
          toast(`Moved to ${relativeDay(date, store.getState().today)}`, {
            undo: () => setDates({ ...t, scheduled: date, due: date }, before.scheduled || before.due, before.due || before.scheduled).catch(fail)
          });
        } catch (err) {
          fail(err);
        }
      },
      async moveMany(tasks, date) {
        const list = tasks.slice();
        let moved = 0;
        for (const t of list) {
          try {
            await setDates(t, date, date);
            moved++;
          } catch (err) {
            fail(err);
            break;
          }
        }
        if (moved) {
          toast(`Moved ${moved} ${moved === 1 ? "task" : "tasks"} to ${relativeDay(date, store.getState().today).toLowerCase()}`, {
            undo: async () => {
              for (const t of list.slice(0, moved)) {
                try {
                  await setDates({ ...t, scheduled: date, due: date }, t.scheduled || t.due, t.due || t.scheduled);
                } catch (err) {
                  fail(err);
                  break;
                }
              }
            }
          });
        }
      },
      async create({ title, date, area }) {
        try {
          const res = await api.create({ title, date, area });
          if (res.task) store.put(res.task);
          toast(res.task && res.task.research === "pending" ? "Added. Hermes is researching it." : "Added", {
            action: res.task ? { label: "Open", run: () => setSelectedId(res.task.task_id) } : void 0
          });
          return true;
        } catch (err) {
          fail(err);
          return false;
        }
      }
    };
    return a;
  }, [api, store, toast]);
  const onDrop = React9.useCallback((task, date) => actions.move(task, date), [actions]);
  const pending = discoveryBadge(runs, streams);
  const ctx = React9.useMemo(() => ({
    api,
    store,
    meta: meta || {},
    today: today || meta && meta.today,
    prefs,
    setPrefs,
    actions,
    selectedId,
    narrow,
    host: host2,
    chat
  }), [api, store, meta, today, prefs, setPrefs, actions, selectedId, narrow, host2, chat]);
  const [height, setHeight] = React9.useState(null);
  React9.useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el || settingsOnly) return void 0;
    const fit = () => {
      const parent = el.parentElement;
      const ph = parent ? parent.getBoundingClientRect().height : 0;
      if (host2 === "desktop" && ph > 300) {
        setHeight(null);
        return;
      }
      const top = el.getBoundingClientRect().top;
      const vh = window.visualViewport && window.visualViewport.height || window.innerHeight;
      setHeight(Math.max(420, Math.round(vh - Math.max(0, top) - 8)));
    };
    fit();
    window.addEventListener("resize", fit);
    if (window.visualViewport) window.visualViewport.addEventListener("resize", fit);
    return () => {
      window.removeEventListener("resize", fit);
      if (window.visualViewport) window.visualViewport.removeEventListener("resize", fit);
    };
  }, [host2, settingsOnly]);
  const content = (() => {
    if (!meta && metaError) {
      return /* @__PURE__ */ React9.createElement(Centered, { icon: "alert", title: "Alchemy Task is not responding", text: describeError(metaError) });
    }
    if (!meta || !ctx.today) return /* @__PURE__ */ React9.createElement("div", { className: "at-loading" }, /* @__PURE__ */ React9.createElement(Spinner, { size: 18 }));
    if (meta.configured === false) {
      return /* @__PURE__ */ React9.createElement(
        Centered,
        {
          icon: "list",
          title: "Set up your tasks",
          text: "Alchemy Task is installed but not set up yet. Setup takes a few minutes in chat: your timezone, where tasks are saved, and your areas.",
          action: /* @__PURE__ */ React9.createElement(SetupPrompt, { text: "Set up my tasks" })
        }
      );
    }
    if (settingsOnly) return /* @__PURE__ */ React9.createElement(SettingsPanel, { inline: true, narrow });
    return /* @__PURE__ */ React9.createElement(React9.Fragment, null, /* @__PURE__ */ React9.createElement("nav", { className: "at-appbar" }, narrow ? null : /* @__PURE__ */ React9.createElement("span", { className: "at-brand" }, /* @__PURE__ */ React9.createElement(BrandMark, { size: 20 }), "Alchemy Task"), /* @__PURE__ */ React9.createElement("div", { className: "at-tabs", role: "tablist" }, /* @__PURE__ */ React9.createElement("button", { type: "button", role: "tab", "aria-selected": tab === "tasks", className: cx("at-tab", tab === "tasks" && "is-on"), onClick: () => setTab("tasks") }, "Tasks"), /* @__PURE__ */ React9.createElement("button", { type: "button", role: "tab", "aria-selected": tab === "discovery", className: cx("at-tab", tab === "discovery" && "is-on"), onClick: () => setTab("discovery") }, "Discovery", pending ? /* @__PURE__ */ React9.createElement("span", { className: "at-badge-dot" }, pending) : null)), /* @__PURE__ */ React9.createElement("span", { className: "at-flex" }), busy ? /* @__PURE__ */ React9.createElement(Spinner, { size: 12 }) : null, /* @__PURE__ */ React9.createElement(IconButton, { icon: "gear", label: "Settings", className: cx(settingsOpen && "is-on"), onClick: () => {
      setSelectedId(null);
      setSettingsOpen((v) => !v);
    } })), /* @__PURE__ */ React9.createElement("div", { className: cx("at-main", selectedId && !narrow && "has-panel", settingsOpen && !narrow && "has-panel") }, tab === "tasks" ? /* @__PURE__ */ React9.createElement(TasksView, { narrow }) : /* @__PURE__ */ React9.createElement(DiscoveryView, { runs, streams, error: runsError, loading: runsLoading, reload: loadRuns })), selectedId ? /* @__PURE__ */ React9.createElement(TaskPanel, { id: selectedId, narrow, onClose: () => setSelectedId(null) }) : null, settingsOpen && !selectedId ? /* @__PURE__ */ React9.createElement(SettingsPanel, { narrow, onClose: () => setSettingsOpen(false) }) : null);
  })();
  return /* @__PURE__ */ React9.createElement(AppContext.Provider, { value: ctx }, /* @__PURE__ */ React9.createElement(
    "div",
    {
      ref: rootRef,
      className: cx("at-root at-vars", narrow && "is-narrow", `host-${host2}`, settingsOnly && "is-settings-only"),
      style: height ? { height } : void 0
    },
    /* @__PURE__ */ React9.createElement(DragProvider, { onDrop }, /* @__PURE__ */ React9.createElement(OverlayHost, { rootRef }, content)),
    /* @__PURE__ */ React9.createElement(ToastOutlet, null)
  ));
}
var selToday2 = (s) => s.today;
var selLoading = (s) => s.loading > 0;
function Centered({ icon, title, text, action }) {
  return /* @__PURE__ */ React9.createElement("div", { className: "at-emptystate is-full" }, /* @__PURE__ */ React9.createElement("span", { className: "at-emptystate-icon" }, /* @__PURE__ */ React9.createElement(Icon, { name: icon, size: 22 })), /* @__PURE__ */ React9.createElement("h2", null, title), /* @__PURE__ */ React9.createElement("p", null, text), action || null);
}

// ui/src/styles.css
var styles_default = '@font-face{font-family:AT Barlow Condensed;font-style:normal;font-weight:500;font-display:swap;src:url(data:font/woff2;base64,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) format("woff2")}@font-face{font-family:AT Barlow Condensed;font-style:normal;font-weight:600;font-display:swap;src:url(data:font/woff2;base64,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) format("woff2")}.at-vars{--at-canvas: #06072a;--at-canvas-deep: #04051f;--at-surface: #0b0d38;--at-raised: #10134a;--at-inset: rgba(4, 5, 30, .55);--at-fg: #eef0ff;--at-fg2: #c4c8f0;--at-muted: #8b91c9;--at-faint: #5b619c;--at-ink: #070a3d;--at-line: rgba(150, 160, 255, .16);--at-line-soft: rgba(150, 160, 255, .09);--at-line-strong: rgba(170, 178, 255, .3);--at-hover: rgba(160, 170, 255, .06);--at-press: rgba(160, 170, 255, .11);--at-soft: rgba(160, 170, 255, .055);--at-accent: #2f37ff;--at-accent-hi: #4a52ff;--at-accent-text: #949bff;--at-accent-fg: #ffffff;--at-accent-tint: rgba(60, 70, 255, .16);--at-glow: 0 0 0 1px rgba(90, 100, 255, .55), 0 6px 24px rgba(40, 50, 255, .38);--at-late: #ffb35c;--at-ok: #5be3a6;--at-danger: #ff6b81;--at-display: "AT Barlow Condensed", "Barlow Condensed", "Roboto Condensed", "Arial Narrow", sans-serif;--at-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Segoe UI", system-ui, sans-serif;--at-mono: ui-monospace, "SF Mono", "JetBrains Mono", "Cascadia Mono", Menlo, monospace;--at-r-sm: 4px;--at-r: 8px;--at-r-lg: 12px;--at-shadow: 0 1px 0 rgba(255, 255, 255, .03) inset, 0 10px 30px rgba(0, 0, 8, .45);--at-shadow-lg: 0 1px 0 rgba(255, 255, 255, .04) inset, 0 24px 70px rgba(0, 0, 10, .6), 0 2px 8px rgba(0, 0, 10, .4);--at-ease: cubic-bezier(.2, .8, .2, 1);color-scheme:dark}.at-root{position:relative;display:flex;flex-direction:column;min-height:420px;height:100%;overflow:hidden;color:var(--at-fg);background:radial-gradient(900px 420px at 8% -12%,rgba(47,55,255,.2),transparent 62%),radial-gradient(700px 380px at 100% -8%,rgba(110,90,255,.09),transparent 60%),var(--at-canvas);font-family:var(--at-sans);font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;letter-spacing:-.003em}.at-root:before{content:"";position:absolute;inset:0;pointer-events:none;z-index:0;background-image:radial-gradient(rgba(170,180,255,.07) 1px,transparent 1.2px);background-size:4px 4px;-webkit-mask-image:linear-gradient(180deg,rgba(0,0,0,.55),transparent 220px);mask-image:linear-gradient(180deg,rgba(0,0,0,.55),transparent 220px)}.at-root.host-dashboard{border:1px solid var(--at-line-soft);border-radius:var(--at-r-lg)}.at-root :where(*,*:before,*:after){box-sizing:border-box}.at-root :where(button,input,textarea){font:inherit;color:inherit}.at-root :where(h1,h2,h3,p){margin:0}.at-root ::selection{background:#505aff73;color:#fff}.at-root.is-settings-only{height:auto;overflow:visible;min-height:0;background:transparent}.at-root.is-settings-only:before{display:none}.at-flex{flex:1 1 auto;min-width:0}.at-muted{color:var(--at-muted)}.at-mono{font-family:var(--at-mono);font-size:11.5px;letter-spacing:0}.at-break{word-break:break-all}.at-scroll{overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;scrollbar-width:thin;scrollbar-color:rgba(150,160,255,.22) transparent}.at-scroll::-webkit-scrollbar{width:8px;height:8px}.at-scroll::-webkit-scrollbar-thumb{background:#96a0ff33;border-radius:8px;border:2px solid transparent;background-clip:padding-box}.at-icon{flex:none;display:block}.at-loading{flex:1;display:grid;place-items:center;min-height:200px}.at-spinner{display:inline-block;flex:none;border-radius:50%;border:1.6px solid var(--at-line);border-top-color:var(--at-accent-text);animation:at-spin .8s linear infinite}@keyframes at-spin{to{transform:rotate(360deg)}}.at-body-label,.at-state-label,.at-prop-label,.at-menu-label,.at-set-sec h3,.at-month-dows>div,.at-week-dow,.at-mmonth-dows span,.at-dp-dow,.at-kicker{font-family:var(--at-mono);font-size:10.5px;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--at-muted)}.at-body-label:before,.at-state-label:before,.at-prop-label:before,.at-set-sec h3:before,.at-kicker:before{content:"// ";color:var(--at-faint);letter-spacing:0}.at-appbar{position:relative;z-index:1;display:flex;align-items:center;gap:10px;flex:none;height:54px;padding:0 14px 0 18px;border-bottom:1px solid var(--at-line-soft);background:linear-gradient(180deg,#06072a33,#06072a99)}.at-brand{display:inline-flex;align-items:center;gap:9px;margin-right:18px;padding-right:18px;border-right:1px solid var(--at-line-soft);height:22px;font-family:var(--at-display);font-weight:600;font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:var(--at-fg)}.at-brand-mark{flex:none;color:#eef0ff;transform:translateY(.35px);filter:drop-shadow(0 0 5px rgba(120,130,255,.85)) drop-shadow(0 0 12px rgba(80,90,255,.55))}.at-tabs{display:flex;gap:4px;height:100%}.at-tab{position:relative;display:inline-flex;align-items:center;gap:8px;padding:0 12px;border:0;background:none;cursor:pointer;font-family:var(--at-display);font-weight:600;font-size:15.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--at-muted);transition:color .15s}.at-tab:hover,.at-tab.is-on{color:var(--at-fg)}.at-tab.is-on:after{content:"";position:absolute;left:12px;right:12px;bottom:-1px;height:2px;background:var(--at-accent-hi);box-shadow:0 0 12px #505affe6}.at-badge-dot{min-width:19px;height:19px;padding:0 5px;border-radius:3px;display:inline-grid;place-items:center;background:var(--at-accent);color:#fff;box-shadow:0 0 12px #3c46ffb3;font-family:var(--at-mono);font-size:10.5px;font-weight:600;letter-spacing:0;font-variant-numeric:tabular-nums}.at-main{position:relative;z-index:1;flex:1;min-height:0;display:flex;flex-direction:column;transition:margin-right .22s var(--at-ease)}.at-main.has-panel{margin-right:min(460px,46%)}.at-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;flex:none;height:34px;padding:0 14px;border-radius:var(--at-r-sm);cursor:pointer;border:1px solid var(--at-line);background:#a0aaff0a;font-family:var(--at-display);font-weight:600;font-size:14.5px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap;color:var(--at-fg);transition:background .15s,border-color .15s,opacity .15s,transform .08s,box-shadow .2s}.at-btn:hover{background:var(--at-hover);border-color:var(--at-line-strong)}.at-btn:active{transform:translateY(.5px)}.at-btn:disabled{opacity:.4;cursor:default}.at-btn-sm{height:30px;padding:0 12px;font-size:13.5px}.at-btn-primary{background:var(--at-accent);border-color:#8c96ff73;color:#fff;box-shadow:0 4px 18px #2832ff59}.at-btn-primary:hover{background:var(--at-accent-hi);border-color:#aab2ff99;box-shadow:var(--at-glow)}.at-btn-ghost{background:transparent;border-color:transparent;color:var(--at-fg2)}.at-btn-ghost:hover{background:var(--at-hover);border-color:transparent;color:var(--at-fg)}.at-iconbtn{display:inline-grid;place-items:center;flex:none;width:32px;height:32px;border-radius:var(--at-r-sm);border:1px solid transparent;background:transparent;color:var(--at-muted);cursor:pointer;transition:background .15s,color .15s,border-color .15s}.at-iconbtn:hover,.at-iconbtn.is-on{background:var(--at-hover);border-color:var(--at-line-soft);color:var(--at-fg)}.at-iconbtn:disabled{opacity:.35;cursor:default}.at-seg{display:inline-flex;padding:3px;gap:2px;border-radius:6px;flex:none;background:var(--at-inset);border:1px solid var(--at-line-soft)}.at-seg-item{height:28px;padding:0 14px;border:0;border-radius:3px;background:transparent;cursor:pointer;font-family:var(--at-display);font-size:14px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--at-muted);transition:background .15s,color .15s,box-shadow .15s}.at-seg-item:hover{color:var(--at-fg)}.at-seg-item.is-on{background:#eef0ff;color:var(--at-ink);box-shadow:0 2px 10px #00000a66}.at-field,.at-filter{display:inline-flex;align-items:center;gap:7px;flex:none;max-width:100%;height:32px;padding:0 12px;border-radius:6px;cursor:pointer;border:1px solid var(--at-line);background:#a0aaff09;font-size:13px;color:var(--at-fg2);white-space:nowrap;transition:background .15s,border-color .15s,color .15s}.at-field:hover,.at-filter:hover{background:var(--at-hover);border-color:var(--at-line-strong);color:var(--at-fg)}.at-field .at-icon,.at-filter .at-icon{color:var(--at-muted)}.at-field.is-late{color:var(--at-late);border-color:#ffb35c61;background:#ffb35c0f}.at-field.is-late .at-icon,.at-field.is-high{color:var(--at-late)}.at-field.is-plain{border-color:transparent;background:transparent;padding:0 8px;margin-left:-8px}.at-filter.is-on{border-color:var(--at-line-strong);color:var(--at-fg)}.at-timefield input{border:0;background:transparent;outline:none;padding:0;width:7.2em;font-family:var(--at-mono);font-size:12.5px;font-variant-numeric:tabular-nums}.at-link{border:0;background:none;padding:0;cursor:pointer;color:var(--at-accent-text);font-size:12.5px;font-weight:550;white-space:nowrap}.at-link:hover{color:#c3c7ff;text-decoration:underline;text-underline-offset:3px}.at-linkish{border:0;background:none;padding:0;cursor:pointer;font-weight:550;text-align:left}.at-linkish:hover{text-decoration:underline;text-underline-offset:3px}.at-chip{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:3px;border:0;font-family:var(--at-mono);font-size:10.5px;font-weight:500;letter-spacing:.04em;background:var(--at-soft);color:var(--at-fg2);cursor:pointer;white-space:nowrap}.at-chip.at-tone-late{background:#ffb35c24;color:var(--at-late);text-transform:uppercase;letter-spacing:.08em}.at-count{display:inline-grid;place-items:center;min-width:20px;height:19px;padding:0 6px;border-radius:3px;background:var(--at-soft);color:var(--at-fg2);font-family:var(--at-mono);font-size:10.5px;font-weight:600;letter-spacing:.02em;font-variant-numeric:tabular-nums}.at-count.is-accent{background:var(--at-accent-tint);color:var(--at-accent-text)}.at-badge{display:inline-flex;align-items:center;height:18px;padding:0 6px;border-radius:3px;background:var(--at-soft);font-family:var(--at-mono);font-size:10px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--at-muted)}.at-areadot{display:inline-block;flex:none;width:7px;height:7px;border-radius:50%;background:var(--at-area);box-shadow:0 0 8px color-mix(in srgb,var(--at-area) 55%,transparent)}.at-statusdot{display:inline-block;flex:none;width:7px;height:7px;border-radius:50%;background:var(--at-faint)}.at-statusdot.is-ok{background:var(--at-ok);box-shadow:0 0 8px #5be3a699}.at-statusdot.is-late{background:var(--at-late);box-shadow:0 0 8px #ffb35c8c}.at-switch{position:relative;width:40px;height:23px;border-radius:999px;border:1px solid var(--at-line);cursor:pointer;background:var(--at-inset);transition:background .18s,border-color .18s,box-shadow .18s}.at-switch i{position:absolute;top:2px;left:2px;width:17px;height:17px;border-radius:50%;background:#d8dbff;box-shadow:0 1px 3px #0006;transition:transform .2s var(--at-ease)}.at-switch.is-on{background:var(--at-accent);border-color:#8c96ff80;box-shadow:0 0 14px #3c46ff80}.at-switch.is-on i{transform:translate(17px);background:#fff}.at-check{position:relative;flex:none;display:inline-grid;place-items:center;width:20px;height:20px;padding:0;margin:0;border-radius:50%;cursor:pointer;border:1.5px solid rgba(190,196,255,.38);background:transparent;transition:border-color .15s,background .18s var(--at-ease),transform .12s,box-shadow .2s}.at-check svg{width:12px;height:12px;fill:none;stroke:#fff;stroke-width:3;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:22;stroke-dashoffset:22;transition:stroke-dashoffset .22s var(--at-ease) .04s}.at-check:hover{border-color:var(--at-accent-text);box-shadow:0 0 0 4px #505aff24}.at-check:hover svg{stroke:var(--at-accent-text);stroke-dashoffset:0;opacity:.7}.at-check:active{transform:scale(.88)}.at-check.is-on{background:var(--at-accent);border-color:var(--at-accent-hi);box-shadow:0 0 10px #3c46ff99}.at-check.is-on svg{stroke:#fff;stroke-dashoffset:0;opacity:1}.at-check.at-tone-high:not(.is-on){border-color:#ffb35cbf}.at-check-sm{width:13px;height:13px;border-width:1.3px}.at-check-sm svg{width:8px;height:8px;stroke-width:3.6}.at-check-lg{width:26px;height:26px;border-width:1.6px}.at-check-lg svg{width:15px;height:15px}.at-check.is-ghost{border-style:dashed;cursor:default}.at-tasks{flex:1;min-height:0;display:flex;flex-direction:column;position:relative}.at-toolbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;flex:none;padding:20px 24px 16px}.at-toolbar-nav{display:flex;align-items:center;gap:4px;min-width:0}.at-toolbar-nav .at-btn{margin-right:8px}.at-toolbar-right{display:flex;align-items:center;gap:10px;margin-left:auto}.at-period{font-family:var(--at-display);font-size:34px;font-weight:500;line-height:1;letter-spacing:.005em;margin-left:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--at-fg)}.at-period-year{color:var(--at-faint);margin-left:.22em}.at-viewport{flex:1;min-height:0;display:flex;flex-direction:column}.at-row{position:relative;display:flex;align-items:flex-start;gap:12px;padding:10px 8px 10px 10px;border-radius:var(--at-r);cursor:pointer;outline:none;transition:background .12s,opacity .2s,box-shadow .15s;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}.at-row:hover{background:var(--at-hover)}.at-row:focus-visible{box-shadow:inset 0 0 0 1.5px #7882ffb3}.at-row.is-selected{background:var(--at-accent-tint);box-shadow:inset 2px 0 0 var(--at-accent-hi)}.at-row>.at-check{margin-top:1px}.at-row-main{flex:1;min-width:0}.at-row-title{font-size:14px;font-weight:450;color:var(--at-fg);overflow-wrap:anywhere;transition:color .2s}.at-row.is-done .at-row-title{color:var(--at-faint);text-decoration:line-through;text-decoration-color:#96a0ff59}.at-row-meta{display:flex;flex-wrap:wrap;align-items:center;gap:3px 12px;margin-top:4px;font-family:var(--at-mono);font-size:10.5px;letter-spacing:.03em;color:var(--at-muted)}.at-row.is-done .at-row-meta{opacity:.55}.at-meta-area{display:inline-flex;align-items:center;gap:6px;text-transform:uppercase;letter-spacing:.08em}.at-meta-date.is-late,.at-meta-prio{color:var(--at-late)}.at-meta-prio{font-weight:600;text-transform:uppercase;letter-spacing:.08em}.at-meta-status{text-transform:uppercase;letter-spacing:.08em}.at-meta-status.is-active{color:var(--at-accent-text)}.at-meta-research{display:inline-flex;align-items:center;gap:4px;color:var(--at-accent-text);text-transform:uppercase;letter-spacing:.08em}.at-row-more{opacity:0;margin:-5px -2px -5px 0;transition:opacity .15s}.at-row:hover .at-row-more,.at-row:focus-within .at-row-more,.at-root.is-narrow .at-row-more{opacity:1}.at-root.is-narrow .at-row-more{color:var(--at-faint);border-color:transparent;background:transparent}.at-row.is-compact{gap:7px;padding:4px 6px;border-radius:5px;align-items:flex-start}.at-row.is-compact>.at-check{margin-top:2.5px}.at-row.is-compact .at-row-title{font-size:12.5px;line-height:1.35;color:var(--at-fg2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.at-row.is-compact:hover .at-row-title{color:var(--at-fg)}.at-row.is-compact.is-done .at-row-title{color:var(--at-faint)}.at-daylist{position:relative;display:flex;flex-direction:column;gap:1px;border-radius:var(--at-r-lg);transition:background .15s,box-shadow .15s;min-height:8px}.at-daylist.is-over,.at-cell.is-over,.at-mcell.is-over{background:#3c46ff1f;box-shadow:inset 0 0 0 1.5px #6e78ffb3,0 0 24px #3c46ff40}.at-drop-hint{padding:6px 10px;font-family:var(--at-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--at-accent-text)}.at-empty-day{padding:9px 10px;font-size:13px;color:var(--at-faint)}.at-add{display:flex;align-items:center;gap:12px;width:100%;padding:9px 10px;margin-top:2px;border:0;border-radius:var(--at-r);background:transparent;cursor:pointer;text-align:left;font-size:13.5px;color:var(--at-faint);transition:background .12s,color .12s}.at-add .at-icon{width:20px}.at-add:hover{background:var(--at-hover);color:var(--at-accent-text)}.at-add-form{display:flex;align-items:center;gap:12px;padding:8px 10px;border-radius:var(--at-r);background:var(--at-inset);box-shadow:inset 0 0 0 1px #6e78ff80,0 0 20px #3c46ff26}.at-add-input{flex:1;min-width:0;border:0;background:transparent;outline:none;font-size:14px;padding:2px 0}.at-add-input::placeholder{color:var(--at-faint)}.at-pop-add{padding:8px}.at-disc{border-radius:var(--at-r)}.at-disc-head{display:flex;align-items:center;gap:9px;width:100%;padding:9px 10px;border:0;background:none;cursor:pointer;border-radius:var(--at-r);text-align:left;font-family:var(--at-display);font-size:14.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--at-fg2)}.at-disc-head:hover{background:var(--at-hover)}.at-disc-chev{transition:transform .18s var(--at-ease);color:var(--at-muted)}.at-disc.is-open>.at-disc-head .at-disc-chev{transform:rotate(90deg)}.at-disc-body{padding:2px 0 6px;animation:at-fade .18s var(--at-ease)}@keyframes at-fade{0%{opacity:0;transform:translateY(-3px)}}.at-overdue{margin-bottom:6px;background:linear-gradient(90deg,#ffb35c17,#ffb35c06);box-shadow:inset 2px 0 0 var(--at-late)}.at-overdue>.at-disc-head{color:var(--at-late)}.at-overdue>.at-disc-head:hover{background:#ffb35c0f}.at-overdue>.at-disc-head .at-disc-chev{color:var(--at-late)}.at-overdue .at-count{background:#ffb35c29;color:var(--at-late)}.at-overdue .at-link{color:var(--at-late);display:none;font-family:var(--at-mono);font-size:10.5px;font-weight:500;letter-spacing:.1em;text-transform:uppercase}.at-overdue.is-open .at-link,.at-overdue .at-disc-head:hover .at-link,.at-root.is-narrow .at-overdue .at-link{display:inline}.at-disc-head{min-width:0}.at-disc-title{white-space:nowrap}.at-overdue .at-disc-body{padding:0 4px 6px}.at-month{flex:1;min-height:0;display:flex;flex-direction:column;padding:0 24px 20px;overflow-y:auto}.at-month-dows{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));padding:0 0 8px}.at-month-dows>div{padding:0 10px}.at-month-grid{flex:none;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border:1px solid var(--at-line);border-radius:var(--at-r-lg);overflow:hidden;background:#080a328c;box-shadow:0 20px 60px #00000a59}.at-cell{position:relative;min-width:0;min-height:0;aspect-ratio:1;display:flex;flex-direction:column;gap:2px;padding:7px 5px 5px;cursor:pointer;overflow:hidden;border-right:1px solid var(--at-line-soft);border-bottom:1px solid var(--at-line-soft);transition:background .12s}.at-cell:nth-child(7n){border-right:0}.at-cell:hover{background:#a0aaff09}.at-cell.is-out{background:#02031459}.at-cell.is-out .at-cell-num{color:var(--at-faint);opacity:.7}.at-cell.is-out .at-row-title{opacity:.6}.at-cell.is-today{background:linear-gradient(180deg,#3c46ff29,#3c46ff0d);box-shadow:inset 0 0 0 1px #6e78ff8c}.at-cell-head{display:flex;align-items:center;gap:6px;padding:0 5px 3px;min-height:22px}.at-cell-num{font-family:var(--at-mono);font-size:11.5px;font-weight:500;color:var(--at-fg2);font-variant-numeric:tabular-nums;line-height:20px;min-width:20px;letter-spacing:.02em}.at-cell.is-past:not(.is-out):not(.is-today) .at-cell-num{color:var(--at-muted)}.at-cell.is-today .at-cell-num{display:inline-grid;place-items:center;height:20px;padding:0 6px;border-radius:3px;background:#eef0ff;color:var(--at-ink);font-weight:700;box-shadow:0 0 14px #96a0ff8c}.at-cell-list{position:relative;flex:1;display:flex;flex-direction:column;gap:1px;min-height:0;overflow:hidden}.at-cell-list.is-tight .at-row-title{-webkit-line-clamp:1}.at-cell-list.is-tight .at-row.is-compact{flex:none;height:24px;min-height:0;padding-top:2px;padding-bottom:2px;overflow:hidden}.at-cell-more{position:absolute;bottom:0;left:6px;height:18px;margin:0;padding:1px 6px;border:0;background:none;border-radius:3px;cursor:pointer;font-family:var(--at-mono);font-size:10px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--at-muted)}.at-cell-more:hover{background:var(--at-hover);color:var(--at-accent-text)}.at-cell-footer{flex:none;height:20px;display:flex;justify-content:flex-end}.at-cell-view{display:inline-flex;align-items:center;gap:3px;padding:1px 4px;border:0;border-radius:3px;background:none;color:var(--at-muted);font:10px var(--at-mono);cursor:pointer;opacity:0;transition:opacity .12s}.at-cell:hover .at-cell-view,.at-cell:focus-within .at-cell-view{opacity:1}.at-cell-view:hover,.at-cell-view:focus-visible{color:var(--at-accent-text);background:var(--at-hover)}@media(hover:none){.at-cell-view{opacity:1}}.at-daypop{display:flex;flex-direction:column;max-height:min(560px,70vh)}.at-daypop-head{display:flex;align-items:flex-start;gap:8px;padding:16px 14px 10px 18px;border-bottom:1px solid var(--at-line-soft);margin-bottom:6px}.at-daypop-head>div{flex:1}.at-daypop-title{font-family:var(--at-display);font-size:24px;font-weight:500;line-height:1.05}.at-daypop-head .at-muted{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;margin-top:4px}.at-daypop-body{padding:0 8px 10px;overflow-y:auto}.at-mmonth{flex:1;padding:0 14px 110px}.at-mmonth-dows,.at-mmonth-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}.at-mmonth-dows span{text-align:center;padding-bottom:6px;letter-spacing:.06em}.at-mmonth-grid{gap:2px;margin-bottom:16px;padding:6px;border-radius:14px;background:#080a3299;border:1px solid var(--at-line-soft)}.at-mcell{position:relative;display:flex;flex-direction:column;align-items:center;gap:4px;height:52px;padding-top:5px;border:0;border-radius:10px;background:transparent;cursor:pointer}.at-mcell-num{display:grid;place-items:center;width:30px;height:30px;border-radius:8px;font-family:var(--at-mono);font-size:14px;font-weight:500;font-variant-numeric:tabular-nums;color:var(--at-fg2)}.at-mcell.is-out .at-mcell-num{color:var(--at-faint);opacity:.6}.at-mcell.is-today .at-mcell-num{color:var(--at-accent-text);font-weight:700}.at-mcell.is-on .at-mcell-num{background:#a0aaff1a;box-shadow:inset 0 0 0 1px var(--at-line-strong);color:var(--at-fg)}.at-mcell.is-today.is-on .at-mcell-num{background:#eef0ff;color:var(--at-ink);box-shadow:0 0 16px #96a0ff8c}.at-mcell-dots{display:flex;gap:3px;height:4px}.at-mcell-dots i{width:4px;height:4px;border-radius:50%;background:var(--at-accent-text);box-shadow:0 0 5px #7882ffcc}.at-mcell-dots i.is-done{background:var(--at-faint);box-shadow:none}.at-mcell-dots i.is-late{background:var(--at-late);box-shadow:0 0 5px #ffb35cb3}.at-mcell-more{position:absolute;right:3px;top:2px;font-family:var(--at-mono);font-size:8.5px;color:var(--at-muted)}.at-desktop-week{flex:1;min-height:0}.at-week-strip{flex:none;overflow:visible}.at-cell.is-picked{box-shadow:inset 0 0 0 2px var(--at-accent)}.at-desktop-week .at-dayview{overflow:visible}.at-week{flex:1;min-height:0;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:0;padding:0 16px 16px}.at-week-col{display:flex;flex-direction:column;min-height:0;min-width:0;padding:0 5px;border-right:1px solid var(--at-line-soft)}.at-week-col:last-child{border-right:0}.at-week-col.is-today{background:linear-gradient(180deg,rgba(60,70,255,.12),transparent 70%);border-radius:var(--at-r-lg) var(--at-r-lg) 0 0}.at-week-head{display:flex;flex-direction:column;gap:2px;padding:8px 10px 14px}.at-week-num{font-family:var(--at-display);font-size:32px;font-weight:500;line-height:1;font-variant-numeric:tabular-nums}.at-week-col.is-past .at-week-num{color:var(--at-faint)}.at-week-col.is-today .at-week-num{color:#fff;text-shadow:0 0 18px rgba(130,140,255,.9)}.at-week-col.is-today .at-week-dow{color:var(--at-accent-text)}.at-week-body{flex:1;min-height:0;overflow-x:hidden}.at-week-body .at-daylist{min-height:100%}.at-week .at-row{padding:8px 6px 8px 7px;gap:9px}.at-week .at-row-title{font-size:13px}.at-week .at-check{width:17px;height:17px}.at-week .at-row-meta{font-size:10px}.at-dayview{flex:1;min-height:0}.at-dayview-inner{max-width:760px;margin:0 auto;padding:8px 28px 72px}.at-dayview-head{padding:6px 10px 20px}.at-dayview-head h2{font-family:var(--at-display);font-size:52px;font-weight:500;line-height:.95}.at-dayview-head .at-muted{font-family:var(--at-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin-top:8px}.at-days{flex:1;min-height:0;padding:0 10px 120px}.at-daysec{padding:2px 0 14px}.at-daysec-head{position:sticky;top:0;z-index:2;display:flex;align-items:baseline;gap:10px;padding:14px 10px 8px;background:#06072ad1;backdrop-filter:saturate(1.3) blur(14px);-webkit-backdrop-filter:saturate(1.3) blur(14px)}.at-daysec-title{font-family:var(--at-display);font-size:24px;font-weight:500;line-height:1;letter-spacing:.005em}.at-daysec-head .at-muted{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase}.at-daysec.is-today .at-daysec-title{color:#fff;text-shadow:0 0 20px rgba(130,140,255,.85)}.at-daysec.is-empty{padding-bottom:0}.at-daysec.is-empty .at-daysec-head{position:static;padding-top:10px;padding-bottom:0;background:none;backdrop-filter:none;-webkit-backdrop-filter:none}.at-daysec.is-empty .at-daysec-title{font-size:17px;color:var(--at-muted)}.at-daysec.is-empty .at-empty-day{padding-top:3px;padding-bottom:6px;font-size:12.5px}.at-sentinel{height:1px}.at-fab{position:absolute;right:18px;bottom:calc(20px + env(safe-area-inset-bottom,0px));z-index:20;width:58px;height:58px;border-radius:18px;border:1px solid rgba(160,170,255,.5);cursor:pointer;display:grid;place-items:center;background:linear-gradient(160deg,#4a52ff,#2a30f0);color:#fff;box-shadow:0 10px 30px #2832ff8c,0 0 0 6px #2f37ff1f;transition:transform .15s var(--at-ease),box-shadow .2s}.at-fab:active{transform:scale(.93)}.at-pop{position:absolute;z-index:60;max-width:calc(100% - 16px);background:linear-gradient(180deg,#14175a,#0e1048);color:var(--at-fg);border:1px solid rgba(150,160,255,.22);border-radius:var(--at-r-lg);box-shadow:var(--at-shadow-lg);animation:at-pop .16s var(--at-ease)}@keyframes at-pop{0%{opacity:0;transform:translateY(-4px) scale(.98)}}.at-menu{padding:6px;display:flex;flex-direction:column}.at-menu .at-menu{padding:0}.at-menu-label{padding:8px 10px 5px}.at-menu-item{display:flex;align-items:center;gap:10px;width:100%;height:36px;padding:0 10px;border:0;border-radius:6px;background:none;cursor:pointer;text-align:left;font-size:13.5px;color:var(--at-fg)}.at-menu-item:hover{background:#505aff38}.at-menu-item .at-icon{color:var(--at-muted)}.at-menu-item:hover .at-icon{color:var(--at-fg)}.at-menu-item.is-danger{color:var(--at-danger)}.at-menu-pad{width:15px;flex:none}.at-menu-hint{color:var(--at-muted);font-family:var(--at-mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase}.at-menu-sep{height:1px;margin:5px 6px;background:var(--at-line-soft)}.at-dp{padding:10px}.at-dp-quick{display:grid;grid-template-columns:1fr 1fr;gap:5px;padding-bottom:10px;border-bottom:1px solid var(--at-line-soft);margin-bottom:8px}.at-dp-q{display:flex;flex-direction:column;align-items:flex-start;gap:1px;padding:8px 10px;border:1px solid var(--at-line-soft);border-radius:6px;background:#a0aaff0a;cursor:pointer;text-align:left;font-size:13px;font-weight:550}.at-dp-q .at-muted{font-family:var(--at-mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;font-weight:500}.at-dp-q:hover{background:#505aff2e;border-color:var(--at-line)}.at-dp-q.is-on{box-shadow:inset 0 0 0 1px var(--at-accent-hi);background:var(--at-accent-tint)}.at-dp-head{display:flex;align-items:center;gap:2px;padding:2px 2px 6px 8px}.at-dp-title{flex:1;font-family:var(--at-display);font-weight:600;font-size:17px;letter-spacing:.04em;text-transform:uppercase}.at-dp-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}.at-dp-dow{text-align:center;padding:2px 0 6px;letter-spacing:.04em}.at-dp-day{height:34px;border:0;border-radius:6px;background:none;cursor:pointer;font-family:var(--at-mono);font-size:12.5px;font-variant-numeric:tabular-nums;color:var(--at-fg2);transition:background .1s}.at-dp-day:hover{background:var(--at-hover);color:var(--at-fg)}.at-dp-day.is-out{color:var(--at-faint)}.at-dp-day.is-today{color:var(--at-accent-text);font-weight:700}.at-dp-day.is-on{background:var(--at-accent);color:#fff;font-weight:650;box-shadow:0 0 14px #3c46ff99}.at-dp-foot{display:flex;align-items:center;gap:8px;padding-top:8px;margin-top:8px;border-top:1px solid var(--at-line-soft)}.at-toasts{position:absolute;left:50%;bottom:calc(22px + env(safe-area-inset-bottom,0px));z-index:80;transform:translate(-50%);display:flex;flex-direction:column;align-items:center;gap:8px;width:min(480px,calc(100% - 24px));pointer-events:none}.at-root.is-narrow .at-toasts{bottom:calc(92px + env(safe-area-inset-bottom,0px))}.at-toast{pointer-events:auto;display:flex;align-items:center;gap:12px;max-width:100%;padding:9px 9px 9px 16px;border-radius:10px;background:#121550eb;color:var(--at-fg);border:1px solid rgba(150,160,255,.25);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:var(--at-shadow-lg);font-size:13.5px;font-weight:500;animation:at-toast .24s var(--at-ease)}.at-toast span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@keyframes at-toast{0%{opacity:0;transform:translateY(8px) scale(.98)}}.at-toast.at-tone-error{border-color:#ffb35c59}.at-toast.at-tone-error .at-icon{color:var(--at-late)}.at-toast-act{flex:none;height:28px;padding:0 11px;border:0;border-radius:4px;cursor:pointer;background:#eef0ff;color:var(--at-ink);font-family:var(--at-display);font-weight:600;font-size:13.5px;letter-spacing:.08em;text-transform:uppercase}.at-toast-act:hover{background:#fff}.at-drag-ghost{position:fixed;left:0;top:0;z-index:2147483000;pointer-events:none;padding:10px 14px;border-radius:8px;font-family:var(--at-sans);font-size:13.5px;font-weight:550;background:#14175a;color:var(--at-fg);border:1px solid rgba(130,140,255,.6);box-shadow:var(--at-glow),var(--at-shadow-lg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:200px;max-width:320px;rotate:-1.5deg}html.at-dragging,html.at-dragging *{cursor:grabbing!important}html.at-dragging .at-row{pointer-events:none}html.at-dragging{-webkit-user-select:none;user-select:none}.at-panel{position:absolute;z-index:40;display:flex;flex-direction:column;background:linear-gradient(180deg,#0d0f42,#090b34);color:var(--at-fg)}.at-panel.is-side{top:0;right:0;bottom:0;width:min(460px,46%);border-left:1px solid var(--at-line);box-shadow:-24px 0 60px #00000a73;animation:at-slide .22s var(--at-ease)}@keyframes at-slide{0%{transform:translate(24px);opacity:0}}.at-panel.is-sheet{inset:12px 0 0;border-radius:18px 18px 0 0;border-top:1px solid var(--at-line-strong);box-shadow:0 -20px 60px #00000a99;animation:at-sheet .28s var(--at-ease)}@keyframes at-sheet{0%{transform:translateY(40px);opacity:.4}}.at-panel-bar{display:flex;align-items:center;gap:4px;flex:none;height:52px;padding:0 12px 0 20px;position:relative}.at-panel-heading{font-family:var(--at-display);font-size:20px;font-weight:600;letter-spacing:.08em;text-transform:uppercase}.at-grabber{position:absolute;left:50%;top:7px;width:38px;height:4px;margin-left:-19px;border-radius:4px;background:var(--at-line-strong)}.at-panel-body{flex:1;min-height:0;padding:0 24px 56px}.at-panel-empty{display:flex;flex-direction:column;align-items:center;gap:12px;padding:64px 12px;color:var(--at-muted);text-align:center}.at-panel-loading{padding:24px 0}.at-panel-titlerow{display:flex;align-items:flex-start;gap:14px;padding:4px 0 16px}.at-panel-titlerow .at-check{margin-top:5px}.at-title-input{flex:1;min-width:0;resize:none;overflow:hidden;border:0;outline:none;background:transparent;padding:0;font-family:var(--at-display);font-size:30px;line-height:1.08;font-weight:500;letter-spacing:.003em;border-radius:4px}.at-title-input:focus:not(.is-idle){box-shadow:0 0 0 6px var(--at-soft);background:var(--at-soft)}.at-title-input.is-done{color:var(--at-muted);text-decoration:line-through;text-decoration-thickness:1.5px;text-decoration-color:#96a0ff73}.at-fields{display:flex;flex-wrap:wrap;gap:7px;padding:0 0 16px 40px}.at-prio-glyph{width:8px;height:8px;border-radius:2px;background:var(--at-faint)}.at-prio-glyph[data-p=urgent]{background:var(--at-danger);box-shadow:0 0 8px #ff6b81b3}.at-prio-glyph[data-p=high]{background:var(--at-late);box-shadow:0 0 8px #ffb35c99}.at-prio-glyph[data-p=low]{background:transparent;box-shadow:inset 0 0 0 1.5px var(--at-faint)}.at-summary-input{display:block;width:calc(100% - 30px);margin-left:30px!important;resize:none;overflow:hidden;border:0;outline:none;background:transparent;padding:8px 10px;margin:0 0 12px;border-radius:6px;font-size:14.5px;line-height:1.55;color:var(--at-fg2)}.at-summary-input:hover{background:var(--at-soft)}.at-summary-input:focus{background:var(--at-soft);color:var(--at-fg);box-shadow:inset 0 0 0 1px var(--at-line)}.at-summary-input::placeholder{color:var(--at-faint)}.at-research-note{display:flex;align-items:center;gap:9px;margin:0 0 14px;padding:10px 12px;border-radius:8px;font-size:13px;background:var(--at-accent-tint);color:var(--at-accent-text);box-shadow:inset 0 0 0 1px #6e78ff4d}.at-research-bar{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin:0 0 14px}.at-research-status{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--at-accent-text)}.at-banner{display:flex;align-items:center;gap:9px;padding:10px 12px;margin-bottom:14px;border-radius:8px;font-size:13px;background:var(--at-soft)}.at-banner.at-tone-late{background:#ffb35c1a;color:var(--at-late);box-shadow:inset 0 0 0 1px #ffb35c40}.at-banner .at-btn{color:var(--at-fg)}.at-body{border-top:1px solid var(--at-line-soft);padding-top:12px}.at-body-bar{display:flex;align-items:center;gap:10px;min-height:34px;margin-bottom:6px}.at-save{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--at-muted)}.at-save.is-error{color:var(--at-late)}.at-state{position:relative;margin:4px 0 16px;padding:14px 16px 12px;border-radius:8px;background:linear-gradient(135deg,#3c46ff24,#3c46ff0a);box-shadow:inset 0 0 0 1px #6e78ff38,inset 2px 0 0 var(--at-accent-hi)}.at-state-label{margin-bottom:6px;color:var(--at-accent-text)}.at-section{margin-bottom:10px}.at-section-title{font-family:var(--at-display);font-size:16px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;margin:18px 0 6px;color:var(--at-fg)}.at-fold{margin:6px -10px 0}.at-fold .at-disc-body{padding:0 10px 8px}.at-more{margin:18px -10px 0;border-top:1px solid var(--at-line-soft);padding-top:8px}.at-more .at-disc-body{padding:4px 10px 8px}.at-more-grid,.at-set-grid{display:grid;grid-template-columns:max-content 1fr;gap:12px 20px;align-items:center;font-size:13px}.at-research-model{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.at-model-input{cursor:text;width:220px;font-family:inherit;outline:none}.at-model-input.is-small{width:150px}.at-model-input:focus{border-color:var(--at-line-strong);color:var(--at-fg)}.at-research-model .at-copy-prompt{flex-basis:100%}.at-more-grid>.at-muted,.at-set-grid>.at-muted{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}.at-empty-notes{display:block;width:100%;padding:14px;border:1px dashed var(--at-line);border-radius:8px;background:none;cursor:pointer;color:var(--at-faint);text-align:left}.at-empty-notes:hover{color:var(--at-accent-text);border-color:#6e78ff80;background:var(--at-soft)}.at-editor{display:block;width:100%;min-height:320px;resize:vertical;padding:16px;border-radius:8px;border:1px solid var(--at-line);background:var(--at-canvas-deep);outline:none;color:var(--at-fg);font-family:var(--at-mono);font-size:12.5px;line-height:1.7}.at-editor:focus{border-color:#6e78ffb3;box-shadow:0 0 0 3px #3c46ff33}.at-editor-hint{margin-top:8px;font-family:var(--at-mono);font-size:10.5px;letter-spacing:.04em;color:var(--at-faint)}.at-md{font-size:14px;line-height:1.65;color:var(--at-fg2);overflow-wrap:anywhere}.at-md p{margin:0 0 9px}.at-md strong{color:var(--at-fg);font-weight:600}.at-md .at-md-h{margin:16px 0 5px;font-family:var(--at-display);font-size:15px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--at-fg)}.at-md a{color:var(--at-accent-text);text-decoration:none;border-bottom:1px solid rgba(148,155,255,.35)}.at-md a:hover{color:#c3c7ff;border-bottom-color:currentColor}.at-md code{font-family:var(--at-mono);font-size:.86em;padding:1px 5px;border-radius:4px;background:#a0aaff1a;color:#d6d9ff}.at-md pre{margin:0 0 10px;padding:12px 14px;border-radius:8px;background:var(--at-canvas-deep);border:1px solid var(--at-line-soft);overflow-x:auto}.at-md pre code{padding:0;background:none}.at-md blockquote{margin:0 0 9px;padding-left:12px;border-left:2px solid var(--at-accent-hi);color:var(--at-muted)}.at-md hr{border:0;border-top:1px solid var(--at-line-soft);margin:14px 0}.at-md-list{margin:0 0 9px;padding-left:1.3em}.at-md-list li{margin:3px 0}.at-md-list li::marker{color:var(--at-faint)}.at-md-check{list-style:none;margin-left:-1.3em!important}.at-md-check label{display:flex;align-items:flex-start;gap:10px;cursor:pointer;padding:3px 0}.at-md-check input{appearance:none;-webkit-appearance:none;flex:none;width:16px;height:16px;margin:3px 0 0;border-radius:4px;border:1.5px solid rgba(190,196,255,.38);cursor:pointer;display:grid;place-items:center;transition:background .15s,border-color .15s,box-shadow .15s}.at-md-check input:hover{border-color:var(--at-accent-text)}.at-md-check input:checked{background:var(--at-accent);border-color:var(--at-accent-hi);box-shadow:0 0 8px #3c46ff8c}.at-md-check input:checked:after{content:"";width:8px;height:4px;border:2px solid #fff;border-top:0;border-right:0;transform:translateY(-1px) rotate(-45deg)}.at-md-check.is-done span{color:var(--at-faint);text-decoration:line-through}.at-md-table{max-width:100%;overflow-x:auto;margin:0 0 10px}.at-md table{border-collapse:collapse;font-size:13px;min-width:100%}.at-md th,.at-md td{min-width:9rem;overflow-wrap:normal;word-break:normal;padding:7px 10px;border-bottom:1px solid var(--at-line-soft);text-align:left;vertical-align:top}.at-md .at-md-time{min-width:7rem;white-space:nowrap}.at-md th{white-space:nowrap;font-family:var(--at-mono);font-size:10.5px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--at-muted)}.at-md-wikilink{color:var(--at-accent-text)}.at-disco{flex:1;min-height:0}.at-disco-inner{max-width:820px;margin:0 auto;padding:20px 24px 96px}.at-disco-bar{display:flex;align-items:center;gap:12px;padding:0 0 22px}.at-disco-bar .at-period{margin-left:0}.at-sources{display:flex;flex-wrap:wrap;align-items:flex-end;gap:6px 12px;padding:8px 8px 8px 12px;margin:-10px 0 16px;border-radius:10px;background:var(--at-soft);border:1px solid var(--at-line-soft)}.at-sources-rows{flex:1 1 320px;display:flex;flex-direction:column;gap:5px;min-width:0}.at-sources-row{display:flex;align-items:baseline;gap:8px;min-width:0}.at-sources-label{flex:none;font-family:var(--at-mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--at-faint);white-space:nowrap}.at-sources-chips{display:flex;flex-wrap:wrap;gap:4px 5px;min-width:0}.at-source-chip{display:inline-flex;align-items:center;gap:5px;max-width:100%;padding:2px 8px 2px 6px;border-radius:999px;font-size:12px;line-height:1.4;color:var(--at-fg2, var(--at-fg));background:var(--at-accent-tint);border:1px solid rgba(130,140,255,.18);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.at-source-chip .at-icon{flex:none;color:var(--at-accent-text)}.at-sources-head{flex:none;display:flex;align-items:baseline;gap:8px}.at-sources-next{font-family:var(--at-mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--at-faint);white-space:nowrap}.at-btn.at-sources-run{flex:none;height:24px;padding:0 8px;font-size:12px;gap:4px;margin-left:auto;align-self:center}@media(max-width:560px){.at-btn.at-sources-run{margin-left:0;align-self:flex-start}}.at-btn.at-sources-run.is-running{opacity:1;color:var(--at-accent-text);border-color:currentColor;cursor:default;gap:6px}.at-btn.at-sources-add{flex:none;margin-left:auto;height:26px;padding:0 10px;font-size:12.5px;gap:5px}.at-root.is-narrow .at-btn.at-sources-add{height:30px}.at-copy-prompt{flex:1 1 100%;display:flex;flex-direction:column;gap:8px;padding:14px 16px;border-radius:12px;background:linear-gradient(180deg,#4a52ff2e,#2f37ff14);border:1.5px solid rgba(140,148,255,.6);box-shadow:0 0 26px #3c46ff4d}.at-copy-prompt .at-setup-prompt-label{font-size:15px}.at-copy-prompt-row{display:flex;align-items:center;gap:12px}.at-copy-prompt-text{flex:1;min-width:0;font-family:var(--at-display);font-size:22px;font-weight:600;line-height:1.15;color:#fff}@media(max-width:560px){.at-btn.at-sources-add{margin-left:0}.at-sources-row{flex-direction:column;gap:4px}.at-copy-prompt-row{flex-direction:column;align-items:stretch}.at-copy-prompt-text{font-size:20px}}.at-caughtup{display:flex;align-items:center;gap:14px;padding:18px 20px;border-radius:var(--at-r-lg);margin-bottom:24px;background:linear-gradient(135deg,#5be3a614,#3c46ff0f);border:1px solid var(--at-line)}.at-caughtup>.at-icon{color:var(--at-ok);filter:drop-shadow(0 0 6px rgba(91,227,166,.6))}.at-caughtup-title{font-family:var(--at-display);font-size:19px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}.at-caughtup .at-muted{font-size:13px}.at-run{margin-bottom:36px}.at-run-head{display:flex;align-items:flex-end;gap:10px;padding:0 2px 12px;margin-bottom:4px;border-bottom:1px solid var(--at-line-soft)}.at-run-title{font-family:var(--at-display);font-size:24px;font-weight:500;line-height:1.05}.at-run-sub{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:5px;font-family:var(--at-mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--at-muted)}.at-run-sub .is-late{color:var(--at-late)}.at-run-none{padding:12px 16px;border-radius:8px;background:var(--at-soft);color:var(--at-muted);font-size:13px}.at-runbar-wrap{padding:14px 2px 0}.at-runbar{position:relative;height:6px;border-radius:999px;background:var(--at-soft);overflow:hidden}.at-runbar-fill{position:absolute;inset:0 auto 0 0;width:0;border-radius:inherit;background:linear-gradient(90deg,var(--at-accent),var(--at-accent-hi));transition:width .6s ease}.at-runbar.is-indeterminate .at-runbar-fill{width:35%;animation:at-runbar 1.6s ease-in-out infinite}@keyframes at-runbar{0%{transform:translate(-100%)}to{transform:translate(290%)}}.at-runbar-label{margin-top:8px;font-size:13px;color:var(--at-muted)}@media(prefers-reduced-motion:reduce){.at-runbar.is-indeterminate .at-runbar-fill{width:100%;opacity:.35;animation:none;transform:none}}.at-proposals{display:flex;flex-direction:column;gap:12px;padding-top:10px}.at-run-fold{margin-top:8px}.at-run-fold.is-quiet>.at-disc-head{color:var(--at-muted)}.at-run-fold.at-tone-late>.at-disc-head{color:var(--at-late)}.at-prop{position:relative;padding:18px 18px 16px;border-radius:var(--at-r-lg);border:1px solid var(--at-line);background:linear-gradient(180deg,#121550bf,#0b0d38bf);box-shadow:0 1px #ffffff0a inset,0 14px 40px #00000a59;animation:at-fade .2s var(--at-ease);transition:border-color .2s}.at-prop:hover{border-color:var(--at-line-strong)}.at-prop.is-expired{opacity:.7}.at-prop-head{display:flex;align-items:flex-start;gap:12px}.at-prop-ref{flex:none;margin-top:3px;min-width:28px;height:20px;padding:0 6px;border-radius:3px;display:grid;place-items:center;font-family:var(--at-mono);font-size:10.5px;font-weight:700;letter-spacing:.04em;background:#eef0ff;color:var(--at-ink);font-variant-numeric:tabular-nums}.at-prop-title{flex:1;margin:0;font-family:var(--at-display);font-size:21px;font-weight:500;line-height:1.15;letter-spacing:.005em}.at-prop-dismiss{margin:-4px -6px 0 0;color:var(--at-faint)}.at-prop-text{margin:8px 0 0 40px;color:var(--at-fg2);font-size:13.5px;line-height:1.6}.at-prop-next{display:flex;gap:12px;margin:10px 0 0 40px;font-size:13.5px;line-height:1.55;color:var(--at-fg)}.at-prop-label{flex:none;padding-top:3px}.at-prop-uncertain{display:flex;gap:9px;margin:12px 0 0 40px;padding:9px 11px;border-radius:6px;font-size:13px;background:#ffb35c14;color:var(--at-late);box-shadow:inset 0 0 0 1px #ffb35c33}.at-prop-uncertain .at-icon{margin-top:2px}.at-prop-links{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0 40px}.at-srclink{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 9px;border-radius:3px;background:var(--at-soft);border:1px solid var(--at-line-soft);color:var(--at-fg2);font-family:var(--at-mono);font-size:10.5px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;text-decoration:none}.at-srclink:hover{background:var(--at-press);border-color:var(--at-line);color:var(--at-fg)}.at-prop-targets{margin:14px 0 0 40px;padding:10px;border-radius:8px;background:var(--at-inset);border:1px solid var(--at-line-soft);transition:opacity .15s}.at-prop-targets.is-muted{opacity:.5}.at-prop-targets>.at-prop-label{display:block;padding:2px 4px 8px}.at-target{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:6px;cursor:pointer;margin-top:4px;background:#a0aaff0a;border:1px solid var(--at-line-soft);transition:border-color .15s,box-shadow .15s,background .15s}.at-target:hover{border-color:var(--at-line)}.at-target.is-on{border-color:#6e78ffbf;background:var(--at-accent-tint);box-shadow:0 0 18px #3c46ff38}.at-target input{accent-color:var(--at-accent-hi);margin:0}.at-target>.at-icon{color:var(--at-accent-text)}.at-target-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.at-target-title{font-weight:600;font-size:13.5px}.at-target-meta{display:flex;align-items:center;gap:6px 12px;flex-wrap:wrap;font-family:var(--at-mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--at-muted)}.at-target-meta .at-areadot{margin-right:-6px}.at-prop-addition{display:flex;gap:12px;padding:12px 4px 2px;font-size:13px}.at-prop-addition ul,.at-prop-list{margin:0;padding-left:1.1em;color:var(--at-fg2)}.at-prop-addition li::marker,.at-prop-list li::marker{color:var(--at-accent-text)}.at-prop-list{margin:10px 0 0 40px;font-size:13.5px}.at-prop-addition p{margin:0;color:var(--at-fg2);line-height:1.55}.at-prop-full{margin:8px 0 0 32px}.at-prop-full .at-disc-head{font-size:12.5px;color:var(--at-muted)}.at-prop-full-sec{padding:6px 8px 0 30px;font-size:13px;line-height:1.6;color:var(--at-fg2)}.at-prop-full-sec p,.at-prop-full-sec ul{margin:2px 0 0}.at-prop-full-sec ul{padding-left:1.1em}.at-prop-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:16px 0 0 40px;padding-top:14px;border-top:1px solid var(--at-line-soft)}.at-prop-foot{margin:10px 0 0 40px;font-family:var(--at-mono);font-size:10.5px;letter-spacing:.04em}.at-prop.is-resolved{display:flex;align-items:center;gap:12px;padding:12px 16px;box-shadow:none;background:#a0aaff06;border-color:var(--at-line-soft)}.at-prop.is-resolved:hover{border-color:var(--at-line)}.at-prop.is-resolved .at-muted{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}.at-prop.is-dismissed .at-prop-resolved{color:var(--at-faint);text-decoration:line-through}.at-prop-resolved{font-size:13.5px;color:var(--at-fg2)}.at-outcome{display:flex;align-items:center;gap:10px;padding:9px 12px;font-size:13.5px;border-radius:6px}.at-outcome:hover{background:var(--at-hover)}.at-outcome .at-muted{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}.at-outcome-title{border:0;background:none;padding:0;cursor:pointer;text-align:left;font-weight:550}.at-outcome-title:hover{text-decoration:underline;text-underline-offset:3px}.at-attn{display:flex;gap:10px;padding:9px 12px;font-size:13.5px}.at-attn>.at-icon{color:var(--at-late);margin-top:3px}.at-attn-title{font-weight:600}.at-details{padding:4px 12px 8px;display:flex;flex-direction:column;gap:9px;font-size:13px}.at-detail-row{display:flex;align-items:center;gap:10px}.at-detail-row>.at-muted{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}.at-emptystate{max-width:460px;margin:0 auto;padding:80px 24px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:12px}.at-emptystate.is-full{flex:1;justify-content:center}.at-emptystate-icon{width:56px;height:56px;border-radius:14px;display:grid;place-items:center;margin-bottom:6px;background:radial-gradient(circle at 50% 30%,#505aff59,#3c46ff14);color:#c9ccff;border:1px solid rgba(130,140,255,.35);box-shadow:0 0 30px #3c46ff4d}.at-emptystate h2{font-family:var(--at-display);font-size:28px;font-weight:500;line-height:1.05}.at-emptystate p{color:var(--at-muted);font-size:14px;line-height:1.6}.at-root q{color:var(--at-fg);font-style:normal}.at-setup-prompt{position:relative;display:flex;flex-direction:column;align-items:center;gap:10px;width:100%;margin-top:10px;padding:22px 28px 18px;border-radius:14px;cursor:pointer;text-align:center;font:inherit;color:var(--at-fg);background:linear-gradient(180deg,#4a52ff38,#2f37ff1a);border:1.5px solid rgba(140,148,255,.75);box-shadow:0 0 0 4px #3c46ff24,0 0 42px #3c46ff73,inset 0 1px #ffffff14;transition:transform .12s ease,box-shadow .15s ease,border-color .15s ease}.at-setup-prompt:hover{border-color:#b9beff;transform:translateY(-1px);box-shadow:0 0 0 4px #3c46ff38,0 0 56px #4a52ff99,inset 0 1px #ffffff1a}.at-setup-prompt:focus-visible{outline:2px solid var(--at-accent-text);outline-offset:4px}.at-setup-prompt-label{display:inline-flex;align-items:center;gap:8px;font-size:18px;font-weight:700;font-variant:small-caps;text-transform:lowercase;letter-spacing:.06em;color:#c9ccff}.at-setup-prompt-label .at-icon{color:var(--at-accent-text)}.at-setup-prompt-text{font-family:var(--at-display);font-size:34px;font-weight:600;line-height:1.05;letter-spacing:.01em;color:#fff;text-shadow:0 0 22px rgba(120,130,255,.55)}.at-setup-prompt-text:before{content:"\\201c";color:var(--at-accent-text)}.at-setup-prompt-text:after{content:"\\201d";color:var(--at-accent-text)}.at-setup-prompt-copy{display:inline-flex;align-items:center;gap:6px;font-family:var(--at-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--at-accent-text)}.at-setup-prompt:hover .at-setup-prompt-copy{color:#c9ccff}@media(max-width:520px){.at-setup-prompt-text{font-size:28px}.at-setup-prompt{padding:18px 18px 14px}}.at-explainer{max-width:920px;margin:0 auto;padding:0 24px 72px;display:flex;flex-direction:column;gap:22px}.at-explainer-head{text-align:center;max-width:640px;margin:0 auto;display:flex;flex-direction:column;gap:10px}.at-explainer-kicker,.at-explainer-sub{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--at-accent-text)}.at-explainer-head h3{font-family:var(--at-display);font-size:30px;font-weight:500;line-height:1.08;color:var(--at-fg);text-wrap:balance}.at-explainer-head p{color:var(--at-muted);font-size:14.5px;line-height:1.65;text-wrap:pretty}.at-explainer-steps{list-style:none;margin:4px 0 0;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.at-explainer-step{position:relative;display:flex;flex-direction:column;gap:8px;padding:18px 18px 16px;border-radius:12px;background:var(--at-soft);border:1px solid var(--at-line-soft)}.at-explainer-num{position:absolute;top:14px;right:16px;font-family:var(--at-display);font-size:28px;font-weight:600;line-height:1;color:#949bff38}.at-explainer-step-icon{width:30px;height:30px;border-radius:8px;display:grid;place-items:center;color:#c9ccff;background:var(--at-accent-tint);border:1px solid rgba(130,140,255,.3)}.at-explainer-step strong{font-size:14.5px;font-weight:600;color:var(--at-fg)}.at-explainer-step-text{font-size:13.5px;line-height:1.55;color:var(--at-muted)}.at-explainer-sub{text-align:center;margin-top:6px}.at-explainer-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.at-catch{display:flex;flex-direction:column;gap:9px;padding:16px 18px;border-radius:12px;background:linear-gradient(180deg,#a0aaff12,#a0aaff08);border:1px solid var(--at-line-soft)}.at-catch-source{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;padding:3px 9px 3px 7px;border-radius:999px;font-family:var(--at-mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--at-accent-text);background:var(--at-accent-tint)}.at-explainer h3,.at-explainer h4,.at-explainer p,.at-explainer blockquote,.at-explainer ol{margin:0}.at-catch h4{font-family:var(--at-display);font-size:20px;font-weight:500;line-height:1.1;color:var(--at-fg)}.at-catch blockquote{margin:0;padding:2px 0 2px 12px;border-left:2px solid rgba(148,155,255,.45);font-size:13.5px;line-height:1.5;color:var(--at-fg);font-style:italic;display:flex;flex-direction:column;gap:2px}.at-catch-where{font-size:12px;color:var(--at-faint)}.at-catch-task{display:flex;align-items:center;gap:9px;margin-top:auto;padding:9px 11px;border-radius:9px;background:#0a0c2859;border:1px solid rgba(130,140,255,.28)}.at-catch-check{flex:none;width:14px;height:14px;border-radius:4px;border:1.5px solid var(--at-accent-text)}.at-catch-task-text{flex:1;min-width:0;font-size:13px;line-height:1.35;color:var(--at-fg)}.at-catch-due{flex:none;font-family:var(--at-mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--at-faint)}.at-explainer-foot{display:flex;align-items:flex-start;justify-content:center;gap:8px;max-width:620px;margin:0 auto;text-align:left;font-size:13px;line-height:1.55;color:var(--at-muted)}.at-explainer-foot .at-icon{flex:none;margin-top:3px;color:var(--at-accent-text)}@media(max-width:760px){.at-explainer-steps,.at-explainer-grid{grid-template-columns:1fr}}@media(max-width:520px){.at-explainer{padding:0 16px 56px;gap:18px}.at-explainer-head h3{font-size:25px}.at-emptystate{padding:48px 16px 28px}}.at-root q:before{content:"\\201c"}.at-root q:after{content:"\\201d"}.at-settings-body{display:flex;flex-direction:column;gap:30px;padding-top:6px}.at-set-sec h3{margin-bottom:6px}.at-set-sec>p{font-size:13px;margin-bottom:14px}.at-set-hint{margin-top:14px;line-height:1.55}.at-set-empty{padding:14px;border-radius:8px;background:var(--at-soft);font-size:13px;color:var(--at-muted)}.at-stream{padding:16px;border-radius:var(--at-r-lg);border:1px solid var(--at-line);margin-bottom:12px;display:flex;flex-direction:column;gap:14px;background:linear-gradient(180deg,#12155099,#0b0d3899)}.at-stream-head{display:flex;align-items:flex-start;gap:10px}.at-stream-name{font-family:var(--at-display);font-weight:500;font-size:21px;line-height:1.1}.at-stream-head .at-muted{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;margin-top:4px}.at-inline-area{display:inline-flex;align-items:center;gap:6px}.at-stream-sched{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.at-tz{font-family:var(--at-mono);font-size:10.5px;letter-spacing:.06em}.at-stream-sources{display:flex;flex-wrap:wrap;gap:6px}.at-stream-sources .at-chip{cursor:default;height:22px}.at-settings-inline{padding:8px 4px}.at-root.is-narrow{font-size:15px}.at-root.is-narrow .at-appbar{height:52px;padding:0 8px;gap:6px}.at-root.is-narrow .at-tab{padding:0 10px;font-size:16px}.at-root.is-narrow .at-tab.is-on:after{left:10px;right:10px}.at-root.is-narrow .at-toolbar{padding:16px 16px 12px;gap:12px}.at-root.is-narrow .at-toolbar-nav{width:100%}.at-root.is-narrow .at-toolbar-nav .at-btn{order:3;margin:0 0 0 4px}.at-root.is-narrow .at-toolbar-nav .at-period{order:-1;margin-left:0;margin-right:auto;font-size:34px}.at-root.is-narrow .at-toolbar-right{width:100%;margin-left:0;gap:8px}.at-root.is-narrow .at-toolbar-right .at-seg{flex:1}.at-root.is-narrow .at-toolbar-right .at-seg-item{flex:1;padding:0 8px}.at-root.is-narrow .at-row{padding:12px 8px 12px 10px;gap:13px}.at-root.is-narrow .at-row-title{font-size:15.5px;line-height:1.4}.at-root.is-narrow .at-row-meta{font-size:11px;margin-top:5px}.at-root.is-narrow .at-check{width:23px;height:23px}.at-root.is-narrow .at-check svg{width:13px;height:13px}.at-root.is-narrow .at-check-lg{width:28px;height:28px}.at-root.is-narrow .at-daylist>.at-row+.at-row:before{content:"";position:absolute;top:-1px;left:46px;right:8px;height:1px;background:var(--at-line-soft)}.at-root.is-narrow .at-panel-body{padding:0 20px 64px}.at-root.is-narrow .at-title-input{font-size:30px}.at-root.is-narrow .at-disco-inner{padding:16px 14px 96px}.at-root.is-narrow .at-prop{padding:16px 16px 14px}.at-root.is-narrow .at-prop-title{font-size:20px}.at-root.is-narrow .at-prop-text,.at-root.is-narrow .at-prop-next,.at-root.is-narrow .at-prop-links,.at-root.is-narrow .at-prop-targets,.at-root.is-narrow .at-prop-actions,.at-root.is-narrow .at-prop-uncertain,.at-root.is-narrow .at-prop-list,.at-root.is-narrow .at-prop-foot,.at-root.is-narrow .at-prop-full{margin-left:0}.at-root.is-narrow .at-prop-full-sec{padding-left:8px}.at-root.is-narrow .at-prop-next{flex-direction:column;gap:3px}.at-root.is-narrow .at-disco-bar{flex-wrap:wrap}.at-root.is-narrow .at-disco-bar .at-period{font-size:34px}.at-root.is-narrow .at-disco-bar .at-seg{order:3;width:100%}.at-root.is-narrow .at-disco-bar .at-seg-item{flex:1}.at-root.is-narrow .at-fields{padding-left:0}.at-root.is-narrow .at-summary-input{margin-left:-10px!important;width:calc(100% + 20px)}.at-root.is-narrow .at-prop-addition{flex-direction:column;gap:4px}.at-root.is-narrow .at-menu-item{height:42px;font-size:15px}.at-root.is-narrow .at-btn-sm,.at-root.is-narrow .at-field{height:34px}@media(prefers-reduced-motion:reduce){.at-root *,.at-pop,.at-panel,.at-toast{animation:none!important;transition:none!important}}.at-row.is-selected,.at-overdue,.at-overdue>.at-disc-head,.at-state{border-top-left-radius:0;border-bottom-left-radius:0}.at-panel.is-sheet{will-change:transform}.at-panel.is-sheet .at-panel-bar{height:60px;padding:8px 10px 0 20px;touch-action:none}.at-panel.is-sheet .at-grabber{top:8px;width:44px;height:5px;margin-left:-22px}.at-panel.is-sheet .at-panel-bar .at-iconbtn{width:44px;height:44px;border-radius:10px;color:var(--at-fg2)}.at-panel.is-sheet .at-panel-bar .at-iconbtn .at-icon{width:22px;height:22px}.at-panel.is-sheet .at-panel-bar .at-iconbtn[aria-label=Close]{background:#a0aaff14;border-color:var(--at-line-soft)}.at-panel.is-sheet .at-panel-body{overscroll-behavior-y:none}.at-panel-bar{z-index:3}.at-panel-bar:after{content:"";position:absolute;left:0;right:0;top:100%;height:36px;pointer-events:none;background:linear-gradient(180deg,#0d0f42,#0d0f42d9 25%,#0d0f4266 62%,#0d0f4200);opacity:0;transition:opacity .2s}.at-panel.is-scrolled .at-panel-bar:after{opacity:1}.at-panel.is-sheet .at-panel-bar{border-radius:18px 18px 0 0;background:#0d0f42}.at-fab{transition:transform .15s var(--at-ease),box-shadow .2s,opacity .15s}.at-fab.is-hidden{opacity:0;transform:scale(.85);pointer-events:none}.at-composer-scrim{position:absolute;inset:0;z-index:30;background:#0203148c;backdrop-filter:blur(2px);-webkit-backdrop-filter:blur(2px);animation:at-fade .18s var(--at-ease)}.at-composer{position:fixed;left:0;right:0;bottom:0;z-index:35;display:flex;flex-direction:column;gap:10px;padding:14px 14px calc(12px + env(safe-area-inset-bottom,0px));background:linear-gradient(180deg,#14175a,#0d0f42);border-top:1px solid var(--at-line-strong);border-radius:18px 18px 0 0;box-shadow:0 -18px 50px #00000a8c;opacity:0;transform:translateY(16px);pointer-events:none;transition:opacity .18s var(--at-ease),transform .22s var(--at-ease)}.at-composer.is-open{opacity:1;transform:none;pointer-events:auto}.at-composer-row{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;background:var(--at-inset);box-shadow:inset 0 0 0 1px #6e78ff80,0 0 20px #3c46ff26}.at-composer-row .at-check{width:22px;height:22px}.at-composer-input{flex:1;min-width:0;border:0;background:transparent;outline:none;padding:2px 0;font-size:16px;color:var(--at-fg)}.at-composer-input::placeholder{color:var(--at-faint)}.at-composer-bar{display:flex;align-items:center;gap:8px}.at-composer-send{flex:none;width:40px;height:40px;border-radius:12px;border:1px solid rgba(160,170,255,.5);cursor:pointer;display:grid;place-items:center;background:linear-gradient(160deg,#4a52ff,#2a30f0);color:#fff;box-shadow:0 6px 20px #2832ff73;transition:opacity .15s,transform .1s}.at-composer-send:disabled{opacity:.35;box-shadow:none;cursor:default}.at-composer-send:active:not(:disabled){transform:scale(.94)}.at-root:has(.at-composer.is-open) .at-toasts{top:64px;bottom:auto}.at-title-input.is-idle{cursor:text;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent}.at-title-input{transition:background .2s,box-shadow .2s,transform .2s var(--at-ease)}.at-title-input.is-armed{background:var(--at-accent-tint);box-shadow:0 0 0 6px var(--at-accent-tint),0 0 24px #3c46ff59;transform:scale(.985)}.at-title-wrap{position:relative;flex:1;min-width:0;display:flex}.at-copied{position:absolute;left:0;top:calc(100% + 10px);z-index:5;display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 11px;border-radius:6px;background:#eef0ff;color:var(--at-ink);box-shadow:0 8px 24px #00000a80,0 0 18px #96a0ff59;font-family:var(--at-display);font-size:14px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;pointer-events:none;animation:at-copied .2s var(--at-ease)}.at-copied:before{content:"";position:absolute;left:16px;top:-5px;width:10px;height:10px;background:#eef0ff;transform:rotate(45deg);border-radius:2px 0 0}.at-copied .at-icon{color:var(--at-accent)}@keyframes at-copied{0%{opacity:0;transform:translateY(-4px)}}.at-toast span{white-space:normal;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;line-height:1.4}.at-iconbtn.is-busy{color:var(--at-accent-text);animation:at-pulse 1s ease-in-out infinite}@keyframes at-pulse{50%{opacity:.45}}.at-panel-foot{position:absolute;left:0;right:0;bottom:0;z-index:3;pointer-events:none;padding:28px 20px calc(16px + env(safe-area-inset-bottom,0px));background:linear-gradient(180deg,#090b3400,#090b34eb 42%,#090b34)}.at-panel-body.has-foot{padding-bottom:116px}.at-cta{pointer-events:auto;display:flex;align-items:center;justify-content:center;gap:10px;width:100%;height:54px;border-radius:16px;border:1px solid rgba(160,170,255,.5);cursor:pointer;background:linear-gradient(160deg,#4a52ff,#2a30f0);color:#fff;box-shadow:0 10px 30px #2832ff80,0 0 0 5px #2f37ff1f;font-family:var(--at-display);font-size:18px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;transition:transform .15s var(--at-ease),box-shadow .2s,filter .2s}.at-cta:hover{filter:brightness(1.08);box-shadow:0 12px 36px #2832ff99,0 0 0 6px #2f37ff29}.at-cta:active{transform:scale(.98)}.at-cta:disabled{cursor:default}.at-cta.is-busy{animation:at-pulse 1.1s ease-in-out infinite}.at-panel.is-side .at-panel-foot{padding:28px 24px 20px}.at-root:has(.at-panel-foot) .at-toasts{bottom:calc(104px + env(safe-area-inset-bottom,0px))}.at-status-dot{width:7px;height:7px;border-radius:50%;flex:none;background:var(--at-faint)}.at-status[data-s=in-progress]{color:var(--at-accent-text);border-color:#6e78ff73}.at-status[data-s=in-progress] .at-status-dot{background:var(--at-accent-text);box-shadow:0 0 8px #7882ffcc}.at-status[data-s=waiting] .at-status-dot{background:var(--at-late);box-shadow:0 0 8px #ffb35c99}.at-status[data-s=done] .at-status-dot{background:var(--at-ok);box-shadow:0 0 8px #5be3a699}.at-field.is-static{cursor:default}.at-field.is-static:hover{background:#a0aaff09;border-color:var(--at-line);color:var(--at-fg2)}.at-root .at-panel .at-panel-body.has-foot{padding-bottom:calc(132px + env(safe-area-inset-bottom,0px))}\n';

// ui/hosts/desktop.jsx
var STYLE_ID = "alchemy-task-ui-styles";
var desktop_default = {
  id: "alchemy-task",
  name: "Alchemy Task",
  register(ctx) {
    if (!document.getElementById(STYLE_ID)) {
      const style = document.createElement("style");
      style.id = STYLE_ID;
      style.textContent = styles_default;
      document.head.appendChild(style);
      ctx.onDispose(() => style.remove());
    }
    const transport = makeTransport((method, path, body) => ctx.rest(path, body === void 0 ? { method } : { method, body }));
    let pending = null;
    const openWith = (view) => {
      pending = view;
      host.navigate("/alchemy-task");
      window.dispatchEvent(new CustomEvent("alchemy-task:open", { detail: view }));
    };
    const chat = {
      async startChat(text) {
        if (typeof host.newChat !== "function" || !host.composer || typeof host.composer.submit !== "function") return false;
        host.newChat();
        for (let i = 0; i < 40; i++) {
          await new Promise((r) => setTimeout(r, 100));
          if (host.composer.submit("new", text)) return true;
        }
        return false;
      }
    };
    const Page = () => /* @__PURE__ */ React10.createElement(App, { transport, host: "desktop", initialView: pending, chat });
    ctx.registerMany([
      { id: "page", area: ROUTES_AREA, data: { path: "/alchemy-task" }, render: () => /* @__PURE__ */ React10.createElement(Page, null) },
      { id: "nav", area: SIDEBAR_NAV_AREA, data: { path: "/alchemy-task", label: "Tasks", codicon: "checklist" } },
      {
        id: "open-tasks",
        area: PALETTE_AREA,
        data: { id: "alchemy-task-open", label: "Open tasks", keywords: ["tasks", "today", "calendar", "alchemy"], run: () => openWith("tasks") }
      },
      {
        id: "open-discovery",
        area: PALETTE_AREA,
        data: { id: "alchemy-task-discovery", label: "Review discovery proposals", keywords: ["discovery", "digest", "proposals", "alchemy"], run: () => openWith("discovery") }
      }
    ]);
    if (typeof ctx.registerSettingsPage === "function") {
      ctx.registerSettingsPage({
        id: "settings",
        title: "Alchemy Task",
        icon: "checklist",
        render: () => /* @__PURE__ */ React10.createElement(App, { transport, host: "desktop", settingsOnly: true })
      });
    }
  }
};
export {
  desktop_default as default
};
