"""Real portable runner behavior through a public-shaped pool, not native delegation."""
from dataclasses import dataclass
from types import SimpleNamespace
import datetime as dt
import json
import time
import pytest
from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.core.discovery_identity import UserError

class Clock:
    def __init__(self): self.value = 0.; self.epoch = time.time()
    def monotonic(self): return self.value
    def time(self): return self.epoch + self.value
    def sleep(self, seconds): self.value += seconds; time.sleep(.001)

@dataclass
class Status:
    state: str
    updated_at: float

class Pool:
    def __init__(self, clock):
        self.clock = clock; self.records = {}; self.requests = []; self.cancelled = []; self.runner = None
        self.fail = False; self.pending = False
    def launch(self, request):
        self.requests.append(request)
        n = len(self.requests)
        sid = f'sa-{n}'
        bootstrap = json.loads(request['context'])
        self.runner.subagent_start(parent_session_id='parent', child_session_id=f'child-{n}', child_subagent_id=sid)
        handle = {'subagent_id': sid, 'parent_session_id': 'parent', 'created_at': self.clock.time(), 'capability': f'cap-{n}'}
        self.records[sid] = {'handle': handle, 'started': self.clock.time(), 'ready': False, 'bootstrap': bootstrap}
        return handle
    def status(self, handle):
        r = self.records[handle['subagent_id']]
        if self.pending: return Status('PENDING', r['started'])
        if self.clock.time() - r['started'] > 2:
            r['ready'] = True
            return Status('FAILED' if self.fail else 'SUCCEEDED', self.clock.time())
        return Status('RUNNING', r['started'])
    def wait(self, handle, *, timeout_seconds):
        self.clock.sleep(timeout_seconds)
        return {'state': self.status(handle).state, 'completed': self.records[handle['subagent_id']]['ready']}
    def result(self, handle):
        r = self.records[handle['subagent_id']]
        return {'ready': r['ready'], 'terminal_state': 'FAILED' if self.fail else 'SUCCEEDED', 'started_at': r['started'], 'completed_at': self.clock.time(), 'summary': 'NOT A PAYLOAD', 'structured_payload': None}
    def reconnect(self, handle): return {'connected': handle['subagent_id'] in self.records, 'state': self.status(handle).state}
    def cancel(self, handle, *, reason):
        self.cancelled.append((handle, reason)); return {'accepted': False, 'unsupported': True, 'state': 'CANCEL_REQUESTED'}


def setup_runner(tmp_path, count=4, **policy):
    from alchemy_task.discovery_runner import DiscoveryRunner, RunnerPolicy
    clock = Clock(); pool = Pool(clock)
    rt = SimpleNamespace(data_dir=tmp_path)
    store = DiscoveryStore(tmp_path / 'discovery')
    run = store.init_run(origin={'session_id': 'parent'}, business_date='2026-01-01')
    store.add_candidates(run, [{'title': f'Work {i}', 'source_ids': [f'source:source:account:thread:t{i}']} for i in range(count)])
    store.freeze_index(run, rubric='Full authoritative primary then all-status task inventory, skills and decomposition. Read only.')
    runner = DiscoveryRunner(SimpleNamespace(subagent_lifecycle=pool), rt, store=store, clock=clock, policy=RunnerPolicy(**policy))
    pool.runner = runner
    return runner, store, pool, run


def callback_all(runner, store, pool, run, handle, *, invalid=False):
    from test_discovery_schema import bundle
    record = pool.records[handle['subagent_id']]
    b = record['bootstrap']; token = b['token']
    n = handle['subagent_id'].split('-')[-1]
    for name, info in b['resources'].items():
        cursor = None
        while True:
            page = runner.fetch(run, name, info['sha256'], token=token, binding=b['binding'], cursor=cursor, session_id='child-' + n, task_id='cron-other')
            if not page['has_more']: break
            cursor = page['next_cursor']
    payload = bundle()
    a = store.get_attempt(run, token)
    payload['candidate_id'] = a['candidate_id']
    # A real schema bundle with generic typed assignment and all20 fields.
    c = store.get_candidate(run, a['candidate_id'])
    payload['workstreams'][0]['exact_source_ids'] = [{'type': 'source', 'source_key': 'source', 'account_key': 'account', 'object_kind': 'thread', 'object_id': c['source_ids'][0].split(':')[-1]}]
    if invalid: payload['workstreams'][0]['title'] = 5
    result = runner.submit(run, token, b['binding'], payload=payload, session_id='child-' + n, task_id='cron-other')
    return result


