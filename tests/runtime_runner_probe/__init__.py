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
        run = store.init_run(origin={'session_id': session_id})
        count = args.get('count', 4)
        store.add_candidates(run, [{'title': 'Synthetic print proof ' + str(i), 'source_ids': ['source:synthetic:sample:thread:item' + str(i)]} for i in range(count)])
        store.freeze_index(run, rubric='Read full primary with runner_probe_source pages 1 and 2. Page 1 is stale; page 2 reverses it. Read every frozen resource. Schema example is available with runner_probe_example. Submit complete schema, not terminal prose. No live sources or writes. Demonstrate read-only guard by calling discovery_join with this run_id as a child; it must block or refuse child authority and cannot write tasks. Read-only source tool is in a separate inherited toolset. Use only probe source and discovery tools.')
        audit('run', {'run_id': run, 'session_id': session_id})
        return json.dumps({'run_id': run, 'index_revision': store.get_run(run)['index_revision'], 'next': 'Call discovery_research_run then fetch all submitted payload pages, assess every checklist dimension and discovery_join. No tasks or external writes.'})
    register_tool('runner_probe_start', start, {'count': {'type': 'integer', 'minimum': 1, 'maximum': 4}}, [], 'Create four synthetic immutable assignments for the actual runner.')
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
    def example(args, **kw):
        return (Path(__file__).parent / 'tests/fixtures/discovery/bundle.json').read_text()
    register_tool('runner_probe_example', example, {}, [], 'Read a generic valid schema example; adapt all evidence and identities to the actual assignment.')
    def receipt(args, **kw):
        latest = ctx.state.get('latest-run', default={}) or {}
        run = args.get('run_id') or latest.get('run_id')
        ledger = store.get_run(run) if run else {}
        return json.dumps({'run_id': run, 'ledger': ledger, 'last_start_hook': ctx.state.get('latest-start', default={}), 'guard': ctx.state.get('latest-guard', default={}), 'sentinel': ctx.state.get('latest-sentinel', default={}), 'source_pages': {a['token']: ctx.state.get('source:' + a['token'], default=[]) for a in ledger.get('attempts', {}).values()}, 'runtime': {'pid': os.getpid(), 'thread': threading.current_thread().name}}, default=str)
    register_tool('runner_probe_receipt', receipt, {'run_id': {'type': 'string'}}, [], 'Read exact persisted synthetic runner ledger and actual hook/caller receipts.')
