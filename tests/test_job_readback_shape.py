"""Readback against the job shape Hermes's ``cronjob_manage list`` really returns (prompt_preview, display
schedule, no timezone), so discovery activation does not fail on fields Hermes never sends."""
from __future__ import annotations

import pytest

from alchemy_task import jobs

DESIRED = jobs.discovery_job_config('work', ['slack-reader'])
SCHEDULE, TZ = '0 18 * * 1-5', 'America/New_York'


def hermes_list_shape(prompt=None, deliver=None, toolsets=None, schedule=SCHEDULE):
    """What tools/cronjob_job_args._format_job returns: no prompt, no timezone."""
    prompt = DESIRED['prompt'] if prompt is None else prompt
    return {'job_id': 'abc', 'name': 'alchemy-task: discovery work',
            'prompt_preview': prompt[:100] + '...' if len(prompt) > 100 else prompt,
            'schedule': schedule, 'deliver': deliver or DESIRED['deliver'], 'enabled': True, 'state': 'scheduled',
            'enabled_toolsets': list(DESIRED['enabled_toolsets'] if toolsets is None else toolsets)}


def test_real_list_shape_of_a_correct_job_has_no_problems():
    assert len(DESIRED['prompt']) > 100  # the case that failed live: prompt only visible as a preview
    assert jobs.job_readback_problems(hermes_list_shape(), DESIRED, schedule=SCHEDULE, timezone=TZ) == []


@pytest.mark.parametrize('kwargs,field', [
    ({'prompt': 'Run something else entirely, which is a different job prompt from the one we created for discovery work.'}, 'prompt'),
    ({'deliver': 'local'}, 'deliver'),
    ({'toolsets': ['web']}, 'enabled_toolsets'),
    ({'schedule': '0 9 * * *'}, 'schedule'),
])
def test_fields_hermes_returns_must_still_match(kwargs, field):
    assert field in jobs.job_readback_problems(hermes_list_shape(**kwargs), DESIRED, schedule=SCHEDULE, timezone=TZ)


def test_a_returned_timezone_must_match_and_a_full_prompt_is_compared_exactly():
    shape = {**hermes_list_shape(), 'timezone': 'Europe/London'}
    assert 'timezone' in jobs.job_readback_problems(shape, DESIRED, schedule=SCHEDULE, timezone=TZ)
    shape = {**hermes_list_shape(), 'prompt': DESIRED['prompt'] + ' extra'}
    assert 'prompt' in jobs.job_readback_problems(shape, DESIRED)


def test_missing_toolsets_are_a_problem_when_we_asked_for_some():
    shape = hermes_list_shape()
    shape.pop('enabled_toolsets')
    assert 'enabled_toolsets' in jobs.job_readback_problems(shape, DESIRED)


def test_matches_hermes_format_job_when_available():
    fmt = pytest.importorskip('tools.cronjob_job_args')._format_job
    raw = {'id': 'abc', 'name': 'alchemy-task: discovery work', 'prompt': DESIRED['prompt'],
           'schedule': {'kind': 'cron', 'expr': SCHEDULE, 'display': SCHEDULE}, 'schedule_display': SCHEDULE,
           'timezone': TZ, 'deliver': DESIRED['deliver'], 'enabled': True, 'enabled_toolsets': DESIRED['enabled_toolsets'],
           'repeat': {'times': None, 'completed': 0}}
    try:
        observed = fmt(raw)
    except Exception as exc:  # noqa: BLE001 - host internals vary; the synthetic shape above is the contract
        pytest.skip(f'host _format_job not callable here: {exc}')
    assert jobs.job_readback_problems(observed, DESIRED, schedule=SCHEDULE, timezone=TZ) == []
