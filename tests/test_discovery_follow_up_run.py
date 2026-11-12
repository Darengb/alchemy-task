"""A run that leaves research queued records one pending follow-up run of the same stream (at most two a day),
tells the digest, and the stream's own job runs it at its next 30-minute tick. No job is ever created."""
from test_discovery_integration import configure, service
from test_discovery_any_chat import bound
from test_discovery_owner_change import HostPool, TickClock

from alchemy_task.core import precheck


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
    calls, prepared = [], []

    def dispatch(name, args):
        calls.append((name, args))
        raise AssertionError('a follow-up never reaches cronjob_manage: %r' % (args,))
    ctx.dispatch_tool = dispatch
    real = integration.digest.prepare

    def prepare(*a, **kw):
        prepared.append({'queued_count': kw.get('queued_count'), 'follow_up_started': kw.get('follow_up_started')})
        return real(*a, **kw)
    integration.digest.prepare = prepare
    return integration, ctx, calls, prepared


def _wake(ctx, now=None):
    return precheck.discovery_wake(lambda key: ctx.state.get(key), 'work', now)


def _slot_already_ran(ctx):
    slot = precheck.latest_slot('0 18 * * *', 'America/New_York', lookback=8 * 24 * 60)
    ctx.state.set('discovery_slots', {'work': {'done': slot.isoformat(), 'schedule': '0 18 * * *'}})


def test_deferred_research_records_one_pending_follow_up_and_tells_the_digest(settings, data_dir, tmp_path):
    integration, ctx, calls, prepared = _setup(settings, data_dir, tmp_path)
    _slot_already_ran(ctx)
    run = _finished_with_deferred(integration, ctx)
    assert ctx.state.get('discovery_follow_ups')['work']['active']['run_id'] == run
    assert _wake(ctx) == {'wakeAgent': False}  # a run in progress: no follow-up wake
    integration.finalize(run, session_id='parent')
    integration.finalize(run, session_id='parent')  # a repeated finalize never records a second one
    assert calls == []
    record = ctx.state.get('discovery_follow_ups')['work']
    assert record['count'] == 1 and record['pending']['run_id'] == run and 'active' not in record
    assert prepared == [{'queued_count': 3, 'follow_up_started': True}]
    assert _wake(ctx)['reason'] == 'follow_up'


def test_daily_cap_stops_a_third_follow_up_and_nothing_queued_starts_none(settings, data_dir, tmp_path):
    integration, ctx, calls, prepared = _setup(settings, data_dir, tmp_path)
    for _ in range(3):
        integration.finalize(_finished_with_deferred(integration, ctx), session_id='parent')
    assert calls == []
    assert [p['follow_up_started'] for p in prepared] == [True, True, False]
    assert prepared[-1]['queued_count'] > 0
    # A new local day resets the count.
    record = ctx.state.get('discovery_follow_ups')
    record['work']['date'] = '2000-01-01'
    ctx.state.set('discovery_follow_ups', record)
    integration.finalize(_finished_with_deferred(integration, ctx), session_id='parent')
    assert ctx.state.get('discovery_follow_ups')['work']['count'] == 1 and prepared[-1]['follow_up_started'] is True


def test_the_streams_own_job_runs_the_follow_up_but_an_unrelated_job_may_not(settings, data_dir, tmp_path):
    integration, ctx, calls, prepared = _setup(settings, data_dir, tmp_path)
    run = _finished_with_deferred(integration, ctx)
    integration.finalize(run, session_id='parent')
    _slot_already_ran(ctx)  # only the follow-up is due
    assert _wake(ctx)['reason'] == 'follow_up'
    fire = dict(execution_id='fire-1', profile='test', scheduled_instant='2030-01-01T00:30:00Z', source='builtin')
    ctx.current_cron_execution = lambda: {**fire, 'job_id': 'job-unrelated'}
    stream = integration._stream('work')
    assert integration._scheduled_identity(stream) is None
    ctx.current_cron_execution = lambda: {**fire, 'job_id': 'job-one'}
    assert integration._scheduled_identity(stream)['job_id'] == 'job-one'
    started = integration.start('work', session_id='follow-up-session')
    assert not started['resumed'] and started['run_id'] != run and started.get('follow_up_run') is True
    # Consumed: the next tick does not wake for it again while nothing else is due.
    assert 'pending' not in ctx.state.get('discovery_follow_ups')['work']
    assert _wake(ctx) == {'wakeAgent': False}
    # The queued items from the earlier run are selected first in the follow-up.
    integration.collect(started['run_id'], 'feed', session_id='follow-up-session', envelope={
        **integration.store.get_run(started['run_id'])['config']['windows']['feed'], 'status': 'complete', 'account_key': 'account', 'items': []})
    integration.freeze(started['run_id'], session_id='follow-up-session')
    assert len(integration.store.get_run(started['run_id'])['candidates']) == 3
    assert calls == []
