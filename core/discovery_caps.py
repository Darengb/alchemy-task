"""Per-source proposal caps, workstream ranking and the 'also mentioned' line (stdlib only).

A research child may find many actions in one source item. The parent never rejects a
bundle for that: it keeps the most important proposals up to the cap for the item's type
and lists the rest by title only, so the user still sees what else the source mentioned.
"""
from __future__ import annotations

from typing import Any

# Workstream priority, most important first. Optional in the child schema.
PRIORITIES = ('user_next_step', 'dated', 'waiting_on_user', 'new_work', 'task_update', 'status_only')
# A workstream without a priority (older payloads) ranks with ordinary new work.
DEFAULT_PRIORITY = 'new_work'

# Source item types and their proposal caps.
SINGLE, CONVERSATION, TRANSCRIPT = 'single', 'conversation', 'transcript'
CAPS = {SINGLE: 7, CONVERSATION: 10, TRANSCRIPT: 10}
# Hard bound on submitted workstreams, for payload size only; extra ones are trimmed, never rejected.
SAFETY_BOUND = 40
# Item kinds a reader may set to mark meeting transcripts or notes.
TRANSCRIPT_ITEM_KINDS = {'transcript', 'meeting_notes', 'meeting-notes', 'notes'}
EXCLUDED_DISPOSITIONS = {'exclude_pure_chase', 'exclude_resolved'}
MAX_LISTED_TITLES = 5


def _author(message: dict[str, Any]) -> str:
    value = message.get('author', message.get('from', message.get('user')))
    if isinstance(value, dict):
        value = value.get('email') or value.get('id') or value.get('name')
    return ' '.join(str(value or '').casefold().split())


def classify_source_item(versions: Any, source_kind: str | None = None) -> str:
    """Return 'transcript', 'conversation' or 'single' for one research candidate.

    - transcript: the item comes from a source configured as kind 'transcript', or the item
      itself says kind/source_kind is transcript or meeting notes;
    - conversation: the newest version has 2+ messages from 2+ distinct authors
      (an email thread with replies, a Slack thread or DM exchange);
    - single: anything else (one message, or several messages by one author).
    """
    items = [v for v in (versions if isinstance(versions, list) else [versions]) if isinstance(v, dict)]
    if str(source_kind or '').casefold() == TRANSCRIPT:
        return TRANSCRIPT
    if any(str(v.get(k) or '').casefold() in TRANSCRIPT_ITEM_KINDS for v in items for k in ('kind', 'source_kind')):
        return TRANSCRIPT
    latest = items[-1] if items else {}
    messages = [m for m in latest.get('messages') or [] if isinstance(m, dict)] if isinstance(latest.get('messages'), list) else []
    authors = {a for a in (_author(m) for m in messages) if a}
    if len(messages) >= 2 and len(authors) >= 2:
        return CONVERSATION
    return SINGLE


def item_noun(item_type: str, *, email: bool = False) -> str:
    if item_type == TRANSCRIPT:
        return 'transcript'
    if item_type == CONVERSATION:
        return 'conversation'
    return 'email' if email else 'message'


def is_noop(workstream: Any) -> bool:
    """A workstream that proposes nothing: the matched task is already current, or it is excluded."""
    return isinstance(workstream, dict) and (workstream.get('existing_task_already_current') is True
                                              or workstream.get('disposition') in EXCLUDED_DISPOSITIONS)


def priority_rank(workstream: Any) -> int:
    value = workstream.get('priority') if isinstance(workstream, dict) else None
    return PRIORITIES.index(value if value in PRIORITIES else DEFAULT_PRIORITY)


def trim_workstreams(streams: list[Any], cap: int, *, bound: int = SAFETY_BOUND) -> tuple[list[Any], list[Any]]:
    """Keep at most ``cap`` proposed workstreams plus noops, at most ``bound`` in total.

    Proposed ones are ranked by priority, then the child's own order; kept workstreams stay in
    the child's order. Returns (kept, dropped proposals); noops dropped for the bound are not listed.
    """
    proposed = [i for i, w in enumerate(streams) if not is_noop(w)]
    ranked = sorted(proposed, key=lambda i: (priority_rank(streams[i]), i))
    keep = set(ranked[:cap])
    dropped = [i for i in ranked[cap:]]
    noops = [i for i, w in enumerate(streams) if is_noop(w)]
    room = max(0, bound - len(keep))
    keep |= set(noops[:room])
    if len(keep) > bound:  # cap above bound: keep the top-ranked proposals
        keep = set(ranked[:bound])
        dropped = [i for i in ranked[bound:]]
    return [w for i, w in enumerate(streams) if i in keep], [streams[i] for i in dropped]


def title_of(workstream: Any) -> str:
    title = workstream.get('title') if isinstance(workstream, dict) else ''
    return ' '.join(str(title or '').split())[:300]


def also_mentioned_line(item_type: str, titles: list[str], *, email: bool = False) -> str:
    """One short plain line: 'Also in this email, not proposed: A, B, C' (+N more)."""
    titles = [t for t in titles if t]
    if not titles:
        return ''
    shown = titles[:MAX_LISTED_TITLES]
    text = ', '.join(shown)
    if len(titles) > len(shown):
        text += f', +{len(titles) - len(shown)} more'
    return f'Also in this {item_noun(item_type, email=email)}, not proposed: {text}'
