(() => {
  // ui/hosts/react-dashboard.js
  var React = window.__HERMES_PLUGIN_SDK__.React;
  var react_dashboard_default = React;

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
  var DragCtx = react_dashboard_default.createContext(null);
  var useDrag = () => react_dashboard_default.useContext(DragCtx);
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
    const [drag, setDrag] = react_dashboard_default.useState(null);
    const dragRef = react_dashboard_default.useRef(null);
    const suppressClick = react_dashboard_default.useRef(false);
    const raf = react_dashboard_default.useRef(0);
    const ghost = react_dashboard_default.useRef(null);
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
    const bind = react_dashboard_default.useCallback((task, from) => ({
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
    const value = react_dashboard_default.useMemo(() => ({ drag, bind }), [drag, bind]);
    react_dashboard_default.useEffect(() => () => {
      if (ghost.current) ghost.current.remove();
    }, []);
    return react_dashboard_default.createElement(DragCtx.Provider, { value }, children);
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
    const get = react_dashboard_default.useCallback(() => selector(store.getState()), [store, selector]);
    const [value, setValue] = react_dashboard_default.useState(get);
    react_dashboard_default.useEffect(() => {
      setValue(get());
      return store.subscribe(() => setValue(get()));
    }, [store, get]);
    return value;
  }
  var AppContext = react_dashboard_default.createContext(null);
  var useApp = () => react_dashboard_default.useContext(AppContext);
  function usePref(key, initial) {
    const full = `alchemy-task.${key}`;
    const [value, setValue] = react_dashboard_default.useState(() => {
      try {
        const raw = window.localStorage.getItem(full);
        return raw === null ? initial : JSON.parse(raw);
      } catch {
        return initial;
      }
    });
    const update = react_dashboard_default.useCallback((v) => {
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
    const [w, setW] = react_dashboard_default.useState(() => typeof window !== "undefined" ? window.innerWidth : 1200);
    react_dashboard_default.useLayoutEffect(() => {
      const el = ref.current;
      if (!el) return void 0;
      setW(el.getBoundingClientRect().width);
      const ro = new ResizeObserver((entries) => setW(entries[0].contentRect.width));
      ro.observe(el);
      return () => ro.disconnect();
    }, [ref]);
    return w;
  }

  // ui/src/lib/month.js
  function fittingRows(total, height, rowHeight, moreHeight, gap = 0) {
    if (total * (rowHeight + gap) - gap <= height) return total;
    return Math.min(total, Math.max(0, Math.floor((height - moreHeight) / (rowHeight + gap))));
  }

  // ui/src/ui.jsx
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
    const id = react_dashboard_default.useMemo(() => `at-mark-${++markSeq}`, []);
    return /* @__PURE__ */ react_dashboard_default.createElement(
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
      /* @__PURE__ */ react_dashboard_default.createElement("clipPath", { id }, /* @__PURE__ */ react_dashboard_default.createElement("polygon", { points: "0.59,85.70 48.00,3.60 95.41,85.70" })),
      /* @__PURE__ */ react_dashboard_default.createElement("polygon", { points: "7.00,82.00 48.00,11.00 89.00,82.00" }),
      /* @__PURE__ */ react_dashboard_default.createElement("polyline", { clipPath: `url(#${id})`, strokeLinecap: "butt", points: "14.87,48.48 39.80,66.38 72.84,34.60" })
    );
  }
  function Icon({ name, size = 16, className = "", strokeWidth = 1.8 }) {
    return /* @__PURE__ */ react_dashboard_default.createElement(
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
      /* @__PURE__ */ react_dashboard_default.createElement("path", { d: P[name] || P.dot })
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
    return /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-btn", `at-btn-${variant}`, size && `at-btn-${size}`, className), ...rest }, icon ? /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: icon, size: size === "sm" ? 14 : 16 }) : null, children ? /* @__PURE__ */ react_dashboard_default.createElement("span", null, children) : null);
  }
  function IconButton({ icon, label, className, size = 16, ...rest }) {
    return /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-iconbtn", className), "aria-label": label, title: label, ...rest }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: icon, size }));
  }
  function Check({ checked, onChange, label, size = "md", tone }) {
    return /* @__PURE__ */ react_dashboard_default.createElement(
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
      /* @__PURE__ */ react_dashboard_default.createElement("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, /* @__PURE__ */ react_dashboard_default.createElement("path", { d: P.check }))
    );
  }
  function Segmented({ value, options, onChange, label }) {
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-seg", role: "tablist", "aria-label": label }, options.map((o) => /* @__PURE__ */ react_dashboard_default.createElement(
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
    return /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-spinner", style: { width: size, height: size }, "aria-label": "Loading" });
  }
  function Disclosure({ title, count, defaultOpen = false, tone, children, right, className }) {
    const [open, setOpen] = react_dashboard_default.useState(defaultOpen);
    return /* @__PURE__ */ react_dashboard_default.createElement("section", { className: cx("at-disc", open && "is-open", tone && `at-tone-${tone}`, className) }, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-disc-head", "aria-expanded": open, onClick: () => setOpen(!open) }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "chevR", size: 14, className: "at-disc-chev" }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-disc-title" }, title), count !== void 0 ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-count" }, count) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), right), open ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-disc-body" }, children) : null);
  }
  function AreaDot({ area }) {
    return /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-areadot", style: { "--at-area": areaColor(area) }, title: area });
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
    const closeRef = react_dashboard_default.useRef(onClose);
    closeRef.current = onClose;
    react_dashboard_default.useEffect(() => {
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
  var OverlayCtx = react_dashboard_default.createContext(null);
  var useOverlay = () => react_dashboard_default.useContext(OverlayCtx);
  function OverlayHost({ rootRef, children }) {
    const [ov, setOv] = react_dashboard_default.useState(null);
    const close = react_dashboard_default.useCallback(() => setOv((cur) => {
      if (cur && cur.onClose) cur.onClose();
      return null;
    }), []);
    const open = react_dashboard_default.useCallback((anchor, render, opts = {}) => setOv({ anchor, render, ...opts }), []);
    const api = react_dashboard_default.useMemo(() => ({ open, close }), [open, close]);
    return /* @__PURE__ */ react_dashboard_default.createElement(OverlayCtx.Provider, { value: api }, children, ov ? /* @__PURE__ */ react_dashboard_default.createElement(Popover, { rootRef, ...ov, close }) : null);
  }
  function Popover({ rootRef, anchor, render, close, align = "start", width }) {
    const ref = react_dashboard_default.useRef(null);
    const [pos, setPos] = react_dashboard_default.useState(null);
    react_dashboard_default.useLayoutEffect(() => {
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
    react_dashboard_default.useEffect(() => {
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { ref, className: "at-pop", role: "dialog", style: { left: pos ? pos.left : -9999, top: pos ? pos.top : -9999, width } }, render(close));
  }
  function Menu({ items, close }) {
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-menu", role: "menu" }, items.filter(Boolean).map((it, i) => it === "-" ? /* @__PURE__ */ react_dashboard_default.createElement("div", { key: i, className: "at-menu-sep" }) : /* @__PURE__ */ react_dashboard_default.createElement(
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
      it.icon ? /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: it.icon, size: 15 }) : /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-menu-pad" }),
      /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }, it.label),
      it.hint ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-menu-hint" }, it.hint) : null
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
    const [month, setMonth] = react_dashboard_default.useState(startOfMonth(value || today));
    const weeks = monthGrid(month);
    const pick = (d) => {
      onPick(d);
      close && close();
    };
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-dp" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-dp-quick" }, quickDates(today).map((q) => /* @__PURE__ */ react_dashboard_default.createElement("button", { key: q.label, type: "button", className: cx("at-dp-q", value === q.date && "is-on"), onClick: () => pick(q.date) }, /* @__PURE__ */ react_dashboard_default.createElement("span", null, q.label), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, q.hint)))), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-dp-head" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-dp-title" }, monthName(month), " ", month.slice(0, 4) !== today.slice(0, 4) ? month.slice(0, 4) : ""), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "chevL", label: "Previous month", onClick: () => setMonth(addMonths(month, -1)) }), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "chevR", label: "Next month", onClick: () => setMonth(addMonths(month, 1)) })), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-dp-grid", role: "grid" }, ["M", "T", "W", "T", "F", "S", "S"].map((d, i) => /* @__PURE__ */ react_dashboard_default.createElement("span", { key: i, className: "at-dp-dow" }, d)), weeks.flat().map((d) => /* @__PURE__ */ react_dashboard_default.createElement(
      "button",
      {
        key: d,
        type: "button",
        onClick: () => pick(d),
        className: cx("at-dp-day", d.slice(0, 7) !== month.slice(0, 7) && "is-out", d === today && "is-today", d === value && "is-on")
      },
      dayNum(d)
    ))), onClear || extra ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-dp-foot" }, extra, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), onClear ? /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", variant: "ghost", onClick: () => {
      onClear();
      close && close();
    } }, "Clear") : null) : null);
  }
  var ToastCtx = react_dashboard_default.createContext(null);
  var ToastListCtx = react_dashboard_default.createContext(null);
  var useToast = () => react_dashboard_default.useContext(ToastCtx);
  function ToastHost({ children }) {
    const [toasts, setToasts] = react_dashboard_default.useState([]);
    const seq = react_dashboard_default.useRef(0);
    const dismiss = react_dashboard_default.useCallback((id) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
    const show = react_dashboard_default.useCallback((message, opts = {}) => {
      const id = ++seq.current;
      setToasts((ts) => [...ts.slice(-2), { id, message, ...opts }]);
      setTimeout(() => dismiss(id), opts.duration || (opts.undo ? 6500 : opts.tone === "error" ? 7e3 : 3500));
      return id;
    }, [dismiss]);
    const list = react_dashboard_default.useMemo(() => ({ toasts, dismiss }), [toasts, dismiss]);
    return /* @__PURE__ */ react_dashboard_default.createElement(ToastCtx.Provider, { value: show }, /* @__PURE__ */ react_dashboard_default.createElement(ToastListCtx.Provider, { value: list }, children));
  }
  function ToastOutlet() {
    const { toasts, dismiss } = react_dashboard_default.useContext(ToastListCtx);
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-toasts", "aria-live": "polite" }, toasts.map((t) => /* @__PURE__ */ react_dashboard_default.createElement("div", { key: t.id, className: cx("at-toast", t.tone && `at-tone-${t.tone}`) }, t.tone === "error" ? /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 15 }) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }, t.message), t.undo ? /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-toast-act", onClick: () => {
      dismiss(t.id);
      t.undo();
    } }, "Undo") : null, t.action ? /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-toast-act", onClick: () => {
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
    return react_dashboard_default.useMemo(() => {
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
      overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(RowMenu, { task, close }), { width: 236, align: "end" });
    };
    return /* @__PURE__ */ react_dashboard_default.createElement(
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
      /* @__PURE__ */ react_dashboard_default.createElement(
        Check,
        {
          checked: done,
          onChange: () => actions.toggle(task),
          label: done ? "Mark not done" : "Mark done",
          size: compact ? "sm" : "md",
          tone: overdue || task.priority === "urgent" || task.priority === "high" ? "high" : void 0
        }
      ),
      /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-row-main" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-row-title", title: compact ? task.title : void 0 }, task.title), compact ? null : /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-row-meta" }, task.area ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-meta-area" }, /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area: task.area }), task.area) : null, showDate ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: cx("at-meta-date", overdue && "is-late") }, relativeDay(taskDate(task), today)) : null, dueDiffers ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-meta-due" }, "due ", relativeDay(task.due, today)) : null, task.priority === "urgent" || task.priority === "high" ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-meta-prio" }, task.priority) : null, task.status === "waiting" ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-meta-status" }, "waiting") : null, task.status === "in-progress" ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-meta-status is-active" }, "in progress") : null, researching ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-meta-research" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "spark", size: 12 }), "researching") : null)),
      compact ? null : /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "more", label: "Task actions", className: "at-row-more", onClick: openMenu, "data-no-drag": "" })
    );
  }
  function RowMenu({ task, close }) {
    const { actions, today } = useApp();
    const [picking, setPicking] = react_dashboard_default.useState(false);
    if (picking) {
      return /* @__PURE__ */ react_dashboard_default.createElement(DatePicker, { value: taskDate(task), today, onPick: (d) => actions.move(task, d), close });
    }
    const items = quickDates(today).slice(0, 3).map((q) => ({
      label: q.label,
      hint: q.hint,
      icon: "cal",
      run: () => actions.move(task, q.date)
    })).filter((it, i) => quickDates(today)[i].date !== taskDate(task));
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-menu", role: "menu" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-menu-label" }, "Move to"), /* @__PURE__ */ react_dashboard_default.createElement(Menu, { items, close }), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-menu-item", onClick: () => setPicking(true) }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "cal", size: 15 }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }, "Pick a date\u2026")), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-menu-sep" }), /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: [
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-daylist", drag && drag.over === date && "is-over"), "data-at-drop": date }, isToday && overdue.length ? /* @__PURE__ */ react_dashboard_default.createElement(OverdueSection, { tasks: overdue }) : null, visible.map((t) => /* @__PURE__ */ react_dashboard_default.createElement(TaskRow, { key: t.task_id, task: t, from: date, compact, selected: selectedId === t.task_id })), !visible.length && !(isToday && overdue.length) ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-empty-day" }, doneHidden ? `${doneHidden} done` : empty) : null, showAdd ? /* @__PURE__ */ react_dashboard_default.createElement(QuickAdd, { date }) : null, drag && drag.over === date && drag.from !== date ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-drop-hint" }, "Move to ", relativeDay(date, today)) : null);
  }
  function OverdueSection({ tasks, defaultOpen = false }) {
    const { actions, today, selectedId } = useApp();
    return /* @__PURE__ */ react_dashboard_default.createElement(
      Disclosure,
      {
        className: "at-overdue",
        tone: "late",
        title: "Overdue",
        count: tasks.length,
        defaultOpen,
        right: /* @__PURE__ */ react_dashboard_default.createElement(
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
      tasks.map((t) => /* @__PURE__ */ react_dashboard_default.createElement(TaskRow, { key: t.task_id, task: t, from: taskDate(t), showDate: true, selected: selectedId === t.task_id }))
    );
  }
  function QuickAdd({ date, autoFocus, onDone }) {
    const { actions, meta, prefs } = useApp();
    const [title, setTitle] = react_dashboard_default.useState("");
    const [busy, setBusy] = react_dashboard_default.useState(false);
    const [open, setOpen] = react_dashboard_default.useState(!!autoFocus);
    const ref = react_dashboard_default.useRef(null);
    react_dashboard_default.useEffect(() => {
      if (open && ref.current) ref.current.focus();
    }, [open]);
    if (!open) {
      return /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-add", onClick: () => setOpen(true), "data-no-drag": "" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "plus", size: 14 }), " Add a task");
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
    return /* @__PURE__ */ react_dashboard_default.createElement("form", { className: "at-add-form", "data-no-drag": "", onSubmit: (e) => {
      e.preventDefault();
      submit();
    } }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-check at-check-md is-ghost", "aria-hidden": "true" }), /* @__PURE__ */ react_dashboard_default.createElement(
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
    ), busy ? /* @__PURE__ */ react_dashboard_default.createElement(Spinner, null) : null);
  }
  function MonthView({ anchor, narrow }) {
    const { today, selectedId } = useApp();
    const { days, overdue } = useTaskIndex();
    const overlay = useOverlay();
    const { drag } = useDrag();
    const weeks = monthGrid(anchor);
    const month = anchor.slice(0, 7);
    const [picked, setPicked] = react_dashboard_default.useState(null);
    if (narrow) {
      const sel = picked && picked.slice(0, 7) === month ? picked : today.slice(0, 7) === month ? today : startOfMonth(anchor);
      return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-scroll at-mmonth" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-mmonth-dows" }, ["M", "T", "W", "T", "F", "S", "S"].map((x, i) => /* @__PURE__ */ react_dashboard_default.createElement("span", { key: i }, x))), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-mmonth-grid" }, weeks.flat().map((d) => {
        const list = days[d] || [];
        const open = list.filter((t) => !isDone(t)).length;
        return /* @__PURE__ */ react_dashboard_default.createElement(
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
          /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mcell-num" }, dayNum(d)),
          /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mcell-dots" }, list.slice(0, 3).map((t) => /* @__PURE__ */ react_dashboard_default.createElement("i", { key: t.task_id, className: isDone(t) ? "is-done" : "" })), d === today && overdue.length ? /* @__PURE__ */ react_dashboard_default.createElement("i", { className: "is-late" }) : null),
          open > 3 ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mcell-more" }, "+", open - 3) : null
        );
      })), /* @__PURE__ */ react_dashboard_default.createElement(DaySection, { date: sel, tasks: days[sel] || [], overdue: sel === today ? overdue : [] }));
    }
    return /* @__PURE__ */ react_dashboard_default.createElement(DesktopMonth, { weeks, month, days, overdue, today, selectedId, drag, overlay });
  }
  function DesktopMonth({ weeks, month, days, overdue, today, selectedId, drag, overlay, picked, onPick }) {
    const expand = (date, el) => onPick ? onPick(date) : overlay.open(el, (close) => /* @__PURE__ */ react_dashboard_default.createElement(DayPopover, { date, close }), { width: 360 });
    const gridRef = react_dashboard_default.useRef(null);
    const [cellW, setCellW] = react_dashboard_default.useState(160);
    react_dashboard_default.useLayoutEffect(() => {
      const el = gridRef.current;
      if (!el) return void 0;
      const ro = new ResizeObserver(() => setCellW(el.clientWidth / 7));
      ro.observe(el);
      return () => ro.disconnect();
    }, [weeks.length]);
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-month", onPick && "at-week-strip") }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-month-dows" }, weeks[0].map((d) => /* @__PURE__ */ react_dashboard_default.createElement("div", { key: d }, dayName(d)))), /* @__PURE__ */ react_dashboard_default.createElement("div", { ref: gridRef, className: "at-month-grid" }, weeks.flat().map((d) => {
      const list = days[d] || [];
      const isToday = d === today;
      return /* @__PURE__ */ react_dashboard_default.createElement(
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
        /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-cell-head" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-cell-num" }, dayNum(d) === 1 ? `${monthName(d, "short")} 1` : dayNum(d)), isToday && overdue.length ? /* @__PURE__ */ react_dashboard_default.createElement(
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
        /* @__PURE__ */ react_dashboard_default.createElement(MonthTasks, { tasks: list, date: d, selectedId, expand }),
        /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-cell-footer" }, /* @__PURE__ */ react_dashboard_default.createElement(
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
          /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "arrowR", size: 12 }),
          /* @__PURE__ */ react_dashboard_default.createElement("span", null, "View day")
        ))
      );
    })));
  }
  function MonthTasks({ tasks, date, selectedId, expand }) {
    const ref = react_dashboard_default.useRef(null);
    const [fit, setFit] = react_dashboard_default.useState(1);
    react_dashboard_default.useLayoutEffect(() => {
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { ref, className: "at-cell-list is-tight" }, tasks.slice(0, fit).map((t) => /* @__PURE__ */ react_dashboard_default.createElement(TaskRow, { key: t.task_id, task: t, from: date, compact: true, selected: selectedId === t.task_id })), /* @__PURE__ */ react_dashboard_default.createElement(
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-daypop" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-daypop-head" }, /* @__PURE__ */ react_dashboard_default.createElement("div", null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-daypop-title" }, relativeDay(date, today) === "Today" ? "Today" : dayName(date, "long")), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-muted" }, longDate(date))), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "x", label: "Close", onClick: close })), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-daypop-body" }, /* @__PURE__ */ react_dashboard_default.createElement(DayList, { date, tasks: days[date] || [], overdue: date === today ? overdue : [], showAdd: true })));
  }
  function WeekView({ anchor, narrow, onStep }) {
    const { today } = useApp();
    const { days, overdue } = useTaskIndex();
    const start = startOfWeek(anchor);
    const dates = range(start, addDays(start, 6));
    if (narrow) {
      return /* @__PURE__ */ react_dashboard_default.createElement(PhoneWeek, { dates, days, overdue, today, onStep });
    }
    return /* @__PURE__ */ react_dashboard_default.createElement(DesktopWeek, { dates, days, overdue, today });
  }
  function DesktopWeek({ dates, days, overdue, today }) {
    const { selectedId } = useApp();
    const { drag } = useDrag();
    const overlay = useOverlay();
    const [picked, setPicked] = react_dashboard_default.useState(null);
    const sel = picked && dates.includes(picked) ? picked : dates.includes(today) ? today : dates[0];
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-desktop-week at-scroll" }, /* @__PURE__ */ react_dashboard_default.createElement(
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
    ), /* @__PURE__ */ react_dashboard_default.createElement(DayView, { anchor: sel }));
  }
  function PhoneWeek({ dates, days, overdue, today, onStep }) {
    const { drag } = useDrag();
    const [picked, setPicked] = react_dashboard_default.useState(null);
    const sel = picked && dates.includes(picked) ? picked : dates.includes(today) ? today : dates[0];
    const swipe = react_dashboard_default.useRef(null);
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-scroll at-mmonth at-mweek" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-mmonth-dows" }, dates.map((d) => /* @__PURE__ */ react_dashboard_default.createElement("span", { key: d }, dayName(d).slice(0, 1)))), /* @__PURE__ */ react_dashboard_default.createElement(
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
        return /* @__PURE__ */ react_dashboard_default.createElement(
          "button",
          {
            key: d,
            type: "button",
            "data-at-drop": d,
            onClick: () => setPicked(d),
            className: cx("at-mcell", d === today && "is-today", d === sel && "is-on", drag && drag.over === d && "is-over")
          },
          /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mcell-num" }, dayNum(d)),
          /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mcell-dots" }, list.slice(0, 3).map((t) => /* @__PURE__ */ react_dashboard_default.createElement("i", { key: t.task_id, className: isDone(t) ? "is-done" : "" })), d === today && overdue.length ? /* @__PURE__ */ react_dashboard_default.createElement("i", { className: "is-late" }) : null),
          open > 3 ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mcell-more" }, "+", open - 3) : null
        );
      })
    ), /* @__PURE__ */ react_dashboard_default.createElement(DaySection, { date: sel, tasks: days[sel] || [], overdue: sel === today ? overdue : [] }));
  }
  function DayView({ anchor }) {
    const { today } = useApp();
    const { days, overdue } = useTaskIndex();
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-scroll at-dayview" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-dayview-inner" }, /* @__PURE__ */ react_dashboard_default.createElement("header", { className: "at-dayview-head" }, /* @__PURE__ */ react_dashboard_default.createElement("h2", null, relativeDay(anchor, today) === "Today" ? "Today" : dayName(anchor, "long")), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-muted" }, longDate(anchor))), /* @__PURE__ */ react_dashboard_default.createElement(DayList, { date: anchor, tasks: days[anchor] || [], overdue: anchor === today ? overdue : [], showAdd: true })));
  }
  function DaySection({ date, tasks, overdue }) {
    const { today } = useApp();
    const rel = relativeDay(date, today);
    const named = rel === "Today" || rel === "Tomorrow" || rel === "Yesterday";
    const empty = !tasks.length && !overdue.length;
    return /* @__PURE__ */ react_dashboard_default.createElement("section", { className: cx("at-daysec", date === today && "is-today", empty && "is-empty") }, /* @__PURE__ */ react_dashboard_default.createElement("header", { className: "at-daysec-head" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-daysec-title" }, named ? rel : dayName(date, "long")), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, shortDate(date, today).replace(/^\w+,\s*/, ""))), /* @__PURE__ */ react_dashboard_default.createElement(DayList, { date, tasks, overdue, showAdd: !empty || date === today }));
  }
  function DayScroll({ anchor, onReachEnd, length }) {
    const { today } = useApp();
    const { days, overdue } = useTaskIndex();
    const dates = range(anchor, addDays(anchor, length - 1));
    const sentinel = react_dashboard_default.useRef(null);
    react_dashboard_default.useEffect(() => {
      const el = sentinel.current;
      if (!el) return void 0;
      const io = new IntersectionObserver((es) => {
        if (es[0].isIntersecting) onReachEnd();
      }, { rootMargin: "400px" });
      io.observe(el);
      return () => io.disconnect();
    }, [onReachEnd]);
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-scroll at-days" }, dates.map((d) => /* @__PURE__ */ react_dashboard_default.createElement(DaySection, { key: d, date: d, tasks: days[d] || [], overdue: d === today ? overdue : [] })), /* @__PURE__ */ react_dashboard_default.createElement("div", { ref: sentinel, className: "at-sentinel" }));
  }
  function TasksView({ narrow }) {
    const { store, prefs, setPrefs, meta, today } = useApp();
    const overlay = useOverlay();
    const view = prefs.view || (narrow ? "day" : "week");
    const [anchor, setAnchor] = react_dashboard_default.useState(today);
    const [scrollLen, setScrollLen] = react_dashboard_default.useState(21);
    const growScroll = react_dashboard_default.useCallback(() => setScrollLen((n) => Math.min(n + 14, 120)), []);
    react_dashboard_default.useEffect(() => {
      if (!anchor && today) setAnchor(today);
    }, [today, anchor]);
    const a = anchor || today;
    const range2 = react_dashboard_default.useMemo(() => {
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
    react_dashboard_default.useEffect(() => {
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
    react_dashboard_default.useEffect(() => {
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
    if (!a) return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-loading" }, /* @__PURE__ */ react_dashboard_default.createElement(Spinner, { size: 18 }));
    const periodText = view === "day" ? periodLabel("month", a, today) : periodLabel(view, a, today);
    const areas = meta.areas || [];
    const areaMenu = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: [
      { label: "All areas", icon: prefs.area ? void 0 : "check", run: () => setPrefs({ area: "" }) },
      "-",
      ...areas.map((ar) => ({ label: ar, icon: prefs.area === ar ? "check" : void 0, run: () => setPrefs({ area: ar }) })),
      "-",
      { label: prefs.hideDone ? "Show completed" : "Hide completed", run: () => setPrefs({ hideDone: !prefs.hideDone }) }
    ] }), { width: 200, align: "end" });
    const addMenu = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-pop-add" }, /* @__PURE__ */ react_dashboard_default.createElement(QuickAdd, { date: view === "day" ? a : today, autoFocus: true, onDone: close })), { width: 320, align: "end" });
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-tasks", `is-${view}`) }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-toolbar" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-toolbar-nav" }, /* @__PURE__ */ react_dashboard_default.createElement(Button, { variant: "ghost", size: "sm", onClick: () => setAnchor(today), disabled: a === today && view !== "month" }, "Today"), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "chevL", label: "Previous", onClick: () => step(-1) }), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "chevR", label: "Next", onClick: () => step(1) }), /* @__PURE__ */ react_dashboard_default.createElement("h1", { className: "at-period" }, periodText, view !== "week" && !periodText.includes(a.slice(0, 4)) ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-period-year" }, a.slice(0, 4)) : null)), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-toolbar-right" }, /* @__PURE__ */ react_dashboard_default.createElement(
      Segmented,
      {
        label: "View",
        value: view,
        onChange: (v) => setPrefs({ view: v }),
        options: [{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]
      }
    ), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-filter", prefs.area && "is-on"), onClick: areaMenu }, prefs.area ? /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area: prefs.area }) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", null, prefs.area || "All areas"), /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "chevD", size: 14 })), narrow ? null : /* @__PURE__ */ react_dashboard_default.createElement(Button, { variant: "primary", size: "sm", icon: "plus", onClick: addMenu }, "Add"))), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-viewport" }, view === "month" ? /* @__PURE__ */ react_dashboard_default.createElement(MonthView, { anchor: a, narrow }) : null, view === "week" ? /* @__PURE__ */ react_dashboard_default.createElement(WeekView, { anchor: a, narrow, onStep: step }) : null, view === "day" && narrow ? /* @__PURE__ */ react_dashboard_default.createElement(DayScroll, { anchor: a, length: scrollLen, onReachEnd: growScroll }) : null, view === "day" && !narrow ? /* @__PURE__ */ react_dashboard_default.createElement(DayView, { anchor: a }) : null), narrow ? /* @__PURE__ */ react_dashboard_default.createElement(PhoneComposer, { date: view === "day" ? a : today }) : null);
  }
  function PhoneComposer({ date: initialDate }) {
    const { actions, meta, prefs, today } = useApp();
    const overlay = useOverlay();
    const [open, setOpen] = react_dashboard_default.useState(false);
    const [title, setTitle] = react_dashboard_default.useState("");
    const [date, setDate] = react_dashboard_default.useState(initialDate);
    const [area, setArea] = react_dashboard_default.useState("");
    const [busy, setBusy] = react_dashboard_default.useState(false);
    const [lift, setLift] = react_dashboard_default.useState(0);
    const input = react_dashboard_default.useRef(null);
    react_dashboard_default.useEffect(() => {
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
    const pickDate = (e) => overlay.open(e.currentTarget, (closePop) => /* @__PURE__ */ react_dashboard_default.createElement(DatePicker, { value: date, today, close: closePop, onPick: (d) => {
      setDate(d);
      refocus();
    } }), { width: 300 });
    const pickArea = (e) => overlay.open(e.currentTarget, (closePop) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close: closePop, items: (meta.areas || []).map((ar) => ({
      label: ar,
      icon: ar === area ? "check" : void 0,
      run: () => {
        setArea(ar);
        refocus();
      }
    })) }), { width: 220 });
    return /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-fab", open && "is-hidden"), "aria-label": "Add a task", onClick: start }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "plus", size: 24 })), open ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-composer-scrim", onClick: close }) : null, /* @__PURE__ */ react_dashboard_default.createElement(
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
      /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-composer-row" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-check is-ghost", "aria-hidden": "true" }), /* @__PURE__ */ react_dashboard_default.createElement(
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
      ), busy ? /* @__PURE__ */ react_dashboard_default.createElement(Spinner, null) : null),
      /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-composer-bar" }, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field", onClick: pickDate, tabIndex: open ? 0 : -1 }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "cal", size: 15 }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, relativeDay(date, today))), (meta.areas || []).length ? /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field", onClick: pickArea, tabIndex: open ? 0 : -1 }, /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, area || "No area")) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement(Button, { variant: "ghost", size: "sm", onClick: close, tabIndex: open ? 0 : -1 }, "Done"), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "submit", className: "at-composer-send", "aria-label": "Add task", disabled: !title.trim() || busy, tabIndex: open ? 0 : -1 }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "arrowR", size: 18, strokeWidth: 2.2 })))
    ));
  }

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
  var h = react_dashboard_default.createElement;
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
    const { store, api, actions, today, meta, host, chat } = useApp();
    const toast = useToast();
    const overlay = useOverlay();
    const sel = react_dashboard_default.useCallback((s) => s.byId[id], [id]);
    const task = useStore(store, sel);
    const [loadError, setLoadError] = react_dashboard_default.useState(null);
    const [editing, setEditing] = react_dashboard_default.useState(false);
    const [stale, setStale] = react_dashboard_default.useState(false);
    const [copied, setCopied] = react_dashboard_default.useState(false);
    react_dashboard_default.useEffect(() => {
      if (!copied) return void 0;
      const hide = () => setCopied(false);
      document.addEventListener("pointerdown", hide, true);
      document.addEventListener("keydown", hide, true);
      return () => {
        document.removeEventListener("pointerdown", hide, true);
        document.removeEventListener("keydown", hide, true);
      };
    }, [copied]);
    react_dashboard_default.useEffect(() => setCopied(false), [id]);
    const [sending, setSending] = react_dashboard_default.useState(false);
    const load = react_dashboard_default.useCallback(() => {
      setLoadError(null);
      setStale(false);
      return store.loadTask(id).catch((err) => setLoadError(err));
    }, [id, store]);
    react_dashboard_default.useEffect(() => {
      setEditing(false);
      load();
    }, [id]);
    const bodyMissing = !!task && task.body === void 0;
    react_dashboard_default.useEffect(() => {
      if (bodyMissing && !loadError) load();
    }, [bodyMissing]);
    react_dashboard_default.useEffect(() => {
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
    react_dashboard_default.useEffect(() => {
      const key = (e) => {
        if (e.key === "Escape" && !e.defaultPrevented && !editing) onClose();
      };
      window.addEventListener("keydown", key);
      return () => window.removeEventListener("keydown", key);
    }, [onClose, editing]);
    const flushRef = react_dashboard_default.useRef(null);
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
    const toggleQueue = react_dashboard_default.useRef(Promise.resolve());
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
      return /* @__PURE__ */ react_dashboard_default.createElement(PanelShell, { narrow, onClose }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 20 }), /* @__PURE__ */ react_dashboard_default.createElement("p", null, describeError(loadError)), /* @__PURE__ */ react_dashboard_default.createElement(Button, { onClick: load }, "Try again")));
    }
    if (!task) return /* @__PURE__ */ react_dashboard_default.createElement(PanelShell, { narrow, onClose }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ react_dashboard_default.createElement(Spinner, { size: 18 })));
    const date = taskDate(task);
    const separateDue = task.due && task.scheduled && task.due !== task.scheduled;
    const pickDate = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(DatePicker, { value: date, today, close, onPick: async (d) => {
      if (await settle()) actions.move(store.getState().byId[id] || task, d);
    } }), { width: 300 });
    const pickDue = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(
      DatePicker,
      {
        value: task.due,
        today,
        close,
        onPick: (d) => patch({ due: d, keep_separate: true }, { due: d })
      }
    ), { width: 300 });
    const pickArea = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: (meta.areas || []).map((ar) => ({
      label: ar,
      icon: ar === task.area ? "check" : void 0,
      run: () => patch({ area: ar })
    })) }), { width: 200 });
    const pickPriority = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: PRIORITIES.map((p) => ({
      label: p[0].toUpperCase() + p.slice(1),
      icon: p === (task.priority || "normal") ? "check" : void 0,
      run: () => patch({ priority: p })
    })) }), { width: 180 });
    const pickStatus = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: STATUSES.map(([v, l]) => ({
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
        if (host === "desktop" && chat) {
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
    return /* @__PURE__ */ react_dashboard_default.createElement(PanelShell, { narrow, onClose, footer: isDone(task) ? null : /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-cta", sending && "is-busy"), onClick: sendToChat, disabled: sending }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "chat", size: 19, strokeWidth: 2 }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, sending ? "Starting\u2026" : "Start in chat")), actions: /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, task.loading ? /* @__PURE__ */ react_dashboard_default.createElement(Spinner, null) : null, /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "clipboard", label: "Copy title and ID for chat", onClick: copyForChat }), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "refresh", label: "Reload", onClick: load })) }, stale ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-banner at-tone-late" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 15 }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }, "This task changed somewhere else."), /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", onClick: load }, "Reload")) : null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-titlerow" }, /* @__PURE__ */ react_dashboard_default.createElement(Check, { checked: isDone(task), onChange: async () => {
      if (await settle()) actions.toggle(store.getState().byId[id] || task);
    }, label: isDone(task) ? "Mark not done" : "Mark done", size: "lg" }), /* @__PURE__ */ react_dashboard_default.createElement(
      TitleField,
      {
        value: task.title,
        done: isDone(task),
        onSave: (title) => patch({ title }),
        onHold: holdRegistered,
        onLongPress: copyForChat,
        copied
      }
    )), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-fields" }, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-field", date && date < today && !isDone(task) && "is-late"), onClick: pickDate }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "cal", size: 15 }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, date ? relativeDay(date, today) : "No date")), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field", onClick: pickArea }, /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area: task.area }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, task.area || "No area")), isDone(task) ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-field at-status is-static", "data-s": task.status }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-status-dot" }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, task.status === "cancelled" ? "Cancelled" : "Done")) : /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field at-status", "data-s": task.status || "open", onClick: pickStatus }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-status-dot" }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, (STATUSES.find(([v]) => v === task.status) || [0, "Open"])[1])), separateDue ? /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field", onClick: pickDue }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Due"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, relativeDay(task.due, today))) : null), /* @__PURE__ */ react_dashboard_default.createElement(SummaryField, { value: task.summary || "", onSave: (summary) => patch({ summary }) }), editing ? /* @__PURE__ */ react_dashboard_default.createElement(BodyEditor, { task, onSave: saveBody, onDone: () => setEditing(false), onStale: () => setStale(true), flushRef }) : task.body === void 0 ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-loading" }, /* @__PURE__ */ react_dashboard_default.createElement(Spinner, null)) : /* @__PURE__ */ react_dashboard_default.createElement(BodyView, { task, onEdit: () => setEditing(true), onToggle: toggle }), /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { title: "More", className: "at-more" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-more-grid" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Priority"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-field is-plain", (task.priority === "high" || task.priority === "urgent") && "is-high"), onClick: pickPriority }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-prio-glyph", "data-p": task.priority || "normal" }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, (task.priority || "normal").replace(/^\w/, (c) => c.toUpperCase())))), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Due date"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, separateDue ? /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field is-plain", onClick: pickDue }, shortDate(task.due, today)) : /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-link", onClick: pickDue }, "Set a separate due date")), task.completed ? /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Completed"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, shortDate(task.completed, today))) : null, task.project ? /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Project"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mono" }, String(task.project).replace(/^\[\[|\]\]$/g, "").split("/").slice(-2, -1)[0] || task.project)) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "File"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mono at-break" }, task.path))));
  }
  function ResearchBar({ task }) {
    const { store, api } = useApp();
    const toast = useToast();
    const [click, setClick] = react_dashboard_default.useState(null);
    react_dashboard_default.useEffect(() => setClick(null), [task.task_id]);
    react_dashboard_default.useEffect(() => {
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-research-bar" }, /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", icon: task.research === "complete" ? "refresh" : "spark", disabled: b.disabled, onClick: start }, b.label), b.note ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-research-status" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "spark", size: 14 }), " ", b.note) : null);
  }
  function PanelShell({ narrow, onClose, actions, footer, children }) {
    const ref = react_dashboard_default.useRef(null);
    useSheetDismiss(ref, narrow, onClose);
    return /* @__PURE__ */ react_dashboard_default.createElement("aside", { ref, className: cx("at-panel", narrow ? "is-sheet" : "is-side"), "aria-label": "Task" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-bar" }, narrow ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-grabber" }) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), actions, /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "x", label: "Close", onClick: onClose })), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-panel-body at-scroll", footer && "has-foot"), onScroll: markScrolled }, children), footer ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-foot" }, footer) : null);
  }
  function TitleField({ value, done, onSave, onHold, onLongPress, copied }) {
    const [v, setV] = react_dashboard_default.useState(value);
    const [editing, setEditing] = react_dashboard_default.useState(false);
    const [armed, setArmed] = react_dashboard_default.useState(false);
    const ref = react_dashboard_default.useRef(null);
    const press = react_dashboard_default.useRef(null);
    const pointer = react_dashboard_default.useRef("");
    react_dashboard_default.useEffect(() => setV(value), [value]);
    react_dashboard_default.useLayoutEffect(() => {
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-title-wrap" }, /* @__PURE__ */ react_dashboard_default.createElement(
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
    ), copied ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-copied", role: "status" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "check", size: 13, strokeWidth: 2.4 }), "Copied") : null);
  }
  function SummaryField({ value, onSave }) {
    const [v, setV] = react_dashboard_default.useState(value);
    const ref = react_dashboard_default.useRef(null);
    react_dashboard_default.useEffect(() => setV(value), [value]);
    react_dashboard_default.useLayoutEffect(() => {
      const el = ref.current;
      if (el) {
        el.style.height = "auto";
        el.style.height = el.scrollHeight + "px";
      }
    }, [v]);
    return /* @__PURE__ */ react_dashboard_default.createElement(
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
    const { sections, managed: allManaged } = react_dashboard_default.useMemo(() => splitSections(task.body || ""), [task.body]);
    const stateBlock = allManaged.find((m) => /current-state/.test(m.name));
    const managed = allManaged.filter((m) => m !== stateBlock);
    const state = stateBlock ? { title: "Current state", text: stateBlock.text, start: 0, managed: true } : sections.find((s) => /^current state$/i.test(s.title));
    const rest = sections.filter((s) => s !== state);
    const logAt = rest.findIndex((s) => /^log$/i.test((s.title || "").trim()));
    const before = logAt >= 0 ? rest.slice(0, logAt) : rest;
    const after = logAt >= 0 ? rest.slice(logAt) : [];
    const renderSection = (s) => renderBlocks(parseBlocks(s.text), { onToggle: (line, checked) => onToggle(s.start + line, checked) });
    const hasContent = sections.some((s) => s.text.trim());
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-body" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-body-bar" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-body-label" }, "Notes"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", variant: "ghost", icon: "edit", onClick: onEdit }, "Edit")), state && state.text.trim() ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-state" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-state-label" }, "Current state"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-md" }, state.managed ? renderBlocks(parseBlocks(state.text)) : renderSection(state))) : null, !hasContent && !managed.length ? /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-empty-notes", onClick: onEdit }, "Add notes") : null, before.map((s, i) => /* @__PURE__ */ react_dashboard_default.createElement(BodySection, { key: `b${i}`, s, render: renderSection })), groupManaged(managed).map((m, i) => /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { key: `m${i}`, title: m.title, defaultOpen: m.title === "Research", className: "at-fold", right: /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "spark", size: 13 }) }, m.title === "Research" && !isDone(task) ? /* @__PURE__ */ react_dashboard_default.createElement(ResearchBar, { task }) : null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-md" }, renderBlocks(parseBlocks(m.text))))), !isDone(task) && !groupManaged(managed).some((m) => m.title === "Research") ? /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { title: "Research", defaultOpen: true, className: "at-fold", right: /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "spark", size: 13 }) }, /* @__PURE__ */ react_dashboard_default.createElement(ResearchBar, { task })) : null, after.map((s, i) => /* @__PURE__ */ react_dashboard_default.createElement(BodySection, { key: `a${i}`, s, render: renderSection })));
  }
  function BodySection({ s, render }) {
    return s.folded ? /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { title: s.title, className: "at-fold" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-md" }, render(s))) : /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-section" }, s.title && !/^notes$/i.test(s.title) ? /* @__PURE__ */ react_dashboard_default.createElement("h3", { className: "at-section-title" }, s.title) : null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-md" }, render(s)));
  }
  function BodyEditor({ task, onSave, onDone, onStale, flushRef }) {
    const toast = useToast();
    const parts = react_dashboard_default.useMemo(() => extractManaged(task.body || ""), []);
    const baseRev = react_dashboard_default.useRef(task.revision);
    const inFlight = react_dashboard_default.useRef(Promise.resolve(true));
    const [text, setText] = react_dashboard_default.useState(parts.editable);
    const [status, setStatus] = react_dashboard_default.useState("saved");
    const latest = react_dashboard_default.useRef(text);
    const saved = react_dashboard_default.useRef(parts.editable);
    const timer = react_dashboard_default.useRef(null);
    const ref = react_dashboard_default.useRef(null);
    const save = react_dashboard_default.useCallback(() => {
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
    react_dashboard_default.useEffect(() => {
      if (!flushRef) return void 0;
      flushRef.current = save;
      return () => {
        flushRef.current = null;
      };
    }, [flushRef, save]);
    const changedElsewhere = task.revision && baseRev.current && task.revision !== baseRev.current && status !== "saving";
    react_dashboard_default.useEffect(() => {
      if (ref.current) ref.current.focus();
    }, []);
    react_dashboard_default.useEffect(() => () => clearTimeout(timer.current), []);
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-body is-editing" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-body-bar" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-body-label" }, "Notes"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: cx("at-save", `is-${status}`) }, status === "saving" ? "Saving\u2026" : status === "saved" ? "Saved" : status === "error" ? "Not saved" : "Editing"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), status === "error" ? /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", variant: "ghost", onClick: onDone }, "Discard changes") : null, status === "error" && !changedElsewhere ? /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", onClick: save }, "Retry") : null, /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", variant: "primary", onClick: done }, "Done")), changedElsewhere ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-banner at-tone-late" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 15 }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }, "This task changed while you were editing. Your text is kept here and will not overwrite it. Copy what you need, then choose Discard changes to see the latest version.")) : null, /* @__PURE__ */ react_dashboard_default.createElement(
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
    ), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-editor-hint" }, "Markdown. Saves as you type.", parts.top.length + parts.bottom.length ? " Research added by Hermes is kept as it is." : ""));
  }

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
    const [filter, setFilter] = react_dashboard_default.useState("waiting");
    if (error && error.code === "not_found") {
      return /* @__PURE__ */ react_dashboard_default.createElement(
        Empty,
        {
          icon: "inbox",
          title: "Discovery is not available yet",
          text: "This version of Alchemy Task has no discovery runs to show. Update the plugin to review discovery here."
        }
      );
    }
    if (!runs && loading) return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-loading" }, /* @__PURE__ */ react_dashboard_default.createElement(Spinner, { size: 18 }));
    if (error && !runs) {
      return /* @__PURE__ */ react_dashboard_default.createElement(Empty, { icon: "alert", title: "Could not load discovery", text: describeError(error), action: /* @__PURE__ */ react_dashboard_default.createElement(Button, { onClick: reload }, "Try again") });
    }
    const all = runs || [];
    const configured = Array.isArray(streams) && streams.length > 0;
    if (!all.length && configured) {
      return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-scroll at-disco" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-disco-inner" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-disco-bar" }, /* @__PURE__ */ react_dashboard_default.createElement("h1", { className: "at-period" }, "Discovery"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "refresh", label: "Refresh", onClick: reload })), /* @__PURE__ */ react_dashboard_default.createElement(SourcesBar, { streams, reload }), /* @__PURE__ */ react_dashboard_default.createElement(RunningCards, { streams }), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-caughtup" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "clock", size: 18 }), /* @__PURE__ */ react_dashboard_default.createElement("div", null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-caughtup-title" }, "Waiting for the first run"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-muted" }, streams.map((s) => `${titleCase(s.name)}: ${s.when || "scheduled"}`).join(" \xB7 "))))));
    }
    if (!all.length) {
      return /* @__PURE__ */ react_dashboard_default.createElement(
        Empty,
        {
          icon: "spark",
          title: "No discovery runs yet",
          text: "Discovery reads the sources you choose and proposes tasks. Setup takes a few minutes in chat.",
          action: /* @__PURE__ */ react_dashboard_default.createElement(SetupPrompt, null),
          after: /* @__PURE__ */ react_dashboard_default.createElement(DiscoveryExplainer, null)
        }
      );
    }
    const needs = (r) => (r.summary ? r.summary.pending : (r.proposals || []).filter((p) => p.state === "pending").length) > 0 || (r.conflicts || []).length || (r.failures || []).length;
    const shown = filter === "waiting" ? all.filter(needs) : all;
    const latest = all[0];
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-scroll at-disco" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-disco-inner" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-disco-bar" }, /* @__PURE__ */ react_dashboard_default.createElement("h1", { className: "at-period" }, "Discovery"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement(
      Segmented,
      {
        label: "Show",
        value: filter,
        onChange: setFilter,
        options: [{ value: "waiting", label: "Waiting for you" }, { value: "all", label: "All runs" }]
      }
    ), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "refresh", label: "Refresh", onClick: reload })), configured ? /* @__PURE__ */ react_dashboard_default.createElement(SourcesBar, { streams, reload }) : null, configured ? /* @__PURE__ */ react_dashboard_default.createElement(RunningCards, { streams }) : null, !shown.length ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-caughtup" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "check", size: 18 }), /* @__PURE__ */ react_dashboard_default.createElement("div", null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-caughtup-title" }, "All caught up"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-muted" }, "Last run: ", titleCase(latest.stream), ", ", relativeDay(latest.day, today), " ", runTime(latest)))) : null, shown.map((r) => /* @__PURE__ */ react_dashboard_default.createElement(RunCard, { key: r.run_id, run: r, filter, reload }))));
  }
  var SETUP_PROMPT = "Set up task discovery";
  var ADD_SOURCE_PROMPT = "I want to add a new source to task discovery";
  var SOURCE_ICONS = { email: "inbox", chat: "chat", transcript: "list", meeting_notes: "list", document: "edit", tracker: "check" };
  function SourcesBar({ streams, reload }) {
    const [adding, setAdding] = react_dashboard_default.useState(false);
    const [starting, setStarting] = react_dashboard_default.useState(null);
    const [started, setStarted] = react_dashboard_default.useState({});
    const { api } = useApp();
    const toast = useToast();
    const now = Date.now();
    const busy = (s) => s.running || starting === s.name || started[s.name] && now - started[s.name] < 3 * 60 * 1e3;
    const anyRunning = streams.some((s) => s.running) || Object.keys(started).length > 0;
    react_dashboard_default.useEffect(() => {
      if (!anyRunning || !reload) return void 0;
      const id = setInterval(() => reload(), 2e4);
      return () => clearInterval(id);
    }, [anyRunning, reload]);
    react_dashboard_default.useEffect(() => {
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-sources" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-sources-rows" }, streams.map((s) => /* @__PURE__ */ react_dashboard_default.createElement("div", { key: s.name, className: "at-sources-row" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-sources-head" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-sources-label" }, many ? `${titleCase(s.name)} reads` : "Reads"), nextRunLabel(s.next_run_at) ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-sources-next", title: "Next scheduled run" }, "// Next ", nextRunLabel(s.next_run_at)) : null), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-sources-chips" }, (s.sources || []).length ? (s.sources || []).map((src, i) => /* @__PURE__ */ react_dashboard_default.createElement("span", { key: `${src.name}-${i}`, className: "at-source-chip", title: src.scope || src.name }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: SOURCE_ICONS[src.type] || "dot", size: 12 }), src.name)) : /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "No sources yet")), busy(s) ? /* @__PURE__ */ react_dashboard_default.createElement(
      Button,
      {
        size: "sm",
        className: "at-sources-run is-running",
        disabled: true,
        title: `${titleCase(s.name)} discovery is running. Its digest posts to the stream's chat when it finishes.`
      },
      /* @__PURE__ */ react_dashboard_default.createElement(Spinner, { size: 12 }),
      starting === s.name ? "Starting\u2026" : "Running\u2026"
    ) : /* @__PURE__ */ react_dashboard_default.createElement(
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
    )))), /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", icon: "plus", className: "at-sources-add", onClick: () => setAdding((v) => !v), "aria-expanded": adding }, "Add a source"), adding ? /* @__PURE__ */ react_dashboard_default.createElement(CopyPrompt, { className: "is-compact", text: ADD_SOURCE_PROMPT }) : null);
  }
  function RunningCards({ streams }) {
    const running = (streams || []).filter((s) => s.running && s.progress);
    const [, tick] = react_dashboard_default.useState(0);
    react_dashboard_default.useEffect(() => {
      if (!running.length) return void 0;
      const id = setInterval(() => tick((n) => n + 1), 3e4);
      return () => clearInterval(id);
    }, [running.length]);
    return running.map((s) => {
      const { label, fraction } = runProgressLabel(s.progress);
      const elapsed = elapsedLabel(s.progress.started_at);
      const pct = fraction == null ? null : Math.round(fraction * 100);
      return /* @__PURE__ */ react_dashboard_default.createElement("article", { key: s.name, className: "at-run at-run-live", "aria-live": "polite" }, /* @__PURE__ */ react_dashboard_default.createElement("header", { className: "at-run-head" }, /* @__PURE__ */ react_dashboard_default.createElement("div", null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-run-title" }, titleCase(s.name), " discovery"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-run-sub" }, /* @__PURE__ */ react_dashboard_default.createElement("span", null, "Running now"), elapsed ? /* @__PURE__ */ react_dashboard_default.createElement("span", null, elapsed) : null))), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-runbar-wrap" }, /* @__PURE__ */ react_dashboard_default.createElement(
        "div",
        {
          className: cx("at-runbar", pct == null && "is-indeterminate"),
          role: "progressbar",
          "aria-label": label,
          "aria-valuemin": 0,
          "aria-valuemax": 100,
          "aria-valuenow": pct == null ? void 0 : pct
        },
        /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-runbar-fill", style: pct == null ? void 0 : { width: `${Math.max(3, pct)}%` } })
      ), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-runbar-label" }, label)));
    });
  }
  function CopyPrompt({ text, className }) {
    const toast = useToast();
    const copy = async () => toast(await copyText(text) ? "Copied. Paste it into a chat with Hermes." : "Could not copy");
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-copy-prompt", className) }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-setup-prompt-label" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "chat", size: 15 }), " Tell Hermes in chat"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-copy-prompt-row" }, /* @__PURE__ */ react_dashboard_default.createElement("q", { className: "at-copy-prompt-text" }, text), /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", icon: "clipboard", onClick: copy }, "Copy")));
  }
  function SetupPrompt({ text = SETUP_PROMPT }) {
    const toast = useToast();
    const copy = async () => toast(await copyText(text) ? "Copied. Paste it into a chat with Hermes." : "Could not copy");
    return /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-setup-prompt", onClick: copy, title: "Copy" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-setup-prompt-label" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "chat", size: 17 }), " Tell Hermes in chat"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-setup-prompt-text" }, text), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-setup-prompt-copy" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "clipboard", size: 15 }), " Copy"));
  }
  function Empty({ icon, title, text, action, after }) {
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-scroll at-disco" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-emptystate" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-emptystate-icon" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: icon, size: 22 })), /* @__PURE__ */ react_dashboard_default.createElement("h2", null, title), /* @__PURE__ */ react_dashboard_default.createElement("p", null, text), action), after);
  }
  var DISCO_STEPS = [
    { icon: "inbox", title: "It reads your sources", text: "On the schedule you pick, it checks the email, chat, meeting transcripts and shared docs you approve." },
    { icon: "spark", title: "It researches each ask", text: "It works out what is being asked of you, whether a task already covers it, and what doing it will take." },
    { icon: "check", title: "You decide", text: /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, "A short numbered digest lands in your chat. Reply ", /* @__PURE__ */ react_dashboard_default.createElement("q", null, "2 create, 4 skip"), " and the tasks appear, already researched.") }
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
    return /* @__PURE__ */ react_dashboard_default.createElement("section", { className: "at-explainer", "aria-label": "What discovery does" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-explainer-head" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-explainer-kicker" }, "Why set it up"), /* @__PURE__ */ react_dashboard_default.createElement("h3", null, "A safety net for the asks that slip through"), /* @__PURE__ */ react_dashboard_default.createElement("p", null, "Every day, small requests get buried: a reply you meant to send, a favor asked halfway through a long thread, one ask among twenty in a meeting. Discovery finds the ones meant for you and offers them as tasks, so nothing quietly falls through the cracks.")), /* @__PURE__ */ react_dashboard_default.createElement("ol", { className: "at-explainer-steps" }, DISCO_STEPS.map((s, i) => /* @__PURE__ */ react_dashboard_default.createElement("li", { key: s.title, className: "at-explainer-step" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-explainer-num" }, i + 1), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-explainer-step-icon" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: s.icon, size: 16 })), /* @__PURE__ */ react_dashboard_default.createElement("strong", null, s.title), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-explainer-step-text" }, s.text)))), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-explainer-sub" }, "What it catches"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-explainer-grid" }, DISCO_CATCHES.map((c) => /* @__PURE__ */ react_dashboard_default.createElement("article", { key: c.source, className: "at-catch" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-catch-source" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: c.icon, size: 14 }), " ", c.source), /* @__PURE__ */ react_dashboard_default.createElement("h4", null, c.title), /* @__PURE__ */ react_dashboard_default.createElement("blockquote", null, [].concat(c.quote).map((line) => /* @__PURE__ */ react_dashboard_default.createElement("span", { key: line }, line))), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-catch-where" }, c.where), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-catch-task" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-catch-check", "aria-hidden": "true" }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-catch-task-text" }, c.task), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-catch-due" }, c.due))))), /* @__PURE__ */ react_dashboard_default.createElement("p", { className: "at-explainer-foot" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "check", size: 14 }), " Nothing becomes a task until you reply. Discovery only reads your sources: it never replies to anyone or changes anything in your email, chat or documents."));
  }
  function RunCard({ run, filter, reload }) {
    const { today } = useApp();
    const proposals = run.proposals || [];
    const visible = filter === "waiting" ? proposals.filter((p) => p.state === "pending") : proposals;
    const outcomes = (run.outcomes || []).filter((o) => o.status !== "noop");
    const attention = [...(run.conflicts || []).map((c) => ({ ...c, kind: "conflict" })), ...run.failures || []];
    const test = run.mode && run.mode !== "production";
    return /* @__PURE__ */ react_dashboard_default.createElement("article", { className: "at-run" }, /* @__PURE__ */ react_dashboard_default.createElement("header", { className: "at-run-head" }, /* @__PURE__ */ react_dashboard_default.createElement("div", null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-run-title" }, titleCase(run.stream)), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-run-sub" }, /* @__PURE__ */ react_dashboard_default.createElement("span", null, relativeDay(run.day, today), runTime(run) ? ` \xB7 ${runTime(run)}` : ""), sourcesLine(run) ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: cx(run.degraded && "is-late") }, sourcesLine(run)) : null, test ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-badge" }, "Test run") : null)), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), run.summary && run.summary.pending ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-count is-accent" }, run.summary.pending, " waiting") : null), visible.length ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-proposals" }, visible.map((p) => /* @__PURE__ */ react_dashboard_default.createElement(ProposalCard, { key: p.proposal_id, p, run, reload, readOnly: test }))) : filter === "all" && !proposals.length ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-run-none" }, "No new proposals in this run.") : null, outcomes.length ? /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { title: "Updated automatically", count: outcomes.length, className: "at-run-fold" }, outcomes.map((o) => /* @__PURE__ */ react_dashboard_default.createElement(Outcome, { key: o.unit_id, o, run, reload }))) : null, attention.length ? /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { title: "Needs attention", count: attention.length, tone: "late", className: "at-run-fold", defaultOpen: true }, attention.map((a, i) => /* @__PURE__ */ react_dashboard_default.createElement("div", { key: i, className: "at-attn" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 14 }), /* @__PURE__ */ react_dashboard_default.createElement("div", null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-attn-title" }, a.title || (a.kind === "conflict" ? "Several tasks match one item" : "Research follow-up")), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-muted" }, a.kind === "conflict" ? "Nothing was changed. Ask Hermes which task this belongs to." : a.reason))))) : null, /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { title: "Run details", className: "at-run-fold is-quiet" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-details" }, (run.coverage || []).map((c, i) => /* @__PURE__ */ react_dashboard_default.createElement("div", { key: i, className: "at-detail-row" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: cx("at-statusdot", c.status === "complete" ? "is-ok" : "is-late") }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }, c.source_key || c.source || "Source"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, c.status === "complete" ? "Checked" : c.status || "Unknown"))), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-detail-row" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Run"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mono" }, String(run.run_id).slice(0, 12))), run.delivery && run.delivery.state ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-detail-row" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Digest"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, deliveryLabel(run.delivery.state))) : null)));
  }
  var deliveryLabel = (s) => ({ delivered: "Sent", host_pending: "Sent by Hermes", prepared: "Prepared", not_prepared: "Not sent", unknown: "Unknown", inflight: "Sending" })[s] || s;
  function Outcome({ o, run, reload }) {
    const { actions, api } = useApp();
    const toast = useToast();
    const [busy, setBusy] = react_dashboard_default.useState(false);
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
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-outcome" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: cx("at-statusdot", done ? "is-ok" : "is-late") }), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-outcome-title", onClick: () => o.task_id && actions.open(o.task_id) }, o.title), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), done ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Updated") : o.resume_action ? /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", onClick: resume, disabled: busy }, busy ? "Finishing\u2026" : "Finish update") : /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, o.status));
  }
  function ProposalCard({ p, run, reload, readOnly }) {
    const { api, actions, today, meta, store } = useApp();
    const toast = useToast();
    const overlay = useOverlay();
    const targets = [...p.targets || []].sort((a, b) => (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0));
    const multi = p.kind === "selection" || targets.length > 1;
    const [mode, setMode] = react_dashboard_default.useState(p.kind === "new" || !targets.length ? "create" : "update");
    const recommended = targets.find((x) => x.recommended);
    const [target, setTarget] = react_dashboard_default.useState(targets.length === 1 ? targets[0].task_id : recommended ? recommended.task_id : null);
    const streamAreas = (meta.streams || {})[run.stream] || [];
    const [date, setDate] = react_dashboard_default.useState(p.due || p.due_hint || today);
    const [area, setArea] = react_dashboard_default.useState(p.area || (streamAreas.length === 1 ? streamAreas[0] : meta.default_area) || "");
    const [busy, setBusy] = react_dashboard_default.useState(null);
    const [gone, setGone] = react_dashboard_default.useState(false);
    if (p.state === "approved" || p.state === "complete") {
      const r = p.result || {};
      const finished = p.state === "complete" || r.state === "complete";
      return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop is-resolved" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: cx("at-statusdot", finished ? "is-ok" : "is-late") }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-prop-resolved" }, r.operation === "updated" ? "Updated" : "Created", " ", /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-linkish", onClick: () => r.task_id && actions.open(r.task_id) }, r.title || p.title)), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), finished ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, p.ref) : /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Saving\u2026"));
    }
    if (p.state === "dismissed" || gone) {
      return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop is-resolved is-dismissed" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-prop-resolved" }, p.title), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Dismissed"));
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
    const pickDate = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(DatePicker, { value: date, today, onPick: setDate, close }), { width: 300 });
    const pickArea = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: (meta.areas || []).map((ar) => ({ label: ar, icon: ar === area ? "check" : void 0, run: () => setArea(ar) })) }), { width: 200 });
    const addition = digestField(p, "digest_addition");
    const state = digestField(p, "digest_current_state");
    const next = digestField(p, "digest_next_action");
    const full = fullResearch(p);
    const links = [].concat(p.source_links || []).filter(Boolean);
    const uncertain = p.research_disposition === "uncertain";
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-prop", p.expired && "is-expired") }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-head" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-prop-ref" }, p.ref), /* @__PURE__ */ react_dashboard_default.createElement("h3", { className: "at-prop-title" }, p.title), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "x", label: "Dismiss", className: "at-prop-dismiss", onClick: dismiss, disabled: !!busy || readOnly })), state ? /* @__PURE__ */ react_dashboard_default.createElement("p", { className: "at-prop-text" }, state) : null, next ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-next" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-prop-label" }, "Next"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, next)) : null, uncertain ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-uncertain" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 14 }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, [].concat(p.uncertainty || []).join(" ") || "Hermes was not sure about this one. Check it before you add it.")) : null, links.length ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-links" }, links.slice(0, 4).map((l, i) => /* @__PURE__ */ react_dashboard_default.createElement(SourceLink, { key: i, href: l }))) : null, targets.length ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-prop-targets", mode === "create" && "is-muted") }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-label" }, multi ? "Could update one of these tasks" : "May update an existing task"), targets.map((t) => /* @__PURE__ */ react_dashboard_default.createElement("label", { key: t.task_id, className: cx("at-target", target === t.task_id && mode === "update" && "is-on") }, multi ? /* @__PURE__ */ react_dashboard_default.createElement(
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
    ) : /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "arrowR", size: 14 }), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-target-main" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-target-title" }, t.title, t.recommended && multi ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-chip", style: { marginLeft: 6 } }, "Recommended") : null), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-target-meta" }, t.area ? /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area: t.area }), t.area) : null, taskDate(t) ? /* @__PURE__ */ react_dashboard_default.createElement("span", null, relativeDay(taskDate(t), today)) : null, t.status && t.status !== "open" ? /* @__PURE__ */ react_dashboard_default.createElement("span", null, t.status) : null)), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-link", onClick: (e) => {
      e.preventDefault();
      actions.open(t.task_id);
    } }, "Open"))), addition ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-addition" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-prop-label" }, "Would add"), /* @__PURE__ */ react_dashboard_default.createElement("p", null, addition)) : null) : null, full.length ? /* @__PURE__ */ react_dashboard_default.createElement(Disclosure, { title: "Full research", className: "at-prop-full is-quiet" }, full.map((sec) => /* @__PURE__ */ react_dashboard_default.createElement("div", { key: sec.label, className: "at-prop-full-sec" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-label" }, sec.label), sec.items ? /* @__PURE__ */ react_dashboard_default.createElement("ul", null, sec.items.map((a, i) => /* @__PURE__ */ react_dashboard_default.createElement("li", { key: i }, a))) : /* @__PURE__ */ react_dashboard_default.createElement("p", null, sec.text)))) : null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-actions" }, mode === "create" ? /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field", onClick: pickDate }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "cal", size: 14 }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, relativeDay(date, today))), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: cx("at-field", !area && "is-late"), onClick: pickArea }, /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, area || "Pick area")), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), targets.length ? /* @__PURE__ */ react_dashboard_default.createElement(Button, { variant: "ghost", size: "sm", onClick: () => setMode("update"), disabled: !!busy }, "Update instead") : null, /* @__PURE__ */ react_dashboard_default.createElement(Button, { variant: "primary", size: "sm", icon: "plus", onClick: () => approve("create"), disabled: !!busy || readOnly }, busy === "create" ? "Creating\u2026" : "Create task")) : /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement(Button, { variant: "ghost", size: "sm", onClick: () => setMode("create"), disabled: !!busy }, "Create new instead"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement(Button, { variant: "primary", size: "sm", icon: "check", onClick: () => approve("update"), disabled: !!busy || !target || readOnly }, busy === "update" ? "Updating\u2026" : multi ? "Update selected" : "Update task"))), p.expired ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-prop-foot at-muted" }, "Expired ", relativeDay(p.expires, today).toLowerCase(), ". You can still add it.") : null);
  }
  function SourceLink({ href }) {
    let label = href;
    try {
      const u = new URL(href);
      const host = u.host.replace(/^www\./, "");
      label = /slack/.test(host) ? "Slack" : /mail\.google|gmail/.test(host) ? "Gmail" : /notion/.test(host) ? "Notion" : /github/.test(host) ? "GitHub" : host;
    } catch {
    }
    return /* @__PURE__ */ react_dashboard_default.createElement("a", { className: "at-srclink", href, target: "_blank", rel: "noreferrer noopener" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "link", size: 12 }), label);
  }

  // ui/src/settings.jsx
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
    const [data, setData] = react_dashboard_default.useState(null);
    const [error, setError] = react_dashboard_default.useState(null);
    const sheetRef = react_dashboard_default.useRef(null);
    useSheetDismiss(sheetRef, narrow && !inline2, onClose);
    const load = react_dashboard_default.useCallback(() => {
      setError(null);
      return api.settings().then(setData, setError);
    }, [api]);
    react_dashboard_default.useEffect(() => {
      load();
    }, [load]);
    const body = !data ? error ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 20 }), /* @__PURE__ */ react_dashboard_default.createElement("p", null, describeError(error)), /* @__PURE__ */ react_dashboard_default.createElement(Button, { onClick: load }, "Try again")) : /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-empty" }, /* @__PURE__ */ react_dashboard_default.createElement(Spinner, { size: 18 })) : /* @__PURE__ */ react_dashboard_default.createElement(SettingsBody, { data, reload: load });
    if (inline2) return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-settings-inline" }, body);
    return /* @__PURE__ */ react_dashboard_default.createElement("aside", { ref: sheetRef, className: cx("at-panel", narrow ? "is-sheet" : "is-side", "at-settings"), "aria-label": "Settings" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-bar" }, narrow ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-grabber" }) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-panel-heading" }, "Settings"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "x", label: "Close", onClick: onClose })), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-panel-body at-scroll", onScroll: markScrolled }, body));
  }
  function SettingsBody({ data, reload }) {
    const streams = data.streams || [];
    const t = data.tasks || {};
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-settings-body" }, /* @__PURE__ */ react_dashboard_default.createElement("section", { className: "at-set-sec" }, /* @__PURE__ */ react_dashboard_default.createElement("h3", null, "Discovery"), /* @__PURE__ */ react_dashboard_default.createElement("p", { className: "at-muted" }, "When each discovery stream reads its sources and proposes tasks."), streams.length ? streams.map((s) => /* @__PURE__ */ react_dashboard_default.createElement(StreamRow, { key: s.name, s, reload })) : /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-set-empty" }, "No streams yet. Ask Hermes: ", /* @__PURE__ */ react_dashboard_default.createElement("q", null, "Set up a daily digest from my email at 7 AM."))), /* @__PURE__ */ react_dashboard_default.createElement("section", { className: "at-set-sec" }, /* @__PURE__ */ react_dashboard_default.createElement("h3", null, "Tasks"), /* @__PURE__ */ react_dashboard_default.createElement(TaskDefaults, { t, reload })), /* @__PURE__ */ react_dashboard_default.createElement("section", { className: "at-set-sec" }, /* @__PURE__ */ react_dashboard_default.createElement("h3", null, "Sync and storage"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-set-grid" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Workspace"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-mono at-break" }, t.workspace_root || "Not set up"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Time zone"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, t.timezone || "Hermes default"), data.sync && data.sync.git ? /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Git"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, data.sync.git)) : null, data.sync && data.sync.reminders ? /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "iOS Reminders"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, data.sync.reminders)) : null), /* @__PURE__ */ react_dashboard_default.createElement("p", { className: "at-muted at-set-hint" }, "To change sources, accounts or areas, ask Hermes in chat, for example ", /* @__PURE__ */ react_dashboard_default.createElement("q", null, "add my team Slack channel to the work digest"), ".")));
  }
  function StreamRow({ s, reload }) {
    const { api } = useApp();
    const toast = useToast();
    const overlay = useOverlay();
    const [freq, setFreq] = react_dashboard_default.useState(s.frequency || "daily");
    const [time, setTime] = react_dashboard_default.useState(to24(s.time || "7 AM"));
    const [busy, setBusy] = react_dashboard_default.useState(null);
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
    const pickFreq = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: FREQUENCIES.map(([v, l]) => ({ label: l, icon: v === freq ? "check" : void 0, run: () => setFreq(v) })) }), { width: 200 });
    const blocked = s.setup_blocked_reason || (s.activation_state && !/active|ok|ready/i.test(s.activation_state) ? s.activation_state : "");
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-stream" }, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-stream-head" }, /* @__PURE__ */ react_dashboard_default.createElement("div", null, /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-stream-name" }, String(s.name).replace(/\b\w/g, (c) => c.toUpperCase())), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-muted" }, (s.areas || []).map((a) => /* @__PURE__ */ react_dashboard_default.createElement("span", { key: a, className: "at-inline-area" }, /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area: a }), a)), s.last_run ? /* @__PURE__ */ react_dashboard_default.createElement("span", null, " \xB7 last ran ", lastRun(s.last_run)) : null)), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", variant: "ghost", icon: "play", onClick: runNow, disabled: !!busy }, busy === "run" ? "Starting\u2026" : "Run now")), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-stream-sched" }, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field", onClick: pickFreq }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "clock", size: 14 }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, (FREQUENCIES.find(([v]) => v === freq) || [0, freq])[1]), /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "chevD", size: 13 })), timed(freq) ? /* @__PURE__ */ react_dashboard_default.createElement("label", { className: "at-field at-timefield" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "at"), /* @__PURE__ */ react_dashboard_default.createElement("input", { type: "time", value: time, step: 300, onChange: (e) => setTime(e.target.value || time) })) : null, s.timezone ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted at-tz" }, s.timezone.replace(/_/g, " ")) : null, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), dirty ? /* @__PURE__ */ react_dashboard_default.createElement(Button, { size: "sm", variant: "primary", onClick: save, disabled: !!busy }, busy === "save" ? "Saving\u2026" : "Save") : null), (s.sources || []).length ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-stream-sources" }, (s.sources || []).map((src) => /* @__PURE__ */ react_dashboard_default.createElement("span", { key: src.name, className: "at-chip", title: src.scope }, src.name))) : null, blocked ? /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-banner at-tone-late" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "alert", size: 14 }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, blocked)) : null);
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
    const pickArea = (e) => overlay.open(e.currentTarget, (close) => /* @__PURE__ */ react_dashboard_default.createElement(Menu, { close, items: (meta.areas || []).map((a) => ({ label: a, icon: a === t.default_area ? "check" : void 0, run: () => set({ default_area: a }) })) }), { width: 200 });
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-set-grid" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Default area"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", className: "at-field", onClick: pickArea }, /* @__PURE__ */ react_dashboard_default.createElement(AreaDot, { area: t.default_area }), /* @__PURE__ */ react_dashboard_default.createElement("span", null, t.default_area || "None"), /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: "chevD", size: 13 }))), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Research new tasks"), /* @__PURE__ */ react_dashboard_default.createElement("span", null, /* @__PURE__ */ react_dashboard_default.createElement(
      "button",
      {
        type: "button",
        role: "switch",
        "aria-checked": !!t.research_by_default,
        className: cx("at-switch", t.research_by_default && "is-on"),
        onClick: () => set({ research_by_default: !t.research_by_default })
      },
      /* @__PURE__ */ react_dashboard_default.createElement("i", null)
    )), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-muted" }, "Research model"), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-research-model" }, /* @__PURE__ */ react_dashboard_default.createElement(ModelInput, { label: "Research model", value: t.research_model, onSave: (v) => set({ research_model: v }) }), /* @__PURE__ */ react_dashboard_default.createElement(ModelInput, { label: "Research provider", value: t.research_provider, small: true, onSave: (v) => set({ research_provider: v }) }), /* @__PURE__ */ react_dashboard_default.createElement(CopyPrompt, { className: "is-compact", text: RESEARCH_MODEL_PROMPT })));
  }
  function ModelInput({ label, value, small, onSave }) {
    const [text, setText] = react_dashboard_default.useState(value || "");
    react_dashboard_default.useEffect(() => {
      setText(value || "");
    }, [value]);
    const commit = () => {
      const v = text.trim();
      if (v !== (value || "")) onSave(v);
    };
    return /* @__PURE__ */ react_dashboard_default.createElement(
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
    return /* @__PURE__ */ react_dashboard_default.createElement(ToastHost, null, /* @__PURE__ */ react_dashboard_default.createElement(AppInner, { ...props }));
  }
  function AppInner({ transport: transport2, host, initialView, settingsOnly, chat }) {
    const api = transport2;
    const toast = useToast();
    const rootRef = react_dashboard_default.useRef(null);
    const width = useWidth(rootRef);
    const narrow = width < NARROW;
    const store = react_dashboard_default.useMemo(() => createTaskStore(api), [api]);
    const today = useStore(store, selToday2);
    const busy = useStore(store, selLoading);
    const [meta, setMeta] = react_dashboard_default.useState(null);
    const [metaError, setMetaError] = react_dashboard_default.useState(null);
    const [tab, setTab] = react_dashboard_default.useState(initialView === "discovery" ? "discovery" : "tasks");
    const [settingsOpen, setSettingsOpen] = react_dashboard_default.useState(initialView === "settings");
    const [selectedId, setSelectedId] = react_dashboard_default.useState(null);
    const [prefsRaw, setPrefsRaw] = usePref("prefs", { view: null, area: "", hideDone: false });
    const prefs = prefsRaw;
    const setPrefs = react_dashboard_default.useCallback((p) => setPrefsRaw((cur) => ({ ...cur, ...p })), [setPrefsRaw]);
    const [runs, setRuns] = react_dashboard_default.useState(null);
    const [runsError, setRunsError] = react_dashboard_default.useState(null);
    const [runsLoading, setRunsLoading] = react_dashboard_default.useState(false);
    const [streams, setStreams] = react_dashboard_default.useState(null);
    const loadMeta = react_dashboard_default.useCallback(() => api.meta().then((m) => {
      setMeta(m);
      setMetaError(null);
      store.setToday(m.today);
    }, setMetaError), [api, store]);
    const loadRuns = react_dashboard_default.useCallback(async () => {
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
    react_dashboard_default.useEffect(() => {
      loadMeta();
      loadRuns();
    }, [loadMeta, loadRuns]);
    react_dashboard_default.useEffect(() => {
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
    react_dashboard_default.useEffect(() => {
      const open = (e) => {
        const v = e.detail;
        if (v === "discovery" || v === "tasks") setTab(v);
        if (v === "settings") setSettingsOpen(true);
      };
      window.addEventListener("alchemy-task:open", open);
      return () => window.removeEventListener("alchemy-task:open", open);
    }, []);
    const actions = react_dashboard_default.useMemo(() => {
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
    const onDrop = react_dashboard_default.useCallback((task, date) => actions.move(task, date), [actions]);
    const pending = discoveryBadge(runs, streams);
    const ctx = react_dashboard_default.useMemo(() => ({
      api,
      store,
      meta: meta || {},
      today: today || meta && meta.today,
      prefs,
      setPrefs,
      actions,
      selectedId,
      narrow,
      host,
      chat
    }), [api, store, meta, today, prefs, setPrefs, actions, selectedId, narrow, host, chat]);
    const [height, setHeight] = react_dashboard_default.useState(null);
    react_dashboard_default.useLayoutEffect(() => {
      const el = rootRef.current;
      if (!el || settingsOnly) return void 0;
      const fit = () => {
        const parent = el.parentElement;
        const ph = parent ? parent.getBoundingClientRect().height : 0;
        if (host === "desktop" && ph > 300) {
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
    }, [host, settingsOnly]);
    const content = (() => {
      if (!meta && metaError) {
        return /* @__PURE__ */ react_dashboard_default.createElement(Centered, { icon: "alert", title: "Alchemy Task is not responding", text: describeError(metaError) });
      }
      if (!meta || !ctx.today) return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-loading" }, /* @__PURE__ */ react_dashboard_default.createElement(Spinner, { size: 18 }));
      if (meta.configured === false) {
        return /* @__PURE__ */ react_dashboard_default.createElement(
          Centered,
          {
            icon: "list",
            title: "Set up your tasks",
            text: "Alchemy Task is installed but not set up yet. Setup takes a few minutes in chat: your timezone, where tasks are saved, and your areas.",
            action: /* @__PURE__ */ react_dashboard_default.createElement(SetupPrompt, { text: "Set up my tasks" })
          }
        );
      }
      if (settingsOnly) return /* @__PURE__ */ react_dashboard_default.createElement(SettingsPanel, { inline: true, narrow });
      return /* @__PURE__ */ react_dashboard_default.createElement(react_dashboard_default.Fragment, null, /* @__PURE__ */ react_dashboard_default.createElement("nav", { className: "at-appbar" }, narrow ? null : /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-brand" }, /* @__PURE__ */ react_dashboard_default.createElement(BrandMark, { size: 20 }), "Alchemy Task"), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-tabs", role: "tablist" }, /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", role: "tab", "aria-selected": tab === "tasks", className: cx("at-tab", tab === "tasks" && "is-on"), onClick: () => setTab("tasks") }, "Tasks"), /* @__PURE__ */ react_dashboard_default.createElement("button", { type: "button", role: "tab", "aria-selected": tab === "discovery", className: cx("at-tab", tab === "discovery" && "is-on"), onClick: () => setTab("discovery") }, "Discovery", pending ? /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-badge-dot" }, pending) : null)), /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-flex" }), busy ? /* @__PURE__ */ react_dashboard_default.createElement(Spinner, { size: 12 }) : null, /* @__PURE__ */ react_dashboard_default.createElement(IconButton, { icon: "gear", label: "Settings", className: cx(settingsOpen && "is-on"), onClick: () => {
        setSelectedId(null);
        setSettingsOpen((v) => !v);
      } })), /* @__PURE__ */ react_dashboard_default.createElement("div", { className: cx("at-main", selectedId && !narrow && "has-panel", settingsOpen && !narrow && "has-panel") }, tab === "tasks" ? /* @__PURE__ */ react_dashboard_default.createElement(TasksView, { narrow }) : /* @__PURE__ */ react_dashboard_default.createElement(DiscoveryView, { runs, streams, error: runsError, loading: runsLoading, reload: loadRuns })), selectedId ? /* @__PURE__ */ react_dashboard_default.createElement(TaskPanel, { id: selectedId, narrow, onClose: () => setSelectedId(null) }) : null, settingsOpen && !selectedId ? /* @__PURE__ */ react_dashboard_default.createElement(SettingsPanel, { narrow, onClose: () => setSettingsOpen(false) }) : null);
    })();
    return /* @__PURE__ */ react_dashboard_default.createElement(AppContext.Provider, { value: ctx }, /* @__PURE__ */ react_dashboard_default.createElement(
      "div",
      {
        ref: rootRef,
        className: cx("at-root at-vars", narrow && "is-narrow", `host-${host}`, settingsOnly && "is-settings-only"),
        style: height ? { height } : void 0
      },
      /* @__PURE__ */ react_dashboard_default.createElement(DragProvider, { onDrop }, /* @__PURE__ */ react_dashboard_default.createElement(OverlayHost, { rootRef }, content)),
      /* @__PURE__ */ react_dashboard_default.createElement(ToastOutlet, null)
    ));
  }
  var selToday2 = (s) => s.today;
  var selLoading = (s) => s.loading > 0;
  function Centered({ icon, title, text, action }) {
    return /* @__PURE__ */ react_dashboard_default.createElement("div", { className: "at-emptystate is-full" }, /* @__PURE__ */ react_dashboard_default.createElement("span", { className: "at-emptystate-icon" }, /* @__PURE__ */ react_dashboard_default.createElement(Icon, { name: icon, size: 22 })), /* @__PURE__ */ react_dashboard_default.createElement("h2", null, title), /* @__PURE__ */ react_dashboard_default.createElement("p", null, text), action || null);
  }

  // ui/hosts/dashboard.jsx
  var SDK = window.__HERMES_PLUGIN_SDK__;
  var BASE = "/api/plugins/alchemy-task";
  var transport = makeTransport(async (method, path, body) => {
    const init = { method, headers: {} };
    if (body !== void 0) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    return SDK.fetchJSON(BASE + path, init);
  });
  function DashboardTasks() {
    return /* @__PURE__ */ react_dashboard_default.createElement(App, { transport, host: "dashboard" });
  }
  window.__HERMES_PLUGINS__.register("alchemy-task", DashboardTasks);
})();
