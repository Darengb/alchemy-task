"""Start in chat: the agent messages the user about a task and waits for "go".

On the desktop app the UI opens a new chat and sends the note there itself; this module only builds it.

From the web dashboard (desktop browser or phone) the plugin cannot open a chat on the user's screen, so it
creates a one-time scheduled agent job that runs the note a few seconds later. Hermes's scheduler delivers
the agent's reply to the user's chat, the same way it delivers discovery digests, so no extra permission is
needed. The chat is, in order:

1. the chat the discovery digests for the task's area go to (where the user already reads and answers
   task messages about that area);
2. the chat where the user set up the plugin (setup always happens in a chat); its address is saved at
   setup so pruning that session later does not lose it;
3. otherwise ``local``: the reply stays in the job's own session, listed under Cron jobs in the app.

The job sets ``attach_to_session`` so Hermes copies the delivered reply into that chat's history; when the
user answers "go" there, the agent in that chat sees which task it is about.

The note is plain instructions; nothing is blocked. It tells the agent where it came from, to read the task,
the exact reply to send, and not to start until the user says "go". Wording stays gender-neutral ("the user").
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from .core.store import NeedsInput
from .runtime import Runtime

PLUGIN = "alchemy-task"
SURFACES = {"dashboard": "the web dashboard", "phone": "a phone", "desktop": "the desktop app"}
KEEP_SECONDS = 24 * 3600
# Session sources Hermes's scheduler cannot deliver to: app, desktop, CLI and other local sessions.
NOT_CHATS = {"gui", "desktop", "tui", "cli", "acp", "cron", "subagent", "api", "api_server", "webhook", "batch",
             "oneshot", "local", "tool", "kanban", ""}
SETUP_CHAT_KEY = "setup_chat"


# ------------------------------------------------------------------ the note

def build_text(task: dict[str, Any], surface: str, *, new_session: bool = False, delivered_to: str = "") -> str:
    """The handoff note. ``task`` is a TaskStore.summary() dict; empty fields drop their line.

    ``new_session`` is the scheduled-job form: the reply is delivered to ``delivered_to`` (a chat label), or
    stays in this session when that is empty."""
    where = SURFACES.get(surface, "the Alchemy Task UI")
    task_id = task.get("task_id") or ""
    facts = [f"Task: {task.get('title') or ''}", f"Task ID: {task_id}"]
    meta = [f"Due: {task['due']}" if task.get("due") else "",
            f"Area: {task['area']}" if task.get("area") else "",
            f"Priority: {task['priority']}" if task.get("priority") and task.get("priority") != "normal" else ""]
    if any(meta):
        facts.append(" · ".join(m for m in meta if m))
    if task.get("status") and task.get("status") not in ("open",):
        facts.append(f"Status: {task['status']}")
    if task.get("summary"):
        facts.append(f"Summary: {task['summary']}")
    state = " ".join(str(task.get("current_state") or "").split())
    if state:
        facts.append(f"Current state: {state[:500]}")
    if not new_session:
        origin = "This message comes from the Alchemy Task plugin, not from the user typing in this chat."
    elif delivered_to:
        origin = ("This message comes from the Alchemy Task plugin, not from the user typing. Your final reply "
                  f"is delivered to the user's chat ({delivered_to}), and the user answers there.")
    else:
        origin = ("This message comes from the Alchemy Task plugin, not from the user typing. This is a new chat "
                  "about one task; the user reads your reply here and answers in this chat.")
    shape = ['"[Task title]: [one sentence on where it stands and the next step].',
             'Want me to start, or talk it through first? Reply **go** to start."']
    if new_session and delivered_to:
        # The chat that receives the reply never saw this note: the ID lets its agent find the task.
        shape[-1] = 'Want me to start, or talk it through first? Reply **go** to start.'
        shape.append(f'Task ID: {task_id}"')
    return "\n".join([
        "[Alchemy Task handoff]",
        f'The user pressed "Start in chat" on a task in the Alchemy Task UI ({where}).',
        origin,
        "Do not start the task or make any changes yet.",
        "",
        f'First, read the full task: call task_find with task_id "{task_id}" and include_body true.',
        "Use its notes, research and current state to write the reply below. Then wait for the user's answer.",
        "",
        *facts,
        "",
        "Reply with exactly this shape, filling in the brackets from the task:",
        *shape,
        "",
        'If the user replies "go", start the task with task_work_start using the same task ID.',
        "If the user replies with anything else, discuss the task or update it as asked, and start only when "
        "the user says to.",
    ])


# ------------------------------------------------------------------ which chat

def _host_origin(session_id: str) -> dict[str, Any] | None:
    """The messaging chat of a host session (platform, chat id, topic), or None."""
    try:
        from . import discovery_integration as di
        return di.host_origin(di._profile_home(), session_id, None)
    except Exception:  # noqa: BLE001
        return None


def chat_address(session_id: str) -> dict[str, Any] | None:
    """A scheduler delivery address for a session's chat, or None for app/desktop/local sessions."""
    origin = _host_origin(session_id) if session_id else None
    if not origin or str(origin.get("source") or "").lower() in NOT_CHATS or not origin.get("chat_id"):
        return None
    platform = str(origin["source"]).lower()
    deliver = f"{platform}:{origin['chat_id']}" + (f":{origin['thread_id']}" if origin.get("thread_id") else "")
    return {"deliver": deliver, "platform": platform, "chat_name": str(origin.get("chat_name") or "")[:80]}


