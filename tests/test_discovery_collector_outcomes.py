"""Collector and admission outcome tests through the registered integration path.

Each test drives approved synthetic readers through start -> collect -> freeze
(and, where cheap, join -> digest) and asserts what the user sees: backlog,
receipts, watermarks and digest text. Synthetic data only.
"""
import json

from test_discovery_integration import service, configure
from test_discovery_metadata_projection import slack_service, envelope, ts_in


def test_long_slack_thread_is_partial_and_keeps_sibling_followups(settings, data_dir, tmp_path):
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    def dispatch(tool, args):
        if tool == 'reader':
            return envelope(args, [
                {'channel_id': 'C1', 'ts': ts_in(args, 100), 'thread_ts': ts_in(args, 90000), 'text': 'reply in busy thread'},
                {'channel_id': 'C2', 'ts': ts_in(args, 3600), 'text': 'Separate ask in quiet channel'},
            ])
        request = args['request']
        if request['operation'] == 'replies':
            # One provider page of a longer thread: more replies remain.
            root = {'ts': request['ts'], 'text': 'root of busy thread'}
            replies = [{'ts': '%s%03d' % (request['ts'][:-3], i), 'text': 'r'} for i in range(1, 200)]
            return envelope(args, [root] + replies, next_cursor='more', pagination_exhausted=False)
        return envelope(args, [{'ts': ts_in(args, 3600), 'channel_id': 'C2', 'text': 'Separate ask in quiet channel'}])
    ctx.dispatch_tool = dispatch
    run = integration.start('work', session_id='parent')['run_id']
    receipt = integration.collect(run, 'feed', session_id='parent')
    assert receipt['status'] == 'partial', receipt
    backlog = {b['source_ids'][0].split(':')[2]: b for b in integration.store.source_state('work', 'feed')['backlog']}
    assert set(backlog) == {'C1', 'C2'}
    assert backlog['C1']['candidate'].get('partial') is True
    assert 'partial' not in backlog['C2']['candidate']
    # Seed pages were exhausted; only thread context was truncated, so the
    # window is acquired (N1) while the receipt and digest stay partial.
    assert integration.store.source_state('work', 'feed').get('watermark') == receipt['end']
    integration.freeze(run, session_id='parent')
    candidates = integration.store.get_run(run)['candidates']
    assert len(candidates) == 2
    joined = integration.runner.join(run, session_id='parent', degraded={c['candidate_id']: 'not researched in this test' for c in candidates})
    assert joined['joined'] is True
    text = integration.finalize(run, session_id='parent')['text']
    assert 'Coverage: feed: partial' in text and 'degraded' in text
    assert 'No new follow-ups found.' not in text


def _mail_message(mid, sender, subject, at, text):
    import base64
    return {'id': mid, 'internalDate': str(at), 'payload': {'mimeType': 'text/plain',
            'headers': [{'name': 'From', 'value': sender}, {'name': 'Subject', 'value': subject}],
            'body': {'data': base64.urlsafe_b64encode(text.encode()).decode()}}}


