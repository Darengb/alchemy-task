"""Background research: launch, research-agent tools, budget and failure hooks,
recovery and the "research finished" notice.

Research runs as a Hermes subagent started through the public
``ctx.subagent_lifecycle`` API with read toolsets (web, file, session_search,
approved discovery readers, inherited MCP) plus this plugin's read-only research
toolset. A pre_tool_call guard refuses write, execution and side-effect tools and
credential-file reads for research children. Only ``research_submit`` writes, and
it writes only the plugin's own dossier block and enrichment state.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from .core import research as rs
from .core import taskfile as tf
from .core.locks import task_lock
from .core.store import NeedsInput
from . import research_git
from .core.research_guard import READ_VERBS, WRITE_BLOCKED_TOOLS, is_write_like  # noqa: F401
from .runtime import Runtime

RESEARCH_TOOLSET = "alchemy-task-research"
CALL_BUDGET = 45
TIME_BUDGET = 15 * 60
INVENTORY_TTL = 3600

_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}      # subagent_id -> run
_by_child_session: dict[str, str] = {}      # child session id -> subagent_id
_started_sessions: dict[str, str] = {}      # subagent_id -> child session id (subagent_start can precede launch's return)
_research_children: set[str] = set()        # every child session id and subagent id this plugin started
MAX_CHILDREN = 500



# ------------------------------------------------------------------ run registry

def _persist(rt: Runtime) -> None:
    try:
        rt.ctx.state.set("research_runs", {k: v for k, v in _runs.items() if not v.get("done")})
    except Exception:  # noqa: BLE001 - registry is an optimisation; task files hold the truth
        pass


def _save_children() -> None:
    try:
        ctx = _runtime_ctx()
        if ctx is not None:
            ctx.state.set("research_children", sorted(_research_children))
    except Exception:  # noqa: BLE001 - in-memory blocking still applies
        pass


def _runtime_ctx() -> Any:
    from . import runtime
    return runtime._ctx


def _mark_children(*ids: str) -> None:
    """Remember research child session/subagent ids; persisted so blocking survives a reload."""
    new = False
    with _lock:
        for i in ids:
            if i and isinstance(i, str) and i not in _research_children:
                _research_children.add(i)
                new = True
        if len(_research_children) > MAX_CHILDREN:
            for old in sorted(_research_children)[: len(_research_children) - MAX_CHILDREN]:
                _research_children.discard(old)
    if new:
        _save_children()


def reload_children(ctx: Any) -> None:
    """Restore the research-child set from plugin state (called on plugin register)."""
    try:
        saved = ctx.state.get("research_children", default=[]) or []
        with _lock:
            _research_children.update(str(x) for x in saved if isinstance(x, str) and x)
    except Exception:  # noqa: BLE001
        pass


def write_block(tool_name: Any = "", session_id: Any = "", task_id: Any = "") -> dict[str, str] | None:
    """Refuse write/exec tools for research children. Never raises; fails closed for blocked names."""
    if not is_write_like(tool_name):
        return None
    message = (f"Research agents are read-only: {tool_name} is not available to you. Use read tools "
               "(files, sessions, skills, web) and report through research_submit.")
    try:
        if (session_id and session_id in _research_children) or (task_id and task_id in _research_children):
            return {"action": "block", "message": message}
        return None
    except Exception:  # noqa: BLE001 - registry unreadable: fail closed for the blocked set
        return {"action": "block", "message": message}


def _run_for(task_id: str = "", run_id: str = "", session_id: str = "") -> tuple[str, dict[str, Any]] | None:
    with _lock:
        if task_id and task_id in _runs:
            return task_id, _runs[task_id]
        if session_id and session_id in _by_child_session:
            sid = _by_child_session[session_id]
            if sid in _runs:
                return sid, _runs[sid]
        if run_id:
            for sid, run in _runs.items():
                if run["run_id"] == run_id:
                    return sid, run
    return None


# ------------------------------------------------------------------ Hermes seams (stubbed in tests)

def model_route(settings: Any) -> dict[str, str]:
    """The research model setting as launch fields; empty when research runs on the main model."""
    route = {}
    for key in ("model", "provider"):
        value = str(getattr(settings, f"research_{key}", "") or "").strip()
        if value:
            route[key] = value
    return route


def _make_request(**kwargs: Any) -> Any:
    from agent.subagent_lifecycle import SubagentLaunchRequest
    return SubagentLaunchRequest(**kwargs)


def _registry_toolsets() -> dict[str, dict]:
    from tools.registry import registry
    return registry.get_available_toolsets()


# ------------------------------------------------------------------ launch

def _linked_notes(rt: Runtime, body: str, limit: int = 3) -> list[tuple[str, str]]:
    root = rt.settings.root()
    out = []
    for target in re.findall(r"\[\[([^\]|#]+)", body)[:10]:
        rel = target.strip()
        candidates = [root / rel, root / f"{rel}.md"]
        for path in candidates:
            try:
                path = path.resolve()
                path.relative_to(root)
            except (ValueError, OSError):
                continue
            if path.is_file() and path.suffix == ".md":
                text = path.read_text(errors="replace")
                try:
                    _, text = tf.split_raw(text)
                except tf.TaskFormatError:
                    pass
                out.append((rel, rs.strip_managed(text)[:3000]))
                break
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ origin session and launch context

CONTEXT_CAP = 30_000          # SubagentLaunchRequest.context allows 32,000; keep headroom
MEMORY_FILE_CAP = 8_000       # per memory file
RELATED_LIMIT = 10
MAX_ORIGINS = 2000
_STOP = frozenset({"with", "from", "that", "this", "into", "about", "your", "their", "them", "have", "what",
                   "when", "then", "than", "task", "make", "next", "more", "some", "will", "for", "and", "the"})


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:  # noqa: BLE001 - outside Hermes (tests, tools)
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def origin_for(rt: Runtime, task_id: str) -> str:
    try:
        return str((rt.ctx.state.get("origin_sessions", default={}) or {}).get(task_id) or "")
    except Exception:  # noqa: BLE001
        return ""


def remember_origin(rt: Runtime, task_id: str, session_id: str) -> None:
    """Save the chat that created a task, once; every later research launch points the worker at it."""
    if not task_id or not session_id:
        return
    try:
        with _lock:
            origins = rt.ctx.state.get("origin_sessions", default={}) or {}
            if origins.get(task_id):
                return
            origins[task_id] = session_id
            while len(origins) > MAX_ORIGINS:
                origins.pop(next(iter(origins)))
            rt.ctx.state.set("origin_sessions", origins)
    except Exception:  # noqa: BLE001 - launch still carries the session it was given
        pass


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(title or "").lower()) if len(w) >= 4 and w not in _STOP}


def _related_tasks(rt: Runtime, doc: Any) -> list[str]:
    store = rt.store()
    words, project = _words(doc.title), str(doc.fm.get("project") or "")
    ranked = []
    for t in store.scan().tasks:
        if t.task_id == doc.task_id:
            continue
        same_project = bool(project) and str(t.fm.get("project") or "") == project
        shared = len(words & _words(t.title))
        if same_project or shared:
            ranked.append((-(10 if same_project else 0) - shared, t.title, t))
    ranked.sort(key=lambda r: (r[0], r[1]))
    lines = []
    for _, _, t in ranked[:RELATED_LIMIT]:
        s = store.summary(t)
        line = f"- {s['title']} [{s.get('status')}]"
        if s.get("completed"):
            line += f" completed {s['completed']}"
        elif s.get("due"):
            line += f" due {s['due']}"
        line += f" ({s['path']})"
        if s.get("summary"):
            line += f": {str(s['summary'])[:200]}"
        lines.append(line)
    return lines


def _memory_text() -> str:
    home = _hermes_home()
    parts = []
    for name in ("MEMORY.md", "USER.md"):
        path = home / "memories" / name
        try:
            if path.is_file():
                text = path.read_text(errors="replace").strip()
                if text:
                    parts.append(f"--- {name} ---\n{text[:MEMORY_FILE_CAP]}")
        except OSError:
            continue
    return "\n\n".join(parts)


def build_context(rt: Runtime, doc: Any, base: str, *, created_in: str = "", requested_in: str = "",
                  toolset_note: str = "") -> str:
    """Launch context in priority order, capped at CONTEXT_CAP characters. Every extra is best-effort."""
    sections = [base[:CONTEXT_CAP]]

    def add(text: str) -> None:
        room = CONTEXT_CAP - sum(len(s) + 2 for s in sections)
        if text and room > 80:
            sections.append(text if len(text) <= room else text[: room - 20] + "\n…(truncated)")

    origin = []
    if created_in:
        origin.append(f"This task was created in Hermes session {created_in}.")
    if requested_in and requested_in != created_in:
        origin.append(f"Research was requested in Hermes session {requested_in}.")
    if origin:
        add("Origin: " + " ".join(origin) + " Call session_search on these session ids to read what the user "
            "said there (decisions, constraints, links) before researching.")
    add(toolset_note)
    try:
        memory = _memory_text()
    except Exception:  # noqa: BLE001 - missing or unreadable memory never blocks research
        memory = ""
    if memory:
        add("The user's Hermes memory (read-only copy; you cannot change it; treat as background facts):\n" + memory)
    try:
        related = _related_tasks(rt, doc)
    except Exception:  # noqa: BLE001
        related = []
    if related:
        add("Related tasks (same project or shared title words, done ones included; read their files with "
            "read_file for history):\n" + "\n".join(related))
    try:
        add(f"Scheduled job outputs live under {_hermes_home() / 'cron' / 'output'} (read with read_file or "
            "search_files if a job's past output matters).")
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(sections)[:CONTEXT_CAP]


BASE_TOOLSETS = ("web", "file", "session_search", RESEARCH_TOOLSET)
FALLBACK_TOOLSETS = ("web", RESEARCH_TOOLSET)


def worker_toolsets(rt: Runtime) -> tuple[str, ...]:
    """Toolsets a research worker requests: read toolsets, the research toolset, approved discovery readers."""
    from .jobs import approved_reader_toolsets
    return tuple(dict.fromkeys((*BASE_TOOLSETS, *approved_reader_toolsets(rt.ctx.state))))


def _toolset_report(requested: tuple[str, ...]) -> dict[str, Any]:
    """Which requested toolsets the host does not report as available (None when it cannot tell)."""
    try:
        known = _registry_toolsets()
        missing = [t for t in requested if t != RESEARCH_TOOLSET and not (known.get(t) or {}).get("available")]
    except Exception:  # noqa: BLE001 - no public answer: keep the requested list only
        missing = None
    return {"requested": list(requested), "not_available_to_worker": missing}


def _toolset_note(report: dict[str, Any]) -> str:
    missing = report.get("not_available_to_worker")
    if not missing:
        return ""
    return ("Toolsets requested for you but not available to you on this Hermes (report access that depends on "
            "them as missing or unverified): " + ", ".join(missing))


def launch(rt: Runtime, ref: str, *, origin_session: str = "") -> dict[str, Any]:
    """Claim a task and start its research agent. Must run inside an agent turn."""
    store = rt.store()
    doc = store.resolve(ref)
    with task_lock(rt.data_dir, doc.task_id, doc.path):
        doc = tf.parse_file(doc.path)
        run_id = rs.claim(doc.fm)
        tf.atomic_write(doc.path, tf.render(doc.fm, doc.body, seq_offset=doc.seq_offset,
                                            keep_blank=doc.blank_keys).encode(), expect=doc.raw)
    fields = {k: tf.norm_date(doc.fm.get(k)) or doc.fm.get(k) for k in ("area", "status", "priority", "due",
                                                                       "scheduled", "project", "estimate")}
    targets = rs.fill_targets(doc.fm, doc.body)  # sections blank (or research-owned) at launch
    goal, context = rs.goal_text(run_id=run_id, title=doc.title, fields=fields, body=rs.strip_managed(doc.body),
                                 linked=_linked_notes(rt, doc.body), today=rt.settings.today(), targets=targets)
    created_in = origin_for(rt, doc.task_id)
    if origin_session and not created_in:
        remember_origin(rt, doc.task_id, origin_session)
        created_in = origin_session
    notice_to = origin_session or created_in
    toolsets = worker_toolsets(rt)
    route = model_route(rt.settings)  # same model on the toolset fallback; never the main model instead
    report = _toolset_report(toolsets)
    if report.get("not_available_to_worker"):
        # Approved reader toolsets that no longer exist would make every launch fail ("Unknown toolsets"):
        # drop them. Core read toolsets stay requested; a parent that lacks them triggers the fallback below.
        dropped = [t for t in report["not_available_to_worker"] if t not in BASE_TOOLSETS]
        if dropped:
            report["dropped"] = dropped
            toolsets = tuple(t for t in toolsets if t not in dropped)
    context = build_context(rt, doc, context, created_in=created_in, requested_in=origin_session,
                            toolset_note=_toolset_note(report))
    try:
        try:
            handle = rt.ctx.subagent_lifecycle.launch(_make_request(
                goal=goal, context=context, role="leaf", allowed_toolsets=toolsets,
                correlation_id=f"alchemy-task:{doc.task_id}:{run_id}", **route))
        except Exception as first:  # noqa: BLE001
            text = str(first).lower()
            if "toolset" not in text and "broaden" not in text:
                raise
            # The parent (for example an older sweep job) lacks some read toolsets: research with what it has.
            report["fallback"] = {"error": str(first)[:300], "toolsets": list(FALLBACK_TOOLSETS)}
            toolsets = FALLBACK_TOOLSETS
            context = build_context(rt, doc, rs.goal_text(run_id=run_id, title=doc.title, fields=fields,
                                                          body=rs.strip_managed(doc.body),
                                                          linked=_linked_notes(rt, doc.body),
                                                          today=rt.settings.today(), targets=targets)[1],
                                    created_in=created_in, requested_in=origin_session,
                                    toolset_note=("Only web and research tools are available to you in this "
                                                  "run; report local access you could not check as unverified."))
            handle = rt.ctx.subagent_lifecycle.launch(_make_request(
                goal=goal, context=context, role="leaf", allowed_toolsets=toolsets,
                correlation_id=f"alchemy-task:{doc.task_id}:{run_id}:fallback", **route))
        handle = dict(handle) if not hasattr(handle, "to_dict") else handle.to_dict()
    except Exception as exc:  # noqa: BLE001 - recovery retries later
        _finish_failure(rt, doc.task_id, run_id, f"could not start research: {exc}")
        return {"started": False, "error": str(exc)[:300], "task_id": doc.task_id}
    with _lock:
        sid = handle["subagent_id"]
        _runs[sid] = {"task_id": doc.task_id, "run_id": run_id, "started": time.time(),
                      "calls": 0, "origin_session": notice_to, "title": doc.title, "handle": handle,
                      "toolsets": report}
        early = _started_sessions.pop(sid, "")
        if early:
            _by_child_session[early] = sid
        for old in [k for k, v in _runs.items() if v.get("done") and time.time() - v["started"] > 3600]:
            _runs.pop(old, None)
    _mark_children(sid, early)
    _persist(rt)
    return {"started": True, "task_id": doc.task_id, "run_id": run_id, "subagent_id": handle["subagent_id"],
            "handle": handle}


def on_task_created(rt: Runtime, doc: Any, origin_session: str = "") -> None:
    remember_origin(rt, doc.task_id, origin_session)
    result = launch(rt, doc.task_id, origin_session=origin_session)
    if not result.get("started"):
        raise RuntimeError(result.get("error") or "research did not start")


# ------------------------------------------------------------------ completion

def _deliver(rt: Runtime, path: Path, message: str) -> dict[str, Any]:
    store = rt.store()
    return rt.git().deliver([store.rel(path)], message)


def _finish_failure(rt: Runtime, task_id: str, run_id: str, error: str) -> str | None:
    store = rt.store()
    try:
        doc = store.resolve(task_id)
    except NeedsInput:
        return None
    with task_lock(rt.data_dir, doc.task_id, doc.path):
        doc = tf.parse_file(doc.path)
        new = rs.fail(doc.fm, run_id, error)
        if new is None:
            return None
        body = doc.body
        if new == "failed":
            body = tf.append_log(body, f"Research failed after {rs.MAX_ATTEMPTS} attempts ({error[:120]}). "
                                       "Say \"research it again\" to retry.", rt.settings.today())
        tf.atomic_write(doc.path, tf.render(doc.fm, body, seq_offset=doc.seq_offset,
                                            keep_blank=doc.blank_keys).encode(), expect=doc.raw)
    _deliver(rt, doc.path, f"task: research {'failed' if new == 'failed' else 'retry queued'} {doc.title[:60]}")
    return new


def submit(rt: Runtime, run_id: str, payload: dict[str, Any], caller_task_id: str = "") -> dict[str, Any]:
    found = _run_for(run_id=run_id)
    if found is None:
        # Not started by this process (e.g. after a restart): accept only if the file still holds the claim.
        task_id = ""
    else:
        sid, run = found
        if caller_task_id and caller_task_id.startswith("sa-") and caller_task_id != sid:
            raise rs.ResearchError("this run_id belongs to a different research agent")
        task_id = run["task_id"]
    fill_raw = payload.get("fill") if isinstance(payload, dict) else None
    normalized = rs.normalize(payload)
    store = rt.store()
    doc = None
    if task_id:
        doc = store.resolve(task_id)
    else:
        for t in store.scan().tasks:
            st = rs.state(t.fm)
            if st and str(st.get("run_id") or "") == run_id:
                doc = t
                break
        if doc is None:
            raise rs.ResearchError("unknown run_id")
    with task_lock(rt.data_dir, doc.task_id, doc.path):
        doc = tf.parse_file(doc.path)
        if not rs.holds_claim(doc.fm, run_id):
            raise rs.ResearchError("this research run was superseded or the task changed state; result discarded")
        block = rs.render(normalized, day=rt.settings.today())
        body = tf.upsert_block(doc.body, rs.START, rs.END, block)
        rs.complete(doc.fm, run_id, normalized)
        body = tf.append_log(body, rs.summary_line(normalized), rt.settings.today())
        body = _apply_fill(rt, doc.fm, body, fill_raw, normalized)
        tf.atomic_write(doc.path, tf.render(doc.fm, body, seq_offset=doc.seq_offset,
                                            keep_blank=doc.blank_keys).encode(), expect=doc.raw)
    receipt = _deliver(rt, doc.path, f"task: research {doc.title[:64]}")
    origin = ""
    with _lock:
        if found is not None:
            found[1]["done"] = True
            origin = found[1].get("origin_session") or ""
    _persist(rt)
    if origin:
        _add_notice(rt, origin, doc.title, normalized)
    return {"task_id": doc.task_id, "git": receipt, "summary": rs.summary_line(normalized)}


def _apply_fill(rt: Runtime, fm: Any, body: str, fill_raw: Any, normalized: dict[str, Any]) -> str:
    """Fill the task's blank sections from the worker's ``fill`` (on the latest content, under the caller's task
    lock). A fill problem never blocks the dossier: bad parts are dropped and noted in the log."""
    try:
        fill, problems = rs.normalize_fill(fill_raw)
        if not fill.get("summary") and normalized.get("summary"):
            fill["summary"] = normalized["summary"]   # the older top-level summary field still fills a blank one
        new_body, summary, prints, report = rs.apply_fill(fm, body, fill, day=rt.settings.today())
    except Exception as exc:  # noqa: BLE001 - the dossier must land whatever the fill holds
        return tf.append_log(body, f"Research fill dropped ({type(exc).__name__}).", rt.settings.today())
    if summary is not None:
        if "summary" in fm:
            fm["summary"] = summary
        elif hasattr(fm, "insert"):
            fm.insert(1, "summary", summary)
        else:
            fm["summary"] = summary
    st = rs.state(fm)
    if st is not None:
        if prints:
            st["fill"] = prints
        elif "fill" in st:
            del st["fill"]
    line = rs.fill_log(report, problems)
    return tf.append_log(new_body, line, rt.settings.today()) if line else new_body


def _add_notice(rt: Runtime, session_id: str, title: str, normalized: dict[str, Any]) -> None:
    missing = [a for a in normalized["access_plan"] if a["status"] == "missing"]
    text = f"Research finished for \"{title}\". {rs.EXECUTION[normalized['execution']]}"
    if missing:
        text += " Missing access: " + "; ".join(
            a["need"] + (f" (setup: {a['setup']})" if a["setup"] else "") for a in missing[:4]) + "."
        text += (" Tell the user briefly, and offer to set this up now or when they start the task. Setting up "
                 "access is separate from doing the task.")
    else:
        text += " Mention it briefly if relevant; do not interrupt the current topic."
    try:
        with _lock:
            notices = rt.ctx.state.get("notices", default={}) or {}
            notices.setdefault(session_id, []).append(text)
            notices[session_id] = notices[session_id][-5:]
            rt.ctx.state.set("notices", notices)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ hooks

def pre_tool_call(tool_name: str = "", args: Any = None, task_id: str = "", session_id: str = "", **_: Any):
    blocked = write_block(tool_name, session_id, task_id)
    if blocked is not None:
        return blocked
    try:
        if (session_id and session_id in _research_children) or (task_id and task_id in _research_children):
            refused = research_git.refuse_file_read(tool_name, args)
            if refused:
                return {"action": "block", "message": refused}
    except Exception:  # noqa: BLE001 - a guard must never throw
        pass
    found = _run_for(task_id=str(task_id or ""))
    if found is None:
        return None
    sid, run = found
    if session_id and session_id not in _research_children:
        _mark_children(session_id)
    with _lock:
        if session_id:
            _by_child_session[session_id] = sid
        run["calls"] += 1
        over = run["calls"] > CALL_BUDGET or time.time() - run["started"] > TIME_BUDGET
    if over and tool_name != "research_submit":
        return {"action": "block", "message": "Research budget used up. Call research_submit now with what you "
                f"have (run_id \"{run['run_id']}\"), then stop."}
    return None


def subagent_start(child_session_id: str = "", child_subagent_id: str = "", **_: Any) -> None:
    if not child_session_id or not child_subagent_id:
        return
    with _lock:
        ours = child_subagent_id in _runs
        if ours:
            _by_child_session[child_session_id] = child_subagent_id
        else:
            _started_sessions[child_subagent_id] = child_session_id
            if len(_started_sessions) > 200:
                _started_sessions.pop(next(iter(_started_sessions)))
    if ours:
        _mark_children(child_session_id, child_subagent_id)


def subagent_stop(child_session_id: str = "", child_status: str = "", child_summary: Any = "", **_: Any) -> None:
    found = _run_for(session_id=str(child_session_id or ""))
    if found is None:
        return
    sid, run = found
    if run.get("done"):
        return
    with _lock:
        run["done"] = True
    try:
        rt = Runtime()
        _finish_failure(rt, run["task_id"], run["run_id"],
                        f"research agent ended ({child_status or 'unknown'}) without submitting")
        _persist(rt)
    except Exception:  # noqa: BLE001 - the stale-claim sweep recovers it
        pass


def pre_llm_call(session_id: str = "", **_: Any):
    if not session_id:
        return None
    try:
        rt = Runtime()
        with _lock:
            notices = rt.ctx.state.get("notices", default={}) or {}
            items = notices.pop(session_id, None)
            if items:
                rt.ctx.state.set("notices", notices)
    except Exception:  # noqa: BLE001
        return None
    if not items:
        return None
    return {"context": "[Alchemy Task] " + " ".join(items)}


# ------------------------------------------------------------------ recovery

def recover(rt: Runtime, *, limit: int = 3, wait_seconds: float = 300) -> dict[str, Any]:
    """Launch research for queued tasks (pending, or a stale running claim) and wait for them."""
    store = rt.store()
    queued = [t for t in store.scan().tasks if rs.eligibility(t.fm) == "eligible"]
    queued.sort(key=lambda t: str((rs.state(t.fm) or {}).get("updated") or ""))
    started, errors = [], []
    for doc in queued[: max(1, min(limit, 8))]:
        try:
            result = launch(rt, doc.task_id)
        except (rs.ResearchError, NeedsInput, tf.TaskFormatError, tf.ConcurrentEditError, OSError) as exc:
            result = {"started": False, "error": str(exc)[:300]}
        (started if result.get("started") else errors).append({"task_id": doc.task_id, "title": doc.title,
                                                               **({"error": result.get("error")} if
                                                                  not result.get("started") else {})})
        if result.get("started"):
            started[-1]["handle"] = result["handle"]
    deadline = time.time() + max(0.0, wait_seconds)
    for item in started:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            rt.ctx.subagent_lifecycle.wait(item.pop("handle"), timeout_seconds=remaining)
        except Exception:  # noqa: BLE001 - outcome is recorded by submit or subagent_stop
            pass
    for item in started:
        item.pop("handle", None)
        try:
            doc = store.resolve(item["task_id"])
            item["research"] = (rs.state(tf.parse_file(doc.path, rt=False).fm) or {}).get("status")
        except (NeedsInput, tf.TaskFormatError, OSError):
            item["research"] = "unknown"
    return {"queued": len(queued), "started": started, "errors": errors}


def request_again(rt: Runtime, ref: str, origin_session: str = "") -> dict[str, Any]:
    store = rt.store()
    doc = store.resolve(ref)
    if rs.eligibility(doc.fm) in ("closed", "unsupported", "no_id"):
        raise rs.ResearchError(f"cannot research this task ({rs.eligibility(doc.fm)}); reopen it or fix it first")
    with task_lock(rt.data_dir, doc.task_id, doc.path):
        doc = tf.parse_file(doc.path)
        rs.request(doc.fm, "user asked to research again")
        body = tf.append_log(doc.body, "Research requested again.", rt.settings.today())
        tf.atomic_write(doc.path, tf.render(doc.fm, body, seq_offset=doc.seq_offset,
                                            keep_blank=doc.blank_keys).encode(), expect=doc.raw)
    return launch(rt, doc.task_id, origin_session=origin_session)


# ------------------------------------------------------------------ research-agent tools

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_ENV_IN_TEXT = re.compile(r"\b[A-Z][A-Z0-9]*_(?:[A-Z0-9]+_)*(?:API_KEY|KEY|TOKEN|SECRET|PASSWORD|PAT|ID|"
                          r"CREDENTIALS?)\b")
_ACCESS_WORDS = re.compile(r"\b(api[ -]?keys?|tokens?|credentials?|oauth|log ?in|sign ?in|password|"
                           r"service account|access key|secret key|env(?:ironment)? var(?:iable)?s?)\b", re.I)


def _env_names(requirements: Any) -> list[str]:
    """Environment variable NAMES from Hermes's registry metadata. Anything not shaped like a name is dropped,
    so a value can never be echoed even if a registry entry is malformed."""
    items = requirements if isinstance(requirements, (list, tuple, set)) else []
    out: list[str] = []
    for item in items:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and _ENV_NAME.match(name) and name not in out:
            out.append(name)
    return out[:20]


def _skill_access_hints(rt: Runtime, limit: int = 60) -> list[dict[str, Any]]:
    """Skills whose name or description mentions keys, logins or accounts (hints, from the listing text only)."""
    try:
        skills = json.loads(str(rt.ctx.dispatch_tool("skills_list", {})))["skills"]
    except Exception:  # noqa: BLE001 - hints are optional
        return []
    hints = []
    for s in skills if isinstance(skills, list) else []:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        text = f"{s.get('name')} {s.get('description') or ''}"
        mentions = list(dict.fromkeys(_ENV_IN_TEXT.findall(text) + [m.lower() for m in _ACCESS_WORDS.findall(text)]))
        if mentions:
            hints.append({"skill": str(s["name"]), "mentions": mentions[:8]})
        if len(hints) >= limit:
            break
    return hints


def _inventory(rt: Runtime, refresh: bool) -> dict[str, Any]:
    cached = None if refresh else rt.ctx.state.get("inventory", default=None)
    if cached and time.time() - float(cached.get("at") or 0) < INVENTORY_TTL:
        return {**cached["data"], "cached_minutes_ago": int((time.time() - cached["at"]) / 60)}
    toolsets = _registry_toolsets()
    skip = {RESEARCH_TOOLSET}
    out_sets, mcp, missing = [], [], []
    for name, meta in sorted(toolsets.items()):
        if name in skip:
            continue
        tools = sorted(meta.get("tools") or [])
        entry = {"toolset": name, "available": bool(meta.get("available")), "tools": tools[:25]}
        if not meta.get("available"):
            needs = _env_names(meta.get("requirements"))
            if needs:
                entry["needs_env"] = needs
            missing.append({"toolset": name, **({"needs_env": needs} if needs else {})})
        (mcp if name.startswith("mcp-") else out_sets).append(entry)
    data = {"toolsets": out_sets,
            "mcp_servers": [{"server": m["toolset"][4:], "available": m["available"], "tools": m["tools"],
                             **({"needs_env": m["needs_env"]} if m.get("needs_env") else {})} for m in mcp],
            "missing_access": missing,
            "skill_access_hints": _skill_access_hints(rt),
            "note": "Names only, never values. missing_access lists toolsets Hermes reports as unusable and the "
                    "environment variable names Hermes says they need. skill_access_hints are skills whose text "
                    "mentions keys, logins or accounts; read them with research_skill_view to learn how the user "
                    "reaches those systems. Hosted connectors and browser profiles are not listed here."}
    rt.ctx.state.set("inventory", {"at": time.time(), "data": data})
    return {**data, "cached_minutes_ago": 0}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


SKILLS_PAGE_CHARS = 12000      # JSON budget per page, well under the tool-result cap
SKILL_DESC_CHARS = 1500        # longer descriptions are shortened (marked) so one entry always fits a page
SKILL_VIEW_CHARS = 30000       # longer skill_view results are paged by offset, never cut silently


def _page_arg(args: dict[str, Any]) -> int:
    try:
        return max(1, int(args.get("page") or 1))
    except (TypeError, ValueError):
        return 1


def _skill_pages(skills: list[Any]) -> list[list[dict[str, str]]]:
    """Pack compact entries into pages by size; an entry is never split across pages."""
    pages: list[list[dict[str, str]]] = [[]]
    used = 0
    for s in skills:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        desc = str(s.get("description") or "")
        if len(desc) > SKILL_DESC_CHARS:
            desc = desc[:SKILL_DESC_CHARS] + " [shortened; skill_view has the full text]"
        entry = {"name": str(s["name"]), "category": str(s.get("category") or ""), "description": desc}
        size = len(_json(entry)) + 2
        if pages[-1] and used + size > SKILLS_PAGE_CHARS:
            pages.append([])
            used = 0
        pages[-1].append(entry)
        used += size
    return pages


def t_skills_list(args: dict[str, Any] | None = None, **_: Any) -> str:
    """The user's complete skills listing, paged. Every skill appears on exactly one page."""
    args = args or {}
    rt = Runtime()
    page = _page_arg(args)
    call = {"category": str(args["category"])} if args.get("category") else {}
    raw = str(rt.ctx.dispatch_tool("skills_list", call))
    try:
        listing = json.loads(raw)
        skills = listing["skills"]
        assert isinstance(skills, list)
    except Exception:  # noqa: BLE001 - not the expected JSON; page the raw text instead of cutting it
        size = SKILLS_PAGE_CHARS
        pages = max(1, -(-len(raw) // size))
        return _json({"ok": True, "page": page, "pages": pages, "raw": raw[(page - 1) * size:page * size],
                      "next_page": page + 1 if page < pages else None,
                      "hint": "Listing was not in the usual format; call again with next_page until it is null."})
    pages = _skill_pages(skills)
    total = sum(len(p) for p in pages)
    out = {"ok": True, "page": page, "pages": len(pages), "total": total,
           "skills": pages[page - 1] if page <= len(pages) else [],
           "next_page": page + 1 if page < len(pages) else None}
    if page == 1 and isinstance(listing.get("categories"), list):
        out["categories"] = listing["categories"]
    out["hint"] = (f"Page {page} of {len(pages)}. Call again with page={page + 1} until next_page is null; "
                   "then use research_skill_view for full skills and their reference files."
                   if out["next_page"] else
                   f"Last page ({len(pages)} pages, {total} skills). Use research_skill_view to read skills and "
                   "their reference files.")
    return _json(out)


def t_skill_view(args: dict[str, Any] | None = None, **_: Any) -> str:
    args = args or {}
    rt = Runtime()
    call = {"name": str(args.get("name") or "")}
    if args.get("file_path"):
        call["file_path"] = str(args["file_path"])
    raw = str(rt.ctx.dispatch_tool("skill_view", call))
    if len(raw) <= SKILL_VIEW_CHARS and not args.get("offset"):
        return raw
    try:
        offset = max(0, int(args.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    end = offset + SKILL_VIEW_CHARS
    return _json({"ok": True, "total_chars": len(raw), "offset": offset, "content": raw[offset:end],
                  "next_offset": end if end < len(raw) else None,
                  "hint": "Long result: call again with offset=next_offset until it is null."})


def t_capabilities(args: dict[str, Any] | None = None, **_: Any) -> str:
    rt = Runtime()
    try:
        return _json({"ok": True, **_inventory(rt, bool((args or {}).get("refresh")))})
    except Exception as exc:  # noqa: BLE001
        return _json({"ok": False, "error": f"inventory unavailable: {exc}"})


def t_submit(args: dict[str, Any] | None = None, task_id: str = "", **_: Any) -> str:
    args = dict(args or {})
    run_id = str(args.pop("run_id", "") or "")
    try:
        result = submit(Runtime(), run_id, args, caller_task_id=str(task_id or ""))
        return _json({"ok": True, "message": "Saved. Your work is done; stop now.", **result})
    except (rs.ResearchError, NeedsInput, tf.TaskFormatError) as exc:
        return _json({"ok": False, "error": str(exc)})
    except tf.ConcurrentEditError:
        return _json({"ok": False, "error": "the task was being edited; call research_submit again"})


_STRS = {"type": "array", "items": {"type": "string"}}
RESEARCH_TOOLS = (
    ({"name": "research_skills_list", "description": "Alchemy Task research agents only: the user's complete "
      "skills listing (name, category, description), read-only and paged. Returns page, pages, total and "
      "next_page; keep calling with page=next_page until next_page is null so you see every skill.",
      "parameters": {"type": "object", "properties": {
          "page": {"type": "integer", "minimum": 1, "description": "Page to read, starting at 1."},
          "category": {"type": "string", "description": "Optional: only skills in this category."}}}},
     t_skills_list),
    ({"name": "research_skill_view", "description": "Alchemy Task research agents only: read one skill, or one of "
      "its linked reference files with file_path (read-only).", "parameters": {"type": "object", "properties": {
          "name": {"type": "string"},
          "file_path": {"type": "string", "description": "Optional linked file inside the skill, for example "
                                                         "references/api.md, as listed in the skill's linked files."},
          "offset": {"type": "integer", "minimum": 0, "description": "Only for long results: continue from "
                                                                     "the next_offset you were given."}},
          "required": ["name"]}}, t_skill_view),
    ({"name": "research_capabilities", "description": "Alchemy Task research agents only: names of the toolsets, "
      "tools and MCP servers this Hermes has, whether each is usable, missing_access (unusable toolsets with the "
      "environment variable names they need, never values) and skill_access_hints (skills that mention keys or "
      "logins). Cached for an hour; pass refresh=true before reporting anything as missing.", "parameters": {"type": "object", "properties": {
          "refresh": {"type": "boolean"}}}}, t_capabilities),
    ({"name": "research_submit", "description": "Alchemy Task research agents only: submit the research result "
      "once, then stop.", "parameters": {"type": "object", "properties": {
          "run_id": {"type": "string"},
          "summary": {"type": "string", "description": "One or two plain sentences on what the task is and why it "
                                                    "matters; used only if the task has no summary yet."},
          "recommended_approach": {**_STRS, "description": "Concrete steps Hermes should take, citing skills/tools."},
          "useful_context": _STRS,
          "dependencies_and_risks": _STRS,
          "open_questions": {**_STRS, "description": "Only questions the task text does not answer."},
          "execution": {"type": "string", "enum": list(rs.EXECUTION)},
          "access_plan": {"type": "array", "items": {"type": "object", "properties": {
              "need": {"type": "string", "description": "What access or tool is needed"},
              "status": {"type": "string", "enum": list(rs.ACCESS_STATUS)},
              "via": {"type": "string", "description": "Which tool, skill or MCP server provides it"},
              "setup": {"type": "string", "description": "How to set it up, with any cost"}},
              "required": ["need", "status"]}},
          "skills_used": {**_STRS, "description": "Names of the user's skills that apply."},
          "fill": {"type": "object", "description": "Written after the research, from its findings, only for the "
                   "sections your context lists under Sections to fill. Plain text, no headings or markers.",
                   "properties": {
                       "summary": {"type": "string", "description": "One or two plain sentences."},
                       "notes": {"type": "string", "description": "2 to 4 sentences of background context; "
                                                                  "not a repeat of the dossier."},
                       "plan": {**_STRS, "minItems": rs.PLAN_MIN, "maxItems": rs.PLAN_MAX,
                                "description": "3 to 7 ordered steps."},
                       "subtasks": {**_STRS, "description": "Checklist items, only when the task needs more "
                                                            "than one sitting or step."},
                       "subtasks_skipped_reason": {"type": "string", "description": "Why no subtasks (for "
                                                                                   "example: one sitting)."}}},
          "sources": {"type": "array", "items": {"type": "object", "properties": {
              "title": {"type": "string"}, "url": {"type": "string"}, "relevance": {"type": "string"}},
              "required": ["url"]}}},
          "required": ["run_id", "execution", "recommended_approach"]}}, t_submit),
) + research_git.TOOLS


def register(ctx: Any) -> None:
    for schema, handler in RESEARCH_TOOLS:
        ctx.register_tool(name=schema["name"], toolset=RESEARCH_TOOLSET, schema=schema, handler=handler,
                          description=schema["description"], emoji="⚗️")
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("subagent_start", subagent_start)
    ctx.register_hook("subagent_stop", subagent_stop)
    ctx.register_hook("pre_llm_call", pre_llm_call)


# ------------------------------------------------------------------ queue without launching (Tasks view)

class ResearchBusy(rs.ResearchError):
    """Research for this task is already queued or running."""


def queue_research(rt: Runtime, ref: str, log: str = "Research requested.") -> tuple[Any, Path]:
    """Mark a task as waiting for research without launching a worker (the research sweep starts it).

    For callers with no agent turn, such as the dashboard: workers can only launch inside one. Refuses
    tasks already queued or running (``ResearchBusy``) and tasks that cannot be researched."""
    store = rt.store()
    doc = store.resolve(ref)
    with task_lock(rt.data_dir, doc.task_id, doc.path):
        doc = tf.parse_file(doc.path)
        why = rs.eligibility(doc.fm)
        if why in ("eligible", "running"):
            raise ResearchBusy("research is already queued or running for this task")
        if why in ("closed", "unsupported", "no_id", "unknown"):
            raise rs.ResearchError(f"cannot research this task ({why}); reopen it or fix it first")
        rs.request(doc.fm, "user asked in the Tasks view")
        body = tf.append_log(doc.body, log, rt.settings.today())
        tf.atomic_write(doc.path, tf.render(doc.fm, body, seq_offset=doc.seq_offset,
                                            keep_blank=doc.blank_keys).encode(), expect=doc.raw)
    return tf.parse_file(doc.path), doc.path
