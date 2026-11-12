"""R5 follow-up outcomes: same-day reruns in a mirrored chat, reply guards and retention.

Synthetic data only. Replies go through the registered discovery_decide tool where the
behavior is user-facing.
"""
import datetime as dt
import hashlib
import json
import os
import time

import pytest

from alchemy_task.core.discovery_identity import UserError
from test_discovery_digest_replies import APPROVE_1, build_run, task_files
from test_discovery_reply_redesign import fixture
from test_discovery_reply_threads import _finalize


def _decide_tool(service, ctx, monkeypatch):
    """The registered chat tool, bound to this test's service."""
    from alchemy_task import discovery_integration, runtime, task_tools
    runtime.bind(ctx)
    monkeypatch.setattr(discovery_integration, 'get_service', lambda rt=None: service)
    return lambda args, session_id: json.loads(task_tools.discovery_decide(args, session_id=session_id))


def _same_day_rerun(s, data_dir, origin, *, empty):
    first = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-03')
    if empty:
        store, run, items, wids = build_run(data_dir, 1, state='Empty rerun.')
        second = s.digest.prepare(run, stream='work', day='2030-01-03', origin={'session_id': origin}, items=[])
    else:
        store, run, items, wids = build_run(data_dir, 1, state='A distinct rerun finding for the launch.', link='https://example.test/work/rerun')
        with store._lock(store._run_lock_name(run)):
            ledger = store.get_run(run)
            ledger['origin'] = {'session_id': origin, 'deliver': 'origin'}
            ledger['config']['stream_name'] = 'work'
            ledger['business_date'] = '2030-01-03'
            store._save(run, ledger)
        s.record_decision(run, wids[0], decision='propose', reason='No task.', session_id=origin)
        second = s.finalize(run, session_id=origin)
        assert second['items'][0]['number'] == 2
    return first, second


@pytest.mark.parametrize('second_empty', [False, True])
def test_same_day_rerun_mirrored_in_chat_numbers_across_the_whole_day(settings, data_dir, tmp_path, monkeypatch, second_empty):
    """R4-1: the origin chat shows both same-day digests. A bare '1' is item 1 of that
    stream's day (from the first list), not refused as ambiguous."""
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    decide = _decide_tool(s, ctx, monkeypatch)
    try:
        first, second = _same_day_rerun(s, data_dir, origin, empty=second_empty)
        for digest in (first, second):
            host.db.append_message(origin, role='user', content='[Cron delivery: alchemy-task: discovery work]\n' + digest['text'])
        host.db.append_message(origin, role='user', content='1 create it')
        before = task_files(settings)
        out = decide(APPROVE_1, session_id=origin)
        assert out['ok'] is True, out
        assert len(set(task_files(settings)) - set(before)) == 1
        assert s.digest._load()['proposals'][first['items'][0]['proposal_id']]['state'] == 'complete'
        if not second_empty:
            assert s.digest._load()['proposals'][second['items'][0]['proposal_id']]['state'] == 'pending'
    finally:
        from alchemy_task import runtime
        runtime.bind(None)
        host.close()


def test_quoted_same_day_rerun_digest_stays_exact(settings, data_dir, tmp_path, monkeypatch):
    """A reply-to quote still binds the exact digest: '1' is not on the quoted rerun list."""
    from gateway.run_inbound import GatewayInboundMixin
    from types import SimpleNamespace
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        first, second = _same_day_rerun(s, data_dir, origin, empty=False)
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        event = SimpleNamespace(reply_to_text=second['text'], reply_to_message_id='m2', reply_to_is_own_message=False)
        text = GatewayInboundMixin._prepend_inbound_reply_context(event, host.source(chat_id='999'), '1 create it')
        host.db.append_message(reply, role='user', content=text)
        before = s.digest.path.read_bytes(), task_files(settings)
        with pytest.raises(UserError):
            s.decide(APPROVE_1, session_id=reply)
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
        assert s.decide({**APPROVE_1, 'approve': ['2'], 'edits': {'2': {'area': 'work', 'undated': True}}},
                        session_id=reply)['results'][0]['state'] == 'complete'
    finally:
        host.close()


