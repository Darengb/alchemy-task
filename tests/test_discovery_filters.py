"""User message filters: message-level exclusion, context-only background, preview, digest count."""
import copy
import json
import time

import pytest

from alchemy_task import discovery_sources
from alchemy_task.core import discovery_filters as F
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.discovery_state import DiscoveryStore

MAIL = {'source_key': 'mail', 'account_key': 'acct', 'kind': 'mail', 'scope': 'me@example.test inbox threads',
        'read_method': 'approved_reader', 'name': 'Work mail'}
CHAT = {'source_key': 'chat', 'account_key': 'chat-acct', 'kind': 'generic', 'scope': 'workspace', 'read_method': 'approved_reader',
        'name': 'Work chat'}
START, END = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
ME = 'Sam Owner <me@example.test>'
PAT = 'Pat Lee <pat@example.test>'
REPORT = 'Weekly Team Report'


def mail_item(n, *messages, title=REPORT):
    msgs = [{'id': f'm{n}-{i}', 'from': a, 'to': 'team@example.test', 'subject': s, 'date': START, 'text': t}
            for i, (a, s, t) in enumerate(messages)]
    return {'source_ids': [f'gmail:acct:t{n}'], 'source_revision': 'r1', 'title': title, 'messages': msgs}


def own_report_rule(**extra):
    return F.normalize_rule({'name': 'My report (keep replies)', 'from': 'me', 'subject': REPORT, **extra})


def filters_for(config, rules, accounts=None):
    return {'rules': rules, 'me': F.me_identity(config, accounts or {})}


def envelope(items):
    return {'start': START, 'end': END, 'account_key': 'acct', 'items': items, 'status': 'complete', 'pagination_exhausted': True}


def test_own_original_is_context_only_and_replies_are_kept(tmp_path):
    store = DiscoveryStore(tmp_path / 'discovery')
    thread = mail_item(1, (ME, REPORT, 'Here is this week.'),
                       (PAT, 'Re: ' + REPORT, 'Can you add the churn numbers?\n\nOn Mon, Jan 1, 2026 at 9:00 AM Sam Owner <me@example.test> wrote:\n> Here is this week.'))
    receipt = discovery_sources.collect_attested(store, 'stream', MAIL, envelope([thread]), filters=filters_for(MAIL, [own_report_rule()]))
    [entry] = store.source_state('stream', 'mail')['backlog']
    assert entry['status'] == 'queued'
    first, reply = entry['candidate']['messages']
    assert first['filtered']['name'] == 'My report (keep replies)' and first['filtered']['context_only'] is True
    assert 'filtered' not in reply
    # Research still sees the original (it is background), and the run records the count.
    assert first['text'] == 'Here is this week.'
    assert receipt['filtered']['messages'] == 1 and receipt['filtered']['context_only'][0]['title'] == REPORT
    assert F.filtered_message_ids([entry['candidate']]) == {'m1-0'}


def test_thread_with_only_own_original_is_skipped_before_research(tmp_path):
    store = DiscoveryStore(tmp_path / 'discovery')
    thread = mail_item(2, (ME, REPORT, 'Here is this week.'))
    other = mail_item(3, (PAT, 'Budget question', 'Can you approve the budget?'), title='Budget question')
    receipt = discovery_sources.collect_attested(store, 'stream', MAIL, envelope([thread, other]), filters=filters_for(MAIL, [own_report_rule()]))
    backlog = {x['candidate']['title']: x for x in store.source_state('stream', 'mail')['backlog']}
    assert backlog[REPORT]['status'] == 'excluded'
    assert backlog[REPORT]['lineage'] == {'screened': 'filter: My report (keep replies)'}
    assert backlog['Budget question']['status'] == 'queued'
    assert receipt['filtered']['skipped'] == [{'title': REPORT, 'rule': 'My report (keep replies)', 'messages': 1}]


