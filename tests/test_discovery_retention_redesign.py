"""Sixty-day retention outcomes, including expired pending proposals and HTTP lookup."""
import datetime as dt
import os
import time

import pytest


from test_discovery_dashboard import fixture_service, client_for


@pytest.mark.parametrize('age,protect', [(40, ''), (61, ''), (61, 'approved'), (61, 'plan'), (61, 'unknown'), (61, 'inflight')])
def test_pending_runs_prune_at_sixty_days_without_losing_unfinished_work(tmp_path, settings, data_dir, monkeypatch, age, protect):
    service, rt, run, wid, proposal = fixture_service(tmp_path, settings, data_dir)
    service.utcnow = lambda: dt.datetime(2031, 1, 1, tzinfo=dt.timezone.utc)
    before = {t.path: t.path.read_bytes() for t in rt.store().scan().tasks}
    if protect == 'approved': service.digest.decide(proposal['proposal_id'], 'approved')
    if protect == 'plan':
        service.conversion.prepare(run, wid, choice='create', area='work', undated=True, user_approved=True, reason='User approved')
    if protect in {'unknown', 'inflight'}: service._delivery_record(run, {'state': protect})
    service.reconcile_endstate(run)
    path = service.store.run_dir(run) / 'ledger.json'
    old = time.time() - age * 86400
    os.utime(path, (old, old))
    result = service.store.prune()
    assert result['days'] == 60
    if age < 60 or protect:
        assert run not in result['deleted_runs'] and path.exists()
        return
    assert run in result['deleted_runs'] and not path.exists()
    assert service.store.get_run(run)['pruned_at']
    client, owner = client_for(service, monkeypatch)
    response = client.post('/api/plugins/alchemy-task/proposals/' + proposal['proposal_id'] + '/approve', headers=owner,
                           json={'choice': 'create', 'area': 'work', 'undated': True, 'allow_expired': True})
    assert response.status_code == 404 and response.json()['error']['code'] == 'not_found', response.text
    assert {t.path: t.path.read_bytes() for t in rt.store().scan().tasks} == before
