"""User-defined discovery filters: deterministic message-level exclusion rules.

Stdlib only, so discovery can load without the research module.

A rule acts on individual MESSAGES, never whole threads. A message a rule
matches stays in its item as background (``message['filtered']``): research
may read it to understand the replies, but no proposal may rest on it alone.
An item whose messages are ALL excluded is saved as excluded before research.

Rule shape::

    {id, name, enabled, mode: 'all' | 'any', action: 'exclude',
     match: {from: [...], to: [...], subject: [...], body: [...], where: [...]}}

Fields in one rule are ANDed. ``from``/``to``/``where`` list alternatives (any
value matches). ``subject``/``body`` list terms: by default every term must
appear (``mode: 'all'``); ``mode: 'any'`` needs one. Matching is
case-insensitive. A field the source does not have never matches there (Slack
has no subject; only email has to/cc). ``from: me`` is the account owner for
that source; when the plugin cannot tell who that is, ``me`` matches nothing.
Body terms ignore quoted reply text, so a rule on an original never catches a
reply that quotes it.

Storage (plugin state key ``discovery_filters``)::

    {'<stream>': {'rules': [...], 'guidance': '...'}, '*': {...}}

``'*'`` holds rules and guidance that apply to every stream.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import re
from typing import Any, Iterable

STATE_KEY = 'discovery_filters'
ALL_STREAMS = '*'
FIELDS = ('from', 'to', 'subject', 'body', 'where')
TEXT_FIELDS = ('subject', 'body')
MAX_RULES = 50
MAX_TERMS = 20
MAX_TERM_CHARS = 200
MAX_GUIDANCE_CHARS = 2000
MAX_NAME_CHARS = 80
PREVIEW_DAYS = 7

ADDRESS = re.compile(r'[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}')
# Quoted reply text: "On <date>, <name> wrote:" (may wrap onto a second line), Outlook headers, original-message banners.
_QUOTE_HEADER = re.compile(r'^[ \t]*On [^\n]{1,300}(?:\n[^\n]{0,300})?\bwrote:[ \t]*$', re.M)
_QUOTE_BANNERS = re.compile(r'^[ \t]*(?:-{2,}[ \t]*Original Message[ \t]*-{2,}|_{10,}[ \t]*$|From:[^\n]{1,300}\n(?:[^\n]{0,300}\n){0,2}?Sent:[^\n]{0,300}$)', re.M | re.I)


class FilterError(ValueError):
    """A rule or setting the user must correct."""


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ''


def _clean(value: Any, limit: int = MAX_TERM_CHARS) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise FilterError('match values must be a string or a list of strings')
    out = []
    for term in value:
        if not isinstance(term, str):
            raise FilterError('match values must be strings')
        term = _clean(term)
        if term and term.lower() not in [t.lower() for t in out]:
            out.append(term)
    if len(out) > MAX_TERMS:
        raise FilterError(f'at most {MAX_TERMS} values per field')
    return out


def rule_id(name: str, match: dict) -> str:
    return 'f_' + hashlib.sha256(repr((name, sorted((k, tuple(v)) for k, v in match.items()))).encode()).hexdigest()[:10]


def normalize_rule(raw: Any, *, existing: dict | None = None) -> dict:
    """Validate and normalize one rule (merged over ``existing`` for updates)."""
    if not isinstance(raw, dict):
        raise FilterError('rule must be an object')
    unknown = set(raw) - {'id', 'name', 'enabled', 'mode', 'action', 'match', 'originals_only', *FIELDS}
    if unknown:
        raise FilterError('unknown rule fields: ' + ', '.join(sorted(unknown)))
    base = copy.deepcopy(existing or {})
    match = dict(base.get('match') or {})
    supplied = dict(raw.get('match') or {}) if isinstance(raw.get('match'), dict) else {}
    if raw.get('match') is not None and not isinstance(raw.get('match'), dict):
        raise FilterError('match must be an object')
    supplied.update({k: raw[k] for k in FIELDS if k in raw})
    if set(supplied) - set(FIELDS):
        raise FilterError('unknown match fields: ' + ', '.join(sorted(set(supplied) - set(FIELDS))) + '; use from, to, subject, body or where')
    for key, value in supplied.items():
        terms = _terms(value)
        if terms:
            match[key] = terms
        else:
            match.pop(key, None)
    if not match:
        raise FilterError('a rule needs at least one of from, to, subject, body or where')
    name = _clean(raw.get('name', base.get('name')), MAX_NAME_CHARS) or _default_name(match)
    mode = raw.get('mode', base.get('mode', 'all'))
    if mode not in ('all', 'any'):
        raise FilterError("mode must be 'all' (every term must appear) or 'any' (one term is enough)")
    action = raw.get('action', base.get('action', 'exclude'))
    if action != 'exclude':
        raise FilterError("the only rule action is 'exclude' (the message stays readable as background)")
    enabled = raw.get('enabled', base.get('enabled', True))
    if type(enabled) is not bool:
        raise FilterError('enabled must be true or false')
    originals_only = raw.get('originals_only', base.get('originals_only', False))
    if type(originals_only) is not bool:
        raise FilterError('originals_only must be true or false')
    out = {'id': base.get('id') or _clean(raw.get('id'), 40) or rule_id(name, match), 'name': name, 'enabled': enabled,
           'mode': mode, 'action': 'exclude', 'match': {k: match[k] for k in FIELDS if k in match}}
    if originals_only:
        out['originals_only'] = True
    return out


def _default_name(match: dict) -> str:
    parts = [f"{k} {'/'.join(v)}" for k, v in match.items()]
    return _clean('Exclude ' + '; '.join(parts), MAX_NAME_CHARS)


def describe_rule(rule: dict) -> str:
    """One plain sentence for showing a rule back to the user before saving."""
    words = {'from': 'from', 'to': 'sent to', 'subject': 'with a subject or title containing', 'body': 'with text containing',
             'where': 'in'}
    joiner = ' and ' if rule.get('mode', 'all') == 'all' else ' or '
    parts = []
    for key in FIELDS:
        values = (rule.get('match') or {}).get(key)
        if not values:
            continue
        shown = [('you' if v.lower() == 'me' and key in ('from', 'to') else v) for v in values]
        sep = joiner if key in TEXT_FIELDS else ' or '
        parts.append(words[key] + ' ' + sep.join(f'"{v}"' if key in TEXT_FIELDS else v for v in shown))
    state = '' if rule.get('enabled', True) else ' (turned off)'
    scope = ('Only original messages are skipped; every reply, including yours, is still read.'
             if rule.get('originals_only') else 'Replies from others in the same thread are still read.')
    return (f"{rule.get('name', 'Rule')}: skip messages " + ', '.join(parts) + '. ' + scope + state)


# ------------------------------------------------------------------ storage

def load(state_get) -> dict:
    data = state_get(STATE_KEY, default={}) if callable(state_get) else {}
    return data if isinstance(data, dict) else {}


def scope_settings(data: dict, scope: str) -> dict:
    entry = data.get(scope) if isinstance(data.get(scope), dict) else {}
    return {'rules': [r for r in entry.get('rules') or [] if isinstance(r, dict)], 'guidance': _text(entry.get('guidance'))}


def rules_for(data: dict, stream: str) -> list[dict]:
    """Enabled rules that apply to ``stream``: its own plus the all-streams ones."""
    out = []
    for scope in (stream, ALL_STREAMS):
        for rule in scope_settings(data, scope)['rules']:
            if rule.get('enabled', True):
                out.append({**rule, 'scope': scope})
    return out


def guidance_for(data: dict, stream: str) -> str:
    parts = [scope_settings(data, s)['guidance'].strip() for s in (ALL_STREAMS, stream)]
    return '\n'.join(p for p in parts if p)


def clean_guidance(text: Any) -> str:
    if text is None:
        return ''
    if not isinstance(text, str):
        raise FilterError('guidance must be text')
    text = '\n'.join(' '.join(line.split()) for line in text.replace('\r', '').split('\n')).strip()
    # Never let saved guidance forge markup in the instructions it is placed in.
    text = text.replace('<!--', '').replace('-->', '').replace('```', '')
    if len(text) > MAX_GUIDANCE_CHARS:
        raise FilterError(f'screening guidance is limited to {MAX_GUIDANCE_CHARS} characters')
    return text


# ------------------------------------------------------------------ identity

def me_identity(config: dict | None, accounts: dict | None = None) -> dict:
    """Who 'me' is for one source: addresses, provider ids and exact display names.

    Taken from the confirmed account identity (user_id, aliases, name), explicit
    address fields on the source, and for mail the mailbox address named first in
    its scope. Empty when unknown; 'me' then matches nothing for that source.
    """
    config = config or {}
    found = {'addresses': set(), 'ids': set(), 'names': set()}
    account = (accounts or {}).get(config.get('account_key')) if isinstance(accounts, dict) else None
    if isinstance(account, dict):
        if _text(account.get('user_id')).strip():
            found['ids'].add(account['user_id'].strip().lower())
        for alias in [account.get('name'), *(account.get('aliases') or [])]:
            alias = _text(alias).strip().lower()
            if not alias:
                continue
            (found['addresses'] if ADDRESS.fullmatch(alias) else found['names']).add(alias)
    for key in ('owner_address', 'owner_email', 'mailbox', 'address', 'account_email', 'email'):
        for value in (config.get(key) if isinstance(config.get(key), list) else [config.get(key)]):
            if ADDRESS.fullmatch(_text(value).strip()):
                found['addresses'].add(value.strip().lower())
    if config.get('kind') in ('mail', 'transcript'):
        first = ADDRESS.search(_text(config.get('scope')))
        if first:
            found['addresses'].add(first.group(0).lower())
    return found


def me_known(me: dict) -> bool:
    return bool(me and (me.get('addresses') or me.get('ids') or me.get('names')))


def describe_me(me: dict) -> str:
    if not me_known(me):
        return 'unknown for this source, so "me" matches nothing here'
    shown = sorted(me['addresses']) + sorted(me['ids']) + sorted(me['names'])
    return ', '.join(shown)


# ------------------------------------------------------------------ message fields

def source_type(config: dict | None, item: dict) -> str:
    """'email', 'chat', 'transcript' or 'other' (notes, documents)."""
    config = config or {}
    ids = [str(x) for x in item.get('source_ids') or []]
    if config.get('kind') == 'transcript':
        return 'transcript'
    if any(x.startswith('slack:') for x in ids) or item.get('channel') or item.get('channel_label'):
        return 'chat'
    if config.get('kind') == 'mail' or any(x.startswith('gmail:') for x in ids):
        return 'email'
    messages = [m for m in item.get('messages') or [] if isinstance(m, dict)]
    if any('ts' in m or 'thread_ts' in m for m in messages):
        return 'chat'
    if any('subject' in m or 'to' in m for m in messages):
        return 'email'
    return 'other'


def strip_quoted(text: str) -> str:
    """The message's own text: drops '>' lines and everything from a reply header down."""
    text = _text(text)
    cut = len(text)
    for pattern in (_QUOTE_HEADER, _QUOTE_BANNERS):
        found = pattern.search(text)
        if found:
            cut = min(cut, found.start())
    own = text[:cut]
    return '\n'.join(line for line in own.split('\n') if not line.lstrip().startswith('>'))


