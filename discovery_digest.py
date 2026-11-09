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


def _failure_status(failure):
    # Project operational diagnostics only; semantic/user context remains useful.
    reason = str(failure.get('reason') or 'Research needs attention')
    if re.search(r'(?:Error:|Exception:|Traceback|fatal:|areas/[^\s]+/tasks/|(?:^|\s)/[^\s]+|[a-f0-9]{8}-[a-f0-9-]{27,})', reason):
        return 'Operation unavailable; inspect saved review diagnostics and retry the saved operation'
    return reason[:400]


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
            for raw in items:
                if raw['kind'] not in {'new', 'semantic', 'selection'}:
                    raise UserError('only new or update proposals are numbered')
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
            lines = [f'Task Discovery: {stream} ({day})']
            degraded = bool(failures or any(s.get('status') != 'complete' for s in coverage))
            # Cap deferrals are a separate count: neither failures nor degraded.
            # Blocked existing-task updates count as existing-task outcomes, not failures.
            lines.append(f"{dt.date.fromisoformat(day).strftime('%A')}: {len(numbered)} new proposals; {len(outcomes or []) + len(blocked)} existing-task outcomes; {len(failures)} failures"
                         + (f'; {len(deferred)} deferred' if deferred else '') + ('; degraded' if degraded else ''))
            lines.append('Review: ' + hashlib.sha256(run.encode()).hexdigest()[:12])
            for item in numbered:
                semantic = item['kind'] in {'semantic', 'selection'}
                lines.append(f"**{item['ref']}.** {item['title']}")
                # Source task relationship labels; they never change numbering or matching.
                if semantic:
                    lines.append('Task type: Potential existing task update')
                    lines.append('Existing task: ' + '; '.join(t.get('title', 'Existing task') for t in item.get('targets', [])))
                elif item.get('research_disposition') == 'uncertain':
                    lines.append('Task type: Unsure')
                else:
                    lines.append('Task type: New task')
                if item.get('research_disposition') == 'uncertain':
                    lines.append('Why unsure: ' + '; '.join(item.get('uncertainty') or ['See verified open questions; user judgment required']))
                if item.get('current_understanding'): lines.append('Current state: ' + item['current_understanding'])
                if item.get('substantive_next_action'): lines.append('Next action: ' + item['substantive_next_action'])
                if item.get('new_information'): lines.append(('Proposed addition: ' if semantic else 'Addition: ') + '; '.join(item['new_information']))
                if semantic:
                    which = ' and name which existing task' if item['kind'] == 'selection' else ''
                    lines.append(f'Choice: reply "{item["ref"]}, update"{which} to add this to the existing task, or "{item["ref"]}, create" for a separate task.')
                if item.get('source_links'): lines.append('Sources: ' + ' '.join(item['source_links']))
                # Source: inaccessible supporting sources are evidence limits, kept in the item record only.
                lines.append('---')
            if not numbered:
                # Deferred or blocked work is not "nothing new": only a complete check with
                # nothing left says no follow-ups were found.
                lines.append('No new follow-ups found.' if not degraded and not outcomes and not deferred and not blocked else 'No new proposals to review.')
            for outcome in outcomes or []:
                line = f"Existing task: {outcome['title']}: {outcome['status']}"
                for surface in ('git', 'phone'):
                    detail = outcome.get(surface) or {}
                    if detail: line += f"; {surface}={detail.get('state', 'unknown')}"
                if outcome.get('resume_action'): line += '; resume with discovery_conversion_recover for this saved run/unit'
                lines.append(line)
            for conflict in blocked:
                # Source: multiple exact matches are an unnumbered Blocked existing-task item.
                lines.append(f"Existing task update blocked: {conflict['title']}: multiple exact task matches conflict; nothing was changed"
                             + (' (' + '; '.join(t.get('title', 'Existing task') for t in conflict.get('targets', [])) + ')' if conflict.get('targets') else ''))
            for failure in failures:
                lines.append('Attention: ' + (str(failure['title']) + ': ' if failure.get('title') else '') + _failure_status(failure))
            for item in deferred:
                lines.append('Deferred: ' + (str(item['title']) + ': ' if item.get('title') else '') + str(item.get('reason') or 'Deferred to the next run')[:400])
            for source in coverage:
                skipped = list(dict.fromkeys(str(x).split(' skipped: ', 1)[1] for x in source.get('primary_partial') or [] if ' skipped: ' in str(x)))
                detail = (': skipped thread: ' + '; '.join(skipped))[:400] if skipped else ': source read unavailable; inspect saved review diagnostics' if source.get('error') else ''
                lines.append('Coverage: ' + str(source.get('source_key', source.get('source', 'source'))) + ': ' + str(source.get('status', 'unknown')) + detail)
            if numbered:
                lines.append('Reply with the numbers you want. Other items remain replyable for seven days.')
            result = {'run_id': run, 'stream': stream, 'day': day, 'prepared_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'origin': origin, 'items': numbered,
                      'failures': failures, 'deferred': deferred, 'coverage': coverage, 'outcomes': outcomes or [], 'blocked': blocked, 'text': '\n'.join(lines)}
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
