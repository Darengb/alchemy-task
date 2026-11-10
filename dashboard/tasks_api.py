"""Task routes for the Tasks UI: list by date range, overdue, read, edit, complete, reopen, move, add.

Every write goes through the same store methods and Git delivery the agent tools use, so a change made in
the UI is committed, pushed and logged exactly like one made in chat.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Request

from ..core import taskfile as tf
from ..core.store import NeedsInput
from .ui_common import UIError, handle, runtime

router = APIRouter()

ROW_LIMIT = 1500


def _row(store: Any, doc: tf.TaskDoc, *, body: bool = False) -> dict[str, Any]:
    out = store.summary(doc, include_body=False)
    out["revision"] = tf.content_hash(doc.raw)
    out["date"] = out.get("scheduled") or out.get("due")
    if body:
        out["body"] = doc.body
    return out


def _date(value: Any, name: str) -> str:
    v = tf.validate_date(value, name)
    if not v:
        raise UIError("invalid_request", f"{name} must be a date (YYYY-MM-DD)")
    return v


def _doc(store: Any, task_id: str) -> tf.TaskDoc:
    if not tf.valid_task_id(task_id):
        raise UIError("not_found", "Unknown task", 404)
    docs = store.find(task_id=task_id, status="any")
    if not docs:
        raise UIError("not_found", "This task is no longer there. It may have been moved or deleted.", 404)
    return docs[0]


def _deliver(rt: Any, paths: list[str], message: str) -> dict[str, Any] | None:
    if not paths:
        return None
    try:
        return rt.git().deliver(paths, message)
    except Exception as exc:  # noqa: BLE001 - the file is saved; Git problems are reported, not fatal
        return {"committed": False, "pushed": False, "state": "error", "error": f"{exc.__class__.__name__}: {exc}"}


def _area_ok(rt: Any, area: str) -> str:
    if area and area not in rt.settings.known_areas():
        raise UIError("area", f"{area!r} is not a known area.")
    return area


# ------------------------------------------------------------------ reads

@router.get("/meta")
async def meta(request: Request):
    def run() -> dict[str, Any]:
        rt = runtime()
        s = rt.settings
        streams: dict[str, list[str]] = {}
        try:
            from .. import discovery
            streams = {name: list(v.get("areas") or []) for name, v in discovery._streams(rt).items()}
        except Exception:  # noqa: BLE001 - discovery is optional for the task views
            streams = {}
        return {"ok": True, "today": s.today(), "configured": bool(s.configured), "timezone": s.timezone or None,
                "areas": s.known_areas() if s.configured else [], "default_area": s.default_area or None,
                "streams": streams}
    return await handle(request, run)


@router.get("/tasks")
async def tasks(request: Request):
    q = request.query_params

    def run() -> dict[str, Any]:
        start = _date(q.get("from"), "from")
        end = _date(q.get("to") or start, "to")
        if end < start:
            start, end = end, start
        if (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days > 200:
            raise UIError("invalid_request", "Ask for at most 200 days at a time")
        include_done = q.get("include_done") in ("1", "true", "yes")
        area = (q.get("area") or "").strip().lower()
        rt = runtime()
        store = rt.store()
        out = []
        for doc in store.scan().tasks:
            fm = doc.fm
            day = tf.norm_date(fm.get("scheduled")) or tf.norm_date(fm.get("due"))
            if not day or not (start <= day <= end):
                continue
            if doc.is_closed and not include_done:
                continue
            if area and str(fm.get("area") or store.area_of(doc.path) or "") != area:
                continue
            out.append(_row(store, doc))
            if len(out) >= ROW_LIMIT:
                break
        return {"ok": True, "today": rt.settings.today(), "from": start, "to": end, "tasks": out}
    return await handle(request, run)


@router.get("/overdue")
async def overdue(request: Request):
    q = request.query_params

    def run() -> dict[str, Any]:
        rt = runtime()
        store = rt.store()
        today = rt.settings.today()
        area = (q.get("area") or "").strip().lower()
        out = []
        for doc in store.scan().tasks:
            if doc.is_closed:
                continue
            day = tf.norm_date(doc.fm.get("scheduled")) or tf.norm_date(doc.fm.get("due"))
            if not day or day >= today:
                continue
            if area and str(doc.fm.get("area") or store.area_of(doc.path) or "") != area:
                continue
            out.append(_row(store, doc))
        out.sort(key=lambda t: t["date"], reverse=True)
        return {"ok": True, "today": today, "count": len(out), "tasks": out[:ROW_LIMIT]}
    return await handle(request, run)


@router.get("/tasks/{task_id}")
async def task(request: Request, task_id: str):
    def run() -> dict[str, Any]:
        rt = runtime()
        store = rt.store()
        return {"ok": True, "task": _row(store, _doc(store, task_id), body=True)}
    return await handle(request, run)


# ------------------------------------------------------------------ writes

PATCH_FIELDS = {"date", "due", "scheduled", "keep_separate", "title", "summary", "priority", "area", "status",
                "reason", "expected_revision"}


def _update(task_id: str, changes: dict[str, Any], log: str, *, expect: str | None = None) -> dict[str, Any]:
    rt = runtime()
    store = rt.store()
    doc = _doc(store, task_id)
    if changes.get("area"):
        _area_ok(rt, str(changes["area"]).strip().lower())
    new, paths, notes = store.update(doc.task_id, {**changes, "log": log}, expect_revision=expect)
    receipt = _deliver(rt, paths, f"task: update {new.title[:72]}")
    return {"ok": True, "task": _row(store, new, body=True), "changed": bool(paths), "changes": notes, "git": receipt}


@router.patch("/tasks/{task_id}")
async def patch_task(request: Request, task_id: str):
    def run(body: dict[str, Any]) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if body.get("date"):
            day = _date(body["date"], "date")
            changes.update(due=day, scheduled=day)  # one date moves both (Daren's rule for dragging and pickers)
        elif body.get("keep_separate"):
            for key in ("due", "scheduled"):
                if body.get(key):
                    changes[key] = _date(body[key], key)
            changes["keep_separate"] = True
        for key in ("title", "summary", "priority", "area", "reason"):
            if key in body and body[key] is not None:
                changes[key] = str(body[key])
        if body.get("status"):
            status = str(body["status"]).strip().lower()
            if status not in ("open", "in-progress", "waiting"):
                raise UIError("invalid_request", "Use complete or reopen for done; cancel from chat")
            changes["status"] = status
            if status == "waiting" and not changes.get("reason"):
                changes["reason"] = "Marked waiting in the Tasks view"
        if not changes:
            raise UIError("invalid_request", "Nothing to change")
        what = "Moved" if body.get("date") else "Changed"
        return _update(task_id, changes, f"{what} in the Tasks view.", expect=body.get("expected_revision") or None)
    return await handle(request, run, PATCH_FIELDS)


@router.post("/tasks/{task_id}/complete")
async def complete(request: Request, task_id: str):
    def run(_: dict[str, Any]) -> dict[str, Any]:
        return _update(task_id, {"status": "done"}, "Marked done in the Tasks view.")
    return await handle(request, run, set())


@router.post("/tasks/{task_id}/reopen")
async def reopen(request: Request, task_id: str):
    def run(_: dict[str, Any]) -> dict[str, Any]:
        return _update(task_id, {"status": "open", "reopen": True}, "Reopened in the Tasks view.")
    return await handle(request, run, set())


@router.put("/tasks/{task_id}/body")
async def put_body(request: Request, task_id: str):
    def run(body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body.get("body"), str):
            raise UIError("invalid_request", "body must be text")
        rt = runtime()
        store = rt.store()
        doc = _doc(store, task_id)
        new, paths = store.replace_body(doc.task_id, body["body"], expect_revision=body.get("expected_revision") or None)
        receipt = _deliver(rt, paths, f"task: edit notes {new.title[:64]}")
        return {"ok": True, "task": _row(store, new, body=True), "changed": bool(paths), "git": receipt}
    return await handle(request, run, {"body", "expected_revision"})


@router.post("/tasks")
async def create(request: Request):
    def run(body: dict[str, Any]) -> dict[str, Any]:
        title = " ".join(str(body.get("title") or "").split())
        if not title:
            raise UIError("title", "A task needs a title.")
        rt = runtime()
        store = rt.store()
        day = _date(body.get("date") or rt.settings.today(), "date")
        area = _area_ok(rt, str(body.get("area") or "").strip().lower())
        try:
            doc = store.create(title=title, area=area, due=day, summary=str(body.get("summary") or ""),
                               source="Tasks view", confirm_new=True)
        except NeedsInput as exc:
            if exc.kind == "area":
                raise UIError("needs_area", "Pick an area first.") from exc
            raise
        receipt = _deliver(rt, [store.rel(doc.path)], f"task: create {doc.title[:72]}")
        research = (doc.fm.get("enrichment") or {}).get("status")
        if research == "pending":
            try:
                from .. import research_agent
                research_agent.on_task_created(rt, doc, "")
            except Exception:  # noqa: BLE001 - the research sweep picks up pending tasks later
                pass
        return {"ok": True, "task": _row(store, tf.parse_file(doc.path), body=True), "git": receipt}
    return await handle(request, run, {"title", "date", "area", "summary"})


# ------------------------------------------------------------------ research button

SWEEP_INTERVAL = "within 30 minutes"


def _background(fn: Any) -> None:
    import threading
    threading.Thread(target=fn, name="alchemy-task-research-sweep", daemon=True).start()


def _start_sweep(rt: Any) -> bool:
    """Fire the research sweep job now through Hermes's public ``cronjob_manage`` tool (action ``run``),
    the same way the discovery "Run now" button fires its job. Returns False when there is no sweep job.

    A dashboard request has no agent turn, so research workers cannot launch here, and ``run`` from a
    dashboard request executes the job in this process for minutes. It runs on a background thread so the
    button answers at once; if it fails, the task stays queued and the scheduled sweep starts it."""
    reg = (rt.ctx.state.get("jobs", default={}) or {}).get("research-sweep") or {}
    job_id = reg.get("job_id")
    if not job_id:
        return False

    def fire() -> None:
        try:
            rt.ctx.dispatch_tool("cronjob_manage", {"action": "run", "job_id": job_id})
        except Exception:  # noqa: BLE001 - the task stays queued; the scheduled sweep picks it up
            pass

    try:
        _background(fire)
    except Exception:  # noqa: BLE001 - same fallback as above
        return False
    return True


@router.post("/tasks/{task_id}/research")
async def research(request: Request, task_id: str):
    """Queue research for a task (start, retry or refresh). Workers only launch inside an agent turn, so
    this marks the task waiting and starts the research sweep job now when one is set up."""
    def run(_: dict[str, Any]) -> dict[str, Any]:
        from .. import research_agent as ra
        from ..core import research as rs
        rt = runtime()
        store = rt.store()
        doc = _doc(store, task_id)
        try:
            new, path = ra.queue_research(rt, doc.task_id, "Research requested in the Tasks view.")
        except ra.ResearchBusy as exc:
            raise UIError("research_busy", "Research is already queued or running for this task.", 409) from exc
        except rs.ResearchError as exc:
            raise UIError("invalid_request", str(exc)) from exc
        receipt = _deliver(rt, [store.rel(path)], f"task: research {new.title[:64]}")
        now = _start_sweep(rt)
        return {"ok": True, "queued": True, "starts": "now" if now else SWEEP_INTERVAL,
                "message": "Starting now" if now else f"Queued, starts {SWEEP_INTERVAL}",
                "task": _row(store, new, body=True), "git": receipt}
    return await handle(request, run, set())


# ------------------------------------------------------------------ send to chat

@router.post("/tasks/{task_id}/handoff")
async def handoff(request: Request, task_id: str):
    """Send the task to chat. ``surface`` desktop returns the note for the desktop app to send in a new chat;
    anything else queues it for the messaging gateway, which hands it to the agent in a chat."""
    def run(body: dict[str, Any]) -> dict[str, Any]:
        from .. import handoff as ho
        surface = str(body.get("surface") or "dashboard")
        if surface not in ho.SURFACES:
            raise UIError("invalid_request", "surface must be dashboard, phone or desktop")
        rt = runtime()
        store = rt.store()
        doc = _doc(store, task_id)
        task = store.summary(doc)
        if surface == "desktop":
            return {"ok": True, "mode": "desktop", "text": ho.build_text(task, surface)}
        return {"ok": True, "mode": "chat", "handoff": ho.request(rt, task, surface)}
    return await handle(request, run, {"surface"})


@router.get("/handoffs/{handoff_id}")
async def handoff_status(request: Request, handoff_id: str):
    def run() -> dict[str, Any]:
        from .. import handoff as ho
        return {"ok": True, "handoff": ho.status(runtime(), handoff_id)}
    return await handle(request, run)
