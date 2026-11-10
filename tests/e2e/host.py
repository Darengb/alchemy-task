"""Synthetic Hermes host for outcome-level discovery runs.

Only Hermes surfaces are faked here: tool/hook registration and dispatch, the
cron tool, the approved source reader tool and the public subagent lifecycle.
Plugin state, settings and the profile name come from the REAL host facade
(`hermes_cli.plugins.PluginContext`) under a synthetic HERMES_HOME, so the
dashboard routes, which build their own host context, see the same profile.
Every plugin code path (registered tool handlers, hooks, stores, conversion,
Git delivery) is the real code, reached only through the real register(ctx).
"""
from __future__ import annotations

import json
import sys
import threading
import time

PLUGIN_ID = 'alchemy-task'


def load_plugin():
    """The repo conftest already imported the plugin directory as package alchemy_task."""
    return sys.modules['alchemy_task']


class FakeSource:
    """Approved structured reader tool. Pages are deterministic fixture data.

    Each page is a list of items, or the string 'TRUNCATED' (provider returns
    truncated=true) or 'ERROR' (provider failure). `timed` items are returned
    only when their timestamp falls inside the requested [start, end) window.
    """

    def __init__(self, account='acct', scope=('board',)):
        self.account, self.scope = account, list(scope)
        self.pages: list = [[]]
        self.calls: list = []
        self.timed: list = []

    def item(self, object_id, title, *, revision='v1', summary=''):
        return {'title': title, 'summary': summary or title, 'source_revision': revision,
                'source_ids': [f'source:feed:{self.account}:issue:{object_id}']}

    def __call__(self, args):
        self.calls.append(args)
        cursor = args.get('cursor')
        index = int(cursor.split('-')[1]) if cursor else 0
        page = self.pages[index]
        if isinstance(page, list) and self.timed:
            page = [it for at, it in self.timed if args['start'] <= at < args['end']] + page
        base = {'account_key': self.account, 'scope': args['scope'], 'start': args['start'], 'end': args['end']}
        if page == 'ERROR':
            return {'error': 'synthetic provider outage'}
        last = index == len(self.pages) - 1
        out = {**base, 'items': [] if page == 'TRUNCATED' else page,
               'next_cursor': None if last else f'page-{index + 1}', 'pagination_exhausted': last}
        if page == 'TRUNCATED':
            out['truncated'] = True
        return out


class VirtualClock:
    """Real time plus a virtual offset, shared by the fake lifecycle and the plugin runner.

    `sleep` only advances the offset, so a scenario can model children that
    run for minutes while the test itself takes milliseconds.
    """

    def __init__(self):
        self.offset = 0.0
        self._lock = threading.Lock()

    def monotonic(self):
        return time.monotonic() + self.offset

    def time(self):
        return time.time() + self.offset

    def sleep(self, seconds):
        with self._lock:
            self.offset += max(0.0, float(seconds))


def default_tool_deadline():
    """The real Hermes per-call tool deadline for this profile (420 s when nothing is configured)."""
    from agent.tool_executor import _resolve_sequential_tool_timeout
    return _resolve_sequential_tool_timeout()


