"""Profile-local discovery backend using the supported public lifecycle runner.

No private collectors, credential lookup, host registry discovery or model-created
coverage claims. Approved reader bindings map actual tool arguments and returns.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
import re
import hashlib
import sqlite3
from zoneinfo import ZoneInfo
from pathlib import Path
from .runtime import Runtime
from .core.discovery_state import DiscoveryStore, atomic_json, read_json
from .core.discovery_identity import UserError, _component, candidate_id
from .core.discovery_dossiers import content_revision
from .core import taskfile as tf
from .core.discovery_research import child_schema, CANARY, SECRET_VALUE, MAX_TITLE_CHARS, MAX_REASON_CHARS, MAX_STRING_CHARS
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


WITHHELD_TITLE = 'Follow-up (title withheld; see source)'
_METADATA_LIMITS = {'title': MAX_TITLE_CHARS, 'prefilter_reason': MAX_REASON_CHARS, 'summary': MAX_STRING_CHARS,
                    'due': MAX_STRING_CHARS, 'priority': MAX_STRING_CHARS}


def _text(value):
    """Source _text projection: drop control characters and DEL."""
    return ''.join(ch for ch in str(value) if ch >= ' ' and ch != '\x7f').strip()


def _withheld_title(value):
    title = _text(value or '')[:MAX_TITLE_CHARS]
    return WITHHELD_TITLE if not title or CANARY.search(title) or SECRET_VALUE.search(title) else title


def _project_metadata(item):
    """COL-043 compact metadata projection; the lossless body resource is unchanged."""
    item = dict(item)
    item['title'] = _withheld_title(item.get('title'))
    for key in ('prefilter_reason', 'summary', 'due', 'priority'):
        if key not in item: continue
        value = _text(item[key])[:_METADATA_LIMITS[key]] if isinstance(item[key], str) else ''
        if not value or CANARY.search(value) or SECRET_VALUE.search(value): item.pop(key)
        else: item[key] = value
    return item


def _profile_home():
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()).resolve()


def host_origin(home, session_id, profile):
    """Chat of an ACTUAL host session id from the installing profile's public SessionDB."""
    path = Path(home) / 'state.db'
    if not session_id or not path.is_file(): return None
    try:
        from hermes_state import SessionDB
        db = SessionDB(db_path=path, read_only=True)
        try: row = db.get_session(session_id)
        finally: db.close()
        if not row or not row.get('chat_id') or not row.get('source') or row['source'] in {'cli', 'cron', 'subagent', 'tool', 'api_server'}:
            return None
        try: recorded = json.loads(row.get('origin_json') or '{}')
        except ValueError: recorded = {}
        if not isinstance(recorded, dict): recorded = {}
        return {'profile': profile, 'source': row['source'], 'chat_id': str(row['chat_id']),
                'thread_id': str(row.get('thread_id') or ''), 'parent_chat_id': str(recorded.get('parent_chat_id') or ''),
                # The chat as recorded when the host created the session: for a cron-seeded thread
                # these are the delivering job's captured origin chat name and workspace/guild.
                'chat_name': str(recorded.get('chat_name') or ''), 'scope_id': str(recorded.get('scope_id') or '')}
    except (ImportError, OSError, ValueError, RuntimeError, sqlite3.Error):
        return None


def host_conversation(home, session_id):
    """Read active transcript lineage through the host store, never model-supplied rows."""
    path = Path(home) / 'state.db'
    if not session_id or not path.is_file(): return [], None
    try:
        from hermes_state import SessionDB
        db = SessionDB(db_path=path, read_only=True)
        try:
            row = db.get_session(session_id)
            messages = db.get_messages(session_id, include_compacted=True, include_ancestors=True) if row else []
        finally: db.close()
        return messages, row
    except (ImportError, OSError, ValueError, RuntimeError, TypeError, sqlite3.Error):
        return [], None


def _mail_admission_declared(config):
    """Source admission is internal-sender mail minus service senders.

    An empty domain list admits every sender, so it must be explicit.
    """
    if config.get('kind') != 'mail':
        return True
    domains = config.get('sender_domains')
    has_domains = isinstance(domains, list) and domains and all(isinstance(d, str) and d.strip() for d in domains)
    return bool(has_domains) or config.get('admit_all') is True