def test_body_rule_ignores_quoted_reply_text():
    rule = F.normalize_rule({'name': 'Launch notes', 'body': 'launch checklist'})
    item = mail_item(4, (ME, 'Plan', 'Launch checklist attached.'),
                     (PAT, 'Re: Plan', 'Looks good to me.\n\nOn Tue, Jan 2, 2026 at 10:00 AM Sam Owner\n<me@example.test> wrote:\n> Launch checklist attached.'),
                     (PAT, 'Re: Plan', 'Thanks!\n> Launch checklist attached.'))
    marked, matched, all_out = F.apply_to_item(item, [rule], config=MAIL, me=F.me_identity(MAIL))
    assert [m['message_id'] for m in matched] == ['m4-0'] and not all_out
    assert F.strip_quoted('Reply\n-----Original Message-----\nlaunch checklist') == 'Reply\n'


def test_subject_rule_never_matches_chat_and_to_is_email_only():
    chat = {'source_ids': ['slack:chat-acct:C1:171.1'], 'title': REPORT, 'channel_label': '#team',
            'messages': [{'id': '171.1', 'author': 'Sam', 'author_id': 'U1', 'text': REPORT + ' is posted'}]}
    me = F.me_identity(CHAT, {'chat-acct': {'user_id': 'U1', 'name': 'Sam'}})
    assert me['ids'] == {'u1'}
    for raw in ({'subject': REPORT}, {'to': 'team@example.test'}):
        _, matched, _ = F.apply_to_item(chat, [F.normalize_rule(raw)], config=CHAT, me=me)
        assert matched == []
    # Body and where do apply to chat; 'me' resolves from the confirmed chat identity.
    _, matched, all_out = F.apply_to_item(chat, [F.normalize_rule({'from': 'me', 'where': '#team', 'body': 'posted'})], config=CHAT, me=me)
    assert len(matched) == 1 and all_out


def test_me_unknown_matches_nothing_and_any_mode_and_disabled_rule():
    unknown = {'source_key': 'x', 'account_key': 'nobody', 'kind': 'generic', 'scope': 'board'}
    item = mail_item(5, (ME, 'Status', 'alpha beta'))
    assert not F.me_known(F.me_identity(unknown))
    _, matched, _ = F.apply_to_item(item, [F.normalize_rule({'from': 'me'})], config=unknown, me=F.me_identity(unknown))
    assert matched == []
    all_mode = F.normalize_rule({'body': ['alpha', 'gamma']})
    any_mode = F.normalize_rule({'body': ['alpha', 'gamma'], 'mode': 'any'})
    assert F.apply_to_item(item, [all_mode], config=MAIL, me={})[1] == []
    assert len(F.apply_to_item(item, [any_mode], config=MAIL, me={})[1]) == 1
    off = {**any_mode, 'enabled': False}
    assert F.apply_to_item(item, [off], config=MAIL, me={})[1] == []
    assert F.rules_for({'s': {'rules': [off]}}, 's') == []
    # Domain and name senders.
    assert len(F.apply_to_item(item, [F.normalize_rule({'from': '@example.test'})], config=MAIL, me={})[1]) == 1
    assert len(F.apply_to_item(item, [F.normalize_rule({'from': 'sam owner'})], config=MAIL, me={})[1]) == 1
    with pytest.raises(F.FilterError):
        F.normalize_rule({'name': 'empty'})


def test_all_streams_scope_and_guidance():
    data = {'*': {'rules': [own_report_rule()], 'guidance': 'Skip vendor pitches.'},
            'work': {'rules': [F.normalize_rule({'body': 'lunch'})], 'guidance': 'Keep anything from my manager.'}}
    assert [r['scope'] for r in F.rules_for(data, 'work')] == ['work', '*']
    assert [r['scope'] for r in F.rules_for(data, 'other')] == ['*']
    assert F.guidance_for(data, 'work') == 'Skip vendor pitches.\nKeep anything from my manager.'
    assert 'you' in F.describe_rule(own_report_rule()) and 'Replies from others' in F.describe_rule(own_report_rule())