def remember_setup_chat(rt: Runtime, session_id: str) -> None:
    """Save the setup chat's address now, while its session exists; a later prune cannot lose it."""
    try:
        address = chat_address(session_id)
        if address:
            rt.ctx.state.set(SETUP_CHAT_KEY, {**address, "session": session_id, "saved_at": time.time()})
    except Exception:  # noqa: BLE001 - setup never fails over this; delivery falls back to the app
        pass


def _explicit(deliver: str) -> dict[str, Any] | None:
    """A stream's explicit ``platform:chat[:topic]`` target as an address."""
    parts = deliver.split(":")
    if len(parts) < 2 or parts[0].lower() in NOT_CHATS or parts[0].lower() in ("origin", "all"):
        return None
    return {"deliver": deliver, "platform": parts[0].lower(), "chat_name": ""}


def delivery_target(rt: Runtime, area: str = "") -> dict[str, Any] | None:
    """Where the handoff reply goes: the digest chat of the task's area's discovery stream, else the setup
    chat, else None (the app). Setup makes one stream per area."""
    state = rt.ctx.state
    saved = _setup_chat(state)
    streams = sorted((s for s in (state.get("streams", default={}) or {}).values()
                      if area and area in (s.get("areas") or [])),
                     key=lambda s: float(s.get("created_at") or 0))
    for stream in streams:
        if not stream.get("job_id"):
            continue
        deliver = str(stream.get("deliver") or "origin").strip()
        address = (chat_address(stream.get("origin_session") or "") if deliver == "origin"
                   else _explicit(deliver))
        if address:
            same_chat = saved and saved.get("deliver", "").split(":")[:2] == address["deliver"].split(":")[:2]
            if not address["chat_name"] and same_chat:
                address["chat_name"] = saved.get("chat_name") or ""
            return address
    return saved


def _setup_chat(state: Any) -> dict[str, Any] | None:
    """The saved setup chat; installs set up before it was saved resolve the recorded setup session once."""
    saved = state.get(SETUP_CHAT_KEY, default=None) or None
    if saved and saved.get("deliver"):
        return saved
    sessions = [r.get("origin_session") for r in (state.get("jobs", default={}) or {}).values()]
    for sid in sorted({s for s in sessions if s}, reverse=True):
        address = chat_address(sid)
        if address:
            state.set(SETUP_CHAT_KEY, {**address, "session": sid, "saved_at": time.time()})
            return address
    return None


