"""Normal failure/restart acceptance for the complete saved workflow."""
import copy
from types import SimpleNamespace
import pytest
from test_discovery_integration import service, configure
from alchemy_task.core.discovery_identity import UserError


def test_registered_slack_recipe_maps_search_and_primary_operation_arguments(settings, data_dir, tmp_path):
    import datetime as dt
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration); config.update(kind='slack', seed_queries=['in:board'])
    config['binding']['request_fields'].update({'query': 'collector_request.query', 'count': 'collector_request.count'})
    config['primary_bindings'] = {}
    for operation, timestamp in [('before', 'latest'), ('after', 'oldest')]:
        bound = copy.deepcopy(config['binding']); bound['tool'] = 'slack_primary'
        bound['request_fields'] = {'account': 'account_key', 'scope': 'scope', 'start': 'start', 'end': 'end', 'operation': 'collector_request.operation', 'channel': 'collector_request.channel', timestamp: 'collector_request.' + timestamp, 'limit': 'collector_request.limit', 'inclusive': 'collector_request.inclusive'}
        bound['response_fields']['recipe_complete'] = 'recipe_complete'
        config['primary_bindings'][operation] = bound
    integration.configure('work', config, user_approved=True)
    run = integration.start('work', session_id='parent')['run_id']
    calls = []
    def dispatch(tool, args):
        calls.append((tool, copy.deepcopy(args)))
        ts = str(dt.datetime.fromisoformat(args['end']).timestamp() - 10)
        message = {'channel_id': 'C1', 'ts': ts, 'text': 'Full genuine source ask'}
        return {'account_key': args['account'], 'scope': args['scope'], 'start': args['start'], 'end': args['end'], 'next_cursor': None, 'pagination_exhausted': True, 'recipe_complete': True, 'items': [message]}
    ctx.dispatch_tool = dispatch
    result = integration.collect(run, 'feed', session_id='parent')
    assert result['status'] == 'complete', result
    assert [c[1].get('operation', 'search') for c in calls] == ['search', 'before', 'after']
    assert calls[0][1]['count'] == 20 and 'in:board after:' in calls[0][1]['query']
    assert calls[1][1]['limit'] == 6 and calls[1][1]['inclusive'] is True
    assert calls[2][1]['limit'] == 10 and calls[2][1]['inclusive'] is False
    assert integration.store.source_state('work', 'feed')['backlog'][0]['candidate']['messages'][0]['text'] == 'Full genuine source ask'


def test_registered_raw_mail_pipeline_expands_actual_thread_and_snapshots(settings, data_dir, tmp_path):
    import base64, datetime as dt, json
    from alchemy_task.discovery_integration import register
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    config.update(kind='mail', sender_domains=['example.test'])
    config['thread_binding'] = {**copy.deepcopy(config['binding']), 'tool': 'full_thread'}
    config['thread_binding']['request_fields']['thread'] = 'collector_request.thread_id'
    integration.configure('work', config, user_approved=True)
    run = integration.start('work', session_id='parent')['run_id']
    calls = []
    def dispatch(tool, args):
        calls.append((tool, copy.deepcopy(args)))
        envelope = {'account_key': args['account'], 'scope': args['scope'], 'start': args['start'], 'end': args['end'], 'next_cursor': None, 'pagination_exhausted': True}
        if tool == 'reader': return {**envelope, 'items': [{'threadId': 'real-thread'}]}
        assert tool == 'full_thread' and args['thread'] == 'real-thread'
        millis = str(int(dt.datetime.fromisoformat(args['end']).timestamp() * 1000))
        return {**envelope, 'items': [{'id': 'real-thread', 'complete': True, 'messages': [{'id': 'real-message', 'internalDate': millis, 'payload': {'mimeType': 'text/plain', 'headers': [{'name': 'From', 'value': 'Author <author@example.test>'}, {'name': 'Subject', 'value': 'Approve proof'}], 'body': {'data': base64.urlsafe_b64encode(b'Full primary source asks for approval.').decode()}}}]}]}
    ctx.dispatch_tool = dispatch
    tools = {}; ctx.register_tool = lambda **kw: tools.update({kw['name']: kw['handler']}); ctx.register_hook = lambda *a: None
    register(ctx, integration=integration)
    result = json.loads(tools['discovery_collect']({'run_id': run, 'source_key': 'feed'}, session_id='parent'))
    assert result['ok'] and result['result']['status'] == 'complete', result
    candidate = integration.store.source_state('work', 'feed')['backlog'][0]['candidate']
    assert candidate['source_ids'] == ['gmail:account:real-thread']
    assert 'Full primary source' in candidate['messages'][0]['body']
    assert [c[0] for c in calls] == ['reader', 'full_thread']
    assert list((integration.store.run_dir(run) / 'source-snapshots').glob('mail-*.json'))
    frozen = integration.freeze(run, session_id='parent')
    ledger = integration.store.get_run(run)
    source_body = ledger['resources']['source-body-' + ledger['candidates'][0]['candidate_id']]
    primary = (integration.store.run_dir(run) / 'resources' / source_body['sha256']).read_text()
    assert 'Full primary source asks for approval.' in primary
    assert frozen['context']['source-material']


