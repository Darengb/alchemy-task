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


import itertools
_RUNS = itertools.count()


def _finalize(integration, data_dir, *, stream, origin_session, deliver='origin', day=None):
    """One proposal for `stream`, finalized the way the stream's own run does it."""
    # Each run reads its own distinct source: a shared source would correctly be a repeat, not a new proposal.
    link = f'https://example.test/{stream}/{day or "today"}/{next(_RUNS)}'
    store, run, items, wids = build_run(data_dir, 1, state=f'{stream} stream view of the launch{" on " + day if day else ""}.', link=link)
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run)
        ledger['origin'] = {'session_id': origin_session, 'deliver': deliver}
        ledger['config']['stream_name'] = stream
        if day: ledger['business_date'] = day
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


# ---------------------------------------------------------------- conversation context wins, not origin location

def test_origin_location_alone_does_not_choose_between_two_streams(settings, data_dir, tmp_path, monkeypatch, home):
    """Without a digest in the transcript, two recent streams require a stream name."""
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
    with pytest.raises(UserError, match='which stream'):
        integration.decide({'dismiss': ['1']}, session_id='s-thread', today='2030-01-01')
    out = integration.decide({'dismiss': ['1'], 'stream': 'home'}, session_id='s-thread', today='2030-01-01')
    assert out['dismissed'] == [home_digest['items'][0]['proposal_id']]


def test_stream_set_up_inside_another_streams_delivery_thread_keeps_bare_replies(settings, data_dir, tmp_path, monkeypatch, home):
    """The mirrored work digest controls bare replies even if home was configured here later.
    Naming home explicitly reaches its newest digest from the same thread."""
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
    assert out['dismissed'] == [work['items'][0]['proposal_id']]
    out = integration.decide({'dismiss': ['1'], 'stream': 'home'}, session_id=thread, today='2030-01-01')
    assert out['dismissed'] == [home_digest['items'][0]['proposal_id']]


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

# The origin channel as the Discord adapter records it; a job created there captures the same
# chat name and guild, and the host seeder records them on every thread it opens for that job.
DISCORD_JOB_ORIGIN = {'chat_name': 'Guild / #general', 'scope_id': 'g1'}


def _discord_digest(integration, data_dir, ctx, host, deliver='origin'):
    origin = host.message('discord', chat_id='555', chat_type='group', user_id='u1', user_name='Ann',
                          chat_name=DISCORD_JOB_ORIGIN['chat_name'], guild_id=DISCORD_JOB_ORIGIN['scope_id'])
    _bind_work(ctx, origin)
    return _finalize(integration, data_dir, stream='work', origin_session=origin, deliver=deliver)


