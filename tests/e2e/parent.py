"""Scripted deterministic parent agent.

Plays the scheduled discovery job's parent turn by calling ONLY registered
tools in the order the shipped discovery skill prescribes, making the
judgments a careful parent would from tool outputs alone. The wall clock is
the single seam into plugin internals (`set_clock`).
"""
from __future__ import annotations

import json

PARENT = 'origin-chat-session'
CHECKLIST_TEXT = 'Read every page of the full primary, the all-status inventory, plausible bodies and skills.'
DEFERRED_REASON = 'Deferred: daily research cap reached; queued for the next run.'


class ToolError(AssertionError):
    pass


def ok(out):
    if not out.get('ok'):
        raise ToolError(json.dumps(out)[:1500])
    return out.get('result', out)


def set_clock(host, when):
    """The only seam: pin the plugin service's wall clock to set the business day.

    The research supervisor shares the host's virtual clock, so child runtimes
    and the host's per-call deadline are measured on the same clock.
    """
    from alchemy_task.discovery_integration import get_service
    from alchemy_task.runtime import Runtime
    service = get_service(Runtime(host))
    service.utcnow = lambda: when
    service.runner.clock = host.clock


def checklist_keys(host):
    """Acceptance dimensions as the registered tool schema advertises them to the model."""
    schema = host.schemas['discovery_research_accept']
    params = schema.get('parameters', schema)
    return params['properties']['assessment']['properties']['checklist']['required']


def setup_stream(host, *, research_cap=50, name='work', session=PARENT):
    host.current_parent = session
    created = host.call('discovery_stream', {'action': 'create', 'name': name, 'areas': ['work'],
        'sources': [{'name': 'Feed', 'scope': 'board', 'method': 'feed_reader'}],
        'research_cap': research_cap, 'user_approved': True}, session=session)
    if not created.get('ok'):
        raise ToolError(created)
    config = {'source_key': 'feed', 'name': 'Feed', 'account_key': host.source.account, 'scope': 'board',
              'read_method': 'feed_reader',
              'relevance': {'identity_requirements': [], 'rules': 'Every unresolved tracker issue on the board.'},
              'binding': {'tool': 'feed_reader', 'arguments': {},
                          'request_fields': {'account': 'account_key', 'scope': 'scope', 'start': 'start', 'end': 'end', 'cursor': 'cursor'},
                          'response_fields': {k: k for k in ['account_key', 'scope', 'start', 'end', 'items', 'next_cursor', 'pagination_exhausted']}}}
    ok(host.call('discovery_config', {'action': 'source', 'stream': name, 'config': config, 'user_approved': True}, session=session))
    return created


def _fetch_callback(host, run_id, info, session=PARENT):
    cursor = None
    while True:
        args = {'run_id': run_id, 'resource': info['resource'], 'revision': info['payload_sha256']}
        if cursor:
            args['cursor'] = cursor
        page = ok(host.call('discovery_research_fetch', args, session=session))
        if not page['has_more']:
            return
        cursor = page['next_cursor']


