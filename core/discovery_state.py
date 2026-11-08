"""Profile-local discovery ledger and immutable full research resources.

No host/runtime imports, model calls, task mutations or delivery side effects.
The coordinator owns caller authentication, lifecycle observation and semantics.
"""
from __future__ import annotations
import contextlib
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterator
from .discovery_identity import UserError, _component, canonical_source_id, candidate_id, freeze_actions
from .discovery_research import (MAX_CANDIDATES, MAX_INDEX_BYTES, MAX_SOURCE_IDS,
    MAX_BUNDLE_BYTES, MAX_TITLE_CHARS, MAX_REASON_CHARS, _str, _privacy_walk,
    child_schema, extract_json, validate_bundle, validate_shape)
def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()

def atomic_write(path: Path, content: bytes, mode: int = 0o600, *, directory_mode: int | None = None) -> None:
    directory_mode = directory_mode if directory_mode is not None else (0o700 if mode == 0o600 else 0o755)
    path.parent.mkdir(parents=True, exist_ok=True, mode=directory_mode)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path); os.chmod(path, mode)
        dirfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)

def atomic_json(path: Path, value: Any) -> None:
    atomic_write(path, _json_bytes(value), 0o600, directory_mode=0o700)

def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text()) if path.exists() else default

def file_fingerprint(path: Path) -> dict[str, Any]:
    data = path.read_bytes(); st = path.stat()
    return {"sha256": hashlib.sha256(data).hexdigest(), "mtime_ns": st.st_mtime_ns}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _name(value: str) -> str:
    value = _component(value, 'state key')
    if value in {'.', '..'}:
        raise UserError('unsafe state key')
    return value


FENCED = {'launch_unknown', 'execution_unknown', 'admission_timeout', 'execution_timeout', 'cancelled', 'safety_hold'}
TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}
RETRY_STATES = {'rejected_retryable'}


