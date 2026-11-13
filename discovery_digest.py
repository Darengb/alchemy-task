"""Immutable discovery digests and profile-local, seven-day proposal bindings.

One atomic ledger allocates same-day numbers across streams. A prepared digest
is not delivery evidence. Pending/unknown sends never authorize automatic resend.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from .core.discovery_state import DiscoveryStore, atomic_json, read_json
from .core.discovery_identity import UserError, canonical_source_id
from urllib.parse import urlsplit, parse_qs
from .core.digest_text import digest_field, first_sentence


def _failure_status(failure):
    # Project operational diagnostics only; semantic/user context remains useful.
    reason = str(failure.get('reason') or 'Research needs attention')
    lifecycle = re.fullmatch(r'\s*lifecycle terminal ([A-Za-z_]+)\s*', reason)
    if lifecycle:
        return _LIFECYCLE.get(lifecycle.group(1).upper(), 'research stopped before it finished')
    if reason.startswith('could not be matched to your tasks'):
        return 'could not be matched to your tasks'
    if reason.startswith("not finished within this run's research time"):
        return 'research did not finish in time; it is queued for the next run'
    if re.search(r'(?:Error:|Exception:|Traceback|fatal:|areas/[^\s]+/tasks/|(?:^|\s)/[^\s]+|[a-f0-9]{8}-[a-f0-9-]{27,})', reason):
        return 'could not be completed in this run; it is queued for the next run'
    # Internal research-review wording (field names, candidate ids, repair instructions) is not for the user.
    if re.search(r'\b[a-z]+_[a-z_]+\b|\bc_[0-9a-f]{20}\b|\b(?:Repair|payload|bundle|workstream|schema)\b', reason):
        return 'research needs another pass; it is queued for the next run'
    # Drop a repeated "Needs attention: <title>:" prefix and never cut a word in half.
    title = str(failure.get('title') or '')
    reason = re.sub(r'^\s*(?:Needs attention:\s*)?' + (re.escape(title) + r'\s*:\s*' if title else ''), '', reason, flags=re.I) or reason
    text = first_sentence(reason)
    if len(text) > 160:
        text = text[:160].rsplit(' ', 1)[0].rstrip(' ,;:') + '...'
    return text


def failure_queued(failure):
    """A failure the next run researches again (time box, another pass): counted, not listed."""
    return _failure_status(failure).endswith('it is queued for the next run')


WRITTEN_STATES = {'local_verified', 'git_pending', 'phone_pending', 'complete'}
# Plain words for research child lifecycle ends; both attempts were used when a failure reaches the digest.
_LIFECYCLE = {'INTERRUPTED': 'research was interrupted before it finished',
              'TIMEOUT': 'research timed out before it finished', 'TIMED_OUT': 'research timed out before it finished',
              'FAILED': 'research failed before it finished', 'ERROR': 'research failed before it finished',
              'CANCELLED': 'research was cancelled before it finished', 'CANCELED': 'research was cancelled before it finished'}


def already_current(item):
    """An existing-task match whose research says that task already has everything."""
    return item.get('existing_task_already_current') is True and item.get('kind') in {'semantic', 'selection'} and bool(item.get('targets'))


def _attested_read(source):
    # Read by the agent with the user's own tools: no structured reader proves completeness.
    return source.get('verification') == 'agent_attested' and source.get('status') in {'partial', 'complete'} and not _skipped(source)


def _skipped(source):
    return list(dict.fromkeys(str(x).split(' skipped: ', 1)[1] for x in source.get('primary_partial') or [] if ' skipped: ' in str(x)))


def coverage_degraded(source):
    """Incomplete coverage that is a real gap; an agent-attested read is not one."""
    return _source_problem(source) is not None


_PARTIAL_REASONS = (('bounded read pass', 'was only partly read before the page limit; the rest is read next run'),
                    ('pagination', 'may not have been read to the end'),
                    ('continuation', 'may not have been read to the end'),
                    ('truncated', 'was only partly read'))


def _source_problem(source):
    """Plain text for a real coverage gap, else None. Reading with the user's own tools is expected and is
    never a gap by itself; a reported incomplete read, a skipped thread or a failed read is."""
    if source.get('status') == 'complete' and not source.get('gaps'): return None
    skipped = _skipped(source)
    if skipped: return ('had a thread that could not be read (' + '; '.join(skipped) + ')')[:160]
    if source.get('gaps'):
        return ('was only partly read: ' + '; '.join(source['gaps']))[:200]
    if _attested_read(source): return None  # read with the user's own tools, nothing reported missing
    if source.get('status') == 'failed' or not source.get('backlog_ids') and not source.get('pages'): return 'could not be read'
    error = ' '.join(str(source.get('error') or '').split()).lower()
    if 'partial primary coverage' in error: return None  # the item itself carries the gap into research
    for marker, text in _PARTIAL_REASONS:
        if marker in error: return text
    if error and source.get('status') != 'complete':
        return 'was only partly read (a read failed); the rest is read next run'  # never hide a failed scan
    return None


def _short_title(title, limit=60):
    title = ' '.join(str(title or '').split())
    if len(title) <= limit: return title
    return title[:limit].rsplit(' ', 1)[0].rstrip(' ,;:') + ' ...'


def _source_name(source):
    return str(source.get('name') or source.get('source_key') or source.get('source') or 'source')


def _join_names(names):
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


def _link_label(url):
    host = re.sub(r'^[a-z]+://', '', str(url).lower()).split('/', 1)[0]
    if host.endswith('slack.com'): return 'Open Slack thread'
    if host == 'mail.google.com' or host.startswith('outlook.'): return 'Open email'
    if host in {'docs.google.com', 'drive.google.com'} or host.endswith(('notion.so', 'notion.site')): return 'Open doc'
    return 'Open source'


def _day_label(day):
    date = dt.date.fromisoformat(day)
    return f"{date.strftime('%B')} {date.day}"


def _plural(n, one, many):
    return f'{n} {one if n == 1 else many}'



def choice_line(ref, targets):
    """Reply instructions for an existing-task proposal, numbered like the listed targets."""
    if len(targets) <= 1:
        return f'Reply "{ref}, update" to add this to the existing task, or "{ref}, create" for a separate task.'
    picked = next((i for i, t in enumerate(targets, 1) if t.get('recommended')), None)
    if picked:
        others = [i for i in range(1, len(targets) + 1) if i != picked]
        title = targets[picked - 1].get('title', 'Existing task')
        if len(others) == 1:
            rest = f'"{ref}, update {others[0]}" for the other task'
        else:
            rest = ' or '.join(f'"{ref}, update {i}"' for i in others) if len(others) == 2 else \
                ', '.join(f'"{ref}, update {i}"' for i in others[:-1]) + f' or "{ref}, update {others[-1]}"'
            rest += ' for another listed task'
        return f'Reply "{ref}, update" to add this to "{title}", {rest}, or "{ref}, create" for a separate task.'
    numbers = list(range(1, len(targets) + 1))
    listed = ', '.join(f'"{ref}, update {i}"' for i in numbers[:-1]) + f' or "{ref}, update {numbers[-1]}"'
    if len(numbers) == 2: listed = f'"{ref}, update 1" or "{ref}, update 2"'
    return f'Reply {listed} to add this to that task, or "{ref}, create" for a separate task.'


SUBTASKS_SHOWN = 5


def subtask_lines(items, shown=SUBTASKS_SHOWN):
    """A short bulleted list of a proposal's subtasks: the first few, then '+N more'."""
    items = [' '.join(str(x).split()) for x in items or [] if str(x).strip()]
    lines = ['- ' + x for x in items[:shown]]
    if len(items) > shown: lines.append(f'- +{len(items) - shown} more')
    return lines


