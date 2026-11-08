"""Profile-local discovery backend using the supported public lifecycle runner.

No private collectors, credential lookup, host registry discovery or model-created
coverage claims. Approved reader bindings map actual tool arguments and returns.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
from pathlib import Path
from .runtime import Runtime
from .core.discovery_state import DiscoveryStore, atomic_json, read_json
from .core.discovery_identity import UserError, _component, candidate_id
from .core.discovery_dossiers import content_revision
from .discovery_context import DiscoveryContext, resolve_identity
from .discovery_sources import SourceAdapter, collect_attested, validate_source_config
from .discovery_runner import DiscoveryRunner, RunnerPolicy, make_tool_handlers, make_hooks, CHECKLIST, BINDING_KEYS
from .discovery_conversion import DiscoveryConversion
from .discovery_digest import DiscoveryDigest


def _pick(value, path):
    if not isinstance(path, str): raise UserError('response mapping path must be text')
    for part in path.split('.') if path else []:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _profile_home():
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()).resolve()


class DiscoveryIntegration:
    def __init__(self, rt, *, profile_home=None):
        self.rt = rt
        self.home = Path(profile_home).resolve() if profile_home else _profile_home()
        self.store = DiscoveryStore(rt.data_dir / 'discovery')
        self.digest = DiscoveryDigest(rt.data_dir / 'discovery')
        self.conversion = DiscoveryConversion(rt, self.store)
        configured_transport = rt.ctx.get_config('discovery_transport_receipt', '')
        transport = json.loads(configured_transport) if configured_transport else {}
        if not isinstance(transport, dict): raise UserError('transport receipt must be an operator-configured JSON object')
        self.runner = DiscoveryRunner(rt.ctx, rt, store=self.store, transport_receipt=transport,
                                      recovery_authorizer=self._authorize_recovery)

    def _scheduled_identity(self, stream):
        """Only the public host execution identity can grant scheduled authority."""
        method = getattr(self.rt.ctx, 'current_cron_execution', None)
        execution = method() if callable(method) else None
        if execution is None: return None
        from .discovery_runner import normalize
        # normalize supports host Records/dataclasses, not arbitrary model args.
        receipt = normalize(execution)
        if not isinstance(receipt, dict): return None
        binding = stream.get('job_binding') or {}
        if (binding.get('verified') is not True or binding.get('job_id') != stream.get('job_id')
                or binding.get('origin_session') != stream.get('origin_session')
                or binding.get('profile') != getattr(self.rt.ctx, 'profile_name', None)
                or receipt.get('profile') != binding.get('profile')
                or receipt.get('job_id') != binding.get('job_id')
                or not receipt.get('execution_id') or not receipt.get('scheduled_instant')):
            return None
        return receipt

    def _authorize_recovery(self, run_id, old_parent, session_id):
        run = self.store.get_run(run_id)
        stream = self._stream(run['config'].get('stream_name', run['stream']))
        execution = self._scheduled_identity(stream)
        frozen = run['origin'].get('job_binding')
        if not execution or not frozen or frozen != stream.get('job_binding'):
            return False
        if run['origin'].get('stream_origin_session') != stream['origin_session']:
            return False
        with self.runner._state(run_id) as state:
            state.setdefault('adoptions', []).append({'from_session': old_parent, 'to_session': session_id,
                                                      'execution': execution, 'job_binding': frozen})
        return True

    def _stream(self, stream):
        from .discovery import _get
        return _get(self.rt, stream)

    def confirm_identity(self, account_key, identity, *, user_confirmed=False):
        _component(account_key, 'account key')
        if user_confirmed is not True:
            raise UserError('confirm explicit account identity mapping with user first')
        metadata = {**identity, 'account_key': account_key, 'confirmed': True}
        if set(identity) - {'name', 'aliases', 'user_id'}:
            raise UserError('identity mapping accepts only name, aliases and user_id')
        if not any(identity.get(k) for k in ('name', 'aliases', 'user_id')):
            raise UserError('explicit required identity fields missing; never infer name from email')
        if identity.get('name'):
            resolved = resolve_identity(metadata, [])
            if resolved['status'] != 'ready': raise UserError('missing or ambiguous account identity')
        if 'aliases' in identity and (not isinstance(identity['aliases'], list) or any(not isinstance(a, str) or not a for a in identity['aliases'])):
            raise UserError('aliases must be explicit nonempty strings')
        accounts = self.rt.ctx.state.get('discovery_identity_accounts', default={}) or {}
        accounts[account_key] = metadata
        self.rt.ctx.state.set('discovery_identity_accounts', accounts)
        return accounts[account_key]

    def configure(self, stream, config, *, user_approved=False):
        configured = copy.deepcopy(config)
        current = self._stream(stream)
        if user_approved is not True:
            raise UserError('approve source/account/scope/reader mapping before configuration')
        _component(configured.get('source_key'), 'source key')
        _component(configured.get('account_key'), 'account key')
        approved = [s for s in current['sources'] if s['name'] == configured.get('name')]
        if len(approved) != 1 or approved[0]['scope'] != configured.get('scope'):
            raise UserError('source scope differs from approved stream; update approved stream first')
        relevance = configured.get('relevance')
        if not isinstance(relevance, dict) or 'identity_requirements' not in relevance or not relevance.get('rules'):
            raise UserError('declare relevance rules and their actual identity requirements')
        if relevance['identity_requirements']:
            account = (self.rt.ctx.state.get('discovery_identity_accounts', default={}) or {}).get(configured['account_key'])
            if account: configured['identity'] = account
        validate_source_config(configured)
        binding = configured.get('binding')
        if binding:
            if not isinstance(binding, dict) or not binding.get('tool') or not isinstance(binding.get('response_fields'), dict):
                raise UserError('reader binding needs actual tool and response-field mapping')
            if binding['tool'] != configured['read_method']:
                raise UserError('binding tool must equal approved read_method')
        configured['approved'] = True
        configs = self.rt.ctx.state.get('discovery_sources', default={}) or {}
        configs.setdefault(current['name'], {})[configured['source_key']] = configured
        self.rt.ctx.state.set('discovery_sources', configs)
        from .jobs import reconcile_discovery_job
        reconcile_discovery_job(self.rt, current)
        return configured

    def _all_runs(self):
        return [self.store.get_run(p.parent.name) for p in sorted((self.store.state_root / 'runs').glob('*/ledger.json'))]

    def start(self, stream, *, session_id):
        current = self._stream(stream)
        storage_stream = current['name'] if ' ' not in current['name'] else 'stream-' + content_revision(current['name']).split(':')[-1][:24]
        if not session_id: raise UserError('actual parent session required')
        if session_id != current['origin_session'] and not self._scheduled_identity(current):
            raise UserError('only origin chat or verified bound scheduled occurrence can start/resume stream')
        with self.store._lock('start:' + current['name']):
            # A finalized digest is distinct from unresolved conversion/delivery.
            # Resume unfinished scan/research on its ORIGINAL window and config.
            pending = [r for r in self._all_runs() if r['config'].get('stream_name', r['stream']) == current['name'] and not r.get('review')]
            if pending:
                run = pending[0]
                try:
                    self.runner._parent(run['run_id'], session_id)
                except UserError:
                    self.runner.recover(run['run_id'], session_id=session_id, adopt=True)
                return {'run_id': run['run_id'], 'resumed': True, 'stream': current['name'],
                        'sources': run['config']['sources'], 'windows': run['config']['windows'],
                        'index_revision': run.get('index_revision'), 'recovery_required': True}
            configs = (self.rt.ctx.state.get('discovery_sources', default={}) or {}).get(current['name'], {})
            if len(configs) != len(current['sources']):
                raise UserError('configure approved source/account/read-method bindings and relevance before starting')
            now = dt.datetime.now(dt.timezone.utc)
            windows = {}
            for key, config in configs.items():
                validate_source_config(config)
                watermark = self.store.source_state(storage_stream, key).get('watermark')
                windows[key] = {'start': watermark or (now - dt.timedelta(days=1)).isoformat(), 'end': now.isoformat()}
            config = {'stream_name': current['name'], 'sources': list(configs.values()), 'windows': windows, 'areas': current['areas'],
                      'research_cap': current['research_cap'], 'timezone': current.get('timezone', self.rt.settings.timezone)}
            run = self.store.init_run(stream=storage_stream, business_date=self.rt.settings.today(), config=config,
                                      origin={'session_id': session_id, 'deliver': current.get('deliver', 'origin'),
                                              'stream_origin_session': current['origin_session'],
                                              'job_binding': copy.deepcopy(current.get('job_binding')),
                                              'cron_execution': self._scheduled_identity(current)})
            return {'run_id': run, 'resumed': False, 'stream': current['name'], 'sources': config['sources'],
                    'windows': windows, 'research_remaining_today': current['research_cap']}

    def _source(self, run_id, source_key, session_id):
        ledger = self.runner._parent(run_id, session_id)
        hits = [s for s in ledger['config']['sources'] if s['source_key'] == source_key]
        if len(hits) != 1: raise UserError('source not approved for this frozen run')
        return ledger, hits[0]

    def _read_page(self, config, start, end, cursor):
        binding = config.get('binding')
        if not binding:
            raise UserError('no verified structured reader binding; use explicitly partial attestation')
        args = copy.deepcopy(binding.get('arguments') or {})
        values = {**config, 'start': start, 'end': end, 'cursor': cursor}
        for parameter, field in binding.get('request_fields', {}).items():
            args[parameter] = values[field]
        capability = None
        if binding.get('capability'):
            probe = binding['capability']
            capability = self.rt.ctx.dispatch_tool(probe['tool'], copy.deepcopy(probe.get('arguments') or {}))
            capability = json.loads(capability) if isinstance(capability, str) else capability
            if not isinstance(capability, dict) or capability.get('error') or capability.get('available') is False:
                raise UserError('approved live capability probe failed')
        returned = self.rt.ctx.dispatch_tool(binding['tool'], args)
        raw = json.loads(returned) if isinstance(returned, str) else returned
        if binding.get('response_root'):
            raw = _pick(raw, binding['response_root'])
            raw = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(raw, dict) or raw.get('error') or raw.get('ok') is False:
            raise UserError('approved reader returned failure/nonstructured response')
        # Missing fields remain missing. Never echo request account/window into a
        # provider receipt or invent pagination_exhausted from a short page.
        result = {name: _pick(raw, path) for name, path in binding['response_fields'].items()}
        if binding.get('item_fields') or binding.get('item_identity'):
            from .core.discovery_identity import canonical_source_id
            items = result.get('items')
            if not isinstance(items, list): raise UserError('reader item mapping requires structured array')
            normalized = []
            for item in items:
                mapped = {k: _pick(item, path) for k, path in binding.get('item_fields', {}).items()}
                identity = binding.get('item_identity')
                if identity:
                    fields = {}
                    for key, selector in identity.items():
                        if not isinstance(selector, dict) or len(selector) != 1:
                            raise UserError('identity selector requires exactly path, config or literal')
                        kind, value = next(iter(selector.items()))
                        if kind == 'path': fields[key] = _pick(item, value)
                        elif kind == 'config' and value in {'account_key', 'source_key'}: fields[key] = config[value]
                        elif kind == 'literal' and key in {'type', 'object_kind'}: fields[key] = value
                        else: raise UserError('identity authority must come from actual item or scoped config')
                    mapped['source_ids'] = [canonical_source_id(fields)]
                if not mapped.get('source_revision'):
                    mapped['source_revision'] = content_revision(item)
                if not mapped.get('title'): raise UserError('reader item lacks mapped title')
                mapped['reader_item'] = copy.deepcopy(item)
                normalized.append(mapped)
            result['items'] = normalized
        result['reader_evidence'] = {'tool': binding['tool'], 'arguments': args, 'response': raw, 'capability': capability}
        return result

    def collect(self, run_id, source_key, *, session_id, envelope=None, max_pages=None):
        ledger, config = self._source(run_id, source_key, session_id)
        if ledger.get('index_revision'): raise UserError('source inventory already frozen')
        resource = 'collection-' + source_key
        if resource in ledger['resources']:
            info = ledger['resources'][resource]
            return json.loads((self.store.run_dir(run_id) / 'resources' / info['sha256']).read_text())
        window = ledger['config']['windows'][source_key]
        if envelope is None:
            receipt = SourceAdapter(self.store, config, read_page=self._read_page).collect(ledger['stream'], **window, max_pages=max_pages)
        else:
            if any(envelope.get(k) != v for k, v in window.items()):
                raise UserError('attestation must use SAME saved source window')
            receipt = collect_attested(self.store, ledger['stream'], config, envelope)
            receipt['status'] = 'partial'  # agent assertion never exhaustive
        receipt['source_key'] = source_key
        self.store.put_resource(run_id, resource, receipt)
        return receipt

    def freeze(self, run_id, *, session_id, context=None):
        ledger = self.runner._parent(run_id, session_id)
        if ledger.get('index_revision'):
            return {'run_id': run_id, 'index_revision': ledger['index_revision']}
        for config in ledger['config']['sources']:
            if 'collection-' + config['source_key'] not in ledger['resources']:
                raise UserError('collect every approved source or record failed/partial coverage first')
        candidates, selection = [], []
        for config in ledger['config']['sources']:
            for entry in self.store.source_state(ledger['stream'], config['source_key'])['backlog']:
                if entry['status'] in {'queued', 'deferred'} or (entry['status'] == 'selected' and entry.get('lineage', {}).get('run_id') == run_id):
                    candidates.append(entry['candidate'])
                    selection.append({'source_key': config['source_key'], 'backlog_id': entry['backlog_id'], 'candidate_id': candidate_id(entry['source_ids'])})
        self.store.add_candidates(run_id, candidates)
        self.store.put_resource(run_id, 'backlog-selection', selection)
        rubric = (Path(__file__).parent / 'skills' / 'discovery' / 'SKILL.md').read_text()
        approved_context = {'parent_supplied': context or {}, 'profile_documents': {}, 'unavailable': []}
        for relative in ('SOUL.md', 'memories/MEMORY.md', 'memories/USER.md'):
            document = (self.home / relative).resolve()
            if not document.is_relative_to(self.home):
                approved_context['unavailable'].append(relative + ': outside installing profile')
            elif document.is_file():
                approved_context['profile_documents'][relative] = document.read_text(encoding='utf-8')
        resources = DiscoveryContext(self.rt, self.store, installed_skills_root=self.home / 'skills').freeze(
            run_id, source_config={'config': ledger['config'], 'available_context': approved_context,
                                   'capability_evidence': 'Approved reader bindings; live failures are retained. Context supplied by parent is not a complete tool catalog.'}, rubric=rubric)
        with self.runner._state(run_id) as state:
            state['context_resources'] = resources
        index = self.store.freeze_index(run_id, rubric=rubric)
        self._settle_backlog(run_id)
        return {'run_id': run_id, 'index_revision': self.store.get_run(run_id)['index_revision'], 'context': resources, 'index': index}

    def _settle_backlog(self, run_id, join=None):
        ledger = self.store.get_run(run_id)
        info = ledger['resources'].get('backlog-selection')
        if not info: return
        selection = json.loads((self.store.run_dir(run_id) / 'resources' / info['sha256']).read_text())
        for entry in selection:
            cid = entry['candidate_id']
            candidate = self.store.get_candidate(run_id, cid)
            lineage = {'run_id': run_id, 'candidate_id': cid}
            if candidate['prefilter_disposition'] == 'excluded': state = 'excluded'
            elif join and cid in join['accepted']: state = 'accepted'
            elif join:
                attempted = any(a['candidate_id'] == cid for a in ledger['attempts'].values())
                state = 'blocked' if attempted else 'deferred'
            else: state = 'selected'
            self.store.update_backlog(ledger['stream'], entry['source_key'], entry['backlog_id'], status=state, lineage=lineage)

    def match(self, run_id, unit_id, *, session_id):
        self.runner._parent(run_id, session_id)
        result = self.conversion.match(run_id, unit_id)
        # Supply complete destination content for semantic judgment/CAS.
        for target in result['targets']:
            doc = self.rt.store().resolve(target['task_id'])
            info = self.store.put_resource(run_id, 'match-body-' + content_revision(doc.raw.decode()).split(':')[-1], doc.raw.decode())
            target['full_body_resource'] = info
        return result


    def _delivery_record(self, run, updates):
        """Trusted transport observation only, not an agent-attested public tool."""
        with self.store._lock('digest-ledger'):
            data = self.digest._load()
            old = data['delivery'][run]
            if old['state'] == 'delivered': return old
            old.update(updates)
            atomic_json(self.digest.path, data)
            return old

    def configure_delivery(self, stream, binding, *, user_approved=False):
        current = self._stream(stream)
        if user_approved is not True or binding.get('origin_session') != current['origin_session']:
            raise UserError('approve exact origin-chat delivery mapping before enabling sends')
        required = {'target', 'send_tool', 'read_tool', 'send_fields', 'send_id_path', 'read_fields', 'read_response'}
        if not required <= set(binding) or not all(binding[k] for k in required):
            raise UserError('delivery binding requires actual send AND exact readback tools/mappings')
        if set(binding['read_response']) != {'message_id', 'target', 'text'}:
            raise UserError('readback must verify message_id, origin target and full text')
        configs = self.rt.ctx.state.get('discovery_delivery', default={}) or {}
        configs[current['name']] = copy.deepcopy(binding)
        self.rt.ctx.state.set('discovery_delivery', configs)
        return {'configured': True, 'stream': current['name'], 'origin_session': current['origin_session']}

    def deliver(self, run_id, *, session_id):
        digest = self.digest.get(run_id)
        if digest['origin']['session_id'] != session_id:
            raise UserError('only exact origin chat can dispatch digest delivery')
        receipt = self.digest.delivery(run_id)
        if receipt['state'] == 'delivered': return receipt
        binding = receipt.get('binding') or (self.rt.ctx.state.get('discovery_delivery', default={}) or {}).get(digest['stream'])
        if not binding:
            return {**receipt, 'reason': 'No approved origin sender/readback binding. Scheduler/final-response delivery is not verified by digest preparation.'}
        if binding['origin_session'] != session_id:
            raise UserError('delivery mapping origin mismatch')
        values = {'target': binding['target'], 'text': digest['text']}
        try:
            if receipt['state'] == 'prepared':
                self.digest.begin_delivery(run_id)
                self._delivery_record(run_id, {'binding': binding})
                args = copy.deepcopy(binding.get('send_arguments') or {})
                for parameter, field in binding['send_fields'].items(): args[parameter] = values[field]
                response = self.rt.ctx.dispatch_tool(binding['send_tool'], args)
                response = json.loads(response) if isinstance(response, str) else response
                if not isinstance(response, dict) or response.get('error') or response.get('ok') is False:
                    raise UserError('sender did not return an authoritative receipt')
                message_id = _pick(response, binding['send_id_path'])
                if not isinstance(message_id, str) or not message_id:
                    raise UserError('sender receipt lacks exact message identity')
                receipt = self._delivery_record(run_id, {'message_id': message_id, 'send_receipt': response})
            if not receipt.get('message_id'):
                return receipt  # pending/unknown never authorizes blind resend
            values['message_id'] = receipt['message_id']
            args = copy.deepcopy(binding.get('read_arguments') or {})
            for parameter, field in binding['read_fields'].items(): args[parameter] = values[field]
            observed = self.rt.ctx.dispatch_tool(binding['read_tool'], args)
            observed = json.loads(observed) if isinstance(observed, str) else observed
            actual = {key: _pick(observed, path) for key, path in binding['read_response'].items()}
            if any(actual[k] != values[k] for k in ('message_id', 'target', 'text')):
                raise UserError('message readback differs from exact digest identity/origin/full text')
            return self._delivery_record(run_id, {'state': 'delivered', 'verified_sha256': digest['sha256'],
                                                 'readback': {'message_id': actual['message_id'], 'target': actual['target']}})
        except Exception as exc:
            return self._delivery_record(run_id, {'state': 'unknown', 'reason': str(exc)[:500]})

    def _decision_path(self, run_id, unit_id):
        self.store.get_candidate(run_id, unit_id)
        return self.store.run_dir(run_id) / 'decisions' / (unit_id + '.json')

    def record_decision(self, run_id, unit_id, *, decision, reason, session_id, target_task_id='', expected_revision='', useful_delta=False):
        self.runner._parent(run_id, session_id)
        if not reason or decision not in {'propose', 'auto', 'noop', 'conflict'}:
            raise UserError('substantive post-join decision required')
        path = self._decision_path(run_id, unit_id)
        with self.store._lock('decision:' + run_id + ':' + unit_id):
            old = read_json(path)
            request = {'decision': decision, 'reason': reason, 'target_task_id': target_task_id,
                       'expected_revision': expected_revision, 'useful_delta': useful_delta}
            if old:
                if old['request'] != request: raise UserError('post-join decision is immutable')
                # A saved auto plan is safe to resume by exact full postimage.
                if decision == 'auto': self.conversion.deliver_git(run_id, unit_id)
                return old
            outcome = self.conversion.match(run_id, unit_id)
            if outcome['kind'] == 'exact' and decision not in {'auto', 'noop'}:
                raise UserError('unique exact target requires useful-delta enrichment or true noop decision')
            if outcome['kind'] == 'conflict' and decision != 'conflict':
                raise UserError('multiple exact targets conflict; cannot mutate or propose a guessed target')
            if decision == 'conflict' and outcome['kind'] != 'conflict':
                raise UserError('no verified multiple-exact conflict')
            if decision in {'auto', 'noop'}:
                prepared = self.conversion.prepare(run_id, unit_id, choice=decision, reason=reason,
                             target_task_id=target_task_id, expected_revision=expected_revision, useful_delta=useful_delta)
                if decision == 'auto': self.conversion.deliver_git(run_id, unit_id)
            record = {'run_id': run_id, 'unit_id': unit_id, 'request': request, 'kind': outcome['kind'],
                      'targets': outcome['targets'], 'title': outcome['research']['title'],
                      'research_revision': content_revision(outcome['research'])}
            atomic_json(path, record)
            return record

    def finalize(self, run_id, *, session_id):
        ledger = self.runner._parent(run_id, session_id)
        if ledger.get('review'):
            self._settle_backlog(run_id, ledger['review']['joined'])
            return self.digest.get(run_id)
        info = ledger['resources'].get('join-record')
        if not info: raise UserError('global join required before review decisions/digest')
        join = json.loads((self.store.run_dir(run_id) / 'resources' / info['sha256']).read_text())
        if not join.get('joined'): raise UserError('global join incomplete')
        items, conflicts = [], []
        for candidate in ledger['candidates']:
            if not candidate.get('parent_candidate_id') or candidate['parent_candidate_id'] not in join['accepted'] or not candidate.get('eligible_research'): continue
            decision = read_json(self._decision_path(run_id, candidate['candidate_id']))
            if not decision: raise UserError('post-join semantic decision missing for ' + candidate['candidate_id'])
            if decision['request']['decision'] == 'propose': items.append(decision)
            elif decision['kind'] == 'conflict': conflicts.append({'unit_id': candidate['candidate_id'], 'reason': 'Multiple exact task destinations conflict', 'targets': decision['targets']})
        coverage = []
        for name, info in ledger['resources'].items():
            if name.startswith('collection-'):
                coverage.append(json.loads((self.store.run_dir(run_id) / 'resources' / info['sha256']).read_text()))
        stream = self._stream(ledger['config'].get('stream_name', ledger['stream']))
        origin = {**ledger['origin'], 'session_id': ledger['origin'].get('stream_origin_session', ledger['origin']['session_id'])}
        digest = self.digest.prepare(run_id, stream=ledger['config'].get('stream_name', ledger['stream']), day=ledger['business_date'], origin=origin,
                                     items=items, failures=join['failures'] + conflicts, coverage=coverage, label=stream.get('label', ''))
        self.store.save_review(run_id, {'digest': digest, 'conflicts': conflicts, 'joined': join})
        self._settle_backlog(run_id, join)
        return digest

    def decide(self, args, *, session_id, today=None):
        today = today or self.rt.settings.today()
        results, dismissed, prepared = [], [], []
        for ref in args.get('dismiss') or []:
            proposal = self.digest.resolve(str(ref), session_id=session_id, today=today, day=args.get('day', ''), stream=args.get('stream', ''))
            self.digest.decide(proposal['proposal_id'], 'dismissed')
            dismissed.append(proposal['proposal_id'])
        for ref in dict.fromkeys(args.get('approve') or []):
            proposal = self.digest.resolve(str(ref), session_id=session_id, today=today, day=args.get('day', ''), stream=args.get('stream', ''))
            run_id, unit_id = proposal['run_id'], proposal['unit_id']
            proposal_state = self.digest._load()['proposals'][proposal['proposal_id']]['state']
            if proposal_state == 'dismissed':
                raise UserError('proposal was dismissed; do not prepare or mutate it')
            if proposal_state == 'complete':
                prepared.append((proposal, run_id, unit_id, True))
                continue
            edit = copy.deepcopy((args.get('edits') or {}).get(str(ref), {}))
            plan_path, _ = self.conversion._paths(run_id, unit_id)
            plan = read_json(plan_path)
            if plan and any(key not in plan['request'] or plan['request'][key] != value for key, value in edit.items()):
                raise UserError('approval edits differ from immutable saved conversion; reconcile/cancel the unwritten plan explicitly or edit the existing task, never silently ignore corrections')
            if not plan:
                kind = proposal['kind']
                choice = edit.pop('choice', 'create' if kind == 'new' else '')
                if choice not in {'create', 'update'}:
                    raise UserError('semantic proposal requires explicit update or create choice')
                if kind == 'selection' and choice == 'update' and not edit.get('target_task_id'):
                    raise UserError('select one of ALL nominated target_task_id options')
                allowed = {'target_task_id', 'expected_revision', 'area', 'title', 'due', 'undated'}
                if set(edit) - allowed: raise UserError('unsupported approval edits: ' + ', '.join(sorted(set(edit) - allowed)))
                self.conversion.prepare(run_id, unit_id, choice=choice, reason='User approved exact immutable proposal ' + proposal['proposal_id'],
                                        user_approved=True, **edit)
            prepared.append((proposal, run_id, unit_id, False))
        # Validate/prepare the complete selected batch before the FIRST task write.
        for proposal, run_id, unit_id, completed in prepared:
            if not completed: self.digest.decide(proposal['proposal_id'], 'approved')
            receipt = self.conversion.deliver_git(run_id, unit_id) if hasattr(self.rt, 'git') else self.conversion.apply(run_id, unit_id)
            if receipt['state'] == 'complete': self.digest.decide(proposal['proposal_id'], 'complete')
            results.append(receipt)
        return {'results': results, 'dismissed': dismissed}

    def backend(self, run_id='', *, session_id):
        def project(ledger):
            # UI sees full records; child capability tokens/launch capabilities remain internal.
            run = ledger['run_id']
            if session_id not in {ledger['origin'].get('session_id'), ledger['origin'].get('stream_origin_session')}:
                self.runner._parent(run, session_id)
            attempts = [{k: v for k, v in a.items() if k not in {'token', 'handle'}} for a in ledger['attempts'].values()]
            decisions = [read_json(p) for p in sorted((self.store.run_dir(run) / 'decisions').glob('*.json'))]
            conversions = [read_json(p) for p in sorted((self.store.run_dir(run) / 'conversions').glob('*.receipt.json'))]
            digest = self.digest._load()['digests'].get(run)
            coverage = [json.loads((self.store.run_dir(run) / 'resources' / info['sha256']).read_text())
                        for name, info in ledger['resources'].items() if name.startswith('collection-')]
            join = (ledger.get('review') or {}).get('joined') or {}
            return {'run_id': run, 'time': ledger['created'], 'day': ledger['business_date'], 'stream': ledger['config'].get('stream_name', ledger['stream']),
                    'status': ledger['status'], 'sources_checked': ledger['config'].get('sources', []),
                    'coverage': coverage, 'research': attempts, 'candidates': ledger['candidates'],
                    'proposals': digest['items'] if digest else [], 'decisions': decisions, 'conversions': conversions,
                    'conflicts': (ledger.get('review') or {}).get('conflicts', []), 'failures': ledger['errors'] + join.get('failures', []),
                    'recovery': read_json(self.store.run_dir(run) / 'supervisor.json', {}),
                    'delivery': self.digest._load()['delivery'].get(run, {'state': 'not_prepared'})}
        if run_id: return project(self.store.get_run(run_id))
        return {'runs': [project(r) for r in self._all_runs() if session_id in {r['origin'].get('session_id'), r['origin'].get('stream_origin_session')}]}


STR = {'type': 'string'}
OBJ = {'type': 'object'}
BOOL = {'type': 'boolean'}
RUN = {'run_id': STR}
BINDING = {'type': 'object', 'properties': {k: STR for k in BINDING_KEYS}, 'required': list(BINDING_KEYS), 'additionalProperties': False}


def _schema(name, description, properties, required=()):
    return {'name': name, 'description': description, 'parameters': {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}}


SCHEMAS = {
 'discovery_research_run': _schema('discovery_research_run', 'Run/resume saved source-first research using the public bounded lifecycle. No proposals before full join.', {**RUN, 'expected_revision': STR}, ['run_id']),
 'discovery_research_fetch': _schema('discovery_research_fetch', 'Read full lossless frozen context/research pages with exact revision; continue until has_more=false.', {**RUN, 'resource': STR, 'revision': STR, 'token': STR, 'binding': BINDING, 'cursor': STR, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 16384}}, ['run_id', 'resource', 'revision']),
 'discovery_research_submit': _schema('discovery_research_submit', 'Child full callback only. Direct payload or multipart begin/part/commit. Continue until committed, then stop.', {**RUN, 'token': STR, 'binding': BINDING, 'payload': OBJ, 'upload': {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': ['begin', 'part', 'commit']}, 'total_bytes': {'type': 'integer'}, 'sha256': STR, 'part_count': {'type': 'integer'}, 'index': {'type': 'integer'}, 'content': STR}, 'required': ['action']}}, ['run_id', 'token', 'binding']),
 'discovery_research_accept': _schema('discovery_research_accept', 'Parent semantic review of FULL fetched immutable payload. Never rewrite child facts. All checklist observations required.', {**RUN, 'token': STR, 'payload_sha256': STR, 'assessment': {'type': 'object', 'properties': {'accepted': BOOL, 'reason': STR, 'retryable': BOOL, 'checklist': {'type': 'object', 'properties': {k: STR for k in CHECKLIST}, 'required': list(CHECKLIST)}}, 'required': ['accepted', 'reason', 'checklist']}}, ['run_id', 'token', 'payload_sha256', 'assessment']),
 'discovery_actions': _schema('discovery_actions', 'Freeze verified independent ask locators/outcomes before acceptance.', {**RUN, 'cid': STR, 'anchors': {'type': 'array', 'items': {'type': 'object', 'properties': {'locator': STR, 'outcome': STR}, 'required': ['locator', 'outcome']}}}, ['run_id', 'cid', 'anchors']),
 'discovery_reconcile': _schema('discovery_reconcile', 'Reconcile later cohorts against current accepted action outcomes before global join.', {**RUN, 'cid': STR, 'record': {'type': 'object', 'properties': {'decision': {'type': 'string', 'enum': ['distinct', 'represented', 'ambiguous']}, 'reason': STR, 'accepted_unit_ids': {'type': 'array', 'items': STR}}, 'required': ['decision', 'reason', 'accepted_unit_ids']}}, ['run_id', 'cid', 'record']),
 'discovery_join': _schema('discovery_join', 'Global barrier: every selected parent accepted, exhausted or explicitly degraded; live attempts never join.', {**RUN, 'degraded': {'type': 'object', 'additionalProperties': STR}}, ['run_id']),
 'discovery_recover': _schema('discovery_recover', 'Recover SAME saved run without blind relaunch/refund. New parent adoption requires out-of-band authorization.', {**RUN, 'owner_restarted': BOOL, 'adopt': BOOL}, ['run_id']),
 'discovery_release_hold': _schema('discovery_release_hold', 'Deliberately release safety hold without refunding unknown attempts.', {**RUN, 'reason': STR}, ['run_id', 'reason']),
 'discovery_config': _schema('discovery_config', 'Configure approved existing source reader or confirm account identity, scoped to installing profile. No credentials.', {'action': {'type': 'string', 'enum': ['source', 'identity', 'delivery', 'status']}, 'stream': STR, 'config': OBJ, 'account_key': STR, 'identity': OBJ, 'user_approved': BOOL}, ['action']),
 'discovery_collect': _schema('discovery_collect', 'Collect approved source with actual configured reader, or explicitly partial attested envelope. SAME saved window.', {**RUN, 'source_key': STR, 'envelope': OBJ, 'max_pages': {'type': 'integer', 'minimum': 1}}, ['run_id', 'source_key']),
 'discovery_context': _schema('discovery_context', 'Freeze collected source inventory, ALL-status task bodies, installed full skills, full rubric and approved context before research.', {**RUN, 'context': OBJ}, ['run_id']),
 'discovery_match': _schema('discovery_match', 'Post-join typed exact matching and all semantic target options; returns full body resources, no mutation.', {**RUN, 'unit_id': STR}, ['run_id', 'unit_id']),
 'discovery_digest': _schema('discovery_digest', 'Prepare/read immutable review digest after all match decisions. Preparation is not delivery proof.', {**RUN, 'action': {'type': 'string', 'enum': ['prepare', 'get', 'delivery', 'send']}}, ['run_id']),
 'discovery_decision': _schema('discovery_decision', 'Parent post-join disposition. Unique exact requires useful delta auto or byte-preserving noop; semantic/new remains proposal; multiple exact conflict.', {**RUN, 'unit_id': STR, 'decision': {'type': 'string', 'enum': ['propose', 'auto', 'noop', 'conflict']}, 'reason': STR, 'target_task_id': STR, 'expected_revision': STR, 'useful_delta': BOOL}, ['run_id', 'unit_id', 'decision', 'reason']),
 'discovery_conversion_recover': _schema('discovery_conversion_recover', 'Resume exact prebound approved conversion and verify local/Git postimages. Never creates a fresh plan.', {**RUN, 'unit_id': STR}, ['run_id', 'unit_id']),
 'discovery_runs': _schema('discovery_runs', 'Backend API: list full run records or get exact run including research, proposals, conflicts, recovery and delivery.', {'run_id': STR}),
}

_services = {}


def get_service(rt=None):
    rt = rt or Runtime()
    key = (id(rt.ctx), str(rt.data_dir))
    if key not in _services: _services[key] = DiscoveryIntegration(rt)
    service = _services[key]
    service.rt = rt
    service.conversion.rt = rt
    service.runner.rt = rt
    return service


def register(ctx, *, integration=None):
    # Catalog capability probes intentionally have no runtime state facade.
    # Register signatures now; resolve profile state only during an actual call.
    class DeferredRunner:
        def __getattr__(self, name):
            def invoke(*args, **kwargs):
                return getattr(get_service(Runtime(ctx)).runner, name)(*args, **kwargs)
            return invoke
    class DeferredIntegration:
        runner = DeferredRunner()
        def __getattr__(self, name):
            return getattr(get_service(Runtime(ctx)), name)
    service = integration or DeferredIntegration()
    handlers = make_tool_handlers(service.runner)
    def config_call(a, **_):
        action = a['action']
        if action == 'source':
            return service.configure(a['stream'], a['config'], user_approved=a.get('user_approved', False))
        if action == 'delivery':
            return service.configure_delivery(a['stream'], a['config'], user_approved=a.get('user_approved', False))
        if action == 'identity':
            return service.confirm_identity(a['account_key'], a['identity'], user_confirmed=a.get('user_approved', False))
        if action == 'status':
            return {'sources': ctx.state.get('discovery_sources', default={}), 'identities': ctx.state.get('discovery_identity_accounts', default={})}
        raise UserError('unknown configuration action')
    def digest_call(a, session_id='', **_):
        ledger = service.store.get_run(a['run_id'])
        if session_id not in {ledger['origin'].get('session_id'), ledger['origin'].get('stream_origin_session')}:
            raise UserError('digest belongs to another origin')
        action = a.get('action', 'prepare')
        if action == 'prepare': return service.finalize(a['run_id'], session_id=session_id)
        if action == 'get': return service.digest.get(a['run_id'])
        if action == 'delivery': return service.digest.delivery(a['run_id'])
        if action == 'send': return service.deliver(a['run_id'], session_id=session_id)
        raise UserError('unknown digest action')
    def conversion_recover(a, session_id='', **_):
        service.backend(a['run_id'], session_id=session_id)  # exact origin authorization
        return service.conversion.deliver_git(a['run_id'], a['unit_id'])
    handlers.update({
        'discovery_config': config_call,
        'discovery_digest': digest_call,
        'discovery_runs': lambda a, session_id='', **_: service.backend(**a, session_id=session_id),
        'discovery_decision': lambda a, session_id='', **_: service.record_decision(**a, session_id=session_id),
        'discovery_conversion_recover': conversion_recover,
        'discovery_collect': lambda a, session_id='', **_: service.collect(**a, session_id=session_id),
        'discovery_context': lambda a, session_id='', **_: service.freeze(**a, session_id=session_id),
        'discovery_match': lambda a, session_id='', **_: service.match(**a, session_id=session_id),
    })
    def wrap(name, handler):
        def call(args, session_id='', task_id='', **kwargs):
            try:
                if any(k in args for k in ('session_id', 'task_id', 'owner_session', 'parent_session_id', 'child_session_id')):
                    raise UserError('caller identity is host supplied, not model arguments')
                if not session_id: raise UserError('actual caller session unavailable')
                if name in make_tool_handlers(service.runner):
                    return handler(args, session_id=session_id, task_id=task_id, **kwargs)
                if service.runner._child_for(session_id, task_id):
                    raise UserError('research child cannot use parent mutation/integration tools')
                return json.dumps({'ok': True, 'result': handler(args, session_id=session_id, task_id=task_id, **kwargs)}, default=str)
            except (UserError, ValueError, KeyError, TypeError, OSError) as exc:
                return json.dumps({'ok': False, 'error': str(exc)[:1000]})
        return call
    for name, schema in SCHEMAS.items():
        handler = handlers[name]
        ctx.register_tool(name=name, toolset='alchemy-task-discovery-child' if name in {'discovery_research_fetch', 'discovery_research_submit'} else 'alchemy-task-discovery',
                          schema=schema, handler=wrap(name, handler), description=schema['description'], emoji='🜍')
    for name, hook in make_hooks(service.runner).items():
        ctx.register_hook(name, hook)
