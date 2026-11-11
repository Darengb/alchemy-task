"""Bounded acceptance for the five remaining source-derived requirements."""
import copy
import datetime as dt
import json
import pytest
from alchemy_task.core.discovery_identity import UserError
from test_discovery_integration import service, configure
from test_setup import home


def fresh(integration, rt, ctx):
    from alchemy_task import discovery
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    return discovery.create_stream(rt, {'name': 'fresh', 'areas': ['work'],
        'sources': [{'name': 'Feed', 'scope': 'board', 'method': 'reader'}], 'delivery_owner': 'verified_sender', 'user_approved': True}, 'parent')


def binding():
    return {'origin_session': 'parent', 'target': 'chat/topic', 'send_tool': 'sender', 'read_tool': 'reader',
        'send_fields': {'destination': 'target', 'body': 'text'}, 'send_id_path': 'id',
        'read_fields': {'destination': 'target', 'id': 'message_id'},
        'read_response': {'message_id': 'id', 'target': 'destination', 'text': 'body'},
        'scheduled_approved': True, 'toolsets': ['approved-messaging'],
        'verification_message_id': 'existing', 'verification_text': 'Existing origin message'}


def test_fresh_binding_requires_exact_read_then_creates_single_local_job(settings, data_dir, tmp_path, home):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    fresh(integration, rt, ctx)
    original = ctx.dispatch_tool
    calls = []
    def dispatch(tool, args):
        calls.append((tool, args))
        if tool == 'reader':
            return {'id': 'existing', 'destination': 'chat/topic', 'body': 'WRONG'}
        return original(tool, args)
    ctx.dispatch_tool = dispatch
    with pytest.raises(UserError, match='readback'):
        integration.configure_delivery('fresh', binding(), user_approved=True)
    assert not ctx.cron
    def dispatch(tool, args):
        calls.append((tool, args))
        if tool == 'reader': return {'id': 'existing', 'destination': 'chat/topic', 'body': 'Existing origin message'}
        return original(tool, args)
    ctx.dispatch_tool = dispatch
    result = integration.configure_delivery('fresh', binding(), user_approved=True)
    stream = ctx.state.get('streams')['fresh']
    assert result['activation_state'] == stream['activation_state'] == 'ACTIVE'
    assert len(ctx.cron) == 1
    assert ctx.cron[stream['job_id']]['deliver'] == 'local'
    assert 'approved-messaging' in ctx.cron[stream['job_id']]['enabled_toolsets']
    assert not any(tool == 'sender' for tool, _ in calls)
    integration.configure_delivery('fresh', binding(), user_approved=True)
    assert len(ctx.cron) == 1


@pytest.mark.parametrize('mode', ['shadow', 'research_only'])
def test_pilot_retains_full_index_and_skips_never_run_join_or_number(settings, data_dir, tmp_path, mode):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    started = integration.start('work', session_id='parent', mode=mode, pilot_limit=1)
    run = started['run_id']
    items = [{'title': f'Candidate {i}', 'source_ids': [f'source:feed:account:issue:{i}'],
              'prefilter_disposition': 'excluded' if i == 0 else 'research'} for i in range(4)]
    integration.store.add_candidates(run, items)
    integration.store.freeze_index(run, rubric='Full rubric')
    ledger = integration.store.get_run(run)
    assert len(integration.store.candidate_index(run)) == 4
    selection = json.loads((integration.store.run_dir(run) / 'resources' / ledger['resources']['pilot-selection']['sha256']).read_text())
    ids = [c['candidate_id'] for c in ledger['candidates']]
    assert selection['selected'] == ids[1:2] and selection['pilot_skipped'] == ids[2:]
    assert integration.runner._eligible(run) == ids[1:2]
    for skipped in ids[2:]:
        with pytest.raises(UserError, match='eligible'):
            integration.store.reserve_attempt(run, skipped, owner_session='parent')
    join = integration.runner.join(run, session_id='parent', degraded={ids[1]: 'Explicit pilot failure'})
    assert join['joined'] and len(join['failures']) == 1
    assert join['pilot_skipped'] == ids[2:]
    digest = integration.finalize(run, session_id='parent')
    assert not digest['items'] and len(digest['failures']) == 1
    assert not integration.store.get_run(run)['attempts']


