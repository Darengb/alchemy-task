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
