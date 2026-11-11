"""Fail-open discovery: one item's problem never stops a run from reaching its digest."""
import json

from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.discovery_state import read_json
from test_discovery_runner import setup_runner, accept_all, drive
from test_discovery_primary_unreadable import _child_reports
from test_discovery_conversion_outcomes import _integration, _register_tools


def _units(store, run):
    return [c['candidate_id'] for c in store.get_run(run)['candidates'] if c.get('parent_candidate_id')]


def test_match_and_decision_failures_land_under_needs_attention(settings, data_dir, tmp_path):
    integration, rt, ctx, store, run = _integration(settings, data_dir, tmp_path, count=3)
    first, second, third = _units(store, run)
    real_match = integration.conversion.match

    def broken(run_id, unit_id):
        if unit_id in {first, second}:
            raise UserError('malformed existing dossier markers')
        return real_match(run_id, unit_id)
    integration.conversion.match = broken
    tools = _register_tools(integration, ctx)
    out = json.loads(tools['discovery_match']({'run_id': run, 'unit_id': first}, session_id='parent'))
    assert out['ok'] is True and out['result']['failed'] is True
    assert 'could not be matched to your tasks: malformed' in out['result']['reason']
    out = json.loads(tools['discovery_decision']({'run_id': run, 'unit_id': second, 'decision': 'propose', 'reason': 'New ask.'}, session_id='parent'))
    assert out['ok'] is True and out['result']['kind'] == 'failed'
    integration.record_decision(run, third, decision='propose', reason='Independent untracked ask.', session_id='parent')
    tasks_before = sorted(p.name for p in rt.store().root.rglob('*.md'))
    digest = integration.finalize(run, session_id='parent')
    reasons = [f['reason'] for f in digest['failures']]
    assert sum('could not be matched to your tasks' in r for r in reasons) == 2
    assert len(digest['items']) == 1
    assert sorted(p.name for p in rt.store().root.rglob('*.md')) == tasks_before  # no automatic writes
    pending = integration.reconcile_endstate(run)['pending_operations']
    assert 'candidate:' + first not in pending and 'candidate:' + second not in pending


def test_caller_mistakes_still_refuse(settings, data_dir, tmp_path):
    integration, rt, ctx, store, run = _integration(settings, data_dir, tmp_path, count=1)
    try:
        integration.match(run, 'w-not-a-unit', session_id='parent')
    except (UserError, KeyError) as exc:
        assert 'malformed' not in str(exc)
    else:
        raise AssertionError('unknown unit must be refused')


def test_finalize_turns_unreviewed_units_into_failures(settings, data_dir, tmp_path):
    integration, rt, ctx, store, run = _integration(settings, data_dir, tmp_path, count=2)
    first, second = _units(store, run)
    integration.record_decision(run, first, decision='propose', reason='Independent untracked ask.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    assert [f['reason'] for f in digest['failures']] == ['not reviewed in this run']
    assert len(digest['items']) == 1
    state = integration.reconcile_endstate(run)
    assert 'candidate:' + second not in state['pending_operations']


def test_unreadable_primaries_fail_only_their_items(tmp_path):
    from alchemy_task.discovery_runner import PRIMARY_UNREADABLE_REASON
    runner, store, pool, run = setup_runner(tmp_path, count=4, slots=2)
    _child_reports(runner, store, pool, run, failing={1, 2})
    reports = drive(runner, store, run)
    assert all(r['status'] != 'held' for r in reports)
    assert len(pool.requests) == 4  # the run kept launching after two unreadable sources
    assert any('saved conversation could not be read' in r.get('note', '') for r in reports)
    join = runner.join(run, session_id='parent')
    assert join['joined'] and len(join['accepted']) == 2
    assert [f['reason'] for f in join['failures']] == [PRIMARY_UNREADABLE_REASON] * 2
    instructions = json.loads(pool.requests[0]['context'])['instructions']
    assert 'If the saved source is incomplete, research from what it contains and note the gap; do not stop.' in instructions


def test_finish_now_and_time_box_defer_unlaunched_work(tmp_path):
    from alchemy_task.discovery_runner import RESEARCH_TIME_BOX_SECONDS, TIME_BOX_DEFERRED_REASON
    # finish_now before anything starts: nothing launches, every item is deferred, the run is complete.
    runner, store, pool, run = setup_runner(tmp_path / 'a', count=3, slots=1)
    report = runner.run(run, session_id='parent', finish_now=True)
    assert report['status'] == 'complete' and report['counts']['deferred'] == 3 and not pool.requests
    join = runner.join(run, session_id='parent')
    assert join['joined'] and [d['reason'] for d in join['deferred']] == [TIME_BOX_DEFERRED_REASON] * 3
    # Automatic time box: after 50 minutes of research no new child starts.
    runner, store, pool, run = setup_runner(tmp_path / 'b', count=4, slots=1, admission_seconds=3)
    _child_reports(runner, store, pool, run, failing=set())
    runner.run(run, session_id='parent')
    accept_all(runner, store, run)
    launched = len(pool.requests)
    assert 0 < launched < 4
    runner.clock.value += RESEARCH_TIME_BOX_SECONDS + 1
    report = runner.run(run, session_id='parent')
    assert report['status'] == 'complete' and report['finishing'] == 'time_box'
    assert len(pool.requests) == launched
    join = runner.join(run, session_id='parent')
    assert join['joined'] and len(join['deferred']) == 4 - launched
    supervisor = read_json(store.run_dir(run) / 'supervisor.json')
    assert supervisor['finish_now'] == 'time_box' and supervisor['research_started_at']
