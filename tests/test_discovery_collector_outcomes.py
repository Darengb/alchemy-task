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
    assert receipt['covered_intervals'] == []
    backlog = {b['source_ids'][0].split(':')[2]: b for b in integration.store.source_state('work', 'feed')['backlog']}
    assert set(backlog) == {'C1', 'C2'}
    assert backlog['C1']['candidate'].get('partial') is True
    assert 'partial' not in backlog['C2']['candidate']
    assert integration.store.source_state('work', 'feed').get('watermark') is None
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
