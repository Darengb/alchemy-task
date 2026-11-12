"""The parent can correct ONE frozen item's saved source; only that item is researched again."""
import json

import pytest

from alchemy_task.core.discovery_identity import UserError, candidate_id
from alchemy_task.core.discovery_state import atomic_json
from alchemy_task.discovery_runner import make_tool_handlers
from test_discovery_runner import setup_runner


def thread(i):
    return f'source:source:account:thread:t{i}'


def item(i, text, extra_ids=()):
    return {'title': f'Work {i}', 'source_ids': [thread(i), *extra_ids], 'source_revision': f'r{i}-full',
            'messages': [{'id': 'm1', 'author': 'U1', 'time': '2026-01-01T10:00:00Z', 'text': 'Can you ship the build?'},
                         {'id': 'm2', 'author': 'U2', 'time': '2026-01-01T11:00:00Z', 'text': text}]}


def frozen(tmp_path, count=3):
    runner, store, pool, run = setup_runner(tmp_path, count=count, slots=3)
    for i in range(count):
        store.put_resource(run, 'source-body-' + candidate_id([thread(i)]),
                           [{'title': f'Work {i}', 'source_ids': [thread(i)], 'messages': [{'id': 'm1', 'text': 'Can you ship the build?'}]}])
    return runner, store, pool, run


def read_all(runner, run, name, info, token, binding, sid):
    out, cursor = '', None
    while True:
        page = runner.fetch(run, name, info['sha256'], token=token, binding=binding, cursor=cursor, session_id=sid, task_id='cron-other')
        out += page['content']
        if not page['has_more']:
            return out
        cursor = page['next_cursor']


def test_correction_is_what_a_new_child_reads_and_others_are_untouched(tmp_path):
    runner, store, pool, run = frozen(tmp_path)
    c0, c1 = candidate_id([thread(0)]), candidate_id([thread(1)])
    before = store.get_run(run)['resources']
    # A settled earlier attempt does not count: the corrected item gets a fresh first attempt.
    old = store.reserve_attempt(run, c0, owner_session='parent')
    ledger = store._load(run)  # a child that finished and whose bundle the parent rejected
    ledger['attempts'][old['token']].update(state='rejected_retryable', rejection={'reason': 'thread was cut short', 'retryable': True})
    store._save(run, ledger)
    result = runner.correct_source(run, candidate_id=c0, item=item(0, 'Dev reply: fixed in build 42', extra_ids=[thread(0) + ':m2']),
                                   reason='saved thread missed two developer replies', session_id='parent')
    ledger = store.get_run(run)
    assert result['old_sha256'] == before['source-body-' + c0]['sha256'] != result['new_sha256']
    assert ledger['resources']['superseded-source-body-' + c0 + '-1']['sha256'] == result['old_sha256']
    record = ledger['source_corrections'][0]
    assert record['reason'] and record['at'] and old['token'] in record['superseded_attempts']
    assert not [a for a in ledger['attempts'].values() if a['candidate_id'] == c0]
    assert ledger['resources']['source-body-' + c1] == before['source-body-' + c1]
    runner.run(run, session_id='parent')
    boots = {}
    for sid, r in pool.records.items():  # first child per candidate
        boots.setdefault(r['bootstrap']['candidate_id'], (sid, r['bootstrap']))
    sid, boot = boots[c0]
    assert boot['ordinal'] == 1 and 'repair' not in boot
    info = boot['resources']['source-body-' + c0]
    assert info['sha256'] == result['new_sha256']
    text = read_all(runner, run, 'source-body-' + c0, info, boot['token'], boot['binding'], 'child-' + sid.split('-')[-1])
    assert 'fixed in build 42' in text
    sid1, boot1 = boots[c1]
    assert boot1['resources']['source-body-' + c1]['sha256'] == before['source-body-' + c1]['sha256']


def test_refused_for_other_thread_in_flight_second_time_and_after_acceptance(tmp_path):
    runner, store, pool, run = frozen(tmp_path)
    c0, c1, c2 = (candidate_id([thread(i)]) for i in range(3))
    with pytest.raises(UserError, match='different thread'):
        runner.correct_source(run, candidate_id=c0, item=item(1, 'x'), reason='r', session_id='parent')
    with pytest.raises(UserError, match='no primary content'):
        runner.correct_source(run, candidate_id=c0, item={'title': 'Work 0', 'source_ids': [thread(0)], 'messages': []}, reason='r', session_id='parent')
    with pytest.raises(UserError, match='does not own'):
        runner.correct_source(run, candidate_id=c0, item=item(0, 'full'), reason='r', session_id='someone-else')
    store.reserve_attempt(run, c1, owner_session='parent')
    with pytest.raises(UserError, match='in flight'):
        runner.correct_source(run, candidate_id=c1, item=item(1, 'full'), reason='r', session_id='parent')
    runner.correct_source(run, candidate_id=c0, item=item(0, 'full'), reason='r', session_id='parent')
    with pytest.raises(UserError, match='already corrected once'):
        runner.correct_source(run, candidate_id=c0, item=item(0, 'fuller'), reason='r', session_id='parent')
    atomic_json(store.run_dir(run) / 'research' / (c2 + '.bundle.json'), {'candidate_id': c2})
    with pytest.raises(UserError, match='accepted bundle'):
        runner.correct_source(run, candidate_id=c2, item=item(2, 'full'), reason='r', session_id='parent')
    assert [c['candidate_id'] for c in store.get_run(run)['source_corrections']] == [c0]


def test_tool_action_on_discovery_recover(tmp_path):
    runner, store, pool, run = frozen(tmp_path, count=1)
    c0 = candidate_id([thread(0)])
    call = make_tool_handlers(runner)['discovery_recover']
    args = {'run_id': run, 'action': 'correct_source', 'candidate_id': c0, 'item': item(0, 'full reply'), 'reason': 'missing replies'}
    refused = json.loads(call(args, session_id='someone-else'))
    assert refused['ok'] is False
    done = json.loads(call(args, session_id='parent'))
    assert done['ok'] is True and done['result']['fresh_attempt'] is True