def test_digest_count_line_only_when_messages_were_skipped():
    from alchemy_task.discovery_digest import render_digest
    base = dict(stream='work', day='2026-01-02', numbered=[], already=[], failures=[], outcomes=[], deferred=[], blocked=[])
    quiet = render_digest('run', coverage=[{'status': 'complete', 'source_key': 'mail', 'backlog_ids': ['x']}], **base)
    assert 'skipped by your filters' not in quiet
    text = render_digest('run', coverage=[{'status': 'complete', 'source_key': 'mail', 'backlog_ids': ['x'], 'filtered': {'messages': 3}},
                                          {'status': 'complete', 'source_key': 'chat', 'backlog_ids': ['y'], 'filtered': {'messages': 1}}], **base)
    assert '4 messages skipped by your filters.' in text
    assert '\u2014' not in text


def test_filter_tool_confirm_before_save_list_and_preview(settings, data_dir, tmp_path):
    from test_discovery_integration import service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('discovery_sources', {'work': {'mail': copy.deepcopy(MAIL)}})
    now = time.time()
    recent = time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime(now - 86400))
    old = time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime(now - 20 * 86400))
    items = [mail_item(6, (ME, REPORT, 'This week.'), (PAT, 'Re: ' + REPORT, 'Question on churn')),
             mail_item(7, (ME, REPORT, 'Only mine.')), mail_item(8, (ME, REPORT, 'Last month.'))]
    for item, when in zip(items, (recent, recent, old)):
        for m in item['messages']:
            m['date'] = when
    store = integration.store
    store.enqueue_backlog('work', 'mail', [{'source_ids': i['source_ids'], 'source_revision': 'r1', 'candidate': i} for i in items])
    rule = {'name': 'My report (keep replies)', 'from': 'me', 'subject': REPORT}
    shown = integration.filters('filter_add', stream='work', rule=rule)
    assert shown['saved'] is False and shown['needs'] == 'confirm' and 'you' in shown['description']
    assert integration.filters('filter_list', stream='work')['scopes']['work']['rules'] == []
    saved = integration.filters('filter_add', stream='work', rule=rule, user_approved=True)
    assert saved['saved'] is True
    listed = integration.filters('filter_list')['scopes']['work']['rules']
    assert [r['name'] for r in listed] == ['My report (keep replies)']
    preview = integration.filters('filter_test', stream='work', rule_id=saved['rule']['id'])
    assert preview['messages_matched'] == 2 and preview['threads_skipped'] == 1 and preview['threads_kept_with_context'] == 1
    assert {m['message_id'] for m in preview['matches']} == {'m6-0', 'm7-0'}
    assert preview['me'] == [{'source': 'Work mail', 'me': 'me@example.test', 'known': True}]
    # Disable, guidance, all-streams, remove.
    integration.filters('filter_update', stream='work', rule_id=saved['rule']['id'], rule={'enabled': False}, user_approved=True)
    assert integration.source_filters('work', MAIL) is None
    integration.filters('guidance_set', stream='*', guidance='Skip vendor pitches.', user_approved=True)
    assert integration.screening_guidance('work') == 'Skip vendor pitches.'
    assert integration._with_screening({}, 'work')['user_screening_preferences']['text'] == 'Skip vendor pitches.'
    integration.filters('filter_remove', stream='work', rule_id=saved['rule']['id'], user_approved=True)
    assert integration.filters('filter_list', stream='work')['scopes']['work']['rules'] == []
    with pytest.raises(UserError):
        integration.filters('filter_add', stream='work', rule={'subject': 'x', 'colour': 'red'})