def _people(value: Any) -> list[str]:
    if isinstance(value, list):
        return [p for v in value for p in _people(v)]
    if isinstance(value, dict):
        return [' '.join(str(value.get(k) or '') for k in ('name', 'email', 'address', 'id')).strip()]
    return [p.strip() for p in re.split(r',(?![^<]*>)', _text(value)) if p.strip()]


def _person_matches(person: str, value: str, me: dict, ids: Iterable[str] = ()) -> bool:
    person_l = person.lower()
    addresses = {a.lower() for a in ADDRESS.findall(person)}
    ids = {str(i).strip().lower() for i in ids if str(i).strip()}
    display = ADDRESS.sub('', person_l).replace('<', '').replace('>', '').strip(' "\'')
    v = value.strip().lower()
    if v == 'me':
        return bool(addresses & me.get('addresses', set()) or ids & me.get('ids', set())
                    or (display and display in me.get('names', set())) or (person_l.strip() in me.get('ids', set())))
    if v.startswith('@'):
        domain = v[1:]
        return any(a.endswith('@' + domain) or a.endswith('.' + domain) for a in addresses)
    if '@' in v:
        return v in addresses
    if v in ids or v == person_l.strip():
        return True
    return bool(display) and re.search(r'(?<![a-z0-9])' + re.escape(v) + r'(?![a-z0-9])', display) is not None


