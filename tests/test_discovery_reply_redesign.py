"""R4 outcomes through host transcripts and public chat tools, synthetic data only."""
import datetime as dt
import hashlib
import json

import pytest

from alchemy_task.core.discovery_identity import UserError
from host_threads import HostSessions
from test_discovery_digest_replies import APPROVE_1, build_run, task_files
from test_discovery_integration import service
from test_discovery_reply_threads import _bind_work, _finalize, _tools, SOURCE_CONFIG


def code(digest):
    return hashlib.sha256(digest['run_id'].encode()).hexdigest()[:12]


def fixture(settings, data_dir, tmp_path, monkeypatch):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    integration.utcnow = lambda: dt.datetime(2030, 1, 3, 12, tzinfo=dt.timezone.utc)
    host = HostSessions(integration.home, monkeypatch)
    origin = host.message(chat_id='100', chat_type='dm', user_id='owner')
    _bind_work(ctx, origin)
    return integration, rt, ctx, host, origin


def test_pasted_old_digest_in_unrelated_chat_creates_once(settings, data_dir, tmp_path, monkeypatch):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        old = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-01')
        newer = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-02')
        reply = host.message(chat_id='999', chat_type='group', thread_id='42', user_id='other')
        host.db.append_message(reply, role='user', content=old['text'])
        host.db.append_message(reply, role='user', content='1')
        before = task_files(settings)
        result = s.decide(APPROVE_1, session_id=reply)
        assert result['results'][0]['state'] == 'complete'
        assert len(set(task_files(settings)) - set(before)) == 1
        assert s.digest._load()['proposals'][old['items'][0]['proposal_id']]['state'] == 'complete'
        assert s.digest._load()['proposals'][newer['items'][0]['proposal_id']]['state'] == 'pending'
        s.decide(APPROVE_1, session_id=reply)
        assert len(set(task_files(settings)) - set(before)) == 1
    finally:
        host.close()


@pytest.mark.parametrize('legacy', [False, True])
def test_reply_quote_beats_newer_transcript_digest(settings, data_dir, tmp_path, monkeypatch, legacy):
    from gateway.run_inbound import GatewayInboundMixin
    from types import SimpleNamespace
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        old = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-01')
        new = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-02')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        host.db.append_message(reply, role='assistant', content=new['text'])
        quote = old['text']
        if legacy:
            # Full text also works for old stored digests without a Review line.
            from alchemy_task.core.discovery_state import atomic_json
            data = s.digest._load()
            quote = quote.replace('Task Discovery:', 'Discovery:')
            quote = '\n'.join(line for line in quote.splitlines() if not line.startswith('Review:'))
            data['digests'][old['run_id']]['text'] = quote
            atomic_json(s.digest.path, data)
        event = SimpleNamespace(reply_to_text=quote, reply_to_message_id='message-1', reply_to_is_own_message=False)
        text = GatewayInboundMixin._prepend_inbound_reply_context(event, host.source(chat_id='999'), '1 create it')
        host.db.append_message(reply, role='user', content=text)
        result = s.decide(APPROVE_1, session_id=reply)
        assert result['results'][0]['state'] == 'complete'
        assert s.digest._load()['proposals'][old['items'][0]['proposal_id']]['state'] == 'complete'
        assert s.digest._load()['proposals'][new['items'][0]['proposal_id']]['state'] == 'pending'
    finally:
        host.close()


def test_explicit_reference_beats_quote_and_review(settings, data_dir, tmp_path, monkeypatch):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        old = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-01')
        new = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-02')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        host.db.append_message(reply, role='user', content=old['text'])
        pid = new['items'][0]['proposal_id']
        assert s.decide({'dismiss': [pid], 'review': code(old)}, session_id=reply)['dismissed'] == [pid]
        assert s.decide({'dismiss': ['1'], 'day': new['day'], 'review': code(old)}, session_id=reply)['dismissed'] == [pid]
    finally:
        host.close()


@pytest.mark.parametrize('review', ['000000000000', 'BAD', 'foreign'])
def test_unknown_or_other_profile_review_never_guesses(settings, data_dir, tmp_path, monkeypatch, review):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        digest = _finalize(s, data_dir, stream='work', origin_session=origin)
        if review == 'foreign':
            from alchemy_task.discovery_digest import DiscoveryDigest
            other = DiscoveryDigest(tmp_path / 'other-profile')
            foreign = other.prepare('foreign-run', stream='work', day='2030-01-01', origin={'session_id': 'foreign'}, items=[])
            review = code(foreign)
        before = s.digest.path.read_bytes(), task_files(settings)
        with pytest.raises(UserError, match='[Rr]eview'):
            s.decide({**APPROVE_1, 'review': review}, session_id=origin)
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
    finally:
        host.close()


def test_pasted_expired_digest_is_refused(settings, data_dir, tmp_path, monkeypatch):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        digest = _finalize(s, data_dir, stream='work', origin_session=origin)
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        host.db.append_message(reply, role='user', content=digest['text'])
        before = s.digest.path.read_bytes(), task_files(settings)
        with pytest.raises(UserError, match='expired'):
            s.decide(APPROVE_1, session_id=reply, today='2030-01-09')
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
    finally:
        host.close()


