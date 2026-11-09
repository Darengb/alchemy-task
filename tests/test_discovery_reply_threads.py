"""Outcome tests: which chat surfaces may answer a digest (Phase 4 re-review N1-N5).

Host sessions come from the gateway's own SessionStore, and the delivery thread is opened and
seeded by cron's own seeder (session row plus the mirrored digest), the way native continuable
delivery records them. Assertions read the outcome: which proposal a reply resolves, TaskNote
files on disk, tool responses and delivery state. Synthetic data only.
"""
import json
import pytest
from alchemy_task.core.discovery_identity import UserError
from host_threads import HostSessions
from test_discovery_conversion import custom_joined
from test_discovery_digest_replies import (APPROVE_1, _coverage_complete, _host_sessions, _own, build_run,
                                           task_files)
from test_discovery_integration import service, configure
from test_setup import home  # noqa: F401  (fixture)


def _finalize(integration, data_dir, *, stream, origin_session, deliver='origin'):
    """One proposal for `stream`, finalized the way the stream's own run does it."""
    store, run, items, wids = build_run(data_dir, 1, state=f'{stream} stream view of the launch.')
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run)
        ledger['origin'] = {'session_id': origin_session, 'deliver': deliver}
        ledger['config']['stream_name'] = stream
        store._save(run, ledger)
    integration.record_decision(run, wids[0], decision='propose', reason='No task.', session_id=origin_session)
    return integration.finalize(run, session_id=origin_session)


def _bind_work(ctx, origin_session):
    streams = ctx.state.get('streams')
    streams['work']['origin_session'] = origin_session
    ctx.state.set('streams', streams)


def _create(rt, ctx, name, session_id):
    from alchemy_task import discovery
    ctx.state.set('timezone_confirmed', True)
    discovery.create_stream(rt, {'name': name, 'areas': [name], 'sources': [{'name': 'Feed', 'scope': ['board'], 'method': 'reader'}],
                                 'user_approved': True}, session_id)
    return ctx.state.get('streams')[name]


def _tools(integration, ctx):
    from alchemy_task.discovery_integration import register
    tools = {}
    ctx.register_tool = lambda **kw: tools.update({kw['name']: kw['handler']})
    ctx.register_hook = lambda *a, **kw: None
    register(ctx, integration=integration)
    return tools


SOURCE_CONFIG = {'source_key': 'feed', 'name': 'Feed', 'account_key': 'account', 'scope': ['board'], 'read_method': 'reader',
                 'relevance': {'identity_requirements': [], 'rules': 'All unresolved project issues'}}


# ---------------------------------------------------------------- N2 exact origin wins

def test_bare_number_in_a_streams_own_thread_origin_resolves_that_stream(settings, data_dir, tmp_path, monkeypatch, home):
    """Stream 'work' set up in chat 123; stream 'home' set up from inside thread 99 of chat 123.
    Different surfaces render plain numbers, so a bare '1' typed in thread 99 (home's own origin,
    where home's digests arrive) resolves home's item 1."""
    from alchemy_task import discovery_integration
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    monkeypatch.setattr(discovery_integration, '_profile_home', lambda: integration.home)
    _host_sessions(integration.home, {
        's-main': dict(chat_id='123', chat_type='dm', user_id='u1'),
        's-thread': dict(chat_id='123', chat_type='dm', thread_id='99', user_id='system:cron')})
    ctx.state.set('streams', {})
    labels = {name: _create(rt, ctx, name, sid)['label'] for name, sid in (('work', 's-main'), ('home', 's-thread'))}
    assert labels == {'work': '', 'home': ''}
    _finalize(integration, data_dir, stream='work', origin_session='s-main')
    home_digest = _finalize(integration, data_dir, stream='home', origin_session='s-thread')
    out = integration.decide({'dismiss': ['1']}, session_id='s-thread', today='2030-01-01')
    assert out['dismissed'] == [home_digest['items'][0]['proposal_id']]


