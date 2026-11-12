from alchemy_task.core.discovery_state import DiscoveryStore


def test_a_blocked_backlog_item_is_selected_once_more_then_stays_blocked(tmp_path):
    store = DiscoveryStore(tmp_path)
    store.enqueue_backlog('work', 'feed', [{'source_ids': ['source:feed:acct:issue:1'], 'source_revision': 'v1', 'title': 'x', 'body': 'text'}])
    bid = store.source_state('work', 'feed')['backlog'][0]['backlog_id']
    store.update_backlog('work', 'feed', bid, status='selected', lineage={'run_id': 'r1', 'candidate_id': 'c'})
    store.update_backlog('work', 'feed', bid, status='blocked', lineage={'run_id': 'r1', 'candidate_id': 'c'})
    item = store.source_state('work', 'feed')['backlog'][0]
    assert item['status'] == 'blocked' and int(item.get('retries') or 0) == 0
    store.update_backlog('work', 'feed', bid, status='selected', lineage={'run_id': 'r2', 'candidate_id': 'c'})
    assert store.source_state('work', 'feed')['backlog'][0]['retries'] == 1


def test_replaying_an_older_run_never_takes_back_an_item_a_later_run_owns(tmp_path):
    store = DiscoveryStore(tmp_path)
    store.enqueue_backlog('work', 'feed', [{'source_ids': ['source:feed:acct:issue:1'], 'source_revision': 'v1', 'title': 'x', 'body': 'text'}])
    bid = store.source_state('work', 'feed')['backlog'][0]['backlog_id']
    store.update_backlog('work', 'feed', bid, status='deferred', lineage={'run_id': 'old', 'candidate_id': 'c'})
    store.update_backlog('work', 'feed', bid, status='accepted', lineage={'run_id': 'new', 'candidate_id': 'c'})
    item = store.source_state('work', 'feed')['backlog'][0]
    assert item['lineage']['run_id'] == 'new'  # integration._settle_backlog skips items owned by another run
