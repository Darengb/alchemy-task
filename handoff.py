"""Send a task to chat: the agent messages the user about it and waits for "go".

The Tasks UI asks for a handoff. On a phone or the web dashboard the plugin picks a messaging chat (the chat
that last worked on the task, else the user's home channel) and queues a request in its own data folder. A
small relay thread in the messaging gateway's process picks the request up and hands the note to Hermes with
``ctx.inject_message``, which starts a normal turn in that chat: the agent reads the task and asks whether to
start. The dashboard and the gateway are separate processes, so the request goes through a file queue.

On the desktop app the UI opens a new chat and sends the same note there itself; this module only builds it.

The note is plain instructions; nothing is blocked. It tells the agent where it came from, to read the task,
the exact reply to send, and not to start until the user says "go". Wording stays gender-neutral ("the user").
"""
from __future__ import annotations

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
GIVE_UP_SECONDS = 90  # no gateway took it in this long: report it instead of waiting forever
APP_GIVE_UP_SECONDS = 20  # an app chat that is not open in the dashboard's process now cannot take it
KEEP_SECONDS = 24 * 3600
# Chats in the Hermes app and desktop app run in the dashboard's process and are addressed by session id;
# messaging chats (Telegram, Discord, ...) run in the gateway and are addressed by their routing key.
APP_SOURCES = {"gui", "desktop", "tui"}
NOT_CHATS = {"cli", "acp", "cron", "subagent", "api", "webhook", "batch", "oneshot", "local", ""}
_lock = threading.Lock()
_skip_until: dict[str, float] = {}  # request id -> time this process may retry it


# ------------------------------------------------------------------ the note

