"""Real OS-process crash proof for plugin-host supervisor leases."""
import datetime as dt
import multiprocessing
import pytest
from alchemy_task.core.discovery_identity import UserError
from test_discovery_state import setup


def test_dead_plugin_process_lease_recovery_preserves_live_exclusion_and_attempts(data_dir):
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
