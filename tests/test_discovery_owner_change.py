"""Outcome tests: research children survive a change of the parent session.

The parent session id changes between research calls when the next scheduled
run takes over an unfinished run, and inside one run when context compression
rotates the session. The host lifecycle then hides the old session's handles
(a handle is visible only while the active parent session equals its
`parent_session_id`), but the children keep running and submit to the
plugin's own spool. A payload committed there is accepted after the usual full
parent review; a child that never submits is timed out at its saved deadline
and retried once under the normal rules.
"""
import json
from types import SimpleNamespace

import pytest

from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.discovery_state import DiscoveryStore
from test_discovery_runner import Clock, Status
from test_discovery_short_calls import SlowPool, charged_units, parents

ORPHAN_MARGIN = 120


class TickClock(Clock):
    """Virtual time; children make progress whenever time passes."""

    def __init__(self):
        super().__init__()
        self.pool, self._ticking = None, False

    def sleep(self, seconds):
        super().sleep(seconds)
        if self.pool and not self._ticking:
            self._ticking = True
            try:
                self.pool.background_tick()
            finally:
                self._ticking = False


def submit_full(runner, store, pool, run, handle, *, invalid=False):
    """A child that fetches every page of its assignment, then submits a valid bundle."""
    from test_discovery_schema import bundle
    record = pool.records[handle['subagent_id']]
    b = record['bootstrap']
    child = 'child-' + handle['subagent_id'].split('-')[-1]
    for name, info in b['resources'].items():
        cursor = None
        while True:
            page = runner.fetch(run, name, info['sha256'], token=b['token'], binding=b['binding'], cursor=cursor,
                                session_id=child, task_id=handle['subagent_id'])
            if not page['has_more']:
                break
            cursor = page['next_cursor']
    payload = bundle()
    a = store.get_attempt(run, b['token'])
    payload['candidate_id'] = a['candidate_id']
    kind, source_key, account, object_kind, object_id = store.get_candidate(run, a['candidate_id'])['source_ids'][0].split(':')[:5]
    payload['workstreams'][0]['exact_source_ids'] = [{'type': kind, 'source_key': source_key, 'account_key': account,
                                                     'object_kind': object_kind, 'object_id': object_id}]
    if invalid:
        payload['workstreams'][0]['title'] = 5
    return runner.submit(run, b['token'], b['binding'], payload=payload, session_id=child, task_id=handle['subagent_id'])


class HostPool(SlowPool):
    """Mirrors the host rule: only the ACTIVE parent session sees its handles."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.active = self.parent

    def _visible(self, handle):
        return handle['parent_session_id'] == self.active

    def launch(self, request):
        self.parent = self.active
        return super().launch(request)

    def _progress(self, handle):
        sid = handle['subagent_id']
        r = self.records[sid]
        age = self.clock.time() - r['started']
        if self._behaviour(sid) == 'hang':
            if sid in self.cancel_accepted:
                r['ready'] = True
                return Status('CANCELLED', self.clock.time())
            return Status('RUNNING', r['started'])
        if age >= self.duration / 2 and sid not in self.submitted:
            self.submitted.add(sid)
            submit_full(self.runner, self.store, self, self.run, handle, invalid=self._behaviour(sid) == 'invalid')
        if age >= self.duration:
            r['ready'] = True
            return Status('SUCCEEDED', self.clock.time())
        return Status('RUNNING', r['started'])

    def background_tick(self):
        for r in list(self.records.values()):
            self._progress(r['handle'])

    def status(self, handle):
        if not self._visible(handle):
            return Status('UNKNOWN', self.clock.time())
        return self._progress(handle)

    def wait(self, handle, *, timeout_seconds):
        self.clock.sleep(timeout_seconds)
        return {'state': self.status(handle).state}

    def reconnect(self, handle):
        if not self._visible(handle):
            return {'connected': False, 'state': 'UNKNOWN', 'diagnostic': 'RECONNECT_UNAVAILABLE'}
        return super().reconnect(handle)

    def cancel(self, handle, *, reason):
        if not self._visible(handle):
            return {'accepted': False, 'unknown_handle': True}
        return super().cancel(handle, reason=reason)


def build(tmp_path, count, *, first_session='cron-1', policy=None, **pool_kw):
    from alchemy_task.discovery_runner import DiscoveryRunner, RunnerPolicy
    clock = TickClock()
    store = DiscoveryStore(tmp_path / 'discovery')
    run = store.init_run(origin={'session_id': first_session}, business_date='2026-01-01')
    store.add_candidates(run, [{'title': f'Work {i}', 'source_ids': [f'source:source:account:thread:t{i}']} for i in range(count)])
    store.freeze_index(run, rubric='Full authoritative primary then all-status task inventory, skills and decomposition. Read only.')
    pool = HostPool(clock, store, run, parent=first_session, **pool_kw)
    runner = DiscoveryRunner(SimpleNamespace(subagent_lifecycle=pool), SimpleNamespace(data_dir=tmp_path), store=store, clock=clock,
                             policy=RunnerPolicy(**(policy or {})), recovery_authorizer=lambda run_id, old, new: True)
    pool.runner, clock.pool = runner, pool
    return runner, store, pool, run


def accept_awaiting(runner, store, run, session):
    """The parent's full review: every payload page, the checklist, then acceptance."""
    from alchemy_task.discovery_runner import CHECKLIST
    for a in list(store.get_run(run)['attempts'].values()):
        if a['state'] != 'terminal_observed' or not a['payload'] or a.get('validation_error'):
            continue
        info, cursor = a['payload'], None
        while True:
            page = runner.fetch(run, info['resource'], info['payload_sha256'], cursor=cursor, session_id=session)
            if not page['has_more']:
                break
            cursor = page['next_cursor']
        runner.accept(run, a['token'], info['payload_sha256'], {'accepted': True, 'reason': 'Full evidence supports the action.',
                      'checklist': {k: 'Reviewed every page.' for k in CHECKLIST}}, session_id=session)


