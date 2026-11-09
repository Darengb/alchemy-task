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
