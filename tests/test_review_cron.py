"""Review item 2: scheduled runs never create or change scheduled jobs, and a stream's job runs its own slot,
"run now" and follow-ups through a free 30-minute wake check instead of extra jobs."""
import datetime as dt
import json
import subprocess
import sys

import pytest

from alchemy_task import discovery, jobs, runtime, task_tools
from alchemy_task.core import precheck
from test_discovery_integration import service
from test_setup import home  # noqa: F401  (fixture)

NY = 'America/New_York'
FIRE = dict(execution_id='fire-1', profile='test', scheduled_instant='2030-01-01T00:30:00Z', source='builtin')


def _at(text, zone=NY):
    from zoneinfo import ZoneInfo
    return dt.datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(zone)).astimezone(dt.timezone.utc)


def _stream(integration, rt, ctx, frequency='daily', time='6 PM'):
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    out = discovery.create_stream(rt, {'name': 'work', 'sources': [{'name': 'Feed', 'scope': 'board'}],
                                       'frequency': frequency, 'time': time, 'user_approved': True}, 'parent')
    return out['job_id']


# ------------------------------------------------------------------ guard

def test_every_scheduling_path_refuses_inside_a_scheduled_run(settings, data_dir, tmp_path, home, monkeypatch):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    jid = _stream(integration, rt, ctx)
    runtime.bind(ctx)
    try:
        before = json.loads(json.dumps(ctx.cron))
        monkeypatch.setattr(jobs, 'agent_scheduling_allowed', lambda: False)
        ctx.current_cron_execution = lambda: {**FIRE, 'job_id': jid}
        for args in ({'action': 'create', 'name': 'more', 'sources': [{'name': 'x', 'scope': 'y'}], 'user_approved': True},
                     {'action': 'update', 'name': 'work', 'time': '9 AM', 'user_approved': True},
                     {'action': 'remove', 'name': 'work'}, {'action': 'run_now', 'name': 'work'},
                     {'action': 'reconcile_jobs'}):
            out = json.loads(task_tools.discovery_stream(args, session_id='cron-session'))
            assert out['ok'] is False and out['message'] == jobs.SCHEDULING_REFUSED, args
        for action in ('jobs_create', 'teardown'):
            out = json.loads(task_tools.task_setup({'action': action, 'user_approved': True, 'user_confirmed': True},
                                                   session_id='cron-session'))
            assert out['ok'] is False and out['message'] == jobs.SCHEDULING_REFUSED
        stream = ctx.state.get('streams')['work']
        with pytest.raises(jobs.SchedulingRefused):
            jobs.reconcile_discovery_job(rt, stream)
        with pytest.raises(jobs.SchedulingRefused):
            jobs.activate_discovery_job(rt, {**stream, 'job_id': None})
        with pytest.raises(jobs.SchedulingRefused):
            jobs.run_stream_now(rt, stream)
        with pytest.raises(discovery.DiscoveryError, match='Scheduled runs cannot'):
            discovery.remove_stream(rt, 'work')
        assert jobs.reverify_sweep(rt)['state'] == 'refused'
        assert ctx.cron == before  # nothing created, changed or removed
        # The Hermes switch cron.allow_agent_scheduling lifts the refusal, as it does for Hermes's own cron tool.
        monkeypatch.setattr(jobs, 'agent_scheduling_allowed', lambda: True)
        assert json.loads(task_tools.discovery_stream({'action': 'reconcile_jobs'}, session_id='cron-session'))['ok']
        # A chat (no cron execution) keeps working.
        monkeypatch.setattr(jobs, 'agent_scheduling_allowed', lambda: False)
        ctx.current_cron_execution = lambda: None
        out = json.loads(task_tools.discovery_stream({'action': 'update', 'name': 'work', 'time': '9 AM',
                                                      'user_approved': True}, session_id='parent'))
        assert out['ok'], out
    finally:
        runtime.bind(None)


def test_allow_agent_scheduling_reads_the_public_hermes_config(monkeypatch):
    import hermes_cli.config as config
    for value, allowed in ((True, True), ('true', True), (False, False), (None, False), ('no', False)):
        monkeypatch.setattr(config, 'load_config_readonly', lambda value=value: {'cron': {'allow_agent_scheduling': value}})
        assert jobs.agent_scheduling_allowed() is allowed


# ------------------------------------------------------------------ the stream job

