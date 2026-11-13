from alchemy_task.core.discovery_state import DiscoveryStore


def _item(ids, rev):
    return {'source_ids': ['source:feed:acct:thread:t1'], 'source_revision': rev, 'title': 'Thread',
            'messages': [{'id': i, 'author': 'a', 'time': t, 'text': 'x' + i} for i, t in ids]}


def test_waiting_copy_of_an_already_researched_thread_is_dropped_but_new_messages_are_kept(tmp_path):
    store = DiscoveryStore(tmp_path)
    old = [('1', '2026-11-10T10:00:00+00:00'), ('2', '2026-11-10T10:05:00+00:00')]
    store.enqueue_backlog('work', 'feed', [_item(old, 'a')])
    first = store.source_state('work', 'feed')['backlog'][0]
    store.update_backlog('work', 'feed', first['backlog_id'], status='selected', lineage={'run_id': 'r1', 'candidate_id': 'c'})
    # A second, differently shaped copy waits in the queue (as left by older runs).
    state = store.source_state('work', 'feed')
    stale = dict(first, backlog_id='stale', status='deferred', candidate=_item(old, 'b'), message_ids=['h:1'], latest_message=None)
    state['backlog'].append(stale)
    import json; (store._source_path('work', 'feed')).write_text(json.dumps(state))
    store.update_backlog('work', 'feed', first['backlog_id'], status='accepted', lineage={'run_id': 'r1', 'candidate_id': 'c'})
    assert store.drop_stale_pending('work', 'feed') == ['stale']
    assert {b['backlog_id']: b['status'] for b in store.source_state('work', 'feed')['backlog']}['stale'] == 'resolved'
    # A waiting copy with a newer message stays queued.
    state = store.source_state('work', 'feed')
    fresh = dict(first, backlog_id='fresh', status='queued', candidate=_item(old + [('3', '2026-11-12T09:00:00+00:00')], 'c'))
    state['backlog'].append(fresh); (store._source_path('work', 'feed')).write_text(json.dumps(state))
    assert store.drop_stale_pending('work', 'feed') == []


def test_needs_attention_text_has_no_repeated_prefix_or_cut_word():
    from alchemy_task.discovery_digest import _failure_status
    long = 'Needs attention: Bowes report: Bowes report findings are in a file whose contents cannot be read with the available read-only tools because the attachment is stored outside the mailbox and the reader only returns message bodies.'
    out = _failure_status({'title': 'Bowes report', 'reason': long})
    assert not out.lower().startswith('needs attention') and not out.startswith('Bowes report:')
    assert out.endswith('...') and not out[:-3].endswith(('read-onl', 'onl'))
