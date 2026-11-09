"""Dashboard approval outcomes (ported review prototypes): tasks, commits and receipts the owner sees.

Kills two mutants the shipped dashboard tests let survive: the saved-receipt
short-circuit before expiry/choice validation, and an off-by-one expiry day.
"""
import asyncio
import datetime as dt
import subprocess
from pathlib import Path

import pytest

from test_discovery_dashboard import fixture_service, client_for

APPROVE = '/api/plugins/alchemy-task/proposals/{}/approve'
EXPIRED_NOW = dt.datetime(2030, 2, 1, 12, tzinfo=dt.timezone.utc)
CREATE = {'choice': 'create', 'undated': True, 'area': 'work'}


def _head(settings):
    return subprocess.check_output(['git', '-C', str(settings.workspace_root), 'rev-parse', 'HEAD'], text=True).strip()


def _commits(settings, since):
    return subprocess.check_output(['git', '-C', str(settings.workspace_root), 'rev-list', since + '..HEAD'], text=True).split()


def _task_bytes(rt):
    return {t.path: t.path.read_bytes() for t in rt.store().scan().tasks}


def _state(service, run):
    return service.project_run(service.store.get_run(run))['proposals'][0]


@pytest.mark.parametrize('same_body', [True, False], ids=['identical', 'conflicting-edits'])
def test_concurrent_approvals_create_exactly_one_task_and_commit(tmp_path, settings, data_dir, monkeypatch, same_body):
    import httpx
    from fastapi import FastAPI
    from hermes_cli import web_server
    from alchemy_task.dashboard import discovery_api
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    hook = Path(settings.workspace_root) / '.git' / 'hooks' / 'pre-commit'
    hook.write_text('#!/bin/sh\nsleep 0.3\n')  # widen the race window
    hook.chmod(0o700)
    monkeypatch.setattr(discovery_api, '_service', lambda: service)
    app = FastAPI()
    app.include_router(discovery_api.router, prefix='/api/plugins/alchemy-task')
    before, head = len(_task_bytes(rt)), _head(settings)
    headers = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}
    bodies = [dict(CREATE) for _ in range(4)]
    if not same_body:
        bodies[1] = {'choice': 'create', 'due': '2030-02-01', 'area': 'work'}
        bodies[3] = {'choice': 'create', 'undated': True, 'area': 'home'}

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
            return await asyncio.gather(*[c.post(APPROVE.format(proposal['proposal_id']), headers=headers, json=b) for b in bodies])
    responses = asyncio.run(go())
    assert all(r.status_code < 500 for r in responses), [(r.status_code, r.text[:200]) for r in responses]
    payloads = [r.json() for r in responses]
    accepted = [p for p in payloads if p.get('ok')]
    assert accepted and len({p['receipt']['task_id'] for p in accepted}) == 1, payloads
    assert all(p['error']['code'] in {'invalid_request', 'stale_revision'} for p in payloads if not p.get('ok')), payloads
    assert len(_task_bytes(rt)) == before + 1 and len(_commits(settings, head)) == 1
    item = _state(service, run)
    assert item['state'] == 'complete' and item['result']['task_id'] == accepted[0]['receipt']['task_id']


