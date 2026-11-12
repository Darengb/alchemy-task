"""Code run by scheduled-job stubs under Hermes's Python (no plugin context).

- ``research_wake``: free pre-check for the research sweep (``wakeAgent``).
- ``maintenance``: validator (assign missing IDs) plus push retry. Prints only
  when something changed or a new problem appeared, so quiet runs are silent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import research as rs
from . import validator
from .config import Settings
from .gitops import GitDelivery
from .store import TaskStore


def _settings() -> Settings:
    from hermes_cli.config import load_config_readonly  # public Hermes module
    cfg = load_config_readonly() or {}
    entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("alchemy-task") or {}
    settings = entry.get("settings") or {}

    def get(key: str, default: Any = None) -> Any:
        return settings.get(key, default)

    return Settings.load(get, str(cfg.get("timezone") or ""))


def research_wake(settings: Settings | None = None, data_dir: str = "") -> dict[str, Any]:
    """``{"wakeAgent": false}`` unless some task is waiting for research."""
    try:
        s = settings or _settings()
        if not s.configured:
            return {"wakeAgent": False}
        store = TaskStore(s, Path(data_dir or "/nonexistent-precheck"))  # read-only scan
        waiting = [t.title for t in store.scan().tasks if rs.eligibility(t.fm, rs.model_key(s)) == "eligible"]
        # with the current model setting, so a task blocked by an earlier setting wakes the sweep
    except Exception:  # noqa: BLE001 - a broken pre-check must not wake the model every tick
        return {"wakeAgent": False}
    if not waiting:
        return {"wakeAgent": False}
    return {"wakeAgent": True, "waiting": len(waiting), "examples": waiting[:3]}


def maintenance(data_dir: str, settings: Settings | None = None) -> str:
    """Assign missing IDs, retry unpushed commits. Returns text to deliver, or "" when nothing changed.

    Every reportable condition (file problems, push state, errors) goes into one digest; a message is
    sent only when that digest changes, so a lasting problem is reported once, and again when it clears.
    """
    data = Path(data_dir)
    lines: list[str] = []
    condition: dict[str, Any] = {}
    try:
        s = settings or _settings()
        if not s.configured:
            return ""
        store = TaskStore(s, data)
        report = validator.validate(store, apply=True)
        git = GitDelivery(s, data)
        if report["changed_paths"]:
            receipt = git.deliver(report["changed_paths"], "task: assign missing task IDs")
            lines.append(f"Assigned IDs to {len(report['changed_paths'])} task(s).")
        push_state = "ok"
        if s.git_transport != "none" and git.status().get("needs_push"):
            r = git.retry()
            if r.get("pushed"):
                lines.append("Pushed task changes that were waiting.")
            else:
                err = str(r.get("error") or r.get("state") or "")
                import re
                push_state = re.split(r":| \(", err)[0].strip()[:80] or "not pushed"
        condition["push"] = push_state
        condition["problems"] = {k: report[k] for k in ("unsupported", "malformed", "unknown_status",
                                                         "done_without_completed", "area_mismatch",
                                                         "duplicate_task_ids")}
        summary = validator.summarize(report) if report["problems"] else ""
    except Exception as exc:  # noqa: BLE001 - report once, never fail every hour
        condition = {"error": f"{exc.__class__.__name__}: {str(exc)[:120]}"}
        summary = ""
    digest = hashlib.sha256(json.dumps(condition, sort_keys=True, default=str).encode()).hexdigest()
    marker = data / "maintenance-state.sha"
    (data / "maintenance-problems.sha").unlink(missing_ok=True)  # pre-0.1 marker name
    previous = marker.read_text().strip() if marker.exists() else ""
    if digest != previous:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest)
        if "error" in condition:
            lines.append(f"The hourly check failed: {condition['error']}. Run /task status.")
        else:
            push_ok = condition["push"] == "ok"
            if not push_ok:
                lines.append(f"Task changes are committed but not pushed ({condition['push']}). Retrying hourly; "
                             "run /task push after fixing it.")
            if summary:
                lines.append("Task file check: " + summary + " Run /task validate for details.")
            if previous and push_ok and not summary and not lines:
                lines.append("Earlier problems are resolved.")
    if lines:
        return "Alchemy Task: " + " ".join(lines)
    return ""


# ------------------------------------------------------------------ discovery stream wake check
#
# Each discovery stream's job ticks every 30 minutes behind this free check. It wakes the agent only when
# the stream's own slot (the user's frequency and time, in the stream's timezone) has come and not run yet,
# a "run now" was asked for from a chat or the dashboard, or a follow-up is pending (a run left research
# queued). The check only reads plugin state; the run itself records what it consumed.

STREAM_TICK = "*/30 * * * *"
SLOT_STATE = "discovery_slots"
FOLLOW_UP_STATE = "discovery_follow_ups"
RUN_REQUEST_STATE = "discovery_run_requests"
SLOT_LOOKBACK = 12 * 60          # minutes: a slot missed for longer than this waits for the next one
RUN_REQUEST_TTL = 45 * 60        # seconds a "run now" request stays valid
FOLLOW_UP_TTL = 20 * 3600        # seconds a pending follow-up stays valid
ACTIVE_STALE = 6 * 3600          # seconds after which an unfinished run no longer blocks a follow-up


def _cron_field(spec: str, value: int, low: int, high: int) -> bool:
    for part in str(spec).split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            start, end = (int(x) for x in part.split("-", 1))
        else:
            start = end = int(part)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def _cron_matches(schedule: str, local: Any) -> bool:
    minute, hour, dom, month, dow = str(schedule).split()
    cron_dow = (local.weekday() + 1) % 7
    return (_cron_field(minute, local.minute, 0, 59) and _cron_field(hour, local.hour, 0, 23)
            and _cron_field(dom, local.day, 1, 31) and _cron_field(month, local.month, 1, 12)
            and (_cron_field(dow, cron_dow, 0, 7) or (cron_dow == 0 and _cron_field(dow, 7, 0, 7))))


def _now(now: Any = None) -> Any:
    import datetime as dt
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).replace(second=0, microsecond=0)


def _zone(name: str) -> Any:
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(name or "UTC")
    except Exception:  # noqa: BLE001 - unknown zone: UTC
        return ZoneInfo("UTC")


def latest_slot(schedule: str, timezone: str, now: Any = None, lookback: int = SLOT_LOOKBACK) -> Any:
    """The most recent instant (UTC) at or before now that the stream's own schedule names, within lookback."""
    import datetime as dt
    cur, zone = _now(now), _zone(timezone)
    for _ in range(lookback + 1):
        if _cron_matches(schedule, cur.astimezone(zone)):
            return cur
        cur -= dt.timedelta(minutes=1)
    return None


