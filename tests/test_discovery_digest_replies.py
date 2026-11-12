"""Outcome tests for the user-facing digest and numbered replies (Phase 4 review fixes).

Assertions read what the user sees (digest text and numbering), what a reply does
(proposal resolution, TaskNote files on disk) and what a research child actually
reads (the frozen rubric resource). Host session rows are written with the host's
own SessionSource/session-key shapes, the way the gateway and the cron delivery
seeder record them. Synthetic data only.
"""
import json
import pytest
from alchemy_task.core import taskfile as tf
from alchemy_task.core.discovery_identity import UserError
from test_discovery_integration import service, configure
from test_discovery_conversion import custom_joined
from test_discovery_schema import bundle
from test_discovery_state import setup, prepare, read_all
from test_setup import home  # noqa: F401  (fixture)


# ---------------------------------------------------------------- helpers

def _own(store, run):
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run); ledger['origin'] = {'session_id': 'parent'}; store._save(run, ledger)


def _coverage_complete(store, run):
    store.put_resource(run, 'collection-feed', {'source_key': 'feed', 'status': 'complete'})


def build_run(data_dir, count, state='', nominations=None, link=None):
    """A joined run with `count` accepted candidates, each its own decisive message."""
    store, run, items = setup(data_dir, count=count)
    wids = []
    for i, item in enumerate(items):
        a = prepare(store, run, item['candidate_id'])
        b = bundle(); b['candidate_id'] = a['candidate_id']
        w = b['workstreams'][0]
        if nominations and i in nominations:
            w['existing_task_candidates'] = nominations[i]
        w['exact_source_ids'][0]['message_ts'] = f'171.{i + 2}'
        if state: w['current_understanding'] = state
        w['title'] = f'Ask {i}'
        if link: w['source_links'] = [f'{link}/{i}']  # a distinct source: not a repeat of an earlier run
        receipt = store.spool_payload(run, a['token'], b)
        store.observe_terminal(run, a['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
        read_all(store, run, receipt['resource'], 'parent')
        store.accept_attempt(run, a['token'], payload_sha256=receipt['payload_sha256'],
                             assessment={'accepted': True, 'reason': 'Verified.'}, reader='parent')
        wids.append(store.accepted_bundle(run, a['candidate_id'])['workstream_ids'][0])
    _own(store, run); _coverage_complete(store, run)
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [i['candidate_id'] for i in items], 'failures': []})
    return store, run, items, wids


def task_files(settings):
    from pathlib import Path
    return sorted(p.name for p in Path(settings.workspace_root, 'areas').rglob('tasks/*.md'))


def _host_sessions(home, rows):
    """Record gateway session peers exactly as the host does: SessionSource -> key/origin_json."""
    from hermes_state import SessionDB
    gateway_session = pytest.importorskip('gateway.session')
    from gateway.config import Platform
    home.mkdir(parents=True, exist_ok=True)
    db = SessionDB(db_path=home / 'state.db')
    try:
        for sid, fields in rows.items():
            source = gateway_session.SessionSource(platform=Platform(fields.pop('platform', 'telegram')), **fields)
            db.create_session(sid, source=source.platform.value)
            db.record_gateway_session_peer(sid, source=source.platform.value, user_id=source.user_id,
                                           session_key=gateway_session.build_session_key(source),
                                           chat_id=source.chat_id, chat_type=source.chat_type,
                                           thread_id=source.thread_id, origin_json=json.dumps(source.to_dict()))
    finally:
        db.close()


def _one_proposal(integration, data_dir):
    store, run, items, wids = build_run(data_dir, 1)
    integration.record_decision(run, wids[0], decision='propose', reason='No task.', session_id='parent')
    return integration.finalize(run, session_id='parent')


APPROVE_1 = {'approve': ['1'], 'edits': {'1': {'area': 'work', 'undated': True}}}


# ---------------------------------------------------------------- F6 native delivery thread

# Replies in the host-opened delivery thread (Telegram, forum topics, Discord) are tested with the
# host's own SessionStore and cron seeder in test_discovery_reply_threads.py.

