"""Outcome tests: discovery research runs as short, bounded, resumable calls.

No operator timeout receipt exists. Every `discovery_research_run` call
returns within its per-call budget (virtual clock) while children keep running
in the background; the parent calls again with the same run until the call
reports `complete`, then joins. Research semantics are unchanged: at most
three slots, an 1800-second observed RUNNING deadline, two attempts, and
fencing of unknown launches without relaunch or refund.
"""
import datetime as dt
import json
from types import SimpleNamespace

import pytest

from alchemy_task.core import discovery_state
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.discovery_state import DiscoveryStore
from test_discovery_runner import Clock, Status, accept_all, callback_all


class SlowPool:
    """Public-shaped lifecycle whose children outlive a single call window.

    behaviours per candidate index and ordinal: valid | invalid | hang.
    A valid child submits its full callback halfway through and is SUCCEEDED
    once `duration` virtual seconds have passed since its launch.
    """

    def __init__(self, clock, store, run, *, duration=400, behaviours=None, parent='parent'):
        self.clock, self.store, self.run, self.duration = clock, store, run, duration
        self.behaviours = behaviours or {}
        self.parent = parent
        self.records, self.requests, self.cancelled, self.launch_times = {}, [], [], []
        self.submitted, self.cancel_accepted = set(), set()
        self.runner = None

    def launch(self, request):
        self.requests.append(request)
        self.launch_times.append(self.clock.monotonic())
        n = len(self.requests)
        sid = f'sa-{n}'
        bootstrap = json.loads(request['context'])
        self.runner.subagent_start(parent_session_id=self.parent, child_session_id=f'child-{n}', child_subagent_id=sid)
        handle = {'subagent_id': sid, 'parent_session_id': self.parent, 'created_at': self.clock.time(), 'capability': f'cap-{n}'}
        self.records[sid] = {'handle': handle, 'started': self.clock.time(), 'ready': False, 'bootstrap': bootstrap}
        return handle

    def _behaviour(self, sid):
        boot = self.records[sid]['bootstrap']
        ids = [c['candidate_id'] for c in self.store.get_run(self.run)['candidates'] if not c.get('parent_candidate_id')]
        seq = self.behaviours.get(ids.index(boot['candidate_id']), ['valid', 'valid'])
        return seq[min(boot['ordinal'], len(seq)) - 1]

    def status(self, handle):
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
            callback_all(self.runner, self.store, self, self.run, handle, invalid=self._behaviour(sid) == 'invalid')
        if age >= self.duration:
            r['ready'] = True
            return Status('SUCCEEDED', self.clock.time())
        return Status('RUNNING', r['started'])

    def wait(self, handle, *, timeout_seconds):
        self.clock.sleep(timeout_seconds)
        return {'state': self.status(handle).state}

    def result(self, handle):
        sid = handle['subagent_id']
        r = self.records[sid]
        return {'ready': r['ready'], 'terminal_state': 'CANCELLED' if sid in self.cancel_accepted else 'SUCCEEDED',
                'started_at': r['started'], 'completed_at': self.clock.time(), 'summary': 'NOT A PAYLOAD', 'structured_payload': None}

    def reconnect(self, handle):
        return {'connected': handle['subagent_id'] in self.records, 'state': self.status(handle).state}

    def cancel(self, handle, *, reason):
        self.cancelled.append((handle, reason, self.clock.monotonic()))
        self.cancel_accepted.add(handle['subagent_id'])
        return {'accepted': True, 'state': 'CANCEL_REQUESTED'}


def build(tmp_path, count=5, *, clock=None, policy=None, **pool_kw):
    from alchemy_task.discovery_runner import DiscoveryRunner, RunnerPolicy
    clock = clock or Clock()
    store = DiscoveryStore(tmp_path / 'discovery')
    run = store.init_run(origin={'session_id': 'parent'}, business_date='2026-01-01')
    store.add_candidates(run, [{'title': f'Work {i}', 'source_ids': [f'source:source:account:thread:t{i}']} for i in range(count)])
    store.freeze_index(run, rubric='Full authoritative primary then all-status task inventory, skills and decomposition. Read only.')
    pool = SlowPool(clock, store, run, **pool_kw)
    # Default construction: no operator receipt or timeout configuration exists.
    runner = DiscoveryRunner(SimpleNamespace(subagent_lifecycle=pool), SimpleNamespace(data_dir=tmp_path), store=store, clock=clock,
                             policy=RunnerPolicy(**(policy or {})))
    pool.runner = runner
    return runner, store, pool, run


