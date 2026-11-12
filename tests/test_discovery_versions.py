"""Source items are versioned by their own messages; researched threads come back only for newer
messages; attested sources keep a read-up-to marker; follow-up runs skip collection."""
import datetime as dt

from alchemy_task.core import discovery_state as m
from test_discovery_integration import configure, service
from test_discovery_any_chat import bound  # noqa: F401
from test_discovery_follow_up_run import _finished_with_deferred, _setup

THREAD = ['slack:acct:C1:100.1']


def _msg(i, hour):
    return {'id': f'm{i}', 'author': 'Ana', 'time': f'2030-01-01T{hour:02d}:00:00+00:00', 'text': f'message {i}'}


def _entry(messages, revision='agent-1', **extra):
    item = {'title': 'Launch plan', 'source_ids': THREAD, 'source_revision': revision, 'messages': messages, **extra}
    return {'source_ids': THREAD, 'source_revision': revision, 'candidate': item}


def test_cosmetic_envelope_change_does_not_requeue_the_same_thread(tmp_path):
    store = m.DiscoveryStore(tmp_path / 'discovery')
    store.enqueue_backlog('work', 'chat', [_entry([_msg(1, 9), _msg(2, 10)])])
    # Same messages, new agent revision and reordered list: same version, nothing new.
    state = store.enqueue_backlog('work', 'chat', [_entry([_msg(2, 10), _msg(1, 9)], revision='agent-2', url='https://x')])
    assert len(state['backlog']) == 1
    entry = state['backlog'][0]
    assert entry['source_revision'].startswith('content:') and entry['agent_source_revision'] == 'agent-1'
    assert entry['message_ids'] == ['m1', 'm2'] and entry['latest_message'].startswith('2030-01-01T10:00')
    # A message without an id is named by its author, time and text.
    no_id = m.content_version({'messages': [{'author': 'Ana', 'time': '1893488400.5', 'text': 'hi'}]})
    assert no_id['message_ids'][0].startswith('h:') and no_id['latest'] is not None


def test_researched_thread_requeues_only_for_newer_messages(tmp_path):
    store = m.DiscoveryStore(tmp_path / 'discovery')
    bid = store.enqueue_backlog('work', 'chat', [_entry([_msg(2, 10), _msg(3, 11)])])['backlog'][0]['backlog_id']
    store.update_backlog('work', 'chat', bid, status='accepted', lineage={'run_id': 'run-1', 'candidate_id': 'c'})
    # Older context only: the saved text is updated for audit, nothing is queued.
    state = store.enqueue_backlog('work', 'chat', [_entry([_msg(1, 9), _msg(2, 10), _msg(3, 11)], revision='agent-2')])
    assert [x['status'] for x in state['backlog']] == ['accepted']
    assert len(state['backlog'][0]['candidate']['messages']) == 3 and state['backlog'][0]['audit_updates']
    # A newer message queues one new version.
    state = store.enqueue_backlog('work', 'chat', [_entry([_msg(1, 9), _msg(2, 10), _msg(3, 11), _msg(4, 12)])])
    assert [x['status'] for x in state['backlog']] == ['accepted', 'queued']
    # Another newer message replaces the pending version in place (same backlog id), no second entry.
    queued_id = state['backlog'][1]['backlog_id']
    state = store.enqueue_backlog('work', 'chat', [_entry([_msg(i, 8 + i) for i in range(1, 6)])])
    assert [x['status'] for x in state['backlog']] == ['accepted', 'queued']
    assert state['backlog'][1]['backlog_id'] == queued_id and 'm5' in state['backlog'][1]['message_ids']
    assert len(state['backlog'][1]['candidate']['messages']) == 5


def test_attested_read_moves_its_marker_and_the_next_window_starts_there(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    first = integration.start('work', session_id='parent')
    window = first['windows']['feed']
    span = dt.datetime.fromisoformat(window['end']) - dt.datetime.fromisoformat(window['start'])
    assert span == dt.timedelta(days=1)  # first run: the last day
    integration.collect(first['run_id'], 'feed', session_id='parent', envelope={**window, 'status': 'complete', 'account_key': 'account', 'items': []})
    state = integration.store.source_state(integration.store.get_run(first['run_id'])['stream'], 'feed')
    assert state['attested_watermark'] == window['end'] and state.get('watermark') is None  # never verified coverage
    second = integration.start('work', session_id='parent', _distinct=True)['windows']['feed']
    assert dt.datetime.fromisoformat(second['start']) == dt.datetime.fromisoformat(window['end']) - dt.timedelta(hours=2)
    # A read the agent reports as unfinished leaves the marker where it was.
    store = integration.store
    store.record_coverage('s', 'k', {'status': 'partial', 'verification': 'agent_attested', 'end': '2030-01-02T00:00:00+00:00', 'pagination_exhausted': False})
    assert store.source_state('s', 'k').get('attested_watermark') is None
    store.record_coverage('s', 'k', {'status': 'partial', 'verification': 'agent_attested', 'end': '2030-01-02T00:00:00+00:00', 'pagination_exhausted': True})
    assert store.source_state('s', 'k')['attested_watermark'] == '2030-01-02T00:00:00+00:00'


def test_follow_up_run_skips_collection_and_freezes_the_queued_items(settings, data_dir, tmp_path):
    integration, ctx, creates, prepared = _setup(settings, data_dir, tmp_path)
    run = _finished_with_deferred(integration, ctx, count=2)
    integration.finalize(run, session_id='parent')
    assert ctx.state.get('discovery_follow_ups')['work']['job_ids'] == ['follow-1']
    fire = dict(execution_id='fire-1', profile='test', scheduled_instant='2030-01-01T00:05:00Z', source='builtin')
    ctx.current_cron_execution = lambda: {**fire, 'job_id': 'job-one'}
    assert 'skip_collection' not in integration.start('work', session_id='s1', _distinct=True)  # the stream's own job collects
    ctx.current_cron_execution = lambda: {**fire, 'job_id': 'follow-1'}
    started = integration.start('work', session_id='s2', _distinct=True)
    assert started['skip_collection'] is True and 'discovery_context' in started['next_action'] and '2 item' in started['next_action']
    assert integration.freeze(started['run_id'], session_id='s2')['index_revision']
    ledger = integration.store.get_run(started['run_id'])
    assert len(ledger['candidates']) == 2
    receipt = integration._collection_receipts(ledger)['feed']
    assert receipt['skipped'] == 'follow-up run' and receipt['verification'] == 'skipped'


def test_queued_reason_names_the_daily_cap_or_the_time_box(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    assert integration._queued_reason(run, {}, 0) == ''
    assert integration._queued_reason(run, {}, 2) == ''
    with integration.runner._state(run) as state:
        state['budget_deferred'] = ['a'] ; state['time_deferred'] = ['a']
    assert integration._queued_reason(run, {}, 2) == 'time'
    with integration.runner._state(run) as state:
        state['budget_deferred'] = ['a', 'b']
    assert integration._queued_reason(run, {}, 2) == 'daily_cap'
