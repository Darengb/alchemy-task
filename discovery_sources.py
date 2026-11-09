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
            full.append({'id': msg['id'], 'from': sender, 'subject': headers.get('subject', ''), 'date': msg['internalDate'], 'body': extract_body_text(payload)})
        if config.get('kind') == 'transcript':
            service = config.get('service_sender', '').strip().lower()
            for raw, msg in zip(ordered, full):
                when = int(msg['date']) / 1000
                if not service or msg['from'] != service:
                    continue
                if config.get('window_start') and when < _date(config['window_start']).timestamp():
                    continue
                if config.get('window_end') and when > _date(config['window_end']).timestamp():
                    continue
                steps = extract_suggested_next_steps(msg['body'])
                if not steps:
                    continue
                msg['suggested_next_steps'] = steps
                identity = canonical_source_id(f"gmail:{config['account_key']}:{tid}:{msg['id']}")
                candidate = {'title': msg['subject'] or 'Meeting follow-up', 'source_ids': [identity], 'source_revision': hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(), 'source_key': config['source_key']}
                out.append({'candidate': candidate, 'messages': [msg], 'latest_activity': int(msg['date'])})
            continue
        allowed = {str(x).strip().lower() for x in config.get('sender_domains', [])}
        excluded = {str(x).strip().lower() for x in config.get('excluded_senders', [])}
        relevant = any(m['from'] not in excluded and (not allowed or m['from'].rsplit('@', 1)[-1] in allowed) for m in full)
        # Source narrow one-message owner report, case-insensitive, not owner-only.
        report = config.get('owner_report_pattern')
        subject = next((m['subject'] for m in full if m['subject']), '')
        owner_only_report = len(full) == 1 and full[0]['from'] == config.get('owner_email', '').strip().lower() and report and re.search(report, subject, re.I)
        if not relevant or owner_only_report:
            continue
        if config.get('window_start') and int(ordered[-1]['internalDate']) < int(_date(config['window_start']).timestamp()) * 1000:
            continue
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


def _persist_items(store, stream, config, items):
    entries = []
    for item in items:
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

    def collect(self, stream, *, start: str, end: str, max_pages: int | None = None, previous_receipt=None):
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
        status, error, exhausted = 'partial', '', False
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
                state = _persist_items(self.store, stream, self.config, page['items'])
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
                    exhausted, status = True, 'complete'
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
                error = str(exc)[:500]
                status = 'partial' if receipts else 'failed'
                break
        receipt = {'config_revision': hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest(), 'covered_intervals': [[start, end]] if exhausted else [], 'status': status, 'verification': 'adapter_verified', 'account_key': self.config['account_key'], 'scope': self.config['scope'], 'start': start, 'end': end, 'pagination_exhausted': exhausted, 'continuation': cursor, 'pages': receipts, 'backlog_ids': ids, 'error': error}
        self.store.record_coverage(stream, self.config['source_key'], receipt)
        return receipt


def collect_attested(store, stream, config, envelope):
    validate_source_config(config)
    if envelope.get('account_key') != config['account_key']:
        raise UserError('attested account mismatch')
    if _date(envelope['start']) >= _date(envelope['end']):
        raise UserError('source window must increase')
    state = _persist_items(store, stream, config, envelope.get('items', []))
    receipt = {k: envelope.get(k) for k in ('status', 'start', 'end', 'pagination_exhausted', 'continuation', 'error')}
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

NEXT_SECTION_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:Summary|Notes|Transcript|Meeting notes|Details|Participants|Action items|Suggested email|Key points|Next steps|Learn more|View in|Open in|Recording)\b",
    re.IGNORECASE,
)

SECTION_HEADING_RE = re.compile(r"^\s*(?:#+\s*)?Suggested next steps\s*:?[\s\u00a0]*$", re.IGNORECASE)

def extract_body_text(payload: dict) -> str:
    """Best-effort plaintext extraction from a Gmail message payload."""
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}
    if mime == "text/plain":
        return _decode_b64(body.get("data", ""))
    parts = payload.get("parts") or []
    # Prefer text/plain children
    for p in parts:
        if p.get("mimeType") == "text/plain":
            t = _decode_b64((p.get("body") or {}).get("data", ""))
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

def _html_to_text(raw_html: str) -> str:
    # Source block/list boundaries must precede tag stripping.
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", raw_html)
    text = re.sub(r"(?i)</\s*(?:p|div|li|tr|h[1-6])\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", text)
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

def extract_suggested_next_steps(body: str) -> str:
    """Return the body text under the "Suggested next steps" heading.

    Gemini Notes formatting has changed over time, so this uses a heading-based
    parser first, then a looser inline fallback.
    """
    if not body:
        return ""

    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not SECTION_HEADING_RE.match(line):
            continue
        section: list[str] = []
        for raw in lines[i + 1 :]:
            line = raw.strip()
            if not line:
                if section and section[-1] != "":
                    section.append("")
                continue
            if NEXT_SECTION_RE.match(line):
                break
            # Gemini/Gmail footers tend to start after the useful suggested steps.
            if re.search(
                r"^(?:We've updated|Meeting records|Document Notes by Gemini|Is the Next Steps section|Not Useful Email|Useful Email|Google LLC|This email|You have received this email|You received this|Google Workspace|Privacy Policy|Terms of Service)\b",
                line,
                re.I,
            ):
                break
            section.append(line)
        text = _normalize_text("\n".join(section))
        # An explicit empty section must not fall back across the next heading.
        return text

    # Fallback: inline/HTML-flattened section.
    m = re.search(
        r"Suggested next steps\s*:?(.*?)(?:\n\s*(?:Summary|Notes|Transcript|Meeting notes|Details|Participants|Action items|Suggested email|Key points|Next steps|Learn more|View in|Open in|Recording)\b|\Z)",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        return _normalize_text(m.group(1))
    return ""
