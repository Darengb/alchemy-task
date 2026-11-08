"""Normal failure/restart acceptance for the complete saved workflow."""
import copy
from types import SimpleNamespace
import pytest
from test_discovery_integration import service, configure
from alchemy_task.core.discovery_identity import UserError


def test_generic_item_mapping_retains_full_actual_reader_evidence(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    config['binding']['response_fields']['items'] = 'data.issues'
    config['binding']['item_fields'] = {'title': 'fields.summary', 'source_revision': 'updated', 'body': 'fields.description'}
    config['binding']['item_identity'] = {'type': {'literal': 'source'}, 'source_key': {'config': 'source_key'}, 'account_key': {'config': 'account_key'}, 'object_kind': {'literal': 'issue'}, 'object_id': {'path': 'id'}}
    config['binding']['capability'] = {'tool': 'describe_reader', 'arguments': {'tool': 'reader'}}
    integration.configure('work', config, user_approved=True)
    run = integration.start('work', session_id='parent')['run_id']
    calls = []
    def dispatch(tool, args):
        calls.append(tool)
        if tool == 'describe_reader': return {'name': 'reader', 'available': True, 'supports': ['issues', 'full-body']}
        return {'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'], 'data': {'issues': [{'id': 'issue-7', 'updated': 'r7', 'fields': {'summary': 'Resolve issue', 'description': 'Full text on final page'}, 'arbitrary_provider_detail': {'owner': 'user-4'}}]}, 'next_cursor': None, 'pagination_exhausted': True}
    ctx.dispatch_tool = dispatch
    receipt = integration.collect(run, 'feed', session_id='parent')
    assert receipt['status'] == 'complete', receipt
    item = integration.store.source_state('work', 'feed')['backlog'][0]['candidate']
    assert item['source_ids'] == ['source:feed:account:issue:issue-7']
    assert item['reader_item']['arbitrary_provider_detail']['owner'] == 'user-4'
    assert item['body'] == 'Full text on final page'
    assert calls == ['describe_reader', 'reader']
    evidence = receipt['pages'][0]['evidence']
    from alchemy_task.core.discovery_state import read_json
    raw = read_json(integration.store.state_root / evidence['path'])
    assert raw['capability']['supports'] == ['issues', 'full-body']
    assert raw['response']['data']['issues'][0]['updated'] == 'r7'


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