def drive(runner, store, run, *, session='parent', max_calls=40, accept=True):
    """The skill's loop over short calls: run, accept awaiting payloads, repeat until complete.

    Every call must stay inside its per-call budget on the virtual clock.
    """
    reports = []
    for _ in range(max_calls):
        start = runner.clock.monotonic()
        report = runner.run(run, session_id=session)
        assert runner.clock.monotonic() - start <= runner.policy.call_seconds
        reports.append(report)
        if accept:
            accept_all(runner, store, run)
        if report['status'] == 'complete':
            return reports
    raise AssertionError('research did not complete: ' + json.dumps(reports[-1])[:800])


def accept_all(runner, store, run):
    from alchemy_task.discovery_runner import CHECKLIST
    accepted = []
    for a in list(store.get_run(run)['attempts'].values()):
        if a['state'] != 'terminal_observed' or not a['payload'] or a.get('validation_error'): continue
        info = a['payload']; cursor = None
        while True:
            p = runner.fetch(run, info['resource'], info['payload_sha256'], cursor=cursor, session_id='parent')
            if not p['has_more']: break
            cursor = p['next_cursor']
        assessment = {'accepted': True, 'reason': 'Current primary evidence establishes the distinct user action; all plausible tasks inspected.', 'checklist': {k: 'Reviewed against full supplied evidence; no unresolved contradiction.' for k in CHECKLIST}}
        accepted.append(runner.accept(run, a['token'], info['payload_sha256'], assessment, session_id='parent'))
    return accepted


def test_full_callback_parent_pages_acceptance_and_join_hook(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=2)
    original = pool.status
    submitted = set()
    def status(h):
        if h['subagent_id'] not in submitted:
            submitted.add(h['subagent_id']); callback_all(runner, store, pool, run, h)
        return original(h)
    pool.status = status
    result = runner.run(run, session_id='parent')
    assert len(pool.requests) == 2
    assert len(result['awaiting_parent']) == 2
    assert not runner.join(run, session_id='parent')['joined']
    assert len(accept_all(runner, store, run)) == 2
    calls = []
    runner.proposal_hook = lambda r, joined: calls.append(r) or {'prepared': True}
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and not joined['degraded']
    assert calls == [run]
    assert len(pool.requests) == 2