_REPLY_SUBJECT = re.compile(r'^\s*(?:re|fwd?|aw|sv)\s*:', re.I)


def is_reply(item: dict, message: dict, index: int = 0) -> bool:
    """A message that answers or forwards an earlier one (not the thread's original)."""
    if index > 0:
        return True
    if _REPLY_SUBJECT.match(_text(message.get('subject'))):
        return True
    if message.get('in_reply_to') or message.get('In-Reply-To'):
        return True
    thread_ts, ts = message.get('thread_ts'), message.get('ts')
    return bool(thread_ts and ts and str(thread_ts) != str(ts))


def message_fields(item: dict, message: dict, kind: str, source_key: str, index: int = 0) -> dict:
    """Matchable fields of one message. A field the source lacks is None (never matches)."""
    author = message.get('from') or message.get('author') or message.get('user') or message.get('sender') or ''
    ids = [message.get(k) for k in ('author_id', 'user', 'user_id', 'sender_id') if message.get(k)]
    if not author and not ids and len(item.get('messages') or []) <= 1:
        author = item.get('from') or ''
    fields: dict[str, Any] = {'from': (_people(author) or ([''] if ids else []), ids)}
    if kind == 'email':
        fields['to'] = (_people(message.get('to')) + _people(message.get('cc')), [])
        fields['subject'] = _text(message.get('subject') or item.get('subject') or item.get('title'))
    else:
        fields['to'] = None
        fields['subject'] = _text(item.get('title') or item.get('subject')) if kind in ('transcript', 'other') else None
    fields['body'] = strip_quoted(_text(message.get('text') or message.get('body') or message.get('snippet')))
    where = {source_key.lower()} if source_key else set()
    for value in (item.get('channel'), item.get('channel_id'), item.get('channel_label'), item.get('channel_name'),
                  message.get('channel'), *(item.get('labels') or []), *(message.get('labels') or []),
                  *(message.get('labelIds') or [])):
        if isinstance(value, str) and value.strip():
            where.add(value.strip().lower().lstrip('#'))
    for sid in item.get('source_ids') or []:
        parts = str(sid).split(':')
        if parts[0] == 'slack' and len(parts) >= 4:
            where.add(parts[2].lower())
    fields['where'] = where
    fields['is_reply'] = is_reply(item, message, index)
    return fields


