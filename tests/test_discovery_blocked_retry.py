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


def test_time_box_cut_offs_are_deferred_without_limit_and_newer_runs_take_over_older_claims():
    import inspect
    from alchemy_task import discovery_integration as di
    src = inspect.getsource(di.DiscoveryIntegration._settle_backlog)
    assert 'TIME_BOX_REASON' in src and "'deferred' if (not attempts or timed_out)" in src
    assert "self._run_created(owner) > str(ledger.get('created')" in src


def test_replaying_an_old_run_leaves_an_item_closed_by_filters_or_the_stale_check_closed(tmp_path):
    store = DiscoveryStore(tmp_path)
    cand = {'source_ids': ['source:feed:acct:issue:1'], 'source_revision': 'v1', 'title': 'x', 'messages': [{'id': 'm1', 'text': 'x'}]}
    store.enqueue_backlog('work', 'feed', [{'source_ids': cand['source_ids'], 'source_revision': 'v1', 'candidate': cand}])
    bid = store.source_state('work', 'feed')['backlog'][0]['backlog_id']
    store.update_backlog('work', 'feed', bid, status='blocked', lineage={'run_id': 'old', 'candidate_id': 'c'})
    store.refilter_pending('work', 'feed', lambda item: (item, [{'name': 'rule'}], True))
    assert store.source_state('work', 'feed')['backlog'][0]['status'] == 'resolved'
    # The old run's outcome is replayed when the stream starts again: no error, item stays closed.
    assert store.settle_backlog('work', 'feed', bid, status='blocked', lineage={'run_id': 'old', 'candidate_id': 'c'}) is None
    item = store.source_state('work', 'feed')['backlog'][0]
    assert item['status'] == 'resolved' and item['lineage'].get('filtered')
    # A run's own terminal outcome is still idempotent.
    store.enqueue_backlog('work', 'feed', [{'source_ids': ['source:feed:acct:issue:2'], 'source_revision': 'v1', 'title': 'y', 'body': 'text'}])
    b2 = [b for b in store.source_state('work', 'feed')['backlog'] if b['backlog_id'] != bid][0]['backlog_id']
    lin = {'run_id': 'r', 'candidate_id': 'c2'}
    store.update_backlog('work', 'feed', b2, status='accepted', lineage=lin)
    assert store.settle_backlog('work', 'feed', b2, status='accepted', lineage=lin)['status'] == 'accepted'


def test_settle_uses_the_closed_item_safe_path():
    import inspect
    from alchemy_task import discovery_integration as di
    src = inspect.getsource(di.DiscoveryIntegration._settle_backlog)
    assert 'self.store.settle_backlog(' in src and 'self.store.update_backlog(' not in src


def test_any_update_to_a_closed_item_is_a_quiet_no_op(tmp_path):
    store = DiscoveryStore(tmp_path)
    store.enqueue_backlog('work', 'feed', [{'source_ids': ['source:feed:acct:issue:9'], 'source_revision': 'v1', 'title': 'x', 'body': 'text'}])
    bid = store.source_state('work', 'feed')['backlog'][0]['backlog_id']
    store.update_backlog('work', 'feed', bid, status='accepted', lineage={'run_id': 'r1', 'candidate_id': 'c'})
    for status in ('blocked', 'selected', 'queued', 'excluded'):
        out = store.update_backlog('work', 'feed', bid, status=status, lineage={'run_id': 'r2', 'candidate_id': 'c'})
        assert out['status'] == 'accepted' and out['lineage']['run_id'] == 'r1'
    item = store.source_state('work', 'feed')['backlog'][0]
    assert item['status'] == 'accepted' and len(item['ignored_updates']) == 4