def test_stream_job_ticks_every_30_minutes_with_a_wake_check_and_no_shell_or_file_toolsets(settings, data_dir, tmp_path, home):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    jid = _stream(integration, rt, ctx)
    job = ctx.cron[jid]
    stream = ctx.state.get('streams')['work']
    assert job['schedule'] == '*/30 * * * *' and stream['schedule'] == '0 18 * * *' and job['timezone'] == stream['timezone']
    assert job['script'] == jobs.stream_stub_name('work')
    stub = (tmp_path / 'hermes-scripts' / job['script']).read_text()
    assert 'discovery_wake_file' in stub and repr(str(rt.data_dir)) in stub and "'work'" in stub
    assert not {'terminal', 'file', 'code_execution', 'cronjob'} & set(job['enabled_toolsets'])
    assert 'within 30 minutes' in job['prompt'] and 'few minutes later' not in job['prompt']
    # Reader/sender toolsets are filtered the same way.
    config = jobs.discovery_job_config('work', ['gmail-reader', 'terminal', 'file', 'hermes-cli', 'code_execution'])
    assert 'gmail-reader' in config['enabled_toolsets']
    assert not {'terminal', 'file', 'hermes-cli', 'code_execution'} & set(config['enabled_toolsets'])
    # Removing the stream removes its stub.
    discovery.remove_stream(rt, 'work')
    assert not (tmp_path / 'hermes-scripts' / job['script']).exists()


def test_reconcile_migrates_an_old_job_without_rerunning_a_passed_slot(settings, data_dir, tmp_path, home):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    jid = _stream(integration, rt, ctx)
    # An earlier version: the job ran on the user's own cron, no wake check, file and terminal toolsets.
    ctx.cron[jid].update(schedule='0 18 * * *', enabled_toolsets=['alchemy-task', 'file', 'terminal'])
    ctx.cron[jid].pop('script')
    ctx.state.set('discovery_slots', {})
    runtime.bind(ctx)
    try:
        out = json.loads(task_tools.discovery_stream({'action': 'reconcile_jobs'}, session_id='parent'))
    finally:
        runtime.bind(None)
    assert out['ok'] and out['streams']['work']['state'] == 'verified'
    job = ctx.cron[jid]
    assert job['schedule'] == '*/30 * * * *' and job['script'] == jobs.stream_stub_name('work')
    assert 'file' not in job['enabled_toolsets'] and 'terminal' not in job['enabled_toolsets']
    # The latest past 6 PM counts as done, so the first tick after migration does not run it again.
    assert precheck.discovery_wake(lambda k: ctx.state.get(k), 'work') == {'wakeAgent': False}


# ------------------------------------------------------------------ wake check

def _state(**extra):
    data = {'streams': {'work': {'name': 'work', 'job_id': 'job-one', 'schedule': '0 18 * * *', 'timezone': NY}}}
    data.update(extra)
    return data.get


def test_slot_wakes_once_when_the_users_time_arrives():
    assert precheck.discovery_wake(_state(), 'work', _at('2030-03-04T17:50')) == {'wakeAgent': False}
    wake = precheck.discovery_wake(_state(), 'work', _at('2030-03-04T18:00'))
    assert wake['wakeAgent'] and wake['reason'] == 'slot' and wake['slot'] == _at('2030-03-04T18:00').isoformat()
    done = {'discovery_slots': {'work': {'done': wake['slot']}}}
    assert precheck.discovery_wake(_state(**done), 'work', _at('2030-03-04T18:30')) == {'wakeAgent': False}
    assert precheck.discovery_wake(_state(**done), 'work', _at('2030-03-05T18:00'))['reason'] == 'slot'
    # A slot missed for over 12 hours waits for the next one.
    assert precheck.discovery_wake(_state(), 'work', _at('2030-03-05T07:00')) == {'wakeAgent': False}
    # Weekdays: no Saturday slot. Hourly: every hour at :05. Across a DST change the local time holds.
    weekdays = {'streams': {'work': {'job_id': 'j', 'schedule': '0 18 * * 1-5', 'timezone': NY}}}
    assert precheck.discovery_wake(weekdays.get, 'work', _at('2030-03-09T18:10')) == {'wakeAgent': False}
    assert precheck.discovery_wake(weekdays.get, 'work', _at('2030-03-11T18:10'))['reason'] == 'slot'
    hourly = {'streams': {'work': {'job_id': 'j', 'schedule': '5 * * * *', 'timezone': NY}}}
    assert precheck.latest_slot('5 * * * *', NY, _at('2030-03-11T09:30')) == _at('2030-03-11T09:05')
    assert precheck.discovery_wake(hourly.get, 'work', _at('2030-03-11T09:30'))['reason'] == 'slot'
    assert precheck.next_slot('0 18 * * *', NY, _at('2030-03-10T12:00')) == _at('2030-03-10T18:00')
    # No job, or unreadable state: never wakes.
    assert precheck.discovery_wake({'streams': {'work': {'schedule': '0 18 * * *'}}}.get, 'work') == {'wakeAgent': False}
    assert precheck.discovery_wake(lambda k: 1 / 0, 'work') == {'wakeAgent': False}