def test_single_stream_missing_number_asks_for_day_not_stream(settings, data_dir, tmp_path, monkeypatch):
    """R4-1 message: with one stream involved, the refusal does not ask which stream."""
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    decide = _decide_tool(s, ctx, monkeypatch)
    try:
        _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-03')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        before = s.digest.path.read_bytes(), task_files(settings)
        out = decide({'approve': ['9'], 'edits': {'9': {'area': 'work', 'undated': True}}}, session_id=reply)
        assert out['ok'] is False, out
        message = json.dumps(out).casefold()
        assert 'stream' not in message and 'day' in message and 'reply to the digest' in message, out
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
    finally:
        from alchemy_task import runtime
        runtime.bind(None)
        host.close()


def _add_home_stream(ctx):
    streams = ctx.state.get('streams')
    streams['home'] = {**streams['work'], 'name': 'home'}
    ctx.state.set('streams', streams)


def test_bare_number_ignores_a_stale_second_stream(settings, data_dir, tmp_path, monkeypatch):
    """R4-4: only streams with a digest inside the seven-day window compete for a bare number."""
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    decide = _decide_tool(s, ctx, monkeypatch)
    try:
        _add_home_stream(ctx)
        stale = _finalize(s, data_dir, stream='home', origin_session=origin, day='2029-12-20')
        work = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-03')
        reply = host.message(chat_id='999', chat_type='dm', user_id='other')
        out = decide(APPROVE_1, session_id=reply)
        assert out['ok'] is True, out
        proposals = s.digest._load()['proposals']
        assert proposals[work['items'][0]['proposal_id']]['state'] == 'complete'
        assert proposals[stale['items'][0]['proposal_id']]['state'] == 'pending'
    finally:
        from alchemy_task import runtime
        runtime.bind(None)
        host.close()


def test_whole_reply_is_resolved_before_any_dismissal(settings, data_dir, tmp_path, monkeypatch):
    """R4-4: 'dismiss 1, approve 99' refuses and leaves item 1 undismissed."""
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    decide = _decide_tool(s, ctx, monkeypatch)
    try:
        digest = _finalize(s, data_dir, stream='work', origin_session=origin, day='2030-01-03')
        before = s.digest.path.read_bytes(), task_files(settings)
        out = decide({'dismiss': ['1'], 'approve': ['99'], 'edits': {'99': {'area': 'work', 'undated': True}}}, session_id=origin)
        assert out['ok'] is False, out
        assert s.digest._load()['proposals'][digest['items'][0]['proposal_id']]['state'] == 'pending'
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
    finally:
        from alchemy_task import runtime
        runtime.bind(None)
        host.close()


def _child(s, origin):
    run = s.store.init_run(origin={'session_id': origin})
    items = s.store.add_candidates(run, [{'title': 'Read only', 'source_ids': ['source:feed:account:issue:one']}])
    s.store.freeze_index(run, rubric='Read only')
    a = s.store.reserve_attempt(run, items[0]['candidate_id'], owner_session=origin)
    s.store.record_start(run, parent_session=origin, child_session='child-sess', subagent_id='sa-child')
    s.store.bind_attempt(run, a['token'], {'subagent_id': 'sa-child'}, owner_session=origin)
    return 'child-sess'


def test_child_agent_cannot_approve_configure_or_change_settings(settings, data_dir, tmp_path, monkeypatch, owner_only_feature):
    """R4-4: a research child is refused through the registered tools and nothing changes."""
    from test_discovery_reply_threads import _tools, SOURCE_CONFIG
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        _finalize(s, data_dir, stream='work', origin_session=origin)
        child = _child(s, origin)
        before = s.digest.path.read_bytes(), task_files(settings)
        tools = _tools(s, ctx)
        decide = _decide_tool(s, ctx, monkeypatch)
        out = decide(APPROVE_1, session_id=child)
        assert out['ok'] is False and 'read-only' in out['message'], out
        # The service refuses a child too, for callers that bypass the tool guard.
        with pytest.raises(UserError, match='child'):
            s.decide(APPROVE_1, session_id=child)
        for args in ({'action': 'approvals', 'config': {'owner_only': True}, 'user_approved': True},
                     {'action': 'source', 'stream': 'work', 'config': SOURCE_CONFIG, 'user_approved': True}):
            r = json.loads(tools['discovery_config'](args, session_id=child))
            assert r['ok'] is False, r
        assert s.approval_settings()['owner_only'] is False
        assert not ctx.state.get('discovery_sources')
        assert (s.digest.path.read_bytes(), task_files(settings)) == before
    finally:
        from alchemy_task import runtime
        runtime.bind(None)
        host.close()


