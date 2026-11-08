"""Discovery streams: scheduled task suggestions from sources the user already reads with Hermes.

A stream is a named configuration (areas, approved sources, schedule, delivery
chat, research cap). Each stream runs as its own cron job created from inside
the chat that should receive its digest (``deliver: origin``). The job's agent
reads only the stream's approved sources with the user's own tools, then
submits candidates here. The plugin de-duplicates them (against earlier
proposals in every stream and against existing tasks), numbers them and returns
the digest the job delivers. Replies such as "1 and 3" in that chat go to
``discovery_decide``, which creates the tasks (with research, as usual).
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
                "skills": ["alchemy-task:discovery"],
                "prompt": (f"Run the Alchemy Task discovery stream \"{name}\". Load the skill alchemy-task:discovery "
                           f"and follow it: call discovery_start with stream \"{name}\", read only the approved "
                           "sources it lists, then call discovery_submit. Your final reply is the digest the tool "
                           "returns, unchanged.")}
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
    at = args.get("time") or current.get("time") or "6 PM"
    cron, when = (schedule_for(frequency, at) if (args.get("frequency") or args.get("time"))
                  else (current["schedule"], current["when"]))
    known = rt.settings.known_areas()
    areas = [validate_area_name(a) for a in (args.get("areas") or current["areas"])]
    if [a for a in areas if a not in known]:
        raise DiscoveryError(f"unknown area; known: {', '.join(known)}")
    sources = current["sources"]
    if args.get("sources"):
        probe = create_args_sources(args["sources"])
        sources = probe
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
    return {"stream": _public(s), "message": f"Updated '{s['name']}': {when} ({tz}), still posting to its own chat."}


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


# ------------------------------------------------------------------ a run

def _today(rt: Runtime) -> str:
    return rt.settings.today()


def _researched_today(props: dict[str, Any], today: str) -> int:
    return int((props.get("researched_by_day") or {}).get(today, 0))


def start(rt: Runtime, name: str) -> dict[str, Any]:
    stream = _get(rt, name)
    props = _props(rt, stream["name"])
    today = _today(rt)
    since = stream.get("last_run")
    window = (f"since {dt.datetime.fromtimestamp(since).isoformat(timespec='minutes')}" if since
              else "the last 24 hours (first run)")
    open_tasks = [{"task_id": t.task_id, "title": t.title, "area": t.fm.get("area")}
                  for t in rt.store().find(status="open", limit=100)
                  if not stream["areas"] or t.fm.get("area") in stream["areas"]]
    return {"stream": stream["name"], "areas": stream["areas"], "sources": stream["sources"], "window": window,
            "since_epoch": since, "today": today,
            "research_remaining_today": max(0, stream["research_cap"] - _researched_today(props, today)),
            "already_proposed_source_ids": sorted(_seen(rt))[-300:],
            "open_tasks": open_tasks,
            "instructions": ("Read only these sources, only the window given, with the tools named in each source's "
                             "method. Look for commitments, requests, decisions and follow-ups that belong to the "
                             "user. Skip anything in already_proposed_source_ids and anything an open task covers. "
                             "Then call discovery_submit with candidates and a coverage entry for every source.")}


def submit(rt: Runtime, name: str, candidates: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> dict[str, Any]:
    stream = _get(rt, name)
    today = _today(rt)
    now = time.time()
    store = rt.store()
    open_docs = store.find(status="open", limit=100)
    with _lock:
        props = _props(rt, stream["name"])
        seen = _seen(rt)
        cap_left = max(0, stream["research_cap"] - _researched_today(props, today))
        if props.get("num_day") != today:  # numbers restart each day and run on through that day's digests
            props["num_day"], props["next_num"] = today, 1
        added, skipped, new_items = 0, [], []
        for raw in (candidates or [])[:40]:
            if not isinstance(raw, dict):
                continue
            title = " ".join(str(raw.get("title") or "").split())[:200]
            source_id = " ".join(str(raw.get("source_id") or "").split())[:300]
            if not title or not source_id:
                skipped.append({"title": title, "why": "missing title or source_id"})
                continue
            if source_id in seen or source_id in props["items"]:
                skipped.append({"title": title, "why": "already proposed"})
                continue
            dup = next((d for d in open_docs if tf.title_similarity(d.title, title) >= 0.6 or
                        (source_id and source_id in d.body)), None)
            if dup:
                skipped.append({"title": title, "why": f"open task exists: {dup.title}"})
                seen[source_id] = {"stream": stream["name"], "at": now, "outcome": "existing"}
                continue
            area = str(raw.get("area") or "").strip().lower()
            if area not in stream["areas"]:
                area = stream["areas"][0] if len(stream["areas"]) == 1 else ""
            research = " ".join(str(raw.get("research_notes") or "").split())[:2000]
            researched = bool(research) and cap_left > 0
            if researched:
                cap_left -= 1
                counts = props.setdefault("researched_by_day", {})
                counts[today] = counts.get(today, 0) + 1
            elif research:
                research = ""
            try:
                due = tf.validate_date(raw.get("due_hint"), "due_hint") if raw.get("due_hint") else None
            except tf.TaskFormatError:
                due = None  # a malformed hint is dropped, not fatal
            num = int(props.get("next_num") or 1)
            props["next_num"] = num + 1
            stype = str(raw.get("source_type") or "other").lower()
            props["items"][source_id] = {
                "title": title, "area": area, "source_id": source_id,
                "source_type": stype if stype in SOURCE_TYPES else "other",
                "source": " ".join(str(raw.get("source") or "").split())[:200],
                "link": str(raw.get("link") or "").strip()[:500],
                "summary": " ".join(str(raw.get("summary") or "").split())[:1000],
                "why": " ".join(str(raw.get("why") or "").split())[:500],
                "due": due, "num": num,
                "research_notes": research, "researched": researched, "day": today, "at": now, "state": "open"}
            seen[source_id] = {"stream": stream["name"], "at": now, "outcome": "proposed"}
            new_items.append(props["items"][source_id])
            added += 1
        cutoff = now - KEEP_DAYS * 86400
        for sid in [k for k, p in props["items"].items() if p["at"] < cutoff or not p.get("num")]:
            props["items"].pop(sid)  # unpicked items stay replyable for 7 days but are never re-listed
        for sid in [k for k, v in seen.items() if v.get("at", 0) < now - 60 * 86400]:
            seen.pop(sid)
        props["digest"] = [p["source_id"] for p in new_items]
        props["researched_by_day"] = {d: n for d, n in (props.get("researched_by_day") or {}).items() if d >= today}
        props["digest_at"] = now
        _save_props(rt, stream["name"], props)
        rt.ctx.state.set("discovery_seen", seen)
        streams = _streams(rt)
        if stream["name"] in streams:
            streams[stream["name"]]["last_run"] = now
            _save_streams(rt, streams)
    digest = render_digest(stream, new_items, coverage or [], today)
    return {"added": added, "skipped": skipped, "digest": digest}


def render_digest(stream: dict[str, Any], items: list[dict[str, Any]], coverage: list[dict[str, Any]],
                  today: str) -> str:
    """One digest lists only this run's new items. Numbers restart each day and continue across that day's runs."""
    label = stream.get("label") or ""
    lines = [f"**{stream['name'].title()} discovery** · {today}"]
    if not items:
        lines.append("Nothing new that needs a task.")
    for p in items:
        bits = [f"**{label}{p['num']}.** {p['title']}"]
        meta = [x for x in (p["area"], f"due {p['due']}" if p["due"] else "", p["source"]) if x]
        if meta:
            bits.append(f"({', '.join(meta)})")
        line = " ".join(bits)
        if p["why"]:
            line += f": {p['why']}"
        if p["link"]:
            line += f" [source]({p['link']})"
        lines.append(line)
    problems = [c for c in coverage if isinstance(c, dict) and str(c.get("status") or "ok").lower() != "ok"]
    covered = [str(c.get("source")) for c in coverage if isinstance(c, dict) and str(c.get("status")).lower() == "ok"]
    if covered:
        lines.append("Checked: " + ", ".join(covered) + ".")
    for c in problems:
        lines.append(f"⚠️ {c.get('source')}: {c.get('status')}" + (f" ({c.get('note')})" if c.get("note") else ""))
    if items:
        example = f"{label}{items[0]['num']}" + (f" and {label}{items[1]['num']}" if len(items) > 1 else "")
        lines.append(f"Reply with the numbers you want as tasks (for example \"{example}\"); the rest are left alone.")
    return "\n".join(lines)


# ------------------------------------------------------------------ decisions

def _day_of(rt: Runtime, day: str) -> str:
    text = str(day or "").strip().lower()
    if not text or text == "today":
        return ""
    if text == "yesterday":
        return (dt.date.fromisoformat(_today(rt)) - dt.timedelta(days=1)).isoformat()
    try:
        return tf.validate_date(text, "day") or ""
    except tf.TaskFormatError as exc:
        raise DiscoveryError("day must be today, yesterday or YYYY-MM-DD") from exc


def _recent(props: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in props["items"].values() if p.get("num")]


def _resolve_numbers(rt: Runtime, refs: list[Any], stream_name: str, day: str = "") -> list[tuple[dict[str, Any],
                                                                                               dict[str, Any]]]:
    """A bare number means today's numbering, or the latest day with a digest if none posted today yet."""
    streams = _streams(rt)
    want_day = _day_of(rt, day)
    today = _today(rt)
    out = []
    for ref in refs:
        text = str(ref).strip().upper()
        m = re.match(r"^([A-Z]?)(\d+)$", text)
        if not m:
            raise DiscoveryError(f"{ref!r} is not a proposal number")
        letter, num = m.group(1), int(m.group(2))
        if stream_name:
            candidates = [_get(rt, stream_name)]
        elif letter:
            candidates = [s for s in streams.values() if s.get("label") == letter]
        else:
            live = [s for s in streams.values() if _recent(_props(rt, s["name"]))]
            candidates = live if len(live) == 1 else []
            if len(live) > 1:
                raise DiscoveryError("several streams have recent digests; pass stream, or use the letter prefix")
        if not candidates:
            raise DiscoveryError(f"no recent discovery digest matches {ref!r}")
        stream = candidates[0]
        items = _recent(_props(rt, stream["name"]))
        target = want_day or (today if any(p["day"] == today for p in items)
                              else max((p["day"] for p in items), default=today))
        match = [p for p in items if p["day"] == target and p["num"] == num]
        if not match:
            nums = sorted(p["num"] for p in items if p["day"] == target)
            raise DiscoveryError(f"{ref!r} is not in the {stream['name']} digest for {target} (numbers: "
                                 f"{', '.join(str(n) for n in nums) or 'none'})")
        if match[0]["state"] == "approved":
            raise DiscoveryError(f"{ref!r} ({match[0]['title']}) was already added as a task")
        if all(p["source_id"] != match[0]["source_id"] for _, p in out):
            out.append((stream, match[0]))
    return out


