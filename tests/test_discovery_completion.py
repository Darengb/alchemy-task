"""Normal failure/restart acceptance for the complete saved workflow."""
import copy
from types import SimpleNamespace
import pytest
from test_discovery_integration import service, configure
from alchemy_task.core.discovery_identity import UserError


def test_enabled_phone_is_queued_and_only_actual_target_readback_completes(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task import ios_sync
    from alchemy_task.core import reminders as rm
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    settings.git_transport = 'none'
    ios_sync.save(rt, {'config': {'enabled': True, 'device_id': 'phone-one', 'list_id': 'list-one', 'areas': ['work']}, 'mappings': {}, 'ops': {}, 'conflicts': {}, 'reads': {}, 'notes': {}})
    plan = conversion.prepare(run, wid, choice='create', reason='User chose task.', user_approved=True, area='work', undated=True)
    receipt = conversion.deliver_git(run, wid)
    assert receipt['state'] == 'phone_pending'
    assert receipt['phone']['state'] == 'queued'
    doc = rt.store().resolve(plan['task_id'])
    st = ios_sync.load(rt)
    notes = rm.compose_notes(doc.fm, doc.body, doc.task_id)
    st['mappings'][doc.task_id] = {'reminder_id': 'rem-one', 'list_id': 'list-one', 'device_id': 'phone-one', 'base': rm.local_projection(doc.fm), 'notes_sent': notes}
    ios_sync.save(rt, st)
    assert conversion.deliver_git(run, wid)['phone']['state'] != 'verified'
    st = ios_sync.load(rt)
    st['mappings'][doc.task_id]['verified_readback'] = {'id': 'rem-one', 'list_id': 'list-one', 'device_id': 'phone-one', 'projection': rm.local_projection(doc.fm), 'notes': notes}
    ios_sync.save(rt, st)
    verified = conversion.deliver_git(run, wid)
    assert verified['state'] == 'complete' and verified['phone']['state'] == 'verified'
    assert verified['phone']['reminder_id'] == 'rem-one'


def test_preflight_checks_entire_batch_before_any_local_write(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task.core import taskfile as tf
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    plan = conversion.prepare(run, wid, choice='create', reason='User chose task.', user_approved=True, area='work', undated=True)
    path = rt.store().root / plan['path']
    path.write_text('foreign user edit')
    with pytest.raises((UserError, tf.ConcurrentEditError)):
        conversion.preflight([(run, wid)])
    assert path.read_text() == 'foreign user edit'


def test_malformed_other_dossier_blocks_conversion_without_correspondence_loss(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task.core import taskfile as tf
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    doc = rt.store().create(title='Existing', area='work', undated=True, research=False, notes='Correspondence retained. slack:T1:C1:171.1:171.2\n<!-- discovery-dossier:start unrelated -->\nold partial dossier')
    before = doc.path.read_bytes()
    with pytest.raises(UserError, match='dossier'):
        conversion.prepare(run, wid, choice='auto', reason='Verified useful delta.', useful_delta=True, target_task_id=doc.task_id, expected_revision=tf.content_hash(before))
    assert doc.path.read_bytes() == before


def test_explicit_unwritten_plan_revision_and_cancellation_preserve_identity(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task.core.discovery_dossiers import content_revision
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    plan = conversion.prepare(run, wid, choice='create', reason='User chose task.', user_approved=True, area='work', undated=True)
    revised = conversion.revise(run, wid, expected_plan_revision=content_revision(plan), edits={'title': 'User corrected scope', 'due': '2030-01-04', 'undated': False}, reason='User corrected pending task before writing.')
    assert revised['task_id'] == plan['task_id']
    assert revised['request']['title'] == 'User corrected scope'
    assert revised['history'][0]['postimage_sha256'] == plan['postimage_sha256']
    with pytest.raises(UserError):
        conversion.revise(run, wid, expected_plan_revision=content_revision(plan), edits={'title': 'stale'}, reason='Stale update.')
    conversion.cancel(run, wid, expected_plan_revision=content_revision(revised), reason='User no longer wants task.')
    with pytest.raises(UserError, match='cancel'):
        conversion.apply(run, wid)
    assert not (rt.store().root / revised['path']).exists()
    assert not (rt.store().root / plan['path']).exists()


def test_scheduled_delivery_requires_origin_approval_and_disables_scheduler_copy(settings, data_dir, tmp_path):
    import json
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    streams = ctx.state.get('streams')
    streams['work'].update(job_id='job-one', job_binding={'job_id': 'job-one', 'origin_session': 'parent', 'profile': 'test', 'verified': True})
    ctx.state.set('streams', streams)
    ctx.cron['job-one'] = {'name': 'alchemy-task: discovery work', 'deliver': 'origin'}
    binding = {'origin_session': 'parent', 'target': 'chat-one', 'send_tool': 'sender', 'read_tool': 'reader', 'send_fields': {'target': 'target', 'text': 'text'}, 'send_id_path': 'id', 'read_fields': {'id': 'message_id'}, 'read_response': {'message_id': 'id', 'target': 'target', 'text': 'text'}, 'scheduled_approved': True}
    integration.configure_delivery('work', binding, user_approved=True)
    assert ctx.cron['job-one']['deliver'] == 'local'
    digest = integration.digest.prepare('scheduled-digest', stream='work', day='2030-01-01', origin={'session_id': 'parent'}, items=[])
    with pytest.raises(UserError): integration.deliver('scheduled-digest', session_id='claimed-scheduler')
    ctx.current_cron_execution = lambda: {'job_id': 'job-one', 'execution_id': 'fire-one', 'profile': 'test', 'scheduled_instant': '2030-01-01T00:00:00Z'}
    original = ctx.dispatch_tool
    sends = []
    def dispatch(name, args):
        if name == 'cronjob_manage': return original(name, args)
        if name == 'sender': sends.append(args); return {'id': 'actual-1'}
        return {'id': 'actual-1', 'target': 'chat-one', 'text': digest['text']}
    ctx.dispatch_tool = dispatch
    assert integration.deliver('scheduled-digest', session_id='actual-scheduler')['state'] == 'delivered'
    assert integration.deliver('scheduled-digest', session_id='actual-scheduler')['state'] == 'delivered'
    assert len(sends) == 1
    assert integration.digest.delivery('scheduled-digest')['readback']['target'] == 'chat-one'


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
