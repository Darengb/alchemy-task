"""Deterministic pre-research screening of collected source items.

Provider-neutral rules over the shared envelope item shape
``{title, source_ids, messages: [{id, author, time, text, headers?}], subject?, from?, headers?}``.
Each rule returns a short reason when an item is clearly low value (calendar
notices, auto-replies, bulk mail, bot-only threads). Rules are conservative:
when unsure, keep. A parent agent may also mark an item
``disposition: exclude`` with a ``reason``; that is honored the same way.

Screened items are saved as excluded backlog entries with a ``screened``
reason, so they are never researched and never counted by the digest.
"""
from __future__ import annotations

import re
from typing import Any, Callable

CALENDAR_SUBJECT_PREFIXES = (
    'invitation:', 'updated invitation:', 'updated invitation with note:', 'accepted:', 'declined:',
    'tentatively accepted:', 'canceled:', 'canceled event', 'cancelled:', 'cancelled event', 'new event:',
)
CALENDAR_BOILERPLATE = (
    re.compile(r'invitation from google calendar', re.I),
    re.compile(r'you are receiving this (?:email|notification|courtesy email) (?:at the account \S+ )?because you are (?:an attendee|subscribed|the organi[sz]er)', re.I),
    re.compile(r'forwarding this invitation could allow any recipient', re.I),
    re.compile(r'microsoft teams meeting.{0,200}join (?:on your computer|the meeting now)', re.I | re.S),
)
AUTO_REPLY_SUBJECT = re.compile(r'^\s*(?:automatic reply|auto(?:matic)?[- ]?reply|auto:|out of (?:the )?office|ooo\b)', re.I)
AUTO_REPLY_TEXT = re.compile(r'^\W*(?:(?:hi|hello|thanks?(?: you)?)[^.\n]{0,40}[.,!\n]\s*)?(?:i am|i\'m|i will be)\s+(?:currently\s+)?(?:out of (?:the )?office|away from (?:the office|my desk)|on (?:vacation|leave|holiday|pto))', re.I)
UNSUBSCRIBE = re.compile(r'\bunsubscribe\b|\bmanage (?:your )?(?:email )?preferences\b|\bopt[- ]out\b', re.I)
BULK_SENDER_LOCALS = ('noreply', 'no-reply', 'no_reply', 'donotreply', 'do-not-reply', 'newsletter', 'newsletters', 'news',
                      'marketing', 'promo', 'promotions', 'offers', 'deals', 'digest', 'updates', 'hello', 'info', 'team',
                      'mailer', 'notifications', 'notification', 'events', 'webinar', 'webinars')
BOT_MARKERS = ('no-reply', 'noreply', 'no_reply', 'donotreply', 'do-not-reply', 'notifications@', 'notification@',
               'mailer-daemon', 'postmaster@')
# Surnames that happen to end in "bot"; never treat these as bots.
NOT_BOTS = ('talbot', 'cabot', 'thibot', 'jabot', 'abbot')


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ''


def _messages(item: dict) -> list[dict]:
    # Mail collectors name the message text 'body'; screening reads it as 'text'.
    return [m if m.get('text') or not m.get('body') else {**m, 'text': m['body']}
            for m in item.get('messages') or [] if isinstance(m, dict)]


def _subject(item: dict) -> str:
    for value in (item.get('subject'), *(m.get('subject') for m in _messages(item)[:1]), item.get('title')):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _headers(item: dict, message: dict | None = None) -> dict[str, str]:
    merged: dict[str, str] = {}
    for source in (item.get('headers'), (message or {}).get('headers')):
        if isinstance(source, dict):
            merged.update({str(k).lower(): str(v) for k, v in source.items()})
        elif isinstance(source, list):  # [{name, value}] as some mail APIs return
            merged.update({str(h.get('name', '')).lower(): str(h.get('value', '')) for h in source if isinstance(h, dict)})
    return merged


def _authors(item: dict) -> list[str]:
    authors = [_text(m.get('author') or m.get('from')).strip().lower() for m in _messages(item)]
    authors = [a for a in authors if a]
    if not authors and _text(item.get('from')).strip():
        authors = [_text(item['from']).strip().lower()]
    return authors


def _is_bot(author: str) -> bool:
    if any(marker in author for marker in BOT_MARKERS):
        return True
    for token in re.split(r'[^a-z0-9]+', author):
        # "slackbot" style names only when the author is one bare word, never an email local part.
        if token == 'bot' or (token.endswith('bot') and len(token) > 3 and token not in NOT_BOTS and ' ' not in author and '@' not in author):
            return True
    return '[bot]' in author


def _local_part(author: str) -> str:
    match = re.search(r'([a-z0-9._+-]+)@', author)
    return match.group(1) if match else ''


def _bulk_sender(author: str) -> bool:
    local = _local_part(author)
    if not local:
        return False
    stem = local.split('+')[0]
    return any(stem == x or stem.startswith(x + '.') or stem.startswith(x + '-') or stem.endswith('-' + x) for x in BULK_SENDER_LOCALS)


