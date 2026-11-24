"""Discovery HTTP routes. They rely on the dashboard's own auth: Hermes admits a request
before it reaches a plugin route.

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
from ..discovery_integration import DiscoveryIntegration, FeatureUnavailable
from ..core.discovery_state import read_json
from ..core.discovery_identity import UserError
from ..core.taskfile import ConcurrentEditError
from ..core.store import NeedsInput

router = APIRouter()


def _service():
    # Public context/state/config facades resolve the host's task-local profile.
    # A fresh Runtime/Integration avoids the model runtime's import-cached _ctx.
    from hermes_constants import get_hermes_home
    from .ui_common import HostContext
    return DiscoveryIntegration(Runtime(HostContext()), profile_home=get_hermes_home())


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
    elif isinstance(exc, FeatureUnavailable):
        code, status = 'not_available', 409
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


def _serving_profile(name):
    # The host SPA adds ?profile=<serving profile> to every plugin request. It
    # carries no authority; accept it only when it names this request's home.
    from hermes_constants import get_hermes_home, profile_name_for_home
    return bool(name) and profile_name_for_home(get_hermes_home()) == name


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


@router.get('/settings/approvals')
async def settings(request: Request):
    try:
        _query(request)
        return await asyncio.to_thread(lambda: {'ok': True, 'approvals': _service().approval_settings()})
    except (UserError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.post('/settings/approvals')
async def update_settings(request: Request):
    try:
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


def _since(query):
    """Client's last seen (version, day), or None. ``since`` must be an integer version."""
    if 'since' not in query: return None
    try:
        return int(query['since']), query.get('day', '')
    except ValueError as exc:
        raise APIError('invalid_request', 'since must be an integer version') from exc


def _unchanged(since, version, day):
    return since is not None and since == (version, day)


def _badge(service):
    return service.badge()


@router.get('/badge')
async def badge(request: Request):
    """Tasks tab badge: pending proposals and whether discovery has any runs or streams. Cheap: reads
    the saved run-summary index only, and answers {unchanged: true} when the client is current."""
    try:
        _query(request, {'since', 'day'})
        since = _since(dict(request.query_params))
        def work():
            out = _badge(_service())
            if _unchanged(since, out['version'], out['day']):
                return {'ok': True, 'unchanged': True, 'version': out['version'], 'day': out['day']}
            return {'ok': True, **out}
        return await asyncio.to_thread(work)
    except (UserError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


def _int(query, key, default, top):
    try:
        value = int(query.get(key, default))
    except ValueError as exc:
        raise APIError('invalid_request', key + ' must be an integer') from exc
    if not 0 <= value <= top: raise APIError('invalid_request', '%s must be 0..%d' % (key, top))
    return value


@router.get('/runs')
async def runs(request: Request):
    """Saved run summaries. Default: only runs that still need the user (pending, failed writes,
    conflicts, alarms). ``all=1`` pages every retained run (``limit``, ``offset``). Full detail of
    one run comes from /runs/{run_id}. Reads never reconcile or write run records."""
    try:
        _query(request, {'stream', 'day_from', 'day_to', 'all', 'limit', 'offset', 'since', 'day'})
        query = dict(request.query_params)
        for key in ('day_from', 'day_to'):
            if query.get(key): dt.date.fromisoformat(query[key])
        every = query.get('all') in {'1', 'true'}
        limit, offset = _int(query, 'limit', 20, 200), _int(query, 'offset', 0, 100000)
        since = _since(query)
        def work():
            service = _service()
            index = service.summary_index()
            day = service.summary_day()
            if _unchanged(since, index['version'], day):
                return {'ok': True, 'unchanged': True, 'version': index['version'], 'day': day}
            views = [r for r in service.summary_views(index)
                     if (not query.get('stream') or r['stream'] == query['stream'])
                     and (not query.get('day_from') or r['day'] >= query['day_from'])
                     and (not query.get('day_to') or r['day'] <= query['day_to'])]
            shown = views[offset:offset + limit] if every else [r for r in views if r['needs_attention']]
            return {'ok': True, 'version': index['version'], 'day': day, 'all': every, 'runs': shown,
                    'total': len(views), 'offset': offset if every else 0,
                    'has_more': every and offset + limit < len(views), 'latest': views[0] if views else None,
                    'pending': sum(v['pending'] for v in views)}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


def _after_action(service, proposal_id):
    """What an approve/dismiss answer carries so the page updates one card and the badge: the
    proposal as the run detail shows it, that run's saved summary, and the new badge."""
    record = service.digest._load()['proposals'].get(proposal_id) or {}
    run_id = (record.get('binding') or {}).get('run_id')
    out = {'badge': _badge(service)}
    if run_id:
        detail = service.project_run(service.store.get_run(run_id), reconcile=False)
        out['proposal'] = next((p for p in detail['proposals'] if p['proposal_id'] == proposal_id), None)
        out['run'] = next((s for s in service.summary_views() if s['run_id'] == run_id), None)
        out['run_detail'] = detail
    return out


@router.get('/runs/{run_id}')
async def run(request: Request, run_id: str):
    try:
        _query(request)
        def work():
            service = _service()
            return {'ok': True, **service.project_run(_run(service, run_id), reconcile=False)}
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
                return {'ok': True, 'receipt': receipt, **_after_action(service, proposal_id)}
            today = service.utcnow().astimezone(ZoneInfo(ledger['config'].get('timezone') or service.rt.settings.timezone)).date().isoformat()
            if proposal['expires'] < today and body.pop('allow_expired', False) is not True:
                raise APIError('expired', 'Proposal expired; explicit allow_expired is required', 409)
            body.pop('allow_expired', None)
            if body.get('choice') not in {'create', 'update'}:
                raise APIError('invalid_choice', 'Explicit create or update choice required')
            if body['choice'] == 'update' and not body.get('target_task_id'):
                raise APIError('target_required', 'Select an exact nominated target_task_id')
            result = service._decide_resolved({'approve': [proposal_id], 'edits': {proposal_id: body}}, resolve=lambda ref: proposal)
            return {'ok': True, 'receipt': result['results'][0], **_after_action(service, proposal_id)}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.post('/proposals/{proposal_id}/dismiss')
async def dismiss(request: Request, proposal_id: str):
    try:
        _query(request)
        await _body(request)
        def work():
            service = _service()
            record, proposal, ledger = _proposal(service, proposal_id)
            if record['state'] != 'pending':
                raise APIError('already_resolved', 'Proposal already resolved', 409)
            service._decide_resolved({'dismiss': [proposal_id]}, resolve=lambda ref: proposal)
            return {'ok': True, 'proposal_id': proposal_id, 'state': 'dismissed', **_after_action(service, proposal_id)}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)


@router.post('/runs/{run_id}/units/{unit_id}/resume')
async def resume(request: Request, run_id: str, unit_id: str):
    try:
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
            # An automatic update has no proposal decision to refresh its summary; do it here.
            service.refresh_run_summaries((run_id,))
            out = _after_action(service, proposals[0][0]) if proposals else {
                'badge': _badge(service), 'run_detail': service.project_run(_run(service, run_id), reconcile=False),
                'run': next((s for s in service.summary_views() if s['run_id'] == run_id), None)}
            return {'ok': True, 'receipt': receipt, **out}
        return await asyncio.to_thread(work)
    except (UserError, NeedsInput, ConcurrentEditError, HTTPException, ValueError, KeyError, TypeError, OSError) as exc:
        return _error(exc)