def timed_call(runner, run, session='parent'):
    start = runner.clock.monotonic()
    report = runner.run(run, session_id=session)
    return report, runner.clock.monotonic() - start


def drive(runner, store, run, *, session='parent', max_calls=40):
    """The skill's loop: call, accept every awaiting payload, repeat until complete."""
    reports = []
    for _ in range(max_calls):
        report, elapsed = timed_call(runner, run, session)
        reports.append((report, elapsed))
        accept_all(runner, store, run, session)
        if report['status'] == 'complete':
            return reports
    raise AssertionError('research did not complete: ' + json.dumps(reports[-1][0])[:800])


def parents(store, run):
    return [c['candidate_id'] for c in store.get_run(run)['candidates'] if not c.get('parent_candidate_id')]


def charged_units(store):
    return sum(len(json.loads(p.read_text())['charged']) for p in (store.state_root / 'budgets').glob('*.json'))


# ---------------------------------------------------------------- policy

def test_default_policy_is_bounded_below_the_default_host_deadline():
    from alchemy_task import discovery_runner as R
    policy = R.RunnerPolicy()
    assert policy.call_seconds == 300
    assert policy.slots == 3 and policy.running_seconds == 1800 and policy.admission_seconds == 60
    assert R.HOST_DEFAULT_TOOL_DEADLINE == 420
    assert policy.call_seconds + R.CALL_DEADLINE_MARGIN < R.HOST_DEFAULT_TOOL_DEADLINE
    assert not hasattr(policy, 'transport_seconds')
    # Configurable only downward, and never so short that a call cannot settle its own launches.
    assert R.RunnerPolicy(call_seconds=200).call_seconds == 200
    for bad in (301, 2040, 60):
        with pytest.raises(UserError):
            R.RunnerPolicy(call_seconds=bad)


def test_runner_constructor_has_no_transport_receipt():
    import inspect
    from alchemy_task.discovery_runner import DiscoveryRunner
    assert 'transport_receipt' not in inspect.signature(DiscoveryRunner).parameters


# ---------------------------------------------------------------- outcome 1

def test_five_candidates_finish_across_several_bounded_calls_then_join(tmp_path):
    runner, store, pool, run = build(tmp_path, 5)
    reports = drive(runner, store, run)
    budget = runner.policy.call_seconds
    assert len(reports) >= 3  # 400-second children cannot finish inside one 300-second call
    assert all(elapsed <= budget for _, elapsed in reports), [e for _, e in reports]
    first = reports[0][0]
    assert first['status'] == 'running' and first['counts']['running'] == 3 and first['counts']['queued'] == 2
    assert 'discovery_research_run' in first['next_action'] and run in first['next_action']
    last = reports[-1][0]
    assert last['status'] == 'complete' and 'discovery_join' in last['next_action']
    assert last['counts']['accepted'] == 5 and last['counts']['running'] == 0 and last['counts']['queued'] == 0
    assert max(r['max_logical_slots'] for r, _ in reports) == 3
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and not joined['degraded'] and sorted(joined['accepted']) == sorted(parents(store, run))
    assert len(pool.requests) == 5 and pool.cancelled == []
    assert 'long_canary' not in last


def test_every_return_carries_status_counts_and_next_action(tmp_path):
    runner, store, pool, run = build(tmp_path, 2)
    for report, _ in drive(runner, store, run):
        assert report['status'] in {'running', 'complete'}
        assert set(report['counts']) >= {'accepted', 'running', 'queued', 'repairing', 'failed', 'deferred'}
        assert isinstance(report['next_action'], str) and report['next_action']


# ---------------------------------------------------------------- outcome 2