def test_workstream_citing_only_filtered_message_is_not_proposed(tmp_path):
    from test_discovery_repairs import setup, own, THREAD
    from test_discovery_state import prepare, read_all
    store, run, cid = setup(tmp_path)
    body = [{'title': 'Thread ask', 'messages': [
        {'id': '171.2', 'author': 'Sam', 'text': 'my weekly report', 'filtered': {'rule': 'f1', 'name': 'Mine', 'context_only': True}},
        {'id': '171.3', 'author': 'Pat', 'text': 'please book the venue'}]}]
    store.put_resource(run, 'source-body-' + cid, body)
    token = prepare(store, run, cid)['token']
    b = own(cid)
    w1 = b['workstreams'][0]; w1['exact_source_ids'] = [{**THREAD, 'message_ts': '171.2'}]; w1['title'] = 'Report follow-up'
    w2 = copy.deepcopy(w1); w2['title'] = 'Book venue'; w2['exact_source_ids'] = [{**THREAD, 'message_ts': '171.3'}]
    b['workstreams'] = [w1, w2]
    receipt = store.spool_payload(run, token, b)
    attempt = store.get_attempt(run, token)
    assert 'validation_error' not in attempt, attempt.get('validation_error')
    assert any('your filters exclude' in r for r in attempt['auto_repairs'])
    stored = {w['title']: w for w in json.loads(read_all(store, run, receipt['resource'], 'parent'))['workstreams']}
    assert stored['Report follow-up']['disposition'] == 'exclude_resolved'
    assert stored['Book venue']['disposition'] != 'exclude_resolved'


def test_run_collect_applies_saved_rules_for_the_stream(settings, data_dir, tmp_path):
    from test_discovery_integration import service, configure
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    ctx.state.set('discovery_identity_accounts', {'account': {'account_key': 'account', 'aliases': ['me@example.test'], 'confirmed': True}})
    integration.filters('filter_add', stream='work', rule={'name': 'Mine', 'from': 'me', 'subject': REPORT}, user_approved=True)
    start = integration.start('work', session_id='parent')
    def reader(tool, args):
        items = [{'title': REPORT, 'source_ids': ['source:feed:account:issue:one'], 'source_revision': 'v1',
                  'messages': [{'id': 'a', 'from': ME, 'subject': REPORT, 'text': 'This week.'}]},
                 {'title': 'Other', 'source_ids': ['source:feed:account:issue:two'], 'source_revision': 'v1',
                  'messages': [{'id': 'b', 'from': PAT, 'subject': REPORT, 'text': 'Reply'}]}]
        return json.dumps({'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
                           'items': items, 'next_cursor': None, 'pagination_exhausted': True})
    ctx.dispatch_tool = reader
    receipt = integration.collect(start['run_id'], 'feed', session_id='parent')
    assert receipt['filtered']['messages'] == 1 and receipt['filtered']['skipped'][0]['rule'] == 'Mine'
    statuses = {x['candidate']['title']: x['status'] for x in integration.store.source_state('work', 'feed')['backlog']}
    assert statuses == {REPORT: 'excluded', 'Other': 'queued'}


def test_child_bootstrap_marks_filtered_messages_as_background(tmp_path):
    from test_discovery_runner import setup_runner
    from test_discovery_state import prepare
    runner, store, pool, run = setup_runner(tmp_path, count=2)
    first, second = [c['candidate_id'] for c in store.candidate_index(run)][:2]
    store.put_resource(run, 'source-body-' + first, [{'title': 'x', 'messages': [
        {'id': 'a', 'author': 'Sam', 'text': 'report', 'filtered': {'rule': 'f1', 'name': 'Mine', 'context_only': True}},
        {'id': 'b', 'author': 'Pat', 'text': 'question'}]}])
    store.put_resource(run, 'source-body-' + second, [{'title': 'y', 'messages': [{'id': 'c', 'author': 'Pat', 'text': 'hi'}]}])
    marked = json.loads(runner._bootstrap(run, prepare(store, run, first))['context'])['instructions']
    plain = json.loads(runner._bootstrap(run, prepare(store, run, second))['context'])['instructions']
    assert 'background' in marked and 'never cite one as a decisive message' in marked
    assert 'never cite one as a decisive message' not in plain