def test_discovery_phone_completion_uses_existing_sync_actual_adapter_readback(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from test_ios_sync import FakePhone, LIST_A
    from alchemy_task import ios_sync
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _, store, run, wid, _ = joined(tmp_path, settings, data_dir)
    settings.git_transport = 'none'
    phone = FakePhone(); ctx.dispatch_tool = phone.dispatch
    ios_sync.save(rt, {'config': {'enabled': True, 'device_id': 'PHONE-1', 'list_id': LIST_A, 'areas': ['work']}, 'mappings': {}, 'ops': {}, 'conflicts': {}, 'reads': {}, 'notes': {}})
    integration.conversion.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved task and existing mirror scope.')
    queued = integration.conversion.deliver_git(run, wid)
    assert queued['phone']['state'] == 'queued' and phone.writes == 0
    ios_sync.sync(rt)
    complete = integration.conversion.deliver_git(run, wid)
    assert complete['state'] == 'complete' and complete['phone']['state'] == 'verified'
    count = phone.writes
    integration.conversion.deliver_git(run, wid)
    ios_sync.sync(rt)
    assert phone.writes == count


def test_sibling_selected_updates_compose_one_whole_postimage(settings, data_dir):
    from alchemy_task.core import taskfile as tf
    rt, store, run, units, conversion = two_joined(settings, data_dir)
    task = rt.store().create(title='Both approved outcomes', area='work', undated=True, research=False, notes='Original correspondence. slack:T1:C1:171.1:171.2 slack:T1:C1:171.1:171.3', plan='Original plan')
    for unit in units:
        conversion.prepare(run, unit, choice='update', user_approved=True, target_task_id=task.task_id, expected_revision=tf.content_hash(task.raw), reason='User approved both updates to this exact task.')
    conversion.preflight([(run, w) for w in units])
    first = conversion.apply(run, units[0]); second = conversion.apply(run, units[1])
    assert first['task_id'] == second['task_id'] == task.task_id
    actual = rt.store().resolve(task.task_id)
    assert actual.body.count('## Notes\n') == actual.body.count('## Plan\n') == actual.body.count('## Log\n') == 1
    for unit in units: assert actual.body.count('<!-- discovery-dossier:start dos-' + unit[2:] + ' -->') == 1
    assert 'Original correspondence.' in actual.body and 'Original plan' in actual.body


def test_explicit_manual_task_recovery_rebinds_unwritten_create_not_duplicate(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task.core import taskfile as tf
    from alchemy_task.core.discovery_dossiers import content_revision
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    prepared = conversion.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved exact proposal.')
    manual = rt.store().create(title='User already made correct task', area='work', undated=True, research=False, notes='Preserve manual correspondence.')
    before = len(rt.store().scan().tasks)
    conversion.bind_manual(run, wid, target_task_id=manual.task_id, expected_revision=tf.content_hash(manual.raw), expected_plan_revision=content_revision(prepared), reason='User explicitly identified manually created destination.')
    result = conversion.apply(run, wid)
    assert result['task_id'] == manual.task_id
    assert len(rt.store().scan().tasks) == before
    actual = rt.store().resolve(manual.task_id)
    assert 'Preserve manual correspondence.' in actual.body
    assert store.research_for(run, wid)['current_understanding'] in actual.body
    assert not (rt.store().root / prepared['path']).exists()


def test_user_scope_overlay_preserves_sections_metadata_and_active_dossier(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task.core import taskfile as tf
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    task = rt.store().create(title='Existing work', area='work', undated=True, research=False, notes='User correspondence. slack:T1:C1:171.1:171.2\nEarlier decision', plan='- Existing implementation context')
    conversion.prepare(run, wid, choice='update', user_approved=True, target_task_id=task.task_id, expected_revision=tf.content_hash(task.raw), reason='User limited approval to browser verification only.',
                       priority='high', scheduled='2030-01-04', execution_method='browser', notes='Verify only; sibling rollout remains deferred.', plan='Check existing deployment, do not deploy.', checklist=['Verify print proof'], active_goal='Verify the existing proof only')
    conversion.apply(run, wid)
    actual = rt.store().resolve(task.task_id)
    assert actual.fm['priority'] == 'high' and str(actual.fm['scheduled']) == '2030-01-04'
    assert actual.fm['execution_method'] == 'browser'
    for heading in ('Notes', 'Plan', 'Log'): assert actual.body.count('## ' + heading + '\n') == 1
    for text in ('User correspondence.', 'Existing implementation context', 'Earlier decision', 'Verify only; sibling rollout remains deferred.', 'Check existing deployment, do not deploy.', 'Verify print proof', 'Verify the existing proof only', 'browser'):
        assert text in actual.body
    assert actual.body.index('## Plan') < actual.body.index('<!-- discovery-dossier:start')
    next_action = actual.body.split('### Next Action\n\n', 1)[1].split('\n\n### ', 1)[0]
    assert 'Verify the existing proof only' in next_action


def test_verified_dead_supervisor_process_lease_can_be_reclaimed_without_refund(data_dir):
    import multiprocessing, datetime as dt
    from test_discovery_state import setup
    store, run, items = setup(data_dir)
    attempt = store.reserve_attempt(run, items[0]['candidate_id'], owner_session='parent')
    expiry = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=40)).isoformat()
    context = multiprocessing.get_context('fork')
    ready, child_ready = context.Pipe(duplex=False)
    def hold():
        store.claim_lease(run, owner='dead-invocation', expires_at=expiry)
        child_ready.send(True)
        import time
        time.sleep(60)
    process = context.Process(target=hold)
    process.start()
    try:
        assert ready.poll(10) and ready.recv()
        with pytest.raises(UserError, match='claimed'):
            store.claim_lease(run, owner='other-invocation', expires_at=expiry)
        process.terminate(); process.join(10)
        claimed = store.claim_lease(run, owner='recovered-invocation', expires_at=expiry)
        assert claimed['owner'] == 'recovered-invocation'
        ledger = store.get_run(run)
        assert ledger['lease_recoveries'][-1]['proof']['state'] == 'dead'
        assert len(ledger['attempts']) == 1 and ledger['attempts'][attempt['token']]['ordinal'] == 1
    finally:
        if process.is_alive(): process.terminate()
        process.join(10)


def test_final_review_projection_recovers_and_retains_unknown_delivery(settings, data_dir, tmp_path):
    from alchemy_task.core.discovery_state import read_json
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    integration.collect(run, 'feed', session_id='parent', envelope={**integration.store.get_run(run)['config']['windows']['feed'], 'account_key': 'account', 'status': 'partial', 'items': []})
    integration.freeze(run, session_id='parent')
    integration.store.put_resource(run, 'join-record', {'joined': True, 'accepted': [], 'failures': []})
    integration.finalize(run, session_id='parent')
    integration.reconcile_endstate(run)
    assert 'digest_delivery' in integration.store.get_run(run)['pending_operations']
    assert integration.store.prune(days=0)['deleted_runs'] == []
    integration._delivery_record(run, {'state': 'delivered', 'verified_sha256': integration.digest.get(run)['sha256'], 'readback': {'message_id': 'test-id', 'target': 'test-chat'}})
    integration.reconcile_endstate(run)
    assert integration.store.get_run(run)['pending_operations'] == []


def test_approved_workspace_urls_and_encoded_tokens_are_consumed(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    doc = rt.store().create(title='Legacy provenance', area='work', undated=True, research=False, notes='slack%3AT1%3AC1%3A171.1%3A171.2')
    assert conversion.match(run, wid)['kind'] == 'exact'
    linked = rt.store().create(title='URL provenance', area='work', undated=True, research=False, notes='https://confirmed.example.test/archives/C1/p171000002?thread_ts=171.1')
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run); ledger['config']['sources'] = [{'url_mappings': {'slack_workspaces': {'confirmed.example.test': 'T1'}}}]; store._save(run, ledger)
    mapped = conversion._exact_values(linked, slack_workspaces={'confirmed.example.test': 'T1'})
    assert 'slack:T1:C1:171.1:171.000002' in mapped
    assert not conversion._exact_values(linked)


def test_exact_nomination_to_untagged_file_refuses_precisely(settings, data_dir, tmp_path):
    from test_discovery_conversion import custom_joined
    relative = 'areas/work/tasks/untagged.md'
    path = settings.area_dir('work') / 'untagged.md'
    path.write_text('---\ntitle: Not a task\n---\nUnrelated content.\n')
    rt, store, run, wid, conversion = custom_joined(settings, data_dir, tmp_path, [{'path': relative, 'match_basis': 'exact'}])
    with pytest.raises(UserError, match='canonical|tagged|nomination'):
        conversion.match(run, wid)


def test_stream_timezone_controls_frozen_business_date_not_profile(settings, data_dir, tmp_path):
    import datetime as dt
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    streams = ctx.state.get('streams'); streams['work']['timezone'] = 'America/Los_Angeles'; ctx.state.set('streams', streams)
    integration.utcnow = lambda: dt.datetime(2030, 1, 2, 2, tzinfo=dt.timezone.utc)
    started = integration.start('work', session_id='parent')
    ledger = integration.store.get_run(started['run_id'])
    assert ledger['business_date'] == '2030-01-01'
    streams['work']['timezone'] = 'UTC'; ctx.state.set('streams', streams)
    resumed = integration.start('work', session_id='parent')
    assert resumed['run_id'] == started['run_id']
    assert integration.store.get_run(started['run_id'])['config']['timezone'] == 'America/Los_Angeles'


@pytest.mark.parametrize('mode', ['shadow', 'research_only', 'unknown', None])
def test_nonproduction_modes_cannot_prepare_or_apply_tasks(settings, data_dir, tmp_path, mode):
    from test_discovery_conversion import joined
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run); ledger['config']['mode'] = mode; store._save(run, ledger)
    before = len(rt.store().scan().tasks)
    assert conversion.match(run, wid)
    with pytest.raises(UserError, match='mode|production'):
        conversion.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='Must not write shadow tasks.')
    assert len(rt.store().scan().tasks) == before