def _text_matches(haystack: str | None, terms: list[str], mode: str) -> bool:
    if haystack is None:
        return False
    hay = haystack.lower()
    hits = [t.lower() in hay for t in terms]
    return all(hits) if mode == 'all' else any(hits)


def rule_matches(rule: dict, fields: dict, me: dict) -> bool:
    match = rule.get('match') or {}
    if not match:
        return False
    if rule.get('originals_only') and fields.get('is_reply'):
        return False
    mode = rule.get('mode', 'all')
    for key, values in match.items():
        if not values:
            continue
        if key in TEXT_FIELDS:
            if not _text_matches(fields.get(key), values, mode):
                return False
        elif key in ('from', 'to'):
            people = fields.get(key)
            if people is None:
                return False
            names, ids = people
            if not any(_person_matches(p, v, me, ids if key == 'from' else ()) for p in (names or ['']) for v in values):
                return False
        elif key == 'where':
            where = fields.get('where') or set()
            if not any(v.strip().lower().lstrip('#') in where for v in values):
                return False
        else:
            return False
    return True


def first_match(rules: list[dict], fields: dict, me: dict) -> dict | None:
    for rule in rules:
        if rule.get('enabled', True) and rule_matches(rule, fields, me):
            return rule
    return None


# ------------------------------------------------------------------ application