@pytest.mark.parametrize('mode,limit', [('production', 1), ('unknown', 1), ('shadow', -1), ('shadow', True), ('shadow', 201)])
def test_bad_pilot_mode_or_limit_fails_closed(settings, data_dir, tmp_path, mode, limit):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    with pytest.raises(UserError):
        integration.start('work', session_id='parent', mode=mode, pilot_limit=limit)
    assert not integration._all_runs()


def saved_input_run(integration):
    run = integration.start('work', session_id='parent', mode='research_only')['run_id']
    store = integration.store
    items = [{'title': f'Original {i}', 'source_ids': [f'source:feed:account:issue:{i}']} for i in range(2)]
    store.add_candidates(run, items)
    for c in store.get_run(run)['candidates']:
        store.put_resource(run, 'source-body-' + c['candidate_id'], [{'body': 'Immutable primary body', 'source_ids': c['source_ids']}])
    store.put_resource(run, 'source-material', [{'candidate_id': c['candidate_id'], 'body': store.resource_info(run, 'source-body-' + c['candidate_id'])} for c in store.get_run(run)['candidates']])
    store.freeze_index(run, rubric='Original rubric')
    ids = [c['candidate_id'] for c in store.get_run(run)['candidates']]
    integration.runner.join(run, session_id='parent', degraded={cid: 'Original research failed' for cid in ids})
    integration.finalize(run, session_id='parent')
    return run


