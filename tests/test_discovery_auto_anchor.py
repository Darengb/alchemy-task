"""Several actions in one email are accepted on the first submit: the plugin anchors them from the bundle."""
import copy
import json
from alchemy_task.core import discovery_state as m
from test_discovery_schema import bundle
from test_discovery_state import prepare, read_all

THREAD = {'type': 'gmail', 'account_slug': 'acct', 'thread_id': 't1'}
MSG = {**THREAD, 'message_id': 'm1'}


def setup(tmp_path):
    store = m.DiscoveryStore(tmp_path / 'discovery')
    run = store.init_run(stream='work', business_date='2030-01-01', config={'sources': ['work'], 'mode': 'production'})
    items = store.add_candidates(run, [{'title': 'Meeting notes', 'source_ids': [dict(THREAD)]}])
    store.freeze_index(run, rubric='Read complete sources.')
    return store, run, items[0]['candidate_id']


def shared_bundle(cid, titles, exact=MSG):
    b = bundle(); b['candidate_id'] = cid
    base = b['workstreams'][0]
    out = []
    for t in titles:
        w = copy.deepcopy(base); w['title'] = t; w['exact_source_ids'] = [dict(exact)]; w['related_source_ids'] = []
        out.append(w)
    b['workstreams'] = out
    return b


TITLES = ['Create an all-products quiz', 'Prioritize multivitamin multimedia sections', 'Improve bundle take-rates',
          'Select a probiotic pairing', 'Extract multivitamin survey results', 'Provide Clear Way video coverage']


def test_shared_message_workstreams_are_auto_anchored_and_valid_first_time(tmp_path):
    store, run, cid = setup(tmp_path); token = prepare(store, run, cid)['token']
    receipt = store.spool_payload(run, token, shared_bundle(cid, TITLES))
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    assert attempt['evidence']['helper'] == 'valid'
    assert any('auto' in r and '6' in r for r in attempt['auto_repairs'])
    registry = store._load(run)['action_registry'][cid]
    assert len(registry) == 6 and all(e['provenance'] == 'auto from research bundle' for e in registry)
    stored = json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']
    assert {w['action_anchor']['locator'] for w in stored} == {e['locator'] for e in registry}
    assert all(w['action_relation'] == 'independent' and w['action_anchor']['locator'].startswith('section:') for w in stored)
    assert stored[0]['action_anchor'] == {'locator': 'section:create-an-all-products-quiz', 'outcome': TITLES[0]}
    units = m.DiscoveryStore._validate_for_attempt(store._load(run), attempt, json.loads(read_all(store, run, receipt['resource'], 'parent')))
    assert len({u[0] for u in units}) == 6


def test_thread_level_and_mixed_ids_are_anchored_too(tmp_path):
    store, run, cid = setup(tmp_path); token = prepare(store, run, cid)['token']
    b = shared_bundle(cid, TITLES[:3], exact=THREAD)
    b['workstreams'][0]['exact_source_ids'] = [dict(MSG)]
    store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')


def test_parent_frozen_anchors_are_kept_and_missing_ones_added(tmp_path):
    store, run, cid = setup(tmp_path)
    frozen = store.freeze_action_registry(run, cid, [{'locator': 'bullet:1', 'outcome': 'Build the quiz'}])
    token = prepare(store, run, cid)['token']
    b = shared_bundle(cid, ['Quiz', 'Video coverage'])
    b['workstreams'][0].update(action_key='quiz', action_anchor={'locator': 'bullet:1', 'outcome': 'Build the quiz'}, action_relation='independent')
    receipt = store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    stored = json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']
    assert stored[0]['action_anchor'] == {'locator': 'bullet:1', 'outcome': 'Build the quiz'}
    registry = store._load(run)['action_registry'][cid]
    assert len(registry) == 2 and frozen[0] in registry
    # The parent may still re-freeze the same anchors after an automatic freeze.
    assert len(store.freeze_action_registry(run, cid, [{'locator': 'section:video-coverage', 'outcome': 'Video coverage'}])) == 2