def test_production_start_keeps_forty_day_runs_and_prunes_sixty_one_day_runs(settings, data_dir, tmp_path):
    """R4-4: discovery_start applies the sixty-day production retention."""
    from test_discovery_integration import configure, service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    store = integration.store

    def closed(days_old):
        run = store.init_run(stream='archive', business_date='2026-01-01', origin={'session_id': 'old-parent'})
        store.save_review(run, {'joined': {'accepted': [], 'failures': []}})
        age = time.time() - days_old * 86400
        os.utime(store.run_dir(run) / 'ledger.json', (age, age))
        return run
    forty, sixty_one = closed(40), closed(61)
    integration.start('work', session_id='parent')
    assert store.run_dir(forty).exists()
    assert not store.run_dir(sixty_one).exists() and store.get_run(sixty_one)['pruned_at']


def _aged_pending_run(tmp_path, settings, data_dir, days_old):
    from test_discovery_dashboard import fixture_service
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    service.utcnow = lambda: dt.datetime(2031, 1, 1, tzinfo=dt.timezone.utc)
    service.reconcile_endstate(run)
    age = time.time() - days_old * 86400
    os.utime(service.store.run_dir(run) / 'ledger.json', (age, age))
    return service, rt, run, proposal


def test_pruned_digest_is_gone_from_chat_replies(tmp_path, settings, data_dir, monkeypatch):
    """R4-4: after pruning, the digest index forgets the run, so its Review code is unknown."""
    service, rt, run, proposal = _aged_pending_run(tmp_path, settings, data_dir, 61)
    assert run in service.store.prune()['deleted_runs']
    saved = service.digest._load()
    assert run not in saved['digests'] and proposal['proposal_id'] not in saved['proposals'] and run not in saved['delivery']
    decide = _decide_tool(service, rt.ctx, monkeypatch)
    try:
        review = hashlib.sha256(run.encode()).hexdigest()[:12]
        out = decide({**APPROVE_1, 'review': review}, session_id='parent')
        assert out['ok'] is False and 'unknown Review code' in out['message'], out
    finally:
        from alchemy_task import runtime
        runtime.bind(None)


@pytest.mark.parametrize('days,deleted', [(10, True), (30, False)])
def test_prune_days_argument_governs_pending_proposal_exemption(tmp_path, settings, data_dir, days, deleted):
    """R4-5: a twenty-day pending run is prunable under a ten-day policy, kept under thirty."""
    service, rt, run, proposal = _aged_pending_run(tmp_path, settings, data_dir, 20)
    result = service.store.prune(days=days)
    assert (run in result['deleted_runs']) is deleted
    assert service.store.run_dir(run).exists() is not deleted


def test_owner_only_is_not_available_in_this_version_from_chat(settings, data_dir, tmp_path, monkeypatch):
    """v1 gate: turning approvals.owner_only on from chat is refused and writes nothing;
    approvals stay open to the profile's chats."""
    from test_discovery_reply_threads import _tools
    s, rt, ctx, host, origin = fixture(settings, data_dir, tmp_path, monkeypatch)
    try:
        digest = _finalize(s, data_dir, stream='work', origin_session=origin)
        out = json.loads(_tools(s, ctx)['discovery_config'](
            {'action': 'approvals', 'config': {'owner_only': True}, 'user_approved': True}, session_id=origin))
        assert out['ok'] is False and out['needs'] == 'not_available', out
        assert 'not available in this version' in out['message'], out
        assert ctx.state.get('discovery_approvals') is None
        assert s.approval_settings() == {'owner_only': False, 'owners': {}}
        other = host.message('slack', chat_id='C1', chat_type='dm', user_id='anyone')
        assert s.decide({'dismiss': ['1']}, session_id=other)['dismissed'] == [digest['items'][0]['proposal_id']]
    finally:
        host.close()