class DiscoveryIntegration:
    def __init__(self, rt, *, profile_home=None):
        self.rt = rt
        self.utcnow = lambda: dt.datetime.now(dt.timezone.utc)
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
        if self.origin_authorized(stream, session_id) and run['origin'].get('stream_origin_session', run['origin'].get('session_id')) == stream['origin_session']:
            return True
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

    def _host_origin(self, session_id):
        """Read the installing profile's public SessionDB by ACTUAL host id."""
        return host_origin(self.home, session_id, self.rt.ctx.profile_name)

    def origin_authorized(self, stream, session_id):
        return bool(self._origin_relation(stream, session_id))

    def _origin_relation(self, stream, session_id):
        """Origin relation for run supervision/read surfaces, not reply authority."""
        if session_id == stream.get('origin_session'): return 'exact'
        original = self._host_origin(stream.get('origin_session'))
        reply = self._host_origin(session_id)
        if not original or not reply or original['profile'] != reply['profile'] or original['source'] != reply['source']:
            return None
        if (original['chat_id'], original['thread_id']) == (reply['chat_id'], reply['thread_id']):
            return 'exact'
        return None

    def approval_settings(self):
        saved = self.rt.ctx.state.get('discovery_approvals', default={}) or {}
        return {'owner_only': saved.get('owner_only', False), 'owners': copy.deepcopy(saved.get('owners', {}))}

    def _sender(self, session_id):
        # The current gateway turn wins over a shared session's original creator.
        from gateway.session_context import get_session_env
        if get_session_env('HERMES_SESSION_ID') == session_id:
            platform = get_session_env('HERMES_SESSION_PLATFORM')
            ids = [get_session_env('HERMES_SESSION_USER_ID'), get_session_env('HERMES_SESSION_USER_ID_ALT')]
        else:
            _, row = host_conversation(self.home, session_id)
            row = row or {}
            try: origin = json.loads(row.get('origin_json') or '{}')
            except ValueError: origin = {}
            platform = row.get('source', '')
            ids = [row.get('user_id'), origin.get('user_id_alt')]
        return platform, list(dict.fromkeys(str(x) for x in ids if x and not str(x).startswith('system:')))

    def authorize_approval(self, session_id):
        if not session_id or self.runner._child_for(session_id, ''):
            raise UserError('research child cannot approve discovery changes')
        method = getattr(self.rt.ctx, 'current_cron_execution', None)
        from gateway.session_context import get_session_env
        if (callable(method) and method() is not None) or get_session_env('HERMES_CRON_SESSION'):
            raise UserError('scheduled run cannot approve discovery changes')
        settings = self.approval_settings()
        if settings['owner_only']:
            platform, ids = self._sender(session_id)
            owners = settings['owners'].get(platform, [])
            if not set(ids).intersection(owners):
                raise UserError('approvals.owner_only is on; only the confirmed owner for this platform may approve, dismiss, revise or cancel')

    def configure_approvals(self, config, *, session_id='', user_approved=False, dashboard=False):
        if set(config) != {'owner_only'} or type(config['owner_only']) is not bool:
            raise UserError('approvals accepts only owner_only: boolean')
        if user_approved is not True:
            raise UserError('confirm approvals.owner_only with the user first')
        settings = self.approval_settings()
        if not dashboard:
            # An unregistered platform can be enrolled only by this explicit confirmed
            # setting action. It cannot approve anything until it has been enrolled.
            platform, ids = self._sender(session_id)
            if settings['owner_only'] and platform in settings['owners']:
                self.authorize_approval(session_id)
            elif settings['owner_only'] and not config['owner_only']:
                self.authorize_approval(session_id)
            else:
                method = getattr(self.rt.ctx, 'current_cron_execution', None)
                from gateway.session_context import get_session_env
                if (callable(method) and method() is not None) or get_session_env('HERMES_CRON_SESSION') or self.runner._child_for(session_id, ''):
                    raise UserError('scheduled run or child cannot configure approvals')
            if config['owner_only']:
                if not platform or not ids: raise UserError('host sender user ID unavailable; turn owner_only on from your own chat')
                settings['owners'][platform] = ids
        elif config['owner_only'] and not settings['owners']:
            raise UserError('confirm owner identity from your own chat with discovery_config action=approvals first')
        settings['owner_only'] = config['owner_only']
        self.rt.ctx.state.set('discovery_approvals', settings)
        return settings

    def _stream(self, stream):
        from .discovery import _get
        return _get(self.rt, stream)

    def _stream_or_frozen(self, name, origin_session):
        """Saved stream, or a removed stream's frozen origin: its digests/runs keep their origin binding."""
        from .discovery import DiscoveryError
        try:
            return self._stream(name)
        except DiscoveryError:
            return {'name': name, 'origin_session': origin_session, 'removed': True}

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
        previous = accounts.get(account_key)
        accounts[account_key] = metadata
        self.rt.ctx.state.set('discovery_identity_accounts', accounts)
        if previous is not None and previous != metadata:
            # Saved sources copied the old mapping and may carry its literals in
            # approved queries. They need visible review, not silent reuse.
            configs = self.rt.ctx.state.get('discovery_sources', default={}) or {}
            changed = False
            for stream_configs in configs.values():
                for saved in stream_configs.values():
                    if saved.get('account_key') == account_key and (saved.get('relevance') or {}).get('identity_requirements'):
                        saved['needs_reconfigure'] = {'status': 'needs_input', 'reason': 'confirmed account identity changed; review seed queries and relevance, then run discovery_config action=source again'}
                        changed = True
            if changed: self.rt.ctx.state.set('discovery_sources', configs)
        return accounts[account_key]

    def configure(self, stream, config, *, user_approved=False):
        configured = copy.deepcopy(config)
        configured.pop('needs_reconfigure', None)
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
        if not _mail_admission_declared(configured):
            raise UserError('mail source needs approved sender_domains (internal sender domains) or explicit admit_all: true')
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

    def start(self, stream, *, session_id, mode=None, pilot_limit=None, _distinct=False, _lineage=None):
        current = self._stream(stream)
        mode = mode or current.get('mode')
        if mode not in {'production', 'shadow', 'research_only'}:
            raise UserError('choose explicit production, shadow or research_only mode before run')
        if pilot_limit is not None and (mode == 'production' or type(pilot_limit) is not int or not 0 <= pilot_limit <= 200):
            raise UserError('pilot_limit requires shadow/research_only mode and an integer 0..200')
        storage_stream = current['name'] if ' ' not in current['name'] else 'stream-' + content_revision(current['name']).split(':')[-1][:24]
        if mode != 'production': storage_stream += '-' + mode
        if not session_id: raise UserError('actual parent session required')
        if not self.origin_authorized(current, session_id) and not self._scheduled_identity(current):
            raise UserError('only origin chat or verified bound scheduled occurrence can start/resume stream')
        self._retain_legacy(current['name'])
        for old in self._all_runs():
            if old['config'].get('stream_name', old['stream']) == current['name'] and old.get('review'):
                self.reconcile_endstate(old['run_id'])
        # Production retention: closed runs older than 60 days (well past the
        # seven-day reply window) become readable tombstones. prune() itself
        # keeps open, unresolved, referenced and pending-delivery runs.
        self.store.prune(days=60)
        with self.store._lock('start:' + current['name']):
            # A finalized digest is distinct from unresolved conversion/delivery.
            # Resume unfinished scan/research on its ORIGINAL window and config.
            pending = [r for r in self._all_runs() if r['config'].get('stream_name', r['stream']) == current['name'] and r['config'].get('mode') == mode and not r.get('review')]
            if pending and not _distinct:
                run = pending[0]
                if pilot_limit != run['config'].get('pilot_limit'):
                    raise UserError('pilot selection is frozen; resume with original pilot_limit')
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
            stale = sorted(key for key, c in configs.items() if c.get('needs_reconfigure'))
            if stale:
                raise UserError('needs_input: reconfigure source(s) %s: %s' % (', '.join(stale), configs[stale[0]]['needs_reconfigure']['reason']))
            undeclared = sorted(key for key, c in configs.items() if not _mail_admission_declared(c))
            if undeclared:
                # A mail source saved before the setup gate never runs with implicit admit-all.
                raise UserError('needs_input: reconfigure mail source(s) %s with approved sender_domains or explicit admit_all: true' % ', '.join(undeclared))
            approved = [(s['name'], s['scope']) for s in current['sources']]
            configured = [(s.get('name'), s.get('scope')) for s in configs.values()]
            if any(configured.count(pair) != 1 for pair in approved) or any(pair not in approved for pair in configured):
                raise UserError('source configuration membership/scope no longer matches approved stream; reconfigure before NEW scan')
            now = self.utcnow()
            windows = {}
            for key, config in configs.items():
                validate_source_config(config)
                source_state = self.store.source_state(storage_stream, key)
                watermark = source_state.get('watermark')
                if not watermark:
                    # No committed coverage yet: a failed or partial first run's
                    # interval is retained, so start at its earliest attempted
                    # start instead of silently sliding to now-24h.
                    attempted = [r['start'] for r in source_state.get('coverage', [])
                                 if r.get('verification') == 'adapter_verified' and isinstance(r.get('start'), str)]
                    watermark = min(attempted, key=lambda s: dt.datetime.fromisoformat(s.replace('Z', '+00:00'))) if attempted else None
                windows[key] = {'start': watermark or (now - dt.timedelta(days=1)).isoformat(), 'end': now.isoformat()}
            config = {'stream_name': current['name'], 'mode': mode, 'sources': list(configs.values()), 'windows': windows, 'areas': current['areas'],
                      'research_cap': current['research_cap'], 'timezone': current.get('timezone', self.rt.settings.timezone)}
            if pilot_limit is not None: config['pilot_limit'] = pilot_limit
            business_date = now.astimezone(ZoneInfo(config['timezone'])).date().isoformat()
            run = self.store.init_run(stream=storage_stream, business_date=business_date, config=config,
                                      origin={'session_id': session_id, 'deliver': current.get('deliver', 'origin'),
                                              'stream_origin_session': current['origin_session'],
                                              'job_binding': copy.deepcopy(current.get('job_binding')),
                                              'cron_execution': self._scheduled_identity(current)}, lineage=_lineage)
            return {'run_id': run, 'resumed': False, 'stream': current['name'], 'sources': config['sources'],
                    'windows': windows, 'research_remaining_today': current['research_cap']}

    def replay(self, run_id, *, operation, mode, session_id, user_approved=False, candidate_ids=None):
        """Three explicit operations; never relabel a current query as old input."""
        if operation not in {'saved_input', 'fresh_validation', 'targeted_supplement'}:
            raise UserError('unknown replay operation')
        if mode not in {'shadow', 'research_only'}:
            raise UserError('historical operations require explicit shadow/research_only mode; no automatic old task mutations')
        old = self.store.get_run(run_id)
        stream = self._stream(old['config'].get('stream_name', old['stream']))
        if user_approved is not True or not self.origin_authorized(stream, session_id):
            raise UserError('explicit actual origin approval required for historical operation')
        if not old.get('review') or not old.get('index_revision'):
            raise UserError('historical operation requires finalized frozen original input')
        parents = [c for c in old['candidates'] if not c.get('parent_candidate_id')]
        ids = [c['candidate_id'] for c in parents]
        if operation == 'targeted_supplement':
            if not isinstance(candidate_ids, list) or not candidate_ids or len(set(candidate_ids)) != len(candidate_ids) or any(c not in ids for c in candidate_ids):
                raise UserError('targeted supplement requires distinct retained original candidate_ids')
        elif candidate_ids is not None:
            raise UserError('candidate_ids only supported for targeted_supplement')
        lineage = {'operation': operation, 'original_run_id': run_id,
                   'original_index_revision': old['index_revision'], 'original_business_date': old['business_date'],
                   'expected_candidates': [{'candidate_id': c['candidate_id'], 'source_ids': c['source_ids'], 'title': c['title']} for c in parents if candidate_ids is None or c['candidate_id'] in candidate_ids]}
        if operation != 'saved_input':
            return {**self.start(stream['name'], session_id=session_id, mode=mode, _distinct=True, _lineage=lineage),
                    'operation': operation, 'faithful_replay': False}
        # Verify every saved input before creating a distinct run. No old writes.
        from .core.discovery_research import child_schema
        from .core.discovery_state import _json_bytes
        if old.get('schema_version') != 2 or old.get('schema_revision') != hashlib.sha256(_json_bytes(child_schema())).hexdigest():
            raise UserError('saved replay schema compatibility failed')
        inputs = {}
        for name, info in old['resources'].items():
            raw = (self.store.run_dir(run_id) / 'resources' / info['sha256']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != info['sha256'] or len(raw) != info['total_bytes']:
                raise UserError('saved replay resource integrity failed')
            inputs[name] = raw.decode('utf-8')
        if 'source-material' not in inputs or any('source-body-' + c['candidate_id'] not in inputs for c in parents):
            raise UserError('saved replay primary resources unavailable; choose current validation/supplement explicitly')
        config = {**copy.deepcopy(old['config']), 'mode': mode, 'replay_operation': 'saved_input'}
        storage = old['stream'] + '-replay'
        # Stream identifiers have a bounded shared format; avoid length expansion.
        storage = 'replay-' + content_revision(storage).split(':')[-1][:24]
        new = self.store.init_run(stream=storage, business_date=old['business_date'], config=config,
            origin={'session_id': session_id, 'stream_origin_session': stream['origin_session'], 'deliver': 'local'}, lineage=lineage)
        fields = {'title', 'source_ids', 'prefilter_disposition', 'prefilter_reason', 'summary', 'due', 'priority', 'source_revision', 'source_key'}
        self.store.add_candidates(new, [{k: v for k, v in c.items() if k in fields} for c in parents])
        prefixes = ('source-body-', 'collection-', 'task-body-', 'installed-skill-', 'skill-')
        names = {'source-material', 'task_inventory', 'skill-inventory', 'source_config', 'context-rubric', 'context-bootstrap'}
        for name, raw in inputs.items():
            if name in names or name.startswith(prefixes): self.store.put_resource(new, name, json.loads(raw) if old['resources'][name].get('entry_count') is not None else raw)
        self.store.put_resource(new, 'replay-inputs', lineage)
        context = json.loads(inputs.get('context-bootstrap', '{}'))
        context['source-material'] = self.store.resource_info(new, 'source-material')
        with self.runner._state(new) as state: state['context_resources'] = context
        self.store.freeze_index(new, rubric=inputs['rubric'])
        return {'run_id': new, 'operation': operation, 'faithful_replay': True,
                'original_run_id': run_id, 'business_date': old['business_date'], 'windows': config['windows']}

    def _source(self, run_id, source_key, session_id):
        ledger = self.runner._parent(run_id, session_id)
        hits = [s for s in ledger['config']['sources'] if s['source_key'] == source_key]
        if len(hits) != 1: raise UserError('source not approved for this frozen run')
        return ledger, hits[0]

    def _read_page(self, config, start, end, cursor, *, binding=None):
        binding = binding or config.get('binding')
        if not binding:
            raise UserError('no verified structured reader binding; use explicitly partial attestation')
        args = copy.deepcopy(binding.get('arguments') or {})
        values = {**config, 'start': start, 'end': end, 'cursor': cursor}
        for parameter, field in binding.get('request_fields', {}).items():
            args[parameter] = _pick(values, field)
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
        if isinstance(raw, dict) and raw.get('error') and binding.get('error_fields'):
            fields = {k: _pick(raw, path) for k, path in binding['error_fields'].items()}
            if type(fields.get('status')) is not int or not isinstance(fields.get('headers'), dict):
                raise UserError('reader structured-error mapping lacks actual numeric status/headers')
            class Response(dict):
                pass
            response = Response(fields['headers']); response.status = fields['status']
            failure = UserError('approved reader structured HTTP error')
            failure.resp = response
            content = fields.get('content')
            failure.content = json.dumps(content).encode() if isinstance(content, dict) else content
            raise failure
        if not isinstance(raw, dict):
            raise UserError('approved reader returned failure/nonstructured response')
        if raw.get('error') or raw.get('ok') is False or raw.get('success') is False:
            # A structured provider-reported failure (for example Slack's
            # thread_not_found). Callers that skip one thread can name it.
            code = raw.get('error') if isinstance(raw.get('error'), str) else 'failure'
            raise UserError('approved reader returned failure/nonstructured response',
                            details={'provider_error': re.sub(r'[^A-Za-z0-9_.-]', '', code)[:60] or 'failure'})
        # Missing fields remain missing. Never echo request account/window into a
        # provider receipt or invent pagination_exhausted from a short page.
        result = {name: _pick(raw, path) for name, path in binding['response_fields'].items()}
        if raw.get('truncated'): result['truncated'] = raw['truncated']
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
        proof = content_revision(result['reader_evidence']).split(':')[-1]
        atomic_json(self.store.state_root / 'source-evidence' / (proof + '.json'), result['reader_evidence'])
        return result

    def _collector_reader(self, run_id, config):
        from .discovery_collectors import make_daily_reader
        def thread(actual, start, end, identity):
            binding = actual.get('thread_binding')
            if not binding: raise UserError('approved full-thread reader binding required')
            return self._read_page({**actual, 'collector_request': {'operation': 'thread', 'thread_id': identity}}, start, end, None, binding=binding)
        def replies(actual, start, end, request):
            binding = (actual.get('primary_bindings') or {}).get(request['operation']) or actual.get('replies_binding')
            if not binding: raise UserError('approved Slack primary operation binding required: ' + request['operation'])
            return self._read_page({**actual, 'collector_request': request}, start, end, None, binding=binding)
        return make_daily_reader(config, self._read_page, snapshot_root=self.store.run_dir(run_id) / 'source-snapshots',
                                 read_thread=thread, read_replies=replies)

    def collect(self, run_id, source_key, *, session_id, envelope=None, max_pages=None):
        ledger, config = self._source(run_id, source_key, session_id)
        if ledger.get('index_revision'): raise UserError('source inventory already frozen')
        resource = 'collection-' + source_key
        prior = self._collection_receipts(ledger).get(source_key)
        if prior and prior['status'] == 'complete': return prior
        window = ledger['config']['windows'][source_key]
        if envelope is None:
            receipt = SourceAdapter(self.store, config, read_page=self._collector_reader(run_id, config)).collect(ledger['stream'], **window, max_pages=max_pages, previous_receipt=prior if prior and prior.get('verification') == 'adapter_verified' else None)
        else:
            if any(envelope.get(k) != v for k, v in window.items()):
                raise UserError('attestation must use SAME saved source window')
            receipt = collect_attested(self.store, ledger['stream'], config, envelope)
            receipt['status'] = 'partial'  # agent assertion never exhaustive
        receipt['source_key'] = source_key
        receipt['pass'] = (prior or {}).get('pass', 0) + 1
        if prior: resource += '-pass-' + str(receipt['pass'])
        self.store.put_resource(run_id, resource, receipt)
        return receipt

    def _collection_receipts(self, ledger):
        current = {}
        for name, info in ledger['resources'].items():
            if name.startswith('collection-'):
                receipt = json.loads((self.store.run_dir(ledger['run_id']) / 'resources' / info['sha256']).read_text())
                key = receipt['source_key']
                if key not in current or receipt.get('pass', 1) > current[key].get('pass', 1): current[key] = receipt
        return current

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
                if entry['status'] in {'queued', 'deferred', 'pilot_skipped'} or (entry['status'] == 'selected' and entry.get('lineage', {}).get('run_id') == run_id):
                    candidates.append(entry['candidate'])
                    selection.append({'source_key': config['source_key'], 'backlog_id': entry['backlog_id'], 'candidate_id': candidate_id(entry['source_ids'])})
        if ledger.get('lineage', {}).get('operation') == 'targeted_supplement':
            expected = ledger['lineage']['expected_candidates']
            wanted = {x['candidate_id'] for x in expected}
            present = {candidate_id(c['source_ids']) for c in candidates}
            self.store.put_resource(run_id, 'supplement-selection', {'expected': expected,
                'present': sorted(wanted & present), 'missing_current': sorted(wanted - present),
                'outside_target': sorted(present - wanted)})
            candidates = [c for c in candidates if candidate_id(c['source_ids']) in wanted]
            selection = [s for s in selection if s['candidate_id'] in wanted]
        # Full primary bodies stay lossless and pageable, separate from the
        # helper's intentionally compact, strictly typed candidate metadata.
        grouped = {}
        for candidate in candidates:
            grouped.setdefault(candidate_id(candidate['source_ids']), []).append(candidate)
        source_index, compact = [], []
        allowed = {'title', 'source_ids', 'prefilter_disposition', 'prefilter_reason', 'summary', 'due', 'priority', 'source_revision', 'source_key'}
        for cid, versions in grouped.items():
            body = self.store.put_resource(run_id, 'source-body-' + cid, versions)
            source_index.append({'candidate_id': cid, 'body': body, 'versions': len(versions)})
            compact.append((cid, _project_metadata({k: v for k, v in versions[-1].items() if k in allowed})))
        primary_index = self.store.put_resource(run_id, 'source-material', source_index)
        # One unindexable item must never wedge the stream: withhold it with a
        # visible reason and block its backlog entry; the body stays saved.
        withheld = []
        for cid, item in compact:
            try:
                self.store.add_candidates(run_id, [item])
            except UserError as exc:
                withheld.append({'candidate_id': cid, 'title': _withheld_title(item.get('title')),
                                 'reason': 'Source item could not be indexed (%s); full source is saved for review' % str(exc)[:200]})
        if withheld:
            gone = {w['candidate_id'] for w in withheld}
            for entry in [s for s in selection if s['candidate_id'] in gone]:
                self.store.update_backlog(ledger['stream'], entry['source_key'], entry['backlog_id'], status='blocked',
                                          lineage={'run_id': run_id, 'candidate_id': entry['candidate_id']})
            selection = [s for s in selection if s['candidate_id'] not in gone]
            self.store.put_resource(run_id, 'freeze-withheld', withheld)
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
        resources['source-material'] = primary_index
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
            elif candidate.get('research_selection') == 'pilot_skipped': state = 'pilot_skipped'
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
        owner = binding.get('delivery_owner', 'verified_sender')
        if owner not in {'native_origin', 'verified_sender'}:
            raise UserError('delivery_owner must be native_origin or verified_sender')
        if owner == 'native_origin':
            if any(d.get('stream') == current['name'] and self.digest.delivery(r)['state'] in {'inflight', 'unknown', 'pending'} for r, d in self.digest._load()['digests'].items()):
                raise UserError('reconcile pending explicit sends before switching delivery owner')
            from .jobs import activate_discovery_job
            current = activate_discovery_job(self.rt, {**current, 'delivery_owner': owner})
            return {'configured': True, 'stream': current['name'], 'delivery_owner': owner, 'job_id': current['job_id'], 'activation_state': current['activation_state']}
        required = {'target', 'send_tool', 'read_tool', 'send_fields', 'send_id_path', 'read_fields', 'read_response'}
        if not required <= set(binding) or not all(binding[k] for k in required):
            raise UserError('delivery binding requires actual send AND exact readback tools/mappings')
        if set(binding['read_response']) != {'message_id', 'target', 'text'}:
            raise UserError('readback must verify message_id, origin target and full text')
        if binding.get('scheduled_approved') is not True or not isinstance(binding.get('toolsets'), list) or not binding['toolsets'] or any(not isinstance(t, str) or not t for t in binding['toolsets']):
            raise UserError('approve scheduled origin delivery and actual sender/reader toolsets before activation')
        # Verify existing origin content without sending a test message.
        values = {'target': binding['target'], 'message_id': binding.get('verification_message_id')}
        if not values['message_id'] or not isinstance(binding.get('verification_text'), str):
            raise UserError('setup readback requires an existing origin message id and exact full text')
        args = copy.deepcopy(binding.get('read_arguments') or {})
        for parameter, field in binding['read_fields'].items(): args[parameter] = values[field]
        observed = self.rt.ctx.dispatch_tool(binding['read_tool'], args)
        observed = json.loads(observed) if isinstance(observed, str) else observed
        actual = {key: _pick(observed, path) for key, path in binding['read_response'].items()}
        if actual != {**values, 'text': binding['verification_text']}:
            raise UserError('setup readback does not match exact origin message/target/full text')
        if current.get('activation_state') or current.get('job_id'):
            from .jobs import activate_discovery_job
            current = activate_discovery_job(self.rt, {**current, 'delivery_owner': owner}, binding)
        else:
            from .discovery import _streams, _save_streams
            current = {**current, 'delivery_owner': owner}
            streams = _streams(self.rt); streams[current['name']] = current; _save_streams(self.rt, streams)
        configs = self.rt.ctx.state.get('discovery_delivery', default={}) or {}
        configs[current['name']] = copy.deepcopy(binding)
        self.rt.ctx.state.set('discovery_delivery', configs)
        return {'configured': True, 'stream': current['name'], 'origin_session': current['origin_session'],
                'delivery_owner': owner,
                'activation_state': current.get('activation_state', 'ACTIVE'), 'job_id': current.get('job_id')}

    def deliver(self, run_id, *, session_id):
        with self.store._lock('delivery-send:' + run_id):
            return self._deliver(run_id, session_id=session_id)

    def _deliver(self, run_id, *, session_id):
        digest = self.digest.get(run_id)
        receipt = self.digest.delivery(run_id)
        binding = receipt.get('binding') or (self.rt.ctx.state.get('discovery_delivery', default={}) or {}).get(digest['stream'])
        stream = self._stream(digest['stream'])
        scheduled = self._scheduled_identity(stream)
        if stream.get('delivery_owner', 'native_origin') == 'native_origin':
            if not self.origin_authorized(stream, session_id) and not scheduled:
                raise UserError('only origin or verified scheduled occurrence may prepare host delivery')
            return self.delivery_status(run_id)
        if not self.origin_authorized(stream, session_id) and not (scheduled and binding and binding.get('scheduled_approved') is True):
            raise UserError('only origin or an explicitly approved bound scheduled occurrence may deliver')
        if receipt['state'] == 'delivered': return receipt
        if not binding:
            return {**receipt, 'reason': 'No approved origin sender/readback binding. Scheduler delivery is local-only; no alternate send is authorized.'}
        if binding['origin_session'] != digest['origin']['session_id']:
            raise UserError('delivery mapping origin mismatch')
        if stream.get('job_id'):
            from .jobs import read_discovery_job
            if read_discovery_job(self.rt, stream).get('deliver') != 'local':
                raise UserError('explicit send blocked: scheduler final delivery must be local-only')
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
                if receipt['state'] in {'pending', 'inflight'}:
                    return self._delivery_record(run_id, {'state': 'unknown', 'reason': 'Unfinished persisted send intent without exact message receipt; never blindly resend'})
                return receipt  # unknown never authorizes blind resend
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

    def delivery_status(self, run_id):
        digest = self.digest.get(run_id)
        receipt = self.digest.delivery(run_id)
        stream = self._stream_or_frozen(digest['stream'], digest['origin']['session_id'])
        owner = stream.get('delivery_owner', 'native_origin')
        if stream.get('removed'):
            # Removed stream: the owner frozen with the digest, else the plugin sender's own receipt evidence.
            owner = digest['origin'].get('delivery_owner') or ('verified_sender' if receipt.get('binding') or receipt.get('message_id') else 'native_origin')
        if owner != 'native_origin': return receipt
        # Native cron owns posting/retries. Preparation and final return supply no
        # host transport evidence, even when an origin exists in SessionDB.
        return {**receipt, 'state': 'host_pending', 'delivery_owner': 'native_origin',
                'delivered': False, 'verification': 'awaiting_host',
                'native_target_status': 'configured' if self._host_origin(stream['origin_session']) else 'unconfigured',
                'deliver': stream.get('deliver', 'origin'), 'job_id': stream.get('job_id'),
                'final_text': digest['text'], 'digest_sha256': digest['sha256'],
                'instruction': 'Return final_text exactly to the host. Do not send an alternate post; native host owns delivery and retries.'}

    def reconcile_endstate(self, run_id):
        """Replay downstream projections from durable facts, never receipt claims."""
        ledger = self.store.get_run(run_id)
        if not ledger.get('review'): return {'state': 'open'}
        self._settle_backlog(run_id, ledger['review']['joined'])
        data = self.digest._load()
        delivery = data['delivery'].get(run_id, {})
        pending = [] if delivery.get('state') == 'delivered' and delivery.get('verified_sha256') == data['digests'][run_id]['sha256'] and delivery.get('readback') else ['digest_delivery']
        if pending and self._native_delivery_closed(run_id, ledger, data, delivery):
            pending = []
        decisions = {}
        for candidate in ledger['candidates']:
            if not candidate.get('parent_candidate_id'): continue
            wid = candidate['candidate_id']
            record = read_json(self._decision_path(run_id, wid), {})
            action = record.get('request', {}).get('decision')
            complete = action == 'noop' or candidate.get('research_disposition', '').startswith('exclude_')
            if action == 'auto':
                receipt = read_json(self.conversion._paths(run_id, wid)[1], {})
                complete = receipt.get('state') == 'complete'
            elif action == 'propose':
                proposal = next((p for p in data['proposals'].values() if p['binding']['run_id'] == run_id and p['binding']['unit_id'] == wid), None)
                complete = bool(proposal and proposal['state'] in {'complete', 'dismissed'})
            if not complete: pending.append('candidate:' + wid)
            decisions[wid] = 'complete' if complete else 'proposed'
        with self.store._lock(self.store._run_lock_name(run_id)):
            current = self.store.get_run(run_id)
            changed = current.get('pending_operations') != pending
            for candidate in current['candidates']:
                if candidate['candidate_id'] in decisions and candidate.get('state') != decisions[candidate['candidate_id']]:
                    candidate['state'] = decisions[candidate['candidate_id']]; changed = True
            current['pending_operations'] = pending
            # An unchanged ledger is not rewritten: its mtime is the retention age.
            if changed: self.store._save(run_id, current)
        return {'state': 'pending' if pending else 'resolved', 'pending_operations': pending}

    def _native_delivery_closed(self, run_id, ledger, data, delivery):
        """Native host delivery holds no plugin receipt to verify. Once the
        seven-day reply window is over, an untouched native digest is no longer
        a pending operation (an attempted explicit send still is)."""
        digest = data['digests'][run_id]
        if delivery.get('state') != 'prepared' or not digest.get('day'): return False
        # The owner frozen with the digest (N4); only digests from before N4 use the current stream's.
        owner = digest['origin'].get('delivery_owner')
        if not owner:
            owner = self._stream_or_frozen(digest['stream'], digest['origin']['session_id']).get('delivery_owner', 'native_origin')
        if owner != 'native_origin': return False
        zone = ZoneInfo(ledger['config'].get('timezone') or self.rt.settings.timezone)
        expires = (dt.date.fromisoformat(digest['day']) + dt.timedelta(days=7)).isoformat()
        return expires < self.utcnow().astimezone(zone).date().isoformat()

    def _retain_legacy(self, stream):
        legacy = self.rt.ctx.state.get('proposals:' + stream, default={}) or {}
        if not legacy.get('items'): return []
        key = 'discovery_legacy:' + stream
        old = self.rt.ctx.state.get(key, default={}) or {}
        for identity, value in legacy['items'].items():
            old.setdefault(identity, {'status': 'legacy_unresearched', 'original': copy.deepcopy(value)})
        self.rt.ctx.state.set(key, old)
        return list(old.values())

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
                      **{k: outcome['research'].get(k) for k in ('current_understanding', 'substantive_next_action', 'source_links', 'related_context_links', 'new_information', 'sources_unavailable')},
                      'research_disposition': outcome['research']['disposition'],
                      'uncertainty': outcome['research']['decisions_and_open_questions']['open_questions'],
                      'research_revision': content_revision(outcome['research'])}
            atomic_json(path, record)
            return record

    def finalize(self, run_id, *, session_id):
        ledger = self.runner._parent(run_id, session_id)
        if ledger.get('review'):
            self.reconcile_endstate(run_id)
            return self.digest.get(run_id)
        info = ledger['resources'].get('join-record')
        if not info: raise UserError('global join required before review decisions/digest')
        join = json.loads((self.store.run_dir(run_id) / 'resources' / info['sha256']).read_text())
        if not join.get('joined'): raise UserError('global join incomplete')
        items, conflicts, outcomes = [], [], []
        for candidate in ledger['candidates']:
            if not candidate.get('parent_candidate_id') or candidate['parent_candidate_id'] not in join['accepted'] or not candidate.get('eligible_research'): continue
            decision = read_json(self._decision_path(run_id, candidate['candidate_id']))
            if not decision: raise UserError('post-join semantic decision missing for ' + candidate['candidate_id'])
            if decision['request']['decision'] == 'propose': items.append(decision)
            elif decision['kind'] == 'conflict': conflicts.append({'unit_id': candidate['candidate_id'], 'title': decision['title'], 'reason': 'Multiple exact task destinations conflict', 'targets': decision['targets']})
            elif decision['request']['decision'] == 'noop':
                continue  # true noops are omitted from the digest (source: not reported as updates)
            elif decision['request']['decision'] == 'auto':
                _, receipt_path = self.conversion._paths(run_id, candidate['candidate_id'])
                receipt = read_json(receipt_path, {})
                outcomes.append({'unit_id': candidate['candidate_id'], 'title': decision['title'],
                                 'task_id': receipt.get('task_id', decision['request']['target_task_id']),
                                 'status': receipt.get('state', 'noop' if decision['request']['decision'] == 'noop' else 'unknown'),
                                 'git': receipt.get('git'), 'phone': receipt.get('phone'),
                                 'resume_action': {'tool': 'discovery_conversion_recover', 'run_id': run_id, 'unit_id': candidate['candidate_id']} if receipt.get('state') != 'complete' and decision['request']['decision'] == 'auto' else None})
        coverage = list(self._collection_receipts(ledger).values())
        supplement_failures = []
        if 'supplement-selection' in ledger['resources']:
            info = ledger['resources']['supplement-selection']
            selection = read_json(self.store.run_dir(run_id) / 'resources' / info['sha256'])
            supplement_failures = [{'title': x['title'], 'reason': 'Retained candidate not found in current approved window; original input remains saved'} for x in selection['expected'] if x['candidate_id'] in selection['missing_current']]
        if 'freeze-withheld' in ledger['resources']:
            info = ledger['resources']['freeze-withheld']
            supplement_failures += [{'title': x['title'], 'reason': x['reason']} for x in read_json(self.store.run_dir(run_id) / 'resources' / info['sha256'])]
        stream = self._stream(ledger['config'].get('stream_name', ledger['stream']))
        # The delivery owner is frozen with the digest so a later stream removal keeps the run's real delivery state.
        origin = {**ledger['origin'], 'session_id': ledger['origin'].get('stream_origin_session', ledger['origin']['session_id']),
                  'delivery_owner': stream.get('delivery_owner', 'native_origin')}
        digest = self.digest.prepare(run_id, stream=ledger['config'].get('stream_name', ledger['stream']), day=ledger['business_date'], origin=origin,
                                     items=items, failures=[{**f, 'title': next((c['title'] for c in ledger['candidates'] if c['candidate_id'] == f.get('candidate_id', f.get('cid', f.get('unit_id')))), f.get('title', 'Research follow-up'))} for f in join['failures'] + supplement_failures], coverage=coverage, outcomes=outcomes,
                                     blocked=conflicts, label=stream.get('label', ''), review_namespace=run_id if ledger.get('lineage', {}).get('operation') else '', deferred=join.get('deferred', []))
        with self.store._lock(self.store._run_lock_name(run_id)):
            pending = self.store.get_run(run_id); pending['pending_operations'] = ['finalization_projection']; self.store._save(run_id, pending)
        self.store.save_review(run_id, {'digest': digest, 'conflicts': conflicts, 'joined': join})
        self.reconcile_endstate(run_id)
        return digest

    def decide(self, args, *, session_id, today=None):
        self.authorize_approval(session_id)
        args = copy.deepcopy(args)
        data = self.digest._load()
        streams = self.rt.ctx.state.get('streams', default={}) or {}
        value = ' '.join(str(args.get('stream') or '').casefold().split())
        value = re.sub(r'\b(?:task discovery|discovery)\b', '', value).strip()
        if value in {'task', 'tasks'}: value = ''
        if value:
            names = {d['stream'] for d in data['digests'].values()} | set(streams)
            matched = [n for n in names if value == n.casefold() or value == str(streams.get(n, {}).get('label') or '\0').casefold()]
            if len(matched) != 1: raise UserError('unknown or ambiguous stream; valid streams: ' + ', '.join(sorted(names)))
            value = matched[0]
        args['stream'] = value
        review = args.get('review')
        reviewed = None
        refs = [*(args.get('approve') or []), *(args.get('dismiss') or [])]
        explicit = bool(refs) and (bool(args.get('day')) or all(str(ref).startswith('p_') for ref in refs))
        if review is not None and not explicit:
            if not isinstance(review, str) or not re.fullmatch(r'[0-9a-fA-F]{12}', review):
                raise UserError('Review code must be exactly 12 hex characters')
            reviewed = {r for r in data['digests'] if hashlib.sha256(r.encode()).hexdigest()[:12] == review.lower()}
            if len(reviewed) != 1: raise UserError('unknown Review code in this profile; paste a stored digest or supply its exact proposal ID')
        messages, _ = host_conversation(self.home, session_id)
        def present(text):
            codes = {m.group(1).lower(): m.start() for m in re.finditer(r'\bReview:\s*([0-9a-fA-F]{12})\b', text)}
            positions = {}
            for run, digest in data['digests'].items():
                position = codes.get(hashlib.sha256(run.encode()).hexdigest()[:12], -1)
                if digest['text'].strip(): position = max(position, text.rfind(digest['text'].strip()))
                if position >= 0: positions[run] = position
            return sorted(positions, key=lambda run: positions[run], reverse=True)
        # The latest user's reply-to pointer wins over any digest elsewhere in history.
        transcript_runs = None
        quoted = False
        users = [m for m in reversed(messages) if m.get('role') == 'user' and isinstance(m.get('content'), str)]
        if users:
            quote = re.search(r'\[Replying to(?: your previous message)?: "(.*?)"\]', users[0]['content'], re.S)
            if quote: transcript_runs = set(present(quote[1])) or None
            quoted = transcript_runs is not None
        if transcript_runs is None:
            # Different streams anywhere in the active conversation need disambiguation;
            # for one stream take only its most recently mentioned digest.
            latest = {}
            ordered = [m for m in reversed(messages) if m.get('role') in {'user', 'assistant'} and isinstance(m.get('content'), str)]
            for message in ordered:
                for run in present(message['content']):
                    name = data['digests'][run]['stream']
                    if name not in latest: latest[name] = run
            transcript_runs = set(latest.values()) or None
        if value and transcript_runs is not None:
            transcript_runs = {r for r in transcript_runs if data['digests'][r]['stream'] == value} or None
        selected = reviewed if reviewed is not None else transcript_runs
        if today is None:
            exact_runs = {data['proposals'][str(ref)]['binding']['run_id'] for ref in refs if str(ref) in data['proposals']}
            relevant = exact_runs if refs and all(str(ref).startswith('p_') for ref in refs) else None
            if not explicit: relevant = selected
            candidates = [d for d in data['digests'].values() if (not value or d['stream'] == value)
                          and (relevant is None or d['run_id'] in relevant)
                          and (not args.get('day') or args['day'] == 'yesterday' or d['day'] == args['day'])]
            zones = {self.store.get_run(d['run_id'])['config'].get('timezone', self.rt.settings.timezone) for d in candidates}
            if len(zones) > 1 and not value:
                raise UserError('streams have different frozen local days; specify stream for reply')
            today = self.utcnow().astimezone(ZoneInfo(next(iter(zones), self.rt.settings.timezone))).date().isoformat()
        # A review code or reply-to quote binds that exact digest. An unquoted digest in
        # the conversation selects its stream's local day, so same-day reruns keep numbers.
        exact = reviewed if reviewed is not None else (transcript_runs if quoted else None)
        days = None if exact is not None or transcript_runs is None else {data['digests'][r]['stream']: data['digests'][r]['day'] for r in transcript_runs}
        def resolve(ref):
            return self.digest.resolve(str(ref), session_id=session_id, today=today, day=args.get('day', ''), stream=value, runs=exact, days=days)
        # Resolve the whole reply before the first dismissal or conversion writes anything.
        resolved = {str(ref): resolve(ref) for ref in refs}
        return self._decide_resolved(args, resolve=lambda ref: resolved.get(str(ref)) or resolve(ref))

    def _decide_resolved(self, args, *, resolve):
        """Shared immutable prepare/batch-preflight/apply path after caller resolution."""
        results, dismissed, prepared = [], [], []
        for ref in args.get('dismiss') or []:
            proposal = resolve(ref)
            self.digest.decide(proposal['proposal_id'], 'dismissed')
            dismissed.append(proposal['proposal_id'])
        for ref in dict.fromkeys(args.get('approve') or []):
            proposal = resolve(ref)
            run_id, unit_id = proposal['run_id'], proposal['unit_id']
            proposal_state = self.digest._load()['proposals'][proposal['proposal_id']]['state']
            if proposal_state == 'dismissed':
                raise UserError('proposal was dismissed; do not prepare or mutate it')
            if proposal_state == 'complete':
                prepared.append((proposal, run_id, unit_id, True))
                continue
            edit = copy.deepcopy((args.get('edits') or {}).get(str(ref), {}))
            if 'title' in edit and (not isinstance(edit['title'], str) or not edit['title'].strip() or len(edit['title']) > 200):
                raise UserError('approval title edit requires 1..200 characters')
            plan_path, _ = self.conversion._paths(run_id, unit_id)
            plan = read_json(plan_path)
            if plan and any(key not in plan['request'] or plan['request'][key] != value for key, value in edit.items()):
                raise UserError('approval edits differ from the immutable saved conversion; revise or cancel the unwritten plan with discovery_conversion_recover (action=revise or action=cancel), or edit the existing task; corrections are never silently ignored')
            if not plan:
                kind = proposal['kind']
                choice = edit.pop('choice', 'create' if kind == 'new' else '')
                if choice not in {'create', 'update'}:
                    raise UserError('semantic proposal requires explicit update or create choice')
                if kind == 'selection' and choice == 'update' and not edit.get('target_task_id'):
                    raise UserError('select one of ALL nominated target_task_id options')
                allowed = {'target_task_id', 'expected_revision', 'area', 'title', 'due', 'undated', 'scope_notes', 'priority', 'scheduled', 'execution_method', 'notes', 'plan', 'checklist', 'active_goal', 'correction_overlay'}
                if set(edit) - allowed: raise UserError('unsupported approval edits: ' + ', '.join(sorted(set(edit) - allowed)))
                self.conversion.prepare(run_id, unit_id, choice=choice, reason='User approved exact immutable proposal ' + proposal['proposal_id'],
                                        user_approved=True, **edit)
            prepared.append((proposal, run_id, unit_id, False))
        # Validate/prepare the complete selected batch before the FIRST task write.
        for group in args.get('merge') or []:
            if not isinstance(group, list) or len(group) < 2: raise UserError('merge requires groups of at least two approved references')
            selected = []
            for ref in group:
                proposal = resolve(ref)
                hits = [(r, w) for p, r, w, complete in prepared if p['proposal_id'] == proposal['proposal_id'] and not complete]
                if len(hits) != 1: raise UserError('every merge member must be explicitly approved in this batch')
                selected += hits
            self.conversion.merge_prepared(selected, reason='User explicitly merged approved proposals: ' + ', '.join(map(str, group)))
        # A complete proposal is already done: report its saved receipt, never re-CAS
        # it against later user edits, so it cannot block new items in the batch.
        self.conversion.preflight([(r, w) for _, r, w, completed in prepared if not completed])
        for proposal, run_id, unit_id, completed in prepared:
            if completed:
                results.append({**read_json(self.conversion._paths(run_id, unit_id)[1], {}), 'already_complete': True})
                continue
            self.digest.decide(proposal['proposal_id'], 'approved')
            receipt = self.conversion.deliver_git(run_id, unit_id) if hasattr(self.rt, 'git') else self.conversion.apply(run_id, unit_id)
            if receipt['state'] == 'complete': self.digest.decide(proposal['proposal_id'], 'complete')
            results.append(receipt)
        return {'results': results, 'dismissed': dismissed}

    def link_audit(self, *, session_id, legacy_roots=()):
        """Read-only HLP-061 audit over the runs this caller may see."""
        if not isinstance(legacy_roots, (list, tuple)) or any(not isinstance(x, str) or not x.strip() for x in legacy_roots):
            raise UserError('legacy_roots must be workspace-relative folder names')
        visible = {r['run_id'] for r in self._all_runs() if session_id in {r['origin'].get('session_id'), r['origin'].get('stream_origin_session')}
                   or self.origin_authorized(self._stream_or_frozen(r['config'].get('stream_name', r['stream']), r['origin'].get('stream_origin_session', r['origin'].get('session_id'))), session_id)}
        return self.conversion.audit_links(run_ids=visible, legacy_roots=legacy_roots)

    def backend(self, run_id='', *, session_id):
        def project(ledger):
            run = ledger['run_id']
            if session_id not in {ledger['origin'].get('session_id'), ledger['origin'].get('stream_origin_session')} and not self.origin_authorized(self._stream_or_frozen(ledger['config'].get('stream_name', ledger['stream']), ledger['origin'].get('stream_origin_session', ledger['origin'].get('session_id'))), session_id):
                self.runner._parent(run, session_id)
            return self.project_run(ledger)
        if run_id: return project(self.store.get_run(run_id))
        return {'runs': [project(r) for r in self._all_runs() if session_id in {r['origin'].get('session_id'), r['origin'].get('stream_origin_session')} or self.origin_authorized(self._stream_or_frozen(r['config'].get('stream_name', r['stream']), r['origin'].get('stream_origin_session', r['origin'].get('session_id'))), session_id)]}

    def project_run(self, ledger):
        """Project durable state after the entrypoint has checked its caller."""
        def project(ledger):
            # UI sees full records; child capability tokens/launch capabilities remain internal.
            run = ledger['run_id']
            if ledger.get('review'):
                self.reconcile_endstate(run)
                ledger = self.store.get_run(run)
            attempts = [{k: v for k, v in a.items() if k not in {'token', 'handle'}} for a in ledger['attempts'].values()]
            decisions = [read_json(p) for p in sorted((self.store.run_dir(run) / 'decisions').glob('*.json'))]
            conversions = [read_json(p) for p in sorted((self.store.run_dir(run) / 'conversions').glob('*.receipt.json'))]
            digest = self.digest._load()['digests'].get(run)
            coverage = list(self._collection_receipts(ledger).values())
            join = (ledger.get('review') or {}).get('joined') or {}
            return {'run_id': run, 'time': ledger['created'], 'day': ledger['business_date'], 'stream': ledger['config'].get('stream_name', ledger['stream']),
                    'status': ledger['status'], 'sources_checked': ledger['config'].get('sources', []),
                    'coverage': coverage, 'research': attempts, 'candidates': ledger['candidates'],
                    'mode': ledger['config'].get('mode'), 'timezone': ledger['config'].get('timezone'),
                    'lineage': ledger.get('lineage', {}), 'pilot_skipped': join.get('pilot_skipped', []),
                    'legacy_proposals': list((self.rt.ctx.state.get('discovery_legacy:' + ledger['config'].get('stream_name', ledger['stream']), default={}) or {}).values()),
                    'proposals': digest['items'] if digest else [], 'decisions': decisions, 'conversions': conversions,
                    'conflicts': (ledger.get('review') or {}).get('conflicts', []), 'failures': ledger['errors'] + join.get('failures', []), 'deferred': join.get('deferred', []),
                    'recovery': read_json(self.store.run_dir(run) / 'supervisor.json', {}),
                    'delivery': self.delivery_status(run) if digest else {'state': 'not_prepared'}}
        result = project(ledger)
        data = self.digest._load()
        for failure in data['digests'].get(result['run_id'], {}).get('failures', []):
            # Finalization adds a display title to join failures. Count that
            # same failure once while preserving its original diagnostic fields.
            key = {k: v for k, v in failure.items() if k != 'title'}
            prior = next((f for f in result['failures'] if {k: v for k, v in f.items() if k != 'title'} == key), None)
            if prior is None:
                result['failures'].append(copy.deepcopy(failure))
            elif 'title' not in prior and 'title' in failure:
                prior['title'] = failure['title']
        receipts = {r['unit_id']: r for r in result['conversions']}
        proposals = []
        today = self.utcnow().astimezone(ZoneInfo(result['timezone'] or self.rt.settings.timezone)).date().isoformat()
        for frozen in result['proposals']:
            state = data['proposals'][frozen['proposal_id']]['state']
            item = {**copy.deepcopy(frozen), 'state': state, 'expired': frozen['expires'] < today}
            if state in {'approved', 'complete'}:
                plan_path, _ = self.conversion._paths(result['run_id'], frozen['unit_id'])
                plan = read_json(plan_path, {})
                receipt = receipts.get(frozen['unit_id'], {})
                fm = tf.split_text(plan['postimage'], rt=True)[0] if plan else {}
                item['result'] = {'task_id': receipt.get('task_id', plan.get('task_id')),
                                  'title': fm.get('title', frozen['title']),
                                  'operation': 'created' if plan.get('request', {}).get('choice') == 'create' else 'updated',
                                  'state': receipt.get('state', 'prepared'), 'receipt': receipt}
            proposals.append(item)
        result['proposals'] = proposals
        result['outcomes'] = copy.deepcopy(data['digests'].get(result['run_id'], {}).get('outcomes', []))
        for outcome in result['outcomes']:
            receipt = receipts.get(outcome['unit_id'], {})
            if receipt:
                outcome.update(status=receipt['state'], task_id=receipt['task_id'], git=receipt.get('git'), phone=receipt.get('phone'))
                if receipt['state'] == 'complete': outcome['resume_action'] = None
                if receipt.get('applied_at'): outcome['applied_at'] = receipt['applied_at']
        result['summary'] = {state: sum(p['state'] == state for p in proposals) for state in ('pending', 'approved', 'complete', 'dismissed')}
        result['summary'].update(auto_updated=sum(o['status'] in {'local_verified', 'git_pending', 'phone_pending', 'complete'} for o in result['outcomes']),
                                 conflicts=len(result['conflicts']), failures=len(result['failures']), deferred=len(result['deferred']))
        result['degraded'] = bool(result['failures'] or any(c.get('status') != 'complete' for c in result['coverage']))
        return result


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
 'discovery_replay': _schema('discovery_replay', 'Explicit saved_input replay of finalized frozen inputs, or current fresh_validation / targeted_supplement. Distinct lineage/review; no old task mutation.', {**RUN, 'operation': {'type': 'string', 'enum': ['saved_input', 'fresh_validation', 'targeted_supplement']}, 'mode': {'type': 'string', 'enum': ['shadow', 'research_only']}, 'candidate_ids': {'type': 'array', 'items': STR}, 'user_approved': BOOL}, ['run_id', 'operation', 'mode', 'user_approved']),
 'discovery_config': _schema('discovery_config', 'Configure approved source/delivery, confirm identity, or approvals.owner_only (default off). action=approvals config={owner_only:true|false} requires explicit user confirmation (user_approved=true). Enabling records the host sender ID for this platform; use your own chat. status shows current approvals. No approver list or credentials.', {'action': {'type': 'string', 'enum': ['source', 'identity', 'delivery', 'approvals', 'status']}, 'stream': STR, 'config': OBJ, 'account_key': STR, 'identity': OBJ, 'user_approved': BOOL}, ['action']),
 'discovery_collect': _schema('discovery_collect', 'Collect approved source with actual configured reader, or explicitly partial attested envelope. SAME saved window.', {**RUN, 'source_key': STR, 'envelope': OBJ, 'max_pages': {'type': 'integer', 'minimum': 1}}, ['run_id', 'source_key']),
 'discovery_context': _schema('discovery_context', 'Freeze collected source inventory, ALL-status task bodies, installed full skills, full rubric and approved context before research.', {**RUN, 'context': OBJ}, ['run_id']),
 'discovery_match': _schema('discovery_match', 'Post-join typed exact matching and all semantic target options; returns full body resources, no mutation.', {**RUN, 'unit_id': STR}, ['run_id', 'unit_id']),
 'discovery_digest': _schema('discovery_digest', 'Prepare/read immutable review digest after all match decisions. Preparation is not delivery proof.', {**RUN, 'action': {'type': 'string', 'enum': ['prepare', 'get', 'delivery', 'send']}}, ['run_id']),
 'discovery_decision': _schema('discovery_decision', 'Parent post-join disposition. Unique exact requires useful delta auto or byte-preserving noop; semantic/new remains proposal; multiple exact conflict.', {**RUN, 'unit_id': STR, 'decision': {'type': 'string', 'enum': ['propose', 'auto', 'noop', 'conflict']}, 'reason': STR, 'target_task_id': STR, 'expected_revision': STR, 'useful_delta': BOOL}, ['run_id', 'unit_id', 'decision', 'reason']),
 'discovery_conversion_recover': _schema('discovery_conversion_recover', 'Inspect/resume exact conversion, or explicitly revise/cancel/bind_manual an unwritten plan with CAS and user approval. Any chat of this profile; approvals.owner_only applies when enabled.', {**RUN, 'unit_id': STR, 'action': {'type': 'string', 'enum': ['resume', 'inspect', 'revise', 'cancel', 'bind_manual']}, 'expected_plan_revision': STR, 'target_task_id': STR, 'expected_revision': STR, 'edits': OBJ, 'reason': STR, 'user_approved': BOOL}, ['run_id', 'unit_id']),
 'discovery_link_audit': _schema('discovery_link_audit', 'Read-only dry-run audit of task links written by discovery conversions visible to this chat: latest occurrence per task/dossier, one marker pair and the expected revision line; optional workspace-relative legacy dossier folders are listed. Never writes or repairs.', {'legacy_roots': {'type': 'array', 'items': STR}}),
 'discovery_runs': _schema('discovery_runs', 'Backend API: list full run records or get exact run including research, proposals, conflicts, recovery and delivery.', {'run_id': STR}),
}

