"""Per-source proposal caps: the parent trims by priority and lists the rest, never rejecting."""
import copy
import json
from alchemy_task.core import discovery_caps as caps
from alchemy_task.core import discovery_state as m
from test_discovery_auto_anchor import THREAD, shared_bundle
from test_discovery_state import prepare, read_all


def msg(i, author):
    return {'id': f'm{i}', 'author': author, 'time': f'2030-01-01T00:0{i % 10}:00Z', 'text': 'hello'}


# --- classification ---------------------------------------------------------

def test_single_email_or_message_is_single():
    assert caps.classify_source_item([{'messages': [msg(1, 'a@x.com')]}]) == caps.SINGLE
    # Several messages by one author are still a single item, not a back-and-forth.
    assert caps.classify_source_item([{'messages': [msg(1, 'a@x.com'), msg(2, 'A@x.com ')]}]) == caps.SINGLE
    assert caps.classify_source_item([{'title': 'no messages'}]) == caps.SINGLE
    assert caps.classify_source_item([]) == caps.SINGLE


def test_two_messages_from_two_authors_is_a_conversation():
    assert caps.classify_source_item([{'messages': [msg(1, 'a'), msg(2, 'b')]}]) == caps.CONVERSATION
    # The newest version decides.
    assert caps.classify_source_item([{'messages': [msg(1, 'a'), msg(2, 'b')]}, {'messages': [msg(3, 'a')]}]) == caps.SINGLE


def test_transcript_by_source_kind_or_item_kind():
    convo = [{'messages': [msg(1, 'a'), msg(2, 'b')]}]
    assert caps.classify_source_item(convo, 'transcript') == caps.TRANSCRIPT
    assert caps.classify_source_item([{'kind': 'meeting_notes', 'messages': [msg(1, 'a')]}]) == caps.TRANSCRIPT
    assert caps.classify_source_item([{'kind': 'thread', 'messages': [msg(1, 'a')]}], 'mail') == caps.SINGLE
    assert caps.CAPS == {'single': 7, 'conversation': 10, 'transcript': 10}


def test_also_mentioned_line_wording():
    assert caps.also_mentioned_line('single', ['A', 'B'], email=True) == 'Also in this email, not proposed: A, B'
    assert caps.also_mentioned_line('single', ['A']) == 'Also in this message, not proposed: A'
    line = caps.also_mentioned_line('conversation', list('ABCDEFG'))
    assert line == 'Also in this conversation, not proposed: A, B, C, D, E, +2 more'
    assert caps.also_mentioned_line('transcript', ['X']).startswith('Also in this transcript')
    assert caps.also_mentioned_line('single', []) == ''


# --- trimming in mechanical repair -------------------------------------------

def setup(tmp_path, messages, *, kind='mail', item_kind=None):
    store = m.DiscoveryStore(tmp_path / 'discovery')
    config = {'sources': [{'source_key': 'inbox', 'kind': kind}], 'mode': 'production'}
    run = store.init_run(stream='work', business_date='2030-01-01', config=config)
    items = store.add_candidates(run, [{'title': 'Item', 'source_ids': [dict(THREAD)]}])
    cid = items[0]['candidate_id']
    body = {'title': 'Item', 'source_ids': [dict(THREAD)], 'source_key': 'inbox', 'messages': messages}
    if item_kind: body['kind'] = item_kind
    store.put_resource(run, 'source-body-' + cid, [body])
    store.freeze_index(run, rubric='Read complete sources.')
    return store, run, cid


PRIORITY_PLAN = ['status_only', 'new_work', 'user_next_step', 'task_update', 'dated', 'new_work', 'waiting_on_user', 'status_only', 'new_work']


def test_nine_proposals_from_one_email_keep_seven_by_priority_first_submit(tmp_path):
    store, run, cid = setup(tmp_path, [msg(1, 'boss@x.com')])
    token = prepare(store, run, cid)['token']
    titles = [f'Action {i}' for i in range(9)]
    b = shared_bundle(cid, titles)
    for w, p in zip(b['workstreams'], PRIORITY_PLAN):
        w['priority'] = p
    receipt = store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    assert attempt['evidence']['helper'] == 'valid' and attempt['ordinal'] == 1 and not attempt.get('rejection')
    stored = json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']
    # Both status_only items go; the rest stay in the child's order.
    assert [w['title'] for w in stored] == ['Action 1', 'Action 2', 'Action 3', 'Action 4', 'Action 5', 'Action 6', 'Action 8']
    assert attempt['not_proposed']['titles'] == ['Action 0', 'Action 7']
    assert attempt['not_proposed']['line'] == 'Also in this email, not proposed: Action 0, Action 7'
    assert any('kept 7 of 9' in r for r in attempt['auto_repairs'])
    units = m.DiscoveryStore._validate_for_attempt(store._load(run), attempt, json.loads(read_all(store, run, receipt['resource'], 'parent')))
    assert len(units) == 7 and len(store._load(run)['action_registry'][cid]) == 7
    # Recorded for the digest once the bundle is accepted.
    ledger = store._load(run); ledger['attempts'][token]['state'] = 'accepted_bundle'; store._save(run, ledger)
    found = store.not_proposed_for(run, cid)
    assert found['parent_candidate_id'] == cid and found['titles'] == ['Action 0', 'Action 7']