def test_rich_digest_preserves_researched_state_action_links_and_titled_failures(data_dir):
    from alchemy_task.discovery_digest import DiscoveryDigest
    digest = DiscoveryDigest(data_dir / 'discovery')
    result = digest.prepare('rich-run', stream='work', day='2030-01-01', origin={'session_id': 'parent'}, items=[
        {'unit_id': 'w_one', 'research_revision': 'v1', 'title': 'Approve proof', 'kind': 'semantic', 'targets': [{'title': 'Existing print work'}],
         'current_understanding': 'The revised proof is ready.', 'substantive_next_action': 'Approve final trim and send to print.', 'source_links': ['https://example.test/proof'], 'new_information': ['The trim changed.'], 'research_disposition': 'uncertain', 'uncertainty': ['Print date needs confirmation.']}],
         failures=[{'title': 'Resolve asset access', 'reason': 'Source unavailable'}], coverage=[{'source_key': 'feed', 'status': 'partial'}])
    text = result['text']
    for value in ['The revised proof is ready.', 'Approve final trim and send to print.', 'https://example.test/proof', 'Existing print work', 'The trim changed.', 'Print date needs confirmation.', 'Resolve asset access', 'degraded', 'Review:']:
        assert value in text, text
    assert 'w_one' not in text
    assert len(result['items']) == 1