def test_new_supervisor_finishes_the_same_run_without_duplicate_launches_or_budget(tmp_path):
    from alchemy_task.discovery_runner import DiscoveryRunner
    runner, store, pool, run = build(tmp_path, 5)
    first, _ = timed_call(runner, run)
    assert first['status'] == 'running'
    launched, charged = len(pool.requests), charged_units(store)
    # The parent stops calling. A NEW session (a different session id, as the
    # next scheduled run or a compressed transcript has) with a fresh
    # supervisor and no in-memory timers continues from saved state only.
    fresh = DiscoveryRunner(SimpleNamespace(subagent_lifecycle=pool), SimpleNamespace(data_dir=tmp_path),
                            store=DiscoveryStore(tmp_path / 'discovery'), clock=runner.clock,
                            recovery_authorizer=lambda run_id, old, new: True)
    pool.runner, pool.parent = fresh, 'next-session'
    runner.clock.sleep(300)
    recovered = fresh.recover(run, session_id='next-session', adopt=True)
    assert recovered['fenced'] == []
    reports = drive(fresh, fresh.store, run, session='next-session')
    ledger = store.get_run(run)
    assert all(r['status'] != 'held' for r, _ in reports)
    assert len(pool.requests) == 5 and launched == 3
    assert sorted(json.loads(r['context'])['candidate_id'] for r in pool.requests) == sorted(parents(store, run))
    assert charged == 3 and charged_units(store) == 5  # each candidate charged once, never twice
    assert all(a['state'] == 'accepted_bundle' for a in ledger['attempts'].values())
    joined = fresh.join(run, session_id='next-session')
    assert joined['joined'] and not joined['degraded']
    assert all(e <= fresh.policy.call_seconds for _, e in reports)


# ---------------------------------------------------------------- outcome 3

def test_child_finishing_between_calls_is_collected_by_the_next_call(tmp_path):
    runner, store, pool, run = build(tmp_path, 3)
    first, _ = timed_call(runner, run)
    assert first['status'] == 'running' and first['counts']['running'] == 3 and not first['awaiting_parent']
    runner.clock.sleep(500)  # no call is active while the children finish
    second, elapsed = timed_call(runner, run)
    assert len(second['awaiting_parent']) == 3 and len(pool.requests) == 3
    assert elapsed < 10  # nothing left to supervise, so the call returns promptly
    accept_all(runner, store, run)
    assert runner.run(run, session_id='parent')['status'] == 'complete'
    assert runner.join(run, session_id='parent')['joined']


def test_running_deadline_passing_between_calls_is_handled_at_the_next_call_start(tmp_path):
    runner, store, pool, run = build(tmp_path, 1, behaviours={0: ['hang', 'valid']})
    cid = parents(store, run)[0]
    timed_call(runner, run)
    a = next(iter(store.get_run(run)['attempts'].values()))
    assert a['state'] == 'RUNNING' and a['deadline_utc'] and not a['fenced']
    runner.clock.sleep(2000)  # the 1800-second deadline passes while no call is active
    start = runner.clock.monotonic()
    report = runner.run(run, session_id='parent')
    first = store.get_run(run)['attempts'][a['token']]
    assert first['fenced'] and first['fence_reason'] == 'execution_timeout'
    assert pool.cancelled and pool.cancelled[0][1] == 'execution_timeout' and pool.cancelled[0][2] - start < 5
    # The cancellation landed, so the one fresh retry ran in the same call.
    attempts = sorted((x for x in store.get_run(run)['attempts'].values() if x['candidate_id'] == cid), key=lambda x: x['ordinal'])
    assert [x['ordinal'] for x in attempts] == [1, 2]
    assert json.loads(pool.requests[-1]['context'])['repair']['reason']['reason'] == 'execution_timeout'
    drive(runner, store, run)
    assert runner.join(run, session_id='parent')['joined']
    assert report['counts']['repairing'] >= 1


def test_fresh_supervisor_honours_the_saved_running_deadline_after_it_passed_between_calls(tmp_path):
    from alchemy_task.discovery_runner import DiscoveryRunner
    runner, store, pool, run = build(tmp_path, 1, behaviours={0: ['hang', 'valid']})
    status = pool.status

    def heartbeat(handle):
        # The host's updated_at moves while a child runs; only the saved start counts.
        out = status(handle)
        return Status(out.state, pool.clock.time()) if out.state == 'RUNNING' else out
    timed_call(runner, run)
    pool.status = heartbeat
    a = next(iter(store.get_run(run)['attempts'].values()))
    assert a['deadline_utc']
    runner.clock.sleep(2000)
    fresh = DiscoveryRunner(SimpleNamespace(subagent_lifecycle=pool), SimpleNamespace(data_dir=tmp_path),
                            store=DiscoveryStore(tmp_path / 'discovery'), clock=runner.clock)
    pool.runner = fresh
    fresh.run(run, session_id='parent')
    first = store.get_attempt(run, a['token'])
    assert first['fence_reason'] == 'execution_timeout' and first['state'] == 'rejected_retryable'
    assert [json.loads(r['context'])['ordinal'] for r in pool.requests] == [1, 2]