def test_discord_reply_in_the_host_opened_delivery_thread_resolves_the_digest(settings, data_dir, tmp_path, monkeypatch):
    """Discord keys the opened thread as its own chat and the host records no parent channel.
    A number typed there by any member answers the digest the host delivered in that thread."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        digest = _discord_digest(integration, data_dir, ctx, host)
        host.deliver_into_thread(platform='discord', origin_chat='555', thread_id='777', text=digest['text'], **DISCORD_JOB_ORIGIN)
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
def test_discord_reply_has_no_location_job_or_platform_filter(settings, data_dir, tmp_path, monkeypatch, case):
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
                                     text='Discovery: home (2030-01-01)\n**1.** Something else', **DISCORD_JOB_ORIGIN)
            reply = host.message('discord', chat_id='779', chat_type='thread', thread_id='779', user_id='u3', user_name='Cy')
        elif case == 'same_text_under_another_job':
            host.deliver_into_thread(platform='discord', origin_chat='556', thread_id='780', stream='home', job_id='job-2',
                                     text=digest['text'], **DISCORD_JOB_ORIGIN)
            reply = host.message('discord', chat_id='780', chat_type='thread', thread_id='780', user_id='u3', user_name='Cy')
        elif case == 'member_thread_quoting_the_digest':
            # A member's own thread whose first turn pastes the delivered digest with the host's mirror header.
            reply = host.message('discord', chat_id='782', chat_type='thread', thread_id='782', user_id='u2',
                                 user_name='Bee', parent_chat_id='555')
            host.db.append_message(reply, role='user', content=f"[Cron delivery: alchemy-task: discovery work]\n{digest['text']}")
        elif case == 'delivered_to_another_target':
            # The stream delivers to another approved channel; the host opened its thread there, not in the origin.
            host.deliver_into_thread(platform='discord', origin_chat='556', thread_id='783', text=digest['text'], **DISCORD_JOB_ORIGIN)
            reply = host.message('discord', chat_id='783', chat_type='thread', thread_id='783', user_id='u3', user_name='Cy')
        elif case == 'same_job_without_this_digest':
            # This stream's job delivered something that is not one of its digests (for example a failure notice).
            host.deliver_into_thread(platform='discord', origin_chat='556', thread_id='781',
                                     text='Discovery could not finish; the saved run will resume.', **DISCORD_JOB_ORIGIN)
            reply = host.message('discord', chat_id='781', chat_type='thread', thread_id='781', user_id='u3', user_name='Cy')
        else:
            host.deliver_into_thread(platform='telegram', origin_chat='555', thread_id='777', text=digest['text'])
            reply = host.message('telegram', chat_id='555', chat_type='group', thread_id='777', user_id='u2', user_name='Bee')
    finally:
        host.close()
    before = task_files(settings)
    result = integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert result['results'][0]['state'] == 'complete'
    assert len(set(task_files(settings)) - set(before)) == 1


# ---------------------------------------------------------------- R2-1 a delivery thread answers its own digest

THREAD_SURFACES = {
    # platform: origin chat fields, and the reply fields inside the thread the host opened for a digest
    'telegram': (dict(chat_id='-1001', chat_type='group'),
                 lambda t: dict(chat_id='-1001', chat_type='group', thread_id=t), {}),
    'slack': (dict(chat_id='C1', chat_type='group'),
              lambda t: dict(chat_id='C1', chat_type='group', thread_id=t), {}),
    'discord': (dict(chat_id='555', chat_type='group', chat_name=DISCORD_JOB_ORIGIN['chat_name'], guild_id='g1'),
                lambda t: dict(chat_id=t, chat_type='thread', thread_id=t, parent_chat_id='555', guild_id='g1'),
                DISCORD_JOB_ORIGIN),
}


@pytest.mark.parametrize('platform', sorted(THREAD_SURFACES))
def test_bare_number_in_an_older_digests_delivery_thread_resolves_that_digest(settings, data_dir, tmp_path, monkeypatch, platform):
    """adaptation-plan.md:188: Monday's digest arrived in thread 41 and Tuesday's in thread 42 of
    the same origin. On Tuesday, '1' typed in thread 41 answers Monday's item 1 (the list in front
    of the user), never Tuesday's. An explicit day or proposal id still reaches other lists, and a
    bare number in the origin chat itself still means the newest list."""
    origin_fields, thread_fields, job_origin = THREAD_SURFACES[platform]
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        origin = host.message(platform, user_id='u1', user_name='Ann', **origin_fields)
        _bind_work(ctx, origin)
        mon = _finalize(integration, data_dir, stream='work', origin_session=origin, day='2030-01-01')
        host.deliver_into_thread(platform=platform, origin_chat=origin_fields['chat_id'], thread_id='41', text=mon['text'], **job_origin)
        tue = _finalize(integration, data_dir, stream='work', origin_session=origin, day='2030-01-02')
        host.deliver_into_thread(platform=platform, origin_chat=origin_fields['chat_id'], thread_id='42', text=tue['text'], **job_origin)
        monday_thread = host.message(platform, user_id='u2', user_name='Bee', **thread_fields('41'))
        tuesday_thread = host.message(platform, user_id='u2', user_name='Bee', **thread_fields('42'))
    finally:
        host.close()
    monday_item, tuesday_item = mon['items'][0]['proposal_id'], tue['items'][0]['proposal_id']
    assert monday_item != tuesday_item and mon['items'][0]['ref'] == tue['items'][0]['ref'] == '1'
    today = '2030-01-02'
    assert integration.decide({'dismiss': ['1']}, session_id=monday_thread, today=today)['dismissed'] == [monday_item]
    assert integration.digest._load()['proposals'][tuesday_item]['state'] == 'pending'
    assert integration.decide({'dismiss': ['1']}, session_id=origin, today=today)['dismissed'] == [tuesday_item]
    assert integration.decide({'dismiss': ['1'], 'day': '2030-01-01'}, session_id=tuesday_thread, today=today)['dismissed'] == [monday_item]
    assert integration.decide({'dismiss': [monday_item]}, session_id=tuesday_thread, today=today)['dismissed'] == [monday_item]
    assert integration.decide({'dismiss': ['1']}, session_id=tuesday_thread, today=today)['dismissed'] == [tuesday_item]


def test_delivery_thread_still_answers_after_conversation_turns(settings, data_dir, tmp_path, monkeypatch):
    """Later conversation without another digest still resolves the mirrored digest."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        origin = host.message(chat_id='-1001', chat_type='group', user_id='u1', user_name='Ann')
        _bind_work(ctx, origin)
        digest = _finalize(integration, data_dir, stream='work', origin_session=origin)
        host.deliver_into_thread(platform='telegram', origin_chat='-1001', thread_id='42', text=digest['text'])
        reply = host.message(chat_id='-1001', chat_type='group', thread_id='42', user_id='u2', user_name='Bee')
        host.db.append_message(reply, role='user', content='[Bee] what is item 1 about?')
        host.db.append_message(reply, role='assistant', content='It is about the launch.')
        host.db.append_message(reply, role='user', content='[Bee] approve 1')
    finally:
        host.close()
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1


