"""Outcome tests for research orchestration, the daily cap and hook cost.

Children are scripted per candidate and per ordinal through a public-shaped
lifecycle pool. Assertions read what the parent and user get: attempts and
launches, budget units, join records, guard verdicts and timings.
"""
import json
import shutil
import time
from types import SimpleNamespace

from test_discovery_runner import Pool, Status, accept_all, callback_all, drive, setup_runner
from alchemy_task.core.discovery_state import DiscoveryStore


class ScriptedPool(Pool):
    """behaviours: {candidate index: [ordinal 1, ordinal 2]} of valid | invalid | hang.

    A hanging child stays RUNNING until a cancellation is accepted and
    `cancel_effective` is true; then it reports CANCELLED.
    """

    def __init__(self, clock, store, run, behaviours):
        super().__init__(clock)
        self.store, self.run, self.behaviours = store, run, behaviours
        self.submitted, self.cancel_accepted = set(), set()
        self.cancel_effective = True

    def _behaviour(self, sid):
        boot = self.records[sid]['bootstrap']
        index = parents(self.store, self.run).index(boot['candidate_id'])
        seq = self.behaviours.get(index, ['valid', 'valid'])
        return seq[min(boot['ordinal'], len(seq)) - 1]

    def status(self, handle):
        sid = handle['subagent_id']
        record = self.records[sid]
        behaviour = self._behaviour(sid)
        if behaviour == 'hang':
            if sid in self.cancel_accepted and self.cancel_effective:
                record['ready'] = True
                return Status('CANCELLED', self.clock.time())
            return Status('RUNNING', record['started'])
        if sid not in self.submitted:
            self.submitted.add(sid)
            callback_all(self.runner, self.store, self, self.run, handle, invalid=behaviour == 'invalid')
        if self.clock.time() - record['started'] > 2:
            record['ready'] = True
            return Status('SUCCEEDED', self.clock.time())
        return Status('RUNNING', record['started'])

    def result(self, handle):
        sid = handle['subagent_id']
        record = self.records[sid]
        return {'ready': record['ready'], 'terminal_state': 'CANCELLED' if sid in self.cancel_accepted else 'SUCCEEDED',
                'started_at': record['started'], 'completed_at': self.clock.time(), 'summary': 'x', 'structured_payload': None}

    def reconnect(self, handle):
        return {'connected': True, 'state': self.status(handle).state}

    def cancel(self, handle, *, reason):
        self.cancelled.append((handle, reason))
        self.cancel_accepted.add(handle['subagent_id'])
        return {'accepted': True, 'state': 'CANCEL_REQUESTED'}


def make(tmp_path, count, behaviours, **policy):
    runner, store, _, run = setup_runner(tmp_path, count=count, **policy)
    pool = ScriptedPool(runner.clock, store, run, behaviours)
    pool.runner = runner
    runner.ctx.subagent_lifecycle = pool
    return runner, store, pool, run


def parents(store, run):
    return [c['candidate_id'] for c in store.get_run(run)['candidates'] if not c.get('parent_candidate_id')]


def attempts_for(store, run, cid):
    return sorted((a for a in store.get_run(run)['attempts'].values() if a['candidate_id'] == cid), key=lambda a: a['ordinal'])


def charged_units(store):
    return sum(len(json.loads(p.read_text())['charged']) for p in (store.state_root / 'budgets').glob('*.json'))


# ---------------------------------------------------------------- ORC-F1

def test_timed_out_researcher_gets_its_one_fresh_retry_in_the_normal_flow(tmp_path):
    runner, store, pool, run = make(tmp_path, 2, {0: ['hang', 'valid'], 1: ['valid']})
    ids = parents(store, run)
    reports = drive(runner, store, run)  # the skill's short calls on the SAME run
    # The cancelled child's terminal state is observed: never left as an unknown.
    assert all(r['unknown_candidates'] == [] for r in reports)
    attempts = attempts_for(store, run, ids[0])
    assert [a['ordinal'] for a in attempts] == [1, 2]
    retry = json.loads(pool.requests[-1]['context'])
    assert retry['candidate_id'] == ids[0] and retry['repair']['reason']['reason'] == 'execution_timeout'
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and not joined['degraded'] and sorted(joined['accepted']) == sorted(ids)
    assert len(pool.requests) == 3 and charged_units(store) == 2  # the retry reuses its budget unit