def test_chat_approved_first_then_dashboard_returns_same_receipt(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    head = _head(settings)
    chat = service.decide({'approve': ['1'], 'edits': {'1': {'undated': True, 'area': 'work'}}}, session_id='parent')
    assert len(_commits(settings, head)) == 1
    after_chat = (_task_bytes(rt), _head(settings))
    r = client.post(APPROVE.format(proposal['proposal_id']), headers=owner, json=CREATE)
    assert r.json() == {'ok': True, 'receipt': chat['results'][0]}
    assert (_task_bytes(rt), _head(settings)) == after_chat


@pytest.mark.parametrize('allow', [None, False])
def test_expired_without_override_writes_nothing_and_chat_still_refuses(tmp_path, settings, data_dir, monkeypatch, allow):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    service.utcnow = lambda: EXPIRED_NOW
    head, before = _head(settings), _task_bytes(rt)
    body = dict(CREATE) if allow is None else {**CREATE, 'allow_expired': allow}
    r = client.post(APPROVE.format(proposal['proposal_id']), headers=owner, json=body)
    assert r.status_code == 409 and r.json()['error']['code'] == 'expired'
    assert _task_bytes(rt) == before and _head(settings) == head
    with pytest.raises(Exception, match='expired'):
        service.decide({'approve': ['1'], 'edits': {'1': {'undated': True, 'area': 'work'}}}, session_id='parent')
    assert _state(service, run)['state'] == 'pending' and _task_bytes(rt) == before


def test_expired_with_explicit_override_creates_one_task(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    service.utcnow = lambda: EXPIRED_NOW
    head, before = _head(settings), len(_task_bytes(rt))
    r = client.post(APPROVE.format(proposal['proposal_id']), headers=owner, json={**CREATE, 'allow_expired': True})
    assert r.json()['receipt']['state'] == 'complete'
    assert len(_task_bytes(rt)) == before + 1 and len(_commits(settings, head)) == 1


def test_dismiss_then_resume_and_approve_write_nothing(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    p = '/api/plugins/alchemy-task'
    head, before = _head(settings), _task_bytes(rt)
    assert client.post(p + '/proposals/' + proposal['proposal_id'] + '/dismiss', headers=owner, json={}).json()['state'] == 'dismissed'
    r = client.post(p + '/runs/' + run + '/units/' + wid + '/resume', headers=owner, json={})
    assert r.json()['error']['code'] in {'already_resolved', 'invalid_request'}
    r = client.post(APPROVE.format(proposal['proposal_id']), headers=owner, json={**CREATE, 'allow_expired': True})
    assert r.json()['error']['code'] == 'already_resolved'
    with pytest.raises(Exception):
        service.decide({'approve': ['1'], 'edits': {'1': {'undated': True, 'area': 'work'}}}, session_id='parent')
    assert _task_bytes(rt) == before and _head(settings) == head
    again = client.post(p + '/proposals/' + proposal['proposal_id'] + '/dismiss', headers=owner, json={}).json()
    assert again['error']['code'] == 'already_resolved'
    assert _state(service, run)['state'] == 'dismissed'


@pytest.mark.parametrize('retry', [{'choice': 'update'}, {'choice': 'other'}, {}, 'expired'],
                         ids=['update-choice', 'unknown-choice', 'empty-body', 'after-expiry'])
def test_retry_of_completed_approval_returns_receipt_whatever_the_body(tmp_path, settings, data_dir, monkeypatch, retry):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    url = APPROVE.format(proposal['proposal_id'])
    first = client.post(url, headers=owner, json=CREATE).json()
    assert first['receipt']['state'] == 'complete'
    after = (_task_bytes(rt), _head(settings))
    if retry == 'expired':
        service.utcnow = lambda: EXPIRED_NOW
        retry = dict(CREATE)
    assert client.post(url, headers=owner, json=retry).json() == first
    assert (_task_bytes(rt), _head(settings)) == after


def test_last_valid_local_day_approves_without_override(tmp_path, settings, data_dir, monkeypatch):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    client, owner = client_for(service, monkeypatch)
    assert proposal['expires'] == '2030-01-08'
    # 23:59 New York on the expiry day: chat would still accept it, so must the dashboard.
    service.utcnow = lambda: dt.datetime(2030, 1, 9, 4, 59, tzinfo=dt.timezone.utc)
    head, before = _head(settings), len(_task_bytes(rt))
    r = client.post(APPROVE.format(proposal['proposal_id']), headers=owner, json=CREATE)
    assert r.json().get('ok') is True and r.json()['receipt']['state'] == 'complete', r.text
    assert len(_task_bytes(rt)) == before + 1 and len(_commits(settings, head)) == 1