def test_transcript_source_run_first_never_hides_ordinary_mail(tmp_path):
    """Only the mail source publishes the shared all-thread snapshot; transcript consumes it."""
    from alchemy_task.core.discovery_state import DiscoveryStore
    from alchemy_task.discovery_collectors import make_daily_reader
    from alchemy_task.discovery_sources import SourceAdapter
    start, end = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
    at = 1767225600000 + 1000
    scope = {'mailbox': 'work'}  # same human scope label for both sources
    mail = {'source_key': 'mail', 'account_key': 'acct', 'scope': scope, 'read_method': 'mailer', 'kind': 'mail',
            'sender_domains': ['example.test']}
    notes = {**mail, 'source_key': 'notes', 'kind': 'transcript', 'service_sender': 'notes@service.test'}
    threads = {'tn': [_mail_message('n1', 'notes@service.test', 'Notes', at, 'Suggested next steps\nShip it\nSummary\nx')],
               'tm': [_mail_message('m1', 'peer@example.test', 'Please approve', at, 'Approve the proof')]}
    def env(c, s, e, items):
        return {'account_key': c['account_key'], 'scope': c['scope'], 'start': s, 'end': e, 'items': items,
                'next_cursor': None, 'pagination_exhausted': True}
    def thread(c, s, e, tid):
        return env(c, s, e, [{'id': tid, 'messages': threads[tid], 'complete': True}])
    store = DiscoveryStore(tmp_path / 'state')
    # The transcript binding filters by service sender, so it lists only note threads.
    notes_receipt = SourceAdapter(store, notes, read_page=make_daily_reader(
        notes, lambda c, s, e, k: env(c, s, e, [{'id': 'n1', 'threadId': 'tn'}]),
        snapshot_root=tmp_path / 'snap', read_thread=thread)).collect('st', start=start, end=end)
    assert notes_receipt['status'] == 'complete'
    assert len(store.source_state('st', 'notes')['backlog']) == 1
    mail_lists = []
    def mail_reader(c, s, e, k):
        mail_lists.append(k)
        return env(c, s, e, [{'id': 'n1', 'threadId': 'tn'}, {'id': 'm1', 'threadId': 'tm'}])
    mail_receipt = SourceAdapter(store, mail, read_page=make_daily_reader(
        mail, mail_reader, snapshot_root=tmp_path / 'snap', read_thread=thread)).collect('st', start=start, end=end)
    assert mail_receipt['status'] == 'complete'
    assert mail_lists, 'mail source must list its own mailbox'
    backlog = store.source_state('st', 'mail')['backlog']
    assert [b['candidate']['title'] for b in backlog] == ['Please approve']
    # A transcript source run after mail reuses the mail snapshot with zero list reads.
    later = {**notes, 'source_key': 'notes2'}
    def no_list(c, s, e, k):
        raise AssertionError('transcript should consume the published mail snapshot')
    receipt = SourceAdapter(store, later, read_page=make_daily_reader(
        later, no_list, snapshot_root=tmp_path / 'snap', read_thread=thread)).collect('st', start=start, end=end)
    assert receipt['status'] == 'complete' and len(store.source_state('st', 'notes2')['backlog']) == 1


def test_mail_source_setup_requires_sender_domains_or_explicit_admit_all(settings, data_dir, tmp_path):
    import pytest
    from alchemy_task.core.discovery_identity import UserError
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    saved_before = json.dumps(ctx.state.get('discovery_sources'), sort_keys=True)
    mail = {**config, 'kind': 'mail'}
    mail.pop('approved', None)
    for missing in ({}, {'sender_domains': []}, {'sender_domains': ['  ']}, {'admit_all': 'yes'}):
        with pytest.raises(UserError, match='sender_domains'):
            integration.configure('work', {**mail, **missing}, user_approved=True)
        assert json.dumps(ctx.state.get('discovery_sources'), sort_keys=True) == saved_before
    saved = integration.configure('work', {**mail, 'sender_domains': ['example.test'], 'excluded_senders': ['support@example.test']}, user_approved=True)
    assert ctx.state.get('discovery_sources')['work']['feed']['sender_domains'] == ['example.test'] == saved['sender_domains']
    saved = integration.configure('work', {**mail, 'admit_all': True}, user_approved=True)
    assert ctx.state.get('discovery_sources')['work']['feed']['admit_all'] is True


def _window_reader(items, *, fail=False):
    """Approved generic reader that returns only items inside the requested window."""
    import datetime as dt
    calls = []
    def reader(tool, args):
        calls.append((args['start'], args['end']))
        if fail:
            return json.dumps({'error': 'provider unavailable'})
        low, high = dt.datetime.fromisoformat(args['start']), dt.datetime.fromisoformat(args['end'])
        inside = [{k: v for k, v in item.items() if k != 'at'} for item in items if low <= item['at'] <= high]
        return json.dumps({'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
                           'items': inside, 'next_cursor': None, 'pagination_exhausted': True})
    reader.calls = calls
    return reader


def _close_run(integration, run):
    integration.freeze(run, session_id='parent')
    candidates = integration.store.get_run(run)['candidates']
    integration.runner.join(run, session_id='parent', degraded={c['candidate_id']: 'not researched in this test' for c in candidates})
    return integration.finalize(run, session_id='parent')