@pytest.mark.parametrize('origin,reply', [
    # another chat
    (dict(chat_id='123', chat_type='dm'), dict(chat_id='456', chat_type='dm')),
    # another chat's thread
    (dict(chat_id='123', chat_type='dm'), dict(chat_id='456', chat_type='dm', thread_id='99')),
    # another topic, even when the origin is itself a topic
    (dict(chat_id='123', chat_type='group', thread_id='7'), dict(chat_id='123', chat_type='group', thread_id='8')),
    # same chat id on a different platform
    (dict(chat_id='123', chat_type='dm'), dict(platform='discord', chat_id='123', chat_type='dm', thread_id='99')),
])
def test_threads_outside_the_digest_origin_can_resolve_and_create(settings, data_dir, tmp_path, origin, reply):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _host_sessions(integration.home, {'parent': dict(origin, user_id='u1'), 'elsewhere': dict(reply, user_id='u1')})
    _one_proposal(integration, data_dir)
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id='elsewhere', today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1


# ---------------------------------------------------------------- F1 true noops are omitted

def test_completed_check_with_only_true_noops_says_no_new_followups(settings, data_dir, tmp_path):
    """Source prompt: unchanged/no-new-information tasks are not reported as updates.
    A completed check with nothing new says exactly 'No new follow-ups found.'"""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path, [])
    _own(store, run); _coverage_complete(store, run)
    task = rt.store().create(title='Existing launch decision', area='work', undated=True, research=False,
                             notes='slack:T1:C1:171.1:171.2')
    before = task.path.read_bytes()
    integration.record_decision(run, wid, decision='noop', reason='Nothing new.', session_id='parent',
                                target_task_id=task.task_id, expected_revision=tf.content_hash(task.raw))
    digest = integration.finalize(run, session_id='parent')
    body = digest['text'].splitlines()
    assert 'No new follow-ups found.' in body
    assert '**0 follow-ups** · **0 need attention**' in digest['text']
    assert 'noop' not in digest['text'] and 'Existing task' not in digest['text'] and 'No new follow-ups found.' in digest['text']
    assert not digest['items'] and task.path.read_bytes() == before
    assert integration.reconcile_endstate(run)['pending_operations'] == ['digest_delivery']


# ---------------------------------------------------------------- F2 conflicts are blocked updates

def test_multiple_exact_conflict_is_an_unnumbered_blocked_update_not_a_failure(settings, data_dir, tmp_path):
    """Source prompt: multiple exact matches are an unnumbered Blocked existing-task item;
    degraded only when research failures are nonzero."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path, [])
    _own(store, run); _coverage_complete(store, run)
    for title in ('Launch decision A', 'Launch decision B'):
        rt.store().create(title=title, area='work', undated=True, research=False, confirm_new=True,
                          notes='slack:T1:C1:171.1:171.2')
    before = task_files(settings)
    integration.record_decision(run, wid, decision='conflict', reason='Two exact tasks.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    text = digest['text']
    assert '**0 follow-ups** · **1 existing task outcome** · **0 need attention**' in text
    assert 'degraded' not in text and 'Attention' not in text and 'No new follow-ups found.' not in text
    assert '**Existing task update blocked:** Workstream 1: multiple exact task matches conflict; nothing was changed' in text
    assert not digest['items'] and '### 1.' not in text and task_files(settings) == before


# ---------------------------------------------------------------- F3 inaccessible sources stay internal

def test_inaccessible_supporting_source_is_kept_in_the_record_but_not_printed(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path, [],
        sources_unavailable=['Linked planning page: access denied for this account'])
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='No task exists.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    assert '### 1. Workstream 1' in digest['text']
    assert 'access denied' not in digest['text'] and 'Unavailable' not in digest['text']
    assert digest['items'][0]['sources_unavailable'] == ['Linked planning page: access denied for this account']


# ---------------------------------------------------------------- F7 source relationship labels

def test_new_unsure_and_potential_update_items_carry_source_labels_and_choice(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    # New task: clear action, no plausible existing task.
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path, [])
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='No task exists.', session_id='parent')
    new = integration.finalize(run, session_id='parent')['text']
    assert '**Task type:** New task' in new and 'Why unsure' not in new and 'Choice:' not in new
    # Unsure: uncertain disposition, no plausible existing task.
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path / 'u', [], disposition='uncertain', source_links=['https://example.test/unsure'],
        decisions_and_open_questions={'decisions': [], 'open_questions': ['Who owns the launch page?']})
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='Owner unclear.', session_id='parent')
    unsure = integration.finalize(run, session_id='parent')['text']
    assert '**Task type:** Unsure' in unsure and '**Why unsure:** Who owns the launch page?' in unsure
    # Potential existing task update: related-only nomination of a real task.
    doc = rt.store().create(title='Plan the launch page', area='work', undated=True, research=False)
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path / 's',
        [{'path': rt.store().rel(doc.path), 'match_basis': 'related_only'}], source_links=['https://example.test/update'])
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='Plausible overlap.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    ref = digest['items'][0]['ref']
    text = digest['text']
    assert '**Task type:** Potential existing task update' in text and '**Existing task:** Plan the launch page' in text
    assert f'**Choice:** Reply "{ref}, update" to add this to the existing task, or "{ref}, create" for a separate task' in text


# ---------------------------------------------------------------- streams sharing a chat

def _finalized(integration, data_dir, *, stream, origin_session, title):
    """Finalize one proposal for `stream` the way the stream's own run would."""
    store, run, items, wids = build_run(data_dir, 1, state=f'{stream} stream view of the launch.', link=f'https://example.test/{stream}')
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run)
        ledger['origin'] = {'session_id': origin_session}
        ledger['config']['stream_name'] = stream
        store._save(run, ledger)
    integration.record_decision(run, wids[0], decision='propose', reason='No task.', session_id=origin_session)
    digest = integration.finalize(run, session_id=origin_session)
    assert digest['items'][0]['title'] == 'Ask 0'
    return digest


