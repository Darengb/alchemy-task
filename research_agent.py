"""Background research: launch, research-agent tools, budget and failure hooks,
recovery and the "research finished" notice.

Research runs as a Hermes subagent started through the public
``ctx.subagent_lifecycle`` API, restricted to the ``web`` toolset plus this
plugin's read-only research toolset. Only ``research_submit`` writes, and it
writes only the plugin's own dossier block and enrichment state.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from .core import research as rs
from .core import taskfile as tf
from .core.locks import task_lock
from .core.store import NeedsInput
from .runtime import Runtime

RESEARCH_TOOLSET = "alchemy-task-research"
CALL_BUDGET = 30
TIME_BUDGET = 10 * 60
INVENTORY_TTL = 3600

_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}      # subagent_id -> run
_by_child_session: dict[str, str] = {}      # child session id -> subagent_id
_started_sessions: dict[str, str] = {}      # subagent_id -> child session id (subagent_start can precede launch's return)


# ------------------------------------------------------------------ run registry

def _persist(rt: Runtime) -> None:
    try:
        rt.ctx.state.set("research_runs", {k: v for k, v in _runs.items() if not v.get("done")})
    except Exception:  # noqa: BLE001 - registry is an optimisation; task files hold the truth
        pass


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
    goal, context = rs.goal_text(run_id=run_id, title=doc.title, fields=fields, body=rs.strip_managed(doc.body),
                                 linked=_linked_notes(rt, doc.body), today=rt.settings.today())
    try:
        handle = rt.ctx.subagent_lifecycle.launch(_make_request(
            goal=goal, context=context, role="leaf", allowed_toolsets=("web", RESEARCH_TOOLSET),
            correlation_id=f"alchemy-task:{doc.task_id}:{run_id}"))
        handle = dict(handle) if not hasattr(handle, "to_dict") else handle.to_dict()
    except Exception as exc:  # noqa: BLE001 - recovery retries later
        _finish_failure(rt, doc.task_id, run_id, f"could not start research: {exc}")
        return {"started": False, "error": str(exc)[:300], "task_id": doc.task_id}
    with _lock:
        sid = handle["subagent_id"]
        _runs[sid] = {"task_id": doc.task_id, "run_id": run_id, "started": time.time(),
                      "calls": 0, "origin_session": origin_session, "title": doc.title, "handle": handle}
        if sid in _started_sessions:
            _by_child_session[_started_sessions.pop(sid)] = sid
        for old in [k for k, v in _runs.items() if v.get("done") and time.time() - v["started"] > 3600]:
            _runs.pop(old, None)
    _persist(rt)
    return {"started": True, "task_id": doc.task_id, "run_id": run_id, "subagent_id": handle["subagent_id"],
            "handle": handle}


def on_task_created(rt: Runtime, doc: Any, origin_session: str = "") -> None:
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
        if not doc.fm.get("summary") and normalized.get("summary"):  # fill a missing summary, never replace one
            if "summary" in doc.fm:
                doc.fm["summary"] = normalized["summary"]
            else:
                doc.fm.insert(1, "summary", normalized["summary"])
        body = tf.append_log(body, rs.summary_line(normalized), rt.settings.today())
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
    found = _run_for(task_id=str(task_id or ""))
    if found is None:
        return None
    sid, run = found
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
        if child_subagent_id in _runs:
            _by_child_session[child_session_id] = child_subagent_id
        else:
            _started_sessions[child_subagent_id] = child_session_id
            if len(_started_sessions) > 200:
                _started_sessions.pop(next(iter(_started_sessions)))


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

def _inventory(rt: Runtime, refresh: bool) -> dict[str, Any]:
    cached = None if refresh else rt.ctx.state.get("inventory", default=None)
    if cached and time.time() - float(cached.get("at") or 0) < INVENTORY_TTL:
        return {**cached["data"], "cached_minutes_ago": int((time.time() - cached["at"]) / 60)}
    toolsets = _registry_toolsets()
    skip = {RESEARCH_TOOLSET}
    out_sets, mcp = [], []
    for name, meta in sorted(toolsets.items()):
        if name in skip:
            continue
        tools = sorted(meta.get("tools") or [])
        entry = {"toolset": name, "available": bool(meta.get("available")), "tools": tools[:25]}
        if not meta.get("available") and meta.get("requirements"):
            entry["needs_env"] = sorted(meta["requirements"])[:5] if isinstance(meta["requirements"], (list, set,
                                                                                              tuple)) else []
        (mcp if name.startswith("mcp-") else out_sets).append(entry)
    data = {"toolsets": out_sets, "mcp_servers": [{"server": m["toolset"][4:], "available": m["available"],
                                                   "tools": m["tools"]} for m in mcp],
            "note": "Names only. Hosted connectors, API keys and browser profiles are not listed here; "
                    "check skills for how the user reaches those systems."}
    rt.ctx.state.set("inventory", {"at": time.time(), "data": data})
    return {**data, "cached_minutes_ago": 0}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def t_skills_list(args: dict[str, Any] | None = None, **_: Any) -> str:
    rt = Runtime()
    return str(rt.ctx.dispatch_tool("skills_list", {}))[:20000]


def t_skill_view(args: dict[str, Any] | None = None, **_: Any) -> str:
    args = args or {}
    rt = Runtime()
    call = {"name": str(args.get("name") or "")}
    if args.get("file_path"):
        call["file_path"] = str(args["file_path"])
    return str(rt.ctx.dispatch_tool("skill_view", call))[:30000]


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
    ({"name": "research_skills_list", "description": "Alchemy Task research agents only: list the user's skills "
      "(read-only).", "parameters": {"type": "object", "properties": {}}}, t_skills_list),
    ({"name": "research_skill_view", "description": "Alchemy Task research agents only: read one skill or one of "
      "its files (read-only).", "parameters": {"type": "object", "properties": {
          "name": {"type": "string"}, "file_path": {"type": "string"}}, "required": ["name"]}}, t_skill_view),
    ({"name": "research_capabilities", "description": "Alchemy Task research agents only: names of the toolsets, "
      "tools and MCP servers this Hermes has, and whether each is usable. Cached for an hour; pass refresh=true "
      "before reporting anything as missing.", "parameters": {"type": "object", "properties": {
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
          "sources": {"type": "array", "items": {"type": "object", "properties": {
              "title": {"type": "string"}, "url": {"type": "string"}, "relevance": {"type": "string"}},
              "required": ["url"]}}},
          "required": ["run_id", "execution", "recommended_approach"]}}, t_submit),
)


def register(ctx: Any) -> None:
    for schema, handler in RESEARCH_TOOLS:
        ctx.register_tool(name=schema["name"], toolset=RESEARCH_TOOLSET, schema=schema, handler=handler,
                          description=schema["description"], emoji="⚗️")
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("subagent_start", subagent_start)
    ctx.register_hook("subagent_stop", subagent_stop)
    ctx.register_hook("pre_llm_call", pre_llm_call)
