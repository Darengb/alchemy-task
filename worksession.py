"""Official work sessions: "work on X" / "continue X", task_checkpoint, and the safety net.

A session is linked to one task when the agent calls ``task_work_start``. The
agent then checkpoints when work finishes, needs the user or is blocked. If a
linked session ends or goes idle without a checkpoint after its last activity,
the plugin writes one itself from the transcript (``ctx.llm``), or a free
mechanical digest when no model call is available. Automatic checkpoints never
mark a task done.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from typing import Any

from .core import checkpoint as ck
from .core import research as rs
from .core import taskfile as tf
from .core.locks import task_lock
from .core.store import NeedsInput, current_state_text
from .runtime import Runtime

IDLE_SECONDS = 30 * 60
SWEEP_SECONDS = 10 * 60
GRACE_SECONDS = 120  # the rest of the turn that wrote a checkpoint counts as covered
_lock = threading.Lock()
_sweeper: threading.Thread | None = None
_stop = threading.Event()


# ------------------------------------------------------------------ link registry (ctx.state "links")

def _links(rt: Runtime) -> dict[str, dict[str, Any]]:
    return rt.ctx.state.get("links", default={}) or {}


def _update_link(rt: Runtime, session_id: str, **fields: Any) -> dict[str, Any] | None:
    with _lock:
        links = _links(rt)
        if fields.get("_delete"):
            links.pop(session_id, None)
            rt.ctx.state.set("links", links)
            return None
        link = links.get(session_id)
        if link is None and "task_id" not in fields:
            return None
        link = {**(link or {}), **fields}
        links[session_id] = link
        if len(links) > 200:  # forget the oldest links
            for sid in sorted(links, key=lambda s: links[s].get("last_activity", 0))[: len(links) - 200]:
                links.pop(sid, None)
        rt.ctx.state.set("links", links)
        return link


def linked_task(rt: Runtime, session_id: str) -> str | None:
    link = _links(rt).get(session_id or "")
    return link.get("task_id") if link else None


# ------------------------------------------------------------------ start / continue

def start_work(rt: Runtime, ref: str, session_id: str) -> dict[str, Any]:
    store = rt.store()
    doc = store.resolve(ref)
    ok, why = tf.writable(doc.fm)
    if not ok:
        raise NeedsInput("unsupported", f"This task cannot be edited by Alchemy Task: {why}.")
    if doc.is_closed:
        raise NeedsInput("reopen", f"This task is {doc.status}. Reopen it with task_update (reopen=true) first if "
                         "the user wants to work on it again.")
    resumed = bool(current_state_text(doc.body))
    paths: list[str] = []
    with task_lock(rt.data_dir, doc.task_id, doc.path):
        doc = tf.parse_file(doc.path)
        if str(doc.fm.get("status") or "").lower() != "in-progress":
            doc.fm["status"] = "in-progress"
        label = "Work resumed" if resumed else "Work started"
        body = tf.append_log(doc.body, f"{label} (session {session_id[:24] or 'unknown'}).", rt.settings.today())
        tf.atomic_write(doc.path, tf.render(doc.fm, body, seq_offset=doc.seq_offset,
                                            keep_blank=doc.blank_keys).encode(), expect=doc.raw)
        paths.append(store.rel(doc.path))
    receipt = rt.git().deliver(paths, f"task: start work {doc.title[:64]}")
    now = time.time()
    if session_id:
        _update_link(rt, session_id, task_id=doc.task_id, title=doc.title, started=now, last_activity=now,
                     last_checkpoint=0)
    _ensure_sweeper(rt)
    fresh = tf.parse_file(doc.path, rt=False)
    research = rs.state(fresh.fm) or {}
    return {"task": store.summary(fresh, include_body=True), "resumed": resumed, "git": receipt,
            "research": research.get("status") or "none", "linked_session": bool(session_id)}


# ------------------------------------------------------------------ checkpoint

def write_checkpoint(rt: Runtime, ref: str, fields: dict[str, Any], *, automatic: bool = False,
                     session_id: str = "") -> dict[str, Any]:
    cp = ck.normalize(fields, automatic=automatic)
    store = rt.store()
    doc = store.resolve(ref)
    ok, why = tf.writable(doc.fm)
    if not ok:
        raise NeedsInput("unsupported", f"This task cannot be edited by Alchemy Task: {why}.")
    today = rt.settings.today()
    with task_lock(rt.data_dir, doc.task_id, doc.path):
        doc = tf.parse_file(doc.path)
        if automatic and doc.is_closed:
            return {"skipped": "task already closed"}
        block = ck.render(cp, day=today, automatic=automatic)
        body = tf.upsert_block(doc.body, tf.CURRENT_STATE_START, tf.CURRENT_STATE_END, block, top=True)
        ck.apply_status(doc.fm, cp, today)
        body = tf.append_log(body, ck.log_line(cp, automatic=automatic), today)
        tf.atomic_write(doc.path, tf.render(doc.fm, body, seq_offset=doc.seq_offset,
                                            keep_blank=doc.blank_keys).encode(), expect=doc.raw)
    receipt = rt.git().deliver([store.rel(doc.path)], f"task: {'auto ' if automatic else ''}checkpoint "
                                                      f"{doc.title[:60]}")
    if session_id:
        if cp["state"] == "done":
            _update_link(rt, session_id, _delete=True)
        else:
            _update_link(rt, session_id, last_checkpoint=time.time())
    return {"task": store.summary(tf.parse_file(doc.path, rt=False)), "state": cp["state"], "git": receipt,
            "automatic": automatic}


# ------------------------------------------------------------------ safety net

def _transcript(session_id: str) -> list[dict[str, Any]]:
    from hermes_state import SessionDB  # public Hermes module
    return SessionDB().get_messages_as_conversation(session_id) or []


def _session_last_activity(session_id: str) -> float | None:
    try:
        from hermes_state import SessionDB
        row = SessionDB().get_session(session_id) or {}
    except Exception:  # noqa: BLE001
        return None
    value = row.get("last_activity_at") or row.get("ended_at")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        import datetime as dt
        when = dt.datetime.fromisoformat(str(value))
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        return when.timestamp()
    except ValueError:
        return None


def _summarize(rt: Runtime, link: dict[str, Any], session_id: str) -> dict[str, str]:
    digest = link.get("digest") or {}
    try:
        text = ck.transcript_text(_transcript(session_id))
    except Exception:  # noqa: BLE001
        text = ""
    if text:
        for task in ("alchemy_task_checkpoint", None):  # our model slot, then the default route
            try:
                result = rt.ctx.llm.complete_structured(
                    instructions=ck.AUTO_INSTRUCTIONS + f"\nTask: {link.get('title', '')}",
                    input=[{"type": "text", "text": text}], json_schema=ck.AUTO_SCHEMA, schema_name="checkpoint",
                    max_tokens=400, timeout=20, purpose="alchemy-task.checkpoint", task=task)
                if isinstance(result.parsed, dict):
                    return {**result.parsed, "evidence": ""}
            except Exception:  # noqa: BLE001 - try the next route, then the free digest
                continue
    return ck.mechanical(str(digest.get("user") or ""), str(digest.get("assistant") or ""))


def _covered(link: dict[str, Any], last: float | None = None) -> bool:
    last = float(link.get("last_activity") or 0) if last is None else last
    return float(link.get("last_checkpoint") or 0) + GRACE_SECONDS >= last


def auto_checkpoint(rt: Runtime, session_id: str, reason: str) -> dict[str, Any] | None:
    link = _links(rt).get(session_id)
    if not link:
        return None
    if _covered(link):
        return None  # nothing happened since the last checkpoint
    fields = _summarize(rt, link, session_id)
    try:
        out = write_checkpoint(rt, link["task_id"], fields, automatic=True, session_id=session_id)
    except (NeedsInput, ck.CheckpointError, tf.TaskFormatError, tf.ConcurrentEditError) as exc:
        _update_link(rt, session_id, last_checkpoint=time.time(), last_error=str(exc)[:200])
        return {"error": str(exc)}
    out["reason"] = reason
    return out


def sweep(rt: Runtime, now: float | None = None) -> list[dict[str, Any]]:
    now = now or time.time()
    results = []
    for sid, link in list(_links(rt).items()):
        last = float(link.get("last_activity") or 0)
        db_last = _session_last_activity(sid)
        if db_last and db_last > last:
            last = db_last
            _update_link(rt, sid, last_activity=last)
        if now - last >= IDLE_SECONDS and not _covered(link, last):
            out = auto_checkpoint(rt, sid, "idle")
            if out:
                results.append({"session": sid, **out})
    return results


def _sweep_loop(data_dir: str) -> None:
    lock_path = os.path.join(data_dir, "locks", "sweeper.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # one sweeper per profile, across processes
    except BlockingIOError:
        os.close(fd)
        return
    try:
        while not _stop.wait(SWEEP_SECONDS):
            try:
                sweep(Runtime())
            except Exception:  # noqa: BLE001 - keep sweeping
                pass
    finally:
        os.close(fd)


def _ensure_sweeper(rt: Runtime) -> None:
    global _sweeper
    with _lock:
        if _sweeper is not None and _sweeper.is_alive():
            return
        if os.environ.get("ALCHEMY_TASK_NO_SWEEPER"):
            return
        _stop.clear()
        _sweeper = threading.Thread(target=_sweep_loop, args=(str(rt.data_dir),), name="alchemy-task-sweeper",
                                    daemon=True)
        _sweeper.start()


def stop_sweeper() -> None:
    _stop.set()


# ------------------------------------------------------------------ hooks

def post_llm_call(session_id: str = "", user_message: Any = "", assistant_response: Any = "", **_: Any) -> None:
    if not session_id:
        return
    try:
        rt = Runtime()
        if session_id not in _links(rt):
            return
        user = user_message if isinstance(user_message, str) else json.dumps(user_message, default=str)
        now = time.time()
        link = _links(rt).get(session_id) or {}
        extra = {"last_checkpoint": now} if now - float(link.get("last_checkpoint") or 0) < GRACE_SECONDS else {}
        _update_link(rt, session_id, last_activity=now, **extra,
                     digest={"user": " ".join(user.split())[:400],
                             "assistant": " ".join(str(assistant_response or "").split())[:800]})
        _ensure_sweeper(rt)
    except Exception:  # noqa: BLE001
        pass


def on_session_finalize(session_id: str = "", reason: str = "", **_: Any) -> None:
    if not session_id:
        return
    try:
        rt = Runtime()
        auto_checkpoint(rt, session_id, reason or "session ended")
    except Exception:  # noqa: BLE001
        pass


def post_compaction(session_id: str = "", old_session_id: str = "", **_: Any) -> None:
    if not session_id or not old_session_id or session_id == old_session_id:
        return
    try:
        rt = Runtime()
        with _lock:
            links = _links(rt)
            if old_session_id in links:
                links[session_id] = links.pop(old_session_id)
                rt.ctx.state.set("links", links)
    except Exception:  # noqa: BLE001
        pass


def pre_llm_call(session_id: str = "", **_: Any):
    if not session_id:
        return None
    try:
        link = _links(Runtime()).get(session_id)
    except Exception:  # noqa: BLE001
        return None
    if not link:
        return None
    return {"context": (f"[Alchemy Task] This chat is working on the task \"{link.get('title', '')}\" "
                        f"(task_id {link['task_id']}). When the work is finished, needs the user, waits on someone "
                        "else or is blocked, call task_checkpoint.")}


def register(ctx: Any) -> None:
    ctx.register_hook("post_llm_call", post_llm_call)
    ctx.register_hook("on_session_finalize", on_session_finalize)
    ctx.register_hook("post_compaction", post_compaction)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    try:
        ctx.register_auxiliary_task("alchemy_task_checkpoint", display_name="Alchemy Task checkpoints",
                                    description="Summarizes unfinished work sessions into task checkpoints.",
                                    inherit_from="compression", defaults={"timeout": 30})
    except Exception:  # noqa: BLE001 - optional: falls back to the default model route
        pass
    try:
        ctx.on_unload(stop_sweeper)
    except Exception:  # noqa: BLE001
        pass