def test_failed_first_run_window_is_reread_by_the_next_run(settings, data_dir, tmp_path):
    import datetime as dt
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    day1 = dt.datetime(2030, 1, 2, 23, 0, tzinfo=dt.timezone.utc)
    day2 = day1 + dt.timedelta(days=1)
    item = {'title': 'Ask raised during the failed first window', 'source_ids': ['source:feed:account:issue:early'],
            'source_revision': 'v1', 'at': day1 - dt.timedelta(hours=3)}
    # Day 1: the stream's first run cannot read the source.
    integration.utcnow = lambda: day1
    ctx.dispatch_tool = _window_reader([item], fail=True)
    first = integration.start('work', session_id='parent')
    assert integration.collect(first['run_id'], 'feed', session_id='parent')['status'] == 'failed'
    text1 = _close_run(integration, first['run_id'])['text']
    assert 'Coverage: feed: failed' in text1 and 'No new follow-ups found.' not in text1
    # Day 2: the reader works again. The failed interval must be read again.
    integration.utcnow = lambda: day2
    reader = _window_reader([item])
    ctx.dispatch_tool = reader
    second = integration.start('work', session_id='parent')
    assert second['resumed'] is False
    assert second['windows']['feed']['start'] == first['windows']['feed']['start']
    assert second['windows']['feed']['end'] == day2.isoformat()
    receipt = integration.collect(second['run_id'], 'feed', session_id='parent')
    assert receipt['status'] == 'complete' and receipt['covered_intervals'] == [[first['windows']['feed']['start'], day2.isoformat()]]
    integration.freeze(second['run_id'], session_id='parent')
    titles = [c['title'] for c in integration.store.get_run(second['run_id'])['candidates']]
    assert titles == ['Ask raised during the failed first window']
    assert integration.store.source_state('work', 'feed')['watermark'] == day2.isoformat()
    # Day 3: the committed watermark controls the window again.
    third_now = day2 + dt.timedelta(days=1)
    integration.utcnow = lambda: third_now
    candidates = integration.store.get_run(second['run_id'])['candidates']
    integration.runner.join(second['run_id'], session_id='parent', degraded={c['candidate_id']: 'not researched in this test' for c in candidates})
    integration.finalize(second['run_id'], session_id='parent')
    third = integration.start('work', session_id='parent')
    assert third['windows']['feed']['start'] == day2.isoformat()


def test_changed_identity_makes_dependent_source_need_reconfigure(settings, data_dir, tmp_path):
    import pytest
    from alchemy_task.core.discovery_identity import UserError
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    config['relevance']['identity_requirements'] = ['name']
    config['seed_queries'] = ['"First Person"']
    integration.confirm_identity('account', {'name': 'First Person', 'aliases': [], 'user_id': None}, user_confirmed=True)
    integration.configure('work', config, user_approved=True)
    # Re-confirming the same mapping changes nothing.
    integration.confirm_identity('account', {'name': 'First Person', 'aliases': [], 'user_id': None}, user_confirmed=True)
    assert 'needs_reconfigure' not in ctx.state.get('discovery_sources')['work']['feed']
    # The user corrects the mapping; the saved source still holds the old name literal.
    integration.confirm_identity('account', {'name': 'Second Person', 'aliases': ['SP'], 'user_id': None}, user_confirmed=True)
    saved = ctx.state.get('discovery_sources')['work']['feed']
    assert saved['needs_reconfigure']['status'] == 'needs_input'
    assert 'identity' in saved['needs_reconfigure']['reason']
    runs_before = len(integration._all_runs())
    with pytest.raises(UserError, match='needs_input'):
        integration.start('work', session_id='parent')
    assert len(integration._all_runs()) == runs_before
    # Reconfiguring with reviewed queries clears the flag and the run uses the new identity.
    config['seed_queries'] = ['"Second Person"', '"SP"']
    integration.configure('work', {k: v for k, v in config.items() if k not in {'identity', 'needs_reconfigure'}}, user_approved=True)
    started = integration.start('work', session_id='parent')
    assert [s['identity']['name'] for s in started['sources']] == ['Second Person']
    assert started['sources'][0]['seed_queries'] == ['"Second Person"', '"SP"']