class FakeLifecycle:
    """Public subagent lifecycle: launch/status/wait/result/reconnect/cancel.

    A launched child is a deterministic function (children.py) that performs
    real registered-tool calls as the child session. With `child_seconds` set,
    a child stays RUNNING for that many (virtual) seconds before it researches
    and finishes, so research outlives any single parent call.
    """

    def __init__(self, host):
        self.host = host
        self.records: dict = {}
        self.launched: list = []
        self.n = 0
        self.child_seconds = 0
        # The real host shows a handle only to the ACTIVE parent session that
        # launched it (agent/subagent_lifecycle.py _record); children keep
        # running and can still call their own tools.
        self.hide_foreign = False
        self._lock = threading.Lock()

    def _visible(self, handle):
        return not self.hide_foreign or handle['parent_session_id'] == self.host.current_parent

    def tick(self):
        """Children progress in the background, whichever parent session is active."""
        for sid in list(self.records):
            self._advance(sid)

    def launch(self, request):
        with self._lock:
            self.n += 1
            n = self.n
        bootstrap = json.loads(request['context'])
        sid, child = f'sa-e2e-{n}', f'child-session-{n}'
        parent = self.host.current_parent
        # Real hosts may fire subagent_start before launch returns.
        self.host.fire_hook('subagent_start', parent_session_id=parent, child_session_id=child,
                            child_subagent_id=sid)
        handle = {'subagent_id': sid, 'parent_session_id': parent, 'created_at': self.host.clock.time()}
        self.records[sid] = {'handle': handle, 'bootstrap': bootstrap, 'child': child, 'phase': 'launched',
                             'terminal': None, 'started': None}
        self.launched.append({'subagent_id': sid, 'candidate_id': bootstrap['candidate_id'],
                              'ordinal': bootstrap['ordinal']})
        return handle

    def _advance(self, sid):
        r = self.records[sid]
        if r['phase'] == 'launched':
            r['phase'], r['started'] = 'running', self.host.clock.time()
            return 'RUNNING'
        if r['phase'] == 'running' and self.host.clock.time() - r['started'] < self.child_seconds:
            return 'RUNNING'
        if r['phase'] == 'running':
            from e2e.children import Child
            terminal = Child(self.host, r['bootstrap']).run(self.host, r['bootstrap'], session=r['child'], task_id=sid)
            r['phase'], r['terminal'] = 'done', terminal
            return terminal
        return r['terminal']

    def status(self, handle):
        sid = handle['subagent_id']
        if not self._visible(handle):
            return {'state': 'UNKNOWN', 'updated_at': self.host.clock.time()}
        state = self._advance(sid)
        r = self.records[sid]
        return {'state': state, 'updated_at': r['started'] or self.host.clock.time()}

    def wait(self, handle, *, timeout_seconds=None):
        r = self.records[handle['subagent_id']]
        if r['phase'] != 'done' and self.child_seconds and timeout_seconds:
            self.host.clock.sleep(timeout_seconds)  # a real wait blocks until change or timeout
        return {'state': r['phase']}

    def result(self, handle):
        r = self.records[handle['subagent_id']]
        return {'ready': r['phase'] == 'done', 'terminal_state': r['terminal'], 'started_at': r['started'],
                'completed_at': self.host.clock.time(), 'summary': 'Child final summary (never a payload).',
                'structured_payload': None}

    def reconnect(self, handle):
        if not self._visible(handle):
            return {'connected': False, 'state': 'UNKNOWN', 'diagnostic': 'RECONNECT_UNAVAILABLE'}
        r = self.records.get(handle['subagent_id'])
        return {'connected': bool(r), 'state': r['terminal'] if r and r['phase'] == 'done' else 'RUNNING'}

    def cancel(self, handle, *, reason):
        return {'accepted': False, 'unsupported': True, 'state': 'CANCEL_REQUESTED'}