def decide(rt: Runtime, args: dict[str, Any], session_id: str = "") -> dict[str, Any]:
    stream_name = args.get("stream", "")
    approve = _resolve_numbers(rt, args.get("approve") or [], stream_name, args.get("day", ""))
    dismiss = _resolve_numbers(rt, args.get("dismiss") or [], stream_name, args.get("day", ""))
    approved_ids = {p["source_id"] for _, p in approve}
    dismiss = [(s, p) for s, p in dismiss if p["source_id"] not in approved_ids]
    edits = {str(k).strip().upper(): v for k, v in (args.get("edits") or {}).items() if isinstance(v, dict)}
    numbered = {p["source_id"]: f"{s.get('label') or ''}{p['num']}" for s, p in approve}
    known = rt.settings.known_areas()
    missing, invalid = [], []
    for stream, p in approve:
        ref = numbered[p["source_id"]]
        e = edits.get(ref, edits.get(str(p["num"]), {}))
        if e.get("due"):
            try:
                e["due"] = tf.parse_date_words(e["due"], _today(rt), "due")
            except tf.TaskFormatError as exc:
                invalid.append(f"{ref}: {exc}")
        if e.get("priority") and str(e["priority"]).lower() not in tf.PRIORITIES:
            invalid.append(f"{ref}: priority must be one of {', '.join(tf.PRIORITIES)}")
        if e.get("area") and str(e["area"]).lower() not in known:
            invalid.append(f"{ref}: unknown area {e['area']!r} (known: {', '.join(known)})")
        if not (e.get("due") or p.get("due") or e.get("undated")):
            missing.append(ref)
        if not (e.get("area") or p.get("area")):
            missing.append(ref + " (area)")
    if invalid:
        raise NeedsInput("fix_call", "Fix these edits and call again (nothing was created): " + "; ".join(invalid))
    if missing:
        raise NeedsInput("due", "Ask the user for a due date (or 'no due date') for: " + ", ".join(missing) +
                         ", then pass them in edits, e.g. {\"1\": {\"due\": \"2026-11-20\"}}.",
                         areas=rt.settings.known_areas())
    store = rt.store()
    created, results, done = [], [], []
    for stream, p in approve:
        ref = numbered[p["source_id"]]
        e = edits.get(ref, edits.get(str(p["num"]), {}))
        notes = [f"Found by the {stream['name']} discovery stream on {p['day']} from {p['source'] or p['source_type']}."]
        if p["summary"]:
            notes.append(p["summary"])
        if p["why"]:
            notes.append(f"Why it matters: {p['why']}")
        if p["link"]:
            notes.append(f"Source: {p['link']}")
        notes.append(f"Source ID: `{p['source_id']}`")
        if p["research_notes"]:
            notes.append("Discovery research: " + p["research_notes"])
        try:
            doc = store.create(title=e.get("title") or p["title"], area=e.get("area") or p["area"],
                               due=e.get("due") or p.get("due") or "", undated=bool(e.get("undated")),
                               priority=e.get("priority", "normal"), notes="\n\n".join(notes), confirm_new=True,
                               source=f"{stream['name']} discovery")
        except (NeedsInput, tf.TaskFormatError) as exc:
            results.append({"number": ref, "error": getattr(exc, "message", str(exc))})
            continue
        created.append(doc)
        done.append((stream, p))
        results.append({"number": ref, "task_id": doc.task_id, "title": doc.title, "area": doc.fm.get("area"),
                        "due": tf.norm_date(doc.fm.get("due"))})
    _mark(rt, done, "approved")  # failures stay open for a retry
    _mark(rt, dismiss, "dismissed")
    return {"created": created, "results": results, "dismissed": [p["title"] for _, p in dismiss]}


