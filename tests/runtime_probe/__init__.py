"""Synthetic public lifecycle probe. No task/source-system writes."""
import dataclasses
import json
import threading
import time
import uuid

_lock = threading.Lock()

def wire(value):
    if dataclasses.is_dataclass(value):
        return wire(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire(v) for v in value]
    if hasattr(value, 'value'):
        return value.value
    return value

def register(ctx):
    def read(args, **kwargs):
        key = 'probe:' + args['run_id']
        with _lock:
            data = ctx.state.get(key, default={}) or {}
            item = data.setdefault(str(args['index']), {})
            pages = item.setdefault('pages', [])
            if args['page'] not in pages:
                pages.append(args['page'])
            ctx.state.set(key, data)
        page = args['page']
        return json.dumps({'page': page, 'has_more': page == 1,
            'content': 'An older draft requested ordering a banner.' if page == 1 else
                       'Latest update: banner order cancelled. Prepare a print proof instead.',
            'decision': 'prepare_print_proof' if page == 2 else 'old_request'})
    def submit(args, **kwargs):
        key = 'probe:' + args['run_id']
        with _lock:
            data = ctx.state.get(key, default={}) or {}
            item = data.setdefault(str(args['index']), {})
            ok = sorted(item.get('pages', [])) == [1, 2] and args['decision'] == 'prepare_print_proof'
            item['accepted'] = ok
            item['decision'] = args['decision']
            ctx.state.set(key, data)
        return json.dumps({'ok': ok, 'message': 'Synthetic research callback accepted.' if ok else 'Read both pages first.'})
    def start(args, **kwargs):
        run_id = uuid.uuid4().hex[:12]
        handles, launch_errors = [], []
        for index in range(2):
            goal = ('Synthetic read-only probe. Call discovery_probe_read for page1, then page2, '
                    'with run_id=' + run_id + ' and index=' + str(index) + '. Then call discovery_probe_submit '
                    'with that run_id/index and decision from the latest page. Do not use any other tools or '
                    'write any files/tasks/settings. Finish with one short sentence.')
            try:
                h = ctx.subagent_lifecycle.launch({'goal': goal,
                    'context': 'Read both pages before submitting. Page1 is deliberately stale.',
                    'role': 'leaf', 'allowed_toolsets': ['alchemy-discovery-probe'],
                    'correlation_id': 'probe:' + run_id + ':' + str(index)})
                handles.append(wire(h))
            except Exception as exc:
                launch_errors.append(type(exc).__name__ + ': ' + str(exc))
        results = []
        for h in handles:
            try:
                waiting = ctx.subagent_lifecycle.wait(h, timeout_seconds=120)
                status = ctx.subagent_lifecycle.status(h)
                result = ctx.subagent_lifecycle.result(h)
                results.append({'wait': wire(waiting), 'status': wire(status),
                    'result': wire(result)})
            except Exception as exc:
                results.append({'error': type(exc).__name__ + ': ' + str(exc)})
        saved = ctx.state.get('probe:' + run_id, default={}) or {}
        return json.dumps({'run_id': run_id, 'launch_errors': launch_errors,
            'handle_count': len(handles), 'results': results, 'saved': saved}, default=str)
    schemas = [
        ('discovery_runtime_probe', start, {'type': 'object', 'properties': {}},
         'Run two synthetic source-aware lifecycle children and observe their persisted submissions.'),
        ('discovery_probe_read', read, {'type': 'object', 'properties': {
            'run_id': {'type': 'string'}, 'index': {'type': 'integer'},
            'page': {'type': 'integer', 'enum': [1, 2]}}, 'required': ['run_id', 'index', 'page']},
         'Read one page of this synthetic probe source.'),
        ('discovery_probe_submit', submit, {'type': 'object', 'properties': {
            'run_id': {'type': 'string'}, 'index': {'type': 'integer'},
            'decision': {'type': 'string'}}, 'required': ['run_id', 'index', 'decision']},
         'Persist a synthetic research decision after reading both pages.')]
    for name, handler, parameters, description in schemas:
        ctx.register_tool(name=name, toolset='alchemy-discovery-probe', handler=handler,
            schema={'name': name, 'description': description, 'parameters': parameters},
            description=description)