def _also_line(repeat):
    """One compact line: an earlier open proposal gets this run's new step and subtasks."""
    step = first_sentence(repeat.get('next_action') or '')
    subtasks = [x for x in repeat.get('new_subtasks') or [] if x]
    if not step and not subtasks: return ''
    text = step.rstrip('.') if step else ''
    if subtasks:
        more = '; '.join(subtasks[:3]) + (f' (+{len(subtasks) - 3} more)' if len(subtasks) > 3 else '')
        text = (text + '; also: ' + more) if text else more
    if len(text) > 200: text = text[:200].rsplit(' ', 1)[0].rstrip(' ,;:') + ' ...'
    return f"{repeat['earlier_ref']} gets a new step: {text}"


def render_digest(run, *, stream, day, numbered, already, failures, coverage, outcomes, deferred, blocked,
                  queued_count=0, follow_up_started=False, still_open=(), queued_reason='', also=()):
    """The Telegram digest text. Short fields come from authored digest_* research
    fields (first-sentence fallback); the stored items keep the full research."""
    date = dt.date.fromisoformat(day)
    review = hashlib.sha256(run.encode()).hexdigest()[:12]
    head = [f'**Review:** `{review}`', f"**{_plural(len(numbered), 'follow-up', 'follow-ups')}**"]
    written = [o for o in outcomes if o.get('status') in WRITTEN_STATES]
    # Blocked existing-task updates count as existing-task outcomes, not failures.
    if outcomes or blocked: head.append(f"**{_plural(len(outcomes) + len(blocked), 'existing task outcome', 'existing task outcomes')}**")
    # Items the next run researches again are one "Still researching" line, not attention.
    queued = len(deferred) + sum(1 for f in failures if failure_queued(f))
    queued = queued_count or queued
    attention_failures = [f for f in failures if not failure_queued(f)]
    source_problems = [(s, _source_problem(s)) for s in coverage]
    source_problems = [(s, p) for s, p in source_problems if p]
    attention = len(attention_failures) + len(source_problems)
    head.append(f"**{attention} {'needs' if attention == 1 else 'need'} attention**")
    lines = [f'## {stream} Task Discovery', '', f"**{date.strftime('%A, %B')} {date.day}**", ' · '.join(head), '']
    for item in numbered:
        semantic = item['kind'] in {'semantic', 'selection'}
        ref = item['ref']
        lines += [f"### {ref}. {item['title']}", '']
        if semantic:
            lines.append('**Task type:** Potential existing task update')
            targets = item.get('targets', [])
            if len(targets) > 1:
                lines.append('**Existing tasks:**')
                lines += [f"{i}. {t.get('title', 'Existing task')}" + (' (recommended)' if t.get('recommended') else '')
                          for i, t in enumerate(targets, 1)]
            else:
                lines.append('**Existing task:** ' + '; '.join(t.get('title', 'Existing task') for t in targets))
        elif item.get('research_disposition') == 'uncertain':
            lines.append('**Task type:** Unsure')
        else:
            lines.append('**Task type:** New task')
        lines.append('')
        if item.get('research_disposition') == 'uncertain':
            why = next((str(x) for x in item.get('uncertainty') or [] if str(x).strip()), 'User judgment required.')
            lines += ['**Why unsure:** ' + first_sentence(why), '']
        state = digest_field(item, 'digest_current_state')
        if state: lines += ['**Current state:** ' + state, '']
        if semantic:
            addition = digest_field(item, 'digest_addition')
            if addition: lines += ['**Proposed addition:** ' + addition, '']
        action = digest_field(item, 'digest_next_action')
        if action: lines += ['**Next action:** ' + action, '']
        if item.get('subtasks'): lines += [*subtask_lines(item['subtasks']), '']
        if item.get('not_proposed_line'): lines += [str(item['not_proposed_line']), '']
        if semantic:
            lines += ['**Choice:** ' + choice_line(ref, item.get('targets', [])), '']
        for url in list(dict.fromkeys(item.get('source_links') or []))[:2]:
            lines.append(f'[{_link_label(url)} \u2192]({url})')
        if item.get('source_links'): lines.append('')
        # Inaccessible supporting sources are evidence limits, kept in the item record only.
        lines += ['---', '']
    if not numbered:
        # Deferred or blocked work is not "nothing new": only a complete check with
        # nothing left says no follow-ups were found.
        degraded = bool(failures or any(coverage_degraded(s) for s in coverage))
        quiet = not degraded and not outcomes and not deferred and not blocked and not already and not queued and not still_open
        lines += ['No new follow-ups found.' if quiet else 'No new proposals to review.', '']
    footer = []
    # Items already recorded in an existing task are kept in the digest record (and the dashboard), not the chat text.
    for outcome in outcomes:
        line = f"**Existing task:** {outcome['title']}: {outcome['status']}"
        for surface in ('git', 'phone'):
            detail = outcome.get(surface) or {}
            if detail: line += f"; {surface}={detail.get('state', 'unknown')}"
        if outcome.get('resume_action'): line += '; resume with discovery_conversion_recover for this saved run/unit'
        footer.append(line)
    for conflict in blocked:
        # Multiple exact matches are an unnumbered blocked existing-task item.
        footer.append(f"**Existing task update blocked:** {conflict['title']}: multiple exact task matches conflict; nothing was changed"
                      + (' (' + '; '.join(t.get('title', 'Existing task') for t in conflict.get('targets', [])) + ')' if conflict.get('targets') else ''))
    also_lines = [(r['earlier_proposal_id'], _also_line(r)) for r in also]
    also_lines = [(pid, line) for pid, line in also_lines if line]
    listed = {pid for pid, _ in also_lines}
    open_rest = [o for o in still_open if o.get('proposal_id') not in listed]
    if open_rest:
        footer.append('**Still open from earlier:** ' + ' · '.join(
            f"{o['ref']}{' from ' + _day_label(o['day']) if o.get('day') and o['day'] != day else ''} ({_short_title(o['title'])})" for o in open_rest))
    for _, line in also_lines:
        footer.append('**Also from an earlier thread:** ' + line)
    if queued:
        verb = 'is' if queued == 1 else 'are'
        if queued_reason == 'daily_cap':
            footer.append(f"**Still researching:** {_plural(queued, 'item', 'items')} {verb} waiting for tomorrow (daily limit reached).")
        elif follow_up_started:
            footer.append(f"**Still researching:** {_plural(queued, 'item', 'items')} {verb} queued for the next run, which starts within 30 minutes.")
        else:
            footer.append(f"**Still researching:** {_plural(queued, 'item', 'items')} {verb} queued for the next scheduled run.")
    # One compact paragraph so attention notes never push the proposals out of view.
    notes = [(str(f['title']) + ': ' if f.get('title') else '') + _failure_status(f) for f in attention_failures]
    notes += [f'{_source_name(source)} {problem}' for source, problem in source_problems]
    if notes:
        footer.append('**Needs attention:** ' + ' · '.join(n.rstrip('.') for n in notes) + '.')
    filtered = sum(int((s.get('filtered') or {}).get('messages') or 0) for s in coverage if isinstance(s, dict))
    if filtered > 0:
        footer.append(f"{filtered} {'message' if filtered == 1 else 'messages'} skipped by your filters.")
    for line in footer: lines += [line, '']
    if numbered:
        example = next((i['ref'] for i in numbered if i['kind'] == 'new'), numbered[0]['ref'])
        lines.append(f'Reply with the item numbers you want, like "{example}, create". Items stay open for seven days.')
    if not written:
        lines.append('No tasks were created or changed.')
    return '\n'.join(lines).rstrip() + '\n'


