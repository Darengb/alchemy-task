"""Work-session checkpoints: the managed "Current state" block and status rules (no Hermes imports)."""
from __future__ import annotations

import re
from typing import Any, Mapping

from . import taskfile as tf

STATES = {
    "done": ("done", "Done"),
    "waiting_user": ("waiting", "Waiting on you"),
    "waiting_other": ("waiting", "Waiting on someone else"),
    "blocked": ("waiting", "Blocked"),
    "in_progress": ("in-progress", "In progress"),
}
AUTO_STATES = ("in_progress", "waiting_user", "waiting_other", "blocked")  # never "done" without evidence
_MARKER_RE = re.compile(r"<!--\s*[a-z0-9-]+:(start|end)\b", re.I)


class CheckpointError(ValueError):
    pass


def _clean(text: Any, limit: int = 1500) -> str:
    out = " ".join(str(text or "").split())
    out = _MARKER_RE.sub(lambda m: "&lt;!--" + m.group(0)[4:], out)
    return out[:limit]


def normalize(fields: Mapping[str, Any], *, automatic: bool = False) -> dict[str, str]:
    state = str(fields.get("state") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if state not in STATES:
        raise CheckpointError(f"state must be one of {', '.join(STATES)}")
    if automatic and state not in AUTO_STATES:
        state = "in_progress"
    out = {"state": state, "done": _clean(fields.get("done")), "next_step": _clean(fields.get("next_step")),
           "needs_from": _clean(fields.get("needs_from"), 500), "evidence": _clean(fields.get("evidence"))}
    if not out["done"]:
        raise CheckpointError("say what was done in this session (done)")
    if state == "done" and not out["evidence"]:
        raise CheckpointError("marking a task done needs evidence: what you checked and how (a live readback, "
                              "a link, a test result)")
    if state in ("waiting_user", "waiting_other", "blocked") and not (out["needs_from"] or out["next_step"]):
        raise CheckpointError("say what is needed and from whom (needs_from)")
    if state != "done" and not out["next_step"]:
        raise CheckpointError("say what the next step is (next_step)")
    return out


def render(cp: Mapping[str, str], *, day: str, automatic: bool) -> str:
    label = STATES[cp["state"]][1]
    how = "automatic checkpoint from the session" if automatic else "checkpoint"
    lines = ["## Current state", "", f"**{label}** · {day} ({how})", "", f"**Done so far:** {cp['done']}"]
    if cp["next_step"]:
        lines.append(f"**Next step:** {cp['next_step']}")
    if cp["needs_from"]:
        lines.append(f"**Needed from:** {cp['needs_from']}")
    if cp["evidence"]:
        lines.append(f"**Evidence:** {cp['evidence']}")
    return tf.CURRENT_STATE_START + "\n" + "\n".join(lines) + "\n" + tf.CURRENT_STATE_END


def log_line(cp: Mapping[str, str], *, automatic: bool) -> str:
    label = STATES[cp["state"]][1].lower()
    text = f"{'Automatic checkpoint' if automatic else 'Checkpoint'} ({label}): {cp['done'][:300]}"
    if cp["next_step"]:
        text += f" Next: {cp['next_step'][:200]}"
    if cp["needs_from"]:
        text += f" Needed from: {cp['needs_from'][:150]}"
    return text


def apply_status(fm: Any, cp: Mapping[str, str], today: str) -> None:
    """Set status (and completed) from the checkpoint state."""
    new = STATES[cp["state"]][0]
    old = str(fm.get("status") or "").strip().lower()
    fm["status"] = new
    if new == "done":
        if not tf.norm_date(fm.get("completed")):
            fm["completed"] = today
    elif old in tf.CLOSED_STATUSES:
        fm["completed"] = None


AUTO_SCHEMA = {
    "type": "object",
    "properties": {
        "state": {"type": "string", "enum": list(AUTO_STATES)},
        "done": {"type": "string", "description": "What was accomplished in this session, concretely."},
        "next_step": {"type": "string", "description": "The next concrete step to continue the work."},
        "needs_from": {"type": "string", "description": "What is needed and from whom, if anything (else empty)."},
    },
    "required": ["state", "done", "next_step", "needs_from"],
    "additionalProperties": False,
}

AUTO_INSTRUCTIONS = (
    "You write a checkpoint for a task from the transcript of a work session that stopped without one. "
    "Fill the fields from what actually happened in the transcript; do not invent progress. state: "
    "waiting_user if the assistant asked the user something or needs their decision, waiting_other if it waits "
    "on a third party, blocked if something failed and it cannot continue, otherwise in_progress. Never claim the "
    "task is finished. Keep each field to one or two sentences."
)


def transcript_text(messages: list[Mapping[str, Any]], *, limit: int = 12000) -> str:
    """Compact transcript: first user message plus the tail, tool output trimmed."""
    rows = []
    for m in messages:
        role = str(m.get("role") or "")
        content = m.get("content")
        if isinstance(content, list):
            content = " ".join(str(p.get("text") or "") for p in content if isinstance(p, Mapping))
        text = " ".join(str(content or "").split())
        if role == "tool":
            text = text[:300]
        elif role == "assistant" and not text and m.get("tool_calls"):
            names = [((c.get("function") or {}).get("name") or "") for c in m.get("tool_calls") or []]
            text = "[called " + ", ".join(n for n in names if n) + "]"
        if text:
            rows.append(f"{role}: {text[:2000]}")
    if not rows:
        return ""
    first = next((r for r in rows if r.startswith("user:")), rows[0])
    tail: list[str] = []
    size = len(first)
    for r in reversed(rows):
        if r is first or size + len(r) > limit:
            break
        tail.append(r)
        size += len(r)
    body = list(reversed(tail))
    return "\n".join([first, "…"] + body if body and body[0] != first else [first] + body)


def mechanical(user: str, assistant: str) -> dict[str, str]:
    """Free fallback when no model call is available."""
    return {"state": "in_progress",
            "done": _clean(f"Session stopped without a checkpoint. Last request: {user[:300]} "
                           f"Last reply: {assistant[:500]}"),
            "next_step": "Review the last reply above and continue from there.", "needs_from": "", "evidence": ""}