def test_follow_up_and_run_now_wake_only_while_valid_and_no_run_is_in_progress():
    now = _at('2030-03-04T20:00')
    done = {'discovery_slots': {'work': {'done': _at('2030-03-04T18:00').isoformat()}}}
    pending = {'discovery_follow_ups': {'work': {'pending': {'at': _at('2030-03-04T19:40').isoformat()}}}}
    assert precheck.discovery_wake(_state(**done, **pending), 'work', now)['reason'] == 'follow_up'
    busy = {'discovery_follow_ups': {'work': {**pending['discovery_follow_ups']['work'],
                                              'active': {'run_id': 'r', 'since': _at('2030-03-04T19:50').isoformat()}}}}
    assert precheck.discovery_wake(_state(**done, **busy), 'work', now) == {'wakeAgent': False}
    # A run that never finished stops blocking after six hours.
    assert precheck.discovery_wake(_state(**done, **busy), 'work', _at('2030-03-05T02:00'))['reason'] == 'follow_up'
    request = {'discovery_run_requests': {'work': {'at': _at('2030-03-04T19:58').isoformat()}}}
    assert precheck.discovery_wake(_state(**done, **request), 'work', now)['reason'] == 'run_now'
    assert precheck.discovery_wake(_state(**done, **request), 'work', _at('2030-03-04T21:00')) == {'wakeAgent': False}


def test_stub_runs_under_python_and_reads_state_json_only(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'state.json').write_text(json.dumps({'streams': {'work': {'job_id': 'j', 'schedule': '* * * * *', 'timezone': 'UTC'}}}))
    text = jobs.stream_stub_text('work', plugin_dir=str(jobs._plugin_dir()), data_dir=str(data))
    (tmp_path / 'stub.py').write_text(text)
    before = (data / 'state.json').read_text()
    out = subprocess.run([sys.executable, str(tmp_path / 'stub.py')], capture_output=True, text=True, timeout=60)
    assert json.loads(out.stdout.strip().splitlines()[-1])['wakeAgent'] is True, out.stderr
    assert (data / 'state.json').read_text() == before and sorted(p.name for p in data.iterdir()) == ['state.json']
    missing = jobs.stream_stub_text('work', plugin_dir=str(tmp_path / 'gone'), data_dir=str(data))
    (tmp_path / 'gone.py').write_text(missing)
    out = subprocess.run([sys.executable, str(tmp_path / 'gone.py')], capture_output=True, text=True, timeout=60)
    assert json.loads(out.stdout.strip()) == {'wakeAgent': False}


# ------------------------------------------------------------------ runs record what they consumed

def test_scheduled_start_records_its_slot_and_run_now_records_the_request(settings, data_dir, tmp_path, home):
    from test_discovery_integration import configure
    from test_discovery_any_chat import bound
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    bound(integration, ctx)
    jid = 'job-one'
    ctx.state.set('discovery_slots', {})  # the latest 6 PM has not run
    integration.utcnow = lambda: precheck.latest_slot('0 18 * * *', NY, lookback=8 * 24 * 60) + dt.timedelta(minutes=3)
    ctx.current_cron_execution = lambda: {**FIRE, 'job_id': jid}
    started = integration.start('work', session_id='cron-session')
    assert not started.get('follow_up_run')
    wake = lambda: precheck.discovery_wake(lambda k: ctx.state.get(k), 'work', integration.utcnow())
    assert ctx.state.get('discovery_slots')['work']['done']
    record = ctx.state.get('discovery_follow_ups')['work']
    assert record['active']['run_id'] == started['run_id'] and wake() == {'wakeAgent': False}
    # "Run now" from a chat records a request the wake check lets through; the manual run consumes it.
    ctx.current_cron_execution = lambda: None
    integration.utcnow = lambda: dt.datetime.now(dt.timezone.utc)
    ctx.dispatch_tool, real = (lambda name, args: (_ for _ in ()).throw(AssertionError(args))
                               if args['action'] != 'run' else json.dumps({'success': True})), ctx.dispatch_tool
    jobs.run_stream_now(rt, ctx.state.get('streams')['work'])
    ctx.dispatch_tool = real
    assert wake()['reason'] == 'run_now'
    ctx.current_cron_execution = lambda: {**FIRE, 'job_id': jid, 'source': 'direct', 'scheduled_instant': None,
                                          'started_at': '2030-01-01T00:00:00Z'}
    integration.start('work', session_id='manual-session')
    assert 'work' not in (ctx.state.get('discovery_run_requests') or {})
