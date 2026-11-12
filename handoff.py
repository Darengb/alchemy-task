"""Send a task to chat: the agent messages the user about it and waits for "go".

Two routes, chosen when the user presses the button (phone or web dashboard):

1. Messaging chat (fast, a few seconds). Used when the messaging gateway is running, the plugin may message
   the user (``allow_gateway_injection``), and there is a messaging chat to use: the chat that last worked on
   the task, else the home channel. The request goes into a file queue in the plugin's data folder (the
   dashboard and the gateway are separate processes); a relay thread in the gateway's process hands it to
   Hermes with ``ctx.inject_message``, which starts a normal turn in that chat. Messaging sessions also show
   in the Hermes app.
2. New session (about a minute). Used otherwise, and as a fallback when the gateway has not taken a queued
   request within ``FALLBACK_SECONDS``. A one-time scheduled agent job runs the same note; its run is a new
   session named after the task, in which the user can reply. It needs only Hermes's scheduler, which runs
   without a messaging gateway. The fallback runs in a background worker (and when the UI asks for the
   status), so it happens even if the user closes the app right after pressing the button.

On the desktop app the UI opens a new chat and sends the note there itself; this module only builds it.

The note is plain instructions; nothing is blocked. It tells the agent where it came from, to read the task,
the exact reply to send, and not to start until the user says "go". Wording stays gender-neutral ("the user").
"""
from __future__ import annotations

import contextvars
import datetime as dt
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .core.store import NeedsInput
from .runtime import Runtime

PLUGIN = "alchemy-task"
SURFACES = {"dashboard": "the web dashboard", "phone": "a phone", "desktop": "the desktop app"}
POLL_SECONDS = 1.0
FALLBACK_SECONDS = 10  # the gateway has not taken a queued request in this long: start a new session instead
KEEP_SECONDS = 24 * 3600
# Sessions that are messaging chats the gateway can reach. App, desktop, CLI, cron and other local sessions
# are not targets: the app only accepts a message into a chat that is open on screen.
NOT_CHATS = {"gui", "desktop", "tui", "cli", "acp", "cron", "subagent", "api", "webhook", "batch", "oneshot",
             "local", ""}
_lock = threading.Lock()
_skip_until: dict[str, float] = {}  # request id -> time this process may retry it


# ------------------------------------------------------------------ the note

def build_text(task: dict[str, Any], surface: str, *, new_session: bool = False) -> str:
    """The handoff note. ``task`` is a TaskStore.summary() dict; empty fields drop their line."""
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
    origin = ("This message comes from the Alchemy Task plugin, not from the user typing. This is a new chat "
              "about one task; the user reads your reply here and answers in this chat." if new_session else
              "This message comes from the Alchemy Task plugin, not from the user typing in this chat.")
    return "\n".join([
        "[Alchemy Task handoff]",
        f'The user pressed "Send to chat" on a task in the Alchemy Task UI ({where}).',
        origin,
        "Do not start the task or make any changes yet.",
        "",
        f'First, read the full task: call task_find with task_id "{task_id}" and include_body true.',
        "Use its notes, research and current state to write the reply below. Then wait for the user's answer.",
        "",
        *facts,
        "",
        "Reply with exactly this shape, filling in the brackets from the task:",
        '"[Task title]: [one sentence on where it stands and the next step].',
        'Want me to start, or talk it through first? Reply **go** to start."',
        "",
        'If the user replies "go", start the task with task_work_start using the same task ID.',
        "If the user replies with anything else, discuss the task or update it as asked, and start only when "
        "the user says to.",
    ])


# ------------------------------------------------------------------ which chat

def remember_chat(rt: Runtime, task_id: str, session_id: str) -> None:
    """Note that this session worked with this task (any task tool call), newest first."""
    if not task_id or not session_id:
        return
    with _lock:
        chats = rt.ctx.state.get("task_chats", default={}) or {}
        seen = [s for s in chats.get(task_id, []) if s != session_id]
        chats[task_id] = [session_id, *seen][:5]
        if len(chats) > 500:  # forget the tasks touched longest ago
            for k in list(chats)[: len(chats) - 500]:
                chats.pop(k, None)
        rt.ctx.state.set("task_chats", chats)


def _session_row(session_id: str) -> dict[str, Any] | None:
    try:
        from hermes_state import SessionDB
        return SessionDB().get_session(session_id)
    except Exception:  # noqa: BLE001
        return None


