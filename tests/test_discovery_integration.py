"""Registered backend integration regressions, using approved synthetic readers."""
import json
from types import SimpleNamespace
import pytest
from alchemy_task import runtime, discovery
from alchemy_task.core.discovery_identity import UserError
from test_setup import SetupCtx


def service(settings, data_dir, tmp_path):
    from alchemy_task.discovery_integration import DiscoveryIntegration
    ctx = SetupCtx({'workspace_root': settings.workspace_root, 'timezone': settings.timezone}, data_dir)
    rt = runtime.Runtime(ctx, settings, data_dir)
    ctx.state.set('streams', {'work': {'name': 'work', 'mode': 'production', 'areas': ['work'], 'research_cap': 50, 'sources': [{'name': 'Feed', 'scope': ['board'], 'method': 'reader'}], 'deliver': 'origin', 'origin_session': 'parent', 'label': ''}})
    return DiscoveryIntegration(rt, profile_home=tmp_path / 'profile'), rt, ctx


def configure(integration):
    return integration.configure('work', {'source_key': 'feed', 'name': 'Feed', 'account_key': 'account', 'scope': ['board'],
        'read_method': 'reader', 'relevance': {'identity_requirements': [], 'rules': 'All unresolved project issues'},
        'binding': {'tool': 'reader', 'arguments': {}, 'request_fields': {'account': 'account_key', 'scope': 'scope', 'start': 'start', 'end': 'end', 'cursor': 'cursor'},
                    'response_fields': {k: k for k in ['account_key', 'scope', 'start', 'end', 'items', 'next_cursor', 'pagination_exhausted']}}}, user_approved=True)