def _marker(rule: dict) -> dict:
    return {'rule': rule.get('id'), 'name': rule.get('name'), 'context_only': True}


def apply_to_item(item: dict, rules: list[dict], *, config: dict | None, me: dict) -> tuple[dict, list[dict], bool]:
    """Return (item copy with excluded messages marked, matched [{message_id, rule}], all excluded)."""
    item = copy.deepcopy(item)
    kind = source_type(config, item)
    key = (config or {}).get('source_key', '')
    messages = [m for m in item.get('messages') or [] if isinstance(m, dict)] if isinstance(item.get('messages'), list) else []
    matched = []
    if not messages:
        rule = first_match(rules, message_fields(item, item, kind, key), me) if rules else None
        if rule:
            item['filtered'] = _marker(rule)
            return item, [{'message_id': None, 'rule': rule.get('id'), 'name': rule.get('name')}], True
        item.pop('filtered', None)
        return item, [], False
    marked_ids = {}
    for index, message in enumerate(messages):
        message.pop('filtered', None)
        rule = first_match(rules, message_fields(item, message, kind, key, index), me) if rules else None
        if rule:
            message['filtered'] = _marker(rule)
            matched.append({'message_id': message.get('id') or message.get('ts'), 'rule': rule.get('id'), 'name': rule.get('name')})
            if message.get('id') or message.get('ts'):
                marked_ids[str(message.get('id') or message.get('ts'))] = message['filtered']
    # Inlined copies of the same messages carry the same mark, so research sees it everywhere.
    if isinstance(item.get('primary_content'), list):
        for copy_msg in item['primary_content']:
            if isinstance(copy_msg, dict):
                copy_msg.pop('filtered', None)
                mark = marked_ids.get(str(copy_msg.get('id') or copy_msg.get('ts') or ''))
                if mark:
                    copy_msg['filtered'] = mark
    return item, matched, bool(messages) and len(matched) == len(messages)


def apply_filters(items: list, rules: list[dict], *, config: dict | None, me: dict) -> tuple[list, list[tuple[dict, str]], dict]:
    """Mark excluded messages; split off items whose messages are all excluded.

    Returns (kept items, [(skipped item, reason)], summary) where summary is
    ``{'messages': N, 'skipped': [{title, rule}], 'context_only': [{title, rule, messages}]}``.
    A broken rule never drops an item: errors keep the item unfiltered.
    """
    summary = {'messages': 0, 'skipped': [], 'context_only': []}
    if not rules:
        return list(items or []), [], summary
    kept, skipped = [], []
    for item in items or []:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        try:
            marked, matched, all_out = apply_to_item(item, rules, config=config, me=me)
        except Exception:  # noqa: BLE001 - a broken rule must never drop an item
            kept.append(item)
            continue
        title = _clean(item.get('title'), 120)
        names = list(dict.fromkeys(m['name'] for m in matched if m.get('name')))
        summary['messages'] += len(matched) or 0
        if all_out:
            summary['skipped'].append({'title': title, 'rule': ', '.join(names), 'messages': len(matched)})
            skipped.append((marked, 'filter: ' + ', '.join(names)))
        else:
            if matched:
                summary['context_only'].append({'title': title, 'rule': ', '.join(names), 'messages': len(matched)})
            kept.append(marked)
    return kept, skipped, summary