def _chat_target(row: dict[str, Any] | None, reason: str) -> dict[str, Any] | None:
    """A messaging chat the gateway can inject into (by its routing key), or None."""
    if not row or not row.get("session_key"):
        return None
    platform = str(row.get("source") or "").lower()
    if platform in NOT_CHATS:
        return None
    return {"platform": platform, "chat_name": str(row.get("display_name") or row.get("title") or "")[:80],
            "reason": reason, "last_activity": row.get("last_activity_at") or 0, "session_key": row["session_key"]}


def _home_targets() -> list[dict[str, Any]]:
    """Each platform's home channel (set with /sethome), as the newest session in that chat."""
    try:
        from gateway.config import load_gateway_config  # public plugin module
        from hermes_state import SessionDB
        cfg = load_gateway_config()
        db = SessionDB()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for platform in cfg.platforms:
        home = cfg.get_home_channel(platform)
        if not home or not home.chat_id:
            continue
        try:
            sid = db.find_session_by_origin(platform=platform.value, chat_id=str(home.chat_id),
                                            thread_id=home.thread_id or None)
        except Exception:  # noqa: BLE001
            sid = None
        target = _chat_target(_session_row(sid) if sid else None, "home")
        if target:
            target["chat_name"] = target["chat_name"] or home.name or "Home"
            out.append(target)
    out.sort(key=lambda t: (t["platform"] != "telegram",))  # Telegram first when several are set up
    return out


def resolve_target(rt: Runtime, task_id: str) -> dict[str, Any] | None:
    """The messaging chat that last worked on the task, else the home channel, else None."""
    from . import worksession
    sessions = list((rt.ctx.state.get("task_chats", default={}) or {}).get(task_id, []))
    sessions += [sid for sid, link in worksession._links(rt).items() if link.get("task_id") == task_id]
    recent = [t for t in (_chat_target(_session_row(sid), "task") for sid in dict.fromkeys(sessions)) if t]
    if recent:
        return max(recent, key=lambda t: float(t.get("last_activity") or 0))
    homes = _home_targets()
    return homes[0] if homes else None


def injection_allowed() -> bool:
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly() or {}
    except Exception:  # noqa: BLE001
        return False
    entry = ((cfg.get("plugins") or {}).get("entries") or {}).get(PLUGIN) or {}
    return entry.get("allow_gateway_injection") is True


def gateway_running() -> bool:
    """Whether this profile's messaging gateway is running (public ``gateway.status`` check)."""
    try:
        from gateway.status import get_running_pid  # public plugin module
        return get_running_pid() is not None
    except Exception:  # noqa: BLE001
        return False


def chat_route(rt: Runtime, task_id: str) -> tuple[dict[str, Any] | None, str]:
    """The messaging chat for route 1, or (None, why route 2 is used)."""
    if not gateway_running():
        return None, "no_gateway"
    if not injection_allowed():
        return None, "no_permission"
    target = resolve_target(rt, task_id)
    return (target, "") if target else (None, "no_chat")


# ------------------------------------------------------------------ queue and records

def _queue_dir(rt: Any) -> Path:
    d = Path(rt.data_dir) / "handoffs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def start_session(rt: Runtime, task: dict[str, Any], surface: str) -> dict[str, Any]:
    """Route 2: a one-time scheduled agent job. Its run is a new session named after the task."""
    from .jobs import parse_job_id, guard_scheduling
    guard_scheduling(rt.ctx)  # scheduled runs never create jobs
    tz = rt.settings.timezone or "UTC"
    try:
        from zoneinfo import ZoneInfo
        when = dt.datetime.now(ZoneInfo(tz)).replace(microsecond=0, tzinfo=None) + dt.timedelta(seconds=5)
    except Exception:  # noqa: BLE001 - unknown zone: schedule in UTC
        tz, when = "UTC", dt.datetime.utcnow().replace(microsecond=0) + dt.timedelta(seconds=5)
    args = {"action": "create", "name": (task.get("title") or "Task")[:80], "schedule": when.isoformat(),
            "timezone": tz, "deliver": "local", "repeat": 1,
            "prompt": build_text(task, surface, new_session=True)}
    raw = rt.ctx.dispatch_tool("cronjob_manage", args)
    job_id = parse_job_id(raw)
    if not job_id:
        raise NeedsInput("schedule", f"Could not start a chat for this task: {str(raw)[:240]}")
    return {"job_id": job_id, "scheduled_for": when.isoformat(), "timezone": tz}