def _two_streams(rt, ctx, sessions):
    from alchemy_task import discovery
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    for name, sid in zip(('work', 'home'), sessions):
        discovery.create_stream(rt, {'name': name, 'areas': [name], 'sources': [{'name': 'Feed', 'scope': ['board'], 'method': 'reader'}],
                                     'user_approved': True}, sid)
    return ctx.state.get('streams')


def test_two_streams_created_in_one_chat_from_different_sessions_get_distinct_prefixes(settings, data_dir, tmp_path, monkeypatch, home):
    """Approved: letter prefixes when more than one stream delivers into the same CHAT;
    a session reset (/new) between setups must not change that."""
    from alchemy_task import discovery_integration
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    monkeypatch.setattr(discovery_integration, '_profile_home', lambda: integration.home)
    chat = dict(chat_id='123', chat_type='dm', user_id='u1')
    _host_sessions(integration.home, {'s-old': dict(chat), 's-new': dict(chat), 's-reply': dict(chat)})
    streams = _two_streams(rt, ctx, ('s-old', 's-new'))
    assert (streams['work']['label'], streams['home']['label']) == ('W', 'H')
    work = _finalized(integration, data_dir, stream='work', origin_session='s-old', title='Ask 0')
    home_digest = _finalized(integration, data_dir, stream='home', origin_session='s-new', title='Ask 0')
    assert '### W1. Ask 0' in work['text'] and '### H1. Ask 0' in home_digest['text']
    with pytest.raises(UserError, match='ambiguous'):        # bare number: ask which stream
        integration.decide({'dismiss': ['1']}, session_id='s-reply', today='2030-01-01')
    out = integration.decide({'dismiss': ['H1']}, session_id='s-reply', today='2030-01-01')
    assert out['dismissed'] == [home_digest['items'][0]['proposal_id']]
    # Separate chats keep plain numbers.
    _host_sessions(integration.home, {'s-far': dict(chat_id='456', chat_type='dm', user_id='u1')})
    from alchemy_task import discovery
    discovery.remove_stream(rt, 'home')
    discovery.create_stream(rt, {'name': 'home', 'areas': ['home'], 'sources': [{'name': 'Feed', 'scope': ['board'], 'method': 'reader'}],
                                 'user_approved': True}, 's-far')
    assert {s['label'] for s in ctx.state.get('streams').values()} == {''}