def build_text(task: dict[str, Any], surface: str) -> str:
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
    return "\n".join([
        "[Alchemy Task handoff]",
        f'The user pressed "Send to chat" on a task in the Alchemy Task UI ({where}).',
        "This message comes from the Alchemy Task plugin, not from the user typing in this chat.",
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
    """A chat Hermes can inject into: an app chat (by session id) or a messaging chat (by routing key)."""
    if not row:
        return None
    platform = str(row.get("source") or "").lower()
    name = str(row.get("display_name") or row.get("title") or "")[:80]
    base = {"platform": platform, "chat_name": name, "reason": reason, "last_activity": row.get("last_activity_at") or 0}
    if platform in APP_SOURCES and row.get("id"):
        return {**base, "kind": "app", "session_key": str(row["id"])}
    if platform in NOT_CHATS or platform in APP_SOURCES or not row.get("session_key"):
        return None
    return {**base, "kind": "chat", "session_key": row["session_key"]}


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


def resolve_target(rt: Runtime, task_id: str) -> dict[str, Any]:
    """The chat that last worked on the task, else the home channel."""
    from . import worksession
    sessions = list((rt.ctx.state.get("task_chats", default={}) or {}).get(task_id, []))
    sessions += [sid for sid, link in worksession._links(rt).items() if link.get("task_id") == task_id]
    recent = [t for t in (_chat_target(_session_row(sid), "task") for sid in dict.fromkeys(sessions)) if t]
    if recent:
        return max(recent, key=lambda t: float(t.get("last_activity") or 0))
    homes = _home_targets()
    if homes:
        return homes[0]
    raise NeedsInput("no_chat", "There is no chat to send this to. Message Hermes once from Telegram (or another "
                     "messaging app), or set a home channel there with /sethome, then try again.")


def injection_allowed() -> bool:
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly() or {}
    except Exception:  # noqa: BLE001
        return False
    entry = ((cfg.get("plugins") or {}).get("entries") or {}).get(PLUGIN) or {}
    return entry.get("allow_gateway_injection") is True


PERMISSION_MESSAGE = ("Alchemy Task needs permission to message you in chat. Ask Hermes to allow it, or run: "
                      f"hermes config set plugins.entries.{PLUGIN}.allow_gateway_injection true")


# ------------------------------------------------------------------ queue

def _queue_dir(rt: Runtime) -> Path:
    d = Path(rt.data_dir) / "handoffs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def request(rt: Runtime, task: dict[str, Any], surface: str) -> dict[str, Any]:
    if not injection_allowed():
        raise NeedsInput("permission", PERMISSION_MESSAGE)
    target = resolve_target(rt, task["task_id"])
    hid = uuid.uuid4().hex[:16]
    rec = {"id": hid, "task_id": task["task_id"], "title": task.get("title") or "", "surface": surface,
           "text": build_text(task, surface), "target": target, "state": "pending", "created": time.time()}
    _write(_queue_dir(rt) / f"{hid}.json", rec)
    return public(rec)


def public(rec: dict[str, Any]) -> dict[str, Any]:
    t = rec.get("target") or {}
    return {"id": rec["id"], "task_id": rec["task_id"], "state": rec["state"], "error": rec.get("error"),
            "target": {"platform": t.get("platform"), "kind": t.get("kind") or "chat", "chat_name": t.get("chat_name"),
                       "reason": t.get("reason")}}


def status(rt: Runtime, hid: str) -> dict[str, Any]:
    if not hid.isalnum():
        raise NeedsInput("not_found", "Unknown handoff")
    d = _queue_dir(rt)
    for name in (f"{hid}.json", f"{hid}.done.json"):
        p = d / name
        if p.exists():
            rec = json.loads(p.read_text(encoding="utf-8"))
            if rec["state"] == "pending" and time.time() - rec["created"] > _give_up(rec) + 10:
                rec["state"], rec["error"] = "failed", _late_error(rec)
            return public(rec)
    if any(d.glob(f"{hid}.claimed-*")):
        return {"id": hid, "state": "sending"}
    raise NeedsInput("not_found", "Unknown handoff")


# ------------------------------------------------------------------ relay (a thread in every process that
# loads the plugin; only the messaging gateway's own process takes requests, so a classic CLI, a cron worker
# or the dashboard never receives one)

def _give_up(rec: dict[str, Any]) -> float:
    return APP_GIVE_UP_SECONDS if (rec.get("target") or {}).get("kind") == "app" else GIVE_UP_SECONDS


def _late_error(rec: dict[str, Any]) -> str:
    if (rec.get("target") or {}).get("kind") == "app":
        return "That chat is not open in the Hermes app right now. Open it, then press Send to chat again."
    return "Hermes did not pick this up. Check that the messaging gateway is running."


def in_dashboard_process() -> bool:
    """True in the dashboard's process (which runs app and desktop chats) or its plugin host. Like the gateway
    check, this reads the marker the dashboard sets, since Hermes has no public call for it yet."""
    return bool(os.environ.get("HERMES_DASHBOARD_PUBLIC_URL"))


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
    """Deliver pending handoffs this process can deliver. ``rt`` only needs ``ctx`` (and ``data_dir`` when
    none is passed): the relay thread passes its profile's folder explicitly."""
    now = now or time.time()
    kinds = {k for k, here in (("chat", in_gateway_process()), ("app", in_dashboard_process())) if here}
    if not kinds:
        return []
    d = Path(data_dir) / "handoffs" if data_dir is not None else _queue_dir(rt)
    if not d.is_dir():
        return []
    ctx = rt.ctx
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
        try:
            peek = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if ((peek.get("target") or {}).get("kind") or "chat") not in kinds:
            continue  # another process's job
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
        if now - rec.get("created", now) > _give_up(rec):
            rec.update(state="failed", error=_late_error(rec))
            _write(d / f"{hid}.done.json", rec)
            claimed.unlink(missing_ok=True)
            continue
        try:
            ok = bool(ctx.inject_message(rec["text"], role="user", session_key=rec["target"]["session_key"]))
        except Exception:  # noqa: BLE001 - treat like a refusal and let another process try
            ok = False
        if ok:
            rec.update(state="sent", sent=now)
            _write(d / f"{hid}.done.json", rec)
            claimed.unlink(missing_ok=True)
            sent.append(hid)
        else:  # refused (for an app chat: not open here right now): give it back and retry shortly
            _skip_until[hid] = now + (2 if (rec.get("target") or {}).get("kind") == "app" else 15)
            os.rename(claimed, p)
    return sent




class _RelayRuntime:
    """What the relay needs: the plugin context. Building a full Runtime here would read the launch
    profile's config, because a thread does not inherit the profile the plugin was loaded for."""
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx


def _loop(ctx: Any, data_dir: Path, stop: threading.Event) -> None:
    wait = POLL_SECONDS
    rt = _RelayRuntime(ctx)
    while not stop.wait(wait):
        try:
            # Outside the gateway's and dashboard's processes there is nothing to do; check again now and
            # then, in case this process becomes one of them.
            wait = POLL_SECONDS if (in_gateway_process() or in_dashboard_process()) else 30.0
            if wait == POLL_SECONDS:
                relay_once(rt, data_dir=data_dir)
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
        t = threading.Thread(target=_loop, args=(ctx, Path(data_dir), stop), name="alchemy-task-handoff-relay",
                             daemon=True)
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
    except Exception:  # noqa: BLE001 - Send to chat reports the missing relay as not picked up
        pass
    try:
        ctx.on_unload(stop_relay)
    except Exception:  # noqa: BLE001
        pass