def next_slot(schedule: str, timezone: str, now: Any = None, horizon_days: int = 8) -> Any:
    """The next instant (UTC) after now that the stream's own schedule names (for display)."""
    import datetime as dt
    cur, zone = _now(now) + dt.timedelta(minutes=1), _zone(timezone)
    for _ in range(horizon_days * 24 * 60):
        if _cron_matches(schedule, cur.astimezone(zone)):
            return cur
        cur += dt.timedelta(minutes=1)
    return None


def _when(value: Any) -> Any:
    import datetime as dt
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def discovery_wake(get: Any, name: str, now: Any = None) -> dict[str, Any]:
    """Why the stream's job should run now: ``{"wakeAgent": true, "reason": "slot"|"run_now"|"follow_up"}``,
    else ``{"wakeAgent": false}``. ``get(key)`` reads one plugin state key; nothing is written."""
    import datetime as dt
    try:
        moment = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
        stream = (get("streams") or {}).get(name) or {}
        if not stream.get("job_id"):
            return {"wakeAgent": False}
        slot = latest_slot(stream.get("schedule") or "", stream.get("timezone") or "UTC", moment)
        done = ((get(SLOT_STATE) or {}).get(name) or {}).get("done")
        if slot is not None and (not done or slot > _when(done)):
            return {"wakeAgent": True, "reason": "slot", "stream": name, "slot": slot.isoformat()}
        request = (get(RUN_REQUEST_STATE) or {}).get(name) or {}
        if request.get("at") and 0 <= (moment - _when(request["at"])).total_seconds() <= RUN_REQUEST_TTL:
            return {"wakeAgent": True, "reason": "run_now", "stream": name}
        record = (get(FOLLOW_UP_STATE) or {}).get(name) or {}
        pending, active = record.get("pending") or {}, record.get("active") or {}
        busy = active.get("since") and (moment - _when(active["since"])).total_seconds() < ACTIVE_STALE
        if pending.get("at") and not busy and (moment - _when(pending["at"])).total_seconds() <= FOLLOW_UP_TTL:
            return {"wakeAgent": True, "reason": "follow_up", "stream": name}
    except Exception:  # noqa: BLE001 - a broken check must not wake the model every 30 minutes
        return {"wakeAgent": False}
    return {"wakeAgent": False}


def discovery_wake_file(data_dir: str, name: str) -> dict[str, Any]:
    """Stub entry point: read the plugin's state.json (read-only) and decide."""
    try:
        data = json.loads((Path(data_dir) / "state.json").read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 - no state yet or unreadable: nothing to do
        return {"wakeAgent": False}
    if not isinstance(data, dict):
        return {"wakeAgent": False}
    return discovery_wake(data.get, name)