def _single_sender(item: dict) -> bool:
    return len(set(_authors(item))) <= 1


# ----------------------------------------------------------------- rules

def _calendar(item: dict) -> str | None:
    if _subject(item).lower().startswith(CALENDAR_SUBJECT_PREFIXES):
        return 'calendar notice'
    texts = [_text(m.get('text')) for m in _messages(item)]
    if texts and all(any(p.search(t) for p in CALENDAR_BOILERPLATE) for t in texts):
        return 'calendar notice'
    return None


def _auto_reply(item: dict) -> str | None:
    messages = _messages(item)
    if AUTO_REPLY_SUBJECT.match(_subject(item)) and _single_sender(item):
        return 'auto-reply'
    if messages and all(_headers(item, m).get('auto-submitted', 'no').lower() not in ('', 'no')
                        or 'x-autoreply' in _headers(item, m) or AUTO_REPLY_TEXT.match(_text(m.get('text')))
                        for m in messages):
        return 'auto-reply'
    return None


def _bulk(item: dict) -> str | None:
    # A thread with replies from more than one sender is a conversation, not a broadcast.
    if not _single_sender(item):
        return None
    messages = _messages(item) or [{}]
    for message in messages:
        headers = _headers(item, message)
        if 'list-unsubscribe' in headers or headers.get('precedence', '').strip().lower() in ('bulk', 'list', 'junk'):
            continue
        author = _text(message.get('author') or message.get('from') or item.get('from')).lower()
        if UNSUBSCRIBE.search(_text(message.get('text'))) and (_bulk_sender(author) or _is_bot(author)):
            continue
        return None
    return 'newsletter or bulk mail'


def _bots(item: dict) -> str | None:
    authors = _authors(item)
    if authors and all(_is_bot(a) for a in authors):
        return 'automated sender'
    return None


# Ordered, data-driven: append (name, rule) pairs to extend. Each rule returns a reason or None.
RULES: list[tuple[str, Callable[[dict], str | None]]] = [
    ('calendar', _calendar),
    ('auto_reply', _auto_reply),
    ('bulk', _bulk),
    ('bot', _bots),
]


def screen(item: dict) -> tuple[bool, str]:
    """Return (keep, reason). keep=False means never research this item."""
    if not isinstance(item, dict):
        return True, ''
    disposition = _text(item.get('disposition')).strip().lower()
    if disposition in ('exclude', 'excluded'):
        reason = ' '.join(_text(item.get('reason') or item.get('disposition_reason')).split())[:200]
        return False, 'parent: ' + (reason or 'excluded before research')
    if disposition == 'research':
        return True, ''  # the parent read it and chose to research; rules never override that
    for name, rule in RULES:
        try:
            reason = rule(item)
        except Exception:  # noqa: BLE001 - a broken rule must never drop an item
            reason = None
        if reason:
            return False, reason
    return True, ''


def screen_items(items: list) -> tuple[list, list[tuple[dict, str]]]:
    kept, screened = [], []
    for item in items or []:
        keep, reason = screen(item)
        if keep:
            kept.append(item)
        else:
            screened.append((item, reason))
    # A thread that is also kept in the same envelope is never screened.
    kept_ids = {str(x) for item in kept if isinstance(item, dict) for x in item.get('source_ids') or []}
    overlap = [(item, reason) for item, reason in screened if kept_ids & {str(x) for x in item.get('source_ids') or []}]
    kept += [item for item, _ in overlap]
    return kept, [x for x in screened if x not in overlap]


def record_screened(store, stream: str, source_key: str, screened: list[tuple[dict, str]], persist: Callable[[list], dict]) -> list[dict]:
    """Save screened items as excluded backlog entries; return a short summary list.

    ``persist`` saves items to the backlog (same validation as kept items) and
    returns the source state. Entries already settled by an earlier run keep
    their status.
    """
    if not screened:
        return []
    from .discovery_identity import canonical_source_id
    state = persist([item for item, _ in screened])
    out = []
    for item, reason in screened:
        ids = sorted(set(canonical_source_id(s) for s in item['source_ids']))
        # The backlog keys versions itself; the newest entry for this thread is the one just saved.
        thread = [x for x in state['backlog'] if sorted(set(x['source_ids'])) == ids]
        entry = thread[-1] if thread else None
        if not entry:
            continue
        if entry['status'] in ('queued', 'deferred', 'pilot_skipped', 'excluded'):
            try:
                store.update_backlog(stream, source_key, entry['backlog_id'], status='excluded', lineage={'screened': reason})
            except Exception:  # noqa: BLE001 - terminal entries keep their earlier outcome
                pass
        out.append({'backlog_id': entry['backlog_id'], 'title': _text(item.get('title'))[:120], 'reason': reason})
    return out
