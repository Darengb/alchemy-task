"""Apple Reminders mirror: pure projection and three-way reconciliation (no Hermes imports).

Mirrored fields: title, due date (date only), completion. Everything else stays in Markdown.
For each field, with base B (last agreed value), local L and remote R:
  only L changed -> push; only R changed -> pull; both changed the same -> adopt; both differently -> conflict.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import taskfile as tf

FIELDS = ("title", "due", "completed")
CREATE_CUTOFF_DAYS = 14
MARKER_PREFIX = "Alchemy Task ·"


def marker(task_id: str) -> str:
    return f"{MARKER_PREFIX} task {task_id}"


NEXT_MAX = 200


def compose_notes(fm: Mapping[str, Any], body: str, task_id: str) -> str:
    """What the reminder's notes show: the task's summary (or the first sentence of its Notes), the next step from
    its latest checkpoint, then a one-line marker. Kept short because the phone shortens long notes."""
    import re
    summary = tf.clean_summary(fm.get("summary")) or tf.fallback_summary(body)
    parts = [summary] if summary else []
    state = ""
    if body.count(tf.CURRENT_STATE_START) == 1 and body.count(tf.CURRENT_STATE_END) == 1:
        state = body[body.index(tf.CURRENT_STATE_START): body.index(tf.CURRENT_STATE_END)]
    m = re.search(r"\*\*Next step:\*\*\s*(.+)", state)
    if m:
        nxt = tf.clean_summary(m.group(1))
        parts.append("Next: " + (nxt if len(nxt) <= NEXT_MAX else nxt[:NEXT_MAX - 1].rsplit(" ", 1)[0] + "…"))
    parts.append(marker(task_id))
    return "\n\n".join(parts)


def marker_task_id(notes: Any) -> str | None:
    text = str(notes or "")
    i = text.find(f"{MARKER_PREFIX} task ")
    if i < 0:
        return None
    cand = text[i + len(MARKER_PREFIX) + 6:].split()[0].rstrip(".")
    return cand if tf.valid_task_id(cand) else None


def local_projection(fm: Mapping[str, Any]) -> dict[str, Any]:
    return {"title": " ".join(str(fm.get("title") or "").split()),
            "due": tf.norm_date(fm.get("due")),
            "completed": str(fm.get("status") or "").strip().lower() in ("done", "completed", "complete")}


def remote_projection(reminder: Mapping[str, Any], tz: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(projection, native extras). A timed due becomes its calendar date in the workspace timezone; the time is
    kept in extras so unrelated pushes never overwrite it."""
    extras: dict[str, Any] = {}
    due = None
    if reminder.get("due_date"):
        due = tf.norm_date(reminder.get("due_date"))
    elif reminder.get("due"):
        raw = str(reminder["due"])
        try:
            when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=ZoneInfo(tz))
            due = when.astimezone(ZoneInfo(tz)).date().isoformat()
            extras["native_due"] = raw
        except ValueError:
            extras["bad_due"] = raw
    completed = bool(reminder.get("completed"))
    if completed and reminder.get("completed_at"):
        extras["completed_at"] = str(reminder["completed_at"])
    return {"title": " ".join(str(reminder.get("title") or "").split()), "due": due, "completed": completed}, extras


def completed_date(completed_at: str | None, tz: str) -> str | None:
    if not completed_at:
        return None
    try:
        when = dt.datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(ZoneInfo(tz)).date().isoformat()


def eligible_for_create(fm: Mapping[str, Any], today: str) -> tuple[bool, str]:
    """New reminders only for open tasks whose due date is at most 14 calendar days in the past."""
    if not tf.valid_task_id(fm.get("task_id")):
        return False, "no valid task_id"
    ok, why = tf.writable(dict(fm))
    if not ok:
        return False, why
    if str(fm.get("status") or "").strip().lower() != "open":
        return False, f"status is {fm.get('status')!r}, not open"
    due = tf.norm_date(fm.get("due"))
    if due:
        cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=CREATE_CUTOFF_DAYS)).isoformat()
        if due < cutoff:
            return False, f"due {due} is more than {CREATE_CUTOFF_DAYS} days ago"
    return True, ""


def reconcile(base: Mapping[str, Any], local: Mapping[str, Any], remote: Mapping[str, Any]) -> dict[str, Any]:
    push, pull, adopt, conflicts = {}, {}, {}, {}
    for f in FIELDS:
        b, l, r = base.get(f), local.get(f), remote.get(f)
        lc, rc = l != b, r != b
        if lc and rc:
            if l == r:
                adopt[f] = l
            else:
                conflicts[f] = {"base": b, "local": l, "native": r}
        elif lc:
            push[f] = l
        elif rc:
            pull[f] = r
    return {"push": push, "pull": pull, "adopt": adopt, "conflicts": conflicts}


def update_args(push: Mapping[str, Any]) -> tuple[dict[str, Any], bool | None]:
    """mobile_reminder_update fields for pushed title/due, plus the completion change (True/False/None)."""
    args: dict[str, Any] = {}
    if "title" in push:
        args["title"] = push["title"]
    if "due" in push:
        if push["due"]:
            args["due_date"] = push["due"]
        else:
            args["clear_due"] = True
    return args, push.get("completed")