def _link_keys(url):
    """(conversation key, message key) for a source link; provider-neutral fallback is the bare URL."""
    parts = urlsplit(str(url).strip())
    host = parts.netloc.lower()
    if host == 'mail.google.com':
        ident = parts.fragment.rstrip('/').rsplit('/', 1)[-1]
        if ident: return 'mail:' + ident, None
    if host.endswith('slack.com'):
        found = re.search(r'/archives/([A-Za-z0-9]+)/p(\d{10})(\d{6})', parts.path)
        if found:
            channel, ts = found.group(1), found.group(2) + '.' + found.group(3)
            root = (parse_qs(parts.query).get('thread_ts') or [ts])[0]
            return f'slack:{channel}:{root}', f'slack:{channel}:{ts}'
    plain = (host + parts.path).rstrip('/').lower()
    return ('url:' + plain, None) if plain else (None, None)


def _typed_keys(source):
    try:
        ident = canonical_source_id(source)
    except (UserError, TypeError, ValueError):
        return None, None
    bits = ident.split(':')
    if bits[0] == 'gmail':
        return 'mail:' + bits[2], ('mail-msg:' + bits[3] if len(bits) == 4 else None)
    if bits[0] == 'slack':
        return f'slack:{bits[2]}:{bits[3]}', (f'slack:{bits[2]}:{bits[4]}' if len(bits) == 5 else None)
    return ident, None