def test_cancellation_landing_during_the_next_call_is_observed_in_that_call(tmp_path):
    runner, store, pool, run = build(tmp_path, 1, behaviours={0: ['hang', 'valid']})
    landed = {'at': None}
    status = pool.status

    def slow_cancel(handle, *, reason):
        pool.cancelled.append((handle, reason, pool.clock.monotonic()))
        return {'accepted': True, 'state': 'CANCEL_REQUESTED'}
    pool.cancel = slow_cancel

    def unwinding(handle):
        if landed['at'] is not None and pool.clock.monotonic() >= landed['at']:
            pool.cancel_accepted.add(handle['subagent_id'])
        return status(handle)
    pool.status = unwinding
    while not pool.cancelled:
        report, _ = timed_call(runner, run)
    assert report['status'] == 'running' and report['unknown_candidates'] == []
    landed['at'] = runner.clock.monotonic() + 30  # lands 30 s into the next call
    report, _ = timed_call(runner, run)
    assert [json.loads(r['context'])['ordinal'] for r in pool.requests] == [1, 2]
    assert report['unknown_candidates'] == [] and report['status'] == 'running'


def test_pending_deadline_passing_between_calls_is_fenced_at_the_next_call_start(tmp_path):
    runner, store, pool, run = build(tmp_path, 1)
    pending = {'on': True}
    status = pool.status
    pool.status = lambda h: Status('PENDING', pool.records[h['subagent_id']]['started']) if pending['on'] else status(h)
    pool.cancel = lambda handle, *, reason: (pool.cancelled.append((handle, reason, pool.clock.monotonic())), {'accepted': False, 'unsupported': True})[1]
    # Simulate a call that returned after binding but before 60 s of PENDING.
    a = store.reserve_attempt(run, parents(store, run)[0], owner_session='parent')
    handle = pool.launch(runner._bootstrap(run, a))
    store.bind_attempt(run, a['token'], handle, owner_session='parent')
    runner.clock.sleep(120)
    start = runner.clock.monotonic()
    runner.run(run, session_id='parent')
    attempt = store.get_attempt(run, a['token'])
    assert attempt['state'] == 'admission_timeout' and attempt['fenced']
    assert pool.cancelled[0][1] == 'admission_timeout' and pool.cancelled[0][2] - start < 5


# ---------------------------------------------------------------- outcome 4 (repair across calls)

def test_semantic_repair_launches_on_a_later_call_with_the_rejected_payload(tmp_path):
    from alchemy_task.discovery_runner import CHECKLIST
    runner, store, pool, run = build(tmp_path, 2)
    for _ in range(5):
        report, _ = timed_call(runner, run)
        if report['awaiting_parent']:
            break
    bad = store.get_attempt(run, sorted(report['awaiting_parent'])[0])
    info = bad['payload']
    page = runner.fetch(run, info['resource'], info['payload_sha256'], session_id='parent')
    while page['has_more']:
        page = runner.fetch(run, info['resource'], info['payload_sha256'], cursor=page['next_cursor'], session_id='parent')
    runner.accept(run, bad['token'], info['payload_sha256'], {'accepted': False, 'retryable': True,
        'reason': 'Ownership contradiction in latest primary requires fresh research',
        'checklist': {k: 'Evidence inspected; ownership gap remains' for k in CHECKLIST}}, session_id='parent')
    reports = drive(runner, store, run)
    repair = json.loads(pool.requests[-1]['context'])
    assert repair['candidate_id'] == bad['candidate_id'] and repair['ordinal'] == 2
    assert repair['repair']['payload'] == bad['payload']
    assert len(pool.requests) == 3 and charged_units(store) == 2
    assert all(e <= runner.policy.call_seconds for _, e in reports)
    assert runner.join(run, session_id='parent')['joined']


def test_schema_invalid_payload_repairs_and_charged_repair_runs_at_cap(tmp_path):
    runner, store, pool, run = build(tmp_path, 4, behaviours={0: ['invalid', 'valid']}, policy={'daily_limit': 2})
    reports = drive(runner, store, run)
    ids = parents(store, run)
    attempts = sorted((x for x in store.get_run(run)['attempts'].values() if x['candidate_id'] == ids[0]), key=lambda x: x['ordinal'])
    assert [x['ordinal'] for x in attempts] == [1, 2] and charged_units(store) == 2
    deferred = sorted({c for r, _ in reports for c in r['budget_deferred']})
    assert deferred == sorted(ids[2:])
    assert reports[-1][0]['counts']['deferred'] == 2
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and sorted(joined['accepted']) == sorted(ids[:2])
    assert [d['candidate_id'] for d in joined['deferred']] == ids[2:]


