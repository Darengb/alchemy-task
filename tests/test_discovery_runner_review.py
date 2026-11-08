"""Ordinary-flow regressions from independent runner review."""
import hashlib
import json
import pytest
from test_discovery_runner import setup_runner
from test_discovery_schema import bundle
from alchemy_task.discovery_runner import BINDING_KEYS, CHECKLIST
from alchemy_task.discovery_sources import SourceAdapter
from alchemy_task.core.discovery_identity import UserError


def bound(runner, store, run, cid):
    a = store.reserve_attempt(run, cid, owner_session='parent', daily_limit=1000)
    store.record_start(run, parent_session='parent', child_session='child', subagent_id='sa-probe')
    store.bind_attempt(run, a['token'], {'subagent_id': 'sa-probe'}, owner_session='parent')
    binding = {k: a[k] for k in BINDING_KEYS}
    for name in a['required_resources']:
        info = store.resource_info(run, name); cursor = None
        while True:
            page = runner.fetch(run, name, info['sha256'], token=a['token'], binding=binding, cursor=cursor, session_id='child')
            if not page['has_more']: break
            cursor = page['next_cursor']
    return a, binding


def payload(cid):
    b = bundle(); b['candidate_id'] = cid
    b['workstreams'][0]['exact_source_ids'] = [{'type': 'source', 'source_key': 'source', 'account_key': 'account', 'object_kind': 'thread', 'object_id': 't0'}]
    return b


def test_multipart_intermediate_continue_then_commit_stop(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    cid = store.get_run(run)['candidates'][0]['candidate_id']
    a, binding = bound(runner, store, run, cid)
    raw = json.dumps(payload(cid)); sha = hashlib.sha256(raw.encode()).hexdigest()
    start = runner.submit(run, a['token'], binding, upload={'action': 'begin', 'total_bytes': len(raw.encode()), 'sha256': sha, 'part_count': 1}, session_id='child')
    assert 'Continue' in start['instruction'] and 'Stop.' not in start['instruction']
    part = runner.submit(run, a['token'], binding, upload={'action': 'part', 'index': 0, 'content': raw}, session_id='child')
    assert 'Continue' in part['instruction'] and not store.get_attempt(run, a['token'])['payload']
    committed = runner.submit(run, a['token'], binding, upload={'action': 'commit'}, session_id='child')
    assert 'Stop.' in committed['instruction']
    assert committed['receipt']['transport_sha256'] == sha


def test_valid_representation_across_200_201_is_accepted(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=201)
    items = store.get_run(run)['candidates']
    a, binding = bound(runner, store, run, items[0]['candidate_id'])
    b = payload(a['candidate_id'])
    b['workstreams'][0]['represented_candidate_ids'] = [items[200]['candidate_id']]
    submitted = runner.submit(run, a['token'], binding, payload=b, session_id='child')
    assert not submitted['validation_error']
    store.observe_terminal(run, a['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
    info = submitted['receipt']; cursor = None
    while True:
        page = runner.fetch(run, info['resource'], info['payload_sha256'], cursor=cursor, session_id='parent')
        if not page['has_more']: break
        cursor = page['next_cursor']
    runner.accept(run, a['token'], info['payload_sha256'], {'accepted': True, 'reason': 'Full primary and canonical scope inspected.', 'checklist': {k: 'Reviewed full source evidence.' for k in CHECKLIST}}, session_id='parent')
    assert store.accepted_bundle(run, a['candidate_id'])


def test_name_independent_rule_does_not_require_identity(tmp_path):
    _, store, _, _ = setup_runner(tmp_path, count=0)
    config = {'source_key': 'feed', 'account_key': 'account', 'scope': ['board'], 'read_method': 'approved_reader',
              'relevance': {'identity_requirements': [], 'rules': 'Unresolved tagged issues regardless of owner'}}
    def read(c, start, end, cursor):
        return {'account_key': 'account', 'scope': c['scope'], 'start': start, 'end': end, 'items': [], 'next_cursor': None, 'pagination_exhausted': True}
    result = SourceAdapter(store, config, read_page=read).collect('stream', start='2030-01-01T00:00:00Z', end='2030-01-02T00:00:00Z')
    assert result['status'] == 'complete'
    config['relevance']['identity_requirements'] = ['name']
    with pytest.raises(UserError, match='identity'):
        SourceAdapter(store, config, read_page=read)