def request(rt: Runtime, task: dict[str, Any], surface: str) -> dict[str, Any]:
    hid = uuid.uuid4().hex[:16]
    rec: dict[str, Any] = {"id": hid, "task_id": task["task_id"], "title": task.get("title") or "",
                           "surface": surface, "created": time.time()}
    target, why = chat_route(rt, task["task_id"])
    if target:
        rec.update(route="chat", state="pending", target=target, text=build_text(task, surface), task=task)
    else:
        rec.update(route="session", state="started", reason=why, session=start_session(rt, task, surface))
    _write(_queue_dir(rt) / (f"{hid}.json" if target else f"{hid}.done.json"), rec)
    if target:
        # Make sure a background worker in this process watches the request, so the fallback happens even if
        # the user closes the app and the gateway never takes it. It inherits this request's profile.
        ensure_relay(rt.ctx, Path(rt.data_dir))
    return public(rec)


def public(rec: dict[str, Any]) -> dict[str, Any]:
    t = rec.get("target") or {}
    out = {"id": rec["id"], "task_id": rec["task_id"], "route": rec.get("route", "chat"), "state": rec["state"],
           "error": rec.get("error"), "reason": rec.get("reason")}
    if rec.get("route", "chat") == "chat" or rec.get("fallback"):
        out["target"] = {"platform": t.get("platform"), "chat_name": t.get("chat_name"), "reason": t.get("reason")}
    return out


def _fall_back(rt: Runtime, d: Path, hid: str, now: float) -> dict[str, Any] | None:
    """Turn a messaging request the gateway has not taken within FALLBACK_SECONDS into a new session.
    Returns the finished record, or None when it is not due or another process got to it first."""
    pending = d / f"{hid}.json"
    try:
        rec = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if now - rec.get("created", now) <= FALLBACK_SECONDS:
        return None
    mine = d / f"{hid}.claimed-fallback-{os.getpid()}"
    try:
        os.rename(pending, mine)  # the same claim the gateway uses: only one of them ever acts on it
    except OSError:
        return None
    try:
        session = start_session(rt, rec.get("task") or {"task_id": rec["task_id"], "title": rec["title"]},
                                rec.get("surface") or "dashboard")
        rec.update(route="session", state="started", fallback=True, reason="gateway_silent", session=session)
    except Exception as exc:  # noqa: BLE001 - report it; nothing was sent
        rec.update(state="failed", error=str(getattr(exc, "message", exc))[:300])
    _write(d / f"{hid}.done.json", rec)
    mine.unlink(missing_ok=True)
    return rec


def status(rt: Runtime, hid: str, now: float | None = None) -> dict[str, Any]:
    """A handoff's state. The background worker normally does the fallback; this does it too when asked first."""
    now = now or time.time()
    if not hid.isalnum():
        raise NeedsInput("not_found", "Unknown handoff")
    d = _queue_dir(rt)
    pending = d / f"{hid}.json"
    if pending.exists():
        rec = _fall_back(rt, d, hid, now)
        if rec is not None:
            return public(rec)
        if pending.exists():
            return public(json.loads(pending.read_text(encoding="utf-8")))
    done = d / f"{hid}.done.json"
    if done.exists():
        return public(json.loads(done.read_text(encoding="utf-8")))
    if any(d.glob(f"{hid}.claimed-*")):
        return {"id": hid, "route": "chat", "state": "sending"}
    raise NeedsInput("not_found", "Unknown handoff")


def fallback_once(rt: Runtime, data_dir: Path, now: float | None = None) -> list[str]:
    """The background half of the fallback, so it happens even when no screen is asking for the status."""
    now = now or time.time()
    d = Path(data_dir) / "handoffs"
    if not d.is_dir():
        return []
    done = []
    for p in sorted(d.glob("*.json")):
        if p.name.endswith(".done.json"):
            continue
        rec = _fall_back(rt, d, p.stem, now)
        if rec is not None:
            done.append(p.stem)
    return done


# ------------------------------------------------------------------ relay (a thread in every process that
# loads the plugin; only the messaging gateway's own process takes requests, so a classic CLI, a cron worker
# or the dashboard never receives one)

def in_gateway_process() -> bool:
    """True in the messaging gateway's process, or in the plugin host it starts (``plugins.isolation: host``).

    The gateway marks its process and its children with ``_HERMES_GATEWAY=1``; Hermes has no public "which
    host am I in" call yet, so this is a disclosed seam. The lock check covers an in-process gateway."""
    if os.environ.get("_HERMES_GATEWAY") == "1":
        return True
    try:
        from gateway.status import owns_gateway_runtime_lock  # public plugin module
        return bool(owns_gateway_runtime_lock())
    except Exception:  # noqa: BLE001
        return False


