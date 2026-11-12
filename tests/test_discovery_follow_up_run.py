"""A run that leaves research queued schedules one follow-up run of the same stream (at most two a day),
tells the digest, and the follow-up job may start the stream like the stream's own job."""
import json

from test_discovery_integration import configure, service
from test_discovery_any_chat import bound
from test_discovery_owner_change import HostPool, TickClock


def _finished_with_deferred(integration, ctx, count=3):
    """A production run that defers every item (finish_now before anything starts), joined."""
    run = integration.start('work', session_id='parent')['run_id']
    window = integration.store.get_run(run)['config']['windows']['feed']
    integration.collect(run, 'feed', session_id='parent', envelope={**window, 'status': 'complete', 'account_key': 'account', 'items': [
        {'title': f'Review release {i}', 'source_ids': [f'source:feed:account:issue:r{run[-6:]}{i}'], 'source_revision': 'v1',
         'body': f'Please review release {i}.'} for i in range(count)]})
    integration.freeze(run, session_id='parent')
    clock = TickClock()
    pool = HostPool(clock, integration.store, run, duration=400, parent='parent')
    ctx.subagent_lifecycle = pool
    pool.runner, clock.pool = integration.runner, pool
    integration.runner.clock = clock
    report = integration.runner.run(run, session_id='parent', finish_now=True)
    # Earlier runs' deferred items are selected again, so later runs defer more than their own new items.
    assert report['status'] == 'complete' and report['counts']['deferred'] >= count
    assert integration.runner.join(run, session_id='parent')['joined']
    return run


def _setup(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    bound(integration, ctx)
    creates, prepared = [], []

    def dispatch(name, args):
        assert name == 'cronjob_manage' and args['action'] == 'create'
        creates.append(args)
        return json.dumps({'success': True, 'job_id': f'follow-{len(creates)}'})
    ctx.dispatch_tool = dispatch
    real = integration.digest.prepare

    def prepare(*a, **kw):
        prepared.append({'queued_count': kw.get('queued_count'), 'follow_up_started': kw.get('follow_up_started')})
        return real(*a, **kw)
    integration.digest.prepare = prepare
    return integration, ctx, creates, prepared


def test_deferred_research_schedules_exactly_one_follow_up_and_tells_the_digest(settings, data_dir, tmp_path):
    integration, ctx, creates, prepared = _setup(settings, data_dir, tmp_path)
    run = _finished_with_deferred(integration, ctx)
    integration.finalize(run, session_id='parent')
    integration.finalize(run, session_id='parent')  # a repeated finalize never schedules a second one
    assert len(creates) == 1
    job = creates[0]
    assert job['name'] == 'alchemy-task: discovery work follow-up' and job['repeat'] == 1
    assert job['schedule'].startswith('in ') and job['skills'] == ['alchemy-task:discovery']
    assert 'Run the Alchemy Task discovery stream "work"' in job['prompt'] and job['deliver'] == 'origin'
    assert prepared == [{'queued_count': 3, 'follow_up_started': True}]
    assert ctx.state.get('discovery_follow_ups')['work']['job_ids'] == ['follow-1']


def test_daily_cap_stops_a_third_follow_up_and_nothing_queued_starts_none(settings, data_dir, tmp_path):
    integration, ctx, creates, prepared = _setup(settings, data_dir, tmp_path)
    for _ in range(3):
        integration.finalize(_finished_with_deferred(integration, ctx), session_id='parent')
    assert len(creates) == 2
    assert [p['follow_up_started'] for p in prepared] == [True, True, False]
    assert prepared[-1]['queued_count'] > 0
    # A new local day resets the count.
    record = ctx.state.get('discovery_follow_ups')
    record['work']['date'] = '2000-01-01'
    ctx.state.set('discovery_follow_ups', record)
    integration.finalize(_finished_with_deferred(integration, ctx), session_id='parent')
    assert len(creates) == 3


def test_follow_up_job_may_start_the_stream_but_an_unrelated_job_may_not(settings, data_dir, tmp_path):
    integration, ctx, creates, prepared = _setup(settings, data_dir, tmp_path)
    run = _finished_with_deferred(integration, ctx)
    integration.finalize(run, session_id='parent')
    fire = dict(execution_id='fire-1', profile='test', scheduled_instant='2030-01-01T00:05:00Z', source='builtin')
    ctx.current_cron_execution = lambda: {**fire, 'job_id': 'job-unrelated'}
    stream = integration._stream('work')
    assert integration._scheduled_identity(stream) is None
    ctx.current_cron_execution = lambda: {**fire, 'job_id': 'follow-1'}
    assert integration._scheduled_identity(stream)['job_id'] == 'follow-1'
    started = integration.start('work', session_id='follow-up-session')
    assert not started['resumed'] and started['run_id'] != run
    # The queued items from the earlier run are selected first in the follow-up.
    integration.collect(started['run_id'], 'feed', session_id='follow-up-session', envelope={
        **integration.store.get_run(started['run_id'])['config']['windows']['feed'], 'status': 'complete', 'account_key': 'account', 'items': []})
    integration.freeze(started['run_id'], session_id='follow-up-session')
    assert len(integration.store.get_run(started['run_id'])['candidates']) == 3
