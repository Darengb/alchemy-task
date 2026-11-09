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


# ---------------------------------------------------------------- helpers

def _own(store, run):
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run); ledger['origin'] = {'session_id': 'parent'}; store._save(run, ledger)


def _coverage_complete(store, run):
    store.put_resource(run, 'collection-feed', {'source_key': 'feed', 'status': 'complete'})


def build_run(data_dir, count):
    """A joined run with `count` accepted candidates, each its own decisive message."""
    store, run, items = setup(data_dir, count=count)
    wids = []
    for i, item in enumerate(items):
        a = prepare(store, run, item['candidate_id'])
        b = bundle(); b['candidate_id'] = a['candidate_id']
        w = b['workstreams'][0]
        w['exact_source_ids'][0]['message_ts'] = f'171.{i + 2}'
        w['title'] = f'Ask {i}'
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

def test_reply_in_host_opened_delivery_thread_resolves_the_digest(settings, data_dir, tmp_path):
    """Native default: the host opens a dedicated thread in the origin chat and seeds its
    session (chat=origin chat, thread=new thread, user system:cron). '1' typed there must
    create exactly one task; repeating it creates none."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _host_sessions(integration.home, {
        'parent': dict(chat_id='123', chat_type='dm', user_id='u1'),
        'cron-thread': dict(chat_id='123', chat_type='dm', thread_id='99', user_id='system:cron')})
    _one_proposal(integration, data_dir)
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id='cron-thread', today='2030-01-01')
    created = sorted(set(task_files(settings)) - set(before))
    assert len(created) == 1
    integration.decide(APPROVE_1, session_id='cron-thread', today='2030-01-01')
    assert sorted(set(task_files(settings)) - set(before)) == created


def test_reply_in_thread_keyed_on_its_own_channel_resolves_through_parent_chat(settings, data_dir, tmp_path):
    """Thread platforms that key the thread as its own chat carry the origin channel as
    parent_chat_id in the reply's origin metadata."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _host_sessions(integration.home, {
        'parent': dict(platform='discord', chat_id='555', chat_type='group', user_id='u1'),
        'cron-thread': dict(platform='discord', chat_id='777', chat_type='thread', thread_id='777',
                            parent_chat_id='555', user_id='u1')})
    _one_proposal(integration, data_dir)
    out = integration.decide({'dismiss': ['1']}, session_id='cron-thread', today='2030-01-01')
    assert len(out['dismissed']) == 1


@pytest.mark.parametrize('origin,reply', [
    # another chat's thread
    (dict(chat_id='123', chat_type='dm'), dict(chat_id='456', chat_type='dm', thread_id='99')),
    # origin has its own topic: the host never opens a new thread, so another topic is refused
    (dict(chat_id='123', chat_type='group', thread_id='7'), dict(chat_id='123', chat_type='group', thread_id='8')),
    # same chat id on a different platform
    (dict(chat_id='123', chat_type='dm'), dict(platform='discord', chat_id='123', chat_type='dm', thread_id='99')),
])
def test_threads_outside_the_digest_origin_cannot_resolve_or_create(settings, data_dir, tmp_path, origin, reply):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _host_sessions(integration.home, {'parent': dict(origin, user_id='u1'), 'elsewhere': dict(reply, user_id='u1')})
    _one_proposal(integration, data_dir)
    before = task_files(settings)
    with pytest.raises(UserError):
        integration.decide(APPROVE_1, session_id='elsewhere', today='2030-01-01')
    assert task_files(settings) == before


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
    assert '0 new proposals; 0 existing-task outcomes; 0 failures' in digest['text']
    assert 'noop' not in digest['text'] and 'Existing task' not in digest['text'] and 'degraded' not in digest['text']
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
    assert '0 new proposals; 1 existing-task outcomes; 0 failures' in text
    assert 'degraded' not in text and 'Attention' not in text and 'No new follow-ups found.' not in text
    assert 'Existing task update blocked: Workstream 1: multiple exact task matches conflict; nothing was changed' in text
    assert not digest['items'] and '**1.**' not in text and task_files(settings) == before


# ---------------------------------------------------------------- F3 inaccessible sources stay internal

def test_inaccessible_supporting_source_is_kept_in_the_record_but_not_printed(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path, [],
        sources_unavailable=['Linked planning page: access denied for this account'])
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='No task exists.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    assert '**1.** Workstream 1' in digest['text']
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
    assert 'Task type: New task' in new and 'Why unsure' not in new and 'Choice:' not in new
    # Unsure: uncertain disposition, no plausible existing task.
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path / 'u', [], disposition='uncertain',
        decisions_and_open_questions={'decisions': [], 'open_questions': ['Who owns the launch page?']})
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='Owner unclear.', session_id='parent')
    unsure = integration.finalize(run, session_id='parent')['text']
    assert 'Task type: Unsure' in unsure and 'Why unsure: Who owns the launch page?' in unsure
    # Potential existing task update: related-only nomination of a real task.
    doc = rt.store().create(title='Plan the launch page', area='work', undated=True, research=False)
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path / 's',
        [{'path': rt.store().rel(doc.path), 'match_basis': 'related_only'}])
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='Plausible overlap.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    ref = digest['items'][0]['ref']
    text = digest['text']
    assert 'Task type: Potential existing task update' in text and 'Existing task: Plan the launch page' in text
    assert f'Choice: reply "{ref}, update" to add this to the existing task, or "{ref}, create" for a separate task' in text