def test_timeout_whose_cancellation_lands_later_is_retried_on_resume(tmp_path):
    runner, store, pool, run = make(tmp_path, 1, {0: ['hang', 'valid']})
    cid = parents(store, run)[0]
    pool.cancel_effective = False  # cancel accepted, child still unwinding when the call ends
    while not pool.cancelled:
        first = runner.run(run, session_id='parent')
    # The fenced timeout is still settling: research is reported running, not unknown.
    assert first['status'] == 'running' and first['unknown_candidates'] == [] and first['counts']['running'] == 1
    pool.cancel_effective = True
    drive(runner, store, run)
    assert [a['ordinal'] for a in attempts_for(store, run, cid)] == [1, 2]
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and joined['accepted'] == [cid] and not joined['failures']


# ---------------------------------------------------------------- ORC-F2 / ORC-F7

def test_cap_reached_still_runs_an_already_charged_repair(tmp_path):
    runner, store, pool, run = make(tmp_path, 4, {0: ['invalid', 'valid'], 1: ['valid']}, daily_limit=2)
    ids = parents(store, run)
    report = runner.run(run, session_id='parent')
    accept_all(runner, store, run)
    assert [a['ordinal'] for a in attempts_for(store, run, ids[0])] == [1, 2]
    assert charged_units(store) == 2
    assert report['budget_deferred'] == ids[2:]  # never the charged repair
    joined = runner.join(run, session_id='parent')
    assert sorted(joined['accepted']) == sorted(ids[:2])


def test_timeout_retry_runs_even_when_cap_is_exhausted(tmp_path):
    # The retry becomes eligible only on the parent's SECOND research call,
    # after the cap is already exhausted and a never-started candidate is
    # refused first: that refusal must not drop the charged retry.
    runner, store, pool, run = make(tmp_path, 3, {0: ['hang', 'valid']}, daily_limit=2)
    ids = parents(store, run)
    drive(runner, store, run)
    assert [a['ordinal'] for a in attempts_for(store, run, ids[0])] == [1, 2]
    assert charged_units(store) == 2
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and not joined['failures']
    assert sorted(joined['accepted']) == sorted(ids[:2])
    assert [d['candidate_id'] for d in joined['deferred']] == [ids[2]]


def test_budget_deferred_lists_each_candidate_once(tmp_path):
    runner, store, pool, run = make(tmp_path, 5, {}, daily_limit=2)
    ids = parents(store, run)
    report = runner.run(run, session_id='parent')
    assert report['budget_deferred'] == ids[2:]


# ---------------------------------------------------------------- ORC-F3 (runner)

def test_cap_deferred_work_joins_as_deferred_not_failed(tmp_path):
    runner, store, pool, run = make(tmp_path, 4, {}, daily_limit=2)
    ids = parents(store, run)
    runner.run(run, session_id='parent')
    accept_all(runner, store, run)
    joined = runner.join(run, session_id='parent')
    assert joined['joined'] and not joined['degraded'] and joined['failures'] == []
    assert sorted(joined['accepted']) == sorted(ids[:2])
    assert [d['candidate_id'] for d in joined['deferred']] == ids[2:]
    assert all('cap' in d['reason'] for d in joined['deferred'])


def test_degraded_acknowledgement_does_not_relabel_a_cap_deferral_as_failure(tmp_path):
    runner, store, pool, run = make(tmp_path, 2, {}, daily_limit=1)
    ids = parents(store, run)
    runner.run(run, session_id='parent')
    accept_all(runner, store, run)
    joined = runner.join(run, session_id='parent', degraded={ids[1]: 'Daily research cap reached'})
    assert joined['joined'] and not joined['failures'] and [d['candidate_id'] for d in joined['deferred']] == [ids[1]]


# ---------------------------------------------------------------- ORC-F4

