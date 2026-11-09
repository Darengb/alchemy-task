"""Scheduled jobs Alchemy Task creates after the user approves them during setup.

Each job is created with ``ctx.dispatch_tool("cronjob_manage", ...)``. Its stub
is copied into ``$HERMES_HOME/scripts/`` (cron only runs scripts from there).
Stubs are thin: they load the installed plugin and call ``core.precheck``, so
plugin updates change behaviour without touching the copied files. A stub stays
silent (and wakes no model) when there is nothing to do or the plugin is gone.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PREFIX = "alchemy-task"

_LOADER = """\
# Alchemy Task: {name} (copied by Alchemy Task setup; removed by /task teardown).
import json, sys
from pathlib import Path
plugin = Path({plugin!r})
if not (plugin / "core" / "precheck.py").exists():
    {missing}
    sys.exit(0)
import importlib.util
spec = importlib.util.spec_from_file_location("alchemy_task", plugin / "__init__.py",
                                              submodule_search_locations=[str(plugin)])
mod = importlib.util.module_from_spec(spec); sys.modules["alchemy_task"] = mod
from alchemy_task.core import precheck  # noqa: E402  (core has no plugin-context imports)
"""

JOBS: dict[str, dict[str, Any]] = {
    "research-sweep": {
        "title": "Research sweep",
        "schedule": "*/30 * * * *",
        "when": "every 30 minutes",
        "mode": "agent",
        "stub": "alchemy_task_research_sweep.py",
        "body": "print(json.dumps(precheck.research_wake(data_dir={data_dir!r})))",
        "missing": 'print(json.dumps({{"wakeAgent": False}}))',
        "toolsets": ["alchemy-task-sweep", "alchemy-task-research", "web"],
        "deliver": "local",
        "prompt": ("Alchemy Task research sweep. Call task_research_sweep to research tasks that are waiting or whose "
                   "research stalled. Reply with one short line saying how many were started and finished. Do "
                   "nothing else."),
        "why": "Researches tasks whose research could not start or stopped early (for example after a restart).",
        "cost": "Free when nothing is waiting (a script checks first); otherwise one short turn plus the research.",
    },
    "maintenance": {
        "title": "Task file check and push retry",
        "schedule": "15 * * * *",
        "when": "every hour",
        "mode": "script",
        "stub": "alchemy_task_maintenance.py",
        "body": "text = precheck.maintenance({data_dir!r})\nif text:\n    print(text)",
        "missing": "pass",
        "deliver": "origin",
        "why": ("Gives hand-made tasks their permanent ID and pushes task commits that could not be pushed earlier. "
                "Messages this chat only when something changes or a new problem appears."),
        "cost": "Free: a script, no model.",
    },
}


def stub_text(job: str, *, plugin_dir: str, data_dir: str) -> str:
    spec = JOBS[job]
    head = _LOADER.format(name=spec["title"], plugin=str(plugin_dir), missing=spec["missing"].format())
    return head + spec["body"].format(data_dir=str(data_dir)) + "\n"


def spec_hash(job: str) -> str:
    spec = {k: v for k, v in JOBS[job].items() if k in ("schedule", "mode", "toolsets", "deliver", "prompt", "stub")}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def job_name(job: str) -> str:
    return f"{PREFIX}: {JOBS[job]['title']}"


def create_args(job: str, *, timezone: str) -> dict[str, Any]:
    spec = JOBS[job]
    args: dict[str, Any] = {"action": "create", "name": job_name(job), "schedule": spec["schedule"],
                            "script": spec["stub"], "deliver": spec["deliver"]}
    if timezone:
        args["timezone"] = timezone
    if spec["mode"] == "script":
        args["no_agent"] = True
    else:
        args["prompt"] = spec["prompt"]
        args["enabled_toolsets"] = spec["toolsets"]
    return args


def inventory(timezone: str) -> list[dict[str, str]]:
    return [{"key": key, "name": spec["title"], "when": f"{spec['when']} ({timezone or 'UTC'})",
             "kind": "script, no model" if spec["mode"] == "script" else "agent behind a free check",
             "why": spec["why"], "cost": spec["cost"], "writes": f"scripts/{spec['stub']}"}
            for key, spec in JOBS.items()]


def discovery_job_config(stream: str, reader_toolsets: list[str] | None = None) -> dict[str, Any]:
    """One supported source-first scheduled workflow, no separate executor."""
    return {
        'deliver': 'local',  # verified plugin sender is the single delivery owner
        'enabled_toolsets': list(dict.fromkeys(['alchemy-task', 'alchemy-task-discovery', 'alchemy-task-discovery-child',
                                              'skills', 'web', 'file', 'session_search', *(reader_toolsets or [])])),
        'prompt': (f'Run the Alchemy Task discovery stream "{stream}". Load alchemy-task:discovery. '
                   'Call discovery_start and resume its SAME saved run/window before scanning anything new. '
                   'Collect every approved source with discovery_collect; freeze complete source/task/skill context with discovery_context. '
                   'Use discovery_research_run, fetch every full callback, perform substantive parent semantic acceptance/repair, '
                   'reconcile all cohorts, then discovery_join. Only after global join perform serial discovery_match/discovery_decision. '
                   'Prepare discovery_digest. No freeform discovery_submit candidates, no task creation before approval, '
                   'no generic post-creation research replacing accepted dossiers. Call discovery_digest action=send with the approved '
                   'origin sender/readback binding. Scheduler delivery is local-only. Return [SILENT], never repeat the digest in the '
                   'final reply, including unknown outcomes. Missing sender approval stays prepared and needs setup; no alternate '
                   'scheduler send is allowed. If blocked, preserve the exact saved run rather than creating another run.')}


def read_discovery_job(rt, stream):
    """Read only the exact bound job via the public cron tool, never cron files."""
    raw = rt.ctx.dispatch_tool('cronjob_manage', {'action': 'list', 'include_disabled': True})
    data = json.loads(raw) if isinstance(raw, str) else raw
    matches = [j for j in data.get('jobs', []) if j.get('job_id') == stream['job_id']]
    if len(matches) != 1 or matches[0].get('name') != f"{PREFIX}: discovery {stream['name']}":
        raise ValueError('bound discovery job identity readback failed')
    return matches[0]


def reconcile_discovery_job(rt, stream):
    if not stream.get('job_id'): return {'state': 'not_configured'}
    read_discovery_job(rt, stream)
    configs = (rt.ctx.state.get('discovery_sources', default={}) or {}).get(stream['name'], {})
    readers = [t for s in stream['sources'] for t in s.get('toolsets', [])]
    readers += [t for c in configs.values() if any(s['name'] == c.get('name') and s['scope'] == c.get('scope') for s in stream['sources']) for t in c.get('toolsets', [])]
    binding = (rt.ctx.state.get('discovery_delivery', default={}) or {}).get(stream['name'], {})
    desired = discovery_job_config(stream['name'], readers + binding.get('toolsets', []))
    raw = rt.ctx.dispatch_tool('cronjob_manage', {'action': 'update', 'job_id': stream['job_id'], **desired})
    result = json.loads(raw) if isinstance(raw, str) else raw
    if result.get('error') or result.get('success') is False:
        raise ValueError('discovery job reconciliation failed: ' + str(result))
    observed = read_discovery_job(rt, stream)
    if observed.get('enabled_toolsets') != desired['enabled_toolsets']:
        raise ValueError('discovery reader toolsets readback mismatch')
    return {'state': 'verified', 'job_id': stream['job_id'], 'enabled_toolsets': observed['enabled_toolsets']}


def activate_discovery_job(rt, stream, binding):
    """Called only after approved binding readback; public cron only."""
    from .discovery import _streams, _save_streams
    configs = (rt.ctx.state.get('discovery_sources', default={}) or {}).get(stream['name'], {})
    toolsets = [t for s in stream['sources'] for t in s.get('toolsets', [])]
    toolsets += [t for c in configs.values() for t in c.get('toolsets', [])]
    toolsets += binding.get('toolsets', [])
    desired = discovery_job_config(stream['name'], toolsets)
    if not stream.get('job_id'):
        args = {'action': 'create', 'name': f"{PREFIX}: discovery {stream['name']}",
                'schedule': stream['schedule'], 'timezone': stream['timezone'],
                'attach_to_session': True, 'skills': ['alchemy-task:discovery'], **desired}
        raw = rt.ctx.dispatch_tool('cronjob_manage', args)
        jid = parse_job_id(raw)
        if not jid: raise ValueError('could not create delivery-ready discovery job')
        stream = {**stream, 'job_id': jid, 'activation_state': 'ACTIVATING'}
        streams = _streams(rt); streams[stream['name']] = stream; _save_streams(rt, streams)
    else:
        read_discovery_job(rt, stream)
        rt.ctx.dispatch_tool('cronjob_manage', {'action': 'update', 'job_id': stream['job_id'], **desired})
    observed = read_discovery_job(rt, stream)
    if observed.get('deliver') != 'local' or observed.get('enabled_toolsets') != desired['enabled_toolsets']:
        raise ValueError('delivery-ready job readback mismatch; activation incomplete')
    if observed.get('paused') is True or observed.get('enabled') is False or observed.get('state') == 'paused':
        rt.ctx.dispatch_tool('cronjob_manage', {'action': 'resume', 'job_id': stream['job_id']})
        observed = read_discovery_job(rt, stream)
        if observed.get('paused') is True or observed.get('enabled') is False or observed.get('state') == 'paused':
            raise ValueError('job resume readback failed')
    stream.update(activation_state='ACTIVE', delivery_state='verified', setup_blocked_reason='',
                  job_binding={'job_id': stream['job_id'], 'origin_session': stream['origin_session'],
                               'profile': rt.ctx.profile_name, 'verified': True})
    streams = _streams(rt); streams[stream['name']] = stream; _save_streams(rt, streams)
    return stream


def parse_job_id(result: Any) -> str:
    try:
        data = json.loads(result) if isinstance(result, str) else dict(result or {})
    except (TypeError, ValueError):
        return ""
    for path in (("job_id",), ("id",), ("job", "id"), ("job", "job_id")):
        cur: Any = data
        for key in path:
            cur = cur.get(key) if isinstance(cur, dict) else None
        if isinstance(cur, str) and cur:
            return cur
    return ""


def write_stub(scripts_dir: Path, job: str, *, plugin_dir: str, data_dir: str) -> Path:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    path = scripts_dir / JOBS[job]["stub"]
    path.write_text(stub_text(job, plugin_dir=plugin_dir, data_dir=data_dir))
    return path