def test_same_session_streams_freeze_prefix_into_digest_and_reply(settings, data_dir, tmp_path, monkeypatch, home):
    """Two streams sharing one origin session render W1/H2; 'H2' resolves home."""
    from alchemy_task import discovery_integration
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    monkeypatch.setattr(discovery_integration, '_profile_home', lambda: integration.home)
    _two_streams(rt, ctx, ('parent', 'parent'))
    work = _finalized(integration, data_dir, stream='work', origin_session='parent', title='Ask 0')
    home_digest = _finalized(integration, data_dir, stream='home', origin_session='parent', title='Ask 0')
    assert '### W1. Ask 0' in work['text'] and '### H2. Ask 0' in home_digest['text']
    out = integration.decide({'dismiss': ['H2']}, session_id='parent', today='2030-01-01')
    assert out['dismissed'] == [home_digest['items'][0]['proposal_id']]


# ---------------------------------------------------------------- F4 removed stream

def test_removing_a_stream_keeps_bare_replies_and_run_list_working_for_the_others(settings, data_dir, tmp_path, monkeypatch, home):
    from alchemy_task import discovery, discovery_integration
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    monkeypatch.setattr(discovery_integration, '_profile_home', lambda: integration.home)
    _two_streams(rt, ctx, ('parent', 'parent'))
    work = _finalized(integration, data_dir, stream='work', origin_session='parent', title='Ask 0')
    _finalized(integration, data_dir, stream='home', origin_session='parent', title='Ask 0')
    discovery.remove_stream(rt, 'home')
    assert ctx.state.get('streams')['work']['label'] == ''
    assert len(integration.backend(session_id='parent')['runs']) == 2
    before = task_files(settings)
    result = integration.decide({'approve': ['W1'], 'edits': {'W1': {'area': 'work', 'undated': True}}},
                                session_id='parent', today='2030-01-02')
    assert result['results'][0]['state'] == 'complete'
    assert len(set(task_files(settings)) - set(before)) == 1
    assert integration.digest._load()['proposals'][work['items'][0]['proposal_id']]['state'] == 'complete'


# ---------------------------------------------------------------- M1 seven-day window

@pytest.mark.parametrize('today,ok', [('2030-01-07', True), ('2030-01-08', True), ('2030-01-09', False)])
def test_numbered_approval_is_open_through_day_seven_and_refused_after(settings, data_dir, tmp_path, today, ok):
    """Digest published 2030-01-01 is replyable through 2030-01-08; 2030-01-09 refuses with no write."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _one_proposal(integration, data_dir)
    before = task_files(settings)
    args = {**APPROVE_1, 'day': '2030-01-01'}
    if not ok:
        with pytest.raises(UserError, match='expired'):
            integration.decide(args, session_id='parent', today=today)
        assert task_files(settings) == before
        return
    result = integration.decide(args, session_id='parent', today=today)
    created = sorted(set(task_files(settings)) - set(before))
    assert len(created) == 1
    assert 'Choose the launch date.' in rt.store().resolve(result['results'][0]['task_id']).raw.decode()
    integration.decide(args, session_id='parent', today=today)
    assert sorted(set(task_files(settings)) - set(before)) == created


# ---------------------------------------------------------------- SEM-009/010 and pure-chase rubric reach children

def test_research_child_reads_the_frozen_rubric_with_handoff_authoritative_and_pure_chase_rules(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    ctx.dispatch_tool = lambda tool, args: json.dumps({'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
        'items': [{'title': 'Review issue', 'source_ids': ['source:feed:account:issue:one'], 'source_revision': 'v1'}],
        'next_cursor': None, 'pagination_exhausted': True})
    integration.collect(run, 'feed', session_id='parent')
    integration.freeze(run, session_id='parent')
    store = integration.store
    attempt = prepare(store, run, store.get_run(run)['candidates'][0]['candidate_id'])
    assert 'rubric' in attempt['required_resources']
    rubric = read_all(store, run, 'rubric', attempt['token'])
    # Pure-chase prefilter rule (source "Candidate pre-filter").
    assert "Exclude only pure chases of another explicit owner's work" in rubric
    assert "Another owner's work may be a dependency without making the user's next step a pure chase." in rubric
    # SEM-009 cross-channel handoffs and hidden links.
    assert 'follow explicit cross-channel handoffs' in rubric and 'file chips' in rubric
    assert 'open the actual linked assets' in rubric
    # SEM-010 authoritative operating systems, active versus legacy records.
    assert 'corroborate them read-only at that system' in rubric
    assert 'Never prefer a legacy record because its title matches better.' in rubric
