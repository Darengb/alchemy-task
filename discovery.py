"""Discovery stream setup and compatibility entrypoints.

Saved source-first runs, research acceptance, global join, guarded conversion and
immutable numbered reviews are implemented by discovery_integration. Stream
schedule, labels and origin-chat UX remain here.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from typing import Any

from .core import taskfile as tf
from .core.config import validate_area_name
from .core.store import NeedsInput
from .runtime import Runtime

PREFIX = "alchemy-task"
DEFAULT_CAP = 50
KEEP_DAYS = 7
SOURCE_TYPES = ("email", "chat", "transcript", "meeting_notes", "document", "tracker", "other")
TIME_CHOICES = ("6:00 PM (recommended)", "7:00 PM", "9:00 AM", "8:00 AM", "Other")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9 -]{0,39}$")
_lock = threading.Lock()


class DiscoveryError(ValueError):
    pass


# ------------------------------------------------------------------ state

def _streams(rt: Runtime) -> dict[str, dict[str, Any]]:
    return rt.ctx.state.get("streams", default={}) or {}


def _save_streams(rt: Runtime, streams: dict[str, dict[str, Any]]) -> None:
    rt.ctx.state.set("streams", streams)


def _props(rt: Runtime, name: str) -> dict[str, Any]:
    return rt.ctx.state.get(f"proposals:{name}", default={"items": {}, "digest": []}) or {"items": {}, "digest": []}


def _save_props(rt: Runtime, name: str, data: dict[str, Any]) -> None:
    rt.ctx.state.set(f"proposals:{name}", data)


def _seen(rt: Runtime) -> dict[str, dict[str, Any]]:
    return rt.ctx.state.get("discovery_seen", default={}) or {}


def _norm_name(name: str) -> str:
    name = " ".join(str(name or "").lower().split())
    if not _NAME_RE.match(name):
        raise DiscoveryError("stream name: 1-40 lowercase letters, digits, spaces or hyphens (for example 'work')")
    return name


def _get(rt: Runtime, name: str) -> dict[str, Any]:
    streams = _streams(rt)
    if name:
        key = _norm_name(name)
        if key not in streams:
            raise DiscoveryError(f"no discovery stream named {key!r}; streams: {', '.join(streams) or 'none'}")
        return streams[key]
    if len(streams) == 1:
        return next(iter(streams.values()))
    raise DiscoveryError(f"say which stream: {', '.join(streams) or 'none set up yet'}")


# ------------------------------------------------------------------ schedule

def parse_time(text: str) -> tuple[int, int]:
    """'6 PM', '6:30pm', '18:00', '9 am' -> (hour, minute)."""
    t = str(text or "").strip().lower().replace(".", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?:\s*\(recommended\))?$", t)
    if not m:
        raise DiscoveryError("time must look like 6 PM, 7:30 PM or 18:00")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm:
        if not 1 <= hour <= 12:
            raise DiscoveryError("hour must be 1-12 with AM/PM")
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise DiscoveryError("not a valid time")
    return hour, minute


def schedule_for(frequency: str, at: str) -> tuple[str, str]:
    """Returns (cron expression, human description)."""
    freq = (frequency or "daily").strip().lower()
    if freq == "daily":
        h, m = parse_time(at or "6 PM")
        label = dt.time(h, m).strftime("%-I:%M %p")
        return f"{m} {h} * * *", f"daily at {label}"
    if freq == "weekdays":
        h, m = parse_time(at or "6 PM")
        return f"{m} {h} * * 1-5", f"weekdays at {dt.time(h, m).strftime('%-I:%M %p')}"
    hours = {"hourly": 1, "every 2 hours": 2, "every 3 hours": 3, "every 4 hours": 4}.get(freq)
    if hours:
        return f"5 */{hours} * * *" if hours > 1 else "5 * * * *", freq
    raise DiscoveryError("frequency: daily (default), weekdays, hourly, every 2/3/4 hours")


# ------------------------------------------------------------------ streams

def create_stream(rt: Runtime, args: dict[str, Any], session_id: str) -> dict[str, Any]:
    from . import setup_flow as sf
    name = _norm_name(args.get("name", ""))
    streams = _streams(rt)
    if name in streams:
        raise DiscoveryError(f"a stream named {name!r} exists; use action=update to change it")
    if not args.get("user_approved"):
        raise DiscoveryError("show the user the stream (sources, areas, schedule, chat, cost) and ask once; call again "
                             "with user_approved=true after they agree")
    tz = sf._timezone_state(rt)
    if tz["likely_unset"]:
        raise DiscoveryError("confirm the user's timezone first (setup step 1)")
    known = rt.settings.known_areas()
    areas = [validate_area_name(a) for a in (args.get("areas") or [])] or known
    unknown = [a for a in areas if a not in known]
    if unknown:
        raise DiscoveryError(f"unknown area(s) {', '.join(unknown)}; known: {', '.join(known)}")
    sources = create_args_sources(args.get("sources") or [])
    if not sources:
        raise DiscoveryError("a stream needs at least one approved source")
    cron, when = schedule_for(args.get("frequency", "daily"), args.get("time", "6 PM"))
    deliver = str(args.get("deliver") or "origin").strip()
    job_args = {"action": "create", "name": f"{PREFIX}: discovery {name}", "schedule": cron,
                "timezone": tz["timezone"] or "UTC", "deliver": deliver, "attach_to_session": True,
                "skills": ["alchemy-task:discovery"]}
    from .jobs import discovery_job_config
    job_args.update(discovery_job_config(name, [toolset for source in sources for toolset in source.get('toolsets', [])]))
    from .jobs import parse_job_id
    raw = rt.ctx.dispatch_tool("cronjob_manage", job_args)
    job_id = parse_job_id(raw)
    if not job_id:
        raise DiscoveryError(f"could not create the scheduled job: {str(raw)[:300]}")
    stream = {"name": name, "areas": areas, "sources": sources, "schedule": cron, "when": when,
              "frequency": args.get("frequency", "daily"), "time": args.get("time", "6 PM"),
              "timezone": tz["timezone"], "deliver": deliver, "origin_session": session_id, "job_id": job_id,
              "research_cap": max(0, min(int(args.get("research_cap", DEFAULT_CAP)), 200)),
              "created_at": time.time(), "last_run": None, "label": ""}
    with _lock:
        streams = _streams(rt)
        streams[name] = stream
        _assign_labels(streams)
        _save_streams(rt, streams)
    return {"stream": _public(stream), "job_id": job_id,
            "message": f"Discovery stream '{name}' runs {when} ({tz['timezone']}) and posts its digest "
                       f"{'in this chat' if deliver == 'origin' else 'to ' + deliver}."}


def _assign_labels(streams: dict[str, dict[str, Any]]) -> None:
    """Plain numbers, unless several streams post into the same chat: then a letter prefix (W1, H2)."""
    by_chat: dict[str, list[str]] = {}
    for name, s in streams.items():
        by_chat.setdefault(f"{s.get('deliver')}|{s.get('origin_session')}", []).append(name)
    for names in by_chat.values():
        used: set[str] = set()
        for name in sorted(names):
            if len(names) == 1:
                streams[name]["label"] = ""
                continue
            letter = next((c.upper() for c in name if c.isalpha() and c.upper() not in used), str(len(used) + 1))
            used.add(letter)
            streams[name]["label"] = letter


def _public(s: dict[str, Any]) -> dict[str, Any]:
    return {k: s.get(k) for k in ("name", "areas", "sources", "when", "timezone", "deliver", "research_cap",
                                  "last_run", "label", "job_id")}


def update_stream(rt: Runtime, args: dict[str, Any], session_id: str) -> dict[str, Any]:
    """Change a stream in place. The job is updated, not recreated, so it keeps posting to its own chat."""
    current = _get(rt, args.get("name", ""))
    if not args.get("user_approved"):
        raise DiscoveryError("confirm the change with the user, then call again with user_approved=true")
    if args.get("deliver") and args["deliver"] != current.get("deliver"):
        raise DiscoveryError("a stream posts where it was created; to move it, remove it and create it again from "
                             "the chat (or Telegram topic) that should receive it")
    try:
        cap = max(0, min(int(args.get("research_cap", current["research_cap"])), 200))
    except (TypeError, ValueError) as exc:
        raise DiscoveryError("research_cap must be a whole number") from exc
    frequency = args.get("frequency") or current.get("frequency") or "daily"
    if args.get("time") and not args.get("frequency") and frequency not in ("daily", "weekdays"):
        frequency = "daily"  # "change it to 9 AM" on an hourly stream means once a day at 9 AM
    at = args.get("time") or current.get("time") or "6 PM"
    cron, when = (schedule_for(frequency, at) if (args.get("frequency") or args.get("time"))
                  else (current["schedule"], current["when"]))
    known = rt.settings.known_areas()
    areas = [validate_area_name(a) for a in (args.get("areas") or current["areas"])]
    if [a for a in areas if a not in known]:
        raise DiscoveryError(f"unknown area; known: {', '.join(known)}")
    sources = list(current["sources"])
    if args.get("sources"):
        sources = create_args_sources(args["sources"])  # explicit full replacement
    added, removed = [], []
    for src in create_args_sources(args.get("add_sources") or []):
        existing = [i for i, s in enumerate(sources) if s["name"].lower() == src["name"].lower()]
        if existing:
            sources[existing[0]] = src
        else:
            sources.append(src)
        added.append(src["name"])
    for name in args.get("remove_sources") or []:
        keep = [s for s in sources if s["name"].lower() != str(name).strip().lower()]
        if len(keep) == len(sources):
            raise DiscoveryError(f"no source named {name!r} in this stream; sources: "
                                 f"{', '.join(s['name'] for s in sources)}")
        sources = keep
        removed.append(str(name))
    if not sources:
        raise DiscoveryError("a stream needs at least one source; remove the stream instead")
    from .setup_flow import _timezone_state
    tz = _timezone_state(rt)["timezone"] or current.get("timezone") or "UTC"
    raw = rt.ctx.dispatch_tool("cronjob_manage", {"action": "update", "job_id": current["job_id"],
                                                  "schedule": cron, "timezone": tz})
    try:
        result = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (TypeError, ValueError):
        result = {"error": str(raw)[:300]}
    if result.get("success") is False or result.get("error"):
        raise DiscoveryError(f"could not update the scheduled job: {str(result.get('error') or raw)[:300]}")
    with _lock:
        streams = _streams(rt)
        s = streams[current["name"]]
        s.update({"schedule": cron, "when": when, "frequency": frequency, "time": at, "timezone": tz,
                  "areas": areas, "sources": sources,
                  "research_cap": cap})
        _save_streams(rt, streams)
    msg = f"Updated '{s['name']}': {when} ({tz}), still posting to its own chat."
    if added:
        msg += f" Added source(s): {', '.join(added)}."
    if removed:
        msg += f" Removed source(s): {', '.join(removed)}."
    msg += " Sources now: " + "; ".join(f"{x['name']} ({x['scope']})" for x in sources) + "."
    return {"stream": _public(s), "message": msg}


def create_args_sources(raw_sources: list[Any]) -> list[dict[str, str]]:
    sources = []
    for src in raw_sources or []:
        if not isinstance(src, dict) or not str(src.get("name") or "").strip():
            raise DiscoveryError("each source needs a name, type, scope (what to read) and method (which tool)")
        stype = str(src.get("type") or "other").strip().lower()
        sources.append({"name": " ".join(str(src["name"]).split())[:80],
                        "type": stype if stype in SOURCE_TYPES else "other",
                        "scope": " ".join(str(src.get("scope") or "").split())[:400],
                        "method": " ".join(str(src.get("method") or "").split())[:300]})
        if src.get('toolsets'):
            if not isinstance(src['toolsets'], list) or any(not isinstance(t, str) or not t for t in src['toolsets']):
                raise DiscoveryError('source toolsets must name the existing approved reader toolsets')
            sources[-1]['toolsets'] = list(dict.fromkeys(src['toolsets']))
    return sources


def remove_stream(rt: Runtime, name: str) -> dict[str, Any]:
    stream = _get(rt, name)
    _remove_job(rt, stream.get("job_id"))
    with _lock:
        streams = _streams(rt)
        streams.pop(stream["name"], None)
        _assign_labels(streams)
        _save_streams(rt, streams)
    rt.ctx.state.set(f"proposals:{stream['name']}", None)
    return {"removed": stream["name"]}


def _remove_job(rt: Runtime, job_id: str | None) -> None:
    if job_id:
        try:
            rt.ctx.dispatch_tool("cronjob_manage", {"action": "remove", "job_id": job_id})
        except Exception:  # noqa: BLE001
            pass


def teardown_streams(rt: Runtime) -> list[str]:
    names = list(_streams(rt))
    for name in names:
        remove_stream(rt, name)
    return names


def status_summary(rt: Runtime) -> dict[str, Any]:
    streams = _streams(rt)
    return {"ready": bool(streams), "streams": len(streams),
            "names": [f"{n} ({s['when']})" for n, s in streams.items()]}


# ------------------------------------------------------------------ saved-run compatibility

def _today(rt: Runtime) -> str:
    return rt.settings.today()


def start(rt: Runtime, name: str, session_id: str = "") -> dict[str, Any]:
    from .discovery_integration import get_service
    return get_service(rt).start(name, session_id=session_id)


def submit(rt: Runtime, name: str, candidates=None, coverage=None, *, run_id="", session_id="") -> dict[str, Any]:
    """Compatibility alias only. Freeform notes cannot bypass research/join."""
    from .core.discovery_identity import UserError
    from .discovery_integration import get_service
    if candidates or coverage or not run_id:
        raise UserError("discovery_submit requires saved run_id after full source-first research/global join; freeform candidates are not proposals")
    return get_service(rt).finalize(run_id, session_id=session_id)


def decide(rt: Runtime, args: dict[str, Any], session_id: str = "") -> dict[str, Any]:
    from .discovery_integration import get_service
    return get_service(rt).decide(args, session_id=session_id)


def pre_llm_call(session_id: str = "", **_: Any):
    if not session_id:
        return None
    from .discovery_integration import get_service
    service = get_service(Runtime())
    data = service.digest._load()
    pending = [p for p in data['proposals'].values() if p['binding']['origin']['session_id'] == session_id
               and p['binding']['expires'] >= service.rt.settings.today() and p['state'] in {'pending', 'approved'}]
    if pending:
        return {"context": "[Alchemy Task] This chat has immutable discovery proposals. Resolve replies by exact proposal number/day/stream with discovery_decide. Selecting one never closes the others. Semantic matches need update/create choice and exact target_task_id; never use title guesses. Ignored items remain replyable seven days."}
    return None


def register(ctx: Any) -> None:
    ctx.register_hook("pre_llm_call", pre_llm_call)
