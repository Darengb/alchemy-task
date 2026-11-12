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
        "toolsets": ["alchemy-task-sweep", "alchemy-task-research", "web", "file", "session_search"],
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


def job_toolsets(job: str, state: Any = None) -> list[str]:
    """Toolsets an agent job enables. The research sweep is the research workers' parent, so it also
    enables every approved discovery reader (MCP ones included) for the workers to inherit."""
    base = list(JOBS[job].get("toolsets") or [])
    if job != "research-sweep":
        return base
    return list(dict.fromkeys(base + approved_reader_toolsets(state, include_mcp=True)))


def sweep_toolsets(state: Any = None) -> list[str]:
    return job_toolsets("research-sweep", state)


def spec_hash(job: str, state: Any = None) -> str:
    spec = {k: v for k, v in JOBS[job].items() if k in ("schedule", "mode", "toolsets", "deliver", "prompt", "stub")}
    if spec.get("toolsets"):
        spec["toolsets"] = job_toolsets(job, state)
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def job_name(job: str) -> str:
    return f"{PREFIX}: {JOBS[job]['title']}"


def create_args(job: str, *, timezone: str, state: Any = None) -> dict[str, Any]:
    spec = JOBS[job]
    args: dict[str, Any] = {"action": "create", "name": job_name(job), "schedule": spec["schedule"],
                            "script": spec["stub"], "deliver": spec["deliver"]}
    if timezone:
        args["timezone"] = timezone
    if spec["mode"] == "script":
        args["no_agent"] = True
    else:
        args["prompt"] = spec["prompt"]
        args["enabled_toolsets"] = job_toolsets(job, state)
    return args


def inventory(timezone: str) -> list[dict[str, str]]:
    return [{"key": key, "name": spec["title"], "when": f"{spec['when']} ({timezone or 'UTC'})",
             "kind": "script, no model" if spec["mode"] == "script" else "agent behind a free check",
             "why": spec["why"], "cost": spec["cost"], "writes": f"scripts/{spec['stub']}"}
            for key, spec in JOBS.items()]


def approved_reader_toolsets(state: Any, *, include_mcp: bool = False) -> list[str]:
    """Union of reader toolsets recorded for approved discovery streams, read from plugin state.

    Sources of each stream, plus approved source configs that match one of its sources. Delivery
    bindings are left out (they carry senders, not readers). MCP toolsets are left out unless
    include_mcp: workers inherit the parent's MCP servers from Hermes. Never raises.
    """
    out: list[str] = []
    try:
        streams = state.get("streams", default={}) or {}
        configs = state.get("discovery_sources", default={}) or {}
        for name, stream in streams.items():
            sources = [s for s in (stream.get("sources") or []) if isinstance(s, dict)]
            names = [t for s in sources for t in (s.get("toolsets") or [])]
            for config in (configs.get(name) or {}).values():
                if not isinstance(config, dict) or config.get("approved") is False:
                    continue
                if any(s.get("name") == config.get("name") and s.get("scope") == config.get("scope") for s in sources):
                    names += list(config.get("toolsets") or [])
            out += [t for t in names if isinstance(t, str) and t and (include_mcp or not t.startswith("mcp-"))]
    except Exception:  # noqa: BLE001 - missing or odd state means no extra readers
        return list(dict.fromkeys(out))
    return list(dict.fromkeys(out))