def _mark(rt: Runtime, pairs: list[tuple[dict[str, Any], dict[str, Any]]], state: str) -> None:
    if not pairs:
        return
    with _lock:
        seen = _seen(rt)
        for stream, p in pairs:
            props = _props(rt, stream["name"])
            if p["source_id"] in props["items"]:
                props["items"][p["source_id"]]["state"] = state
            _save_props(rt, stream["name"], props)
            seen[p["source_id"]] = {"stream": stream["name"], "at": time.time(), "outcome": state}
        rt.ctx.state.set("discovery_seen", seen)


def pre_llm_call(session_id: str = "", **_: Any):
    if not session_id:
        return None
    try:
        rt = Runtime()
        streams = [s for s in _streams(rt).values() if s.get("origin_session") == session_id]
    except Exception:  # noqa: BLE001
        return None
    live = [s for s in streams if _recent(_props(rt, s["name"]))]
    if not live:
        return None
    names = ", ".join(f"{s['name']}" + (f" (numbers start with {s['label']})" if s.get("label") else "") for s in live)
    return {"context": f"[Alchemy Task] This chat receives discovery digests for: {names}. If the user replies with "
                       "proposal numbers, call discovery_decide with approve. Numbers restart each day: a bare number means "
                       "today's digests (or the latest day if none posted today); pass day=yesterday or a date when the "
                       "user refers to an earlier digest. Unpicked items need no action."}


def register(ctx: Any) -> None:
    ctx.register_hook("pre_llm_call", pre_llm_call)
