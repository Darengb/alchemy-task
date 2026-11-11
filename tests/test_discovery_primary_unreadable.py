"""Two research children that cannot read their primary source stop the run early."""
from test_discovery_runner import setup_runner
from test_discovery_schema import bundle


def _child_reports(runner, store, pool, run, failing):
    """Each child pages its bootstrap and submits; children named in `failing` report PRIMARY_UNREADABLE."""
    original = pool.status
    submitted = set()

    def status(h):
        sid = h['subagent_id']
        if sid not in submitted:
            submitted.add(sid)
            b = pool.records[sid]['bootstrap']; token = b['token']; n = sid.split('-')[-1]
            for name, info in b['resources'].items():
                cursor = None
                while True:
                    page = runner.fetch(run, name, info['sha256'], token=token, binding=b['binding'], cursor=cursor,
                                        session_id='child-' + n, task_id='cron-other')
                    if not page['has_more']: break
                    cursor = page['next_cursor']
            payload = bundle()
            a = store.get_attempt(run, token)
            payload['candidate_id'] = a['candidate_id']
            c = store.get_candidate(run, a['candidate_id'])
            w = payload['workstreams'][0]
            w['exact_source_ids'] = [{'type': 'source', 'source_key': 'source', 'account_key': 'account',
                                      'object_kind': 'thread', 'object_id': c['source_ids'][0].split(':')[-1]}]
            if int(n) in failing:
                w['research_status'] = 'failed'
                w['errors'] = ['PRIMARY_UNREADABLE: the frozen source body has no conversation text']
            runner.submit(run, token, b['binding'], payload=payload, session_id='child-' + n, task_id='cron-other')
        return original(h)
    pool.status = status


def test_two_unreadable_primaries_hold_the_run_and_stop_launches(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=6, slots=2)
    _child_reports(runner, store, pool, run, failing={1, 2})
    report = runner.run(run, session_id='parent')
    assert report['status'] == 'held' and 'primary_unreadable' in report['holds']
    assert 'cannot read the primary sources' in report['primary_unreadable_error']
    assert 'fix collection' in report['next_action']
    assert len(pool.requests) == 2  # no further children launched
    again = runner.run(run, session_id='parent')
    assert again['status'] == 'held' and len(pool.requests) == 2


def test_one_unreadable_primary_does_not_hold(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=3, slots=1)
    _child_reports(runner, store, pool, run, failing={1})
    report = runner.run(run, session_id='parent')
    assert report['status'] != 'held' and 'primary_unreadable' not in report.get('holds', [])
    assert len(pool.requests) >= 2


def test_parent_rejection_reason_counts(tmp_path):
    from alchemy_task.discovery_runner import primary_unreadable
    assert primary_unreadable('The child could not read its primary source.')
    assert primary_unreadable({'workstreams': [{'errors': ['primary_read_blocked by guard']}]})
    assert not primary_unreadable({'workstreams': [{'title': 'PRIMARY_UNREADABLE', 'errors': []}]})