def discovery_job_config(stream: str, reader_toolsets: list[str] | None = None, *, delivery_owner='native_origin', deliver='origin') -> dict[str, Any]:
    """One supported source-first scheduled workflow, no separate executor."""
    return {
        'deliver': 'local' if delivery_owner == 'verified_sender' else deliver,
        'enabled_toolsets': list(dict.fromkeys(['alchemy-task', 'alchemy-task-discovery', 'alchemy-task-discovery-child',
                                              'skills', 'web', 'file', 'session_search', *(reader_toolsets or [])])),
        'prompt': (f'Run the Alchemy Task discovery stream "{stream}". Load alchemy-task:discovery. '
                   'Call discovery_start and resume its SAME saved run/window before scanning anything new. '
                   'Collect every approved source with discovery_collect, putting full message text and full email bodies into the envelope, never paths; '
                   'first give every item a disposition (research, or exclude with a short reason) and merge chat fragments into one conversation, as the skill collect step says; freeze complete source/task/skill context with discovery_context. '
                   'Research runs as short calls: call discovery_research_run with the SAME run_id, fetch every page of each awaiting_parent '
                   'payload and perform substantive parent semantic acceptance/repair, and call discovery_research_run again until it returns '
                   'status complete. If it refuses with explicit recovery required (a new session id), call discovery_recover with adopt=true '
                   'and continue the same run. Reconcile all cohorts, then discovery_join. Only after global join perform serial discovery_match/discovery_decision. '
                   'Prepare discovery_digest. No freeform discovery_submit candidates, no task creation before approval, '
                   'no generic post-creation research replacing accepted dossiers. ' + (
                   'Call discovery_digest action=send with the approved '
                   'origin sender/readback binding. Scheduler delivery is local-only. Return [SILENT], never repeat the digest in the '
                   'final reply, including unknown outcomes. Missing sender approval stays prepared and needs setup; no alternate '
                   'scheduler send is allowed. ' if delivery_owner == 'verified_sender' else
                   'Return the exact immutable prepared digest text as the final reply for native host delivery, with no paraphrase, '
                   'prefix or extra post. discovery_digest action=send returns final_text metadata only; never use an alternate sender. '
                   'Preparation/final return is not proof of delivery; native host retry semantics apply, not universal exactly-once. '
                   ) + 'Fail open: every run ends with a readable digest; imperfect information beats none. '
                   'Per item, research from the saved source even if incomplete and note the gap; when accepting, you may add newer context '
                   'you read with the user\'s own tools, noted as such; if an item cannot be researched, reject it as not retryable so it '
                   'goes under Needs attention. A problem with one item, source or tool never stops the run: never retry the same failing '
                   'call more than twice, skip that item and continue. A match or decision failure for one item is recorded and the run continues. '
                   'Time box research to about 45 minutes, then call discovery_research_run with finish_now=true, join and prepare the digest; '
                   'deferred items are researched first next run. When research is left queued, a follow-up run '
                   'of this stream starts on its own a few minutes later; never start or schedule one yourself. Stop early only when nothing at all can proceed. Never create another run; '
                   'the next run continues the same saved run. ' + (
                   '' if delivery_owner == 'verified_sender' else
                   'Do not leave a failed file edit: write any helper script to a new unique filename. '
                   'If preparing the digest is refused or fails, the final reply is a partial digest you write in the same layout, marked '
                   'Partial digest: heading, one section per accepted finding with current state and next action, a Needs attention list '
                   'of each skipped item and why, then the run_id. Never end with only a status report.'))}


def _preview(text):
    """Hermes's cron list shows only a prompt preview: the first 100 characters plus '...' when longer."""
    text = str(text or '')
    return text[:100] + '...' if len(text) > 100 else text


def job_readback_problems(observed, desired, *, schedule=None, timezone=None):
    """Compare a job read back through ``cronjob_manage list`` with what we asked for, using only fields Hermes
    returns there. The list shows ``prompt_preview`` (not the full prompt), ``schedule`` as its display string
    and ``enabled_toolsets`` only when set; it omits ``timezone``. A field Hermes does return must match; a
    field it never returns is not treated as a mismatch (the create/update call itself carried it)."""
    problems = []
    if observed.get('deliver') != desired.get('deliver'):
        problems.append('deliver')
    if 'prompt' in observed:
        if observed.get('prompt') != desired.get('prompt'):
            problems.append('prompt')
    elif observed.get('prompt_preview') != _preview(desired.get('prompt')):
        problems.append('prompt')
    want_ts = list(desired.get('enabled_toolsets') or [])
    if want_ts and list(observed.get('enabled_toolsets') or []) != want_ts:
        problems.append('enabled_toolsets')
    if schedule is not None and observed.get('schedule') != schedule:
        problems.append('schedule')
    if timezone is not None and 'timezone' in observed and observed.get('timezone') != timezone:
        problems.append('timezone')
    return problems


def read_discovery_job(rt, stream):
    """Read only the exact bound job via the public cron tool, never cron files."""
    raw = rt.ctx.dispatch_tool('cronjob_manage', {'action': 'list', 'include_disabled': True})
    data = json.loads(raw) if isinstance(raw, str) else raw
    matches = [j for j in data.get('jobs', []) if j.get('job_id') == stream['job_id']]
    if len(matches) != 1 or matches[0].get('name') != f"{PREFIX}: discovery {stream['name']}":
        raise ValueError('bound discovery job identity readback failed')
    return matches[0]