def test_conversation_twelve_keeps_ten(tmp_path):
    store, run, cid = setup(tmp_path, [msg(1, 'a'), msg(2, 'b')], kind='generic')
    token = prepare(store, run, cid)['token']
    receipt = store.spool_payload(run, token, shared_bundle(cid, [f'Step {i}' for i in range(12)]))
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    assert len(json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']) == 10
    # Without priorities the child's own order decides.
    assert attempt['not_proposed']['titles'] == ['Step 10', 'Step 11']
    assert attempt['not_proposed']['line'].startswith('Also in this conversation, not proposed:')


def test_transcript_source_kind_gets_ten(tmp_path):
    store, run, cid = setup(tmp_path, [msg(1, 'notes@x.com')], kind='transcript')
    token = prepare(store, run, cid)['token']
    store.spool_payload(run, token, shared_bundle(cid, [f'Item {i}' for i in range(11)]))
    attempt = store.get_attempt(run, token)
    assert attempt['not_proposed']['item_type'] == 'transcript' and attempt['not_proposed']['titles'] == ['Item 10']


def test_noops_do_not_count_toward_the_cap(tmp_path):
    store, run, cid = setup(tmp_path, [msg(1, 'a')])
    token = prepare(store, run, cid)['token']
    b = shared_bundle(cid, [f'Action {i}' for i in range(10)])
    for w in b['workstreams'][:3]:
        w['existing_task_already_current'] = True
    receipt = store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    assert len(json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']) == 10
    assert 'not_proposed' not in attempt


def test_old_payload_without_priority_and_under_cap_is_unchanged(tmp_path):
    store, run, cid = setup(tmp_path, [msg(1, 'a')])
    token = prepare(store, run, cid)['token']
    b = shared_bundle(cid, [f'Action {i}' for i in range(7)])
    assert not any('priority' in w for w in b['workstreams'])
    store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt and 'not_proposed' not in attempt
    assert not any('kept' in r for r in attempt['auto_repairs'])


def test_over_safety_bound_is_trimmed_not_rejected(tmp_path):
    store, run, cid = setup(tmp_path, [msg(1, 'a')])
    token = prepare(store, run, cid)['token']
    b = shared_bundle(cid, [f'Action {i}' for i in range(45)])
    for w in b['workstreams'][7:]:
        w['existing_task_already_current'] = True
    receipt = store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    assert len(json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']) == caps.SAFETY_BOUND


def test_invalid_priority_value_is_a_validation_error_not_a_crash(tmp_path):
    store, run, cid = setup(tmp_path, [msg(1, 'a')])
    token = prepare(store, run, cid)['token']
    b = shared_bundle(cid, ['One'])
    b['workstreams'][0]['priority'] = 'urgent'
    store.spool_payload(run, token, b)
    assert 'validation_error' in store.get_attempt(run, token)


# --- digest line -------------------------------------------------------------

def test_digest_shows_also_mentioned_line_once_under_first_proposal(tmp_path):
    from alchemy_task.discovery_digest import DiscoveryDigest
    digest = DiscoveryDigest(tmp_path)
    extra = {'parent_candidate_id': 'c_1', 'item_type': 'single', 'email': True, 'titles': ['Order labels', 'Book room'],
             'line': 'Also in this email, not proposed: Order labels, Book room'}
    items = [{'unit_id': f'w_{i}', 'research_revision': f'r{i}', 'title': f'Ask {i}', 'kind': 'new', 'targets': [],
              'not_proposed': copy.deepcopy(extra)} for i in range(2)]
    d = digest.prepare('run1', stream='work', day='2030-01-01', origin={'session_id': 'chat'}, items=items)
    assert d['text'].count('Also in this email, not proposed: Order labels, Book room') == 1
    assert d['text'].index('Also in this email') < d['text'].index('### 2. Ask 1')
    assert d['items'][0]['not_proposed_line'] and 'not_proposed_line' not in d['items'][1]
    stored = digest._load()['proposals'][d['items'][0]['proposal_id']]['binding']
    assert stored['not_proposed_line'].startswith('Also in this email')


def test_bootstrap_asks_for_ranked_workstreams(tmp_path):
    from test_discovery_runner import setup_runner
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    cid = store.candidate_index(run)[0]['candidate_id']
    text = json.loads(runner._bootstrap(run, prepare(store, run, cid))['context'])['instructions']
    assert 'most important first' in text and 'user_next_step' in text and 'status_only' in text
    assert 'Plain status or FYI items are usually omitted' in text
