"""Discovery HTTP routes. Only trusted host admission grants profile-owner access.

Do not import this module from model tools or accept caller/profile authority in
payloads. The host mount binds get_hermes_home for each request, including IPC.
"""
from __future__ import annotations

import datetime as dt
import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from ..runtime import Runtime
from ..discovery_integration import DiscoveryIntegration
from ..core.discovery_state import read_json
from ..core.discovery_identity import UserError
from ..core.taskfile import ConcurrentEditError
from ..core.store import NeedsInput

router = APIRouter()


def _service():
    # Public context/state/config facades resolve the host's task-local profile.
    # A fresh Runtime/Integration avoids the model runtime's import-cached _ctx.
    from hermes_constants import get_hermes_home
    from hermes_cli.plugins import PluginContext, PluginManifest
    ctx = PluginContext(PluginManifest(name='alchemy-task'), manager=None)
    return DiscoveryIntegration(Runtime(ctx), profile_home=get_hermes_home())


class APIError(UserError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def _error(exc):
    if isinstance(exc, APIError):
        code, status = exc.code, exc.status
    elif isinstance(exc, HTTPException):
        code, status = ('unauthorized' if exc.status_code == 401 else 'forbidden'), exc.status_code
    elif isinstance(exc, ConcurrentEditError):
        code, status = 'stale_revision', 409
    else:
        code, status = 'invalid_request', 400
        message = str(exc).lower()
        if 'due date' in message: code = 'needs_due'
        elif 'area' in message: code = 'needs_area'
        elif 'dismissed' in message or 'already resolved' in message: code, status = 'already_resolved', 409
        elif 'choice' in message: code = 'invalid_choice'
        elif 'target_task_id' in message: code = 'target_required'
    message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
    return JSONResponse({'ok': False, 'error': {'code': code, 'message': message}}, status_code=status)


def _admit(request):
    # Canonical sensitive-route guard includes browser session, loopback token,
    # native owner grant, and private IPC admission. Never trust HTTP headers
    # claiming hosted admission or a boolean sent by the client.
    from hermes_cli.web_deps import late
    late('_require_token')(request)


def _serving_profile(name):
    # The host SPA adds ?profile=<serving profile> to every plugin request. It
    # carries no authority; accept it only when it names this request's home.
    from hermes_constants import get_hermes_home
    from hermes_cli.profiles import profile_matches_home
    return bool(name) and profile_matches_home(name, get_hermes_home())


def _query(request, allowed=()):
    keys = set(request.query_params)
    if 'profile' in keys:
        if not all(_serving_profile(name) for name in request.query_params.getlist('profile')):
            raise APIError('invalid_request', 'profile query names a different profile')
        keys.discard('profile')
    if keys - set(allowed):
        raise APIError('invalid_request', 'Unsupported query parameters')


def _proposal(service, proposal_id):
    record = service.digest._load()['proposals'].get(proposal_id)
    if record is None:
        raise APIError('not_found', 'Unknown exact proposal_id', 404)
    proposal = record['binding']
    ledger = service.store.get_run(proposal['run_id'])
    if ledger.get('pruned_at'):
        raise APIError('not_found', 'Proposal expired from retained storage; its run was pruned', 404)
    _production(ledger)
    return record, proposal, ledger


def _run(service, run_id):
    try:
        return service.store.get_run(run_id)
    except UserError as exc:
        if str(exc) == 'unknown run':
            raise APIError('not_found', 'Unknown exact run_id', 404) from exc
        raise


def _production(ledger):
    if ledger['config'].get('mode') != 'production':
        raise APIError('not_production', 'Only production runs permit mutation', 409)


@router.get('/settings')
async def settings(request: Request):
    try:
        _admit(request)
        _query(request)
        return await asyncio.to_thread(lambda: {'ok': True, 'approvals': _service().approval_settings()})
    except (UserError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.post('/settings')
async def update_settings(request: Request):
    try:
        _admit(request)
        _query(request)
        body = await request.json()
        if not isinstance(body, dict) or set(body) != {'approvals', 'user_approved'} or not isinstance(body['approvals'], dict):
            raise APIError('invalid_request', 'Expected approvals:{owner_only:boolean} and user_approved:true')
        def work():
            return {'ok': True, 'approvals': _service().configure_approvals(body['approvals'],
                    user_approved=body['user_approved'], dashboard=True)}
        return await asyncio.to_thread(work)
    except (UserError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.get('/runs')
async def runs(request: Request):
    try:
        _admit(request)
        _query(request, {'stream', 'day_from', 'day_to'})
        query = dict(request.query_params)
        for key in ('day_from', 'day_to'):
            if query.get(key): dt.date.fromisoformat(query[key])
        def work():
            service = _service()
            records = [service.project_run(r) for r in service._all_runs()
                       if (not query.get('stream') or r['config'].get('stream_name', r['stream']) == query['stream'])
                       and (not query.get('day_from') or r['business_date'] >= query['day_from'])
                       and (not query.get('day_to') or r['business_date'] <= query['day_to'])]
            return {'ok': True, 'runs': sorted(records, key=lambda r: (r['time'], r['run_id']), reverse=True)}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.get('/runs/{run_id}')
async def run(request: Request, run_id: str):
    try:
        _admit(request)
        _query(request)
        def work():
            service = _service()
            return {'ok': True, **service.project_run(_run(service, run_id))}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


async def _body(request, *, approve=False):
    body = await request.json() if await request.body() else {}
    allowed = {'choice', 'target_task_id', 'expected_revision', 'title', 'due', 'undated', 'area', 'priority', 'scheduled', 'allow_expired'} if approve else set()
    if not isinstance(body, dict) or set(body) - allowed:
        raise APIError('invalid_request', 'Unsupported request fields; caller authority is host supplied')
    for key, value in body.items():
        valid = type(value) is bool if key in {'undated', 'allow_expired'} else isinstance(value, str)
        if not valid: raise APIError('invalid_request', 'Invalid field type: ' + key)
    return body


@router.post('/proposals/{proposal_id}/approve')
async def approve(request: Request, proposal_id: str):
    try:
        _admit(request)
        _query(request)
        body = await _body(request, approve=True)
        def work():
            service = _service()
            record, proposal, ledger = _proposal(service, proposal_id)
            if record['state'] == 'dismissed':
                raise APIError('already_resolved', 'Proposal was dismissed', 409)
            # Retries return the saved receipt even if delivery still needs resume.
            receipt = read_json(service.conversion._paths(proposal['run_id'], proposal['unit_id'])[1])
            if receipt:
                return {'ok': True, 'receipt': receipt}
            today = service.utcnow().astimezone(ZoneInfo(ledger['config'].get('timezone') or service.rt.settings.timezone)).date().isoformat()
            if proposal['expires'] < today and body.pop('allow_expired', False) is not True:
                raise APIError('expired', 'Proposal expired; explicit allow_expired is required', 409)
            body.pop('allow_expired', None)
            if body.get('choice') not in {'create', 'update'}:
                raise APIError('invalid_choice', 'Explicit create or update choice required')
            if body['choice'] == 'update' and not body.get('target_task_id'):
                raise APIError('target_required', 'Select an exact nominated target_task_id')
            result = service._decide_resolved({'approve': [proposal_id], 'edits': {proposal_id: body}}, resolve=lambda ref: proposal)
            return {'ok': True, 'receipt': result['results'][0]}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.post('/proposals/{proposal_id}/dismiss')
async def dismiss(request: Request, proposal_id: str):
    try:
        _admit(request)
        _query(request)
        await _body(request)
        def work():
            service = _service()
            record, proposal, ledger = _proposal(service, proposal_id)
            if record['state'] != 'pending':
                raise APIError('already_resolved', 'Proposal already resolved', 409)
            service._decide_resolved({'dismiss': [proposal_id]}, resolve=lambda ref: proposal)
            return {'ok': True, 'proposal_id': proposal_id, 'state': 'dismissed'}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.post('/runs/{run_id}/units/{unit_id}/resume')
async def resume(request: Request, run_id: str, unit_id: str):
    try:
        _admit(request)
        _query(request)
        await _body(request)
        def work():
            service = _service()
            _production(_run(service, run_id))
            proposals = [(pid, record) for pid, record in service.digest._load()['proposals'].items()
                         if record['binding']['run_id'] == run_id and record['binding']['unit_id'] == unit_id]
            for _, record in proposals:
                if record['state'] == 'dismissed':
                    raise APIError('already_resolved', 'Proposal was dismissed', 409)
                if record['state'] not in {'approved', 'complete'}:
                    raise APIError('invalid_request', 'Approve the proposal before resuming its saved plan', 409)
            plan, _ = service.conversion._paths(run_id, unit_id)
            if not read_json(plan): raise APIError('invalid_request', 'Resume requires an existing immutable plan')
            receipt = service.conversion.deliver_git(run_id, unit_id)
            for pid, _ in proposals:
                if receipt['state'] == 'complete': service.digest.decide(pid, 'complete')
            return {'ok': True, 'receipt': receipt}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)