class DiscoveryStore:
    """One profile's durable discovery truth. Pass its explicit data directory.

    All RMW operations take short cross-process locks. Never hold these locks
    around a model, network or lifecycle call. Resource contents and accepted
    commit intents are immutable; mutable workflow state lives in ledger.json.
    """

    def __init__(self, state_root: Path):
        self.state_root = Path(state_root)
        for name in ('', 'runs', 'locks', 'sources', 'budgets', 'reviews', 'tombstones'):
            path = self.state_root / name
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path, 0o700)

    @contextlib.contextmanager
    def _lock(self, name: str) -> Iterator[None]:
        path = self.state_root / 'locks' / (_hash(name.encode()) + '.lock')
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _run_lock_name(self, run_id: str) -> str:
        return 'run:' + _name(run_id)

    @contextlib.contextmanager
    def candidate_lock(self, run_id: str, cid: str) -> Iterator[None]:
        with self._lock('candidate:' + _name(run_id) + ':' + _name(cid)):
            yield

    def run_dir(self, run_id: str) -> Path:
        return self.state_root / 'runs' / _name(run_id)

    def _load(self, run_id: str, *, open_only: bool = False) -> dict[str, Any]:
        value = read_json(self.run_dir(run_id) / 'ledger.json')
        if value is None:
            value = read_json(self.state_root / 'tombstones' / (_name(run_id) + '.json'))
        if value is None:
            raise UserError('unknown run')
        if open_only and value['status'] == 'finalized':
            raise UserError('run is finalized; review is immutable')
        return value

    def _save(self, run_id: str, ledger: dict[str, Any]) -> None:
        if (self.state_root / 'tombstones' / (_name(run_id) + '.json')).exists():
            raise UserError('pruned run cannot be recreated by a late transition')
        ledger['revision'] += 1
        atomic_json(self.run_dir(run_id) / 'ledger.json', ledger)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._load(run_id)

    def init_run(self, run_id: str | None = None, *, stream: str = 'default', business_date: str = '', config: dict[str, Any] | None = None, schema_revision: str | None = None, origin: dict[str, Any] | None = None, lineage: dict[str, Any] | None = None) -> str:
        run_id = _name(run_id or uuid.uuid4().hex)
        _name(stream)
        config = copy.deepcopy(config or {})
        with self._lock(self._run_lock_name(run_id)):
            path = self.run_dir(run_id)
            if (self.state_root / 'tombstones' / (run_id + '.json')).exists():
                raise UserError('run was pruned; its tombstone is immutable')
            if (path / 'ledger.json').exists():
                old = self._load(run_id)
                if old['stream'] != stream or old['config'] != config or old['business_date'] != business_date:
                    raise UserError('run frozen configuration conflict')
                return run_id
            for directory in (path, path / 'resources', path / 'spool', path / 'research', path / 'commits', path / 'uploads'):
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(directory, 0o700)
            atomic_json(path / 'ledger.json', {'schema_version': 2, 'run_id': run_id, 'stream': stream, 'business_date': business_date, 'config': config, 'config_revision': _hash(_json_bytes(config)), 'schema_revision': schema_revision or _hash(_json_bytes(child_schema())), 'origin': copy.deepcopy(origin or {}), 'lineage': copy.deepcopy(lineage or {}), 'created': now(), 'status': 'open', 'revision': 1, 'index_revision': None, 'candidates': [], 'cohorts': [], 'attempts': {}, 'resources': {}, 'page_receipts': {}, 'start_events': {}, 'errors': [], 'action_registry': {}})
        return run_id

    def add_candidates(self, run_id: str, supplied_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Daily Store.add_candidates normalization, without a whole-run 200 cap.
        if not isinstance(supplied_items, list) or any(not isinstance(x, dict) for x in supplied_items):
            raise UserError('candidates input must be a list of objects')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            if ledger['index_revision']:
                raise UserError('candidate index is frozen')
            items = ledger['candidates']
            seen = {x['candidate_id'] for x in items}
            pending = []
            for supplied in supplied_items:
                unknown = set(supplied) - {'title', 'source_ids', 'prefilter_disposition', 'prefilter_reason', 'summary', 'due', 'priority', 'source_revision', 'source_key'}
                if unknown:
                    raise UserError(f'unknown candidate keys: {sorted(unknown)}')
                raw_sources = supplied.get('source_ids', [])
                if not isinstance(raw_sources, list) or len(raw_sources) > MAX_SOURCE_IDS:
                    raise UserError('source ID count exceeds shared limit')
                sources = sorted(set(canonical_source_id(x) for x in raw_sources))
                cid = candidate_id(sources)
                if cid in seen:
                    continue
                prefilter = supplied.get('prefilter_disposition', 'research')
                if prefilter not in {'research', 'excluded'}:
                    raise UserError('invalid prefilter disposition')
                title = _str(supplied.get('title') or 'Follow-up', 'title', allow_empty=False, limit=MAX_TITLE_CHARS)
                reason = _str(supplied.get('prefilter_reason', ''), 'prefilter_reason', limit=MAX_REASON_CHARS)
                item = {'candidate_id': cid, 'run_id': run_id, 'occurrence_id': f'{run_id}:{cid}', 'input_index': len(items) + len(pending), 'title': title, 'source_ids': sources, 'prefilter_disposition': prefilter, 'prefilter_reason': reason, 'state': 'proposed', 'created': now(), 'updated': now()}
                for key in ('summary', 'due', 'priority', 'source_revision', 'source_key'):
                    if key in supplied:
                        item[key] = _str(supplied[key], key)
                _privacy_walk(item)
                pending.append(item)
                seen.add(cid)
            ledger['candidates'] = [*items, *pending]
            self._save(run_id, ledger)
            return ledger['candidates']

    def candidate_index(self, run_id: str, cohort: int | None = None) -> list[dict[str, Any]]:
        ledger = self._load(run_id)
        items = [x for x in ledger['candidates'] if not x.get('parent_candidate_id')]
        if cohort is not None:
            ids = set(ledger['cohorts'][cohort]['candidate_ids'])
            items = [x for x in items if x['candidate_id'] in ids]
        return [{key: item[key] for key in ('candidate_id', 'title', 'source_ids', 'prefilter_disposition')} for item in items]

    def get_candidate(self, run_id: str, cid: str) -> dict[str, Any]:
        return self._candidate(self._load(run_id), cid)

    @staticmethod
    def _candidate(ledger: dict[str, Any], cid: str) -> dict[str, Any]:
        found = [x for x in ledger['candidates'] if x['candidate_id'] == cid]
        if len(found) != 1:
            raise UserError('unknown or ambiguous candidate occurrence')
        return found[0]

    def _put_resource_locked(self, run_id: str, ledger: dict[str, Any], name: str, content: Any) -> dict[str, Any]:
        name = _name(name)
        data = content.encode('utf-8') if isinstance(content, str) else _json_bytes(content)
        digest = _hash(data)
        old = ledger['resources'].get(name)
        if old and old['sha256'] != digest:
            raise UserError('immutable resource revision conflict')
        info = {'name': name, 'sha256': digest, 'total_bytes': len(data), 'entry_count': len(content) if isinstance(content, (list, dict)) else None}
        path = self.run_dir(run_id) / 'resources' / digest
        if path.exists() and path.read_bytes() != data:
            raise UserError('resource hash conflict')
        if not path.exists():
            atomic_write(path, data)
        ledger['resources'][name] = info
        return info

    def put_resource(self, run_id: str, name: str, content: Any) -> dict[str, Any]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            info = self._put_resource_locked(run_id, ledger, name, content)
            self._save(run_id, ledger)
            return info

    def resource_info(self, run_id: str, name: str) -> dict[str, Any]:
        try:
            return self._load(run_id)['resources'][_name(name)]
        except KeyError:
            raise UserError('unknown resource') from None

    def freeze_index(self, run_id: str, *, rubric: str) -> dict[str, Any]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            if ledger['index_revision']:
                return {'index_revision': ledger['index_revision'], 'cohorts': ledger['cohorts']}
            index = [{key: x[key] for key in ('candidate_id', 'title', 'source_ids', 'prefilter_disposition')} for x in ledger['candidates']]
            chunks, current = [], []
            for item in index:
                if len(_json_bytes([item])) > MAX_INDEX_BYTES:
                    raise UserError('individual candidate index exceeds shared byte limit; retain deferred')
                if current and (len(current) >= MAX_CANDIDATES or len(_json_bytes([*current, item])) > MAX_INDEX_BYTES):
                    chunks.append(current)
                    current = []
                current.append(item)
            if current:
                chunks.append(current)
            for number, chunk in enumerate(chunks):
                info = self._put_resource_locked(run_id, ledger, f'index-{number}', chunk)
                ledger['cohorts'].append({'number': number, 'candidate_ids': [x['candidate_id'] for x in chunk], **info})
            manifest = {'config_revision': ledger['config_revision'], 'candidates': index, 'cohorts': ledger['cohorts']}
            ledger['index_revision'] = self._put_resource_locked(run_id, ledger, 'manifest', manifest)['sha256']
            schema_info = self._put_resource_locked(run_id, ledger, 'schema', child_schema())
            if schema_info['sha256'] != ledger['schema_revision']:
                raise UserError('frozen schema revision mismatch')
            self._put_resource_locked(run_id, ledger, 'rubric', rubric)
            self._publish_outcomes_locked(run_id, ledger)
            for item in ledger['candidates']:
                self._put_resource_locked(run_id, ledger, 'assignment-' + item['candidate_id'], {**item, 'config': ledger['config'], 'config_revision': ledger['config_revision'], 'index_revision': ledger['index_revision'], 'schema_revision': ledger['schema_revision']})
            self._save(run_id, ledger)
            return {'index_revision': ledger['index_revision'], 'cohorts': ledger['cohorts']}

    def _publish_outcomes_locked(self, run_id: str, ledger: dict[str, Any]) -> dict[str, Any]:
        outcomes = [{'workstream_id': x['candidate_id'], 'parent_candidate_id': x['parent_candidate_id'], 'action_id': x.get('action_id'), 'source_ids': x['source_ids'], 'disposition': x['research_disposition']} for x in ledger['candidates'] if x.get('parent_candidate_id')]
        digest = _hash(_json_bytes(outcomes))
        info = self._put_resource_locked(run_id, ledger, 'outcomes-' + digest[:24], outcomes)
        ledger['outcome_resource'] = info
        return info

    def fetch_resource(self, run_id: str, name: str, *, revision: str, reader: str, cursor: str | None = None, limit: int = 8192) -> dict[str, Any]:
        if type(limit) is not int or not 4 <= limit <= 16384:
            raise UserError('resource byte limit must be 4..16384')
        _name(reader)
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            info = ledger['resources'].get(_name(name))
            if not info or info['sha256'] != revision:
                raise UserError('stale or unknown resource revision')
            if reader in ledger['attempts']:
                self._live_attempt(ledger, reader)
            offset = 0
            if cursor:
                try:
                    bound, raw_offset = cursor.split(':')
                    offset = int(raw_offset)
                except (ValueError, TypeError):
                    raise UserError('invalid resource cursor') from None
                if bound != _hash(f'{name}:{revision}:{reader}'.encode())[:24]:
                    raise UserError('cursor binding conflict')
            data = (self.run_dir(run_id) / 'resources' / revision).read_bytes()
            if _hash(data) != revision or offset < 0 or offset > len(data):
                raise UserError('resource content or offset conflict')
            end = min(offset + limit, len(data))
            while end < len(data) and data[end] & 0xC0 == 0x80:
                end -= 1
            try:
                content = data[offset:end].decode('utf-8')
            except UnicodeDecodeError:
                raise UserError('cursor is not a UTF-8 boundary') from None
            receipts = ledger['page_receipts'].setdefault(reader, {}).setdefault(name, {'revision': revision, 'ranges': []})
            if receipts['revision'] != revision:
                raise UserError('reader revision conflict')
            pair = [offset, end]
            if pair not in receipts['ranges']:
                receipts['ranges'].append(pair)
            self._save(run_id, ledger)
            more = end < len(data)
            next_cursor = _hash(f'{name}:{revision}:{reader}'.encode())[:24] + ':' + str(end) if more else None
            return {**info, 'content': content, 'offset': offset, 'end': end, 'page_sha256': _hash(data[offset:end]), 'next_cursor': next_cursor, 'has_more': more}

    @staticmethod
    def _has_pages(ledger: dict[str, Any], reader: str, name: str) -> bool:
        resource = ledger['resources'].get(name)
        receipt = ledger['page_receipts'].get(reader, {}).get(name)
        if not resource or not receipt or resource['sha256'] != receipt['revision']:
            return False
        boundary = 0
        for start, end in sorted(receipt['ranges']):
            if start > boundary:
                return False
            boundary = max(boundary, end)
        return boundary == resource['total_bytes']

    def reserve_attempt(self, run_id: str, cid: str, *, owner_session: str, daily_limit: int = 50) -> dict[str, Any]:
        if type(daily_limit) is not int or daily_limit < 0:
            raise UserError('daily limit must be non-negative')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            item = self._candidate(ledger, cid)
            if not ledger['index_revision'] or item.get('parent_candidate_id') or item['prefilter_disposition'] != 'research' or item.get('decomposition_state') == 'complete':
                raise UserError('candidate is not eligible for a fresh attempt')
            previous = [a for a in ledger['attempts'].values() if a['candidate_id'] == cid]
            if len(previous) >= 2 or previous and previous[-1]['state'] not in RETRY_STATES:
                raise UserError('attempt budget exhausted, active, held or unknown')
            budget_key = f"{ledger['stream']}:{ledger['business_date']}"
            with self._lock('budget:' + budget_key):
                path = self.state_root / 'budgets' / (_hash(budget_key.encode()) + '.json')
                budget = read_json(path, {'charged': []})
                unit = f'{run_id}:{cid}'
                if unit not in budget['charged']:
                    if len(budget['charged']) >= daily_limit:
                        raise UserError('daily research budget deferred')
                    budget['charged'].append(unit)
                    atomic_json(path, budget)
            cohort = next(x for x in ledger['cohorts'] if cid in x['candidate_ids'])
            token = secrets.token_hex(24)
            attempt = {'token': token, 'correlation_id': uuid.uuid4().hex, 'run_id': run_id, 'candidate_id': cid, 'ordinal': len(previous) + 1, 'owner_session': _str(owner_session, 'owner session', allow_empty=False), 'config_revision': ledger['config_revision'], 'index_revision': ledger['index_revision'], 'schema_revision': ledger['schema_revision'], 'source_revision': item.get('source_revision'), 'rubric_revision': ledger['resources']['rubric']['sha256'], 'required_resources': ['manifest', cohort['name'], 'schema', 'rubric', 'assignment-' + cid], 'state': 'launch_intent', 'created': now(), 'fenced': False, 'handle': None, 'child_session': None, 'payload': None, 'terminal': None, 'assessment': None, 'evidence': {'execution': 'intent', 'shape': 'not_checked', 'helper': 'not_checked', 'semantic': 'not_reviewed', 'acceptance': 'not_committed'}}
            attempt['outcome_revision'] = ledger['outcome_resource']['sha256']
            attempt['required_resources'].append(ledger['outcome_resource']['name'])
            ledger['attempts'][token] = attempt
            self._save(run_id, ledger)
            return attempt

    def get_attempt(self, run_id: str, token: str) -> dict[str, Any]:
        ledger = self._load(run_id)
        if token not in ledger['attempts']:
            raise UserError('unknown attempt')
        return ledger['attempts'][token]

    @staticmethod
    def _live_attempt(ledger: dict[str, Any], token: str, *, check_deadline: bool = True) -> dict[str, Any]:
        attempt = ledger['attempts'].get(token)
        if not attempt or attempt['fenced'] or attempt['state'] in FENCED:
            raise UserError('unknown or fenced attempt')
        deadline = attempt.get('deadline_utc')
        if check_deadline and deadline and dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(deadline):
            raise UserError('attempt deadline passed')
        return attempt

    def record_start(self, run_id: str, *, parent_session: str, child_session: str, subagent_id: str) -> None:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            event = {'parent_session': parent_session, 'child_session': child_session, 'subagent_id': subagent_id}
            old = ledger['start_events'].get(subagent_id)
            if old and old != event:
                raise UserError('contradictory start binding')
            ledger['start_events'][subagent_id] = event
            # Complete exact handle/start joins even when start arrives second.
            for attempt in ledger['attempts'].values():
                if attempt['handle'] and attempt['handle'].get('subagent_id') == subagent_id:
                    if attempt['owner_session'] != parent_session:
                        raise UserError('start parent binding conflict')
                    attempt['child_session'] = child_session
            self._save(run_id, ledger)

    def bind_attempt(self, run_id: str, token: str, handle: dict[str, Any], *, owner_session: str) -> dict[str, Any]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            attempt = self._live_attempt(ledger, token)
            if attempt['owner_session'] != owner_session or not isinstance(handle, dict) or not isinstance(handle.get('subagent_id'), str):
                raise UserError('handle owner binding conflict')
            if attempt['handle'] and attempt['handle'] != handle:
                raise UserError('immutable handle binding conflict')
            if any(x['token'] != token and x['handle'] and x['handle'].get('subagent_id') == handle['subagent_id'] for x in ledger['attempts'].values()):
                raise UserError('handle already bound to another attempt')
            attempt['handle'] = copy.deepcopy(handle)
            event = ledger['start_events'].get(handle['subagent_id'])
            if event:
                if event['parent_session'] != owner_session:
                    raise UserError('start event parent mismatch')
                attempt['child_session'] = event['child_session']
            if attempt['state'] == 'launch_intent':
                attempt['state'] = 'handle_bound'
            self._save(run_id, ledger)
            return attempt

    def authorize_attempt(self, run_id: str, token: str, *, child_session: str, subagent_id: str | None = None) -> dict[str, Any]:
        attempt = self._live_attempt(self._load(run_id), token)
        if not attempt['handle'] or not attempt['child_session'] or child_session != attempt['child_session'] or subagent_id is not None and subagent_id != attempt['handle']['subagent_id']:
            raise UserError('caller identity is not exactly bound; quarantine required')
        return attempt

    def mark_running(self, run_id: str, token: str, *, started_at: str, deadline_utc: str) -> dict[str, Any]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            attempt = self._live_attempt(ledger, token)
            if not attempt['handle']:
                raise UserError('running requires handle')
            if attempt.get('started_at') and (attempt['started_at'] != started_at or attempt['deadline_utc'] != deadline_utc):
                raise UserError('execution start/deadline is immutable')
            if dt.datetime.fromisoformat(started_at).tzinfo is None or dt.datetime.fromisoformat(deadline_utc).tzinfo is None:
                raise UserError('execution dates require timezone')
            attempt.update(started_at=started_at, deadline_utc=deadline_utc, state='RUNNING')
            self._save(run_id, ledger)
            return attempt

    def fence_attempt(self, run_id: str, token: str, *, reason: str, cancellation: dict[str, Any] | None = None) -> dict[str, Any]:
        if reason not in FENCED:
            raise UserError('invalid fence reason')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            attempt = ledger['attempts'].get(token)
            if not attempt:
                raise UserError('unknown attempt')
            if attempt['state'] == 'accepted_bundle':
                raise UserError('accepted attempt cannot be fenced')
            attempt.update(fenced=True, state=reason, fence_reason=reason, cancellation=copy.deepcopy(cancellation), fenced_at=now())
            self._save(run_id, ledger)
            return attempt

    def recover_owner(self, run_id: str, *, owner_session: str, owner_restarted: bool = False) -> list[str]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            fenced = []
            for attempt in ledger['attempts'].values():
                if attempt['terminal'] or attempt['fenced'] or attempt['state'] in {'accepted_bundle', 'rejected_retryable', 'exhausted'}:
                    continue
                if owner_restarted or attempt['owner_session'] != owner_session:
                    attempt.update(state='execution_unknown' if attempt['handle'] else 'launch_unknown', fenced=True, fenced_at=now())
                    fenced.append(attempt['token'])
            self._save(run_id, ledger)
            return fenced

    def observe_terminal(self, run_id: str, token: str, *, state: str, receipt: dict[str, Any]) -> dict[str, Any]:
        if state not in TERMINAL:
            raise UserError('not a terminal lifecycle state')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            attempt = ledger['attempts'].get(token)
            if not attempt:
                raise UserError('unknown attempt')
            terminal = {'state': state, 'receipt': copy.deepcopy(receipt), 'sha256': _hash(_json_bytes(receipt))}
            if attempt['terminal'] and attempt['terminal'] != terminal:
                raise UserError('terminal evidence conflict')
            attempt['terminal'] = terminal
            attempt['evidence']['execution'] = 'terminal_observed'
            if not attempt['fenced'] and attempt['state'] not in {'accepted_bundle', 'rejected_retryable', 'exhausted'}:
                attempt['state'] = 'terminal_observed'
            self._save(run_id, ledger)
            return attempt

    def reject_attempt(self, run_id: str, token: str, *, reason: str, retryable: bool, semantic: bool = False) -> dict[str, Any]:
        reason = _str(reason, 'rejection reason', allow_empty=False, limit=500)
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            attempt = ledger['attempts'].get(token)
            if not attempt or not attempt['terminal'] or attempt['state'] == 'accepted_bundle':
                raise UserError('rejection requires terminal unaccepted attempt')
            attempt.update(state='rejected_retryable' if retryable and attempt['ordinal'] < 2 else 'exhausted', rejection={'reason': reason, 'retryable': bool(retryable), 'semantic': semantic})
            if semantic:
                attempt['evidence']['semantic'] = 'rejected'
            self._save(run_id, ledger)
            return attempt

    def _spool_locked(self, run_id: str, ledger: dict[str, Any], token: str, payload: Any) -> dict[str, Any]:
        attempt = ledger['attempts'].get(token)
        if not attempt or type(payload) not in {dict, str}:
            raise UserError('unknown attempt or invalid payload type')
        transport = payload.encode('utf-8') if isinstance(payload, str) else _json_bytes(payload)
        if len(transport) > MAX_BUNDLE_BYTES:
            raise UserError('serialized research bundle exceeds shared limit')
        parse_error = None
        try:
            parsed = extract_json(payload)
        except UserError as exc:
            parsed = None
            parse_error = str(exc)[:500]
        data = transport if parsed is None else _json_bytes(parsed)
        if len(data) > MAX_BUNDLE_BYTES:
            raise UserError('serialized research bundle exceeds shared limit')
        digest = _hash(data)
        if attempt['payload']:
            if attempt['payload']['payload_sha256'] != digest or attempt['payload']['transport_sha256'] != _hash(transport):
                raise UserError('committed payload is immutable')
            return attempt['payload']
        self._live_attempt(ledger, token)
        if ledger['status'] == 'finalized':
            raise UserError('run is finalized; new payloads are forbidden')
        if attempt['state'] in {'rejected_retryable', 'exhausted'} or attempt['terminal'] and attempt['terminal']['state'] != 'SUCCEEDED':
            raise UserError('closed attempt cannot submit new payload')
        if not attempt['child_session']:
            raise UserError('unbound callback must be quarantined')
        if any(not self._has_pages(ledger, token, name) for name in attempt['required_resources']):
            raise UserError('child must fetch all frozen resource pages')
        resource = 'payload-' + token
        self._put_resource_locked(run_id, ledger, resource, payload if parsed is None else parsed)
        self._put_resource_locked(run_id, ledger, 'transport-' + token, transport.decode('utf-8'))
        receipt = {'run_id': run_id, 'candidate_id': attempt['candidate_id'], 'token': token, 'payload_sha256': digest, 'transport_sha256': _hash(transport), 'parsed': parsed is not None, 'resource': resource, 'total_bytes': len(data)}
        atomic_write(self.run_dir(run_id) / 'spool' / (token + '.json'), data)
        attempt['payload'] = receipt
        attempt['state'] = 'submitted' if not attempt['terminal'] else 'terminal_observed'
        # Full invalid payload remains an audit resource, not accepted research.
        try:
            if parse_error:
                raise UserError(parse_error)
            validate_shape(parsed)
        except UserError as exc:
            attempt['validation_error'] = str(exc)[:500]
            attempt['evidence'].update(shape='rejected', helper='not_checked')
        else:
            attempt['evidence']['shape'] = 'valid'
            try:
                self._validate_for_attempt(ledger, attempt, parsed)
            except UserError as exc:
                attempt['validation_error'] = str(exc)[:500]
                attempt['evidence']['helper'] = 'rejected'
            else:
                attempt.pop('validation_error', None)
                attempt['evidence']['helper'] = 'valid'
        atomic_json(self.run_dir(run_id) / 'spool' / (token + '.receipt.json'), receipt)
        self._save(run_id, ledger)
        return receipt

    def spool_payload(self, run_id: str, token: str, payload: Any) -> dict[str, Any]:
        with self._lock(self._run_lock_name(run_id)):
            return self._spool_locked(run_id, self._load(run_id), token, payload)

    def recover_spools(self, run_id: str) -> list[dict[str, Any]]:
        """Recover full committed callbacks, never infer terminal execution.

        Bytes without a committed receipt remain unaccepted audit orphans. A
        fenced callback can be recovered as evidence but cannot become accepted.
        """
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            recovered = []
            changed = False
            for path in sorted((self.run_dir(run_id) / 'spool').glob('*.receipt.json')):
                receipt = read_json(path)
                token = receipt['token']
                attempt = ledger['attempts'].get(token)
                if not attempt or receipt['run_id'] != run_id or receipt['candidate_id'] != attempt['candidate_id'] or not attempt['child_session'] or path.name != token + '.receipt.json':
                    raise UserError('spool receipt binding conflict')
                data = (self.run_dir(run_id) / 'spool' / (token + '.json')).read_bytes()
                transport = (self.run_dir(run_id) / 'resources' / receipt['transport_sha256']).read_bytes()
                if len(data) > MAX_BUNDLE_BYTES or len(transport) > MAX_BUNDLE_BYTES or _hash(data) != receipt['payload_sha256'] or _hash(transport) != receipt['transport_sha256'] or len(data) != receipt['total_bytes']:
                    raise UserError('committed spool bytes/hash mismatch')
                if attempt['payload']:
                    if attempt['payload'] != receipt:
                        raise UserError('spool receipt and ledger disagree')
                    recovered.append(receipt)
                    continue
                text = data.decode('utf-8')
                payload = extract_json(text) if receipt['parsed'] else text
                info = self._put_resource_locked(run_id, ledger, receipt['resource'], payload)
                if info['sha256'] != receipt['payload_sha256']:
                    raise UserError('reconstructed spool hash mismatch')
                self._put_resource_locked(run_id, ledger, 'transport-' + token, transport.decode('utf-8'))
                attempt['payload'] = receipt
                if not attempt['fenced']:
                    attempt['state'] = 'terminal_observed' if attempt['terminal'] else 'submitted'
                try:
                    if not receipt['parsed']:
                        raise UserError('malformed committed JSON text')
                    validate_shape(payload)
                except UserError as exc:
                    attempt['validation_error'] = str(exc)[:500]
                    attempt['evidence'].update(shape='rejected', helper='not_checked')
                else:
                    attempt['evidence']['shape'] = 'valid'
                    try:
                        self._validate_for_attempt(ledger, attempt, payload)
                    except UserError as exc:
                        attempt['validation_error'] = str(exc)[:500]
                        attempt['evidence']['helper'] = 'rejected'
                    else:
                        attempt['evidence']['helper'] = 'valid'
                recovered.append(receipt)
                changed = True
            if changed:
                self._save(run_id, ledger)
            return recovered

    @staticmethod
    def _validate_for_attempt(ledger: dict[str, Any], attempt: dict[str, Any], payload: Any) -> list[tuple[str, dict[str, Any], list[str]]]:
        cid = attempt['candidate_id']
        item = DiscoveryStore._candidate(ledger, cid)
        cohort = next(x for x in ledger['cohorts'] if cid in x['candidate_ids'])
        others = {x['candidate_id']: x['source_ids'] for x in ledger['candidates'] if x['candidate_id'] in cohort['candidate_ids'] and x['candidate_id'] != cid and x['prefilter_disposition'] == 'research'}
        return validate_bundle(payload, cid, item['source_ids'], other_sources=others, action_registry=ledger['action_registry'].get(cid))

    def freeze_action_registry(self, run_id: str, cid: str, anchors: list[dict[str, str]]) -> list[dict[str, Any]]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            item = self._candidate(ledger, cid)
            registry = freeze_actions(cid, item['source_ids'], anchors, existing=ledger['action_registry'].get(cid))
            ledger['action_registry'][cid] = registry
            self._save(run_id, ledger)
            return registry

    def begin_upload(self, run_id: str, token: str, *, total_bytes: int, sha256: str, part_count: int) -> dict[str, Any]:
        if type(total_bytes) is not int or not 1 <= total_bytes <= MAX_BUNDLE_BYTES or type(part_count) is not int or not 1 <= part_count <= 1024 or not re.fullmatch(r'[a-f0-9]{64}', sha256):
            raise UserError('invalid upload declaration')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            attempt = self._live_attempt(ledger, token)
            upload = {'total_bytes': total_bytes, 'sha256': sha256, 'part_count': part_count, 'parts': {}}
            if attempt.get('upload'):
                if any(attempt['upload'][k] != upload[k] for k in ('total_bytes', 'sha256', 'part_count')):
                    raise UserError('upload declaration conflict')
                return attempt['upload']
            attempt['upload'] = upload
            self._save(run_id, ledger)
            return upload

    def upload_part(self, run_id: str, token: str, *, index: int, content: str) -> dict[str, Any]:
        if type(index) is not int or type(content) is not str or len(content.encode('utf-8')) > 16384:
            raise UserError('upload part must be indexed text up to 16 KiB')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            attempt = self._live_attempt(ledger, token)
            upload = attempt.get('upload')
            if not upload or not 0 <= index < upload['part_count']:
                raise UserError('upload part outside declaration')
            data = content.encode('utf-8')
            info = {'sha256': _hash(data), 'bytes': len(data)}
            key = str(index)
            if key in upload['parts'] and upload['parts'][key] != info:
                raise UserError('immutable upload part conflict')
            prospective = {**upload['parts'], key: info}
            if sum(x['bytes'] for x in prospective.values()) > upload['total_bytes']:
                raise UserError('upload exceeds declared bound')
            atomic_write(self.run_dir(run_id) / 'uploads' / (token + '-' + key), data)
            upload['parts'] = prospective
            self._save(run_id, ledger)
            return info

    def commit_upload(self, run_id: str, token: str) -> dict[str, Any]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            attempt = self._live_attempt(ledger, token)
            upload = attempt.get('upload')
            if not upload or set(upload['parts']) != {str(i) for i in range(upload['part_count'])}:
                raise UserError('incomplete upload parts')
            chunks = []
            for index in range(upload['part_count']):
                data = (self.run_dir(run_id) / 'uploads' / (token + '-' + str(index))).read_bytes()
                if _hash(data) != upload['parts'][str(index)]['sha256']:
                    raise UserError('upload part hash mismatch')
                chunks.append(data)
            data = b''.join(chunks)
            if len(data) != upload['total_bytes'] or _hash(data) != upload['sha256']:
                raise UserError('upload total/hash mismatch')
            return self._spool_locked(run_id, ledger, token, data.decode('utf-8'))

    def accept_attempt(self, run_id: str, token: str, *, payload_sha256: str, assessment: dict[str, Any], reader: str) -> dict[str, Any]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            attempt = self._live_attempt(ledger, token, check_deadline=False)
            if attempt['state'] in {'rejected_retryable', 'exhausted'}:
                raise UserError('rejected attempt requires a fresh child, not changed acceptance')
            if not attempt['terminal'] or attempt['terminal']['state'] != 'SUCCEEDED' or not attempt['payload']:
                raise UserError('acceptance requires completed successful execution and saved full payload')
            if not attempt['payload']['parsed']:
                raise UserError('malformed full payload is audit evidence, not acceptable research')
            if payload_sha256 != attempt['payload']['payload_sha256']:
                raise UserError('semantic assessment payload binding conflict')
            if not self._has_pages(ledger, reader, attempt['payload']['resource']):
                raise UserError('parent must fetch all payload pages')
            if not isinstance(assessment, dict) or assessment.get('accepted') is not True or not isinstance(assessment.get('reason'), str) or not assessment['reason'].strip() or len(assessment['reason']) > 500:
                raise UserError('substantive parent semantic assessment required')
            payload = read_json(self.run_dir(run_id) / 'spool' / (token + '.json'))
            if _hash(_json_bytes(payload)) != payload_sha256:
                raise UserError('spool hash conflict')
            units = self._validate_for_attempt(ledger, attempt, payload)
            intent = {'run_id': run_id, 'candidate_id': attempt['candidate_id'], 'token': token, 'bundle_sha256': payload_sha256, 'units': units, 'assessment': copy.deepcopy(assessment)}
            path = self.run_dir(run_id) / 'commits' / (attempt['candidate_id'] + '.intent.json')
            old = read_json(path)
            if old and old != json.loads(json.dumps(intent)):
                raise UserError('accepted bundle intent is immutable')
            if not old:
                atomic_json(path, intent)
            return self._materialize_bundle_locked(run_id, ledger, intent)

    def _materialize_bundle_locked(self, run_id: str, ledger: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
        cid = intent['candidate_id']
        parent = self._candidate(ledger, cid)
        marker_path = self.run_dir(run_id) / 'research' / (cid + '.bundle.json')
        marker = {'candidate_id': cid, 'bundle_sha256': intent['bundle_sha256'], 'workstream_ids': [x[0] for x in intent['units']]}
        old = read_json(marker_path)
        if old and old != marker:
            raise UserError('accepted research bundle is immutable')
        if old:
            if parent.get('workstream_ids') != marker['workstream_ids'] or ledger['attempts'][intent['token']]['state'] != 'accepted_bundle':
                raise UserError('commit marker and ledger disagree')
            for wid, payload, _ in intent['units']:
                if read_json(self.run_dir(run_id) / 'research' / (wid + '.json')) != payload:
                    raise UserError('committed research unit content conflict')
            return old
        # Validate every collision before writing the first unit (daily parity).
        for wid, payload, canonical in intent['units']:
            matches = [x for x in ledger['candidates'] if x['candidate_id'] == wid]
            previous = read_json(self.run_dir(run_id) / 'research' / (wid + '.json'))
            if matches and matches[0].get('parent_candidate_id') != cid:
                raise UserError('workstream identity collision')
            if previous is not None and previous != payload:
                raise UserError('partially recorded workstream is immutable')
        for wid, payload, canonical in intent['units']:
            atomic_json(self.run_dir(run_id) / 'research' / (wid + '.json'), payload)
            if not any(x['candidate_id'] == wid for x in ledger['candidates']):
                ledger['candidates'].append({'candidate_id': wid, 'run_id': run_id, 'occurrence_id': f'{run_id}:{wid}', 'input_index': len(ledger['candidates']), 'title': payload['title'], 'source_ids': canonical, 'parent_candidate_id': cid, 'prefilter_disposition': 'research', 'state': 'proposed', 'research_status': payload['status'], 'research_disposition': payload['disposition'], 'eligible_research': payload['status'] == 'complete' and payload['disposition'] in {'retain', 'uncertain'}, 'action_id': payload.get('action_id')})
        parent.update(decomposition_state='complete', workstream_ids=marker['workstream_ids'])
        attempt = ledger['attempts'][intent['token']]
        attempt.update(state='accepted_bundle', assessment=intent['assessment'])
        attempt['evidence'].update(shape='valid', helper='valid', semantic='accepted', acceptance='committed')
        self._publish_outcomes_locked(run_id, ledger)
        self._save(run_id, ledger)
        atomic_json(marker_path, marker)
        return marker

    def recover_bundles(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            return [self._materialize_bundle_locked(run_id, ledger, read_json(path)) for path in sorted((self.run_dir(run_id) / 'commits').glob('*.intent.json'))]

    def accepted_bundle(self, run_id: str, cid: str) -> dict[str, Any] | None:
        return read_json(self.run_dir(run_id) / 'research' / (_name(cid) + '.bundle.json'))

    def research_for(self, run_id: str, wid: str) -> dict[str, Any]:
        item = self.get_candidate(run_id, wid)
        if not item.get('parent_candidate_id') or not self.accepted_bundle(run_id, item['parent_candidate_id']):
            raise UserError('research bundle not committed')
        return read_json(self.run_dir(run_id) / 'research' / (_name(wid) + '.json'))

    def record_failure(self, run_id: str, cid: str, operation: str, reason: str, *, attempt_count: int | None = None, failure_category: str = 'unknown') -> dict[str, Any]:
        reason = _str(reason, 'failure reason', allow_empty=False, limit=500).replace('\n', ' ')
        _privacy_walk({'reason': reason})
        if attempt_count is not None and (type(attempt_count) is not int or not 1 <= attempt_count <= 2):
            raise UserError('attempt count must be 1 or 2')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            item = self._candidate(ledger, cid)
            error = {'occurrence_id': item['occurrence_id'], 'operation': _name(operation), 'reason': reason, 'attempt_count': attempt_count, 'failure_category': _name(failure_category), 'at': now()}
            ledger['errors'].append(error)
            item.update(state='recoverable_failure', last_completed_state=item.get('last_completed_state', item['state']), failed_operation=operation)
            self._save(run_id, ledger)
            return error

    def _source_path(self, stream: str, source: str) -> Path:
        return self.state_root / 'sources' / (_hash((_name(stream) + ':' + _name(source)).encode()) + '.json')

    def source_state(self, stream: str, source: str) -> dict[str, Any]:
        return read_json(self._source_path(stream, source), {'backlog': [], 'coverage': []})

    def enqueue_backlog(self, stream: str, source: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock('source:' + _name(stream) + ':' + _name(source)):
            state = self.source_state(stream, source)
            seen = {x['backlog_id'] for x in state['backlog']}
            for supplied in entries:
                sources = sorted(set(canonical_source_id(x) for x in supplied['source_ids']))
                if not sources or not isinstance(supplied.get('source_revision'), str):
                    raise UserError('backlog requires stable sources and revision')
                bid = _hash(_json_bytes([sources, supplied['source_revision']]))
                if bid not in seen:
                    state['backlog'].append({**copy.deepcopy(supplied), 'source_ids': sources, 'backlog_id': bid, 'status': 'queued'})
                    seen.add(bid)
            atomic_json(self._source_path(stream, source), state)
            return state

    def update_backlog(self, stream: str, source: str, backlog_id: str, *, status: str, lineage: dict[str, Any]) -> dict[str, Any]:
        if status not in {'queued', 'selected', 'deferred', 'blocked', 'accepted', 'excluded', 'resolved'} or not isinstance(lineage, dict):
            raise UserError('invalid backlog status or lineage')
        with self._lock('source:' + _name(stream) + ':' + _name(source)):
            state = self.source_state(stream, source)
            found = [x for x in state['backlog'] if x['backlog_id'] == backlog_id]
            if len(found) != 1:
                raise UserError('unknown backlog identity')
            item = found[0]
            if item['status'] in {'accepted', 'excluded', 'resolved'} and (item['status'] != status or item.get('lineage') != lineage):
                raise UserError('terminal backlog lineage is immutable; new source activity needs a new revision')
            item.update(status=status, lineage=copy.deepcopy(lineage))
            atomic_json(self._source_path(stream, source), state)
            return item

    def record_coverage(self, stream: str, source: str, receipt: dict[str, Any]) -> dict[str, Any]:
        if receipt.get('status') not in {'complete', 'partial', 'failed', 'unsupported'} or receipt.get('verification') not in {'agent_attested', 'adapter_verified'}:
            raise UserError('explicit coverage status and verification required')
        with self._lock('source:' + _name(stream) + ':' + _name(source)):
            state = self.source_state(stream, source)
            state['coverage'].append(copy.deepcopy(receipt))
            # Adapter validates account/window/contiguity. Never promote attestation.
            if receipt['status'] == 'complete' and receipt['verification'] == 'adapter_verified' and receipt.get('pagination_exhausted') is True:
                ids = {x['backlog_id'] for x in state['backlog']}
                if not isinstance(receipt.get('backlog_ids'), list) or not set(receipt['backlog_ids']) <= ids or not isinstance(receipt.get('end'), str):
                    raise UserError('coverage requires durable backlog identity receipt')
                state['watermark'] = receipt['end']
            atomic_json(self._source_path(stream, source), state)
            return state

    def save_review(self, run_id: str, review: dict[str, Any]) -> dict[str, Any]:
        """Freeze caller-built review. Coordinator must enforce its full join."""
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            if 'review' in ledger:
                if ledger['review'] != review:
                    raise UserError('review is immutable')
                path = self.state_root / 'reviews' / (run_id + '.json')
                if not path.exists():
                    atomic_json(path, review)
                elif read_json(path) != review:
                    raise UserError('review projection conflict')
                return copy.deepcopy(review)
            ledger['review'] = copy.deepcopy(review)
            ledger['status'] = 'finalized'
            self._save(run_id, ledger)
            atomic_json(self.state_root / 'reviews' / (run_id + '.json'), review)
            return review

    def claim_lease(self, run_id: str, *, owner: str, expires_at: str) -> dict[str, Any]:
        """Short supervisor claim; an expired claim does not release attempts."""
        expiry = dt.datetime.fromisoformat(expires_at)
        if expiry.tzinfo is None or expiry <= dt.datetime.now(dt.timezone.utc):
            raise UserError('lease expiry must be in the future with timezone')
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            lease = ledger.get('lease')
            if lease and lease['owner'] != owner and dt.datetime.fromisoformat(lease['expires_at']) > dt.datetime.now(dt.timezone.utc):
                raise UserError('supervisor already claimed')
            lease = {'owner': owner, 'expires_at': expires_at}
            ledger['lease'] = lease
            self._save(run_id, ledger)
            return lease

    def release_lease(self, run_id: str, *, owner: str) -> None:
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id)
            lease = ledger.get('lease')
            if not lease:
                return
            if lease['owner'] != owner:
                raise UserError('only the current supervisor may release its lease')
            ledger.pop('lease')
            self._save(run_id, ledger)

    def prune(self, *, days: int = 30) -> dict[str, Any]:
        """Age-prune resolved artifacts, retaining readable review/run tombstones.

        Unlike the daily helper, age never deletes an open run, unresolved error,
        attempt, upload, review choice or source backlog. Conversion/delivery
        completion states must be supplied by the later coordinator.
        """
        if type(days) is not int or days < 0:
            raise UserError('retention days must be non-negative')
        cutoff = dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
        retained, deleted = [], []
        with self._lock('retention'):
            backlog_pending = any(any(x.get('status') not in {'accepted', 'excluded', 'resolved'} for x in read_json(p, {}).get('backlog', [])) for p in (self.state_root / 'sources').glob('*.json'))
            for path in sorted((self.state_root / 'runs').iterdir()):
                if not path.is_dir():
                    continue
                with self._lock(self._run_lock_name(path.name)):
                    ledger = self._load(path.name)
                    unsettled = any(not x.get('parent_candidate_id') and x.get('prefilter_disposition') != 'excluded' and x.get('decomposition_state') != 'complete' for x in ledger['candidates'])
                    unsettled = unsettled or any(x.get('parent_candidate_id') and not x.get('research_disposition', '').startswith('exclude_') and x.get('state') != 'complete' for x in ledger['candidates'])
                    attempts_pending = any(x['state'] != 'accepted_bundle' or x['fenced'] for x in ledger['attempts'].values())
                    young = (path / 'ledger.json').stat().st_mtime >= cutoff
                    if young or ledger['status'] != 'finalized' or backlog_pending or ledger['errors'] or unsettled or attempts_pending or ledger.get('pending_operations'):
                        retained.append({'run_id': path.name, 'reason': 'unresolved_or_not_expired', 'status': ledger['status']})
                        continue
                    tombstone = {**ledger, 'pruned_at': now()}
                    atomic_json(self.state_root / 'tombstones' / (path.name + '.json'), tombstone)
                    shutil.rmtree(path)
                    dirfd = os.open(self.state_root / 'runs', os.O_RDONLY)
                    try:
                        os.fsync(dirfd)
                    finally:
                        os.close(dirfd)
                    deleted.append(path.name)
        return {'deleted_runs': deleted, 'retained_runs': retained, 'days': days}

    def quarantine(self, run_id: str, token: str, *, caller: dict[str, Any], payload: Any) -> dict[str, Any]:
        """Save early callback audit, never silently associate or accept it."""
        with self._lock(self._run_lock_name(run_id)):
            ledger = self._load(run_id, open_only=True)
            if token not in ledger['attempts']:
                raise UserError('unknown capability')
            parsed = extract_json(payload)
            resource = 'quarantine-' + token + '-' + _hash(_json_bytes(parsed))[:16]
            info = self._put_resource_locked(run_id, ledger, resource, parsed)
            ledger['attempts'][token].setdefault('quarantine', []).append({'caller': copy.deepcopy(caller), 'resource': resource, 'sha256': info['sha256']})
            self._save(run_id, ledger)
            return {'quarantined': True, 'resource': resource}