def _busy_thread_dispatch(day1, *, replies_calls=None):
    """Seeds on day 1 only: one reply in a thread longer than one provider page, one quiet ask."""
    import datetime as dt
    seed_ts = '%.6f' % (day1 - dt.timedelta(hours=2)).timestamp()
    root_ts = '%.6f' % (day1 - dt.timedelta(hours=20)).timestamp()
    sib_ts = '%.6f' % (day1 - dt.timedelta(hours=3)).timestamp()
    def dispatch(tool, args):
        if tool == 'reader':
            low, high = dt.datetime.fromisoformat(args['start']).timestamp(), dt.datetime.fromisoformat(args['end']).timestamp()
            seeds = [{'channel_id': 'C1', 'ts': seed_ts, 'thread_ts': root_ts, 'text': 'reply in busy thread'},
                     {'channel_id': 'C2', 'ts': sib_ts, 'text': 'Separate ask in quiet channel'}]
            return envelope(args, [s for s in seeds if low <= float(s['ts']) <= high])
        request = args['request']
        if request['operation'] == 'replies':
            root = {'ts': request['ts'], 'text': 'root of busy thread'}
            replies = [{'ts': '%s%03d' % (request['ts'][:-3], i), 'text': 'r'} for i in range(1, 200)]
            return envelope(args, [root] + replies, next_cursor='more', pagination_exhausted=False)
        return envelope(args, [{'ts': sib_ts, 'channel_id': 'C2', 'text': 'Separate ask in quiet channel'}])
    return dispatch


def test_busy_slack_thread_is_partial_once_then_the_window_moves_on(settings, data_dir, tmp_path):
    """Seed pages exhausted and only one thread truncated: partial that day, watermark advances (source reads one page)."""
    import datetime as dt
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    day1 = dt.datetime(2030, 1, 2, 23, 0, tzinfo=dt.timezone.utc)
    ctx.dispatch_tool = _busy_thread_dispatch(day1)
    integration.utcnow = lambda: day1
    first = integration.start('work', session_id='parent')
    receipt = integration.collect(first['run_id'], 'feed', session_id='parent')
    assert receipt['status'] == 'partial' and 'not exhausted' in receipt['error']
    backlog = {b['source_ids'][0].split(':')[2]: b for b in integration.store.source_state('work', 'feed')['backlog']}
    assert backlog['C1']['candidate'].get('partial') is True and 'partial' not in backlog['C2']['candidate']
    assert integration.store.source_state('work', 'feed')['watermark'] == day1.isoformat()
    text1 = _close_run(integration, first['run_id'])['text']
    assert 'Coverage: feed: partial' in text1 and 'degraded' in text1
    day2 = day1 + dt.timedelta(days=1)
    integration.utcnow = lambda: day2
    second = integration.start('work', session_id='parent')
    assert second['windows']['feed'] == {'start': day1.isoformat(), 'end': day2.isoformat()}
    for b in integration.store.source_state('work', 'feed')['backlog']:
        # Stand-in for day 1 research having settled both follow-ups, so day 2 has nothing new.
        integration.store.update_backlog('work', 'feed', b['backlog_id'], status='accepted', lineage={'run_id': first['run_id'], 'test': 'settled'})
    receipt2 = integration.collect(second['run_id'], 'feed', session_id='parent')
    assert receipt2['status'] == 'complete'
    text2 = _close_run(integration, second['run_id'])['text']
    assert 'Coverage: feed: complete' in text2 and 'degraded' not in text2
    assert 'No new follow-ups found.' in text2


def test_unexhausted_slack_search_page_still_never_advances(settings, data_dir, tmp_path):
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    def dispatch(tool, args):
        if tool == 'reader':
            return envelope(args, [{'channel_id': 'C2', 'ts': ts_in(args, 3600), 'text': 'Ask'}],
                            next_cursor=None, pagination_exhausted=False)
        return envelope(args, [{'ts': ts_in(args, 3600), 'channel_id': 'C2', 'text': 'Ask'}])
    ctx.dispatch_tool = dispatch
    run = integration.start('work', session_id='parent')['run_id']
    receipt = integration.collect(run, 'feed', session_id='parent')
    assert receipt['status'] != 'complete'
    assert integration.store.source_state('work', 'feed').get('watermark') is None