def test_two_pasted_streams_ask_which_then_prefix_or_name_resolves(settings, data_dir, tmp_path, monkeypatch):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        streams = ctx.state.get('streams')
        streams['work']['label'] = 'A'
        streams['home'] = {**streams['work'], 'name': 'home', 'label': 'B', 'origin_session': 'home-origin'}
        ctx.state.set('streams', streams)
        work = _finalize(s, data_dir, stream='work', origin_session=origin)
        home = _finalize(s, data_dir, stream='home', origin_session='home-origin')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        host.db.append_message(reply, role='user', content=work['text'] + '\n\n' + home['text'])
        with pytest.raises(UserError, match='[Ww]hich stream|ambiguous'):
            s.decide({'dismiss': ['1']}, session_id=reply)
        assert s.decide({'dismiss': ['B1']}, session_id=reply)['dismissed'] == [home['items'][0]['proposal_id']]
        assert s.decide({'dismiss': ['1'], 'stream': 'WORK TASK DISCOVERY'}, session_id=reply)['dismissed'] == [work['items'][0]['proposal_id']]
    finally:
        host.close()


@pytest.mark.parametrize('stream', ['work discovery', 'WORK TASK DISCOVERY', 'W', 'tasks', 'task', ''])
def test_create_skip_update_tool_arguments_leave_skip_pending(settings, data_dir, tmp_path, monkeypatch, stream):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        streams = ctx.state.get('streams'); streams['work']['label'] = 'W'; ctx.state.set('streams', streams)
        targets = [rt.store().create(title=title, area='work', undated=True, research=False)
                   for title in ('Existing target', 'Other target')]
        nominations = [{'path': rt.store().rel(t.path), 'match_basis': 'related_only'} for t in targets]
        store, run, items, wids = build_run(data_dir, 3, nominations={2: nominations})
        with store._lock(store._run_lock_name(run)):
            ledger = store.get_run(run); ledger['origin'] = {'session_id': origin}; store._save(run, ledger)
        for wid in wids:
            s.record_decision(run, wid, decision='propose', reason='Independent action.', session_id=origin)
        digest = s.finalize(run, session_id=origin)

        # The model maps "work discovery 1 create 2 skip 3 update" to approve+edits,
        # omitting skip, exactly as it omits unmentioned items.
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        before = len(task_files(settings))
        from alchemy_task.core.taskfile import content_hash
        args = {'stream': stream, 'approve': ['1', '3'], 'edits': {
            '1': {'choice': 'create', 'area': 'work', 'undated': True},
            '3': {'choice': 'update', 'target_task_id': targets[0].task_id, 'expected_revision': content_hash(targets[0].raw)}}}
        # Several nominated targets require an explicit selection, with no task writes.
        missing = {**args, 'edits': {**args['edits'], '3': {'choice': 'update'}}}
        with pytest.raises(UserError, match='target_task_id'):
            s.decide(missing, session_id=reply)
        assert len(task_files(settings)) == before and targets[0].path.read_bytes() == targets[0].raw
        out = s.decide(args, session_id=reply)
        assert all(r['state'] == 'complete' for r in out['results']) and len(task_files(settings)) == before + 1
        skipped = digest['items'][1]
        assert s.digest._load()['proposals'][skipped['proposal_id']]['state'] == 'pending'
        s.decide({'approve': ['2'], 'edits': {'2': {'choice': 'create', 'area': 'work', 'undated': True}}}, session_id=reply, today='2030-01-04')
        assert len(task_files(settings)) == before + 2
        assert targets[0].path.read_bytes() != targets[0].raw
        assert targets[1].path.read_bytes() == targets[1].raw
    finally:
        host.close()


def test_confirmed_owner_only_setting_and_sender_not_session_creator(settings, data_dir, tmp_path, monkeypatch):
    from gateway.session_context import set_session_vars, clear_session_vars
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        digest = _finalize(s, data_dir, stream='work', origin_session=origin)
        tools = _tools(s, ctx)
        args = {'action': 'approvals', 'config': {'owner_only': True}, 'user_approved': True}
        no_confirm = json.loads(tools['discovery_config']({**args, 'user_approved': False}, session_id=origin))
        assert no_confirm['ok'] is False
        enabled = json.loads(tools['discovery_config'](args, session_id=origin))
        assert enabled['ok'], enabled
        assert enabled['result']['owner_only'] is True
        assert enabled['result']['owners']['telegram'] == ['owner']
        assert json.loads(tools['discovery_config']({'action': 'status'}, session_id=origin))['result']['approvals']['owner_only'] is True
        # A shared session may still record its creator (or system:cron). Current host
        # per-message context must win, never a claimed sender in tool arguments.
        tokens = set_session_vars(platform='telegram', user_id='other', session_id=origin, cron_session='')
        before = s.digest.path.read_bytes(), task_files(settings)
        try:
            with pytest.raises(UserError, match='owner'):
                s.decide(APPROVE_1, session_id=origin)
            refused = json.loads(tools['discovery_config']({'action': 'source', 'stream': 'work', 'config': SOURCE_CONFIG, 'user_approved': True}, session_id=origin))
            assert refused['ok'] is False and not ctx.state.get('discovery_sources')
            assert json.loads(tools['discovery_config']({**args, 'config': {'owner_only': False}}, session_id=origin))['ok'] is False
        finally:
            clear_session_vars(tokens)
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
        other_chat = host.message(chat_id='999', chat_type='dm', user_id='owner')
        assert s.decide(APPROVE_1, session_id=other_chat)['results'][0]['state'] == 'complete'
    finally:
        host.close()


def test_default_sender_rule_allows_other_user_and_config_from_any_topic(settings, data_dir, tmp_path, monkeypatch):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        _finalize(s, data_dir, stream='work', origin_session=origin)
        other = host.message(chat_id='999', chat_type='group', thread_id='42', user_id='other')
        assert s.decide(APPROVE_1, session_id=other)['results'][0]['state'] == 'complete'
        tools = _tools(s, ctx)
        response = json.loads(tools['discovery_config']({'action': 'source', 'stream': 'work', 'config': SOURCE_CONFIG, 'user_approved': True}, session_id=other))
        assert response['ok'] and ctx.state.get('discovery_sources')['work']['feed']['approved']
    finally:
        host.close()