def test_ordinary_task_research_from_the_same_chat_is_not_a_discovery_child(tmp_path):
    runner, store, pool, run = make(tmp_path, 2, {})
    report = runner.run(run, session_id='parent')
    assert report['status'] == 'running' and len(report['awaiting_parent']) == 2  # run stays open
    assert 'discovery_research_accept' in report['next_action']
    runner.subagent_start(parent_session_id='parent', child_session_id='ordinary-child', child_subagent_id='sa-ordinary')
    for tool in ('research_submit', 'task_update', 'write_file', 'patch'):
        assert runner.pre_tool_call(tool_name=tool, session_id='ordinary-child', task_id='sa-ordinary') is None
    # Real discovery children of the run stay read-only.
    assert runner.pre_tool_call(tool_name='task_create', session_id='child-1', task_id='sa-1')['action'] == 'block'


def test_child_started_during_a_discovery_launch_is_released_once_the_launch_binds(tmp_path):
    runner, store, pool, run = make(tmp_path, 1, {})
    original = pool.launch
    seen = {}

    def launch(request):
        # The user's ordinary research child starts while discovery's own launch is in flight.
        runner.subagent_start(parent_session_id='parent', child_session_id='ordinary-child', child_subagent_id='sa-ordinary')
        seen['during'] = runner.pre_tool_call(tool_name='research_submit', session_id='ordinary-child', task_id='sa-ordinary')
        return original(request)
    pool.launch = launch
    report = runner.run(run, session_id='parent')
    assert len(report['awaiting_parent']) == 1  # discovery child bound exactly and submitted
    assert seen['during']['action'] == 'block'  # conservative while the launch is unresolved
    assert runner.pre_tool_call(tool_name='research_submit', session_id='ordinary-child', task_id='sa-ordinary') is None
    assert runner.pre_tool_call(tool_name='task_create', session_id='child-1', task_id='sa-1')['action'] == 'block'


def test_child_of_an_unknown_discovery_launch_stays_blocked(tmp_path):
    runner, store, pool, run = make(tmp_path, 1, {})

    def lost(request):
        runner.subagent_start(parent_session_id='parent', child_session_id='lost-child', child_subagent_id='sa-lost')
        raise OSError('transport lost after the host accepted the launch')
    pool.launch = lost
    runner.run(run, session_id='parent')
    assert runner.pre_tool_call(tool_name='task_create', session_id='lost-child', task_id='sa-lost')['action'] == 'block'


def test_child_start_between_launch_reply_and_bind_is_still_a_discovery_child(tmp_path):
    # Simulated host whose subagent_start lands after launch returns but before
    # the runner binds the handle (the contract lets start and return race).
    runner, store, pool, run = make(tmp_path, 1, {})
    original_launch, original_bind, real_start = pool.launch, store.bind_attempt, runner.subagent_start
    seen = {}

    def launch(request):
        runner.subagent_start = lambda **kw: None  # the host has not fired the start hook yet
        try:
            seen['handle'] = original_launch(request)
        finally:
            runner.subagent_start = real_start
        return seen['handle']

    def bind(run_id, token, handle, **kw):
        if not seen.get('fired'):
            seen['fired'] = True
            real_start(parent_session_id='parent', child_session_id='late-child', child_subagent_id=handle['subagent_id'])
        return original_bind(run_id, token, handle, **kw)
    pool.launch, store.bind_attempt = launch, bind
    try:
        runner.run(run, session_id='parent')
    except Exception:
        pass  # the scripted child of this host cannot submit; the guard verdict is the outcome
    assert seen.get('fired')
    verdict = runner.pre_tool_call(tool_name='task_create', session_id='late-child', task_id='')
    assert verdict and verdict['action'] == 'block'


# ---------------------------------------------------------------- ORC-F5