def test_start_resume_same_frozen_window_and_real_reader_before_context_freeze(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    start = integration.start('work', session_id='parent')
    resumed = integration.start('work', session_id='parent')
    assert resumed['run_id'] == start['run_id'] and resumed['windows'] == start['windows']
    calls = []
    def reader(tool, args):
        calls.append((tool, args))
        return json.dumps({'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
                           'items': [{'title': 'Review issue', 'source_ids': ['source:feed:account:issue:one'], 'source_revision': 'v1'}],
                           'next_cursor': None, 'pagination_exhausted': True})
    ctx.dispatch_tool = reader
    receipt = integration.collect(start['run_id'], 'feed', session_id='parent')
    assert receipt['status'] == 'complete' and len(calls) == 1
    profile = tmp_path / 'profile'
    (profile / 'memories').mkdir(parents=True)
    (profile / 'SOUL.md').write_text('Approved operator preferences, no inferred account name.')
    (profile / 'memories' / 'MEMORY.md').write_text('Approved task context.')
    frozen = integration.freeze(start['run_id'], session_id='parent')
    ledger = integration.store.get_run(start['run_id'])
    info = ledger['resources']['source_config']
    config_context = json.loads((integration.store.run_dir(start['run_id']) / 'resources' / info['sha256']).read_text())
    assert 'Approved operator preferences' in str(config_context)
    assert 'Approved task context' in str(config_context)
    assert len(ledger['candidates']) == 1
    assert ledger['resources']['task_inventory'] and ledger['resources']['context-rubric']
    assert frozen['index_revision'] == ledger['index_revision']
    assert 'joined' not in ledger
    with pytest.raises(UserError, match='join'):
        integration.match(start['run_id'], ledger['candidates'][0]['candidate_id'], session_id='parent')


def test_account_identity_only_when_relevance_requires_and_profile_scoped(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    assert config['source_key'] == 'feed'
    config['relevance']['identity_requirements'] = ['name']
    with pytest.raises(UserError, match='identity'):
        integration.configure('work', config, user_approved=True)
    integration.confirm_identity('account', {'name': 'Operator', 'aliases': [], 'user_id': None}, user_confirmed=True)
    saved = integration.configure('work', config, user_approved=True)
    assert saved['identity']['name'] == 'Operator'
    assert ctx.state.get('discovery_identity_accounts')['account']['confirmed'] is True


def test_registration_defers_state_access_until_real_invocation():
    from alchemy_task.discovery_integration import register, SCHEMAS
    captured = {}
    ctx = SimpleNamespace(register_tool=lambda **kw: captured.update({kw['name']: kw}),
                          register_hook=lambda *a, **kw: None)
    register(ctx)
    assert set(captured) == set(SCHEMAS)


def test_registered_runner_tools_have_complete_object_schemas(settings, data_dir, tmp_path):
    from alchemy_task.discovery_integration import SCHEMAS, register
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.registered_tools = {}
    ctx.register_tool = lambda **kw: ctx.registered_tools.update({kw['name']: kw})
    ctx.hooks = {}
    ctx.register_hook = lambda name, fn: ctx.hooks.update({name: fn})
    runtime.bind(ctx)
    register(ctx, integration=integration)
    for name in ['discovery_research_run', 'discovery_research_fetch', 'discovery_research_submit', 'discovery_research_accept', 'discovery_join', 'discovery_recover', 'discovery_collect', 'discovery_context', 'discovery_match', 'discovery_digest', 'discovery_runs']:
        assert name in ctx.registered_tools
        schema = ctx.registered_tools[name]['schema']['parameters']
        assert schema['type'] == 'object' and schema['properties']
    assert {'subagent_start', 'pre_tool_call', 'pre_llm_call'} <= set(ctx.hooks)
    raw = ctx.registered_tools['discovery_collect']['handler']({'run_id': 'missing', 'source_key': 'feed', 'session_id': 'parent'}, session_id='other')
    assert json.loads(raw)['ok'] is False


def test_post_join_decision_digest_exact_binding_and_backend(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task.discovery_integration import DiscoveryIntegration
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    ctx = SetupCtx({'workspace_root': settings.workspace_root, 'timezone': settings.timezone}, data_dir)
    rt.ctx = ctx
    from alchemy_task.core.gitops import GitDelivery
    rt.git = lambda: GitDelivery(settings, data_dir)
    ctx.state.set('streams', {'work': {'name': 'work', 'label': '', 'origin_session': 'parent'}})
    # Synthetic core fixture uses no origin, bind it through trusted test fixture.
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run); ledger['origin'] = {'session_id': 'parent', 'deliver': 'origin'}
        store._save(run, ledger)
    integration = DiscoveryIntegration(rt, profile_home=tmp_path / 'profile')
    with pytest.raises(UserError, match='decision'):
        integration.finalize(run, session_id='parent')
    integration.record_decision(run, wid, decision='propose', reason='New independent substantive action.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    proposal = digest['items'][0]
    assert proposal['unit_id'] == wid and proposal['number'] == 1
    before = len(rt.store().scan().tasks)
    result = integration.decide({'approve': ['1'], 'day': '2030-01-01', 'edits': {'1': {'area': 'work', 'undated': True}}}, session_id='parent', today='2030-01-02')
    assert len(rt.store().scan().tasks) == before + 1
    assert result['results'][0]['task_id']
    assert integration.backend(run, session_id='parent')['proposals'][0]['unit_id'] == wid
    assert integration.digest.delivery(run)['state'] == 'prepared'
    # Retrying exact approval resumes saved binding; no generic research or extra task.
    integration.decide({'approve': ['1'], 'day': '2030-01-01', 'edits': {'1': {'area': 'work', 'undated': True}}}, session_id='parent', today='2030-01-02')
    assert len(rt.store().scan().tasks) == before + 1


def test_approval_batch_preflight_rejects_invalid_second_edit_without_task_writes(settings, data_dir, tmp_path):
    from test_discovery_state import setup, prepare, read_all
    from test_discovery_schema import bundle
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    store, run, items = setup(data_dir, count=2)
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run); ledger['origin'] = {'session_id': 'parent'}; store._save(run, ledger)
    for index, item in enumerate(items):
        a = prepare(store, run, item['candidate_id'])
        b = bundle(); b['candidate_id'] = item['candidate_id']; b['workstreams'][0]['exact_source_ids'][0]['message_ts'] = f'171.{index+2}'
        b['workstreams'][0]['title'] = f'Independent action {index}'
        receipt = store.spool_payload(run, a['token'], b)
        store.observe_terminal(run, a['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
        read_all(store, run, receipt['resource'], 'parent')
        store.accept_attempt(run, a['token'], payload_sha256=receipt['payload_sha256'], assessment={'accepted': True, 'reason': 'Distinct substantive action fully verified.'}, reader='parent')
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [x['candidate_id'] for x in items], 'failures': []})
    for c in store.get_run(run)['candidates']:
        if c.get('parent_candidate_id'): integration.record_decision(run, c['candidate_id'], decision='propose', reason='Independent untracked ask.', session_id='parent')
    integration.finalize(run, session_id='parent')
    before = len(rt.store().scan().tasks)
    with pytest.raises((UserError, ValueError)):
        integration.decide({'approve': ['1', '2'], 'day': '2030-01-01', 'edits': {'1': {'area': 'work', 'undated': True}, '2': {'area': 'work', 'due': 'not a date'}}}, session_id='parent', today='2030-01-02')
    assert len(rt.store().scan().tasks) == before
    with pytest.raises(UserError, match='edits'):
        integration.decide({'approve': ['1', '2'], 'day': '2030-01-01', 'edits': {'1': {'title': 'Changed user scope', 'area': 'work', 'undated': True}, '2': {'area': 'work', 'undated': True}}}, session_id='parent', today='2030-01-02')
    assert len(rt.store().scan().tasks) == before


def test_stream_names_with_spaces_preserve_public_identity(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    streams = ctx.state.get('streams'); streams['project work'] = streams.pop('work'); streams['project work']['name'] = 'project work'; ctx.state.set('streams', streams)
    integration.configure('project work', config, user_approved=True)
    first = integration.start('project work', session_id='parent')
    assert first['stream'] == 'project work'
    assert integration.start('project work', session_id='parent')['run_id'] == first['run_id']


def test_source_to_registered_research_join_proposal_conversion_and_next_run(settings, data_dir, tmp_path):
    from alchemy_task.discovery_integration import register
    from alchemy_task.discovery_runner import CHECKLIST
    from test_discovery_runner import Clock, Pool
    from test_discovery_schema import bundle
    from alchemy_task import task_tools
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    window = integration.store.get_run(run)['config']['windows']['feed']
    integration.collect(run, 'feed', session_id='parent', envelope={**window, 'status': 'partial', 'account_key': 'account', 'items': [
        {'title': 'Review release', 'source_ids': ['source:feed:account:issue:one'], 'source_revision': 'v1', 'body': 'Please review the release notes before Friday.'}]})
    revision = integration.freeze(run, session_id='parent')['index_revision']
    clock = Clock(); pool = Pool(clock); ctx.subagent_lifecycle = pool; pool.runner = integration.runner
    integration.runner.clock = clock
    tools = {}; hooks = {}
    ctx.register_tool = lambda **kw: tools.update({kw['name']: kw['handler']})
    ctx.register_hook = lambda name, fn: hooks.update({name: fn})
    register(ctx, integration=integration)
    def call(name, args, session='parent'):
        result = json.loads(tools[name](args, session_id=session))
        assert result['ok'], result
        return result['result']
    original_status = pool.status
    submitted = set()
    def status(handle):
        data = pool.records[handle['subagent_id']]
        bootstrap = data['bootstrap']
        if handle['subagent_id'] not in submitted:
            child = 'child-' + handle['subagent_id'].split('-')[-1]
            for name, info in bootstrap['resources'].items():
                cursor = None
                while True:
                    page = call('discovery_research_fetch', {'run_id': run, 'resource': name, 'revision': info['sha256'], 'token': bootstrap['token'], 'binding': bootstrap['binding'], **({'cursor': cursor} if cursor else {})}, child)
                    if not page['has_more']: break
                    cursor = page['next_cursor']
            payload = bundle(); payload['candidate_id'] = bootstrap['candidate_id']
            payload['workstreams'][0]['exact_source_ids'] = [{'type': 'source', 'source_key': 'feed', 'account_key': 'account', 'object_kind': 'issue', 'object_id': 'one'}]
            call('discovery_research_submit', {'run_id': run, 'token': bootstrap['token'], 'binding': bootstrap['binding'], 'payload': payload}, child)
            submitted.add(handle['subagent_id'])
        return original_status(handle)
    pool.status = status
    before = len(rt.store().scan().tasks)
    result = call('discovery_research_run', {'run_id': run, 'expected_revision': revision})
    assert len(rt.store().scan().tasks) == before and result['awaiting_parent']
    for token in result['awaiting_parent']:
        info = integration.store.get_attempt(run, token)['payload']; cursor = None
        while True:
            page = call('discovery_research_fetch', {'run_id': run, 'resource': info['resource'], 'revision': info['payload_sha256'], **({'cursor': cursor} if cursor else {})})
            if not page['has_more']: break
            cursor = page['next_cursor']
        call('discovery_research_accept', {'run_id': run, 'token': token, 'payload_sha256': info['payload_sha256'],
            'assessment': {'accepted': True, 'reason': 'Full primary and all plausible tasks show independent user action.', 'checklist': {k: 'Reviewed all supplied full evidence.' for k in CHECKLIST}}})
    assert call('discovery_join', {'run_id': run})['joined']
    ledger = integration.store.get_run(run)
    wid = next(c['candidate_id'] for c in ledger['candidates'] if c.get('parent_candidate_id'))
    assert call('discovery_match', {'run_id': run, 'unit_id': wid})['kind'] == 'new'
    call('discovery_decision', {'run_id': run, 'unit_id': wid, 'decision': 'propose', 'reason': 'Independent untracked action.'})
    digest = call('discovery_digest', {'run_id': run})
    assert len(rt.store().scan().tasks) == before and len(digest['items']) == 1
    runtime.bind(ctx)
    approved = json.loads(task_tools.discovery_decide({'approve': ['1'], 'edits': {'1': {'area': 'work', 'undated': True}}}, session_id='parent'))
    assert approved['ok'], approved
    assert len(rt.store().scan().tasks) == before + 1
    assert integration.store.source_state('work', 'feed')['backlog'][0]['status'] == 'accepted'


def test_default_runtime_without_receipt_uses_frozen_stream_budget(settings, data_dir, tmp_path):
    from alchemy_task.discovery_integration import DiscoveryIntegration
    from test_discovery_runner import Clock, Pool
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    streams = ctx.state.get('streams'); streams['work']['research_cap'] = 0; ctx.state.set('streams', streams)
    # Default install: no timeout receipt is configured, and none is needed.
    integration = DiscoveryIntegration(rt, profile_home=tmp_path / 'profile')
    run = integration.start('work', session_id='parent')['run_id']
    ledger = integration.store.get_run(run); window = ledger['config']['windows']['feed']
    integration.collect(run, 'feed', session_id='parent', envelope={**window, 'status': 'partial', 'account_key': 'account', 'items': [
        {'title': 'Deferred work', 'source_ids': ['source:feed:account:issue:one'], 'source_revision': 'v1', 'body': 'Deferred work item text.'}]})
    integration.freeze(run, session_id='parent')
    clock = Clock(); pool = Pool(clock); ctx.subagent_lifecycle = pool
    integration.runner.clock = clock; pool.runner = integration.runner
    result = integration.runner.run(run, session_id='parent')
    assert not pool.requests and result['budget_deferred']


def test_registered_task_service_refuses_discovery_child_writes(settings, data_dir, tmp_path):
    from alchemy_task.discovery_integration import get_service
    from alchemy_task import task_tools
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    # Use the same cached service that all registered task entrypoints consult.
    runtime.bind(ctx)
    integration = get_service(rt)
    run = integration.store.init_run(origin={'session_id': 'parent'})
    items = integration.store.add_candidates(run, [{'title': 'Read only', 'source_ids': ['source:feed:account:issue:one']}])
    integration.store.freeze_index(run, rubric='Read only')
    a = integration.store.reserve_attempt(run, items[0]['candidate_id'], owner_session='parent')
    integration.store.record_start(run, parent_session='parent', child_session='child', subagent_id='sa-child')
    integration.store.bind_attempt(run, a['token'], {'subagent_id': 'sa-child'}, owner_session='parent')
    before = len(rt.store().scan().tasks)
    result = json.loads(task_tools.task_create({'title': 'Forbidden child write', 'area': 'work', 'undated': True}, session_id='child'))
    assert result['ok'] is False and 'read-only' in str(result).lower()
    assert len(rt.store().scan().tasks) == before


def test_origin_delivery_requires_actual_readback_and_unknown_never_resends(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    digest = integration.digest.prepare('delivery-run', stream='work', day='2030-01-01', origin={'session_id': 'parent'},
        items=[{'unit_id': 'w_one', 'research_revision': 'r', 'title': 'Review release', 'kind': 'new', 'targets': []}])
    ctx.dispatch_tool = lambda name, args: {'id': 'existing', 'chat': 'synthetic-chat', 'text': 'Existing message'}
    integration.configure_delivery('work', {'origin_session': 'parent', 'target': 'synthetic-chat',
        'scheduled_approved': True, 'toolsets': ['approved-messaging'], 'verification_message_id': 'existing', 'verification_text': 'Existing message',
        'send_tool': 'approved_sender', 'read_tool': 'approved_message_reader',
        'send_arguments': {}, 'send_fields': {'chat': 'target', 'text': 'text'}, 'send_id_path': 'message.id',
        'read_arguments': {}, 'read_fields': {'chat': 'target', 'id': 'message_id'},
        'read_response': {'message_id': 'id', 'target': 'chat', 'text': 'text'}}, user_approved=True)
    calls = []
    def dispatch(name, args):
        calls.append((name, args))
        if name == 'approved_sender': return {'message': {'id': 'sent-1'}}
        return {'id': 'sent-1', 'chat': 'synthetic-chat', 'text': digest['text']}
    ctx.dispatch_tool = dispatch
    result = integration.deliver('delivery-run', session_id='parent')
    assert result['state'] == 'delivered' and result['message_id'] == 'sent-1'
    assert len(calls) == 2
    integration.deliver('delivery-run', session_id='parent')
    assert len(calls) == 2
    integration.digest.prepare('lost-run', stream='work', day='2030-01-01', origin={'session_id': 'parent'}, items=[])
    def lost(name, args):
        calls.append((name, args))
        raise OSError('lost send receipt')
    ctx.dispatch_tool = lost
    assert integration.deliver('lost-run', session_id='parent')['state'] == 'unknown'
    count = len(calls)
    assert integration.deliver('lost-run', session_id='parent')['state'] == 'unknown'
    assert len(calls) == count