def stream_job_config(rt, stream):
    """The prompt, toolsets and deliver of a stream's own job, from its approved sources and delivery binding."""
    configs = (rt.ctx.state.get('discovery_sources', default={}) or {}).get(stream['name'], {})
    readers = [t for s in stream['sources'] for t in s.get('toolsets', [])]
    readers += [t for c in configs.values() if any(s['name'] == c.get('name') and s['scope'] == c.get('scope') for s in stream['sources']) for t in c.get('toolsets', [])]
    binding = (rt.ctx.state.get('discovery_delivery', default={}) or {}).get(stream['name'], {})
    return discovery_job_config(stream['name'], readers + binding.get('toolsets', []),
                                delivery_owner=stream.get('delivery_owner', 'native_origin'), deliver=stream.get('deliver', 'origin'))


def follow_up_job_name(stream_name):
    return f"{PREFIX}: discovery {stream_name} follow-up"


def follow_up_create_args(rt, stream, *, schedule='in 5m'):
    """A one-shot job that runs the same stream once, a few minutes after the current run ends. It is a
    separate job, so it never collides with the stream's own job still finishing its reply."""
    return {'action': 'create', 'name': follow_up_job_name(stream['name']), 'schedule': schedule, 'repeat': 1,
            'attach_to_session': True, 'skills': ['alchemy-task:discovery'], **stream_job_config(rt, stream)}


def reconcile_discovery_job(rt, stream):
    if not stream.get('job_id'): return {'state': 'not_configured'}
    read_discovery_job(rt, stream)
    desired = stream_job_config(rt, stream)
    raw = rt.ctx.dispatch_tool('cronjob_manage', {'action': 'update', 'job_id': stream['job_id'], **desired})
    result = json.loads(raw) if isinstance(raw, str) else raw
    if result.get('error') or result.get('success') is False:
        raise ValueError('discovery job reconciliation failed: ' + str(result))
    observed = read_discovery_job(rt, stream)
    if job_readback_problems(observed, desired):
        raise ValueError('discovery reader toolsets readback mismatch: ' + ', '.join(job_readback_problems(observed, desired)))
    reverify_sweep(rt)
    return {'state': 'verified', 'job_id': stream['job_id'], 'enabled_toolsets': observed.get('enabled_toolsets') or desired['enabled_toolsets']}


def reverify_sweep(rt) -> dict[str, Any]:
    """Best effort: bring the research sweep job's toolsets in line after discovery streams change."""
    try:
        from .setup_flow import reconcile_sweep_job
        return reconcile_sweep_job(rt)
    except Exception as exc:  # noqa: BLE001 - setup status reports the job as needing an update
        return {'state': 'error', 'error': str(exc)[:200]}


def activate_discovery_job(rt, stream, binding=None):
    """Approved native scheduling or verified sender setup; public cron only."""
    from .discovery import _streams, _save_streams
    binding = binding or {}
    configs = (rt.ctx.state.get('discovery_sources', default={}) or {}).get(stream['name'], {})
    toolsets = [t for s in stream['sources'] for t in s.get('toolsets', [])]
    toolsets += [t for c in configs.values() for t in c.get('toolsets', [])]
    toolsets += binding.get('toolsets', [])
    owner = stream.get('delivery_owner', 'native_origin')
    desired = discovery_job_config(stream['name'], toolsets, delivery_owner=owner, deliver=stream.get('deliver', 'origin'))
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
    problems = job_readback_problems(observed, desired, schedule=stream['schedule'], timezone=stream['timezone'])
    if problems:
        raise ValueError('delivery-ready job readback mismatch (' + ', '.join(problems) + '); activation incomplete')
    if observed.get('paused') is True or observed.get('enabled') is False or observed.get('state') == 'paused':
        rt.ctx.dispatch_tool('cronjob_manage', {'action': 'resume', 'job_id': stream['job_id']})
        observed = read_discovery_job(rt, stream)
        if observed.get('paused') is True or observed.get('enabled') is False or observed.get('state') == 'paused':
            raise ValueError('job resume readback failed')
    stream.update(activation_state='ACTIVE', delivery_state='verified' if owner == 'verified_sender' else 'host_pending', setup_blocked_reason='',
                  job_binding={'job_id': stream['job_id'], 'origin_session': stream['origin_session'],
                               'profile': rt.ctx.profile_name, 'verified': True})
    streams = _streams(rt); streams[stream['name']] = stream; _save_streams(rt, streams)
    reverify_sweep(rt)
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