def test_same_message_actions_do_not_auto_bind_each_others_task(settings, data_dir, tmp_path):
    from test_discovery_state import setup, prepare, read_all
    from test_discovery_schema import bundle
    from alchemy_task.discovery_conversion import DiscoveryConversion
    from alchemy_task.core.store import TaskStore
    store, run, items = setup(data_dir)
    cid = items[0]['candidate_id']
    payload = bundle(); payload['candidate_id'] = cid
    payload['workstreams'].append(copy.deepcopy(payload['workstreams'][0]))
    for i, unit in enumerate(payload['workstreams'], 1):
        unit.update(action_key=f'ask{i}', action_anchor={'locator': f'bullet:{i}', 'outcome': f'Outcome {i}'}, action_relation='independent')
    store.freeze_action_registry(run, cid, [u['action_anchor'] for u in payload['workstreams']])
    attempt = prepare(store, run, cid)
    receipt = store.spool_payload(run, attempt['token'], payload)
    store.observe_terminal(run, attempt['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
    read_all(store, run, receipt['resource'], 'parent')
    store.accept_attempt(run, attempt['token'], payload_sha256=receipt['payload_sha256'], assessment={'accepted': True, 'reason': 'Two primary verified independent asks.'}, reader='parent')
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [cid], 'failures': []})
    rt = SimpleNamespace(data_dir=data_dir, settings=settings, store=lambda: TaskStore(settings, data_dir))
    conversion = DiscoveryConversion(rt, store)
    units = store.accepted_bundle(run, cid)['workstream_ids']
    conversion.prepare(run, units[0], choice='create', user_approved=True, area='work', undated=True, reason='User approved first ask only.')
    first = conversion.apply(run, units[0])
    outcome = conversion.match(run, units[1])
    assert outcome['kind'] == 'new'
    assert not outcome['targets']
    assert conversion.match(run, units[0])['targets'][0]['task_id'] == first['task_id']