PLATFORM_NAMES = {"telegram": "Telegram", "slack": "Slack", "discord": "Discord", "whatsapp": "WhatsApp",
                  "signal": "Signal", "photon": "iMessage", "matrix": "Matrix", "mattermost": "Mattermost"}


def label(address: dict[str, Any] | None) -> str:
    if not address or not address.get("platform"):
        return ""
    platform = PLATFORM_NAMES.get(address["platform"], address["platform"].title())
    return f"{platform} ({address['chat_name']})" if address.get("chat_name") else platform


# ------------------------------------------------------------------ records

def _queue_dir(rt: Any) -> Path:
    d = Path(rt.data_dir) / "handoffs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def start_session(rt: Runtime, task: dict[str, Any], surface: str,
                  address: dict[str, Any] | None = None) -> dict[str, Any]:
    """A one-time scheduled agent job that writes the reply, delivered to ``address`` (else kept local)."""
    from .jobs import parse_job_id, guard_scheduling
    guard_scheduling(rt.ctx)  # scheduled runs never create jobs
    tz = rt.settings.timezone or "UTC"
    try:
        from zoneinfo import ZoneInfo
        when = dt.datetime.now(ZoneInfo(tz)).replace(microsecond=0, tzinfo=None) + dt.timedelta(seconds=5)
    except Exception:  # noqa: BLE001 - unknown zone: schedule in UTC
        tz, when = "UTC", dt.datetime.utcnow().replace(microsecond=0) + dt.timedelta(seconds=5)
    args = {"action": "create", "name": (task.get("title") or "Task")[:80], "schedule": when.isoformat(),
            "timezone": tz, "deliver": address["deliver"] if address else "local", "repeat": 1,
            "prompt": build_text(task, surface, new_session=True, delivered_to=label(address))}
    if address:
        args["attach_to_session"] = True  # copy the reply into that chat's history, so "go" has context
    raw = rt.ctx.dispatch_tool("cronjob_manage", args)
    job_id = parse_job_id(raw)
    if not job_id:
        raise NeedsInput("schedule", f"Could not start a chat for this task: {str(raw)[:240]}")
    return {"job_id": job_id, "scheduled_for": when.isoformat(), "timezone": tz, "deliver": args["deliver"]}


def request(rt: Runtime, task: dict[str, Any], surface: str) -> dict[str, Any]:
    hid = uuid.uuid4().hex[:16]
    address = delivery_target(rt, str(task.get("area") or ""))
    rec: dict[str, Any] = {"id": hid, "task_id": task["task_id"], "title": task.get("title") or "",
                           "surface": surface, "created": time.time(), "route": "session", "state": "started",
                           "target": address, "session": start_session(rt, task, surface, address)}
    d = _queue_dir(rt)
    _write(d / f"{hid}.done.json", rec)
    _prune(d, rec["created"])
    return public(rec)


def _prune(d: Path, now: float) -> None:
    for p in d.glob("*.json"):
        try:
            if now - p.stat().st_mtime > KEEP_SECONDS:
                p.unlink()
        except OSError:
            pass


def public(rec: dict[str, Any]) -> dict[str, Any]:
    t = rec.get("target") or {}
    return {"id": rec["id"], "task_id": rec["task_id"], "route": rec.get("route", "session"),
            "state": rec["state"], "error": rec.get("error"), "reason": rec.get("reason"),
            "target": ({"platform": t.get("platform"), "chat_name": t.get("chat_name"), "label": label(t)}
                       if t.get("platform") else None)}


def status(rt: Runtime, hid: str) -> dict[str, Any]:
    if not hid.isalnum():
        raise NeedsInput("not_found", "Unknown handoff")
    for name in (f"{hid}.done.json", f"{hid}.json"):  # older installs also queued pending requests
        p = _queue_dir(rt) / name
        if p.exists():
            return public(json.loads(p.read_text(encoding="utf-8")))
    raise NeedsInput("not_found", "Unknown handoff")


def register(ctx: Any) -> None:
    """Nothing runs in the background any more; kept so the plugin's register order is unchanged."""
    return None
