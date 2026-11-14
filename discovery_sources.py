"""Approved-reader adapters and source-derived pure algorithms, never credentials."""

from __future__ import annotations

import base64, re, html, hashlib, json, copy

from datetime import datetime, timezone

from decimal import Decimal

from typing import Any, Callable

from .core.discovery_identity import UserError, canonical_source_id
from .core.discovery_state import atomic_json
from pathlib import Path
from email.utils import parsedate_to_datetime, parseaddr
import os
import stat
import random
import time


def is_quota_error(exc):
    status = getattr(getattr(exc, 'resp', None), 'status', None)
    if status == 429:
        return True
    if status != 403:
        return False
    try:
        data = json.loads(getattr(exc, 'content', b'{}'))
        reasons = {e.get('reason') for e in data['error'].get('errors', [])}
    except (AttributeError, ValueError, KeyError, TypeError):
        return False
    return bool(reasons & {'rateLimitExceeded', 'userRateLimitExceeded'})


def retry_after(exc):
    headers = getattr(exc, 'resp', {})
    raw = next((v for k, v in headers.items() if k.lower() == 'retry-after'), None) if hasattr(headers, 'items') else None
    if raw is None:
        return 0
    try:
        return max(0, float(raw))
    except (ValueError, TypeError):
        try:
            return max(0, parsedate_to_datetime(raw).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return 0


class QuotaExhausted(RuntimeError):
    pass


class QuotaReader:
    """Source nine-attempt/240s algorithm for structured errors ONLY.

    Use only when the approved reader exposes these errors and does not already
    own retries. Never apply a guessed HTTP policy to prose connector errors.
    """
    def __init__(self, budget_seconds=240, max_attempts=9, *, clock=time, jitter=random.random, retry_after=retry_after):
        self.clock, self.jitter, self.retry_after = clock, jitter, retry_after
        self.deadline = clock.monotonic() + budget_seconds
        self.max_attempts = max_attempts
        self.requests = self.quota_retries = 0
        self.quota_wait_seconds = 0.

    def execute(self, request):
        for attempt in range(self.max_attempts):
            try:
                self.requests += 1
                return request()
            except Exception as exc:
                if not is_quota_error(exc):
                    raise
                delay = max(self.retry_after(exc), min(2 ** attempt, 32) + self.jitter())
                if attempt + 1 == self.max_attempts or self.clock.monotonic() + delay >= self.deadline:
                    raise QuotaExhausted('source_quota_exhausted') from None
                self.quota_retries += 1
                self.quota_wait_seconds += delay
                self.clock.sleep(delay)


def publish_snapshot(path, *, account, start, end, threads, complete):
    if complete is not True or not isinstance(threads, list):
        raise UserError('never publish incomplete mailbox snapshot')
    path = Path(path)
    if path.exists() or path.is_symlink():
        load_snapshot(path, account=account, start=start, end=end)
    atomic_json(path, {'account': account, 'window_start': start, 'window_end': end, 'complete': True, 'threads': threads})


def load_snapshot(path, *, account, start, end):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return None
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise UserError('unsafe mailbox snapshot')
    data = json.loads(path.read_text())
    if data.get('account') != account or data.get('complete') is not True or data.get('window_start') != start or data.get('window_end') != end or not isinstance(data.get('threads'), list):
        raise UserError('invalid mailbox snapshot account/window/completeness')
    return data


# Note-taker senders shipped as transcript defaults. Confirmed in real mail:
# gemini-notes@google.com, no-reply@zoom.us, fred@fireflies.ai and
# notifications@mail.granola.ai. Documented by the vendor only:
# meetings-noreply@google.com, meet-recordings-noreply@google.com (Google Meet
# recordings and transcripts) and no-reply@otter.ai (Otter help center).
# Microsoft Teams/Copilot recaps have no documented sender, so none ships; users
# add one. Zoom marketing senders (e.zoom.us) are deliberately not included.
DEFAULT_TRANSCRIPT_SENDERS = (
    'gemini-notes@google.com', 'meetings-noreply@google.com', 'meet-recordings-noreply@google.com',
    'no-reply@zoom.us', 'fred@fireflies.ai', 'no-reply@otter.ai', 'notifications@mail.granola.ai',
)
DEFAULT_TRANSCRIPT_KEYWORDS = (
    'next steps', 'action items', 'transcript', 'notes', 'summary', 'recap',
    'follow-up', 'follow up', 'followup', 'takeaways', 'to-do', 'todo', 'to do',
)


def transcript_senders(config):
    """Sender list for a transcript source; legacy service_sender is a one-item list."""
    if 'service_senders' in config:
        raw = config['service_senders']
    elif 'service_sender' in config:
        raw = [config['service_sender']]
    else:
        raw = list(DEFAULT_TRANSCRIPT_SENDERS)
    if not isinstance(raw, (list, tuple)) or any(not isinstance(x, str) for x in raw):
        raise UserError('transcript service_senders must be a list of addresses or @domains')
    senders = [x.strip().lower() for x in raw if x.strip()]
    if not senders:
        raise UserError('transcript source requires a nonempty service_senders list')
    return senders


def transcript_keywords(config):
    """Admission keywords; an empty list is refused unless admit_all is explicit."""
    raw = config.get('keywords', list(DEFAULT_TRANSCRIPT_KEYWORDS))
    if not isinstance(raw, (list, tuple)) or any(not isinstance(x, str) for x in raw):
        raise UserError('transcript keywords must be a list of words or phrases')
    words = [x.strip().lower() for x in raw if x.strip()]
    if not words:
        if config.get('admit_all') is True:
            return []
        raise UserError('transcript keywords cannot be empty unless admit_all: true')
    return words


def sender_matches(sender, senders):
    """Exact address, or a '@domain' entry matching that exact domain."""
    sender = (sender or '').strip().lower()
    if not sender:
        return False
    domain = '@' + sender.rsplit('@', 1)[-1]
    return any(sender == s if not s.startswith('@') else domain == s for s in senders)


def _has_keyword(text, keywords):
    low = text.lower()
    return any(re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', low) for k in keywords)


SCREENING_HEADERS = ('list-unsubscribe', 'precedence', 'auto-submitted', 'x-autoreply')


def _mail_admits(full, ordered, config):
    """True when a mail source with this config admits the thread (sender rules, owner report, window)."""
    allowed = {str(x).strip().lower() for x in config.get('sender_domains', [])}
    excluded = {str(x).strip().lower() for x in config.get('excluded_senders', [])}
    # Note-taker mail belongs to the mailbox's transcript source, never to both.
    skipped = [str(x).strip().lower() for x in config.get('transcript_senders', []) if str(x).strip()]
    relevant = any(m['from'] not in excluded and not sender_matches(m['from'], skipped) and (not allowed or m['from'].rsplit('@', 1)[-1] in allowed) for m in full)
    # Source narrow one-message owner report, case-insensitive, not owner-only.
    report = config.get('owner_report_pattern')
    subject = next((m['subject'] for m in full if m['subject']), '')
    owner_only_report = len(full) == 1 and full[0]['from'] == (config.get('owner_email') or '').strip().lower() and report and re.search(report, subject, re.I)
    if not relevant or owner_only_report:
        return False
    if config.get('window_start') and int(ordered[-1]['internalDate']) < int(_date(config['window_start']).timestamp()) * 1000:
        return False
    return True


def normalize_mail_threads(threads, config):
    """Daily full-thread-before-sender-admission projection, no clipping.

    Caller must have fetched every unique thread fully. This pure transform is
    NOT an exhaustion receipt. Keep historical messages and latest activity.
    """
    by_thread = {}
    for thread in threads:
        tid = thread['id']
        target = by_thread.setdefault(tid, {})
        for msg in thread['messages']:
            mid = msg['id']
            if mid in target and target[mid] != msg:
                raise UserError('contradictory full message snapshot')
            target[mid] = msg
    out = []
    for tid, messages in by_thread.items():
        ordered = sorted(messages.values(), key=lambda m: int(m['internalDate']))
        if not ordered:
            continue
        full = []
        for msg in ordered:
            payload = msg.get('payload') or {}
            headers = {h['name'].lower(): h.get('value', '') for h in payload.get('headers', [])}
            sender = parseaddr(headers.get('from', ''))[1].lower()
            entry = {'id': msg['id'], 'from': sender, 'subject': headers.get('subject', ''), 'date': msg['internalDate'], 'body': extract_message_text(payload)}
            # Bulk/auto-reply markers let pre-research screening drop newsletters and auto-replies.
            marks = {k: headers[k] for k in SCREENING_HEADERS if k in headers}
            if marks: entry['headers'] = marks
            full.append(entry)
        if config.get('kind') == 'transcript':
            # A thread its mailbox source admits (for example notes a colleague forwarded) is that
            # mailbox's one candidate, notes included; never a second transcript candidate.
            admission = config.get('mailbox_admission')
            if isinstance(admission, dict) and _mail_admits(full, ordered, {**admission, 'window_start': config.get('window_start')}):
                continue
            senders = transcript_senders(config)
            keywords = transcript_keywords(config)
            for raw, msg in zip(ordered, full):
                when = int(msg['date']) / 1000
                if not sender_matches(msg['from'], senders):
                    continue
                if config.get('window_start') and when < _date(config['window_start']).timestamp():
                    continue
                if config.get('window_end') and when > _date(config['window_end']).timestamp():
                    continue
                # Keyword gate only: research reads the full body, never a section.
                if keywords and not _has_keyword(msg['subject'] + '\n' + msg['body'], keywords):
                    continue
                identity = canonical_source_id(f"gmail:{config['account_key']}:{tid}:{msg['id']}")
                candidate = {'title': msg['subject'] or 'Meeting follow-up', 'source_ids': [identity], 'source_revision': hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(), 'source_key': config['source_key']}
                out.append({'candidate': candidate, 'messages': [msg], 'latest_activity': int(msg['date'])})
            continue
        if not _mail_admits(full, ordered, config):
            continue
        subject = next((m['subject'] for m in full if m['subject']), '')
        identity = canonical_source_id(f"gmail:{config['account_key']}:{tid}")
        revision = hashlib.sha256(json.dumps(ordered, sort_keys=True).encode()).hexdigest()
        candidate = {'title': subject or 'Mail follow-up', 'source_ids': [identity], 'source_revision': revision, 'source_key': config['source_key']}
        out.append({'candidate': candidate, 'messages': full, 'latest_activity': int(ordered[-1]['internalDate'])})
    return sorted(out, key=lambda x: x['latest_activity'])


def group_slack_seeds(messages: list[dict]) -> list[dict]:
    """Daily channel/reply grouping with precise spelling and 1800s adjacency."""
    channels = {}
    seen = set()
    for msg in messages:
        channel = (msg.get('channel') or {}).get('id') or msg.get('channel_id')
        ts = msg.get('ts')
        if not channel or not ts or (channel, ts) in seen:
            continue
        seen.add((channel, ts))
        # Validate spelling without converting the stored timestamp.
        canonical_source_id(f'slack:workspace:{channel}:{ts}')
        bucket = channels.setdefault(channel, {'threaded': {}, 'toplevel': []})
        permalink = msg.get('permalink', '')
        match = re.search(r'[?&]thread_ts=([0-9]+\.[0-9]+)', permalink)
        thread = msg.get('thread_ts') or (match.group(1) if match else None)
        if thread and thread != ts:
            bucket['threaded'].setdefault(thread, []).append(msg)
        else:
            bucket['toplevel'].append(msg)
    groups = []
    for channel, bucket in channels.items():
        for thread, seeds in bucket['threaded'].items():
            groups.append({'channel_id': channel, 'anchor': thread, 'kind': 'thread', 'seeds': seeds})
        clusters = []
        for msg in sorted(bucket['toplevel'], key=lambda m: Decimal(m['ts'])):
            if clusters and Decimal(msg['ts']) - Decimal(clusters[-1][-1]['ts']) <= 1800:
                clusters[-1].append(msg)
            else:
                clusters.append([msg])
        for cluster in clusters:
            groups.append({'channel_id': channel, 'anchor': cluster[0]['ts'], 'kind': 'conversation', 'seeds': cluster})
    return sorted(groups, key=lambda g: (Decimal(g['anchor']), g['channel_id']))


def _date(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise UserError('source window requires timezone')
    return result.astimezone(timezone.utc)


def validate_source_config(config):
    for key in ('source_key', 'account_key', 'scope', 'read_method'):
        if not config.get(key):
            raise UserError('source not ready: missing ' + key)
    relevance = config.get('relevance') or {}
    requirements = relevance.get('identity_requirements', [])
    if not isinstance(requirements, list) or not set(requirements) <= {'name', 'aliases', 'user_id'}:
        raise UserError('invalid relevance identity requirements')
    if requirements:
        identity = config.get('identity') or {}
        if identity.get('confirmed') is not True or any(not identity.get(k) for k in requirements):
            raise UserError('source relevance identity needs interactive confirmation')
        if identity.get('account_key', config['account_key']) != config['account_key']:
            raise UserError('source relevance identity account mismatch')


PRIMARY_POINTER_KEYS = ('primary_cache', 'cache_path', 'path', 'file')
PRIMARY_MAX_BYTES = 5 * 1024 * 1024


def _hermes_home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


def _primary_roots(store) -> list[Path]:
    roots = [_hermes_home() / 'cache']
    state_root = getattr(store, 'state_root', None)
    if state_root is not None:
        state_root = Path(state_root)
        roots += [state_root, state_root.parent]
        roots += [p for p in state_root.parents if p.name == 'plugin-data'][:1]
    out = []
    for root in roots:
        try:
            out.append(root.resolve())
        except OSError:
            pass
    return out


def _has_text(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_text(value.get(k)) for k in ('text', 'body', 'content', 'snippet'))
    return False


def has_primary_content(item) -> bool:
    messages = item.get('messages')
    if isinstance(messages, list) and any(_has_text(m) for m in messages):
        return True
    if any(isinstance(item.get(k), str) and item[k].strip() for k in ('body', 'text', 'content')):
        return True
    return item.get('primary_content') not in (None, '', [], {})


def _pointer(item):
    for key in PRIMARY_POINTER_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.startswith('/') and Path(value).is_file():
            return key, value
    for key, value in item.items():
        if isinstance(value, str) and value.startswith('/') and '\n' not in value and len(value) < 4096:
            try:
                if Path(value).is_file():
                    return key, value
            except OSError:
                continue
    for key in PRIMARY_POINTER_KEYS:
        if isinstance(item.get(key), str) and item[key].startswith('/'):
            return key, item[key]
    return None, None


def inline_primary(item, store=None):
    """Return a copy of item that carries its full primary text in the run.

    Agents sometimes hand over a pointer to a cache file instead of the text.
    Only files under the Hermes cache or this plugin's data dir are read; the
    pointer is replaced by the content and only the file basename is kept.
    """
    if has_primary_content(item):
        return item
    label = '%r (%s)' % (item.get('title') or 'untitled', ', '.join(map(str, item.get('source_ids') or [])) or 'no source id')
    missing = 'item has no primary content: include the full message text (or full email body) in the envelope item: ' + label
    key, value = _pointer(item)
    if key is None:
        raise UserError(missing)
    try:
        path = Path(value).resolve(strict=True)
    except OSError:
        raise UserError('primary content file is unreadable for ' + label + '; ' + missing)
    if not any(path.is_relative_to(root) for root in _primary_roots(store)):
        raise UserError('primary content file is outside the Hermes cache and plugin data for ' + label + '; ' + missing)
    if not path.is_file() or path.stat().st_size > PRIMARY_MAX_BYTES:
        raise UserError('primary content file is missing or larger than 5 MB for ' + label + '; ' + missing)
    raw = path.read_text(encoding='utf-8', errors='replace')
    try:
        content = json.loads(raw)
    except ValueError:
        content = raw
    if content in (None, '', [], {}) or (isinstance(content, str) and not content.strip()):
        raise UserError('primary content file is empty for ' + label + '; ' + missing)
    content = _select_for_item(content, item)
    if content in (None, '', [], {}):
        raise UserError('could not find this item in its pointer file (unrecognized or too large) for ' + label + '; ' + missing)
    result = copy.deepcopy(item)
    result.pop(key, None)
    result.pop('primary_thread_id', None)
    result['primary_content'] = content
    if isinstance(content, dict) and isinstance(content.get('messages'), list):
        result['messages'] = content['messages']
    elif isinstance(content, list) and content and all(isinstance(m, dict) for m in content) and not isinstance(result.get('messages'), list):
        result['messages'] = content
    result['primary_inlined_from'] = path.name
    return result


def _header(msg, name):
    for h in ((msg.get('payload') or {}).get('headers') or []):
        if str(h.get('name', '')).lower() == name:
            return h.get('value', '')
    return ''


def _gmail_text(msg):
    return {'from': _header(msg, 'from'), 'to': _header(msg, 'to'), 'cc': _header(msg, 'cc'),
            'date': _header(msg, 'date'), 'subject': _header(msg, 'subject'), 'id': msg.get('id'),
            'text': extract_message_text(msg.get('payload') or {}) or msg.get('snippet', '')}


def _slack_text(msg):
    return {'user': msg.get('user') or msg.get('username') or msg.get('bot_id'), 'ts': msg.get('ts'),
            'thread_ts': msg.get('thread_ts'), 'text': msg.get('text', ''),
            'files': [f.get('name') for f in msg.get('files') or [] if isinstance(f, dict)]}


SMALL_UNKNOWN_BYTES = 200_000


def _select_for_item(content, item):
    """From a shared cache file, keep only this item's own thread as plain text (no raw base64 payloads)."""
    ids = [str(x) for x in item.get('source_ids') or []]
    gmail = [x.rsplit(':', 1)[-1] for x in ids if x.startswith('gmail:')]
    want = str(item.get('primary_thread_id') or (gmail[0] if gmail else '') or '')
    # Gmail: a list of thread objects {id, messages: [raw messages]}, or one thread object.
    threads = content if isinstance(content, list) else [content] if isinstance(content, dict) and 'id' in content else None
    if threads and all(isinstance(t, dict) for t in threads) and any('messages' in t and 'id' in t for t in threads):
        chosen = [t for t in threads if str(t.get('id')) == want] if want else (threads if len(threads) == 1 else [])
        if not chosen:
            return None
        return [_gmail_text(m) if 'payload' in m else m for m in chosen[0].get('messages') or [] if isinstance(m, dict)]
    # Slack: a channel dump {messages: [...]}; keep the thread root and its replies.
    if isinstance(content, dict) and isinstance(content.get('messages'), list):
        slack = [x for x in ids if x.startswith('slack:')]
        root = slack[0].rsplit(':', 1)[-1] if slack else ''
        msgs = [m for m in content['messages'] if isinstance(m, dict)]
        if root:
            mine = [m for m in msgs if str(m.get('ts')) == root or str(m.get('thread_ts')) == root]
            msgs = mine or msgs
        return [_slack_text(m) if ('ts' in m and 'text' in m) else m for m in msgs]
    # Unrecognized format: inline only when small, so an unfamiliar dump never becomes one huge blob.
    if len(json.dumps(content, default=str)) > SMALL_UNKNOWN_BYTES:
        return None
    return content


def _persist_items(store, stream, config, items, *, inline=False):
    entries = []
    for item in items:
        if inline:
            item = inline_primary(item, store)
        ids = [canonical_source_id(x) for x in item['source_ids']]
        # Configured adapters must prove provider scope before this boundary.
        prefix = f"source:{config['source_key']}:{config['account_key']}:"
        if any((x.startswith('source:') and not x.startswith(prefix)) or (x.startswith('gmail:') and not x.startswith(f"gmail:{config['account_key']}:")) or (x.startswith('slack:') and not x.startswith(f"slack:{config['account_key']}:")) for x in ids):
            raise UserError('candidate source account mismatch')
        revision = item.get('source_revision')
        if not isinstance(revision, str) or not revision:
            raise UserError('source activity revision required')
        entries.append({'source_ids': ids, 'source_revision': revision, 'candidate': item})
    return store.enqueue_backlog(stream, config['source_key'], entries)


class SourceAdapter:
    """Trusted integration-owned reader, not a model-supplied completeness flag.

    read_page(config,start,end,cursor) uses the already approved existing tool.
    It must return the actual scoped account/window, full normalized items and
    explicit pagination evidence. A connector without this contract is partial.
    No account credential discovery or anonymous fallback is performed here.
    """
    def __init__(self, store, config: dict, *, read_page: Callable):
        validate_source_config(config)
        self.store, self.config, self.read_page = store, copy.deepcopy(config), read_page

    def collect(self, stream, *, start: str, end: str, max_pages: int | None = None, previous_receipt=None, filters=None):
        if _date(start) >= _date(end):
            raise UserError('source window must increase')
        if max_pages is not None and (type(max_pages) is not int or max_pages < 1):
            raise UserError('positive page bound required')
        previous = self.store.source_state(stream, self.config['source_key']).get('watermark')
        if previous and _date(end) < _date(previous):
            raise UserError('stale source window cannot regress committed coverage')
        if previous and _date(start) > _date(previous):
            raise UserError('source window has a coverage gap')
        prior = previous_receipt or {}
        if prior and any(prior.get(k) != v for k, v in {'start': start, 'end': end, 'account_key': self.config['account_key'], 'scope': self.config['scope']}.items()):
            raise UserError('continuation receipt differs from frozen source/window')
        cursor = prior.get('continuation')
        receipts = copy.deepcopy(prior.get('pages', []))
        pass_start = len(receipts)
        seen, ids = {p['cursor'] for p in receipts if p.get('cursor') is not None}, list(prior.get('backlog_ids', []))
        status, error, exhausted, primary_partial = 'partial', '', False, []
        screened = list(prior.get('screened', []))
        filtered = copy.deepcopy(prior.get('filtered') or {'messages': 0, 'skipped': [], 'context_only': []})
        while True:
            try:
                read_started = datetime.now(timezone.utc).isoformat()
                page = self.read_page(copy.deepcopy(self.config), start, end, cursor)
                read_ended = datetime.now(timezone.utc).isoformat()
                if not isinstance(page, dict):
                    raise UserError('reader lacks structured pagination')
                if page.get('account_key') != self.config['account_key'] or page.get('scope') != self.config['scope']:
                    raise UserError('reader account/scope mismatch')
                if page.get('start') != start or page.get('end') != end:
                    raise UserError('reader source window mismatch')
                if page.get('truncated') or page.get('error'):
                    raise UserError('reader truncated or failed')
                # Same pre-research screening as attested envelopes: calendar notices, auto-replies,
                # bulk mail and bot-only threads are saved as excluded, never researched.
                from .core.screening import screen_items, record_screened
                kept, dropped = screen_items(page['items'])
                kept, skipped = _apply_user_filters(kept, self.config, filters, filtered)
                dropped += skipped
                state = _persist_items(self.store, stream, self.config, kept)
                if dropped:
                    screened += record_screened(self.store, stream, self.config['source_key'], dropped,
                                                lambda xs: _persist_items(self.store, stream, self.config, xs))
                    state = self.store.source_state(stream, self.config['source_key'])
                ids = [x['backlog_id'] for x in state['backlog']]
                page_hash = hashlib.sha256(json.dumps(page, sort_keys=True).encode()).hexdigest()
                proof = {'read_started': read_started, 'read_ended': read_ended, 'cursor': cursor, 'sha256': page_hash, 'count': len(page['items'])}
                if 'reader_evidence' in page:
                    relative = 'source-evidence/' + page_hash + '.json'
                    atomic_json(self.store.state_root / relative, page['reader_evidence'])
                    proof['evidence'] = {'path': relative, 'page_sha256': page_hash}
                receipts.append(proof)
                if 'next_cursor' not in page or type(page.get('pagination_exhausted')) is not bool:
                    error = 'reader lacks pagination exhaustion evidence'
                    break
                next_cursor = page['next_cursor']
                if page['pagination_exhausted'] is True and next_cursor is None:
                    exhausted = True
                    partial = (page.get('collection') or {}).get('partial')
                    if partial:
                        # Every seed page was exhausted; only per-thread primary
                        # context was truncated or skipped. The source reads one
                        # page per thread and moves on, so the receipt stays
                        # partial for this run but the window is acquired.
                        primary_partial = [str(x) for x in partial]
                        error = ('partial primary coverage: ' + '; '.join(primary_partial))[:500]
                        break
                    status = 'complete'
                    break
                if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen:
                    error = 'missing or repeated continuation'
                    break
                seen.add(next_cursor)
                cursor = next_cursor
                if max_pages is not None and len(receipts) - pass_start >= max_pages:
                    error = 'bounded read pass; continuation retained'
                    break
            except Exception as exc:
                error, exhausted, primary_partial = str(exc)[:500], False, []
                status = 'partial' if receipts else 'failed'
                break
        receipt = {'config_revision': hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest(), 'covered_intervals': [[start, end]] if exhausted else [], 'status': status, 'verification': 'adapter_verified', 'account_key': self.config['account_key'], 'scope': self.config['scope'], 'start': start, 'end': end, 'pagination_exhausted': exhausted, 'continuation': cursor, 'pages': receipts, 'backlog_ids': ids, 'error': error}
        if primary_partial: receipt['primary_partial'] = primary_partial
        if screened: receipt['screened'] = screened
        if filtered['messages']: receipt['filtered'] = filtered
        self.store.record_coverage(stream, self.config['source_key'], receipt)
        return receipt


def _apply_user_filters(items, config, filters, summary):
    """Apply the user's message filters; returns (kept items, [(skipped item, reason)]).

    Excluded messages stay in kept items marked ``filtered`` (background only);
    items whose messages are all excluded are returned as skipped. ``summary``
    accumulates counts and titles for the digest and dashboard.
    """
    rules = (filters or {}).get('rules') or []
    if not rules:
        return items, []
    from .core.discovery_filters import apply_filters
    kept, skipped, found = apply_filters(items, rules, config=config, me=(filters or {}).get('me') or {})
    summary['messages'] = summary.get('messages', 0) + found['messages']
    for key in ('skipped', 'context_only'):
        summary.setdefault(key, []).extend(found[key])
        summary[key] = summary[key][-100:]
    return kept, skipped


def collect_attested(store, stream, config, envelope, filters=None):
    validate_source_config(config)
    if envelope.get('account_key') != config['account_key']:
        raise UserError('attested account mismatch')
    if _date(envelope['start']) >= _date(envelope['end']):
        raise UserError('source window must increase')
    # Calendar notices, auto-replies, bulk mail, bot threads and parent exclusions are saved as excluded, never researched.
    from .core.screening import screen_items, record_screened
    items, screened = screen_items(envelope.get('items', []))
    filtered = {'messages': 0, 'skipped': [], 'context_only': []}
    if (filters or {}).get('rules'):
        # Rules read the item's own messages, so file pointers are inlined first.
        items = [inline_primary(item, store) for item in items]
        items, skipped = _apply_user_filters(items, config, filters, filtered)
        screened = list(screened) + skipped
    state = _persist_items(store, stream, config, items, inline=True)
    screened = record_screened(store, stream, config['source_key'], screened, lambda xs: _persist_items(store, stream, config, xs))
    state = store.source_state(stream, config['source_key']) if screened else state
    receipt = {k: envelope.get(k) for k in ('status', 'start', 'end', 'pagination_exhausted', 'continuation', 'error')}
    if screened: receipt['screened'] = screened
    if filtered['messages']: receipt['filtered'] = filtered
    # Plain-language gaps the agent knows it missed (shown to the user); never boilerplate about attestation.
    gaps = envelope.get('gaps')
    if isinstance(gaps, list):
        from .core.digest_text import first_sentence
        receipt['gaps'] = [first_sentence(' '.join(str(g).split()))[:120] for g in gaps if str(g).strip()][:3]
    receipt.update(verification='agent_attested', backlog_ids=[x['backlog_id'] for x in state['backlog']], account_key=config['account_key'])
    store.record_coverage(stream, config['source_key'], receipt)
    return receipt

def _decode_b64(data: str) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
    except Exception:
        return ""

TEXT_ATTACHMENT_SUFFIXES = ('.md', '.txt', '.csv')
TEXT_ATTACHMENT_TYPES = ('text/plain', 'text/markdown', 'text/x-markdown', 'text/csv')
ATTACHMENT_MAX_BYTES = 50 * 1024
ATTACHMENTS_MAX_BYTES = 100 * 1024
ATTACHMENT_LABEL = '[Attachment: '


def _is_attachment(part: dict) -> bool:
    if part.get('filename'):
        return True
    for h in part.get('headers') or []:
        if str(h.get('name', '')).lower() == 'content-disposition' and str(h.get('value', '')).lower().startswith('attachment'):
            return True
    return False


def is_text_attachment(part: dict) -> bool:
    """A small-text attachment research may read: .md/.txt/.csv by name or text/plain|markdown|csv by type."""
    if not isinstance(part, dict) or not _is_attachment(part):
        return False
    name = str(part.get('filename') or '').lower()
    mime = str(part.get('mimeType') or '').lower().split(';')[0].strip()
    return name.endswith(TEXT_ATTACHMENT_SUFFIXES) or mime in TEXT_ATTACHMENT_TYPES


def _attachment_parts(payload: dict):
    for part in (payload or {}).get('parts') or []:
        if not isinstance(part, dict):
            continue
        if _is_attachment(part):
            yield part
        else:
            yield from _attachment_parts(part)


def _cut_utf8(raw: bytes, limit: int) -> str:
    return raw[:limit].decode('utf-8', errors='ignore')


def extract_attachment_text(payload: dict) -> str:
    """Labeled blocks for inline text attachments; other attachments stay filename-only (omitted).

    Bounded: ATTACHMENT_MAX_BYTES per attachment and ATTACHMENTS_MAX_BYTES per message, with a
    plain note wherever text was cut, so nothing is lost silently.
    """
    blocks, budget = [], ATTACHMENTS_MAX_BYTES
    for part in _attachment_parts(payload):
        if not is_text_attachment(part):
            continue
        data = (part.get('body') or {}).get('data')
        if not data:
            continue
        try:
            raw = base64.urlsafe_b64decode(str(data) + '===')
        except Exception:
            continue
        name = ' '.join(str(part.get('filename') or 'attachment').split())[:200].replace(']', ')')
        limit = min(ATTACHMENT_MAX_BYTES, budget)
        if limit <= 0:
            blocks.append(f'{ATTACHMENT_LABEL}{name}]\n(not included: this message\'s attachment text limit was reached)')
            continue
        text = _normalize_text(_cut_utf8(raw, limit))
        budget -= min(len(raw), limit)
        if len(raw) > limit:
            text += f'\n(attachment truncated: first {limit // 1024} KB of {max(1, len(raw) // 1024)} KB shown)'
        if text:
            blocks.append(f'{ATTACHMENT_LABEL}{name}]\n{text}')
    return '\n\n'.join(blocks)


def extract_message_text(payload: dict) -> str:
    """Message body plus labeled text-attachment blocks."""
    body = extract_body_text(payload)
    extra = extract_attachment_text(payload)
    return (body + '\n\n' + extra if body else extra) if extra else body


def extract_body_text(payload: dict) -> str:
    """Best-effort plaintext extraction from a Gmail message payload (attachments excluded)."""
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}
    if mime == "text/plain":
        return _normalize_text(_decode_b64(body.get("data", "")))
    parts = [p for p in payload.get("parts") or [] if isinstance(p, dict) and not _is_attachment(p)]
    # Prefer text/plain children
    for p in parts:
        if p.get("mimeType") == "text/plain":
            t = _normalize_text(_decode_b64((p.get("body") or {}).get("data", "")))
            if t:
                return t
    # Recurse multipart/*
    for p in parts:
        t = extract_body_text(p)
        if t:
            return t
    # Fallback: strip HTML tags from text/html
    if mime == "text/html":
        html = _decode_b64(body.get("data", ""))
        return _html_to_text(html)
    for p in parts:
        if p.get("mimeType") == "text/html":
            html = _decode_b64((p.get("body") or {}).get("data", ""))
            return _html_to_text(html)
    return ""

def _link_text(match) -> str:
    url, label = match.group(1).strip(), re.sub(r"<[^>]+>", "", match.group(2)).strip()
    if not url.lower().startswith(("http://", "https://")):
        return label
    return f"{label} ({url})" if label and html.unescape(label) != html.unescape(url) else url


_LINK_RE = re.compile(r"""(?is)<\s*a\b[^>]{0,2000}?(?<![\w-])href\s*=\s*["']([^"'<>]{1,4000})["'][^>]{0,2000}>((?:(?!<\s*a\b).){0,2000}?)<\s*/\s*a\s*>""")


def _html_to_text(raw_html: str) -> str:
    # Source block/list boundaries must precede tag stripping.
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", raw_html)
    text = re.sub(r"(?i)</\s*(?:p|div|li|tr|h[1-6])\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", text)
    # Keep link targets (label (url)) so research can open linked transcripts.
    # Bounded and linear on untrusted mail: the opening tag and the label are
    # capped, the label never crosses another <a, and data-href is ignored.
    text = _LINK_RE.sub(_link_text, text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return _normalize_text(text)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    # Collapse repeated blank lines, preserving paragraph separation.
    out: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                out.append("")
            blank = True
            continue
        out.append(line)
        blank = False
    return "\n".join(out).strip()