def _month_of_runs(tmp_path, runs=30, attempts=50):
    """A template run with bound children, cloned into a profile's existing state."""
    template = DiscoveryStore(tmp_path / 'template')
    run = template.init_run(origin={'session_id': 'cron-0'}, business_date='2026-01-01', stream='s')
    template.add_candidates(run, [{'title': f'Work {i}', 'source_ids': [f'source:source:account:thread:t{i}']} for i in range(attempts)])
    template.freeze_index(run, rubric='x' * 20000)
    for i, c in enumerate(template.get_run(run)['candidates'][:attempts]):
        a = template.reserve_attempt(run, c['candidate_id'], owner_session='cron-0', daily_limit=10000)
        template.record_start(run, parent_session='cron-0', child_session=f'child-{i}', subagent_id=f'sa-{i}')
        template.bind_attempt(run, a['token'], {'subagent_id': f'sa-{i}'}, owner_session='cron-0')
    text = (template.run_dir(run) / 'ledger.json').read_text()
    root = tmp_path / 'profile' / 'discovery'
    for r in range(runs):
        new = f'run{r:02d}' + 'a' * 26
        target = root / 'runs' / new
        shutil.copytree(template.run_dir(run), target)
        (target / 'ledger.json').write_text(text.replace(run, new).replace('cron-0', f'cron-{r}')
                                            .replace('"child-', f'"r{r}-child-').replace('"sa-', f'"sa-r{r}-'))
    return root


def test_hooks_stay_fast_and_write_nothing_with_a_month_of_retained_runs(tmp_path):
    from alchemy_task.discovery_runner import DiscoveryRunner
    root = _month_of_runs(tmp_path)
    store = DiscoveryStore(root)  # existing profile state from before any index existed
    runner = DiscoveryRunner(SimpleNamespace(subagent_lifecycle=None), SimpleNamespace(data_dir=tmp_path), store=store)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file() and 'locks' not in p.parts}
    started = time.perf_counter()
    for _ in range(100):
        assert runner.pre_tool_call(tool_name='terminal', session_id='unrelated', task_id='') is None
    tool_ms = (time.perf_counter() - started) * 10
    started = time.perf_counter()
    for _ in range(100):
        assert runner.pre_llm_call(session_id='unrelated') is None
    llm_ms = (time.perf_counter() - started) * 10
    print(f'pre_tool_call {tool_ms:.3f} ms, pre_llm_call {llm_ms:.3f} ms per unrelated call')
    assert tool_ms < 5 and llm_ms < 5, (tool_ms, llm_ms)
    after = {p: p.read_bytes() for p in root.rglob('*') if p.is_file() and 'locks' not in p.parts}
    assert {p: b for p, b in after.items() if p in before} == before
    assert not [p for p in after if p not in before and p.name == 'supervisor.json']
    # The fast path keeps exact answers for real owners and children.
    assert 'run17' in runner.pre_llm_call(session_id='cron-17')['context']
    assert runner.pre_tool_call(tool_name='task_create', session_id='r17-child-3', task_id='sa-r17-3')['action'] == 'block'
    assert runner.pre_tool_call(tool_name='task_create', session_id='r17-child-3', task_id='')['action'] == 'block'


# ---------------------------------------------------------------- ORC-T1

def test_repair_child_receives_the_exact_rejection_and_the_old_payload(tmp_path):
    runner, store, pool, run = make(tmp_path, 3, {1: ['invalid', 'valid']})
    ids = parents(store, run)
    runner.run(run, session_id='parent')
    accept_all(runner, store, run)
    runner.run(run, session_id='parent')
    accept_all(runner, store, run)
    joined = runner.join(run, session_id='parent')
    assert len(pool.requests) == 4 and joined['joined'] and not joined['degraded'] and sorted(joined['accepted']) == sorted(ids)
    assert charged_units(store) == 3
    first, second = attempts_for(store, run, ids[1])
    repair = json.loads(pool.requests[-1]['context'])
    assert repair['candidate_id'] == ids[1] and repair['ordinal'] == 2 and repair['token'] == second['token']
    assert first['rejection']['reason'] == first['validation_error']
    assert repair['repair']['reason'] == first['rejection']
    assert repair['repair']['payload'] == first['payload']
    old = first['payload']['resource']
    assert repair['resources'][old] == store.resource_info(run, old)
    # The repair child actually read every page of the rejected payload with its own capability.
    assert store._has_pages(store.get_run(run), second['token'], old)
    # Successful siblings were not rerun.
    assert [len(attempts_for(store, run, c)) for c in ids] == [1, 2, 1]


# ---------------------------------------------------------------- ORC-F3 / E2E-2 (digest and backlog)