# ---------------------------------------------------------------- outcome 5

def test_join_refuses_while_research_is_running_and_points_to_the_research_call(tmp_path):
    runner, store, pool, run = build(tmp_path, 2)
    report, _ = timed_call(runner, run)
    assert report['status'] == 'running'
    joined = runner.join(run, session_id='parent')
    assert not joined['joined'] and joined['pending']
    assert 'discovery_research_run' in joined['next_action'] and run in joined['next_action']
    # Explicit degraded acknowledgement never finishes a live attempt.
    forced = runner.join(run, session_id='parent', degraded={c: 'give up' for c in parents(store, run)})
    assert not forced['joined']


# ---------------------------------------------------------------- admission and launch receipts

def test_launches_happen_only_in_the_admission_window_and_are_bound_before_return(tmp_path):
    runner, store, pool, run = build(tmp_path, 7, duration=30)
    starts = []
    original = runner.run

    def run_call(run_id, **kw):
        starts.append(runner.clock.monotonic())
        out = original(run_id, **kw)
        # Every attempt has a launch receipt (bound handle) or is fenced before the call returns.
        for a in store.get_run(run_id)['attempts'].values():
            assert a['handle'] or a['fenced'], a['state']
        return out
    runner.run = run_call
    drive(runner, store, run)
    policy = runner.policy
    for t in pool.launch_times:
        call_start = max(s for s in starts if s <= t)
        assert t - call_start < policy.admission_seconds
        assert t - call_start < policy.call_seconds - policy.pending_seconds
    assert len(pool.requests) == 7


def test_unknown_launch_is_fenced_without_relaunch_or_refund_across_calls(tmp_path):
    runner, store, pool, run = build(tmp_path, 2)

    def lost(request):
        raise OSError('transport lost after the host may have accepted the launch')
    pool.launch = lost
    reports = [runner.run(run, session_id='parent') for _ in range(4)]
    attempts = list(store.get_run(run)['attempts'].values())
    assert len(attempts) == 2 and all(a['state'] == 'launch_unknown' and a['ordinal'] == 1 for a in attempts)
    assert charged_units(store) == 2
    assert reports[-1]['status'] == 'complete' and sorted(reports[-1]['unknown_candidates']) == sorted(parents(store, run))
    joined = runner.join(run, session_id='parent')
    assert not joined['joined']


def test_exception_mid_call_fences_bound_children_and_holds_the_run(tmp_path):
    runner, store, pool, run = build(tmp_path, 2)
    wait = pool.wait

    def broken(handle, *, timeout_seconds):
        # Fail only once both children are bound, so the precondition below is deterministic.
        bound = [a for a in store.get_run(run)['attempts'].values() if a.get('handle')]
        if len(pool.records) == 2 and len(bound) == 2:
            raise RuntimeError('host lifecycle failed mid-call')
        return wait(handle, timeout_seconds=timeout_seconds)
    pool.wait = broken
    with pytest.raises(RuntimeError):
        runner.run(run, session_id='parent')
    attempts = list(store.get_run(run)['attempts'].values())
    assert len(attempts) == 2 and all(a['handle'] for a in attempts)
    assert all(a['fenced'] and a['state'] == 'execution_unknown' for a in attempts)
    assert len(pool.cancelled) == 2  # bound children were asked to stop
    pool.wait = wait
    held = runner.run(run, session_id='parent')
    assert held['status'] == 'held' and 'interrupted' in held['holds']
    assert 'discovery_recover' in held['next_action'] and len(pool.requests) == 2  # no relaunch
    assert charged_units(store) == 2


# ---------------------------------------------------------------- lease

class _Shifted(dt.datetime):
    offset = dt.timedelta(0)

    @classmethod
    def now(cls, tz=None):
        return dt.datetime.now(tz) + cls.offset