_CONVERSATION_PREFIXES = ('slack:', 'mail:')


def decisive_sources(item):
    """Stable decisive source keys of a proposal: typed exact ids plus every conversation link.

    Every source link that names a conversation (a chat thread or an email thread) counts, in any
    order; the primary link counts whatever it is. Returns (conversation keys, message keys).
    Other supporting links (files, docs) are not decisive."""
    typed = item.get('exact_source_ids') or item.get('source_ids') or []
    pairs = [_typed_keys(x) for x in typed]
    links = [_link_keys(url) for url in item.get('source_links') or []]
    pairs += [pair for i, pair in enumerate(links) if i == 0 and not any(c for c, _ in pairs)
              or (pair[0] or '').startswith(_CONVERSATION_PREFIXES)]
    return {c for c, _ in pairs if c}, {m for _, m in pairs if m}


def _earlier_match(data, run, raw, keys, messages, day, split_keys):
    """Earlier proposal (any stream) this item repeats, or None.

    A shared decisive source matches. When that source holds several separate asks
    (split in this run or an earlier one), only the same unit matches. Pending
    proposals suppress only inside their seven days; dismissed, approved or
    completed ones suppress unless the decisive source shows a newer message."""
    best = None
    for pid, record in data['proposals'].items():
        b = record['binding']
        if b.get('run_id') == run or b.get('relist'): continue  # a relisting test stream never hides others' items
        if record.get('state') == 'pending' and b.get('expires', '') < day: continue
        old_keys, old_messages = decisive_sources(b)
        shared = keys & old_keys
        if not shared: continue
        if (shared & split_keys or shared & set(data.get('split_sources', ()))) and b.get('unit_id') != raw.get('unit_id'): continue
        if record.get('state') != 'pending' and messages and old_messages and not messages <= old_messages:
            continue  # the source has a newer decisive message: a real new follow-up
        if best is None or (b['day'], b['number']) > (best[1]['day'], best[1]['number']):
            best = (pid, b, record.get('state'))
    return best