def test_cap_deferral_is_a_separate_digest_line_and_stays_queued_for_the_next_run(settings, data_dir, tmp_path):
    from alchemy_task.discovery_integration import register
    from alchemy_task.discovery_runner import CHECKLIST
    from test_discovery_integration import configure, service
    from test_discovery_schema import bundle
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    streams = ctx.state.get('streams'); streams['work']['research_cap'] = 1; ctx.state.set('streams', streams)
    configure(integration)
    items = [{'title': 'Review release notes', 'source_ids': ['source:feed:account:issue:one'], 'source_revision': 'v1'},
             {'title': 'Plan vendor renewal', 'source_ids': ['source:feed:account:issue:two'], 'source_revision': 'v1'}]
    feed = {'items': items}
    ctx.dispatch_tool = lambda tool, args: json.dumps({'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
                                                     'items': feed['items'], 'next_cursor': None, 'pagination_exhausted': True})
    clock = __import__('test_discovery_runner').Clock()
    pool = Pool(clock); ctx.subagent_lifecycle = pool; pool.runner = integration.runner; integration.runner.clock = clock
    tools = {}
    ctx.register_tool = lambda **kw: tools.update({kw['name']: kw['handler']})
    ctx.register_hook = lambda name, fn: None
    register(ctx, integration=integration)

    def call(name, args, session='parent'):
        result = json.loads(tools[name](args, session_id=session))
        assert result['ok'], result
        return result['result']
    original = pool.status
    done = set()

    def status(handle):
        boot = pool.records[handle['subagent_id']]['bootstrap']
        if handle['subagent_id'] not in done:
            child = 'child-' + handle['subagent_id'].split('-')[-1]
            for name, info in boot['resources'].items():
                cursor = None
                while True:
                    page = call('discovery_research_fetch', {'run_id': boot['run_id'], 'resource': name, 'revision': info['sha256'], 'token': boot['token'],
                                                             'binding': boot['binding'], **({'cursor': cursor} if cursor else {})}, child)
                    if not page['has_more']: break
                    cursor = page['next_cursor']
            source = integration.store.get_candidate(boot['run_id'], boot['candidate_id'])['source_ids'][0]
            payload = bundle(); payload['candidate_id'] = boot['candidate_id']
            payload['workstreams'][0]['exact_source_ids'] = [{'type': 'source', 'source_key': 'feed', 'account_key': 'account', 'object_kind': 'issue', 'object_id': source.split(':')[-1]}]
            call('discovery_research_submit', {'run_id': boot['run_id'], 'token': boot['token'], 'binding': boot['binding'], 'payload': payload}, child)
            done.add(handle['subagent_id'])
        return original(handle)
    pool.status = status

    def day():
        run = integration.start('work', session_id='parent')['run_id']
        assert call('discovery_collect', {'run_id': run, 'source_key': 'feed'})['status'] == 'complete'
        revision = call('discovery_context', {'run_id': run})['index_revision']
        report = call('discovery_research_run', {'run_id': run, 'expected_revision': revision})
        for token in report['awaiting_parent']:
            info = integration.store.get_attempt(run, token)['payload']; cursor = None
            while True:
                page = call('discovery_research_fetch', {'run_id': run, 'resource': info['resource'], 'revision': info['payload_sha256'], **({'cursor': cursor} if cursor else {})})
                if not page['has_more']: break
                cursor = page['next_cursor']
            call('discovery_research_accept', {'run_id': run, 'token': token, 'payload_sha256': info['payload_sha256'],
                 'assessment': {'accepted': True, 'reason': 'Full primary and all plausible tasks show an independent user action.',
                                'checklist': {k: 'Reviewed all supplied full evidence.' for k in CHECKLIST}}})
        joined = call('discovery_join', {'run_id': run})
        assert joined['joined'], joined
        for unit in [c['candidate_id'] for c in integration.store.get_run(run)['candidates'] if c.get('parent_candidate_id')]:
            assert call('discovery_match', {'run_id': run, 'unit_id': unit})['kind'] == 'new'
            call('discovery_decision', {'run_id': run, 'unit_id': unit, 'decision': 'propose', 'reason': 'Independent untracked action.'})
        return run, report, call('discovery_digest', {'run_id': run})

    run, report, digest = day()
    lines = digest['text'].splitlines()
    assert lines[1].endswith(': 1 new proposals; 0 existing-task outcomes; 0 failures; 1 deferred')
    assert 'degraded' not in digest['text'] and not [l for l in lines if l.startswith('Attention:')]
    assert 'Deferred: Plan vendor renewal: Daily research cap reached; queued for the next run' in lines
    assert 'Coverage: feed: complete' in lines
    backlog = {e['candidate']['title']: e['status'] for e in integration.store.source_state('work', 'feed')['backlog']}
    assert backlog == {'Review release notes': 'accepted', 'Plan vendor renewal': 'deferred'}
    record = call('discovery_runs', {'run_id': run})
    assert record['summary']['failures'] == 0 and record['summary']['deferred'] == 1 and not record['degraded']
    assert [d['title'] for d in record['deferred']] == ['Plan vendor renewal']

    # Same day, nothing new at the source: the deferred item is carried, researched
    # only when budget allows, and a deferred-only day is not "nothing new".
    feed['items'] = []
    run2, report2, digest2 = day()
    assert run2 != run and [integration.store.get_candidate(run2, c)['title'] for c in report2['budget_deferred']] == ['Plan vendor renewal']
    assert 'No new follow-ups found.' not in digest2['text'] and 'degraded' not in digest2['text']
    assert 'Deferred: Plan vendor renewal: Daily research cap reached; queued for the next run' in digest2['text'].splitlines()
    assert {e['candidate']['title']: e['status'] for e in integration.store.source_state('work', 'feed')['backlog']}['Plan vendor renewal'] == 'deferred'