def relay_once(rt: Any, now: float | None = None, *, data_dir: Path | None = None) -> list[str]:
    """Deliver pending messaging requests from the gateway's process. ``rt`` only needs ``ctx`` (and
    ``data_dir`` when none is passed): the relay thread passes its profile's folder explicitly."""
    now = now or time.time()
    if not in_gateway_process():
        return []
    d = Path(data_dir) / "handoffs" if data_dir is not None else _queue_dir(rt)
    if not d.is_dir():
        return []
    sent = []
    for p in sorted(d.glob("*.json")):
        if p.name.endswith(".done.json"):
            try:
                if now - p.stat().st_mtime > KEEP_SECONDS:
                    p.unlink()
            except OSError:
                pass
            continue
        hid = p.stem
        if _skip_until.get(hid, 0) > now:
            continue
        claimed = p.with_name(f"{hid}.claimed-{os.getpid()}")
        try:
            os.rename(p, claimed)  # only one process wins the claim
        except OSError:
            continue
        try:
            rec = json.loads(claimed.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            claimed.unlink(missing_ok=True)
            continue
        try:
            ok = bool(rt.ctx.inject_message(rec["text"], role="user", session_key=rec["target"]["session_key"]))
        except Exception:  # noqa: BLE001 - treat like a refusal
            ok = False
        if ok:
            rec.update(state="sent", sent=now)
            _write(d / f"{hid}.done.json", rec)
            claimed.unlink(missing_ok=True)
            sent.append(hid)
        else:  # refused: give it back; the dashboard falls back to a new session if this keeps failing
            _skip_until[hid] = now + 3
            os.rename(claimed, p)
    return sent


class _RelayRuntime:
    """What the relay needs: the plugin context."""
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx


def _loop(ctx: Any, data_dir: Path, stop: threading.Event) -> None:
    """Runs in the context captured when it was started (see ensure_relay), so Hermes's notion of the current
    profile is the plugin's own: a job it schedules lands in this profile. Only the gateway's process delivers
    to messaging chats; any process may do the fallback, because the claim lets only one act on a request."""
    relay_rt = _RelayRuntime(ctx)
    while not stop.wait(POLL_SECONDS):
        try:
            if in_gateway_process():
                relay_once(relay_rt, data_dir=data_dir)
            folder = Path(data_dir) / "handoffs"
            if folder.is_dir() and any(not p.name.endswith(".done.json") for p in folder.glob("*.json")):
                fallback_once(Runtime(ctx, data_dir=Path(data_dir)), data_dir)
        except Exception:  # noqa: BLE001 - keep relaying
            pass


_relays: dict[str, tuple[threading.Thread, threading.Event]] = {}


def ensure_relay(ctx: Any, data_dir: Path) -> None:
    """One relay thread per profile folder. ``data_dir`` is captured when the plugin loads, while Hermes has
    the plugin's profile selected; a thread started later would otherwise see the launch profile's home."""
    if os.environ.get("ALCHEMY_TASK_NO_RELAY"):
        return
    key = str(Path(data_dir).resolve())
    with _lock:
        cur = _relays.get(key)
        if cur and cur[0].is_alive():
            return
        stop = threading.Event()
        # A new thread starts with an empty context; run it in a copy of the current one, which carries the
        # profile Hermes selected while loading the plugin.
        loaded = contextvars.copy_context()
        t = threading.Thread(target=loaded.run, args=(_loop, ctx, Path(data_dir), stop),
                             name="alchemy-task-handoff-relay", daemon=True)
        _relays[key] = (t, stop)
        t.start()


def stop_relay() -> None:
    with _lock:
        for _t, stop in _relays.values():
            stop.set()
        _relays.clear()


# ------------------------------------------------------------------ hooks

def post_tool_call(tool_name: str = "", args: Any = None, result: Any = None, session_id: str = "", **_: Any) -> None:
    if not session_id or not str(tool_name).startswith("task_"):
        return
    try:
        from .core import taskfile as tf
        task_id = ""
        if isinstance(args, dict):
            for key in ("task_id", "task"):
                if tf.valid_task_id(str(args.get(key) or "")):
                    task_id = str(args[key])
                    break
        if not task_id and isinstance(result, str) and '"task_id"' in result:
            data = json.loads(result)
            task = data.get("task") if isinstance(data, dict) else None
            task_id = str((task or {}).get("task_id") or "")
        if task_id and tf.valid_task_id(task_id):
            remember_chat(Runtime(), task_id, session_id)
    except Exception:  # noqa: BLE001
        pass


def register(ctx: Any) -> None:
    ctx.register_hook("post_tool_call", post_tool_call)
    try:
        data_dir = Path(ctx.state.data_dir)
        (data_dir / "handoffs").mkdir(parents=True, exist_ok=True)
        ensure_relay(ctx, data_dir)
    except Exception:  # noqa: BLE001 - without a relay, requests fall back to a new session
        pass
    try:
        ctx.on_unload(stop_relay)
    except Exception:  # noqa: BLE001
        pass