def test_stream_set_up_inside_another_streams_delivery_thread_keeps_bare_replies(settings, data_dir, tmp_path, monkeypatch, home):
    """Real host: work's digest is delivered into a host-opened thread of chat 123; the user sets
    up stream 'home' while talking in that thread. A bare '1' there is home's (exact origin);
    naming the stream reaches work's item from the same thread."""
    from alchemy_task import discovery_integration
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    monkeypatch.setattr(discovery_integration, '_profile_home', lambda: integration.home)
    host = HostSessions(integration.home, monkeypatch)
    try:
        main = host.message(chat_id='123', chat_type='dm', user_id='u1')
        ctx.state.set('streams', {})
        _create(rt, ctx, 'work', main)
        work = _finalize(integration, data_dir, stream='work', origin_session=main)
        host.deliver_into_thread(platform='telegram', origin_chat='123', thread_id='99', text=work['text'], is_dm=True)
        thread = host.message(chat_id='123', chat_type='dm', thread_id='99', user_id='u1', message_id='m1')
        _create(rt, ctx, 'home', thread)
        home_digest = _finalize(integration, data_dir, stream='home', origin_session=thread)
    finally:
        host.close()
    out = integration.decide({'dismiss': ['1']}, session_id=thread, today='2030-01-01')
    assert out['dismissed'] == [home_digest['items'][0]['proposal_id']]
    out = integration.decide({'dismiss': ['1'], 'stream': 'work'}, session_id=thread, today='2030-01-01')
    assert out['dismissed'] == [work['items'][0]['proposal_id']]


# ---------------------------------------------------------------- host-opened delivery thread

def test_reply_in_the_host_opened_delivery_thread_creates_once(settings, data_dir, tmp_path, monkeypatch):
    """Native default: the host opens a dedicated thread in the origin chat (chat = origin chat,
    thread = new thread) and seeds it with the delivered digest. '1' typed there creates exactly
    one task; repeating it creates none."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        origin = host.message(chat_id='123', chat_type='dm', user_id='u1')
        _bind_work(ctx, origin)
        digest = _finalize(integration, data_dir, stream='work', origin_session=origin)
        host.deliver_into_thread(platform='telegram', origin_chat='123', thread_id='99', text=digest['text'], is_dm=True)
        reply = host.message(chat_id='123', chat_type='dm', thread_id='99', user_id='u1', message_id='m1')
    finally:
        host.close()
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    created = sorted(set(task_files(settings)) - set(before))
    assert len(created) == 1
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert sorted(set(task_files(settings)) - set(before)) == created


# ---------------------------------------------------------------- N1 Discord host-opened thread

def _discord_digest(integration, data_dir, ctx, host, deliver='origin'):
    origin = host.message('discord', chat_id='555', chat_type='group', user_id='u1', user_name='Ann')
    _bind_work(ctx, origin)
    return _finalize(integration, data_dir, stream='work', origin_session=origin, deliver=deliver)


def test_discord_reply_in_the_host_opened_delivery_thread_resolves_the_digest(settings, data_dir, tmp_path, monkeypatch):
    """Discord keys the opened thread as its own chat and the host records no parent channel.
    A number typed there by any member answers the digest the host delivered in that thread."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        digest = _discord_digest(integration, data_dir, ctx, host)
        host.deliver_into_thread(platform='discord', origin_chat='555', thread_id='777', text=digest['text'])
        reply = host.message('discord', chat_id='777', chat_type='thread', thread_id='777', user_id='u2',
                             user_name='Bee', parent_chat_id='555', message_id='m1')
    finally:
        host.close()
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    created = sorted(set(task_files(settings)) - set(before))
    assert len(created) == 1
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert sorted(set(task_files(settings)) - set(before)) == created


@pytest.mark.parametrize('case', ['thread_opened_by_a_member', 'thread_of_another_stream', 'same_text_under_another_job',
                                  'same_job_without_this_digest', 'member_thread_quoting_the_digest',
                                  'delivered_to_another_target', 'other_platform'])