def test_saved_input_replay_clones_date_window_identities_primary_and_distinct_review(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    integration.utcnow = lambda: dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    original = saved_input_run(integration)
    before = copy.deepcopy(integration.store.get_run(original))
    integration.utcnow = lambda: dt.datetime(2030, 2, 3, tzinfo=dt.timezone.utc)
    result = integration.replay(original, operation='saved_input', mode='research_only', session_id='parent', user_approved=True)
    run = result['run_id']
    replay = integration.store.get_run(run)
    assert run != original and replay['business_date'] == before['business_date']
    assert replay['config']['windows'] == before['config']['windows']
    assert integration.store.candidate_index(run) == integration.store.candidate_index(original)
    assert replay['resources']['source-material']['sha256'] == before['resources']['source-material']['sha256']
    assert replay['lineage']['operation'] == 'saved_input' and replay['lineage']['original_run_id'] == original
    assert not replay['attempts'] and not replay.get('review')
    assert integration.store.get_run(original) == before
    ids = [c['candidate_id'] for c in replay['candidates']]
    integration.runner.join(run, session_id='parent', degraded={cid: 'Replay explicitly degraded' for cid in ids})
    review = integration.finalize(run, session_id='parent')
    assert review['run_id'] != integration.digest.get(original)['run_id']
    assert integration.store.get_run(original) == before
    with pytest.raises(UserError, match='production'):
        integration.conversion.prepare(run, ids[0], choice='auto', reason='No old mutation')


@pytest.mark.parametrize('operation', ['fresh_validation', 'targeted_supplement'])
def test_current_alternatives_are_distinct_current_and_explicit_lineage(settings, data_dir, tmp_path, operation):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    integration.utcnow = lambda: dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    original = saved_input_run(integration)
    ids = [c['candidate_id'] for c in integration.store.get_run(original)['candidates']]
    integration.utcnow = lambda: dt.datetime(2030, 2, 3, tzinfo=dt.timezone.utc)
    result = integration.replay(original, operation=operation, mode='shadow', session_id='parent',
                                user_approved=True, candidate_ids=ids[:1] if operation == 'targeted_supplement' else None)
    run = integration.store.get_run(result['run_id'])
    assert run['business_date'] == '2030-02-02'  # New York, midnight UTC
    assert run['config']['windows'] != integration.store.get_run(original)['config']['windows']
    assert not run['candidates'] and not run['index_revision']
    assert run['lineage']['operation'] == operation and run['lineage']['original_run_id'] == original


@pytest.mark.parametrize('operation,mode', [('bogus', 'shadow'), ('saved_input', 'bogus'), ('saved_input', 'production'), ('saved_input', '')])
def test_unknown_replay_operations_modes_refuse(settings, data_dir, tmp_path, operation, mode):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    original = saved_input_run(integration)
    with pytest.raises(UserError):
        integration.replay(original, operation=operation, mode=mode, session_id='parent', user_approved=True)
    assert len(integration._all_runs()) == 1


def test_replay_corrupt_cache_refuses_without_creating_run(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    original = saved_input_run(integration)
    info = integration.store.resource_info(original, 'source-material')
    (integration.store.run_dir(original) / 'resources' / info['sha256']).write_text('corrupt')
    with pytest.raises(UserError, match='integrity'):
        integration.replay(original, operation='saved_input', mode='shadow', session_id='parent', user_approved=True)
    assert len(integration._all_runs()) == 1


def test_real_public_sessiondb_origin_new_session_same_topic(settings, data_dir, tmp_path):
    from hermes_state import SessionDB
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    integration.home.mkdir()
    db = SessionDB(db_path=integration.home / 'state.db')
    try:
        for sid, topic in [('parent', '7'), ('new', '7'), ('other', '8')]:
            db.create_session(sid, source='telegram')
            db.record_gateway_session_peer(sid, source='telegram', session_key='telegram:123:' + topic,
                chat_id='123', thread_id=topic, chat_type='group')
    finally:
        db.close()
    assert integration.origin_authorized(integration._stream('work'), 'new')
    assert not integration.origin_authorized(integration._stream('work'), 'other')
    assert not integration.origin_authorized(integration._stream('work'), 'missing')
    configure(integration)
    started = integration.start('work', session_id='parent')
    resumed = integration.start('work', session_id='new')
    assert resumed['run_id'] == started['run_id']
    # origin_authorized is display only: another chat of the profile still acts on the run.
    assert integration.start('work', session_id='other')['run_id'] == started['run_id']
    with pytest.raises(UserError, match='profile'):
        integration.start('work', session_id='missing')


def test_targeted_supplement_accounts_missing_ids_without_substituting_equal_count(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    original = saved_input_run(integration)
    old = integration.store.get_run(original)
    wanted = old['candidates'][0]['candidate_id']
    result = integration.replay(original, operation='targeted_supplement', mode='shadow',
        session_id='parent', user_approved=True, candidate_ids=[wanted])
    run = result['run_id']
    # One current item, same total as requested, but a DIFFERENT typed identity.
    current = {'title': 'New replacement', 'source_ids': ['source:feed:account:issue:replacement'], 'source_revision': 'v1'}
    integration.store.enqueue_backlog('work-shadow', 'feed', [{**current, 'candidate': current}])
    integration.store.put_resource(run, 'collection-feed', {'source_key': 'feed', 'status': 'complete'})
    integration.freeze(run, session_id='parent')
    ledger = integration.store.get_run(run)
    selection = json.loads((integration.store.run_dir(run) / 'resources' / ledger['resources']['supplement-selection']['sha256']).read_text())
    assert selection['missing_current'] == [wanted] and selection['present'] == []
    assert not ledger['candidates']
    integration.runner.join(run, session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    assert 'Original 0' in digest['text'] and 'not found' in digest['text']


def test_replayed_same_research_has_distinct_numbered_review(data_dir):
    from alchemy_task.discovery_digest import DiscoveryDigest
    digest = DiscoveryDigest(data_dir / 'discovery')
    item = {'unit_id': 'same', 'research_revision': 'same', 'title': 'Same accepted action', 'kind': 'new'}
    first = digest.prepare('original', stream='work', day='2030-01-01', origin={'session_id': 'parent'}, items=[item])
    second = digest.prepare('replay', stream='work', day='2030-01-01', origin={'session_id': 'parent'}, items=[item], review_namespace='replay')
    assert len(second['items']) == 1
    assert first['items'][0]['proposal_id'] != second['items'][0]['proposal_id']
    assert second['items'][0]['number'] == 2


def test_replay_keeps_referenced_original_artifacts_during_prune(data_dir):
    import os
    from alchemy_task.core.discovery_state import DiscoveryStore
    store = DiscoveryStore(data_dir / 'discovery')
    original = store.init_run(stream='old', config={'mode': 'research_only'})
    store.save_review(original, {'joined': {'accepted': [], 'failures': []}})
    store.init_run(stream='new', lineage={'operation': 'saved_input', 'original_run_id': original})
    ledger = store.run_dir(original) / 'ledger.json'
    os.utime(ledger, (1, 1))
    store.prune(days=1)
    assert ledger.exists()


def test_approved_binding_resumes_public_paused_job_and_reads_back(settings, data_dir, tmp_path, home):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    fresh(integration, rt, ctx)
    original = ctx.dispatch_tool
    def dispatch(tool, args):
        if tool == 'reader': return {'id': 'existing', 'destination': 'chat/topic', 'body': 'Existing origin message'}
        if tool == 'cronjob_manage' and args['action'] == 'resume':
            ctx.cron[args['job_id']].update(enabled=True, state='scheduled')
            return {'success': True}
        return original(tool, args)
    ctx.dispatch_tool = dispatch
    result = integration.configure_delivery('fresh', binding(), user_approved=True)
    jid = result['job_id']
    ctx.cron[jid].update(enabled=False, state='paused')
    integration.configure_delivery('fresh', binding(), user_approved=True)
    assert ctx.cron[jid]['enabled'] is True and ctx.cron[jid]['state'] == 'scheduled'
    assert len(ctx.cron) == 1


def test_origin_authorization_survives_only_proven_same_chat(settings, data_dir, tmp_path, monkeypatch):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    origins = {'parent': {'profile': 'test', 'source': 'telegram', 'chat_id': '123', 'thread_id': '7'},
               'new': {'profile': 'test', 'source': 'telegram', 'chat_id': '123', 'thread_id': '7'},
               'other': {'profile': 'test', 'source': 'telegram', 'chat_id': '123', 'thread_id': '8'}}
    monkeypatch.setattr(integration, '_host_origin', lambda session: origins.get(session))
    stream = integration._stream('work')
    assert integration.origin_authorized(stream, 'new')
    assert not integration.origin_authorized(stream, 'other')
    assert not integration.origin_authorized(stream, 'unknown')


def test_structured_correction_overlays_active_sections_retains_original(settings, data_dir, tmp_path):
    from test_discovery_conversion import custom_joined
    rt, store, run, wid, conversion = custom_joined(settings, data_dir, tmp_path, [],
        implementation_context=['Rejected instruction'], dependencies_and_risks=['Rejected dependency'])
    overlay = {'new_information': ['Current factual summary'], 'current_understanding': 'Approved current state',
        'decisions_and_open_questions': {'decisions': ['Verification only'], 'open_questions': ['Which proof?']},
        'implementation_context': ['Read existing proof'], 'dependencies_and_risks': ['Read access required']}
    original = copy.deepcopy(store.research_for(run, wid))
    conversion.prepare(run, wid, choice='create', reason='User corrected recommendations', user_approved=True,
        area='work', undated=True, active_goal='Verify only', correction_overlay=overlay)
    receipt = conversion.apply(run, wid)
    body = rt.store().resolve(receipt['task_id']).body
    active, history = body.split('### Historical Accepted Recommendation', 1)
    assert 'Rejected instruction' not in active and 'Rejected dependency' not in active
    assert all(value in active for value in ['Read existing proof', 'Which proof?', 'Read access required', 'Current factual summary'])
    assert 'Rejected instruction' in history
    assert store.research_for(run, wid) == original


@pytest.mark.parametrize('overlay', [{'exact_source_ids': []}, {'implementation_context': 'bad'}, {'decisions_and_open_questions': {'decisions': []}}])
def test_bad_correction_overlay_refuses_before_task_write(settings, data_dir, tmp_path, overlay):
    from test_discovery_conversion import custom_joined
    rt, store, run, wid, conversion = custom_joined(settings, data_dir, tmp_path, [])
    before = len(rt.store().scan().tasks)
    with pytest.raises((ValueError, UserError)):
        conversion.prepare(run, wid, choice='create', reason='Correction', user_approved=True,
            area='work', undated=True, correction_overlay=overlay)
    assert len(rt.store().scan().tasks) == before
