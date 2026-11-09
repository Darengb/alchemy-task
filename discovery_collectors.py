"""Daily algorithms over approved typed readers, with no provider transport.

The factory returns SourceAdapter's normalized read_page callable. Provider
bindings must attest actual pagination/scope, not infer them from model prose.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

from .core.discovery_identity import UserError
from .core.discovery_state import atomic_json
from .discovery_sources import (QuotaReader, load_snapshot, publish_snapshot,
                                normalize_mail_threads, validate_source_config,
                                group_slack_seeds, _date)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _envelope(config, start, end, items, **fields):
    return dict(account_key=config['account_key'], scope=config['scope'],
                start=start, end=end, items=items, **fields)


def _validate(page, config, start, end):
    if not isinstance(page, dict):
        raise UserError('reader lacks structured response')
    for key, value in [('account_key', config['account_key']), ('scope', config['scope']),
                       ('start', start), ('end', end)]:
        if page.get(key) != value:
            raise UserError('reader account/scope/window mismatch')
    if page.get('error') or page.get('truncated'):
        raise UserError('reader truncated or failed')
    if not isinstance(page.get('items'), list):
        raise UserError('reader lacks raw items')


def _pagination(page):
    if 'next_cursor' not in page or type(page.get('pagination_exhausted')) is not bool:
        raise UserError('reader lacks pagination exhaustion evidence')
    next_cursor = page['next_cursor']
    if page['pagination_exhausted'] is True and next_cursor is None:
        return True
    if page['pagination_exhausted'] is not False or not isinstance(next_cursor, str) or not next_cursor:
        raise UserError('missing or inconsistent continuation')
    return False


def _complete_thread(thread):
    if thread.get('complete') is not True or thread.get('truncated') or not isinstance(thread.get('messages'), list):
        raise UserError('unexpanded or truncated mail thread')
    for msg in thread['messages']:
        if not msg.get('id') or 'internalDate' not in msg or not isinstance(msg.get('payload'), dict) or msg.get('truncated'):
            raise UserError('incomplete primary message')


def make_daily_reader(config, read_page, *, snapshot_root, read_thread=None, read_replies=None):
    """Bind daily normalization to SourceAdapter; see docs API for raw fields.

    Mail holds all pages durably before admission. A second mail/transcript
    source can consume the same complete account/scope/window snapshot. Partial
    raw passes never publish snapshots or imply full source coverage.
    """
    validate_source_config(config)
    frozen = copy.deepcopy(config)
    kind = frozen.get('kind', 'generic')
    if kind not in {'mail', 'transcript', 'slack', 'generic'}:
        raise UserError('unsupported daily source kind')
    if kind == 'transcript' and (not isinstance(frozen.get('service_sender'), str) or not frozen['service_sender'].strip()):
        raise UserError('transcript source requires configured service_sender')
    root = Path(snapshot_root)
    quota = None
    quota_window = None

    def invoke(callback, *args):
        nonlocal quota, quota_window
        policy = frozen.get('reader_policy', {})
        if kind in {'mail', 'transcript'} and policy.get('structured_errors') is True and policy.get('owns_retries') is False:
            window = args[1:3]
            if quota is None or quota_window != window:
                quota, quota_window = QuotaReader(), window
            return quota.execute(lambda: callback(*args))
        return callback(*args)

    def reader(actual, start, end, cursor):
        if actual != frozen:
            raise UserError('daily reader frozen config mismatch')
        if kind == 'generic':
            return read_page(actual, start, end, cursor)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Scope is part of snapshot key: never reuse a restricted transcript scan
        # as evidence that a broader mailbox has been collected.
        shared = [frozen['account_key'], frozen['scope'], start, end]
        snapshot = root / ('mail-' + _hash(shared) + '.json')
        pending = root / ('pass-' + _hash([frozen, start, end]) + '.json')
        if kind in {'mail', 'transcript'}:
            saved = load_snapshot(snapshot, account=frozen['account_key'], start=start, end=end)
            if saved is not None:
                return project(saved['threads'], start, end, shared_snapshot=True)
        state = json.loads(pending.read_text()) if pending.exists() else {'items': [], 'pages': [], 'cursor': None, 'listed': False, 'threads': {}}
        if not state['listed']:
            request_cursor = state['cursor']
            if cursor is not None and cursor != state.get('adapter_cursor', request_cursor):
                raise UserError('daily continuation mismatch')
            request_config = actual
            if kind == 'slack':
                queries = frozen.get('seed_queries')
                if not isinstance(queries, list) or not queries or any(not isinstance(q, str) or not q.strip() for q in queries):
                    raise UserError('Slack requires approved seed_queries, no identity guessing')
                branch = state.get('branch', 0)
                after = (datetime.fromisoformat(start.replace('Z', '+00:00')).date() - timedelta(days=1)).isoformat()
                before = (datetime.fromisoformat(end.replace('Z', '+00:00')).date() + timedelta(days=1)).isoformat()
                request_config = {**actual, 'collector_request': {'operation':'search', 'query':f'{queries[branch]} after:{after} before:{before}', 'count':20, 'sort':'timestamp', 'sort_dir':'asc'}}
            page = invoke(read_page, request_config, start, end, request_cursor)
            _validate(page, frozen, start, end)
            exhausted = _pagination(page)
            branch_key = state.get('branch', 0)
            if not exhausted and any(p.get('branch', 0) == branch_key and p['next_cursor'] == page['next_cursor'] for p in state['pages']):
                raise UserError('repeated raw continuation')
            state['items'].extend(page['items'])
            state['pages'].append({'branch': branch_key, 'cursor': request_cursor, 'next_cursor': page['next_cursor'], 'sha256': _hash(page), 'count': len(page['items'])})
            state['cursor'], state['listed'] = page['next_cursor'], exhausted
            if kind == 'slack' and exhausted and branch_key + 1 < len(queries):
                state['branch'], state['listed'] = branch_key + 1, False
            state['adapter_cursor'] = ('daily:' + _hash(state['pages'])) if kind == 'slack' and not state['listed'] else state['cursor']
            atomic_json(pending, state)
            if not state['listed']:
                return _envelope(frozen, start, end, [], next_cursor=state['adapter_cursor'], pagination_exhausted=False,
                                 collection={'raw_pages': state['pages'], 'admission_pending': True})
        if kind == 'slack':
            return _slack_page(frozen, start, end, state['items'], read_replies)
        # Gather unique threads and message identities BEFORE sender/report
        # admission. Full thread references can repeat across search pages.
        refs, direct_messages = {}, {}
        for item in state['items']:
            tid = item.get('id') if 'messages' in item else item.get('threadId')
            if not tid:
                raise UserError('mail raw item lacks real thread identity')
            # Standalone transcript scanners acquire full messages rather than
            # full historical threads. Do not upgrade these to mailbox snapshots.
            if kind == 'transcript' and 'payload' in item:
                _complete_thread({'id':tid,'messages':[item],'complete':True})
                direct_messages.setdefault(tid, []).append(item)
                continue
            refs.setdefault(tid, []).append(item)
        for tid in sorted(refs):
            if tid in state['threads']:
                continue
            full = [t for t in refs[tid] if 'messages' in t and t.get('complete') is True and not t.get('truncated')]
            if not full:
                if read_thread is None:
                    raise UserError('unexpanded mail thread requires approved read_thread')
                result = invoke(read_thread, actual, start, end, tid)
                _validate(result, frozen, start, end)
                if not _pagination(result):
                    raise UserError('mail thread pagination incomplete')
                full = result['items']
                if len(full) != 1 or full[0].get('id') != tid:
                    raise UserError('mail thread identity mismatch')
            for thread in full:
                _complete_thread(thread)
            # Pure normalizer dedupes message IDs, and rejects contradictory
            # bodies. Save raw union so snapshot also includes service notes.
            messages = {}
            for thread in full:
                for msg in thread['messages']:
                    mid = msg['id']
                    if mid in messages and messages[mid] != msg:
                        raise UserError('contradictory full message snapshot')
                    messages[mid] = msg
            state['threads'][tid] = {'id': tid, 'messages': sorted(messages.values(), key=lambda m: int(m['internalDate']))}
            atomic_json(pending, state)
        threads = list(state['threads'].values())
        if direct_messages:
            threads += [{'id':tid,'messages':messages} for tid,messages in direct_messages.items()]
        # Source design: the mail source publishes the all-thread snapshot and
        # transcript consumes it. A transcript listing is sender-filtered, so it
        # is never published as whole-mailbox evidence.
        published = kind == 'mail' and not direct_messages
        if published:
            publish_snapshot(snapshot, account=frozen['account_key'], start=start, end=end, threads=threads, complete=True)
        return project(threads, start, end, raw_pages=state['pages'], shared_snapshot_published=published)

    def project(threads, start, end, **metadata):
        normalized = normalize_mail_threads(threads, {**frozen, 'window_start': start, 'window_end': end})
        items = [{**x['candidate'], 'messages': x['messages'], 'latest_activity': x['latest_activity']} for x in normalized]
        return _envelope(frozen, start, end, items, next_cursor=None, pagination_exhausted=True, collection=metadata)

    return reader


class _SlackThreadError(UserError):
    """Content defect confined to one primary thread or cluster."""


def _slack_page(config, start, end, seeds, read_replies):
    # Daily date padding is only a search optimization. Exact inclusive seed
    # admission happens before the source 1800s channel clustering recipe.
    low, high = Decimal(str(_date(start).timestamp())), Decimal(str(_date(end).timestamp()))
    for seed in seeds:
        if not seed.get('ts') or not ((seed.get('channel') or {}).get('id') or seed.get('channel_id')):
            raise UserError('Slack raw search match lacks real message identity')
    exact = [m for m in seeds if low <= Decimal(m['ts']) <= high]
    seed_messages = {}
    for message in exact:
        channel = (message.get('channel') or {}).get('id') or message.get('channel_id')
        key = (channel, message['ts'])
        previous = seed_messages.get(key, {})
        old, new = previous.get('text', ''), message.get('text', '')
        if old and new and old != new and not old.startswith(new) and not new.startswith(old):
            raise UserError('contradictory Slack seed message content')
        seed_messages[key] = {**previous, **message, 'text':old if len(old)>len(new) else new}
    groups = group_slack_seeds(list(seed_messages.values()))
    blocks, partial = [], []
    truncated = set()

    def acquire(request, *, counted=False):
        if read_replies is None:
            raise UserError('Slack primary acquisition requires approved read_replies')
        try:
            page = read_replies(copy.deepcopy(config), start, end, request)
        except UserError as exc:
            # Source slack_daily_followups.py:364-367 skips a thread whose fetch
            # fails at the provider. Contract violations still fail the source.
            if (exc.details or {}).get('provider_error'):
                raise _SlackThreadError('provider error ' + exc.details['provider_error']) from exc
            raise
        _validate(page, config, start, end)
        if counted:
            # Count-limited neighbor context is NOT global history exhaustion.
            if page.get('recipe_complete') is not True:
                raise UserError('Slack counted context recipe incomplete')
        elif not _pagination(page):
            # Source reads one 200-limit page and keeps sibling threads. The
            # unexhausted primary is kept, flagged and reported as partial.
            truncated.add((request['channel'], request.get('ts') or request.get('oldest')))
            partial.append(f"Slack {request['operation']} {request['channel']}:{request.get('ts') or request.get('oldest')} not exhausted")
        return page['items']

    for group in groups:
        cid, anchor, cluster = group['channel_id'], group['anchor'], group['seeds']
        # Source slack_daily_followups.py: a failed thread is logged and skipped;
        # sibling threads continue. The skip is reported as partial coverage.
        try:
            if group['kind'] == 'thread':
                messages = acquire({'operation':'replies','channel':cid,'ts':anchor,'limit':200,'inclusive':True})
                if not any(m.get('ts') == anchor for m in messages):
                    raise _SlackThreadError('primary thread root missing')
            else:
                first, last = cluster[0]['ts'], cluster[-1]['ts']
                before = acquire({'operation':'before','channel':cid,'latest':first,'inclusive':True,'limit':6}, counted=True)
                after = acquire({'operation':'after','channel':cid,'oldest':last,'inclusive':False,'limit':10}, counted=True)
                between = acquire({'operation':'between','channel':cid,'oldest':first,'latest':last,'inclusive':True,'limit':100}) if len(cluster)>1 else []
                messages = list(reversed(before)) + list(reversed(between)) + list(reversed(after))
            merged = {}
            # Always retain real seed bodies too: source search can carry useful
            # text/metadata missing from reply/history responses. Never invent IDs.
            for msg in cluster + messages:
                ts = msg.get('ts')
                if not ts:
                    raise _SlackThreadError('primary message lacks real timestamp')
                channel = msg.get('channel')
                actual_cid = channel.get('id') if isinstance(channel, dict) else msg.get('channel_id')
                if actual_cid and actual_cid != cid:
                    raise _SlackThreadError('primary channel mismatch')
                existing = merged.get(ts, {})
                old, new = existing.get('text', ''), msg.get('text', '')
                if old and new and old != new and not old.startswith(new) and not new.startswith(old):
                    raise _SlackThreadError('contradictory primary message content')
                merged[ts] = {**existing, **msg, 'text': old if len(old)>len(new) else new}
            ordered = sorted(merged.values(), key=lambda m: Decimal(m['ts']))
            signature = set(merged)
            ids = [f"slack:{config['account_key']}:{cid}:{m['ts']}" for m in cluster]
            containing = next((b for b in blocks if b['channel_id']==cid and signature <= b['signature']), None)
            if containing is not None:
                retained = {m['ts']:m for m in containing['item']['messages']}
                for msg in ordered:
                    old = retained[msg['ts']]
                    left, right = old.get('text',''), msg.get('text','')
                    if left and right and not left.startswith(right) and not right.startswith(left):
                        raise _SlackThreadError('contradictory overlapping block content')
                    retained[msg['ts']] = {**old, **msg, 'text': left if len(left)>len(right) else right}
                containing['item']['source_ids'] = list(dict.fromkeys(containing['item']['source_ids'] + ids))
                containing['item']['messages'] = sorted(retained.values(), key=lambda m:Decimal(m['ts']))
                containing['item']['source_revision'] = _hash(containing['item']['messages'])
                continue
            item = {'title': cluster[0].get('text') or 'Conversation follow-up',
                    'source_key':config['source_key'],'source_ids':ids,
                    'source_revision':_hash(ordered),'messages':ordered,
                    'context_recipe':group['kind'],'permalink':cluster[0].get('permalink','')}
            if (cid, anchor) in truncated:
                item.update(partial=True, partial_reason='primary conversation has more messages than one provider page')
            blocks.append({'channel_id':cid,'signature':signature,'item':item})
        except _SlackThreadError as exc:
            partial.append(f"Slack {group['kind']} {cid}:{anchor} skipped: {exc}")
    collection = {'coverage':'all approved seed queries plus finite primary recipe; not whole-channel history'}
    if partial: collection['partial'] = partial
    return _envelope(config,start,end,[b['item'] for b in blocks],next_cursor=None,pagination_exhausted=True,
                     collection=collection)