def drive(runner, store, run, session, max_calls=40):
    reports = []
    for _ in range(max_calls):
        report = runner.run(run, session_id=session)
        reports.append(report)
        accept_awaiting(runner, store, run, session)
        if report['status'] == 'complete':
            return reports
    raise AssertionError('research did not complete: ' + json.dumps(reports[-1])[:800])


def old_children(pool, run):
    return {r['bootstrap']['token']: (r['handle'], r['bootstrap']) for r in pool.records.values()}


def assert_capability_revoked(runner, store, run, handle, bootstrap):
    child = 'child-' + handle['subagent_id'].split('-')[-1]
    name, info = next(iter(bootstrap['resources'].items()))
    with pytest.raises(UserError):
        runner.fetch(run, name, info['sha256'], token=bootstrap['token'], binding=bootstrap['binding'],
                     session_id=child, task_id=handle['subagent_id'])
    out = runner.submit(run, bootstrap['token'], bootstrap['binding'], payload={'late': True},
                        session_id=child, task_id=handle['subagent_id'])
    assert out['accepted'] is False and out.get('quarantined') is True
    verdict = runner.pre_tool_call(tool_name='discovery_research_fetch', session_id=child, task_id=handle['subagent_id'])
    assert verdict and verdict['action'] == 'block'


# ---------------------------------------------------------------- Part A: next scheduled run

def test_next_scheduled_run_accepts_committed_payloads_of_the_stopped_session(tmp_path):
    runner, store, pool, run = build(tmp_path, 6)
    first = runner.run(run, session_id='cron-1')
    assert first['counts']['running'] == 3
    in_flight = [a for a in store.get_run(run)['attempts'].values() if a['payload'] and not a.get('validation_error')]
    assert len(in_flight) == 3 and all(not a['terminal'] for a in in_flight)
    old = old_children(pool, run)
    # cron-1 stops. The next scheduled run is a NEW session; the host hides cron-1's handles.
    pool.active = 'cron-2'
    pool.clock.sleep(600)
    recovered = runner.recover(run, session_id='cron-2', adopt=True)
    assert recovered['fenced'] == []
    reports = drive(runner, store, run, 'cron-2')
    assert all(r['status'] != 'held' for r in reports)
    assert reports[-1]['unknown_candidates'] == [] and reports[-1]['counts']['accepted'] == 6
    joined = runner.join(run, session_id='cron-2')
    assert joined['joined'] and not joined['degraded'] and sorted(joined['accepted']) == sorted(parents(store, run))
    assert len(pool.requests) == 6 and charged_units(store) == 6  # no relaunch, no extra charge
    for token, (handle, bootstrap) in old.items():
        assert_capability_revoked(runner, store, run, handle, bootstrap)


# ---------------------------------------------------------------- Part B: compression mid-run

def test_compression_rotating_the_session_mid_run_keeps_children_that_commit_afterwards(tmp_path):
    runner, store, pool, run = build(tmp_path, 5, duration=800)  # children submit 400 s after launch
    first = runner.run(run, session_id='cron-1')
    assert first['counts']['running'] == 3
    assert all(not a['payload'] for a in store.get_run(run)['attempts'].values())
    # Context compression rotates the session id between two research calls.
    pool.active = 'cron-1-compressed'
    with pytest.raises(UserError, match='recovery'):
        runner.run(run, session_id='cron-1-compressed')
    recovered = runner.recover(run, session_id='cron-1-compressed', adopt=True)
    assert recovered['fenced'] == []
    second = runner.run(run, session_id='cron-1-compressed')
    # The rotated-away children still hold their slots: nothing else launched
    # while all three slots were in use (they commit 100 s into this call).
    assert second['status'] == 'running' and len(pool.requests) == 3
    assert second['unknown_candidates'] == []
    accept_awaiting(runner, store, run, 'cron-1-compressed')
    reports = [second] + drive(runner, store, run, 'cron-1-compressed')
    assert all(r['status'] != 'held' for r in reports)
    joined = runner.join(run, session_id='cron-1-compressed')
    assert joined['joined'] and not joined['degraded'] and len(joined['accepted']) == 5
    assert len(pool.requests) == 5 and charged_units(store) == 5


