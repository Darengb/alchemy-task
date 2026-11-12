"""discovery_start fails open when a saved run is gone: missing ledger, pruned or abandoned."""
import shutil
from alchemy_task.core.discovery_state import atomic_json
from test_discovery_integration import service, configure


def test_start_gives_a_fresh_run_when_the_open_run_is_gone(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    first = integration.start('work', session_id='parent')['run_id']
    store = integration.store
    # A late writer recreated the run folder after the run was archived: resources but no ledger.
    run_dir = store.run_dir(first)
    shutil.rmtree(run_dir)
    (run_dir / 'resources').mkdir(parents=True)
    (run_dir / 'resources' / 'late').write_text('{}')
    second = integration.start('work', session_id='parent')['run_id']
    assert second != first
    # An abandoned run (tombstone, folder gone) is never resumed either.
    atomic_json(store.state_root / 'tombstones' / (second + '.json'), {**store.get_run(second), 'status': 'abandoned'})
    shutil.rmtree(store.run_dir(second))
    third = integration.start('work', session_id='parent')['run_id']
    assert third not in {first, second}
    # A ledger still on disk but marked abandoned is skipped as well.
    ledger = store.get_run(third); ledger['status'] = 'abandoned'
    atomic_json(store.run_dir(third) / 'ledger.json', ledger)
    fourth = integration.start('work', session_id='parent')
    assert fourth['run_id'] not in {first, second, third} and not fourth.get('resumed')