class DiscoveryDigest:
    def __init__(self, root):
        self.root = Path(root)
        self.store = DiscoveryStore(self.root)
        self.path = self.root / 'digest-ledger.json'

    def _load(self):
        return read_json(self.path, {'digests': {}, 'proposals': {}, 'numbers': {}, 'seen': {}, 'delivery': {}})

    def prepare(self, run, *, stream, day, origin, items, failures=None, coverage=None, outcomes=None, label='', review_namespace='',
                deferred=None, blocked=None, queued_count=0, follow_up_started=False, queued_reason='', relist=False):
        dt.date.fromisoformat(day)
        if not origin.get('session_id'):
            raise UserError('digest requires actual origin session')
        with self.store._lock('digest-ledger'):
            data = self._load()
            if run in data['digests']:
                return data['digests'][run]
            numbered = []
            key = origin['session_id'] + ':' + day
            already, still_open, repeats, also = [], [], [], []
            items = [self._with_subtasks(run, raw) for raw in items]
            # Several units from one decisive source are separate asks: only their own unit repeats them.
            counts = {}
            for raw in items:
                for k in decisive_sources(raw)[0]: counts.setdefault(k, set()).add(raw.get('unit_id'))
            split_keys = {k for k, units in counts.items() if len(units) > 1}
            if split_keys: data['split_sources'] = sorted(set(data.get('split_sources', [])) | split_keys)
            for raw in items:
                if raw['kind'] not in {'new', 'semantic', 'selection'}:
                    raise UserError('only new or update proposals are numbered')
                if already_current(raw):
                    # Research says the matched task already records this work: listed once,
                    # unnumbered, with no proposal record to approve.
                    already.append({'unit_id': raw['unit_id'], 'title': raw['title'], 'targets': raw.get('targets', [])})
                    continue
                binding = [raw['unit_id'], raw['research_revision']]
                if review_namespace: binding.append(review_namespace)
                identity = hashlib.sha256(json.dumps(binding).encode()).hexdigest()
                # Same accepted action/revision is not relisted in another stream.
                if identity in data['seen'] and not relist:
                    continue
                keys, messages = decisive_sources(raw)
                # A new run over the same source does not renumber an open or resolved proposal.
                # Review reruns (review_namespace) relist on purpose.
                earlier = None if review_namespace or relist else _earlier_match(data, run, raw, keys, messages, day, split_keys)
                if earlier:
                    pid, b, state = earlier
                    repeats.append({'unit_id': raw['unit_id'], 'research_revision': raw['research_revision'], 'title': raw['title'],
                                    'earlier_proposal_id': pid, 'earlier_ref': b['ref'], 'earlier_day': b['day'], 'earlier_state': state})
                    if state == 'pending' and pid not in {o['proposal_id'] for o in still_open}:
                        still_open.append({'proposal_id': pid, 'ref': b['ref'], 'day': b['day'], 'title': b['title']})
                    if state == 'pending' and pid not in {a['earlier_proposal_id'] for a in also}:
                        # The earlier proposal stays the place to reply; this run's new step is listed compactly.
                        step = digest_field(raw, 'digest_next_action')
                        known = {' '.join(str(x).split()).casefold() for x in b.get('subtasks') or []}
                        fresh = [x for x in raw.get('subtasks') or [] if ' '.join(str(x).split()).casefold() not in known]
                        if step and step == digest_field(b, 'digest_next_action'): step = ''
                        if step or fresh:
                            also.append({'earlier_proposal_id': pid, 'earlier_ref': b['ref'], 'next_action': step, 'new_subtasks': fresh})
                    data['seen'][identity] = pid
                    continue
                num = data['numbers'].get(key, 0) + 1
                data['numbers'][key] = num
                pid = 'p_' + hashlib.sha256((run + ':' + identity).encode()).hexdigest()[:24]
                item = {**raw, 'proposal_id': pid, 'run_id': run, 'stream': stream, 'day': day, 'number': num,
                        'ref': label + str(num), 'origin': origin,
                        'expires': (dt.date.fromisoformat(day) + dt.timedelta(days=7)).isoformat()}
                if relist: item['relist'] = True
                numbered.append(item)
                data['proposals'][pid] = {'binding': item, 'state': 'pending'}
                data['seen'][identity] = pid
            # One 'also mentioned' line per source item, under its first numbered proposal.
            shown_parents = set()
            for item in numbered:
                extra = item.get('not_proposed') if isinstance(item.get('not_proposed'), dict) else None
                parent = extra.get('parent_candidate_id') if extra else None
                if extra and extra.get('line') and parent not in shown_parents:
                    shown_parents.add(parent)
                    item['not_proposed_line'] = str(extra['line'])[:600]
                    data['proposals'][item['proposal_id']]['binding'] = item
            failures, coverage, deferred, blocked = failures or [], coverage or [], deferred or [], blocked or []
            text = render_digest(run, stream=stream, day=day, numbered=numbered, already=already, failures=failures,
                                 coverage=coverage, outcomes=outcomes or [], deferred=deferred, blocked=blocked,
                                 queued_count=queued_count, follow_up_started=follow_up_started, still_open=still_open,
                                 queued_reason=queued_reason, also=also)
            result = {'run_id': run, 'stream': stream, 'day': day, 'prepared_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'origin': origin, 'items': numbered,
                      'failures': failures, 'deferred': deferred, 'coverage': coverage, 'outcomes': outcomes or [], 'blocked': blocked,
                      'already_current': already, 'still_open': still_open, 'repeats': repeats,
                      'queued_count': queued_count, 'follow_up_started': follow_up_started, 'queued_reason': queued_reason,
                      'also_from_earlier': also, 'text': text}
            result['sha256'] = hashlib.sha256(result['text'].encode()).hexdigest()
            data['digests'][run] = result
            data['delivery'][run] = {'state': 'prepared', 'digest_sha256': result['sha256'], 'origin': origin}
            atomic_json(self.path, data)
            return result

    def _with_subtasks(self, run, raw):
        """The proposal with its research subtasks; older decision records do not copy them."""
        if 'subtasks' in raw or not raw.get('unit_id'): return raw
        try:
            research = self.store.research_for(raw.get('run_id') or run, raw['unit_id'])
        except (UserError, OSError, ValueError, KeyError, TypeError):
            return raw
        items = [x for x in (research or {}).get('subtasks') or [] if isinstance(x, str) and x.strip()]
        return {**raw, 'subtasks': items} if items else raw

    def get(self, run):
        try:
            return self._load()['digests'][run]
        except KeyError as exc:
            raise UserError('no immutable digest for this run') from exc

    def resolve(self, ref, *, session_id, today, day='', stream='', origin_sessions=(), runs=None, days=None):
        date = dt.date.fromisoformat(today)
        if day == 'yesterday': day = (date - dt.timedelta(days=1)).isoformat()
        data = self._load()
        hits = [x['binding'] for x in data['proposals'].values()
                if (x['binding']['ref'].casefold() == str(ref).casefold() or str(x['binding']['number']) == str(ref) or x['binding']['proposal_id'] == ref)
                and (not stream or x['binding']['stream'] == stream)
                and (not day or x['binding']['day'] == day)]
        if runs is not None and not day and not str(ref).startswith('p_'):
            hits = [x for x in hits if x['run_id'] in runs]
        elif days is not None and not day and not str(ref).startswith('p_'):
            # A digest seen unquoted in the conversation selects its stream's whole
            # local day: daily numbers continue across same-day digests.
            hits = [x for x in hits if days.get(x['stream']) == x['day']]
            if not stream and str(ref).isdigit() and len(days) > 1:
                raise UserError('ambiguous reply; which stream? ' + ', '.join(sorted(days)))
        elif not day and not str(ref).startswith('p_'):
            # The newest digest selects each stream's daily numbering. Numbers continue
            # across same-day invocations, including an empty rerun; old days never
            # become an implicit fallback. Explicit review/transcript runs stay exact.
            newest = {}
            for digest in data['digests'].values():
                name = digest['stream']
                if stream and name != stream: continue
                if name not in newest or (digest['day'], digest.get('prepared_at', '')) > (newest[name]['day'], newest[name].get('prepared_at', '')):
                    newest[name] = digest
            recent = {name: d for name, d in newest.items()
                      if (dt.date.fromisoformat(d['day']) + dt.timedelta(days=7)).isoformat() >= today}
            # Preserve an expired-list error when there is only one old stream.
            selected = recent or newest
            hits = [x for x in hits if x['stream'] in selected and x['day'] == selected[x['stream']]['day']]
            if not stream and str(ref).isdigit() and len(selected) > 1:
                raise UserError('ambiguous reply; which stream? ' + ', '.join(sorted(selected)))
        if len(hits) != 1:
            streams = sorted({x['stream'] for x in hits})
            if len(streams) > 1:
                raise UserError('ambiguous reply; which stream? ' + ', '.join(streams))
            raise UserError('proposal reply is missing or ambiguous; specify the day or exact proposal_id, or reply to the digest message')
        if hits[0]['expires'] < today:
            raise UserError('proposal expired after seven days')
        return hits[0]

    def decide(self, proposal_id, state):
        if state not in {'approved', 'dismissed', 'complete'}:
            raise UserError('invalid proposal decision')
        with self.store._lock('digest-ledger'):
            data = self._load()
            if proposal_id not in data['proposals']: raise UserError('unknown proposal binding')
            old = data['proposals'][proposal_id]['state']
            if old in {'complete', 'dismissed'} and old != state:
                raise UserError('proposal already resolved')
            data['proposals'][proposal_id]['state'] = state
            atomic_json(self.path, data)
            return data['proposals'][proposal_id]

    def delivery(self, run):
        return self._load()['delivery'][run]

    def begin_delivery(self, run):
        with self.store._lock('digest-ledger'):
            data = self._load()
            receipt = data['delivery'][run]
            if receipt['state'] != 'prepared':
                raise UserError('delivery is pending/unknown/delivered; reconcile exact receipt, never blindly resend')
            receipt['state'] = 'inflight'
            atomic_json(self.path, data)
            return receipt

    def delivery_unknown(self, run, reason):
        with self.store._lock('digest-ledger'):
            data = self._load()
            if data['delivery'][run]['state'] == 'delivered':
                raise UserError('verified delivery cannot regress')
            data['delivery'][run].update(state='unknown', reason=reason)
            atomic_json(self.path, data)
            return data['delivery'][run]