def test_discord_threads_that_are_not_this_digests_delivery_thread_are_refused(settings, data_dir, tmp_path, monkeypatch, case):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        digest = _discord_digest(integration, data_dir, ctx, host,
                                 deliver='discord:556' if case == 'delivered_to_another_target' else 'origin')
        if case == 'thread_opened_by_a_member':
            # A member's own thread under the origin channel (the adapter does record the parent).
            reply = host.message('discord', chat_id='778', chat_type='thread', thread_id='778', user_id='u2',
                                 user_name='Bee', parent_chat_id='555')
        elif case == 'thread_of_another_stream':
            host.deliver_into_thread(platform='discord', origin_chat='556', thread_id='779', stream='home', job_id='job-2',
                                     text='Discovery: home (2030-01-01)\n**1.** Something else')
            reply = host.message('discord', chat_id='779', chat_type='thread', thread_id='779', user_id='u3', user_name='Cy')
        elif case == 'same_text_under_another_job':
            host.deliver_into_thread(platform='discord', origin_chat='556', thread_id='780', stream='home', job_id='job-2',
                                     text=digest['text'])
            reply = host.message('discord', chat_id='780', chat_type='thread', thread_id='780', user_id='u3', user_name='Cy')
        elif case == 'member_thread_quoting_the_digest':
            # A member's own thread whose first turn pastes the delivered digest with the host's mirror header.
            reply = host.message('discord', chat_id='782', chat_type='thread', thread_id='782', user_id='u2',
                                 user_name='Bee', parent_chat_id='555')
            host.db.append_message(reply, role='user', content=f"[Cron delivery: alchemy-task: discovery work]\n{digest['text']}")
        elif case == 'delivered_to_another_target':
            # The stream delivers to another approved channel; the host opened its thread there, not in the origin.
            host.deliver_into_thread(platform='discord', origin_chat='556', thread_id='783', text=digest['text'])
            reply = host.message('discord', chat_id='783', chat_type='thread', thread_id='783', user_id='u3', user_name='Cy')
        elif case == 'same_job_without_this_digest':
            # This stream's job delivered something that is not one of its digests (for example a failure notice).
            host.deliver_into_thread(platform='discord', origin_chat='556', thread_id='781',
                                     text='Discovery could not finish; the saved run will resume.')
            reply = host.message('discord', chat_id='781', chat_type='thread', thread_id='781', user_id='u3', user_name='Cy')
        else:
            host.deliver_into_thread(platform='telegram', origin_chat='555', thread_id='777', text=digest['text'])
            reply = host.message('telegram', chat_id='555', chat_type='group', thread_id='777', user_id='u2', user_name='Bee')
    finally:
        host.close()
    before = task_files(settings)
    with pytest.raises(UserError):
        integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert task_files(settings) == before


# ---------------------------------------------------------------- N3 forum topics

