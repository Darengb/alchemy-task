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
            if _name == 'pre_tool_call' and not result and runner._child_for(kw.get('session_id', ''), kw.get('task_id', '')):
                # Test-only containment preserves the inherited catalog but prevents
                # synthetic canary agents from touching unrelated instance state.
                allowed = {'tool_search', 'tool_describe', 'tool_call', 'discovery_research_fetch', 'discovery_research_submit', 'discovery_join', 'runner_probe_source', 'runner_probe_example', 'runner_probe_stress', 'runner_probe_late'}
                name = kw.get('tool_name', '')
                nested = (kw.get('args') or {}).get('calls', []) if name == 'tool_call' else []
                if isinstance(nested, str):
                    try: nested = json.loads(nested)
                    except ValueError: nested = [None]
                if name not in allowed or not isinstance(nested, list) or any(not isinstance(c, dict) or c.get('name') not in allowed for c in nested):
                    result = {'action': 'block', 'message': 'Synthetic TEST containment: use ONLY this probe source/read/fetch/submit tools. No terminal, code execution, other probes or external source tools. Preserve exact failure rather than bypassing the public handler.'}
                    audit('test-containment', {'kwargs': kw, 'result': result})
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
    def late_probe(args, session_id='', task_id='', **kw):
        import time
        found = runner._child_for(session_id, task_id)
        if not found or not found[1]: return json.dumps({'error': 'Authentic bound child required'})
        run, a = found
        runner._authorize(run, a['token'], session_id=session_id, task_id=task_id)
        audit('late-start', {'run_id': run, 'session_id': session_id, 'task_id': task_id, 'at': time.time()})
        time.sleep(90)
        from .discovery_runner import BINDING_KEYS
        resource = store.resource_info(run, 'manifest')
        result = ctx.dispatch_tool('discovery_research_fetch', {'run_id': run, 'resource': 'manifest', 'revision': resource['sha256'], 'token': a['token'], 'binding': {k: a[k] for k in BINDING_KEYS}}, session_id=session_id, task_id=task_id)
        receipt = {'run_id': run, 'actual_child_session': session_id, 'task_id': task_id, 'late_dispatch': json.loads(result), 'at': time.time(), 'pid': os.getpid()}
        audit('late-result', receipt)
        return json.dumps(receipt)
    register_tool('runner_probe_late', late_probe, {}, [], 'For cancellation test ONLY:90s synthetic blocking I/O then real authenticated late fetch, which must be fenced. No source or task access.')
    def cancel_case(args, session_id='', **kw):
        import time
        if not session_id: return json.dumps({'error': 'Actual parent required'})
        run = store.init_run(origin={'session_id': session_id}, stream='cancel-probe')
        store.add_candidates(run, [{'title': 'Synthetic cancellation evidence', 'source_ids': ['source:synthetic:sample:thread:cancel']}])
        store.freeze_index(run, rubric='Cancellation canary ONLY. FIRST ACTION call runner_probe_late with empty arguments before any research fetch. It sleeps90s to simulate blocking source I/O. Do not use any other tool,source or write. Finish after its result. This child is intentionally cancelled by a scaled60s RUNNING deadline.')
        short = DiscoveryRunner(ctx, SimpleNamespace(data_dir=root), store=store,
            policy=RunnerPolicy(admission_seconds=1, pending_seconds=10, running_seconds=60, poll_seconds=.2, transport_seconds=180),
            transport_receipt={'sequential_call':2040,'concurrent_batch':2040})
        response = make_tool_handlers(short)['discovery_research_run']({'run_id': run}, session_id=session_id)
        # New coordinator object models loss of plugin-local timers, not an actual service restart.
        fresh = DiscoveryRunner(ctx, SimpleNamespace(data_dir=root), store=store, policy=short.policy)
        reconnect = fresh.recover(run, session_id=session_id)
        time.sleep(95)
        reconciled = fresh.recover(run, session_id=session_id)
        owner_restart = fresh.recover(run, session_id=session_id, owner_restarted=True)
        result = {'run_id': run, 'scaled_policy': {'running_seconds':60}, 'supervisor_result': json.loads(response), 'same_owner_new_coordinator_reconnect': reconnect, 'reconciled_after_wait': reconciled, 'simulated_owner_restart': owner_restart, 'late_start': ctx.state.get('latest-late-start',default={}), 'late_result':ctx.state.get('latest-late-result',default={}), 'ledger':store.get_run(run), 'warning':'cooperative cancel only; not physical kill; new coordinator/recover flag simulation, not service or plugin-host restart'}
        audit('cancel', result)
        return json.dumps(result)
    register_tool('runner_probe_cancel_case', cancel_case, {}, [], 'Actual shortened60s RUNNING cancellation and real late callback fencing, followed by public same-owner reconnect and coordinator-state restart simulation. No service restart.')
    def late_case(args, session_id='', **kw):
        import time
        from .discovery_runner import normalize
        if not session_id: return json.dumps({'error':'Actual parent required'})
        run = store.init_run(origin={'session_id':session_id}, stream='late-probe')
        store.add_candidates(run,[{'title':'Synthetic late callback only','source_ids':['source:synthetic:sample:thread:late']}])
        store.freeze_index(run,rubric='Public cooperative cancellation protocol test only; no research or tasks.')
        cid=store.get_run(run)['candidates'][0]['candidate_id']
        a=store.reserve_attempt(run,cid,owner_session=session_id)
        request=runner._bootstrap(run,a)
        request['goal']='Cancellation PROTOCOL test only. Immediately call runner_probe_late {} exactly once, wait for its result, then stop. Do NOT fetch resources, research, read sources or use any other tools.'
        data=json.loads(request['context']);data['instructions']=request['goal'];request['context']=json.dumps(data)
        handle=normalize(ctx.subagent_lifecycle.launch(request))
        store.bind_attempt(run,a['token'],handle,owner_session=session_id)
        started=time.monotonic(); entered=False
        while time.monotonic()-started<60:
            entry=ctx.state.get('latest-late-start',default={}) or {}
            if entry.get('run_id')==run: entered=True;break
            ctx.subagent_lifecycle.wait(handle,timeout_seconds=.5)
        before=normalize(ctx.subagent_lifecycle.reconnect(handle))
        cancellation=runner._cancel(run,a['token'],handle,'execution_timeout')
        # The child tool may still finish its blocked I/O after cooperative cancel.
        until=time.monotonic()+100
        while entered and time.monotonic()<until:
            late=ctx.state.get('latest-late-result',default={}) or {}
            if late.get('run_id')==run: break
            time.sleep(.5)
        result={'run_id':run,'label':'public cancellation protocol stress, not runner deadline duration proof','entered_real_child_io':entered,'same_owner_reconnect':before,'cancellation':cancellation,'status':normalize(ctx.subagent_lifecycle.status(handle)),'result':normalize(ctx.subagent_lifecycle.result(handle)),'late_result':ctx.state.get('latest-late-result',default={}), 'ledger':store.get_run(run)}
        audit('late-case',result)
        return json.dumps(result)
    register_tool('runner_probe_late_case',late_case,{},[],'Public-lifecycle cancellation protocol stress using real runner bootstrap/store/hooks/binding and authentic blocked-I/O late fetch. No process restart.')
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
        return json.dumps({'run_id': run, 'ledger': ledger, 'last_start_hook': ctx.state.get('latest-start', default={}), 'guard': ctx.state.get('latest-guard', default={}), 'sentinel': ctx.state.get('latest-sentinel', default={}), 'source_pages': {a['token']: ctx.state.get('source:' + a['token'], default=[]) for a in ledger.get('attempts', {}).values()}, 'late_case': ctx.state.get('latest-late-case', default={}), 'late_result': ctx.state.get('latest-late-result', default={}), 'cancel_case': ctx.state.get('latest-cancel', default={}), 'stress': {a['token']: ctx.state.get('latest-stress-' + a['token'], default={}) for a in ledger.get('attempts', {}).values()}, 'runtime': {'pid': os.getpid(), 'thread': threading.current_thread().name}}, default=str)
    register_tool('runner_probe_receipt', receipt, {'run_id': {'type': 'string'}}, [], 'Read exact persisted synthetic runner ledger and actual hook/caller receipts.')