class FakeHost:
    """PluginContext stand-in: registration and dispatch are faked, state/config/profile are real."""

    def __init__(self, *, cron_path):
        from hermes_cli.plugins import PluginContext, PluginManifest
        self._real = PluginContext(PluginManifest(name=PLUGIN_ID), manager=None)
        self.state = self._real.state
        self.profile_name = self._real.profile_name
        self.tools: dict = {}
        self.schemas: dict = {}
        self.hooks: dict = {}
        self.skills: dict = {}
        self._cron_path = cron_path
        self.cron: dict = json.loads(cron_path.read_text()) if cron_path.exists() else {}
        self.source = FakeSource()
        self.sent_messages: list = []  # any host-side send would land here; must stay empty
        self.subagent_lifecycle = FakeLifecycle(self)
        self.current_parent = ''
        self.behaviors: dict = {}
        self.research_specs: dict = {}
        self.blocked_calls: list = []
        self.raised: list = []
        # The host enforces its real default per-call tool deadline on every plugin tool.
        self.clock = VirtualClock()
        self.tool_deadline = default_tool_deadline()
        self.call_durations: list = []
        self.deadline_violations: list = []

    # ---- registration surface used by the plugin
    def register_tool(self, name, toolset=None, schema=None, handler=None, description='', emoji='', **_):
        self.tools[name] = handler
        self.schemas[name] = schema

    def register_hook(self, name, fn):
        self.hooks.setdefault(name, []).append(fn)

    def register_skill(self, name, path, description=''):
        self.skills[name] = path

    def register_command(self, *a, **k):
        pass

    def register_system_prompt_section(self, *a, **k):
        pass

    def get_config(self, key, default=None):
        return self._real.get_config(key, default)

    def set_config(self, key, value):
        self._real.set_config(key, value)

    def current_cron_execution(self):
        return None

    # ---- host-provided tools the plugin dispatches
    def dispatch_tool(self, name, args):
        if name == 'cronjob_manage':
            return self._cron(args)
        if name == 'feed_reader':
            return self.source(args)
        raise AssertionError(f'unexpected host tool dispatch {name!r}: {args}')

    def _cron(self, args):
        action = args['action']
        if action == 'create':
            jid = f'job{len(self.cron) + 1}'
            self.cron[jid] = {k: v for k, v in args.items() if k != 'action'}
            out = {'success': True, 'job_id': jid}
        elif action == 'list':
            out = {'jobs': [{**v, 'job_id': k} for k, v in self.cron.items()]}
        elif action == 'update':
            self.cron[args['job_id']].update({k: v for k, v in args.items() if k not in ('action', 'job_id')})
            out = {'success': True, 'job_id': args['job_id']}
        elif action == 'remove':
            self.cron.pop(args['job_id'], None)
            out = {'success': True}
        elif action in ('resume', 'pause', 'run'):
            out = {'success': True, 'job_id': args.get('job_id')}
        else:
            raise AssertionError(args)
        self._cron_path.write_text(json.dumps(self.cron))
        return json.dumps(out)

    # ---- host behaviors
    def fire_hook(self, name, **kwargs):
        return [fn(**kwargs) for fn in self.hooks.get(name, [])]

    def call(self, name, args, *, session, task_id=''):
        """Invoke a registered tool the way the host does: pre_tool_call hooks, then the handler."""
        for verdict in self.fire_hook('pre_tool_call', tool_name=name, args=args, session_id=session, task_id=task_id):
            if isinstance(verdict, dict) and verdict.get('action') == 'block':
                self.blocked_calls.append((name, session, verdict.get('message')))
                return {'ok': False, 'blocked': True, 'error': verdict.get('message')}
        started = self.clock.monotonic()
        try:
            raw = self.tools[name](json.loads(json.dumps(args)), session_id=session, task_id=task_id)
        except Exception as exc:  # noqa: BLE001
            # Hermes registry dispatch turns any handler exception into {"error": ...}.
            self.raised.append((name, type(exc).__name__, str(exc)[:300]))
            raw = json.dumps({'error': f'{type(exc).__name__}: {exc}'[:1000]})
        elapsed = self.clock.monotonic() - started
        self.call_durations.append((name, elapsed))
        if self.tool_deadline and elapsed > self.tool_deadline:
            # The real host abandons the call and returns a timeout to the model.
            self.deadline_violations.append((name, elapsed))
            return {'ok': False, 'error': f'tool {name} timed out after {self.tool_deadline:.0f}s'}
        return json.loads(raw)


def plugin_settings(workspace, *, timezone='America/New_York', areas=('work',)):
    # A default install: no timeout configuration or transport receipt of any kind.
    return {'workspace_root': str(workspace), 'timezone': timezone, 'areas': list(areas),
            'git_transport': 'system', 'git_run_hooks': True}


def build_host(*, cron_path):
    """Create a host and run the plugin's REAL register(ctx)."""
    host = FakeHost(cron_path=cron_path)
    load_plugin().register(host)
    return host