def run_day(host, *, stream='work', decisions=None, max_rounds=20, retry_stale=False, between_rounds=None):
    """One full scheduled run. Returns everything a user or operator can observe.

    `between_rounds(host, index)` runs after each research call and may return a
    new parent session id: the host rotated the session (context compression,
    or a new scheduled session took over). The parent then continues the SAME
    run from that session, recovering it first as the refusal instructs.
    """
    host.current_parent = PARENT
    session = PARENT
    decisions = decisions or {}
    log = []
    started = host.call('discovery_start', {'stream': stream}, session=session)
    if not started.get('ok'):
        raise ToolError(started)
    run_id = started['run_id']
    collect = ok(host.call('discovery_collect', {'run_id': run_id, 'source_key': 'feed'}, session=session))
    frozen = ok(host.call('discovery_context', {'run_id': run_id}, session=session))
    revision = frozen['index_revision']
    keys = checklist_keys(host)
    rounds = []
    # The skill's loop: short bounded calls on the SAME run until it reports complete.
    for _ in range(max_rounds):
        out = host.call('discovery_research_run', {'run_id': run_id, 'expected_revision': revision}, session=session)
        if not out.get('ok') and 'recovery' in str(out.get('error')):
            # A new session of the same parent: recover the SAME run, then continue it.
            log.append(('recovered', ok(host.call('discovery_recover', {'run_id': run_id, 'adopt': True}, session=session))))
            out = host.call('discovery_research_run', {'run_id': run_id, 'expected_revision': revision}, session=session)
        res = ok(out)
        rounds.append(res)
        for token in res['awaiting_parent']:
            record = ok(host.call('discovery_runs', {'run_id': run_id}, session=session))
            attempt = next(a for a in record['research'] if (a.get('payload') or {}).get('token') == token)
            info = attempt['payload']
            _fetch_callback(host, run_id, info, session)
            ok(host.call('discovery_research_accept', {'run_id': run_id, 'token': token, 'payload_sha256': info['payload_sha256'],
                'assessment': {'accepted': True, 'retryable': True,
                               'reason': 'Full primary, all-status tasks and skills support an independent user action.',
                               'checklist': {k: CHECKLIST_TEXT for k in keys}}}, session=session))
        if res['status'] == 'complete':
            break
        rotated = between_rounds(host, len(rounds)) if between_rounds else None
        if rotated:
            session = host.current_parent = rotated
    join = ok(host.call('discovery_join', {'run_id': run_id}, session=session))
    if not join['joined']:
        # The parent acknowledges only non-live, never-started work, with bounded reasons.
        reasons = {p['candidate_id']: DEFERRED_REASON for p in join['pending']
                   if p['reason'] == 'unstarted_or_budget_deferred'}
        join = ok(host.call('discovery_join', {'run_id': run_id, 'degraded': reasons}, session=session))
    if not join['joined']:
        raise ToolError('join blocked: ' + json.dumps(join)[:800])
    record = ok(host.call('discovery_runs', {'run_id': run_id}, session=session))
    units = [c for c in record['candidates'] if c.get('parent_candidate_id') in join['accepted'] and c.get('eligible_research')]
    matches = {}
    for unit in units:
        wid = unit['candidate_id']
        m = ok(host.call('discovery_match', {'run_id': run_id, 'unit_id': wid}, session=session))
        matches[wid] = m
        first = m['research']['exact_source_ids'][0]
        object_id = first.split(':')[4] if isinstance(first, str) else first['object_id']
        override = decisions.get(object_id)
        if m['kind'] == 'exact':
            choice = override or 'auto'

            def decide(target):
                return host.call('discovery_decision', {'run_id': run_id, 'unit_id': wid, 'decision': choice,
                    'reason': 'Unique exact task; new verified state is a useful addition.' if choice == 'auto' else 'Task already records everything.',
                    'target_task_id': target['task_id'], 'expected_revision': target['revision'], 'useful_delta': choice == 'auto'}, session=session)
            out = decide(m['targets'][0])
            if not out.get('ok') and retry_stale:
                # Careful parent: the task changed under us; re-match for the fresh revision and retry once.
                log.append(('decision_refused', out.get('error')))
                m = ok(host.call('discovery_match', {'run_id': run_id, 'unit_id': wid}, session=session))
                matches[wid] = m
                out = decide(m['targets'][0])
            ok(out)
        elif m['kind'] == 'conflict':
            ok(host.call('discovery_decision', {'run_id': run_id, 'unit_id': wid, 'decision': 'propose', 'reason': 'Several exact destinations; the user picks one.'}, session=session))
        else:
            ok(host.call('discovery_decision', {'run_id': run_id, 'unit_id': wid, 'decision': 'propose', 'reason': 'Independent untracked user action.'}, session=session))
    digest = ok(host.call('discovery_digest', {'run_id': run_id}, session=session))
    send = ok(host.call('discovery_digest', {'run_id': run_id, 'action': 'send'}, session=session))
    record = ok(host.call('discovery_runs', {'run_id': run_id}, session=session))
    return dict(run_id=run_id, started=started, collect=collect, rounds=rounds, join=join, matches=matches,
                digest=digest, send=send, record=record, log=log)


def approve(host, refs, *, edits=None, day=None, session=PARENT):
    args = {'approve': list(refs), 'edits': edits or {r: {'area': 'work', 'undated': True} for r in refs}}
    if day:
        args['day'] = day
    return host.call('discovery_decide', args, session=session)
