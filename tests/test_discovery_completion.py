"""Normal failure/restart acceptance for the complete saved workflow."""
import copy
from types import SimpleNamespace
import pytest
from test_discovery_integration import service, configure
from alchemy_task.core.discovery_identity import UserError


def test_source_change_reconciles_existing_job_reader_toolsets(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    streams = ctx.state.get('streams')
    streams['work']['job_id'] = 'job-one'
    ctx.state.set('streams', streams)
    ctx.cron['job-one'] = {'name': 'alchemy-task: discovery work', 'deliver': 'origin', 'enabled_toolsets': ['stale-reader']}
    config = configure(integration)
    config['toolsets'] = ['approved-reader']
    integration.configure('work', config, user_approved=True)
    job = ctx.cron['job-one']
    assert {'alchemy-task-discovery', 'alchemy-task-discovery-child', 'approved-reader'} <= set(job['enabled_toolsets'])
    assert 'stale-reader' not in job['enabled_toolsets']
    assert job['deliver'] == 'origin'
    assert integration._stream('work')['job_id'] == 'job-one'


def test_scheduled_new_session_adopts_same_saved_config_window(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    streams = ctx.state.get('streams')
    streams['work'].update(job_id='job-one', job_binding={'job_id': 'job-one', 'origin_session': 'parent', 'profile': 'test', 'verified': True})
    ctx.state.set('streams', streams)
    ctx.profile_name = 'test'
    ctx.current_cron_execution = lambda: None
    started = integration.start('work', session_id='parent')
    saved = copy.deepcopy(integration.store.get_run(started['run_id']))
    with pytest.raises(UserError):
        integration.start('work', session_id='new-session')
    ctx.current_cron_execution = lambda: dict(job_id='job-other', execution_id='fire-one', profile='test', scheduled_instant='2030-01-01T00:00:00Z', source='builtin')
    with pytest.raises(UserError):
        integration.start('work', session_id='new-session')
    ctx.current_cron_execution = lambda: dict(job_id='job-one', execution_id='fire-one', profile='test', scheduled_instant='2030-01-01T00:00:00Z', source='builtin')
    resumed = integration.start('work', session_id='new-session')
    assert resumed['run_id'] == started['run_id']
    assert integration.store.get_run(started['run_id'])['config'] == saved['config']
    assert integration.runner._parent(started['run_id'], 'new-session')
    assert integration.backend(started['run_id'], session_id='new-session')['recovery']['adoptions'][-1]['execution']['execution_id'] == 'fire-one'
    ctx.current_cron_execution = lambda: None
    with pytest.raises(UserError):
        integration.start('work', session_id='third-session')