def test_start_prunes_old_closed_runs_but_keeps_replyable_and_resumable_ones(settings, data_dir, tmp_path):
    import os
    from test_discovery_integration import configure, service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    store = integration.store
    month_ago = time.time() - 70 * 86400

    def closed(stream, age):
        run = store.init_run(stream=stream, business_date='2026-01-01', origin={'session_id': 'old-parent'})
        store.save_review(run, {'joined': {'accepted': [], 'failures': []}})
        os.utime(store.run_dir(run) / 'ledger.json', (age, age))
        return run
    old = closed('archive', month_ago)
    recent = closed('archive', time.time() - 3 * 86400)  # still inside the seven-day reply window
    unfinished = store.init_run(stream='archive', business_date='2026-01-01', origin={'session_id': 'old-parent'})
    os.utime(store.run_dir(unfinished) / 'ledger.json', (month_ago, month_ago))
    # A blocked item in some source's durable backlog does not pin every run forever;
    # the backlog itself lives outside run directories and is never pruned.
    store.enqueue_backlog('archive', 'feed', [{'source_ids': ['source:feed:account:issue:x'], 'source_revision': 'v1', 'candidate': {'title': 'Blocked', 'source_ids': ['source:feed:account:issue:x']}}])
    bid = store.source_state('archive', 'feed')['backlog'][0]['backlog_id']
    store.update_backlog('archive', 'feed', bid, status='blocked', lineage={'run_id': unfinished})
    integration.start('work', session_id='parent')
    assert not store.run_dir(old).exists() and store.get_run(old)['pruned_at']  # readable tombstone
    assert store.run_dir(recent).exists() and store.run_dir(unfinished).exists()
    assert store.source_state('archive', 'feed')['backlog'][0]['status'] == 'blocked'