# ---------------------------------------------------------------- R2-2 the delivery thread belongs to the origin

def test_digest_delivered_into_another_chat_is_replyable(settings, data_dir, tmp_path, monkeypatch):
    """A digest mirrored in a different Telegram chat is still replyable."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        origin = host.message(chat_id='-1001', chat_type='group', user_id='u1', user_name='Ann', chat_name='Team')
        _bind_work(ctx, origin)
        digest = _finalize(integration, data_dir, stream='work', origin_session=origin)
        host.deliver_into_thread(platform='telegram', origin_chat='-2002', thread_id='42', text=digest['text'], chat_name='Team')
        reply = host.message(chat_id='-2002', chat_type='group', thread_id='42', user_id='u9', user_name='Eve')
    finally:
        host.close()
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1


@pytest.mark.parametrize('job_origin', [{'chat_name': 'Other guild / #general', 'scope_id': 'g2'},
                                        {'chat_name': 'Guild / #random', 'scope_id': 'g1'},
                                        {'chat_name': 'general', 'scope_id': None}],
                         ids=['another_guild', 'another_channel_same_guild', 'job_origin_not_the_origin_channel'])
def test_discord_job_channel_name_and_scope_do_not_filter_replies(settings, data_dir, tmp_path, monkeypatch, job_origin):
    """Discord job headers, channel names and scope IDs do not authorize or filter replies."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        digest = _discord_digest(integration, data_dir, ctx, host)
        host.deliver_into_thread(platform='discord', origin_chat='999', thread_id='900', text=digest['text'], job_id='job-9', **job_origin)
        reply = host.message('discord', chat_id='900', chat_type='thread', thread_id='900', user_id='evil', user_name='Eve',
                             parent_chat_id='999', guild_id=job_origin['scope_id'])
    finally:
        host.close()
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1


# ---------------------------------------------------------------- N3 forum topics

def test_any_forum_topic_accepts_replies_and_confirmed_config(settings, data_dir, tmp_path, monkeypatch):
    """Any forum topic may approve the only recent digest and confirmed source configuration."""
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
    integration.decide(APPROVE_1, session_id=other_topic, today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1
    configured = json.loads(tools['discovery_config']({'action': 'source', 'stream': 'work', 'config': SOURCE_CONFIG,
                                                    'user_approved': True}, session_id=other_topic))
    assert configured['ok'] and ctx.state.get('discovery_sources')['work']['feed']['approved']
    integration.decide(APPROVE_1, session_id=delivery_topic, today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1
    accepted = json.loads(tools['discovery_config']({'action': 'source', 'stream': 'work', 'config': SOURCE_CONFIG,
                                                     'user_approved': True}, session_id=delivery_topic))
    assert accepted['ok'] is True and ctx.state.get('discovery_sources')['work']['feed']['approved'] is True


def test_reply_from_an_unrelated_thread_uses_the_only_recent_digest(settings, data_dir, tmp_path, monkeypatch):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    host = HostSessions(integration.home, monkeypatch)
    try:
        _discord_digest(integration, data_dir, ctx, host)
        reply = host.message('discord', chat_id='778', chat_type='thread', thread_id='778', user_id='u2',
                             user_name='Bee', parent_chat_id='555')
    finally:
        host.close()
    before = task_files(settings)
    integration.decide(APPROVE_1, session_id=reply, today='2030-01-01')
    assert len(set(task_files(settings)) - set(before)) == 1


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
    line = next(l for l in integration.finalize(run, session_id='parent')['text'].splitlines() if l.startswith('**Existing task update blocked:**'))
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
    assert f'**Choice:** Reply "{ref}, update 1" or "{ref}, update 2" to add this to that task, or "{ref}, create" for a separate task.' in digest['text']
    # One task per line, in research order.
    assert '**Existing tasks:**\n1. Plan the launch page\n2. Plan the launch email\n' in digest['text']


def test_completed_tasks_are_never_suggested_as_existing_task_updates(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    docs = [rt.store().create(title=t, area='work', undated=True, research=False, confirm_new=True)
            for t in ('Plan the launch page', 'Plan the launch email')]
    done = docs[1].path
    done.write_text(done.read_text().replace('status: open', 'status: done', 1))
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path,
        [{'path': rt.store().rel(d.path), 'match_basis': 'related_only'} for d in docs])
    _own(store, run); _coverage_complete(store, run)
    outcome = integration.conversion.match(run, wid)
    assert outcome['kind'] == 'semantic' and [t['title'] for t in outcome['targets']] == ['Plan the launch page']
    assert [t['title'] for t in outcome['closed_related']] == ['Plan the launch email']
    first = docs[0].path
    first.write_text(first.read_text().replace('status: open', 'status: done', 1))
    assert integration.conversion.match(run, wid)['kind'] == 'new'
