"""Temporary synthetic canary integrating the pinned production runner unchanged."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from .discovery_runner import DiscoveryRunner, RunnerPolicy, make_tool_handlers, make_hooks
from .core.discovery_state import DiscoveryStore


def register(ctx):
    root = Path(ctx.state.data_dir)
    store = DiscoveryStore(root / 'runner-probe')
    runner = DiscoveryRunner(ctx, SimpleNamespace(data_dir=root), store=store,
        policy=RunnerPolicy(admission_seconds=400, pending_seconds=90, running_seconds=600, transport_seconds=2040),
        transport_receipt={'sequential_call': 2040, 'concurrent_batch': 2040,
                           'long_canary': 'separate registered duration receipts'})
    handlers = make_tool_handlers(runner)
    def audit(kind, data):
        ctx.state.set('latest-' + kind, data)
    for name, hook in make_hooks(runner).items():
        def wrapped(_hook=hook, _name=name, **kw):
            if _name == 'subagent_start': audit('start', kw)
            result = _hook(**kw)
            if result and _name == 'pre_tool_call': audit('guard', {'kwargs': kw, 'result': result})
            return result
        ctx.register_hook(name, wrapped)
    def register_tool(name, handler, properties, required, description, toolset='alchemy-discovery-runner-probe'):
        ctx.register_tool(name=name, toolset=toolset, handler=handler, description=description,
            schema={'name': name, 'description': description, 'parameters': {'type': 'object', 'properties': properties, 'required': required}})
    types = {'run_id': 'string', 'expected_revision': 'string', 'resource': 'string', 'revision': 'string', 'token': 'string', 'binding': 'object', 'cursor': 'string', 'limit': 'integer', 'payload': 'object', 'upload': 'object', 'payload_sha256': 'string', 'assessment': 'object', 'cid': 'string', 'anchors': 'array', 'record': 'object', 'degraded': 'object', 'owner_restarted': 'boolean', 'adopt': 'boolean', 'reason': 'string'}
    methods = {'discovery_research_run': runner.run, 'discovery_research_fetch': runner.fetch, 'discovery_research_submit': runner.submit, 'discovery_research_accept': runner.accept, 'discovery_actions': runner.actions, 'discovery_reconcile': runner.reconcile, 'discovery_join': runner.join, 'discovery_recover': runner.recover, 'discovery_release_hold': runner.release_hold}
    for name, method in methods.items():
        params = {k: v for k, v in inspect.signature(method).parameters.items() if k not in {'session_id', 'task_id'}}
        properties = {k: {'type': types[k]} for k in params}
        required = [k for k, v in params.items() if v.default is inspect.Parameter.empty]
        register_tool(name, handlers[name], properties, required, 'Synthetic probe: actual pinned runner ' + name)
    def start(args, session_id='', task_id='', **kw):
        if not session_id: return json.dumps({'error': 'Actual host session_id unavailable', 'kw_keys': sorted(kw)})
        run = store.init_run(origin={'session_id': session_id}, config={'probe_mode': args.get('mode', 'functional')})
        count = args.get('count', 4)
        store.add_candidates(run, [{'title': 'Synthetic print proof ' + str(i), 'source_ids': ['source:synthetic:sample:thread:item' + str(i)]} for i in range(count)])
        store.freeze_index(run, rubric='Read full primary with runner_probe_source pages 1 and 2. Page 1 is stale; page 2 reverses it. Read every frozen resource. Schema example is available with runner_probe_example. Submit complete schema, not terminal prose. No live sources or writes. Demonstrate read-only guard by calling discovery_join with this run_id as a child; it must block or refuse child authority and cannot write tasks. Read-only source tool is in a separate inherited toolset. Adapt the generic example prose to primary evidence; its exact typed identity is assignment-specific. This source has only one independent current action so OMIT optional action_key/action_anchor/action_relation (no frozen action anchors exist). If assignment.config.probe_mode equals transport, AFTER full source/resource reads call runner_probe_stress with your small researched payload instead of ordinary submit. It expands protocol filler to512KiB and dispatches the real submit callback. This is protocol stress, NOT model-generated512KiB. Otherwise ordinary discovery_research_submit. Use only probe source and discovery tools.')
        audit('run', {'run_id': run, 'session_id': session_id})
        return json.dumps({'run_id': run, 'index_revision': store.get_run(run)['index_revision'], 'next': 'Call discovery_research_run then fetch all submitted payload pages, assess every checklist dimension and discovery_join. No tasks or external writes.'})
    register_tool('runner_probe_start', start, {'count': {'type': 'integer', 'minimum': 1, 'maximum': 4}, 'mode': {'type': 'string', 'enum': ['functional', 'transport']}}, [], 'Create four synthetic immutable assignments for the actual runner.')
    def source(args, session_id='', task_id='', **kw):
        run, attempt = runner._child_for(session_id, task_id) or (None, None)
        if not attempt: return json.dumps({'error': 'No authentic bound discovery child'})
        runner._authorize(run, attempt['token'], session_id=session_id, task_id=task_id)
        key = 'source:' + attempt['token']
        pages = ctx.state.get(key, default=[]) or []
        if args['page'] not in pages: pages.append(args['page'])
        ctx.state.set(key, pages)
        return json.dumps({'page': args['page'], 'has_more': args['page'] == 1, 'content': 'Old request: order the banner now.' if args['page'] == 1 else 'Latest decision: banner order cancelled. Prepare the print proof for approval. Sample User owns this action.', 'caller': {'session_id': session_id, 'task_id': task_id}})
    register_tool('runner_probe_source', source, {'page': {'type': 'integer', 'enum': [1, 2]}}, ['page'], 'Read synthetic complete primary conversation. Both pages required.', toolset='runner-probe-source-reader')
    def example(args, session_id='', task_id='', **kw):
        payload = json.loads((Path(__file__).parent / 'tests/fixtures/discovery/bundle.json').read_text())
        found = runner._child_for(session_id, task_id)
        if found and found[1]:
            run, attempt = found
            candidate = store.get_candidate(run, attempt['candidate_id'])
            payload['candidate_id'] = attempt['candidate_id']
            identity = candidate['source_ids'][0].split(':')
            w = payload['workstreams'][0]
            w['exact_source_ids'] = [{'type': 'source', 'source_key': identity[1], 'account_key': identity[2], 'object_kind': identity[3], 'object_id': identity[4], 'message_id': 'latest'}]
            w.update(source_links=[])
        return json.dumps(payload)
    register_tool('runner_probe_example', example, {}, [], 'Read a generic valid schema example; adapt all evidence and identities to the actual assignment.')
    def stress(args, session_id='', task_id='', **kw):
        found = runner._child_for(session_id, task_id)
        if not found or not found[1]: return json.dumps({'error': 'Authentic bound child required'})
        run, attempt = found
        runner._authorize(run, attempt['token'], session_id=session_id, task_id=task_id)
        payload = json.loads(json.dumps(args['payload']))
        target = 512 * 1024
        def encoded(): return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()
        fields = ['implementation_context', 'dependencies_and_risks', 'new_information']
        w = payload['workstreams'][0]
        for field in fields: w[field] = []
        last = None
        for field in fields:
            for i in range(50):
                if len(encoded()) == target: break
                w[field].append('')
                remaining = target - len(encoded())
                if remaining < 0:
                    w[field].pop()
                    if last:
                        array, index = last
                        array[index] += 'x' * (target - len(encoded()))
                    break
                w[field][-1] = 'x' * min(3900, remaining)
                last = (w[field], len(w[field]) - 1)
            if len(encoded()) == target: break
        data = encoded()
        if len(data) != target: return json.dumps({'error': 'Fixture filler did not reach target', 'bytes': len(data)})
        from .discovery_runner import BINDING_KEYS
        base = {'run_id': run, 'token': attempt['token'], 'binding': {k: attempt[k] for k in BINDING_KEYS}}
        candidate = store.get_candidate(run, attempt['candidate_id'])
        mode = 'direct' if candidate['input_index'] % 2 == 0 else 'multipart'
        responses = []
        def dispatch(extra):
            result = json.loads(ctx.dispatch_tool('discovery_research_submit', {**base, **extra}, session_id=session_id, task_id=task_id))
            responses.append(result)
            return result
        if mode == 'direct':
            dispatch({'payload': payload})
        else:
            text = data.decode()
            parts = [text[i:i+12000] for i in range(0, len(text), 12000)]
            dispatch({'upload': {'action': 'begin', 'total_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'part_count': len(parts)}})
            for i, part in enumerate(parts): dispatch({'upload': {'action': 'part', 'index': i, 'content': part}})
            dispatch({'upload': {'action': 'commit'}})
        saved = store.get_attempt(run, attempt['token'])
        raw = {'label': 'protocol stress; fixture filler, not model-generated512KiB', 'mode': mode, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'caller_session': session_id, 'caller_task': task_id, 'responses': responses, 'saved_payload': saved.get('payload'), 'validation_error': saved.get('validation_error'), 'runtime': {'pid': os.getpid(), 'thread': threading.current_thread().name}}
        audit('stress-' + attempt['token'], raw)
        return json.dumps(raw)
    register_tool('runner_probe_stress', stress, {'payload': {'type': 'object'}}, ['payload'], 'Authenticated child-only512KiB protocol stress: expand small researched payload and dispatch real callback direct or lossless multipart; stop afterwards.')
    def wire_payload(args, **kw):
        raw = (json.dumps(args['payload'], indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()
        ctx.state.set('wire-payload', args['payload'])
        saved = ctx.state.get('wire-payload', default={})
        replay = (json.dumps(saved, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()
        return json.dumps({'label': 'registered host wire and state transport only; not authenticated runner callback', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'readback_sha256': hashlib.sha256(replay).hexdigest(), 'pid': os.getpid(), 'thread': threading.current_thread().name})
    register_tool('runner_probe_wire', wire_payload, {'payload': {'type': 'object'}}, ['payload'], 'Synthetic registered wire/state payload checksum and exact readback. Not an authenticated runner callback.')
    def receipt(args, **kw):
        latest = ctx.state.get('latest-run', default={}) or {}
        run = args.get('run_id') or latest.get('run_id')
        ledger = store.get_run(run) if run else {}
        return json.dumps({'run_id': run, 'ledger': ledger, 'last_start_hook': ctx.state.get('latest-start', default={}), 'guard': ctx.state.get('latest-guard', default={}), 'sentinel': ctx.state.get('latest-sentinel', default={}), 'source_pages': {a['token']: ctx.state.get('source:' + a['token'], default=[]) for a in ledger.get('attempts', {}).values()}, 'stress': {a['token']: ctx.state.get('latest-stress-' + a['token'], default={}) for a in ledger.get('attempts', {}).values()}, 'runtime': {'pid': os.getpid(), 'thread': threading.current_thread().name}}, default=str)
    register_tool('runner_probe_receipt', receipt, {'run_id': {'type': 'string'}}, [], 'Read exact persisted synthetic runner ledger and actual hook/caller receipts.')