def test_partial_collection_resumes_same_window_and_actual_cursor(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    calls = []
    def read(tool, args):
        calls.append(copy.deepcopy(args))
        cursor = args['cursor']
        return {'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
                'items': [{'title': 'Issue ' + str(cursor), 'source_ids': ['source:feed:account:issue:' + ('one' if cursor is None else 'two')], 'source_revision': 'v1'}],
                'next_cursor': 'page-two' if cursor is None else None, 'pagination_exhausted': cursor is not None}
    ctx.dispatch_tool = read
    partial = integration.collect(run, 'feed', session_id='parent', max_pages=1)
    assert partial['status'] == 'partial'
    assert not integration.store.source_state('work', 'feed').get('watermark')
    complete = integration.collect(run, 'feed', session_id='parent')
    assert complete['status'] == 'complete'
    assert [c['cursor'] for c in calls] == [None, 'page-two']
    assert calls[0]['start'] == calls[1]['start'] and calls[0]['end'] == calls[1]['end']
    assert len(integration.store.source_state('work', 'feed')['backlog']) == 2
    assert len(complete['pages']) == 2


def two_joined(settings, data_dir):
    from test_discovery_state import setup, prepare, read_all
    from test_discovery_schema import bundle
    from alchemy_task.discovery_conversion import DiscoveryConversion
    from alchemy_task.core.store import TaskStore
    store, run, items = setup(data_dir, count=2)
    units = []
    for i, item in enumerate(items):
        attempt = prepare(store, run, item['candidate_id'])
        payload = bundle(); payload['candidate_id'] = item['candidate_id']
        payload['workstreams'][0]['exact_source_ids'][0]['message_ts'] = f'171.{i+2}'
        payload['workstreams'][0]['title'] = f'Action {i}'
        receipt = store.spool_payload(run, attempt['token'], payload)
        store.observe_terminal(run, attempt['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
        read_all(store, run, receipt['resource'], 'parent')
        store.accept_attempt(run, attempt['token'], payload_sha256=receipt['payload_sha256'], assessment={'accepted': True, 'reason': 'Full distinct source and task verification.'}, reader='parent')
        units += store.accepted_bundle(run, item['candidate_id'])['workstream_ids']
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [c['candidate_id'] for c in items], 'failures': []})
    rt = SimpleNamespace(data_dir=data_dir, settings=settings, store=lambda: TaskStore(settings, data_dir))
    return rt, store, run, units, DiscoveryConversion(rt, store)


def test_explicit_merge_preserves_every_dossier_one_task_and_resumes(settings, data_dir, tmp_path):
    from alchemy_task.core.discovery_state import read_json
    rt, store, run, units, conversion = two_joined(settings, data_dir)
    before = len(rt.store().scan().tasks)
    for unit in units:
        conversion.prepare(run, unit, choice='create', user_approved=True, area='work', undated=True, reason='User selected same combined task.')
    merge = conversion.merge_prepared([(run, w) for w in units], reason='User explicitly merged these two proposals.')
    assert merge['state'] == 'prepared'
    conversion.preflight([(run, w) for w in units])
    first = conversion.apply(run, units[0])
    second = conversion.apply(run, units[1])
    assert first['task_id'] == second['task_id']
    assert len(rt.store().scan().tasks) == before + 1
    doc = rt.store().resolve(first['task_id'])
    for unit in units:
        assert doc.body.count('<!-- discovery-dossier:start dos-' + unit[2:] + ' -->') == 1
        assert store.research_for(run, unit)['current_understanding'] in doc.body
    assert conversion.apply(run, units[0]) == first


def test_enabled_phone_is_queued_and_only_actual_target_readback_completes(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task import ios_sync
    from alchemy_task.core import reminders as rm
    rt, store, run, wid, conversion = joined(tmp_path, settings, data_dir)
    settings.git_transport = 'none'
    ios_sync.save(rt, {'config': {'enabled': True, 'device_id': 'phone-one', 'list_id': 'list-one', 'areas': ['work']}, 'mappings': {}, 'ops': {}, 'conflicts': {}, 'reads': {}, 'notes': {}})
    plan = conversion.prepare(run, wid, choice='create', reason='User chose task.', user_approved=True, area='work', undated=True)
    before_queue = ios_sync.load(rt)
    receipt = conversion.deliver_git(run, wid)
    assert ios_sync.load(rt) == before_queue  # observing queue must not overwrite the live sync engine's state
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
    streams['work'].update(schedule='0 18 * * *', timezone='America/New_York', job_id='job-one', job_binding={'job_id': 'job-one', 'origin_session': 'parent', 'profile': 'test', 'verified': True})
    ctx.state.set('streams', streams)
    ctx.cron['job-one'] = {'name': 'alchemy-task: discovery work', 'deliver': 'origin', 'schedule': '0 18 * * *', 'timezone': 'America/New_York'}
    binding = {'origin_session': 'parent', 'target': 'chat-one', 'send_tool': 'sender', 'read_tool': 'reader', 'send_fields': {'target': 'target', 'text': 'text'}, 'send_id_path': 'id', 'read_fields': {'id': 'message_id'}, 'read_response': {'message_id': 'id', 'target': 'target', 'text': 'text'}, 'scheduled_approved': True}
    binding.update(toolsets=['approved-messaging'], verification_message_id='existing', verification_text='Existing message')
    original_setup = ctx.dispatch_tool
    ctx.dispatch_tool = lambda name, args: {'id': 'existing', 'target': 'chat-one', 'text': 'Existing message'} if name == 'reader' else original_setup(name, args)
    integration.configure_delivery('work', binding, user_approved=True)
    assert ctx.cron['job-one']['deliver'] == 'local'
    digest = integration.digest.prepare('scheduled-digest', stream='work', day='2030-01-01', origin={'session_id': 'parent'}, items=[])
    # An unrelated scheduled job cannot send, whatever session it claims.
    ctx.current_cron_execution = lambda: {'job_id': 'job-other', 'execution_id': 'fire-x', 'profile': 'test', 'scheduled_instant': '2030-01-01T00:00:00Z'}
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
    streams['work'].update(schedule='0 18 * * *', timezone='America/New_York', job_id='job-one', job_binding={'job_id': 'job-one', 'origin_session': 'parent', 'profile': 'test', 'verified': True})
    ctx.state.set('streams', streams)
    ctx.profile_name = 'test'
    ctx.current_cron_execution = lambda: None
    started = integration.start('work', session_id='parent')
    saved = copy.deepcopy(integration.store.get_run(started['run_id']))
    ctx.current_cron_execution = lambda: dict(job_id='job-other', execution_id='fire-one', profile='test', scheduled_instant='2030-01-01T00:00:00Z', source='builtin')
    with pytest.raises(UserError):
        integration.start('work', session_id='new-session')
    ctx.current_cron_execution = lambda: dict(job_id='job-one', execution_id='fire-one', profile='test', scheduled_instant='2030-01-01T00:00:00Z', source='builtin')
    resumed = integration.start('work', session_id='new-session')
    assert resumed['run_id'] == started['run_id']
    assert integration.store.get_run(started['run_id'])['config'] == saved['config']
    assert integration.runner._parent(started['run_id'], 'new-session')
    assert integration.backend(started['run_id'], session_id='new-session')['recovery']['adoptions'][-1]['execution']['execution_id'] == 'fire-one'
    # Any chat of the profile may then take the same run over again (authority by who acts, not where).
    ctx.current_cron_execution = lambda: None
    assert integration.start('work', session_id='third-session')['run_id'] == started['run_id']
    assert integration.store.get_run(started['run_id'])['config'] == saved['config']


def test_manual_run_now_of_the_bound_job_can_start_the_stream(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    streams = ctx.state.get('streams')
    streams['work'].update(schedule='0 18 * * *', timezone='America/New_York', job_id='job-one', job_binding={'job_id': 'job-one', 'origin_session': 'parent', 'profile': 'test', 'verified': True})
    ctx.state.set('streams', streams)
    ctx.profile_name = 'test'
    base = dict(job_id='job-one', execution_id='fire-now', profile='test', scheduled_instant=None, started_at='2030-01-01T02:48:32Z')
    # an off-schedule fire that is not a direct run, or has no start time, is still refused
    ctx.current_cron_execution = lambda: {**base, 'source': 'builtin'}
    with pytest.raises(UserError):
        integration.start('work', session_id='cron-session')
    ctx.current_cron_execution = lambda: {**base, 'source': 'direct', 'started_at': None}
    with pytest.raises(UserError):
        integration.start('work', session_id='cron-session')
    # another job's run now is refused
    ctx.current_cron_execution = lambda: {**base, 'source': 'direct', 'job_id': 'job-other'}
    with pytest.raises(UserError):
        integration.start('work', session_id='cron-session')
    ctx.current_cron_execution = lambda: {**base, 'source': 'direct'}
    started = integration.start('work', session_id='cron-session')
    assert started['run_id']
