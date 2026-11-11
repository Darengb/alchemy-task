"""Authority follows who acts, not where: any chat of the installing profile may start, resume,
recover, read and prepare a discovery run. Research children and unrelated
scheduled jobs are still refused. Digests still go to the stream's saved destination."""
import pytest

from alchemy_task.core.discovery_identity import UserError
from test_discovery_integration import configure, service
from test_discovery_owner_change import HostPool, TickClock, accept_awaiting, drive
from test_discovery_short_calls import charged_units


def bound(integration, ctx):
    streams = ctx.state.get('streams')
    streams['work'].update(schedule='0 18 * * *', timezone='America/New_York', job_id='job-one',
                           job_binding={'job_id': 'job-one', 'origin_session': 'parent', 'profile': 'test', 'verified': True})
    ctx.state.set('streams', streams)
    ctx.profile_name = 'test'


def test_start_from_a_different_chat_keeps_the_saved_destination(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    started = integration.start('work', session_id='other-chat')
    run = integration.store.get_run(started['run_id'])
    assert run['origin']['session_id'] == 'other-chat'
    assert run['origin']['stream_origin_session'] == 'parent'  # delivery stays with the saved origin
    assert integration.backend(started['run_id'], session_id='yet-another-chat')['run_id'] == started['run_id']
    listed = integration.backend(session_id='yet-another-chat')['runs']
    assert [r['run_id'] for r in listed] == [started['run_id']]


def test_third_chat_resumes_and_recovers_without_relaunch_or_double_charge(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    window = integration.store.get_run(run)['config']['windows']['feed']
    integration.collect(run, 'feed', session_id='parent', envelope={**window, 'status': 'partial', 'account_key': 'account', 'items': [
        {'title': f'Review release {i}', 'source_ids': [f'source:feed:account:issue:i{i}'], 'source_revision': 'v1', 'body': f'Please review release {i}.'} for i in range(4)]})
    integration.freeze(run, session_id='parent')
    clock = TickClock()
    pool = HostPool(clock, integration.store, run, duration=400, parent='parent')
    ctx.subagent_lifecycle = pool
    pool.runner, clock.pool = integration.runner, pool
    integration.runner.clock = clock
    assert integration.runner.run(run, session_id='parent')['counts']['running'] == 3
    # The user comes back from a third chat; the real integration authorizer decides.
    pool.active = 'third-chat'
    resumed = integration.start('work', session_id='third-chat')
    assert resumed['resumed'] and resumed['run_id'] == run
    assert integration.runner._parent(run, 'third-chat')
    adoptions = integration.backend(run, session_id='third-chat')['recovery']['adoptions']
    assert adoptions[-1]['from_session'] == 'parent' and adoptions[-1]['to_session'] == 'third-chat'
    drive(integration.runner, integration.store, run, 'third-chat')
    joined = integration.runner.join(run, session_id='third-chat')
    assert joined['joined'] and len(joined['accepted']) == 4
    assert len(pool.requests) == 4 and charged_units(integration.store) == 4  # no relaunch, no extra charge
    assert integration.store.get_run(run)['origin']['stream_origin_session'] == 'parent'


def test_manual_run_now_resumes_a_run_a_chat_started(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    bound(integration, ctx)
    started = integration.start('work', session_id='some-chat')
    ctx.current_cron_execution = lambda: dict(job_id='job-one', execution_id='fire-now', profile='test',
                                              scheduled_instant=None, started_at='2030-01-01T02:48:32Z', source='direct')
    resumed = integration.start('work', session_id='cron-session')
    assert resumed['resumed'] and resumed['run_id'] == started['run_id']
    assert integration.runner._parent(started['run_id'], 'cron-session')


def test_research_child_is_refused_everywhere(settings, data_dir, tmp_path, monkeypatch):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    monkeypatch.setattr(integration.runner, '_child_for', lambda session_id='', task_id='': (run, None) if session_id == 'child' else None)
    with pytest.raises(UserError):
        integration.start('work', session_id='child')
    assert integration.runner._parent(run, 'parent')  # the child did not adopt the run
    assert not integration._authorize_recovery(run, 'parent', 'child')
    with pytest.raises(UserError):
        integration.backend(run, session_id='child')
    assert integration.backend(session_id='child')['runs'] == []
    with pytest.raises(UserError):
        integration.authorize_approval('child')


def test_unrelated_scheduled_job_still_cannot_start_or_adopt(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    bound(integration, ctx)
    run = integration.start('work', session_id='parent')['run_id']
    ctx.current_cron_execution = lambda: dict(job_id='job-other', execution_id='fire-one', profile='test',
                                              scheduled_instant='2030-01-01T00:00:00Z', source='builtin')
    with pytest.raises(UserError):
        integration.start('work', session_id='other-cron')
    assert not integration._authorize_recovery(run, 'parent', 'other-cron')
    assert integration.runner._parent(run, 'parent')


def test_a_session_not_yet_in_the_store_can_still_act_and_read(settings, data_dir, tmp_path):
    from hermes_state import SessionDB
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    integration.home.mkdir()
    db = SessionDB(db_path=integration.home / 'state.db')
    try:
        db.create_session('parent', source='telegram')
    finally:
        db.close()
    configure(integration)
    started = integration.start('work', session_id='brand-new-chat')
    assert integration.start('work', session_id='parent')['run_id'] == started['run_id']
    assert [r['run_id'] for r in integration.backend(session_id='brand-new-chat')['runs']] == [started['run_id']]


def test_any_chat_may_prepare_native_delivery_which_stays_with_the_origin(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    integration.digest.prepare('d1', stream='work', day='2030-01-01', origin={'session_id': 'parent'}, items=[])
    status = integration.deliver('d1', session_id='other-chat')
    assert status == integration.delivery_status('d1')
    assert integration.digest.get('d1')['origin']['session_id'] == 'parent'