def test_fewer_workstreams_than_registry_is_accepted_and_registry_kept(tmp_path):
    store, run, cid = setup(tmp_path)
    t1 = prepare(store, run, cid)['token']
    store.spool_payload(run, t1, shared_bundle(cid, TITLES))
    assert len(store._load(run)['action_registry'][cid]) == 6
    store2_bundle = shared_bundle(cid, TITLES[:2])
    attempt = store.get_attempt(run, t1)
    units = m.DiscoveryStore._validate_for_attempt(store._load(run), attempt, store._mechanical_repairs(run, store._load(run), attempt, store2_bundle)[0])
    assert len(units) == 2
    assert len(store._load(run)['action_registry'][cid]) == 6


def test_single_workstream_and_distinct_messages_are_unchanged(tmp_path):
    store, run, cid = setup(tmp_path); token = prepare(store, run, cid)['token']
    b = shared_bundle(cid, TITLES[:2])
    b['workstreams'][1]['exact_source_ids'] = [{**THREAD, 'message_id': 'm2'}]
    receipt = store.spool_payload(run, token, b)
    assert 'validation_error' not in store.get_attempt(run, token)
    stored = json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']
    assert not any('action_key' in w for w in stored)
    assert not store._load(run)['action_registry'].get(cid)


def test_bootstrap_treats_previous_research_as_a_starting_point(tmp_path, monkeypatch):
    from test_discovery_runner import setup_runner
    from alchemy_task.core import discovery_research as dr
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    cid = store.candidate_index(run)[0]['candidate_id']
    monkeypatch.setattr(dr, 'previous_research', lambda *a, **k: [{'run_id': 'r0', 'title': 'Quiz', 'disposition': 'propose',
                                                                   'next_action': 'x', 'subtasks': [], 'decisive_source_ids': []}])
    first = prepare(store, run, cid)
    data = json.loads(runner._bootstrap(run, first)['context'])
    text = data['instructions']
    assert data['previous-research'] and 'ADD every other' in text and 'never drop an action' in text
    assert 'same split' not in text and 'only for a genuinely new action' not in text
    assert 'anchors each action automatically' in text


def test_long_multi_topic_email_with_many_actions_is_valid_on_first_submit(tmp_path):
    """A weekly team update is one message carrying many separate actions. The old cap of 12
    made the child merge or pad actions to fit, then the parent rejected the merged unit.
    Every action now gets its own workstream and anchor on the first submit, within a clear bound."""
    from alchemy_task.core.discovery_research import MAX_WORKSTREAMS, child_schema
    assert MAX_WORKSTREAMS == 24 and child_schema()['properties']['workstreams']['maxItems'] == MAX_WORKSTREAMS
    titles = [f'Topic {i}: follow up on the weekly update section {i}' for i in range(1, 21)]
    store, run, cid = setup(tmp_path); token = prepare(store, run, cid)['token']
    receipt = store.spool_payload(run, token, shared_bundle(cid, titles))
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    assert attempt['evidence']['helper'] == 'valid' and attempt['ordinal'] == 1
    registry = store._load(run)['action_registry'][cid]
    assert len(registry) == 20
    units = m.DiscoveryStore._validate_for_attempt(store._load(run), attempt, json.loads(read_all(store, run, receipt['resource'], 'parent')))
    assert len({u[0] for u in units}) == 20


def test_over_the_action_bound_still_fails_with_a_clear_error(tmp_path):
    import pytest
    from alchemy_task.core.discovery_identity import UserError
    from alchemy_task.core.discovery_research import validate_bundle
    store, run, cid = setup(tmp_path)
    b = shared_bundle(cid, [f'Action {i}' for i in range(25)])
    with pytest.raises(UserError, match='workstream count exceeds shared limit'):
        validate_bundle(b, cid, [dict(THREAD)])
