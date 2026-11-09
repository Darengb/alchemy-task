"""R5 follow-up outcomes: same-day reruns in a mirrored chat.

Synthetic data only. Replies go through the registered discovery_decide tool where the
behavior is user-facing.
"""
import json

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
        store, run, items, wids = build_run(data_dir, 1, state='A distinct rerun finding for the launch.')
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
