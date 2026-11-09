"""Deterministic fake research children.

A child behaves like a read-only model child at the tool boundary: it reads
every page of every bootstrap resource through the registered
discovery_research_fetch tool (as its own child session), learns its assigned
source identity from the primary source body, then submits a payload through
discovery_research_submit. No model calls; outputs are fixed per scenario.

Behaviors (per source object id, optionally per attempt ordinal):
  'valid'      schema-valid bundle built from the item's research spec
  'invalid'    schema-invalid bundle (missing required field), lifecycle SUCCEEDED
  'fail'       lifecycle FAILED, no submission
  'no_submit'  lifecycle SUCCEEDED with no callback payload
"""
from __future__ import annotations

import copy
import json


def research_spec_default(object_id, title):
    return {'title': title, 'current_understanding': f'{title}: the request is open and unowned elsewhere.',
            'substantive_next_action': f'Do the next concrete step for {title}.',
            'new_information': [f'Verified latest state for {title}.'], 'existing_task_candidates': []}


def bundle(candidate_id, object_id, spec, account='acct'):
    return {'candidate_id': candidate_id, 'workstreams': [{
        'disposition': 'retain', 'title': spec['title'],
        'current_understanding': spec['current_understanding'],
        'substantive_next_action': spec['substantive_next_action'],
        'owner_and_collaborators': [{'name': 'Synthetic Operator', 'role': 'owner'}],
        'decisions_and_open_questions': {'decisions': [], 'open_questions': []},
        'dependencies_and_risks': [], 'implementation_context': [],
        'execution_classification': 'user_collaboration_or_approval',
        'exact_source_ids': [{'type': 'source', 'source_key': 'feed', 'account_key': account,
                              'object_kind': 'issue', 'object_id': object_id}],
        'related_source_ids': [], 'source_links': [f'https://tracker.example.test/issue/{object_id}'],
        'related_context_links': [], 'sources_consulted': [{'source': 'Synthetic tracker issue', 'result': 'complete'}],
        'sources_unavailable': [], 'existing_task_candidates': copy.deepcopy(spec.get('existing_task_candidates', [])),
        'represented_candidate_ids': [], 'new_information': list(spec['new_information']), 'errors': [],
        'research_status': 'sufficient'}]}


class Child:
    def __init__(self, host, bootstrap):
        self.host, self.bootstrap = host, bootstrap

    def _fetch_all(self, session, task_id):
        b = self.bootstrap
        bodies = {}
        for name, info in b['resources'].items():
            cursor, parts = None, []
            while True:
                args = {'run_id': b['run_id'], 'resource': name, 'revision': info['sha256'],
                        'token': b['token'], 'binding': b['binding']}
                if cursor:
                    args['cursor'] = cursor
                out = self.host.call('discovery_research_fetch', args, session=session, task_id=task_id)
                if not out.get('ok'):
                    raise AssertionError(f'child fetch refused: {out}')
                page = out['result']
                parts.append(page['content'])
                if not page['has_more']:
                    break
                cursor = page['next_cursor']
            bodies[name] = ''.join(parts)
        return bodies

    def run(self, host, bootstrap, *, session, task_id):
        bodies = self._fetch_all(session, task_id)
        primary = json.loads(bodies['source-body-' + bootstrap['candidate_id']])
        source_id = primary[-1]['source_ids'][0]
        object_id = source_id.split(':')[4]
        title = primary[-1]['title']
        plan = host.behaviors.get(object_id, 'valid')
        if isinstance(plan, dict):
            plan = plan.get(bootstrap['ordinal'], plan.get('default', 'valid'))
        host.subagent_lifecycle.records[task_id]['object_id'] = object_id
        if plan == 'fail':
            return 'FAILED'
        if plan == 'no_submit':
            return 'SUCCEEDED'
        spec = host.research_specs.get(object_id) or research_spec_default(object_id, title)
        payload = bundle(bootstrap['candidate_id'], object_id, spec, account=host.source.account)
        if plan == 'invalid':
            del payload['workstreams'][0]['substantive_next_action']
        out = host.call('discovery_research_submit', {'run_id': bootstrap['run_id'], 'token': bootstrap['token'],
                                                       'binding': bootstrap['binding'], 'payload': payload},
                        session=session, task_id=task_id)
        if not out.get('ok'):
            raise AssertionError(f'child submit refused: {out}')
        return 'SUCCEEDED'
