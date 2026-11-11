"""Cheap research corrections: same-child fixes, parent mechanical repair, repair children."""
import copy
import json
import pytest
from alchemy_task.core import discovery_state as m
from test_discovery_schema import bundle
from test_discovery_state import prepare, read_all

THREAD = {'type': 'slack', 'workspace_id': 'T1', 'channel_id': 'C1', 'thread_root_ts': '171.1'}


def setup(tmp_path):
    store = m.DiscoveryStore(tmp_path / 'discovery')
    run = store.init_run(stream='work', business_date='2030-01-01', config={'sources': ['work'], 'mode': 'production'})
    items = store.add_candidates(run, [{'title': 'Thread ask', 'source_ids': [dict(THREAD)]}])
    store.freeze_index(run, rubric='Read complete sources.')
    return store, run, items[0]['candidate_id']


def own(cid, title='Ask'):
    b = bundle(); b['candidate_id'] = cid; b['workstreams'][0]['title'] = title
    return b


def test_invalid_commit_is_corrected_by_same_child_and_capped(tmp_path):
    store, run, cid = setup(tmp_path); a = prepare(store, run, cid); token = a['token']
    bad = own('c_' + 'f' * 20)
    first = store.spool_payload(run, token, bad)
    assert store.get_attempt(run, token)['validation_error']
    assert store.spool_payload(run, token, bad) == first  # identical resubmit is receipt only
    assert m.DiscoveryStore.corrections_left(store.get_attempt(run, token)) == 2
    good = own(cid)
    fixed = store.spool_payload(run, token, good)
    attempt = store.get_attempt(run, token)
    assert fixed['payload_sha256'] != first['payload_sha256'] and 'validation_error' not in attempt
    assert attempt['corrections'][0]['payload_sha256'] == first['payload_sha256']
    assert attempt['corrections'][0]['validation_error']
    spool = store.run_dir(run) / 'spool'
    assert (spool / f'{token}.rejected-1.json').exists() and (spool / f'{token}.rejected-1.receipt-archive.json').exists()
    assert store.resource_info(run, first['resource'] + '-rejected-1')['sha256'] == first['payload_sha256']
    assert json.loads(read_all(store, run, fixed['resource'], 'parent'))['candidate_id'] == cid
    assert store.recover_spools(run) == [fixed]
    # A valid committed payload stays immutable.
    with pytest.raises(m.UserError, match='immutable'):
        store.spool_payload(run, token, own(cid, 'Other'))
    # Cap: two corrections per attempt, then the old immutable behavior.
    store2, run2, cid2 = setup(tmp_path / 'b'); t2 = prepare(store2, run2, cid2)['token']
    for i in range(3):
        store2.spool_payload(run2, t2, own('c_' + 'f' * 20, f'Bad {i}'))
    assert m.DiscoveryStore.corrections_left(store2.get_attempt(run2, t2)) == 0
    with pytest.raises(m.UserError, match='immutable'):
        store2.spool_payload(run2, t2, own(cid2))


def test_action_fields_without_frozen_registry_are_dropped(tmp_path):
    store, run, cid = setup(tmp_path); token = prepare(store, run, cid)['token']
    b = own(cid)
    b['workstreams'][0].update(action_key='k1', action_anchor={'locator': 'message:171.2', 'outcome': 'Ship it'}, action_relation='independent')
    receipt = store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt and attempt['evidence']['helper'] == 'valid'
    assert attempt['auto_repairs'] and 'action' in attempt['auto_repairs'][0]
    stored = json.loads(read_all(store, run, receipt['resource'], 'parent'))
    assert not {'action_key', 'action_anchor', 'action_relation'} & set(stored['workstreams'][0])


def test_decomposed_thread_ids_refined_only_from_source_body(tmp_path):
    store, run, cid = setup(tmp_path)
    store.put_resource(run, 'source-body-' + cid, 'messages: ts=171.2 "send deck" ts=171.3 "book venue"')
    token = prepare(store, run, cid)['token']
    b = own(cid)
    w1 = b['workstreams'][0]; w1['exact_source_ids'] = [dict(THREAD)]
    w1['related_source_ids'] = [{**THREAD, 'message_ts': '171.2'}]
    w2 = copy.deepcopy(w1); w2['title'] = 'Book venue'; w2['related_source_ids'] = []
    w2.update(action_key='k', action_anchor={'locator': 'message:171.3', 'outcome': 'Book venue'}, action_relation='independent')
    b['workstreams'] = [w1, w2]
    receipt = store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    stored = json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']
    assert [w['exact_source_ids'][0].get('message_ts') for w in stored] == ['171.2', '171.3']
    assert stored[0]['related_source_ids'] == []
    # An id the source body does not contain is left for same-child correction.
    store2, run2, cid2 = setup(tmp_path / 'b')
    store2.put_resource(run2, 'source-body-' + cid2, 'ts=171.2 only')
    t2 = prepare(store2, run2, cid2)['token']
    b2 = json.loads(json.dumps(b)); b2['candidate_id'] = cid2
    for w in b2['workstreams']:
        w['exact_source_ids'] = [dict(THREAD)]; w['related_source_ids'] = []
        w.update(action_key='k' + w['title'], action_anchor={'locator': 'message:171.9', 'outcome': w['title']}, action_relation='independent')
    store2.spool_payload(run2, t2, b2)
    assert 'decisive message identity' in store2.get_attempt(run2, t2)['validation_error']


def test_repair_child_reads_only_previous_bundle_and_gets_targeted_instructions(tmp_path):
    from test_discovery_runner import setup_runner
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    cid = store.candidate_index(run)[0]['candidate_id']
    first = prepare(store, run, cid)
    receipt = store.spool_payload(run, first['token'], own('c_' + 'f' * 20))
    store.observe_terminal(run, first['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
    store.reject_attempt(run, first['token'], reason='research bundle must match the assigned candidate', retryable=True)
    second = store.reserve_attempt(run, cid, owner_session='parent', daily_limit=1000)
    assert second['required_resources'] == [receipt['resource']] and second['repair_of'] == first['token']
    assert 'schema' in second['available_resources']
    request = runner._bootstrap(run, second)
    data = json.loads(request['context'])
    assert data['instructions'].startswith('Your previous attempt was rejected for: research bundle must match')
    assert receipt['resource'] in data['instructions'] and 'fix only what the reason names' in data['instructions']
    assert 'schema' in data['resources'] and receipt['resource'] in data['resources']
    fresh = json.loads(runner._bootstrap(run, first)['context'])['instructions']
    assert 'You must call discovery_research_submit before finishing.' in fresh