def _closed_work_run(integration, *, day, delivery, proposal_state=None, frozen_owner=None):
    """A finalized run of the SAME stream start() runs, with its digest record."""
    from alchemy_task.core.discovery_state import atomic_json
    store = integration.store
    run = store.init_run(stream='work', business_date=day, origin={'session_id': 'parent'})
    store.save_review(run, {'joined': {'accepted': [], 'failures': []}})
    data = integration.digest._load()
    data['digests'][run] = {'sha256': 'digest-sha', 'run_id': run, 'stream': 'work', 'day': day, 'origin': {'session_id': 'parent'}}
    if frozen_owner:
        data['digests'][run]['origin']['delivery_owner'] = frozen_owner  # N4: owner frozen at finalize
    data['delivery'][run] = {'digest_sha256': 'digest-sha', 'origin': {'session_id': 'parent'}, **delivery}
    if proposal_state:
        # One proposed unit whose plan was approved but not yet written.
        with store._lock(store._run_lock_name(run)):
            ledger = store.get_run(run)
            ledger['candidates'].append({'candidate_id': 'unit-1', 'parent_candidate_id': 'parent-1', 'state': 'proposed', 'title': 'Unit'})
            store._save(run, ledger)
        (store.run_dir(run) / 'decisions').mkdir(exist_ok=True)
        atomic_json(store.run_dir(run) / 'decisions' / 'unit-1.json', {'request': {'decision': 'propose'}})
        data['proposals']['p_unit'] = {'binding': {'run_id': run, 'unit_id': 'unit-1'}, 'state': proposal_state}
    atomic_json(integration.digest.path, data)
    # An earlier start already reconciled it; it has been untouched since.
    integration.reconcile_endstate(run)
    old = time.time() - 70 * 86400
    import os
    os.utime(store.run_dir(run) / 'ledger.json', (old, old))
    return run


def test_start_prunes_an_old_settled_run_of_the_stream_it_starts(settings, data_dir, tmp_path):
    from test_discovery_integration import configure, service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    store = integration.store
    verified = _closed_work_run(integration, day='2026-01-01', delivery={'state': 'delivered', 'verified_sha256': 'digest-sha', 'readback': {'message_id': 'm', 'target': 't'}})
    integration.start('work', session_id='parent')
    assert not store.run_dir(verified).exists() and store.get_run(verified)['pruned_at']


def test_native_origin_runs_are_pruned_only_after_their_reply_window(settings, data_dir, tmp_path):
    import datetime as dt
    from test_discovery_integration import configure, service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    store = integration.store
    today = dt.date.today().isoformat()
    # The stream's default owner is native_origin: the host posts and retries,
    # so the plugin never holds a verified receipt for these digests.
    expired = _closed_work_run(integration, day='2026-01-01', delivery={'state': 'prepared'})
    replyable = _closed_work_run(integration, day=today, delivery={'state': 'prepared'})
    approved = _closed_work_run(integration, day='2026-01-01', delivery={'state': 'prepared'}, proposal_state='approved')
    send_unknown = _closed_work_run(integration, day='2026-01-01', delivery={'state': 'unknown'})
    integration.start('work', session_id='parent')
    assert not store.run_dir(expired).exists() and store.get_run(expired)['pruned_at']
    assert store.run_dir(replyable).exists()  # still inside the seven-day reply window
    assert store.run_dir(approved).exists() and store.get_run(approved)['pending_operations'] == ['candidate:unit-1']
    assert store.run_dir(send_unknown).exists()  # an explicit send without proof is never forgotten


def test_native_digest_window_follows_the_owner_frozen_with_the_digest(settings, data_dir, tmp_path):
    """R2-4: a stream switched from native to verified-sender after a digest still closes that
    native digest after its reply window; a never-sent verified-sender digest is never closed."""
    from test_discovery_integration import configure, service
    from alchemy_task.discovery import _streams, _save_streams
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    store = integration.store
    streams = _streams(rt); streams['work'] = {**streams['work'], 'delivery_owner': 'verified_sender'}; _save_streams(rt, streams)
    native = _closed_work_run(integration, day='2026-01-01', delivery={'state': 'prepared'}, frozen_owner='native_origin')
    unsent = _closed_work_run(integration, day='2026-01-01', delivery={'state': 'prepared'}, frozen_owner='verified_sender')
    assert store.get_run(native)['pending_operations'] == []
    assert store.get_run(unsent)['pending_operations'] == ['digest_delivery']
    streams = _streams(rt); streams['work'] = {**streams['work'], 'delivery_owner': 'native_origin'}; _save_streams(rt, streams)
    assert integration.reconcile_endstate(unsent)['pending_operations'] == ['digest_delivery']
    out = store.prune(days=60)
    assert native in out['deleted_runs'] and unsent not in out['deleted_runs']
