"""Regression cases for the dashboard remediation review."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_discovery_dashboard import fixture_service, client_for


def _two_joined(tmp_path, settings, data_dir):
    from test_discovery_state import setup, prepare, read_all
    from test_discovery_schema import bundle
    from alchemy_task.core.store import TaskStore

    store, run, parents = setup(data_dir, count=2)
    for index, parent in enumerate(parents):
        attempt = prepare(store, run, parent['candidate_id'])
        payload = bundle()
        payload['candidate_id'] = parent['candidate_id']
        payload['workstreams'][0]['exact_source_ids'][0]['message_ts'] = f'171.{index + 2}'
        payload['workstreams'][0]['title'] = f'Independent action {index}'
        receipt = store.spool_payload(run, attempt['token'], payload)
        store.observe_terminal(run, attempt['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
        read_all(store, run, receipt['resource'], 'parent')
        store.accept_attempt(run, attempt['token'], payload_sha256=receipt['payload_sha256'],
                             assessment={'accepted': True, 'reason': 'Distinct verified action.'}, reader='parent')
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [p['candidate_id'] for p in parents], 'failures': []})
    wid = next(c['candidate_id'] for c in store.get_run(run)['candidates'] if c.get('parent_candidate_id'))
    rt = SimpleNamespace(data_dir=data_dir, settings=settings, store=lambda: TaskStore(settings, data_dir))
    return rt, store, run, wid, None


@pytest.mark.parametrize('dismissed', [False, True], ids=['not-approved', 'dismissed'])
def test_resume_cannot_approve_or_revive_an_unwritten_plan(tmp_path, settings, data_dir, monkeypatch, dismissed):
    from alchemy_task.core.discovery_identity import UserError
    from alchemy_task.core.store import NeedsInput
    import subprocess

    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir, _two_joined)
    client, owner = client_for(service, monkeypatch)
    prefix = '/api/plugins/alchemy-task'
    ids = [p['proposal_id'] for p in service.digest.get(run)['items']]
    before = len(rt.store().scan().tasks)
    with pytest.raises((UserError, NeedsInput), match='due date'):
        service.decide({'approve': ids, 'edits': {
            ids[0]: {'choice': 'create', 'undated': True, 'area': 'work'},
            ids[1]: {'choice': 'create', 'area': 'work'},
        }}, session_id='parent')
    plan, receipt = service.conversion._paths(run, wid)
    original_plan = plan.read_bytes()
    assert len(rt.store().scan().tasks) == before and not receipt.exists()
    if dismissed:
        response = client.post(prefix + '/proposals/' + proposal['proposal_id'] + '/dismiss', headers=owner, json={})
        assert response.json()['state'] == 'dismissed'
    def git_head():
        return subprocess.check_output(['git', '-C', str(settings.workspace_root), 'rev-parse', 'HEAD'])
    original_head = git_head()
    response = client.post(prefix + '/runs/' + run + '/units/' + wid + '/resume', headers=owner, json={})
    assert response.json()['ok'] is False
    assert response.json()['error']['code'] == ('already_resolved' if dismissed else 'invalid_request')
    assert len(rt.store().scan().tasks) == before
    assert git_head() == original_head
    assert plan.read_bytes() == original_plan and not receipt.exists()
    assert service.digest._load()['proposals'][proposal['proposal_id']]['state'] == ('dismissed' if dismissed else 'pending')


def test_real_git_hook_does_not_block_unrelated_http_request(tmp_path, settings, data_dir, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from hermes_cli import web_server
    from alchemy_task.dashboard import discovery_api

    service, _, _, _, proposal = fixture_service(tmp_path, settings, data_dir)
    hook = Path(settings.workspace_root) / '.git' / 'hooks' / 'pre-commit'
    hook.write_text('#!/bin/sh\nsleep 0.4\n')
    hook.chmod(0o700)
    monkeypatch.setattr(discovery_api, '_service', lambda: service)
    app = FastAPI()
    app.include_router(discovery_api.router, prefix='/api/plugins/alchemy-task')
    events = []
    @app.get('/unrelated')
    async def unrelated():
        events.append('unrelated')
        return {'ok': True}
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            async def approve():
                response = await client.post('/api/plugins/alchemy-task/proposals/' + proposal['proposal_id'] + '/approve',
                    headers={web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN},
                    json={'choice': 'create', 'undated': True, 'area': 'work'})
                events.append('approve_complete')
                assert response.json()['receipt']['state'] == 'complete'
            async def other():
                await asyncio.sleep(0.02)
                assert (await client.get('/unrelated')).json()['ok'] is True
            await asyncio.gather(approve(), other())
        assert events == ['unrelated', 'approve_complete']
    asyncio.run(exercise())
