"""One delivery owner: ordinary native cron versus optional verified sender."""
import json
import pytest
from alchemy_task import discovery
from alchemy_task.discovery_integration import register
from test_discovery_integration import service
from test_setup import home


def test_fresh_native_origin_needs_no_sender_and_returns_immutable_host_text(settings, data_dir, tmp_path, home):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    result = discovery.create_stream(rt, {'name': 'work', 'areas': ['work'],
        'sources': [{'name': 'Feed', 'scope': ['board'], 'method': 'reader'}], 'user_approved': True}, 'parent')
    stream = ctx.state.get('streams')['work']
    assert result['stream']['delivery_owner'] == 'native_origin'
    assert stream['activation_state'] == 'ACTIVE' and len(ctx.cron) == 1
    job = ctx.cron[stream['job_id']]
    assert job['deliver'] == 'origin' and job['attach_to_session'] is True
    assert '[SILENT]' not in job['prompt'] and 'exact immutable' in job['prompt']
    # Exercise registered public APIs; synthetic host has no origin metadata.
    integration.configure('work', {'source_key': 'feed', 'name': 'Feed', 'account_key': 'account', 'scope': "['board']",
        'read_method': 'reader', 'relevance': {'identity_requirements': [], 'rules': 'All unresolved issues'}}, user_approved=True)
    run = integration.start('work', session_id='parent')['run_id']
    integration.store.freeze_index(run, rubric='Approved rubric')
    integration.runner.join(run, session_id='parent')
    ctx.registered_tools = {}
    ctx.register_tool = lambda **kw: ctx.registered_tools.update({kw['name']: kw})
    ctx.register_hook = lambda *a, **kw: None
    register(ctx, integration=integration)
    def call(name, args):
        returned = json.loads(ctx.registered_tools[name]['handler'](args, session_id='parent'))
        assert returned['ok'], returned
        return returned['result']
    digest = call('discovery_digest', {'run_id': run})
    first = call('discovery_digest', {'run_id': run, 'action': 'send'})
    again = call('discovery_digest', {'run_id': run, 'action': 'send'})
    assert first == again
    assert first['state'] == 'host_pending' and first['delivered'] is False
    assert first['final_text'] == digest['text'] and first['digest_sha256'] == digest['sha256']
    assert first['native_target_status'] == 'unconfigured'
    assert call('discovery_digest', {'run_id': run}) == digest
    backend = call('discovery_runs', {'run_id': run})
    assert backend['delivery']['state'] == 'host_pending' and not backend['delivery']['delivered']
    assert len(ctx.cron) == 1


def test_approved_owner_switch_reuses_job_origin_and_schedule(settings, data_dir, tmp_path, home):
    from test_final_requirements import binding
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    result = discovery.create_stream(rt, {'name': 'work', 'sources': [{'name': 'Feed', 'scope': 'board'}], 'user_approved': True}, 'parent')
    jid = result['job_id']
    before = dict(ctx.cron[jid])
    original = ctx.dispatch_tool
    calls = []
    def dispatch(tool, args):
        calls.append((tool, args))
        if tool == 'reader': return {'id': 'existing', 'destination': 'chat/topic', 'body': 'Existing origin message'}
        return original(tool, args)
    ctx.dispatch_tool = dispatch
    integration.configure_delivery('work', binding(), user_approved=True)
    stream = ctx.state.get('streams')['work']
    assert stream['delivery_owner'] == 'verified_sender'
    assert stream['job_id'] == jid and stream['origin_session'] == 'parent'
    assert ctx.cron[jid]['deliver'] == 'local' and '[SILENT]' in ctx.cron[jid]['prompt']
    integration.configure_delivery('work', {'delivery_owner': 'native_origin', 'origin_session': 'parent'}, user_approved=True)
    assert ctx.state.get('streams')['work']['delivery_owner'] == 'native_origin'
    assert ctx.cron[jid]['deliver'] == 'origin' and '[SILENT]' not in ctx.cron[jid]['prompt']
    assert ctx.cron[jid]['schedule'] == before['schedule'] and ctx.cron[jid]['attach_to_session'] is True
    assert len(ctx.cron) == 1 and not any(t == 'sender' for t, _ in calls)


def test_native_preserves_approved_target_through_reconcile_and_schedule(settings, data_dir, tmp_path, home):
    from alchemy_task.jobs import reconcile_discovery_job
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    result = discovery.create_stream(rt, {'name': 'work', 'sources': [{'name': 'Feed', 'scope': 'board'}],
        'deliver': 'telegram:approved:topic', 'user_approved': True}, 'parent')
    jid = result['job_id']
    reconcile_discovery_job(rt, integration._stream('work'))
    discovery.update_stream(rt, {'name': 'work', 'time': '8 AM', 'user_approved': True}, 'parent')
    assert ctx.cron[jid]['deliver'] == 'telegram:approved:topic'
    assert ctx.cron[jid]['schedule'] == '0 8 * * *' and len(ctx.cron) == 1


def test_explicit_owner_requires_available_exact_readback_before_any_job(settings, data_dir, tmp_path, home):
    from test_final_requirements import fresh, binding
    from alchemy_task.core.discovery_identity import UserError
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    result = fresh(integration, rt, ctx)
    assert result['stream']['activation_state'] == 'SETUP_BLOCKED' and not ctx.cron
    bad = binding(); bad.pop('verification_message_id')
    with pytest.raises(UserError, match='existing origin message'):
        integration.configure_delivery('fresh', bad, user_approved=True)
    with pytest.raises(UserError, match='approve exact origin'):
        integration.configure_delivery('fresh', {'delivery_owner': 'native_origin', 'origin_session': 'other'}, user_approved=True)
    assert not ctx.cron


def test_native_send_ignores_saved_sender_and_reprepare_keeps_numbers(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    from test_final_requirements import binding
    ctx.state.set('discovery_delivery', {'work': binding()})
    args = dict(stream='work', day='2030-01-01', origin={'session_id': 'parent'},
        items=[{'unit_id': 'unit-one', 'research_revision': 'r1', 'title': 'Review the actual request', 'kind': 'new'}])
    first = integration.digest.prepare('native-number', **args)
    result = integration.deliver('native-number', session_id='parent')
    assert result['final_text'] == first['text'] and not result['delivered']
    assert integration.digest.prepare('native-number', **args) == first
    assert integration.digest._load()['numbers'] == {'parent:2030-01-01': 1}
    assert not ctx.cron  # No extra job or alternate sender dispatch (fake rejects both).