def test_orphan_past_its_deadline_is_retried_once_and_its_late_payload_is_rejected(tmp_path):
    from alchemy_task.discovery_runner import DiscoveryRunner
    import datetime as dt
    runner, store, pool, run = build(tmp_path, 1, behaviours={0: ['hang', 'valid']}, policy={'call_seconds': 100})
    runner.run(run, session_id='cron-1')
    attempt = next(iter(store.get_run(run)['attempts'].values()))
    deadline = dt.datetime.fromisoformat(attempt['deadline_utc']).timestamp()
    old = old_children(pool, run)
    pool.active = 'cron-2'
    assert runner.recover(run, session_id='cron-2', adopt=True)['fenced'] == []
    pool.clock.sleep(deadline + 10 - pool.clock.time())
    # Inside the deadline margin the orphan still holds its slot: no retry yet.
    within = runner.run(run, session_id='cron-2')
    assert pool.clock.time() < deadline + ORPHAN_MARGIN
    assert within['status'] == 'running' and len(pool.requests) == 1 and within['unknown_candidates'] == []
    # Once the deadline plus margin passes with no payload, it is a timeout: one fresh retry.
    report = runner.run(run, session_id='cron-2')
    assert [json.loads(r['context'])['ordinal'] for r in pool.requests] == [1, 2]
    assert json.loads(pool.requests[-1]['context'])['repair']['reason']['reason'] == 'execution_timeout'
    assert charged_units(store) == 1  # same budget unit, no extra charge
    assert report['unknown_candidates'] == []
    # The old child wakes up and tries to deliver: its token is revoked.
    (handle, bootstrap), = old.values()
    assert_capability_revoked(runner, store, run, handle, bootstrap)
    assert store.get_attempt(run, bootstrap['token'])['payload'] is None
    drive(runner, store, run, 'cron-2')
    joined = runner.join(run, session_id='cron-2')
    assert joined['joined'] and not joined['degraded']
    assert len(pool.requests) == 2


def test_launch_without_a_receipt_stays_fenced_after_an_owner_change(tmp_path):
    runner, store, pool, run = build(tmp_path, 1)
    # A reservation whose launch never returned a handle: its outcome is truly unknown.
    a = store.reserve_attempt(run, parents(store, run)[0], owner_session='cron-1')
    pool.active = 'cron-2'
    recovered = runner.recover(run, session_id='cron-2', adopt=True)
    assert recovered['fenced'] == [a['token']]
    assert runner.run(run, session_id='cron-2')['status'] == 'held'
    assert store.get_attempt(run, a['token'])['state'] == 'launch_unknown'


# ---------------------------------------------------------------- backlog after recovery

def test_backlog_marks_candidates_recovered_after_an_owner_change_accepted_not_blocked(settings, data_dir, tmp_path):
    from test_discovery_integration import configure, service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    run = integration.start('work', session_id='parent')['run_id']
    window = integration.store.get_run(run)['config']['windows']['feed']
    integration.collect(run, 'feed', session_id='parent', envelope={**window, 'status': 'partial', 'account_key': 'account', 'items': [
        {'title': f'Review release {i}', 'source_ids': [f'source:feed:account:issue:i{i}'], 'source_revision': 'v1'} for i in range(4)]})
    integration.freeze(run, session_id='parent')
    clock = TickClock()
    pool = HostPool(clock, integration.store, run, duration=400, parent='parent')
    ctx.subagent_lifecycle = pool
    pool.runner, clock.pool = integration.runner, pool
    integration.runner.clock = clock
    assert integration.runner.run(run, session_id='parent')['counts']['running'] == 3
    # The session changes (authorization of the new session is not under test here).
    pool.active = 'parent-next'
    integration.runner.recovery_authorizer = lambda run_id, old, new: True
    assert integration.runner.recover(run, session_id='parent-next', adopt=True)['fenced'] == []
    drive(integration.runner, integration.store, run, 'parent-next')
    joined = integration.runner.join(run, session_id='parent-next')
    assert joined['joined'] and len(joined['accepted']) == 4
    for unit in [c for c in integration.store.get_run(run)['candidates'] if c.get('parent_candidate_id')]:
        integration.match(run, unit['candidate_id'], session_id='parent-next')
        integration.record_decision(run, unit['candidate_id'], decision='propose', reason='Independent untracked action.', session_id='parent-next')
    integration.finalize(run, session_id='parent-next')
    statuses = [b['status'] for b in integration.store.source_state('work', 'feed')['backlog']]
    assert statuses == ['accepted'] * 4
