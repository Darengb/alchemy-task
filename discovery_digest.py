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
from .core.discovery_identity import UserError
from .core.digest_text import digest_field, first_sentence


def _failure_status(failure):
    # Project operational diagnostics only; semantic/user context remains useful.
    reason = str(failure.get('reason') or 'Research needs attention')
    lifecycle = re.fullmatch(r'\s*lifecycle terminal ([A-Za-z_]+)\s*', reason)
    if lifecycle:
        return _LIFECYCLE.get(lifecycle.group(1).upper(), 'research stopped before it finished')
    if re.search(r'(?:Error:|Exception:|Traceback|fatal:|areas/[^\s]+/tasks/|(?:^|\s)/[^\s]+|[a-f0-9]{8}-[a-f0-9-]{27,})', reason):
        return 'Operation unavailable; inspect saved review diagnostics and retry the saved operation'
    return reason[:400]


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
    return source.get('status') != 'complete' and not _attested_read(source)


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


def _plural(n, one, many):
    return f'{n} {one if n == 1 else many}'


def render_digest(run, *, stream, day, numbered, already, failures, coverage, outcomes, deferred, blocked):
    """The Telegram digest text. Short fields come from authored digest_* research
    fields (first-sentence fallback); the stored items keep the full research."""
    date = dt.date.fromisoformat(day)
    review = hashlib.sha256(run.encode()).hexdigest()[:12]
    head = [f'**Review:** `{review}`', f"**{_plural(len(numbered), 'follow-up', 'follow-ups')}**"]
    written = [o for o in outcomes if o.get('status') in WRITTEN_STATES]
    # Blocked existing-task updates count as existing-task outcomes, not failures.
    if outcomes or blocked: head.append(f"**{_plural(len(outcomes) + len(blocked), 'existing task outcome', 'existing task outcomes')}**")
    if deferred: head.append(f'**{len(deferred)} deferred**')
    attention = len(failures)
    head.append(f"**{attention} {'needs' if attention == 1 else 'need'} attention**")
    lines = [f'## {stream} Task Discovery', '', f"**{date.strftime('%A, %B')} {date.day}**", ' · '.join(head), '']
    for item in numbered:
        semantic = item['kind'] in {'semantic', 'selection'}
        ref = item['ref']
        lines += [f"### {ref}. {item['title']}", '']
        if semantic:
            lines.append('**Task type:** Potential existing task update')
            lines.append('**Existing task:** ' + '; '.join(t.get('title', 'Existing task') for t in item.get('targets', [])))
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
        if semantic:
            which = ' and name which existing task to add this to' if item['kind'] == 'selection' else ' to add this to the existing task'
            lines += [f'**Choice:** Reply "{ref}, update"{which}, or "{ref}, create" for a separate task.', '']
        for url in list(dict.fromkeys(item.get('source_links') or []))[:2]:
            lines.append(f'[{_link_label(url)} \u2192]({url})')
        if item.get('source_links'): lines.append('')
        # Inaccessible supporting sources are evidence limits, kept in the item record only.
        lines += ['---', '']
    if not numbered:
        # Deferred or blocked work is not "nothing new": only a complete check with
        # nothing left says no follow-ups were found.
        degraded = bool(failures or any(coverage_degraded(s) for s in coverage))
        lines += ['No new follow-ups found.' if not degraded and not outcomes and not deferred and not blocked and not already else 'No new proposals to review.', '']
    footer = []
    if already:
        groups = {}
        for a in already:
            groups.setdefault(tuple(t.get('title', 'Existing task') for t in a['targets']), []).append(a['title'])
        footer.append('**Already in your tasks:** ' + '; '.join(
            ' · '.join(titles) + ' (in ' + ', '.join(f'"{t}"' for t in key) + ')' for key, titles in groups.items()))
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
    for failure in failures:
        footer.append('**Needs attention:** ' + (str(failure['title']) + ': ' if failure.get('title') else '') + _failure_status(failure))
    for item in deferred:
        footer.append('**Deferred:** ' + (str(item['title']) + ': ' if item.get('title') else '') + str(item.get('reason') or 'Deferred to the next run')[:400])
    attested = [_source_name(s) for s in coverage if _attested_read(s)]
    if attested:
        verb = 'was' if len(set(attested)) == 1 else 'were'
        footer.append(f'**Coverage:** {_join_names(attested)} {verb} read with your own tools, so completeness is not verified.')
    for source in coverage:
        if _attested_read(source) or source.get('status') == 'complete': continue
        skipped = _skipped(source)
        if skipped: detail = ('skipped thread: ' + '; '.join(skipped))[:400]
        elif source.get('status') == 'failed' or not source.get('backlog_ids') and not source.get('pages'): detail = 'could not be read'
        else: detail = 'was only partly read'
        footer.append(f'**Coverage:** {_source_name(source)}: {detail}')
    for line in footer: lines += [line, '']
    if numbered:
        example = next((i['ref'] for i in numbered if i['kind'] == 'new'), numbered[0]['ref'])
        lines.append(f'Reply with the item numbers you want, like "{example}, create". Items stay open for seven days.')
    if not written:
        lines.append('No tasks were created or changed.')
    return '\n'.join(lines).rstrip() + '\n'


class DiscoveryDigest:
    def __init__(self, root):
        self.root = Path(root)
        self.store = DiscoveryStore(self.root)
        self.path = self.root / 'digest-ledger.json'

    def _load(self):
        return read_json(self.path, {'digests': {}, 'proposals': {}, 'numbers': {}, 'seen': {}, 'delivery': {}})

    def prepare(self, run, *, stream, day, origin, items, failures=None, coverage=None, outcomes=None, label='', review_namespace='', deferred=None, blocked=None):
        dt.date.fromisoformat(day)
        if not origin.get('session_id'):
            raise UserError('digest requires actual origin session')
        with self.store._lock('digest-ledger'):
            data = self._load()
            if run in data['digests']:
                return data['digests'][run]
            numbered = []
            key = origin['session_id'] + ':' + day
            already = []
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
                if identity in data['seen']:
                    continue
                num = data['numbers'].get(key, 0) + 1
                data['numbers'][key] = num
                pid = 'p_' + hashlib.sha256((run + ':' + identity).encode()).hexdigest()[:24]
                item = {**raw, 'proposal_id': pid, 'run_id': run, 'stream': stream, 'day': day, 'number': num,
                        'ref': label + str(num), 'origin': origin,
                        'expires': (dt.date.fromisoformat(day) + dt.timedelta(days=7)).isoformat()}
                numbered.append(item)
                data['proposals'][pid] = {'binding': item, 'state': 'pending'}
                data['seen'][identity] = pid
            failures, coverage, deferred, blocked = failures or [], coverage or [], deferred or [], blocked or []
            text = render_digest(run, stream=stream, day=day, numbered=numbered, already=already, failures=failures,
                                 coverage=coverage, outcomes=outcomes or [], deferred=deferred, blocked=blocked)
            result = {'run_id': run, 'stream': stream, 'day': day, 'prepared_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'origin': origin, 'items': numbered,
                      'failures': failures, 'deferred': deferred, 'coverage': coverage, 'outcomes': outcomes or [], 'blocked': blocked,
                      'already_current': already, 'text': text}
            result['sha256'] = hashlib.sha256(result['text'].encode()).hexdigest()
            data['digests'][run] = result
            data['delivery'][run] = {'state': 'prepared', 'digest_sha256': result['sha256'], 'origin': origin}
            atomic_json(self.path, data)
            return result

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