def test_slack_search_with_more_pages_and_a_truncated_thread_never_advances(settings, data_dir, tmp_path):
    """A real next search cursor (the pass stops at max_pages=1) plus a busy thread: the window is not acquired."""
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    def dispatch(tool, args):
        if tool == 'reader':
            if args.get('cursor'):
                return envelope(args, [{'channel_id': 'C3', 'ts': ts_in(args, 7200), 'text': 'Second page ask'}])
            return envelope(args, [{'channel_id': 'C1', 'ts': ts_in(args, 100), 'thread_ts': ts_in(args, 90000), 'text': 'reply in busy thread'}],
                            next_cursor='page2', pagination_exhausted=False)
        request = args['request']
        if request['operation'] == 'replies':
            return envelope(args, [{'ts': request['ts'], 'text': 'root'}, {'ts': ts_in(args, 100), 'text': 'reply in busy thread'}],
                            next_cursor='more', pagination_exhausted=False)
        return envelope(args, [{'ts': request.get('oldest') or request.get('latest'), 'channel_id': request['channel'], 'text': 'ctx'}])
    ctx.dispatch_tool = dispatch
    run = integration.start('work', session_id='parent')['run_id']
    receipt = integration.collect(run, 'feed', session_id='parent', max_pages=1)
    assert receipt['status'] != 'complete'
    assert integration.store.source_state('work', 'feed').get('watermark') is None


import pytest as _pytest


_SKIP_REASON = {'missing_root': 'primary thread root missing', 'channel_mismatch': 'primary channel mismatch',
                'contradictory': 'contradictory primary message content', 'provider_error': 'provider error thread_not_found'}


@_pytest.mark.parametrize('defect', ['missing_root', 'channel_mismatch', 'contradictory', 'provider_error'])
def test_one_bad_slack_thread_is_skipped_with_an_error_and_siblings_survive(settings, data_dir, tmp_path, defect):
    """Source slack_daily_followups: a per-thread failure is logged and the other threads continue."""
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    def dispatch(tool, args):
        if tool == 'reader':
            return envelope(args, [
                {'channel_id': 'C1', 'ts': ts_in(args, 100), 'thread_ts': ts_in(args, 90000), 'text': 'reply in a broken thread'},
                {'channel_id': 'C2', 'ts': ts_in(args, 3600), 'text': 'Separate ask in quiet channel'}])
        request = args['request']
        if request['operation'] == 'replies':
            root = {'ts': request['ts'], 'text': 'root'}
            reply = {'ts': ts_in(args, 100), 'text': 'reply in a broken thread'}
            if defect == 'provider_error':
                # Slack's answer for a thread that no longer exists (source :364-367 skips it).
                return json.dumps({'ok': False, 'error': 'thread_not_found'})
            if defect == 'missing_root':
                return envelope(args, [reply])
            if defect == 'channel_mismatch':
                return envelope(args, [{**root, 'channel_id': 'C9'}, reply])
            return envelope(args, [root, {**reply, 'text': 'entirely different words'}])
        return envelope(args, [{'ts': ts_in(args, 3600), 'channel_id': 'C2', 'text': 'Separate ask in quiet channel'}])
    ctx.dispatch_tool = dispatch
    run = integration.start('work', session_id='parent')['run_id']
    receipt = integration.collect(run, 'feed', session_id='parent')
    assert receipt['status'] == 'partial', receipt
    assert 'skipped' in receipt['error'] and 'C1' in receipt['error']
    backlog = integration.store.source_state('work', 'feed')['backlog']
    assert [b['source_ids'][0].split(':')[2] for b in backlog] == ['C2']
    assert backlog[0]['candidate']['title'] == 'Separate ask in quiet channel'
    assert integration.store.source_state('work', 'feed').get('watermark') == receipt['end']
    text = _close_run(integration, run)['text']
    assert 'Coverage: feed: partial' in text and 'degraded' in text
    assert 'No new follow-ups found.' not in text
    # The digest names the actual skip reason, not a generic read failure.
    coverage = [l for l in text.splitlines() if l.startswith('Coverage: feed:')]
    assert coverage == ['Coverage: feed: partial: skipped thread: ' + _SKIP_REASON[defect]]


