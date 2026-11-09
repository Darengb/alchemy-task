"""Immutable discovery digests and origin-scoped, seven-day proposal bindings.

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

    def prepare(self, run, *, stream, day, origin, items, failures=None, coverage=None, outcomes=None, label='', review_namespace=''):
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
            failures, coverage = failures or [], coverage or []
            lines = [f'Discovery: {stream} ({day})']
            degraded = bool(failures or any(s.get('status') != 'complete' for s in coverage))
            lines.append(f"{dt.date.fromisoformat(day).strftime('%A')}: {len(numbered)} new proposals; {len(outcomes or [])} existing-task outcomes; {len(failures)} failures" + ('; degraded' if degraded else ''))
            lines.append('Review: ' + hashlib.sha256(run.encode()).hexdigest()[:12])
            for item in numbered:
                qualifier = ' [update or create]' if item['kind'] in {'semantic', 'selection'} else ''
                lines.append(f"**{item['ref']}.** {item['title']}{qualifier}")
                if item.get('current_understanding'): lines.append('Current state: ' + item['current_understanding'])
                if item.get('substantive_next_action'): lines.append('Next action: ' + item['substantive_next_action'])
                if item['kind'] in {'semantic', 'selection'}:
                    lines.append('Potential overlap: ' + '; '.join(t.get('title', 'Existing task') for t in item.get('targets', [])))
                if item.get('new_information'): lines.append('Addition: ' + '; '.join(item['new_information']))
                if item.get('research_disposition') == 'uncertain': lines.append('Uncertain: ' + '; '.join(item.get('uncertainty') or ['See verified open questions; user judgment required']))
                if item.get('source_links'): lines.append('Sources: ' + ' '.join(item['source_links']))
                if item.get('sources_unavailable'): lines.append('Unavailable context: ' + '; '.join(item['sources_unavailable']))
                lines.append('---')
            if not numbered:
                lines.append('No new follow-ups found.' if not degraded and not outcomes else 'No new proposals to review.')
            for outcome in outcomes or []:
                line = f"Existing task: {outcome['title']}: {outcome['status']}"
                for surface in ('git', 'phone'):
                    detail = outcome.get(surface) or {}
                    if detail: line += f"; {surface}={detail.get('state', 'unknown')}"
                if outcome.get('resume_action'): line += '; resume with discovery_conversion_recover for this saved run/unit'
                lines.append(line)
            for failure in failures:
                lines.append('Attention: ' + (str(failure['title']) + ': ' if failure.get('title') else '') + _failure_status(failure))
            for source in coverage:
                lines.append('Coverage: ' + str(source.get('source_key', source.get('source', 'source'))) + ': ' + str(source.get('status', 'unknown')) + (': source read unavailable; inspect saved review diagnostics' if source.get('error') else ''))
            if numbered:
                lines.append('Reply with the numbers you want. Other items remain replyable for seven days.')
            result = {'run_id': run, 'stream': stream, 'day': day, 'origin': origin, 'items': numbered,
                      'failures': failures, 'coverage': coverage, 'outcomes': outcomes or [], 'text': '\n'.join(lines)}
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

    def resolve(self, ref, *, session_id, today, day='', stream=''):
        date = dt.date.fromisoformat(today)
        if day == 'yesterday': day = (date - dt.timedelta(days=1)).isoformat()
        data = self._load()
        hits = [x['binding'] for x in data['proposals'].values()
                if x['binding']['origin']['session_id'] == session_id
                and (x['binding']['ref'] == str(ref) or str(x['binding']['number']) == str(ref) or x['binding']['proposal_id'] == ref)
                and (not stream or x['binding']['stream'] == stream)
                and (not day or x['binding']['day'] == day)]
        if not day and not str(ref).startswith('p_'):
            days = [x['binding']['day'] for x in data['proposals'].values()
                    if x['binding']['origin']['session_id'] == session_id and (not stream or x['binding']['stream'] == stream)]
            target_day = today if today in days else max(days, default=today)
            hits = [x for x in hits if x['day'] == target_day]
        if len(hits) != 1:
            raise UserError('proposal reply is missing or ambiguous; specify stream and exact day/proposal_id')
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
