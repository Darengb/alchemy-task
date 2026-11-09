"""Synthetic discovery dashboard behavior; mounted host tests live separately."""
import datetime as dt
import json
import pytest
from test_discovery_conversion import joined
from test_setup import SetupCtx
from alchemy_task.discovery_integration import DiscoveryIntegration
from alchemy_task.core.gitops import GitDelivery


def client_for(service, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from alchemy_task.dashboard import discovery_api
    from hermes_cli import web_server
    app = FastAPI()
    app.include_router(discovery_api.router, prefix='/api/plugins/alchemy-task')
    monkeypatch.setattr(discovery_api, '_service', lambda: service)
    return TestClient(app), {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}


def test_http_create_idempotent_and_owner_only(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    base = '/api/plugins/alchemy-task'
    assert client.get(base + '/runs').status_code == 401
    assert client.get(base + '/runs', headers=owner).json()['runs'][0]['run_id'] == run
    before = len(rt.store().scan().tasks)
    url = base + '/proposals/' + proposal['proposal_id'] + '/approve'
    receipt = client.post(url, headers=owner, json={'choice': 'create', 'due': '2030-01-09', 'area': 'work'}).json()
    assert receipt['ok'], receipt
    assert receipt['receipt']['state'] == 'complete'
    assert client.post(url, headers=owner, json={'choice': 'create'}).json() == receipt
    assert len(rt.store().scan().tasks) == before + 1
    item = client.get(base + '/runs/' + run, headers=owner).json()['proposals'][0]
    assert item['state'] == 'complete'
    assert item['result']['task_id'] == receipt['receipt']['task_id']
    assert item['result']['operation'] == 'created'


def fixture_service(tmp_path, settings, data_dir, seed=joined):
    rt, store, run, wid, _ = seed(tmp_path, settings, data_dir)
    ctx = SetupCtx({'workspace_root': settings.workspace_root, 'timezone': settings.timezone}, data_dir)
    rt.ctx = ctx
    rt.git = lambda: GitDelivery(settings, data_dir)
    ctx.state.set('streams', {'work': {'name': 'work', 'label': '', 'origin_session': 'parent'}})
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run)
        ledger['origin'] = {'session_id': 'parent', 'deliver': 'origin'}
        ledger['config']['timezone'] = 'America/New_York'
        store._save(run, ledger)
    service = DiscoveryIntegration(rt, profile_home=tmp_path / 'profile')
    service.utcnow = lambda: dt.datetime(2030, 1, 2, tzinfo=dt.timezone.utc)
    for candidate in service.store.get_run(run)['candidates']:
        if candidate.get('parent_candidate_id'):
            service.record_decision(run, candidate['candidate_id'], decision='propose', reason='Independent substantive action.', session_id='parent')
    digest = service.finalize(run, session_id='parent')
    return service, rt, run, wid, digest['items'][0]


def test_projection_reads_current_ledger_preserving_frozen_fields(tmp_path, settings, data_dir):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    service.digest.decide(proposal['proposal_id'], 'dismissed')
    result = service.project_run(service.store.get_run(run))
    item = result['proposals'][0]
    assert item == {**proposal, 'state': 'dismissed', 'expired': False}
    assert result['summary'] == dict(pending=0, approved=0, complete=0, dismissed=1,
                                    auto_updated=0, conflicts=0, failures=0, deferred=0)
    assert result['degraded'] is False
    assert result['outcomes'] == []
    assert service.digest.get(run)['items'][0] == proposal


@pytest.mark.parametrize('body,code', [
    ({'choice': 'create', 'area': 'work'}, 'needs_due'),
    ({'choice': 'create', 'undated': True}, 'needs_area'),
    ({'choice': 'other'}, 'invalid_choice'),
    ({'choice': 'update'}, 'target_required'),
    ({'choice': 'create', 'allow_expired': 'true'}, 'invalid_request'),
    ({'choice': 'create', 'profile': 'other'}, 'invalid_request'),
    ({'choice': 'create', 'owner': True}, 'invalid_request'),
])
def test_http_errors_write_no_tasks(tmp_path, settings, data_dir, monkeypatch, body, code):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    before = {t.path: t.path.read_bytes() for t in rt.store().scan().tasks}
    response = client.post('/api/plugins/alchemy-task/proposals/' + proposal['proposal_id'] + '/approve', headers=owner, json=body)
    assert response.json()['error']['code'] == code, response.text
    assert {t.path: t.path.read_bytes() for t in rt.store().scan().tasks} == before


@pytest.mark.parametrize('mode', ['shadow', 'research_only'])
def test_nonproduction_mutations_fail_closed(tmp_path, settings, data_dir, monkeypatch, mode):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    with service.store._lock(service.store._run_lock_name(run)):
        ledger = service.store.get_run(run); ledger['config']['mode'] = mode; service.store._save(run, ledger)
    client, owner = client_for(service, monkeypatch)
    prefix = '/api/plugins/alchemy-task'
    for path in ['/proposals/' + proposal['proposal_id'] + '/approve', '/proposals/' + proposal['proposal_id'] + '/dismiss', '/runs/' + run + '/units/' + wid + '/resume']:
        assert client.post(prefix + path, headers=owner, json={'choice': 'create'} if path.endswith('approve') else {}).json()['error']['code'] == 'not_production'


def test_expiry_timezone_override_and_unchanged_chat(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    prefix = '/api/plugins/alchemy-task'
    service.utcnow = lambda: dt.datetime(2030, 1, 9, 4, 59, tzinfo=dt.timezone.utc)
    assert client.get(prefix + '/runs', headers=owner).json()['runs'][0]['proposals'][0]['expired'] is False
    service.utcnow = lambda: dt.datetime(2030, 1, 9, 5, 0, tzinfo=dt.timezone.utc)
    assert client.get(prefix + '/runs', headers=owner).json()['runs'][0]['proposals'][0]['expired'] is True
    url = prefix + '/proposals/' + proposal['proposal_id'] + '/approve'
    assert client.post(url, headers=owner, json={'choice': 'create'}).json()['error']['code'] == 'expired'
    with pytest.raises(Exception, match='expired'):
        service.decide({'approve': ['1']}, session_id='parent')
    response = client.post(url, headers=owner, json={'choice': 'create', 'area': 'work', 'undated': True, 'allow_expired': True})
    assert response.json()['receipt']['state'] == 'complete', response.text


def test_dismissal_and_exact_ids(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    prefix = '/api/plugins/alchemy-task/proposals/'
    assert client.post(prefix + '1/dismiss', headers=owner, json={}).status_code == 404
    url = prefix + proposal['proposal_id']
    assert client.post(url + '/dismiss', headers=owner, json={}).json()['state'] == 'dismissed'
    assert client.post(url + '/approve', headers=owner, json={'choice': 'create'}).json()['error']['code'] == 'already_resolved'
    assert client.get('/api/plugins/alchemy-task/runs', headers=owner).json()['runs'][0]['summary']['dismissed'] == 1


def test_real_host_mount_auth_and_profile_boundary(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    home = tmp_path / 'host-home'; home.mkdir()
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'HERMES_HOME': str(home)}
    import hermes_cli
    core_root = Path(hermes_cli.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'tests' / 'dashboard_host_probe.py'), str(root), str(home), str(core_root)],
                            env=env, text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'actual host mount/auth/profile PASS' in result.stdout


def test_real_host_accepts_serving_profile_selector_on_every_route(tmp_path):
    """The host SPA sends ?profile=<serving>; list, detail, approve, dismiss and resume must work."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    import hermes_cli
    home = tmp_path / 'host-home'; home.mkdir()
    root = Path(__file__).resolve().parents[1]
    core_root = Path(hermes_cli.__file__).resolve().parents[1]
    import pytest as _pytest
    extra = [str(Path(_pytest.__file__).resolve().parents[1])]
    try:
        import python_multipart
        extra.append(str(Path(python_multipart.__file__).resolve().parents[1]))
    except ImportError:
        pass
    extra = os.pathsep.join(extra)
    result = subprocess.run([sys.executable, str(root / 'tests' / 'dashboard_serving_profile_probe.py'), str(root), str(home), str(core_root), extra],
                            env={**os.environ, 'HERMES_HOME': str(home)}, text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'serving profile selector PASS' in result.stdout


def test_route_itself_refuses_a_different_profile_selector_without_writes(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    before = {t.path: t.path.read_bytes() for t in rt.store().scan().tasks}
    base = '/api/plugins/alchemy-task'
    for path in ('/runs?profile=other-profile', '/runs/' + run + '?profile=other-profile'):
        assert client.get(base + path, headers=owner).json()['error']['code'] == 'invalid_request'
    response = client.post(base + '/proposals/' + proposal['proposal_id'] + '/approve?profile=other-profile', headers=owner,
                           json={'choice': 'create', 'due': '2030-01-09', 'area': 'work'})
    assert response.status_code == 400 and response.json()['error']['code'] == 'invalid_request', response.text
    assert {t.path: t.path.read_bytes() for t in rt.store().scan().tasks} == before
    assert service.digest._load()['proposals'][proposal['proposal_id']]['state'] == 'pending'


def test_unknown_run_is_not_found_like_unknown_proposal(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    base = '/api/plugins/alchemy-task'
    before = {t.path: t.path.read_bytes() for t in rt.store().scan().tasks}
    for response in (client.get(base + '/runs/' + 'f' * 32, headers=owner),
                     client.post(base + '/runs/' + 'f' * 32 + '/units/' + wid + '/resume', headers=owner, json={}),
                     client.post(base + '/proposals/p_missing/approve', headers=owner, json={'choice': 'create'})):
        assert response.status_code == 404 and response.json()['error']['code'] == 'not_found', response.text
    assert {t.path: t.path.read_bytes() for t in rt.store().scan().tasks} == before


@pytest.mark.parametrize('prepared', [False, True])
def test_semantic_stale_revision_before_and_after_preparation(tmp_path, settings, data_dir, monkeypatch, prepared):
    from test_discovery_conversion import custom_joined
    from alchemy_task.core.store import TaskStore
    from alchemy_task.core.taskfile import content_hash
    tasks = TaskStore(settings, data_dir)
    doc = tasks.create(title='Related action', area='work', undated=True, research=False)
    seed = lambda tmp, settings, data: custom_joined(settings, data, tmp, [{'path': tasks.rel(doc.path), 'match_basis': 'related_only'}])
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir, seed)
    client, owner = client_for(service, monkeypatch)
    body = {'choice': 'update', 'target_task_id': doc.task_id, 'expected_revision': content_hash(doc.raw)}
    if prepared:
        service.conversion.prepare(run, wid, **body, user_approved=True, reason='User approved exact immutable proposal ' + proposal['proposal_id'])
    doc.path.write_bytes(doc.raw + b'\nNew user edit\n')
    before = {t.path: t.path.read_bytes() for t in tasks.scan().tasks}
    response = client.post('/api/plugins/alchemy-task/proposals/' + proposal['proposal_id'] + '/approve', headers=owner, json=body)
    assert response.status_code == 409 and response.json()['error']['code'] == 'stale_revision', response.text
    assert {t.path: t.path.read_bytes() for t in tasks.scan().tasks} == before


def test_pending_receipt_duplicate_and_resume_saved_plan(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    original = rt.git
    class Offline:
        def deliver(self, *args): raise OSError('Synthetic local remote temporarily unavailable')
    rt.git = lambda: Offline()
    prefix = '/api/plugins/alchemy-task'
    url = prefix + '/proposals/' + proposal['proposal_id'] + '/approve'
    before = len(rt.store().scan().tasks)
    first = client.post(url, headers=owner, json={'choice': 'create', 'undated': True, 'area': 'work'}).json()
    assert first['receipt']['state'] == 'git_pending', first
    plan = service.conversion._paths(run, wid)[0]
    saved_plan = plan.read_bytes()
    assert client.post(url, headers=owner, json={'choice': 'create'}).json() == first
    assert len(rt.store().scan().tasks) == before + 1
    rt.git = original
    resumed = client.post(prefix + '/runs/' + run + '/units/' + wid + '/resume', headers=owner, json={}).json()
    assert resumed['receipt']['state'] == 'complete'
    assert resumed['receipt']['task_id'] == first['receipt']['task_id']
    assert plan.read_bytes() == saved_plan
    assert len(rt.store().scan().tasks) == before + 1


def test_selection_update_selects_only_nominated_target(tmp_path, settings, data_dir, monkeypatch):
    from test_discovery_conversion import custom_joined
    from alchemy_task.core.store import TaskStore
    from alchemy_task.core.taskfile import content_hash
    tasks = TaskStore(settings, data_dir)
    docs = [tasks.create(title=title, area='work', undated=True, research=False) for title in ('Related action', 'Other action')]
    seed = lambda tmp, settings, data: custom_joined(settings, data, tmp, [{'path': tasks.rel(d.path), 'match_basis': 'related_only'} for d in docs])
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir, seed)
    assert proposal['kind'] == 'selection'
    client, owner = client_for(service, monkeypatch)
    url = '/api/plugins/alchemy-task/proposals/' + proposal['proposal_id'] + '/approve'
    assert client.post(url, headers=owner, json={'choice': 'update'}).json()['error']['code'] == 'target_required'
    result = client.post(url, headers=owner, json={'choice': 'update', 'target_task_id': docs[0].task_id, 'expected_revision': content_hash(docs[0].raw)}).json()
    assert result['receipt']['state'] == 'complete', result
    assert docs[0].path.read_bytes() != docs[0].raw
    assert docs[1].path.read_bytes() == docs[1].raw
    item = client.get('/api/plugins/alchemy-task/runs', headers=owner).json()['runs'][0]['proposals'][0]
    assert item['result']['operation'] == 'updated'


def test_model_cannot_claim_http_authority_or_override_expiry(tmp_path, settings, data_dir):
    from alchemy_task.discovery_integration import register
    from alchemy_task import runtime, task_tools
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    runtime.bind(rt.ctx)
    tools = {}
    rt.ctx.register_tool = lambda **kw: tools.update({kw['name']: kw['handler']})
    rt.ctx.register_hook = lambda *a, **kw: None
    register(rt.ctx, integration=service)
    assert json.loads(tools['discovery_runs']({'dashboard_owner': True}, session_id='outsider'))['ok'] is False
    assert json.loads(tools['discovery_runs']({}, session_id='outsider'))['result']['runs'] == []
    # The durable host start/binding fixture is the same verified-child path used
    # by production tool wrappers, not caller-supplied session arguments.
    child_run = service.store.init_run(origin={'session_id': 'parent'})
    parent = service.store.add_candidates(child_run, [{'title': 'Read only', 'source_ids': ['source:feed:account:issue:child']}])[0]
    service.store.freeze_index(child_run, rubric='Read only')
    attempt = service.store.reserve_attempt(child_run, parent['candidate_id'], owner_session='parent')
    service.store.record_start(child_run, parent_session='parent', child_session='child', subagent_id='sa-child')
    service.store.bind_attempt(child_run, attempt['token'], {'subagent_id': 'sa-child'}, owner_session='parent')
    before = len(rt.store().scan().tasks)
    for name, args in [('discovery_runs', {}), ('discovery_conversion_recover', {'run_id': run, 'unit_id': wid})]:
        refused = json.loads(tools[name]({**args, 'dashboard_owner': True}, session_id='child'))
        assert refused['ok'] is False and 'child' in str(refused).lower()
    assert len(rt.store().scan().tasks) == before


def test_approve_one_leaves_sibling_pending(tmp_path, settings, data_dir, monkeypatch):
    from test_discovery_state import setup, prepare, read_all
    from test_discovery_schema import bundle
    from alchemy_task.core.store import TaskStore
    from types import SimpleNamespace
    def seed(tmp, settings, data):
        store, run, parents = setup(data, count=2)
        for i, parent in enumerate(parents):
            attempt = prepare(store, run, parent['candidate_id'])
            payload = bundle(); payload['candidate_id'] = parent['candidate_id']
            payload['workstreams'][0]['exact_source_ids'][0]['message_ts'] = f'171.{i+2}'
            payload['workstreams'][0]['title'] = f'Independent action {i}'
            receipt = store.spool_payload(run, attempt['token'], payload)
            store.observe_terminal(run, attempt['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
            read_all(store, run, receipt['resource'], 'parent')
            store.accept_attempt(run, attempt['token'], payload_sha256=receipt['payload_sha256'], assessment={'accepted': True, 'reason': 'Distinct verified action.'}, reader='parent')
        store.put_resource(run, 'join-record', {'joined': True, 'accepted': [p['candidate_id'] for p in parents], 'failures': []})
        wid = next(c['candidate_id'] for c in store.get_run(run)['candidates'] if c.get('parent_candidate_id'))
        return SimpleNamespace(data_dir=data, settings=settings, store=lambda: TaskStore(settings, data)), store, run, wid, None
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir, seed)
    client, owner = client_for(service, monkeypatch)
    response = client.post('/api/plugins/alchemy-task/proposals/' + proposal['proposal_id'] + '/approve', headers=owner,
                           json={'choice': 'create', 'undated': True, 'area': 'work'})
    assert response.json()['receipt']['state'] == 'complete', response.text
    record = client.get('/api/plugins/alchemy-task/runs', headers=owner).json()['runs'][0]
    assert record['summary']['complete'] == 1 and record['summary']['pending'] == 1


@pytest.mark.parametrize('raw', ['{', '[]', 'null', '{"undated":1}'])
def test_malformed_http_bodies_are_structured(tmp_path, settings, data_dir, monkeypatch, raw):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    response = client.post('/api/plugins/alchemy-task/proposals/' + proposal['proposal_id'] + '/approve', headers=owner, content=raw)
    assert response.json()['ok'] is False and response.json()['error']['code'] == 'invalid_request'


def test_run_list_newest_filters_and_full_summaries(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    later = service.store.init_run(stream='other', business_date='2030-01-02',
        config={'stream_name': 'other', 'mode': 'shadow', 'timezone': 'UTC', 'sources': []}, origin={'session_id': 'other-origin'})
    client, owner = client_for(service, monkeypatch)
    url = '/api/plugins/alchemy-task/runs'
    records = client.get(url, headers=owner).json()['runs']
    assert [r['run_id'] for r in records] == [later, run]
    assert all(set(r['summary']) == {'pending', 'approved', 'complete', 'dismissed', 'auto_updated', 'conflicts', 'failures', 'deferred'} for r in records)
    assert [r['run_id'] for r in client.get(url + '?stream=work', headers=owner).json()['runs']] == [run]
    assert [r['run_id'] for r in client.get(url + '?day_from=2030-01-02&day_to=2030-01-02', headers=owner).json()['runs']] == [later]
    assert client.get(url + '?day_from=bad', headers=owner).json()['error']['code'] == 'invalid_request'


def test_existing_outcomes_keep_resume_and_real_timestamp_only(tmp_path, settings, data_dir):
    from alchemy_task.core.discovery_state import atomic_json
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    data = service.digest._load()
    data['digests'][run]['outcomes'] = [{'unit_id': wid, 'task_id': 'synthetic-task', 'title': 'Existing task',
        'status': 'git_pending', 'resume_action': {'run_id': run, 'unit_id': wid}, 'extra': 'preserved'}]
    atomic_json(service.digest.path, data)
    projected = service.project_run(service.store.get_run(run))
    assert projected['outcomes'][0] == data['digests'][run]['outcomes'][0]
    assert projected['summary']['auto_updated'] == 1
    assert 'applied_at' not in projected['outcomes'][0]
    _, receipt_path = service.conversion._paths(run, wid)
    atomic_json(receipt_path, {'unit_id': wid, 'task_id': 'synthetic-task', 'state': 'complete', 'applied_at': '2030-01-02T00:00:00+00:00'})
    projected = service.project_run(service.store.get_run(run))
    assert projected['outcomes'][0]['applied_at'] == '2030-01-02T00:00:00+00:00'
    assert projected['outcomes'][0]['resume_action'] is None
    assert projected['outcomes'][0]['extra'] == 'preserved'
    assert projected['summary']['auto_updated'] == 1


def test_frozen_digest_failure_remains_visible_and_degraded(tmp_path, settings, data_dir):
    from alchemy_task.core.discovery_state import atomic_json
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    data = service.digest._load()
    data['digests'][run]['failures'].append({'title': 'Retained candidate', 'reason': 'Not found in current supplement window'})
    atomic_json(service.digest.path, data)
    projected = service.project_run(service.store.get_run(run))
    assert projected['summary']['failures'] == 1
    assert projected['degraded'] is True
    assert projected['failures'][0]['title'] == 'Retained candidate'
    with service.store._lock(service.store._run_lock_name(run)):
        ledger = service.store.get_run(run)
        ledger['errors'].append({'reason': 'Not found in current supplement window'})
        service.store._save(run, ledger)
    projected = service.project_run(service.store.get_run(run))
    assert projected['summary']['failures'] == 1