def test_forum_origin_accepts_only_the_host_opened_topic_for_replies_and_approvals(settings, data_dir, tmp_path, monkeypatch):
    """Origin: the General area of a forum group. A different member's unrelated topic cannot
    approve a proposal or a source configuration; the topic the host opened for the digest can."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        origin = host.message(chat_id='-1001', chat_type='group', user_id='u1', user_name='Ann')
        _bind_work(ctx, origin)
        digest = _finalize(integration, data_dir, stream='work', origin_session=origin)
        other_topic = host.message(chat_id='-1001', chat_type='group', thread_id='555', user_id='u2', user_name='Bee')
        host.deliver_into_thread(platform='telegram', origin_chat='-1001', thread_id='42', text=digest['text'])
        delivery_topic = host.message(chat_id='-1001', chat_type='group', thread_id='42', user_id='u2', user_name='Bee')
    finally:
        host.close()
    tools = _tools(integration, ctx)
    before = task_files(settings)
    with pytest.raises(UserError):
        integration.decide(APPROVE_1, session_id=other_topic, today='2030-01-01')
    assert task_files(settings) == before
    refused = json.loads(tools['discovery_config']({'action': 'source', 'stream': 'work', 'config': SOURCE_CONFIG,
                                                    'user_approved': True}, session_id=other_topic))
    assert refused['ok'] is False and 'origin' in refused['error']
    assert not ctx.state.get('discovery_sources')
    integration.decide(APPROVE_1, session_id=delivery_topic, today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1
    accepted = json.loads(tools['discovery_config']({'action': 'source', 'stream': 'work', 'config': SOURCE_CONFIG,
                                                     'user_approved': True}, session_id=delivery_topic))
    assert accepted['ok'] is True and ctx.state.get('discovery_sources')['work']['feed']['approved'] is True


def test_reply_from_an_unrelated_thread_says_where_to_reply(settings, data_dir, tmp_path, monkeypatch):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        _discord_digest(integration, data_dir, ctx, host)
        reply = host.message('discord', chat_id='778', chat_type='thread', thread_id='778', user_id='u2',
                             user_name='Bee', parent_chat_id='555')
    finally:
        host.close()
    with pytest.raises(UserError, match='reply in the origin chat'):
        integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')


# ---------------------------------------------------------------- N4 removed verified-sender stream

def test_removed_verified_sender_stream_keeps_its_runs_real_delivery_state(settings, data_dir, tmp_path):
    from alchemy_task import discovery
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.dispatch_tool = lambda name, args: {'id': 'existing', 'chat': 'synthetic-chat', 'text': 'Existing message'}
    integration.configure_delivery('work', {'origin_session': 'parent', 'target': 'synthetic-chat',
        'scheduled_approved': True, 'toolsets': ['approved-messaging'], 'verification_message_id': 'existing', 'verification_text': 'Existing message',
        'send_tool': 'approved_sender', 'read_tool': 'approved_message_reader',
        'send_arguments': {}, 'send_fields': {'chat': 'target', 'text': 'text'}, 'send_id_path': 'message.id',
        'read_arguments': {}, 'read_fields': {'chat': 'target', 'id': 'message_id'},
        'read_response': {'message_id': 'id', 'target': 'chat', 'text': 'text'}}, user_approved=True)
    sent = _finalize(integration, data_dir, stream='work', origin_session='parent')
    unsent = _finalize(integration, data_dir, stream='work', origin_session='parent')
    ctx.dispatch_tool = lambda name, args: ({'message': {'id': 'sent-1'}} if name == 'approved_sender'
                                            else {'id': 'sent-1', 'chat': 'synthetic-chat', 'text': sent['text']})
    assert integration.deliver(sent['run_id'], session_id='parent')['state'] == 'delivered'
    discovery.remove_stream(rt, 'work')
    delivered = integration.delivery_status(sent['run_id'])
    assert delivered['state'] == 'delivered' and delivered['message_id'] == 'sent-1'
    assert 'final_text' not in delivered and delivered.get('delivered') is not False
    prepared = integration.delivery_status(unsent['run_id'])
    assert prepared['state'] == 'prepared' and 'instruction' not in prepared and prepared.get('delivery_owner') != 'native_origin'


# ---------------------------------------------------------------- N5 digest wording gaps

def test_blocked_conflict_line_names_the_conflicting_tasks(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path, [])
    _own(store, run); _coverage_complete(store, run)
    for title in ('Launch decision A', 'Launch decision B'):
        rt.store().create(title=title, area='work', undated=True, research=False, confirm_new=True,
                          notes='slack:T1:C1:171.1:171.2')
    integration.record_decision(run, wid, decision='conflict', reason='Two exact tasks.', session_id='parent')
    line = next(l for l in integration.finalize(run, session_id='parent')['text'].splitlines() if l.startswith('Existing task update blocked'))
    assert 'Launch decision A' in line and 'Launch decision B' in line


def test_selection_among_several_existing_tasks_asks_which_task_to_update(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    docs = [rt.store().create(title=t, area='work', undated=True, research=False, confirm_new=True)
            for t in ('Plan the launch page', 'Plan the launch email')]
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path,
        [{'path': rt.store().rel(d.path), 'match_basis': 'related_only'} for d in docs])
    _own(store, run); _coverage_complete(store, run)
    integration.record_decision(run, wid, decision='propose', reason='Two plausible tasks.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    ref = digest['items'][0]['ref']
    assert f'Choice: reply "{ref}, update" and name which existing task to add this to the existing task' in digest['text']
    existing = next(l for l in digest['text'].splitlines() if l.startswith('Existing task: '))
    assert 'Plan the launch page' in existing and 'Plan the launch email' in existing