def test_parent_must_fetch_every_payload_page_and_supply_checklist(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    old = pool.status; seen = set()
    def status(h):
        if h['subagent_id'] not in seen:
            seen.add(h['subagent_id']); callback_all(runner, store, pool, run, h)
        return old(h)
    pool.status = status
    result = runner.run(run, session_id='parent'); token = result['awaiting_parent'][0]
    a = store.get_attempt(run, token)
    with pytest.raises(UserError, match='checklist'):
        runner.accept(run, token, a['payload']['payload_sha256'], {'accepted': True, 'reason': 'Looks fine'}, session_id='parent')
    from alchemy_task.discovery_runner import CHECKLIST
    with pytest.raises(UserError, match='pages'):
        runner.accept(run, token, a['payload']['payload_sha256'], {'accepted': False, 'reason': 'Research is missing primary ownership', 'retryable': True, 'checklist': {k: 'Inspected available evidence' for k in CHECKLIST}}, session_id='parent')
    with pytest.raises(UserError, match='pages'):
        runner.accept(run, token, a['payload']['payload_sha256'], {'accepted': True, 'reason': 'Reviewed', 'checklist': {k: 'Checked evidence' for k in CHECKLIST}}, session_id='parent')


def test_semantic_repair_shares_two_ordinals_and_preserves_success(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=2)
    old = pool.status; seen = set()
    def status(h):
        if h['subagent_id'] not in seen:
            seen.add(h['subagent_id']); callback_all(runner, store, pool, run, h)
        return old(h)
    pool.status = status
    runner.run(run, session_id='parent')
    attempts = sorted(store.get_run(run)['attempts'].values(), key=lambda a: a['candidate_id'])
    from alchemy_task.discovery_runner import CHECKLIST
    bad = attempts[0]
    p = runner.fetch(run, bad['payload']['resource'], bad['payload']['payload_sha256'], session_id='parent')
    while p['has_more']:
        p = runner.fetch(run, bad['payload']['resource'], bad['payload']['payload_sha256'], cursor=p['next_cursor'], session_id='parent')
    runner.accept(run, bad['token'], bad['payload']['payload_sha256'], {'accepted': False, 'reason': 'Ownership contradiction in latest primary requires fresh research', 'retryable': True, 'checklist': {k: 'Evidence inspected; ownership gap remains' for k in CHECKLIST}}, session_id='parent')
    assert len(accept_all(runner, store, run)) == 1
    runner.run(run, session_id='parent')
    assert len(pool.requests) == 3
    assert len(accept_all(runner, store, run)) == 1
    assert runner.join(run, session_id='parent')['joined']
    assert [a['ordinal'] for a in store.get_run(run)['attempts'].values()].count(2) == 1



def test_fifo_rolling_three_and_missing_callback_is_not_success(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=8)
    report = runner.run(run, session_id='parent')
    assert len(pool.requests) == 16 # no full callbacks, two fresh attempts each
    assert [json.loads(r['context'])['ordinal'] for r in pool.requests[:8]] == [1] * 8
    assert report['max_logical_slots'] == 3
    assert report['status'] == 'complete' and report['counts']['failed'] == 8
    assert all(a['state'] == 'exhausted' for a in store.get_run(run)['attempts'].values() if a['ordinal'] == 2)
    assert all('allowed_toolsets' not in r and 'timeout_seconds' not in r and len(r['context']) <= 32000 for r in pool.requests)
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and joined['degraded']


def test_pending_timeout_is_fenced_not_false_retry_or_kill(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    pool.pending = True
    report = runner.run(run, session_id='parent')
    assert len(pool.requests) == 1
    a = next(iter(store.get_run(run)['attempts'].values()))
    assert a['state'] == 'admission_timeout' and a['fenced']
    assert a['cancellation']['unsupported'] is True
    # The cancellation may still land: the next call watches for it before
    # the fenced attempt is reported unknown. It is never relaunched.
    assert report['status'] == 'running' and report['unknown_candidates'] == []
    reports = drive(runner, store, run)
    assert reports[-1]['unknown_candidates'] == [a['candidate_id']] and len(pool.requests) == 1
    assert not runner.join(run, session_id='parent')['joined']


def test_missing_actual_identity_and_new_owner_cannot_adopt(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    with pytest.raises(UserError, match='identity'): runner.run(run, session_id='')
    with pytest.raises(UserError, match='parent'): runner.run(run, session_id='foreign')
    assert not pool.requests


def test_running_deadline_uses_observed_start_not_pending_or_progress(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    original = pool.status
    def forever_running(handle):
        return Status('RUNNING', pool.records[handle['subagent_id']]['started'])
    pool.status = forever_running
    fenced_at = []
    cancel = pool.cancel
    pool.cancel = lambda handle, *, reason: fenced_at.append(runner.clock.monotonic()) or cancel(handle, reason=reason)
    reports = drive(runner, store, run)  # several short calls, each inside its budget
    assert len(reports) >= 7 and len(pool.requests) == 1
    a = next(iter(store.get_run(run)['attempts'].values()))
    assert a['state'] == 'execution_timeout' and a['fenced']
    assert len(fenced_at) == 1 and 1800 <= fenced_at[0] < 1810
    assert a['cancellation']['unsupported']
    assert reports[-1]['unknown_candidates'] == [a['candidate_id']]


def test_unknown_launch_fenced_no_retry_and_unstarted_backlog_retained(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=52)
    called = []
    def fail_after_call(request): called.append(request); raise OSError('unknown admission transport loss')
    pool.launch = fail_after_call
    result = runner.run(run, session_id='parent')
    assert all(a['ordinal'] == 1 and a['state'] == 'launch_unknown' for a in store.get_run(run)['attempts'].values())
    assert len(called) <= 3
    assert len(result['queued']) >= 49


def test_early_callback_quarantine_and_cross_child_read_guard(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    c = store.get_run(run)['candidates'][0]
    a = store.reserve_attempt(run, c['candidate_id'], owner_session='parent')
    binding = {k: a[k] for k in __import__('alchemy_task.discovery_runner', fromlist=['BINDING_KEYS']).BINDING_KEYS}
    result = runner.submit(run, a['token'], binding, payload={}, session_id='early', task_id='cron-id')
    assert result['quarantined'] and not store.get_attempt(run, a['token'])['payload']
    store.record_start(run, parent_session='parent', child_session='correct', subagent_id='sa-correct')
    store.bind_attempt(run, a['token'], {'subagent_id': 'sa-correct'}, owner_session='parent')
    with pytest.raises(UserError):
        runner.fetch(run, 'manifest', store.resource_info(run, 'manifest')['sha256'], token=a['token'], binding=binding, session_id='foreign', task_id='sa-correct')
    with pytest.raises(UserError):
        runner.fetch(run, 'manifest', store.resource_info(run, 'manifest')['sha256'], token=a['token'], binding=binding, session_id='correct', task_id='sa-wrong')
    assert runner.pre_tool_call(tool_name='task_create', session_id='correct', task_id='cron-id')['action'] == 'block'


def test_new_owner_adoption_requires_non_model_approval(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    with pytest.raises(UserError, match='approval'):
        runner.recover(run, session_id='foreign', adopt=True)


def test_cross_cohort_overlap_cannot_authorize_parent_acceptance(tmp_path):
    from alchemy_task.discovery_runner import CHECKLIST
    from test_discovery_schema import bundle
    runner, store, pool, run = setup_runner(tmp_path, count=0)
    #201 selected parents: two different assignments cover one decisive source.
    items = [{'title': f'Work {i}', 'source_ids': [f'source:source:account:thread:t{i}']} for i in range(200)]
    items.append({'title': 'Refined overlapping work', 'source_ids': ['source:source:account:thread:t0:m1']})
    # setup froze an empty manifest; use a new authentic run with a fresh index.
    run = store.init_run(origin={'session_id': 'parent'})
    store.add_candidates(run, items); store.freeze_index(run, rubric='Full source and task research')
    cid = store.get_run(run)['candidates'][0]['candidate_id']
    a = store.reserve_attempt(run, cid, owner_session='parent', daily_limit=1000)
    store.record_start(run, parent_session='parent', child_session='child-overlap', subagent_id='sa-overlap')
    store.bind_attempt(run, a['token'], {'subagent_id': 'sa-overlap'}, owner_session='parent')
    for name in a['required_resources']:
        info = store.resource_info(run, name); cursor = None
        while True:
            p = runner.fetch(run, name, info['sha256'], token=a['token'], binding={k: a[k] for k in __import__('alchemy_task.discovery_runner', fromlist=['BINDING_KEYS']).BINDING_KEYS}, cursor=cursor, session_id='child-overlap')
            if not p['has_more']: break
            cursor = p['next_cursor']
    b = bundle(); b['candidate_id'] = cid
    b['workstreams'][0]['exact_source_ids'] = [{'type': 'source', 'source_key': 'source', 'account_key': 'account', 'object_kind': 'thread', 'object_id': 't0', 'message_id': 'm1'}]
    receipt = runner.submit(run, a['token'], {k: a[k] for k in __import__('alchemy_task.discovery_runner', fromlist=['BINDING_KEYS']).BINDING_KEYS}, payload=b, session_id='child-overlap')['receipt']
    store.observe_terminal(run, a['token'], state='SUCCEEDED', receipt={'terminal_state': 'SUCCEEDED'})
    p = runner.fetch(run, receipt['resource'], receipt['payload_sha256'], session_id='parent')
    while p['has_more']:
        p = runner.fetch(run, receipt['resource'], receipt['payload_sha256'], cursor=p['next_cursor'], session_id='parent')
    result = runner.accept(run, a['token'], receipt['payload_sha256'], {'accepted': True, 'reason': 'Reviewed all evidence', 'checklist': {k: 'Full review completed' for k in CHECKLIST}}, session_id='parent')
    assert not store.accepted_bundle(run, cid)
    assert store.get_attempt(run, a['token'])['state'] == 'rejected_retryable'
    assert result['rejected']
    assert not runner.join(run, session_id='parent')['joined']


def test_join_hook_is_idempotent_and_cancelled_handle_can_reconcile(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    pool.pending = True
    runner.run(run, session_id='parent')
    a = next(iter(store.get_run(run)['attempts'].values()))
    assert a['state'] == 'admission_timeout' and not a['terminal']
    pool.pending = False; pool.fail = True
    runner.recover(run, session_id='parent')
    assert store.get_attempt(run, a['token'])['terminal']['state'] == 'FAILED'
    assert store.get_attempt(run, a['token'])['state'] == 'rejected_retryable'
    pool.fail = True
    runner.run(run, session_id='parent')
    calls = []
    runner.proposal_hook = lambda run_id, result: calls.append(run_id) or {'review_ready': True}
    assert runner.join(run, session_id='parent')['joined']
    assert runner.join(run, session_id='parent')['joined']
    assert calls == [run]


@pytest.mark.parametrize('count', [51, 52, 201])
def test_zero_budget_retains_entire_fifo_across_cohorts(tmp_path, count):
    runner, store, pool, run = setup_runner(tmp_path, count=count, daily_limit=0)
    report = runner.run(run, session_id='parent')
    assert not pool.requests
    assert len(report['budget_deferred']) == count
    assert len(report['queued']) == count
    assert len(store.get_run(run)['candidates']) == count
    # Cap 0 defers research: a joined deferred audit, never failures or proposals.
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and not joined['failures'] and not joined['degraded'] and not joined['accepted']
    assert len(joined['deferred']) == count


def test_later_cohort_requires_outcome_bound_unambiguous_reconciliation(tmp_path):
    runner, store, pool, oldrun = setup_runner(tmp_path, count=0)
    run = store.init_run(origin={'session_id': 'parent'})
    store.add_candidates(run, [{'title': f'Work {i}', 'source_ids': [f'source:source:account:thread:t{i}'], 'prefilter_disposition': 'research' if i in {0, 200} else 'excluded'} for i in range(201)])
    store.freeze_index(run, rubric='Full source research')
    original = pool.status; seen = set()
    def status(h):
        if h['subagent_id'] not in seen:
            seen.add(h['subagent_id']); callback_all(runner, store, pool, run, h)
        return original(h)
    pool.status = status
    runner.run(run, session_id='parent'); accept_all(runner, store, run)
    assert not runner.join(run, session_id='parent')['joined']
    parents = [c for c in store.get_run(run)['candidates'] if not c.get('parent_candidate_id')]
    cid = parents[200]['candidate_id']
    result = runner.reconcile(run, cid, {'decision': 'ambiguous', 'reason': 'Possible same outcome needs parent choice', 'accepted_unit_ids': []}, session_id='parent')
    assert result['outcome_revision'] == store.get_run(run)['outcome_resource']['sha256']
    assert not runner.join(run, session_id='parent')['joined']


def test_authorized_new_parent_gets_pointer_and_deliberate_hold_release(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    cid = store.get_run(run)['candidates'][0]['candidate_id']
    a = store.reserve_attempt(run, cid, owner_session='parent')
    runner.recovery_authorizer = lambda run_id, old, new: old == 'parent' and new == 'new-parent'
    runner.recover(run, session_id='new-parent', adopt=True, owner_restarted=True)
    assert runner.pre_llm_call(session_id='new-parent')['context']
    assert runner.pre_llm_call(session_id='parent') is None
    held = runner.run(run, session_id='new-parent')
    assert held['status'] == 'held' and 'discovery_release_hold' in held['next_action']
    with pytest.raises(UserError): runner.release_hold(run, reason='', session_id='new-parent')
    runner.release_hold(run, reason='User deliberately releases remaining unstarted work; unknown launch remains fenced', session_id='new-parent')
    assert store.get_attempt(run, a['token'])['state'] == 'launch_unknown'
    result = runner.run(run, session_id='new-parent')
    assert not pool.requests and result['unknown_candidates'] == [cid]


def test_parent_tool_factory_does_not_accept_model_identity(tmp_path):
    from alchemy_task.discovery_runner import make_tool_handlers
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    handlers = make_tool_handlers(runner)
    result = json.loads(handlers['discovery_research_run']({'run_id': run, 'session_id': 'parent'}))
    assert result['ok'] is False and not pool.requests