def test_crashed_callers_lease_expires_within_the_call_budget_plus_margin(tmp_path, monkeypatch):
    from alchemy_task import discovery_runner as R
    runner, store, pool, run = build(tmp_path, 1)
    seen = {}
    wait = pool.wait

    def capture(handle, *, timeout_seconds):
        seen.setdefault('lease', store.get_run(run).get('lease'))
        seen.setdefault('at', runner.clock.time())
        return wait(handle, timeout_seconds=timeout_seconds)
    pool.wait = capture
    runner.run(run, session_id='parent')
    lease = seen['lease']
    expiry = dt.datetime.fromisoformat(lease['expires_at']).timestamp()
    assert runner.policy.call_seconds < expiry - seen['at'] <= runner.policy.call_seconds + R.CALL_DEADLINE_MARGIN
    # The caller crashed while holding the lease on another host (no process proof).
    with store._lock(store._run_lock_name(run)):
        ledger = store._load(run)
        expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=runner.policy.call_seconds + R.CALL_DEADLINE_MARGIN)
        ledger['lease'] = {'owner': 'crashed-invocation', 'expires_at': expires.isoformat(), 'process_incarnation': None}
        store._save(run, ledger)
    monkeypatch.setattr(discovery_state, 'dt', SimpleNamespace(datetime=_Shifted, timezone=dt.timezone, timedelta=dt.timedelta))
    _Shifted.offset = dt.timedelta(seconds=10)
    with pytest.raises(UserError, match='claimed'):
        runner.run(run, session_id='parent')
    _Shifted.offset = dt.timedelta(seconds=runner.policy.call_seconds + R.CALL_DEADLINE_MARGIN + 1)
    report = runner.run(run, session_id='parent')  # the next caller adopts the same run
    assert report['run_id'] == run and len(pool.requests) == 1  # adopted, no relaunch
    assert 'lease' not in store.get_run(run)


# ---------------------------------------------------------------- integration (no receipt) and digest refusal

def test_integration_researches_without_receipt_and_digest_refuses_until_research_completes(settings, data_dir, tmp_path):
    from test_discovery_integration import configure, service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    # A receipt left over from an older install is ignored, never required.
    ctx.set_config('discovery_transport_receipt', '')
    run = integration.start('work', session_id='parent')['run_id']
    window = integration.store.get_run(run)['config']['windows']['feed']
    integration.collect(run, 'feed', session_id='parent', envelope={**window, 'status': 'partial', 'account_key': 'account', 'items': [
        {'title': 'Review release', 'source_ids': ['source:feed:account:issue:one'], 'source_revision': 'v1', 'body': 'Please review the release.'}]})
    integration.freeze(run, session_id='parent')
    clock = Clock()
    pool = SlowPool(clock, integration.store, run, duration=400)
    ctx.subagent_lifecycle = pool; pool.runner = integration.runner; integration.runner.clock = clock
    report = integration.runner.run(run, session_id='parent')
    assert report['status'] == 'running' and len(pool.requests) == 1
    with pytest.raises(UserError, match='discovery_research_run'):
        integration.finalize(run, session_id='parent')
    joined = integration.runner.join(run, session_id='parent')
    assert not joined['joined'] and 'discovery_research_run' in joined['next_action']


# ---------------------------------------------------------------- scheduled prompt

def test_scheduled_prompt_states_the_call_loop_and_always_ends_with_a_readable_digest():
    from alchemy_task.jobs import discovery_job_config
    native = discovery_job_config('work')['prompt']
    assert 'until it returns status complete' in native and 'discovery_recover' in native
    assert 'finish_now=true' in native and 'Needs attention' in native and 'more than twice' in native
    assert 'Partial digest' in native and 'Never end with only a status report' in native
    assert 'unfinished' not in native and '\u2014' not in native
    sender = discovery_job_config('work', delivery_owner='verified_sender')['prompt']
    assert 'until it returns status complete' in sender and 'Return [SILENT]' in sender
    assert 'finish_now=true' in sender and 'Partial digest' not in sender



def test_call_returns_once_a_child_finishes_so_its_slot_and_payload_never_wait_out_the_call(tmp_path):
    # The first child takes 400 s, the others 1000 s; the 4th candidate waits for a free slot. The slot
    # freed after the admission window must not idle until the call budget ends: the call returns with
    # the payload ready, the parent accepts it, and the next call launches the queued candidate.
    runner, store, pool, run = build(tmp_path, 4)
    base = pool.status

    def status(handle):
        index = int(handle['subagent_id'].split('-')[1])
        pool.duration = 400 if index == 1 else 1000
        return base(handle)
    pool.status = status
    reports = drive(runner, store, run)
    assert len(pool.launch_times) == 4
    assert pool.launch_times[3] < 450, pool.launch_times
    early = [(r, e) for r, e in reports if r['awaiting_parent'] and r['counts']['running']]
    assert early and all(e < runner.policy.call_seconds for _, e in early)
    assert reports[-1][0]['status'] == 'complete' and runner.join(run, session_id='parent')['joined']
