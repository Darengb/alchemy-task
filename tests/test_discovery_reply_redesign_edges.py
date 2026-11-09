"""Additional reply precedence and sender authority outcomes."""
import json

import pytest

from alchemy_task.core.discovery_identity import UserError
from host_threads import HostSessions
from test_discovery_reply_redesign import fixture, code
from test_discovery_reply_threads import _finalize, _tools
from test_discovery_digest_replies import APPROVE_1, task_files


def test_explicit_review_selects_old_digest_without_transcript(settings, data_dir, tmp_path, monkeypatch):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        old = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-01')
        _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-02')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        assert s.decide({'dismiss': ['1'], 'review': code(old)}, session_id=reply)['dismissed'] == [old['items'][0]['proposal_id']]
    finally:
        host.close()


@pytest.mark.parametrize('order', ['two_user_turns', 'one_user_turn', 'assistant_after_user'])
def test_most_recent_digest_in_conversation_wins_for_one_stream(settings, data_dir, tmp_path, monkeypatch, order):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        old = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-01')
        new = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-02')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        if order == 'one_user_turn':
            host.db.append_message(reply, role='user', content=old['text'] + '\n\n' + new['text'])
        else:
            host.db.append_message(reply, role='user', content=old['text'])
            host.db.append_message(reply, role='assistant' if order == 'assistant_after_user' else 'user', content=new['text'])
        host.db.append_message(reply, role='user', content='1 dismiss')
        assert s.decide({'dismiss': ['1']}, session_id=reply)['dismissed'] == [new['items'][0]['proposal_id']]
    finally:
        host.close()


def test_quote_of_stream_a_beats_newer_stream_b(settings, data_dir, tmp_path, monkeypatch):
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        work = _finalize(s, data_dir, stream='work', origin_session=origin)
        streams = ctx.state.get('streams'); streams['home'] = {**streams['work'], 'name': 'home'}; ctx.state.set('streams', streams)
        home = _finalize(s, data_dir, stream='home', origin_session=origin, day='2030-01-02')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        host.db.append_message(reply, role='assistant', content=home['text'])
        host.db.append_message(reply, role='user', content=f'[Replying to: "{work["text"]}"]\n\n1 dismiss')
        assert s.decide({'dismiss': ['1']}, session_id=reply)['dismissed'] == [work['items'][0]['proposal_id']]
    finally:
        host.close()


@pytest.mark.parametrize('action', ['revise', 'cancel'])
def test_plan_changes_use_sender_rule_not_location(settings, data_dir, tmp_path, monkeypatch, action):
    from alchemy_task.core.discovery_dossiers import content_revision
    from alchemy_task.core.discovery_state import read_json
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        digest = _finalize(s, data_dir, stream='work', origin_session=origin)
        item = digest['items'][0]
        run, wid = item['run_id'], item['unit_id']
        s.conversion.prepare(run, wid, choice='create', area='work', undated=True, user_approved=True, reason='User approved')
        plan_path, _ = s.conversion._paths(run, wid)
        tools = _tools(s, ctx)
        other = host.message(chat_id='999', chat_type='dm', user_id='other')
        owner = host.message(chat_id='888', chat_type='dm', user_id='owner')
        args = {'run_id': run, 'unit_id': wid, 'action': action, 'expected_plan_revision': content_revision(read_json(plan_path)),
                'reason': 'User correction', 'user_approved': True, 'edits': {'title': 'Corrected action'}}
        enabled = json.loads(tools['discovery_config']({'action': 'approvals', 'config': {'owner_only': True}, 'user_approved': True}, session_id=origin))
        assert enabled['ok']
        before = plan_path.read_bytes(), task_files(settings)
        denied = json.loads(tools['discovery_conversion_recover'](args, session_id=other))
        assert denied['ok'] is False and 'owner' in denied['error']
        assert (plan_path.read_bytes(), task_files(settings)) == before
        accepted = json.loads(tools['discovery_conversion_recover'](args, session_id=owner))
        assert accepted['ok'], accepted
        assert plan_path.read_bytes() != before[0] and task_files(settings) == before[1]
    finally:
        host.close()


def test_scheduled_context_cannot_approve_or_change_settings(settings, data_dir, tmp_path, monkeypatch):
    from gateway.session_context import set_session_vars, clear_session_vars
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        _finalize(s, data_dir, stream='work', origin_session=origin)
        tokens = set_session_vars(platform='telegram', user_id='owner', session_id=origin, cron_session='1')
        before = s.digest.path.read_bytes(), task_files(settings)
        try:
            with pytest.raises(UserError, match='scheduled'):
                s.decide(APPROVE_1, session_id=origin)
            tools = _tools(s, ctx)
            assert json.loads(tools['discovery_config']({'action': 'approvals', 'config': {'owner_only': True}, 'user_approved': True}, session_id=origin))['ok'] is False
        finally:
            clear_session_vars(tokens)
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
    finally:
        host.close()


def test_tasks_create_skip_through_public_tool(settings, data_dir, tmp_path, monkeypatch):
    from alchemy_task import runtime, task_tools, discovery_integration
    from test_discovery_digest_replies import build_run
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        store, run, _, wids = build_run(data_dir, 2)
        for wid in wids: s.record_decision(run, wid, decision='propose', reason='Independent ask', session_id='parent')
        s.finalize(run, session_id='parent')
        other = host.message(chat_id='999', chat_type='group', user_id='other')
        runtime.bind(ctx)
        monkeypatch.setattr(discovery_integration, 'get_service', lambda rt=None: s)
        args = {'stream': 'tasks', 'approve': ['1'], 'edits': {'1': {'choice': 'create', 'area': 'work', 'undated': True}}}
        before = len(task_files(settings))
        out = json.loads(task_tools.discovery_decide(args, session_id=other))
        assert out['ok'] and out['results'][0]['state'] == 'complete', out
        assert len(task_files(settings)) == before + 1
        assert [p['state'] for p in sorted(s.digest._load()['proposals'].values(), key=lambda p: p['binding']['number'])] == ['complete', 'pending']
    finally:
        runtime.bind(None)
        host.close()


def test_owner_identity_is_confirmed_per_platform_with_host_alternate_id(settings, data_dir, tmp_path, monkeypatch):
    from gateway.session_context import set_session_vars, clear_session_vars
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        digest = _finalize(s, data_dir, stream='work', origin_session=origin)
        tools = _tools(s, ctx)
        args = {'action': 'approvals', 'config': {'owner_only': True}, 'user_approved': True}
        assert json.loads(tools['discovery_config'](args, session_id=origin))['ok']
        second = host.message('slack', chat_id='C1', chat_type='dm', user_id='slack-owner', user_id_alt='alternate-owner')
        with pytest.raises(UserError, match='owner'):
            s.decide({'dismiss': ['1']}, session_id=second)
        assert json.loads(tools['discovery_config'](args, session_id=second))['ok']
        assert s.approval_settings()['owners']['slack'] == ['slack-owner', 'alternate-owner']
        tokens = set_session_vars(platform='slack', user_id='different-primary', user_id_alt='alternate-owner', session_id=second, cron_session='')
        try:
            assert s.decide({'dismiss': ['1']}, session_id=second)['dismissed'] == [digest['items'][0]['proposal_id']]
        finally:
            clear_session_vars(tokens)
    finally:
        host.close()