@_pytest.mark.parametrize('violation', ['account_mismatch', 'nonstructured'])
def test_reader_contract_violation_in_one_thread_still_fails_the_source(settings, data_dir, tmp_path, violation):
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    def dispatch(tool, args):
        if tool == 'reader':
            return envelope(args, [
                {'channel_id': 'C1', 'ts': ts_in(args, 100), 'thread_ts': ts_in(args, 90000), 'text': 'reply in thread'},
                {'channel_id': 'C2', 'ts': ts_in(args, 3600), 'text': 'Separate ask in quiet channel'}])
        request = args['request']
        if request['operation'] == 'replies':
            if violation == 'nonstructured':
                return json.dumps(['not', 'an', 'envelope'])
            return {**envelope(args, [{'ts': request['ts'], 'text': 'root'}]), 'account_key': 'another-account'}
        return envelope(args, [{'ts': ts_in(args, 3600), 'channel_id': 'C2', 'text': 'Separate ask in quiet channel'}])
    ctx.dispatch_tool = dispatch
    run = integration.start('work', session_id='parent')['run_id']
    receipt = integration.collect(run, 'feed', session_id='parent')
    assert receipt['status'] == 'failed' and 'skipped' not in receipt['error']
    state = integration.store.source_state('work', 'feed')
    assert state.get('watermark') is None and state['backlog'] == []


def test_overlapping_block_conflict_skips_only_that_group_and_leaves_the_sibling_block_unchanged(settings, data_dir, tmp_path):
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    def dispatch(tool, args):
        root = ts_in(args, 7200)
        if tool == 'reader':
            return envelope(args, [
                {'channel_id': 'C1', 'ts': ts_in(args, 100), 'thread_ts': root, 'text': 'reply asking for the budget'},
                {'channel_id': 'C1', 'ts': root, 'text': 'edited root words'}])
        request = args['request']
        if request['operation'] == 'replies':
            return envelope(args, [{'ts': root, 'text': 'original root words'}, {'ts': ts_in(args, 100), 'text': 'reply asking for the budget'}])
        if request['operation'] == 'before':
            return envelope(args, [{'ts': root, 'channel_id': 'C1', 'text': 'edited root words'}])
        return envelope(args, [])
    ctx.dispatch_tool = dispatch
    run = integration.start('work', session_id='parent')['run_id']
    receipt = integration.collect(run, 'feed', session_id='parent')
    assert receipt['status'] == 'partial' and 'skipped: contradictory overlapping block content' in receipt['error']
    backlog = integration.store.source_state('work', 'feed')['backlog']
    assert len(backlog) == 1
    # The skipped group's seed never half-merges into the retained thread block.
    assert backlog[0]['source_ids'] == [backlog[0]['candidate']['source_ids'][0]] and len(backlog[0]['candidate']['source_ids']) == 1
    assert backlog[0]['candidate']['title'] == 'reply asking for the budget'


def test_legacy_mail_source_without_admission_needs_input_at_start(settings, data_dir, tmp_path):
    import pytest
    from alchemy_task.core.discovery_identity import UserError
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    sources = ctx.state.get('discovery_sources')
    sources['work']['feed']['kind'] = 'mail'
    sources['work']['feed'].pop('sender_domains', None)
    ctx.state.set('discovery_sources', sources)
    runs = integration.store.state_root / 'runs'
    before = sorted(runs.glob('*')) if runs.exists() else []
    with pytest.raises(UserError, match='needs_input.*sender_domains'):
        integration.start('work', session_id='parent')
    assert (sorted(runs.glob('*')) if runs.exists() else []) == before
    sources['work']['feed']['admit_all'] = True
    ctx.state.set('discovery_sources', sources)
    assert integration.start('work', session_id='parent')['run_id']
