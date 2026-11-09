"""End-to-end approval through the user's other surfaces: the dashboard HTTP routes and chat replies
from the host's real session records (native delivery thread, a new session in the same chat, another chat).
"""
import pytest

from e2e import parent as P
from e2e.outcomes import dossier_ids, frontmatter, snapshot
from e2e.test_scenarios import ITEMS, proposal_states, proposal_titles, started_host

PREFIX = '/api/plugins/alchemy-task'


def dashboard_client():
    """The plugin's real dashboard router with the host's real admission; it builds its own host context."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_cli import web_server
    from alchemy_task.dashboard import discovery_api
    app = FastAPI()
    app.include_router(discovery_api.router, prefix=PREFIX)
    return TestClient(app), {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}


def test_dashboard_http_approval_after_scheduled_run_then_chat_reply_is_idempotent(world, host_factory):
    host = started_host(host_factory)
    host.source.pages = [[host.source.item(o, t) for o, t in ITEMS[:2]]]
    day = P.run_day(host)
    titles = proposal_titles(day['digest'])
    client, owner = dashboard_client()
    assert client.get(PREFIX + '/runs').status_code == 401
    listed = client.get(PREFIX + '/runs', headers=owner).json()
    assert [r['run_id'] for r in listed['runs']] == [day['run_id']]
    detail = client.get(PREFIX + '/runs/' + day['run_id'], headers=owner).json()
    proposal = next(p for p in detail['proposals'] if p['number'] == 1)
    before = snapshot(world)
    r = client.post(PREFIX + '/proposals/' + proposal['proposal_id'] + '/approve', headers=owner,
                    json={'choice': 'create', 'due': '2026-11-20', 'area': 'work'})
    assert r.status_code == 200 and r.json()['ok'] is True, r.text
    receipt = r.json()['receipt']
    assert receipt['state'] == 'complete' and receipt['git']['state'] == 'verified'
    created = [p for p in world.task_files() if world.rel(p) not in before['local']]
    assert len(created) == 1
    content = created[0].read_text()
    fm = frontmatter(content)
    assert fm['title'] == titles[1] and str(fm['due']) == '2026-11-20' and fm['area'] == 'work'
    assert len(dossier_ids(content)) == 1 and fm['dossier_ids'] == dossier_ids(content)
    after = snapshot(world)
    assert after['commits'] == before['commits'] + 1 and after['head'] == after['remote_head'] and after['dirty'] == ''
    assert after['remote'][world.rel(created[0])] == created[0].read_bytes()
    # The chat sees the dashboard decision: the same number returns the same receipt and writes nothing.
    assert proposal_states(host, day['run_id']) == {1: 'complete', 2: 'pending'}
    again = P.approve(host, ['1'])
    assert again['ok'] and again['results'][0]['task_id'] == receipt['task_id'], again
    assert snapshot(world) == after
    # Retrying the HTTP approval returns the saved receipt and writes nothing.
    assert client.post(PREFIX + '/proposals/' + proposal['proposal_id'] + '/approve', headers=owner,
                       json={'choice': 'create', 'undated': True, 'area': 'work'}).json() == r.json()
    assert snapshot(world) == after


# ----------------------------------------------------------------- chat surfaces from real session records
ORIGIN_CHAT = '1001'


def record_sessions(world, peers):
    """Real host SessionDB rows in the synthetic profile: (session_id, chat_id, thread_id)."""
    from hermes_state import SessionDB
    db = SessionDB(db_path=world.hermes_home / 'state.db')
    try:
        for sid, chat, thread in peers:
            db.create_session(sid, source='telegram')
            db.record_gateway_session_peer(sid, source='telegram', session_key=f'telegram:{chat}:{thread}',
                                           chat_id=chat, thread_id=thread, chat_type='dm')
    finally:
        db.close()


def day_with_one_proposal(world, host_factory, peers):
    record_sessions(world, [(P.PARENT, ORIGIN_CHAT, '')] + peers)
    host = started_host(host_factory)
    host.source.pages = [[host.source.item('101', 'Draft Q1 vendor contract')]]
    day = P.run_day(host)
    assert [i['number'] for i in day['digest']['items']] == [1]
    return host, day


def test_reply_from_a_new_session_in_the_origin_chat_resolves(world, host_factory):
    host, day = day_with_one_proposal(world, host_factory, [('after-reset', ORIGIN_CHAT, '')])
    before = snapshot(world)
    out = P.approve(host, ['1'], session='after-reset')
    assert out['ok'], out
    assert len(world.task_files()) == len(before['local']) + 1
    assert proposal_states(host, day['run_id']) == {1: 'complete'}


def test_reply_from_another_chat_creates_once(world, host_factory):
    host, day = day_with_one_proposal(world, host_factory, [('other-chat', '2002', '')])
    before = snapshot(world)
    out = P.approve(host, ['1'], session='other-chat')
    assert out['ok'], out
    after = snapshot(world)
    assert len(after['local']) == len(before['local']) + 1
    out = P.approve(host, ['1'], session='other-chat', day='2026-11-03')
    assert out['ok'], out
    assert snapshot(world) == after
    assert proposal_states(host, day['run_id']) == {1: 'complete'}


def test_reply_in_native_delivery_thread_resolves_the_digest(world, host_factory, monkeypatch):
    """The native job attaches to the session; for an origin without a topic the host opens a delivery
    thread in the same chat and seeds it with the delivered digest (the host's own SessionStore and cron
    seeder). A numbered reply typed there answers the digest shown in that thread; another topic of the
    same chat cannot."""
    from host_threads import HostSessions
    host, day = day_with_one_proposal(world, host_factory, [])
    sessions = HostSessions(world.hermes_home, monkeypatch)
    try:
        sessions.deliver_into_thread(platform='telegram', origin_chat=ORIGIN_CHAT, thread_id='77',
                                     text=day['send']['final_text'], is_dm=True)
        delivery_thread = sessions.message(chat_id=ORIGIN_CHAT, chat_type='dm', thread_id='77', user_id='u1', message_id='m1')
        other_topic = sessions.message(chat_id=ORIGIN_CHAT, chat_type='dm', thread_id='78', user_id='u1', message_id='m2')
    finally:
        sessions.close()
    before = snapshot(world)
    accepted = P.approve(host, ['1'], session=other_topic)
    assert accepted['ok'], accepted
    after = snapshot(world)
    out = P.approve(host, ['1'], session=delivery_thread)
    assert out['ok'], out
    assert snapshot(world) == after
    created = [p for p in world.task_files() if world.rel(p) not in before['local']]
    assert len(created) == 1 and frontmatter(created[0].read_text())['title'] == 'Draft Q1 vendor contract'
    assert proposal_states(host, day['run_id']) == {1: 'complete'}