# Expose the actual structured callback contract to the model/provider. Keeping
# only payload:object hid all twenty required fields from the called tool.
# References resolve at the tool parameters root, not the nested payload root.
_child_contract = child_schema()
_submit_parameters = SCHEMAS['discovery_research_submit']['parameters']
_submit_parameters['$defs'] = copy.deepcopy(_child_contract['$defs'])
_submit_parameters['properties']['payload'] = {
    key: copy.deepcopy(value) for key, value in _child_contract.items()
    if key not in {'$schema', '$defs', '$id'}
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
    def config_call(a, session_id='', **_):
        action = a['action']
        if action == 'approvals':
            return service.configure_approvals(a['config'], session_id=session_id, user_approved=a.get('user_approved', False))
        if action != 'status': service.authorize_approval(session_id)
        if action == 'source':
            return service.configure(a['stream'], a['config'], user_approved=a.get('user_approved', False))
        if action == 'delivery':
            return service.configure_delivery(a['stream'], a['config'], user_approved=a.get('user_approved', False))
        if action == 'identity':
            return service.confirm_identity(a['account_key'], a['identity'], user_confirmed=a.get('user_approved', False))
        if action == 'status':
            return {'sources': ctx.state.get('discovery_sources', default={}), 'identities': ctx.state.get('discovery_identity_accounts', default={}), 'streams': ctx.state.get('streams', default={}), 'delivery': ctx.state.get('discovery_delivery', default={}), 'approvals': service.approval_settings()}
        raise UserError('unknown configuration action')
    def digest_call(a, session_id='', **_):
        ledger = service.store.get_run(a['run_id'])
        if session_id not in {ledger['origin'].get('session_id'), ledger['origin'].get('stream_origin_session')} and not service.origin_authorized(service._stream(ledger['config'].get('stream_name', ledger['stream'])), session_id):
            service.runner._parent(a['run_id'], session_id)
        action = a.get('action', 'prepare')
        if action == 'prepare': return service.finalize(a['run_id'], session_id=session_id)
        if action == 'get': return service.digest.get(a['run_id'])
        if action == 'delivery': return service.delivery_status(a['run_id'])
        if action == 'send':
            if ledger['config'].get('mode') != 'production': raise UserError('non-production run cannot send digest')
            return service.deliver(a['run_id'], session_id=session_id)
        raise UserError('unknown digest action')
    def conversion_recover(a, session_id='', **_):
        service.authorize_approval(session_id)
        action = a.get('action', 'resume')
        if action == 'inspect':
            plan = read_json(service.conversion._paths(a['run_id'], a['unit_id'])[0])
            return {'plan': plan, 'plan_revision': content_revision(plan) if plan else None}
        if action != 'resume':
            if a.get('user_approved') is not True:
                raise UserError('pending-plan changes require explicit user approval')
            params = {k: a[k] for k in ('expected_plan_revision', 'reason')}
            if action == 'revise': return service.conversion.revise(a['run_id'], a['unit_id'], edits=a.get('edits', {}), **params)
            if action == 'cancel': return service.conversion.cancel(a['run_id'], a['unit_id'], **params)
            if action == 'bind_manual': return service.conversion.bind_manual(a['run_id'], a['unit_id'], target_task_id=a['target_task_id'], expected_revision=a['expected_revision'], **params)
            raise UserError('unknown plan action')
        return service.conversion.deliver_git(a['run_id'], a['unit_id'])
    handlers.update({
        'discovery_replay': lambda a, session_id='', **_: service.replay(**a, session_id=session_id),
        'discovery_config': config_call,
        'discovery_digest': digest_call,
        'discovery_runs': lambda a, session_id='', **_: service.backend(**a, session_id=session_id),
        'discovery_link_audit': lambda a, session_id='', **_: service.link_audit(**a, session_id=session_id),
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
            except tf.ConcurrentEditError as exc:
                # Same stable code the dashboard uses; the parent re-reads with discovery_match and retries.
                return json.dumps({'ok': False, 'error': {'code': 'stale_revision', 'message': str(exc)[:1000] + '. The task changed; re-read it with discovery_match and decide again with the current revision.'}})
            except (UserError, ValueError, KeyError, TypeError, OSError) as exc:
                return json.dumps({'ok': False, 'error': str(exc)[:1000]})
        return call
    for name, schema in SCHEMAS.items():
        handler = handlers[name]
        ctx.register_tool(name=name, toolset='alchemy-task-discovery-child' if name in {'discovery_research_fetch', 'discovery_research_submit'} else 'alchemy-task-discovery',
                          schema=schema, handler=wrap(name, handler), description=schema['description'], emoji='🜍')
    for name, hook in make_hooks(service.runner).items():
        ctx.register_hook(name, hook)