def filtered_message_ids(versions: Any) -> set[str]:
    """Message ids marked context-only in a frozen source body (list of item versions)."""
    out: set[str] = set()
    for version in versions if isinstance(versions, list) else [versions]:
        if not isinstance(version, dict):
            continue
        for key in ('messages', 'primary_content'):
            for message in version.get(key) or [] if isinstance(version.get(key), list) else []:
                if isinstance(message, dict) and message.get('filtered'):
                    mid = message.get('id') or message.get('ts')
                    if mid:
                        out.add(str(mid))
    return out


def unfiltered_message_ids(versions: Any) -> set[str]:
    out: set[str] = set()
    for version in versions if isinstance(versions, list) else [versions]:
        if isinstance(version, dict):
            for message in version.get('messages') or [] if isinstance(version.get('messages'), list) else []:
                if isinstance(message, dict) and not message.get('filtered') and (message.get('id') or message.get('ts')):
                    out.add(str(message.get('id') or message.get('ts')))
    return out


# ------------------------------------------------------------------ preview

def _epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) / (1000.0 if value > 1e11 else 1.0)
    text = _text(value).strip()
    if not text:
        return None
    if re.fullmatch(r'\d{9,11}(?:\.\d+)?', text):
        return float(text)
    try:
        parsed = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def message_time(message: dict) -> float | None:
    for key in ('time', 'date', 'ts', 'timestamp', 'internalDate'):
        if message.get(key) not in (None, ''):
            found = _epoch(message.get(key))
            if found is not None:
                return found
    return None


def preview(rules: list[dict], sources: list[tuple[dict, dict, list[dict]]], *, now: float, days: int = PREVIEW_DAYS,
            limit: int = 50) -> dict:
    """What ``rules`` would exclude in already-collected items from the last ``days`` days.

    ``sources`` is [(source config, me identity, [saved items])]. No new reading.
    """
    since = now - days * 86400
    matches, threads_skipped, kept_with_context, scanned = [], 0, 0, 0
    me_notes = []
    seen: set[tuple[str, str]] = set()
    wants_me = any(v.lower() == 'me' for r in rules for k in ('from', 'to') for v in (r.get('match') or {}).get(k) or [])
    for config, me, items in sources:
        key = config.get('source_key', '')
        if wants_me:
            me_notes.append({'source': config.get('name') or key, 'me': describe_me(me), 'known': me_known(me)})
        for item in items:
            if not isinstance(item, dict):
                continue
            messages = [m for m in item.get('messages') or [] if isinstance(m, dict)]
            recent = [m for m in messages if (message_time(m) or 0) >= since]
            if messages and not recent:
                continue
            marked, matched, all_out = apply_to_item(item, rules, config=config, me=me)
            ident = (key, '|'.join(sorted(str(x) for x in item.get('source_ids') or [])))
            if ident in seen:
                continue
            seen.add(ident)
            scanned += 1
            if not matched:
                continue
            threads_skipped += 1 if all_out else 0
            kept_with_context += 0 if all_out else 1
            by_id = {str(m.get('id') or m.get('ts')): m for m in marked.get('messages') or [] if isinstance(m, dict)}
            for hit in matched:
                message = by_id.get(str(hit.get('message_id'))) or {}
                author = _text(message.get('from') or message.get('author') or message.get('user'))
                matches.append({'source': config.get('name') or key, 'title': _clean(item.get('title'), 120),
                                'message_id': hit.get('message_id'), 'from': _clean(author, 120),
                                'subject': _clean(message.get('subject'), 160), 'time': _clean(message.get('date') or message.get('time') or message.get('ts'), 60),
                                'rule': hit.get('name'), 'thread': 'skipped' if all_out else 'kept, other messages still read'})
    return {'days': days, 'items_scanned': scanned, 'messages_matched': len(matches), 'threads_skipped': threads_skipped,
            'threads_kept_with_context': kept_with_context, 'matches': matches[:limit], 'truncated': len(matches) > limit,
            'me': me_notes}


def digest_line(count: int) -> str | None:
    if not isinstance(count, int) or count <= 0:
        return None
    return f"{count} {'message' if count == 1 else 'messages'} skipped by your filters."
