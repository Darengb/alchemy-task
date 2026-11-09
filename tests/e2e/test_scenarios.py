"""Outcome-level end-to-end discovery scenarios.

Every scenario drives the plugin only through registered tools (the surface
the scheduled job's parent and the chat reply use), or through the dashboard
HTTP routes, and asserts only user-visible outcomes: task files, frontmatter,
dossier markers, bare-remote bytes, digest lines, run records and the
delivery receipt.
"""
import datetime as dt

import pytest

from e2e import parent as P
from e2e.children import research_spec_default
from e2e.conftest import DAY1
from e2e.outcomes import dossier_ids, frontmatter, numbered_lines, snapshot

ITEMS = [('101', 'Draft Q1 vendor contract'), ('102', 'Plan onboarding for new analyst'), ('103', 'Fix login timeout')]
NORMAL_HEADER = 'Tuesday: 2 new proposals; 1 existing-task outcomes; 0 failures'


def seed_normal(world, host, *, existing_status='open'):
    tid, path = world.add_task('fix-login-timeout', 'Fix login timeout',
                               notes='User wrote this. Tracked from source:feed:acct:issue:103 on the board.',
                               status=existing_status)
    src = host.source
    src.pages = [[src.item(o, t, revision='v1') for o, t in ITEMS]]
    return tid, path


def proposal_titles(digest):
    return {item['number']: item['title'] for item in digest['items']}


def header(day):
    return day['digest']['text'].splitlines()[1]


def new_task_files(world, before):
    return [p for p in world.task_files() if world.rel(p) not in before['local']]


def run_record(host, run_id):
    return P.ok(host.call('discovery_runs', {'run_id': run_id}, session=P.PARENT))


def proposal_states(host, run_id):
    return {p['number']: p['state'] for p in run_record(host, run_id)['proposals']}


def started_host(host_factory, **stream):
    host = host_factory()
    P.setup_stream(host, **stream)
    P.set_clock(host, DAY1)
    return host


# --------------------------------------------------------------------------- a
def test_a_normal_day_two_proposals_one_enrichment_then_approve_one(world, host_factory):
    host = started_host(host_factory)
    tid, existing = seed_normal(world, host)
    original_existing = existing.read_text()
    day = P.run_day(host)
    text = day['digest']['text']
    assert header(day) == NORMAL_HEADER
    assert set(proposal_titles(day['digest']).values()) == {'Draft Q1 vendor contract', 'Plan onboarding for new analyst'}
    assert sorted(proposal_titles(day['digest'])) == [1, 2]
    assert 'Existing task: Fix login timeout: complete; git=verified' in text
    assert 'Coverage: feed: complete' in text and 'degraded' not in text
    assert text.rstrip().endswith('Reply with the numbers you want. Other items remain replyable for seven days.')
    # Automatic enrichment landed in the file, kept the user's words and status, and is on the remote.
    enriched = existing.read_text()
    assert enriched != original_existing
    assert 'User wrote this.' in enriched and frontmatter(enriched)['status'] == 'open'
    assert len(dossier_ids(enriched)) == 1 and enriched.count('Discovery context added') == 1
    snap = snapshot(world)
    assert snap['remote'][world.rel(existing)] == existing.read_bytes()
    # Native delivery: the host owns posting; the final text is the exact digest and nothing was sent by the plugin.
    assert day['send']['state'] == 'host_pending' and day['send']['delivered'] is False
    assert day['send']['final_text'] == text
    assert day['record']['summary'] == {'pending': 2, 'approved': 0, 'complete': 0, 'dismissed': 0,
                                        'auto_updated': 1, 'conflicts': 0, 'failures': 0}
    # Approve #1 in chat.
    first_title = proposal_titles(day['digest'])[1]
    before = snapshot(world)
    out = P.approve(host, ['1'])
    assert out['ok'], out
    created = new_task_files(world, before)
    assert len(created) == 1
    content = created[0].read_text()
    fm = frontmatter(content)
    assert fm['title'] == first_title and fm['status'] == 'open' and 'task' in fm['tags']
    assert len(dossier_ids(content)) == 1 and fm['dossier_ids'] == dossier_ids(content)
    assert 'Do the next concrete step for ' + first_title in content  # accepted research promoted verbatim
    after = snapshot(world)
    assert after['remote'][world.rel(created[0])] == created[0].read_bytes()
    assert after['head'] == after['remote_head'] and after['dirty'] == '' and after['commits'] == before['commits'] + 1
    record = run_record(host, day['run_id'])
    assert {p['number']: p['state'] for p in record['proposals']} == {1: 'complete', 2: 'pending'}
    assert next(p for p in record['proposals'] if p['number'] == 1)['result']['operation'] == 'created'
    assert host.sent_messages == [] and len(host.cron) == 1


def test_a2_delivered_numbers_bind_to_the_titles_shown(world, host_factory):
    """Number N in the delivered text approves exactly the item shown as N."""
    host = started_host(host_factory)
    host.source.pages = [[host.source.item(o, t) for o, t in ITEMS[:2]]]
    day = P.run_day(host)
    shown = numbered_lines(day['send']['final_text'])
    assert sorted(shown) == [1, 2], day['send']['final_text']
    before = snapshot(world)
    assert P.approve(host, ['2'])['ok']
    created = new_task_files(world, before)
    assert len(created) == 1 and frontmatter(created[0].read_text())['title'] == shown[2]
    assert proposal_states(host, day['run_id']) == {1: 'pending', 2: 'complete'}


# --------------------------------------------------------------------------- b
def test_b_rerun_same_day_and_reapprove_is_idempotent(world, host_factory):
    host = started_host(host_factory)
    seed_normal(world, host)
    day = P.run_day(host)
    assert P.approve(host, ['1'])['ok']
    after_first = snapshot(world)
    existing_text = next(p for p in world.task_files() if 'fix-login-timeout' in p.name).read_text()
    # A fresh host process (plugin re-registered, state reloaded from disk) reruns the same day.
    host2 = host_factory()
    host2.source.pages = host.source.pages
    P.set_clock(host2, DAY1 + dt.timedelta(minutes=20))
    again = P.run_day(host2)
    assert again['run_id'] != day['run_id']
    assert again['digest']['items'] == []
    assert 'No new follow-ups found.' in again['digest']['text'].splitlines()
    # Re-approve #1 from the same chat, then re-prepare and re-send the first digest.
    out = P.approve(host2, ['1'])
    assert out['ok'], out
    assert P.ok(host2.call('discovery_digest', {'run_id': day['run_id']}, session=P.PARENT))['text'] == day['digest']['text']
    resend = P.ok(host2.call('discovery_digest', {'run_id': day['run_id'], 'action': 'send'}, session=P.PARENT))
    assert resend['final_text'] == day['send']['final_text'] and resend.get('digest_sha256') == day['send'].get('digest_sha256')
    assert host.sent_messages == [] and host2.sent_messages == []
    final = snapshot(world)
    assert final['local'] == after_first['local'] and final['remote'] == after_first['remote']
    assert final['commits'] == after_first['commits']
    existing_now = next(p for p in world.task_files() if 'fix-login-timeout' in p.name).read_text()
    assert existing_now == existing_text and existing_now.count('Discovery context added') == 1
    runs = P.ok(host2.call('discovery_runs', {}, session=P.PARENT))['runs']
    assert len(runs) == 2  # one per scheduled invocation, none duplicated
    first = next(r for r in runs if r['run_id'] == day['run_id'])
    assert {p['number']: p['state'] for p in first['proposals']} == {1: 'complete', 2: 'pending'}
    # #2 is still replyable by number after the empty rerun on the same day.
    assert P.approve(host2, ['2'])['ok']
    assert len(world.task_files()) == len(after_first['local']) + 1


def test_b2_interrupted_run_resumes_same_run_without_duplicate_children(world, host_factory):
    host = started_host(host_factory)
    seed_normal(world, host)
    host.current_parent = P.PARENT
    started = host.call('discovery_start', {'stream': 'work'}, session=P.PARENT)
    P.ok(host.call('discovery_collect', {'run_id': started['run_id'], 'source_key': 'feed'}, session=P.PARENT))
    # The host process dies here; a new host instance serves the same origin chat session.
    host2 = host_factory()
    host2.source.pages = host.source.pages
    P.set_clock(host2, DAY1 + dt.timedelta(minutes=5))
    day = P.run_day(host2)
    assert day['run_id'] == started['run_id'] and day['started']['resumed'] is True
    assert header(day) == NORMAL_HEADER
    assert len(host2.subagent_lifecycle.launched) == 3
    assert len(host.source.calls) == 1 and host2.source.calls == []  # the saved collection was not re-read


# --------------------------------------------------------------------------- c
def test_c1_empty_completed_day(world, host_factory):
    host = started_host(host_factory)
    host.source.pages = [[]]
    before = snapshot(world)
    day = P.run_day(host)
    text = day['digest']['text']
    lines = text.splitlines()
    assert 'No new follow-ups found.' in lines
    assert 'Reply with the numbers' not in text and 'degraded' not in text
    assert lines[1] == 'Tuesday: 0 new proposals; 0 existing-task outcomes; 0 failures'
    assert day['send']['final_text'] == text and snapshot(world) == before
    assert day['record']['degraded'] is False


@pytest.mark.parametrize('pages', [['TRUNCATED'], 'ITEM_THEN_TRUNCATED', ['ERROR']],
                         ids=['truncated', 'item-then-truncated', 'provider-error'])
def test_c2_incomplete_first_collection_is_degraded_and_next_run_rereads_the_window(world, host_factory, pages):
    host = started_host(host_factory)
    src = host.source
    src.pages = [[src.item('201', 'Renew domain')], 'TRUNCATED'] if pages == 'ITEM_THEN_TRUNCATED' else pages
    day = P.run_day(host)
    text = day['digest']['text']
    assert 'No new follow-ups found.' not in text
    assert 'degraded' in text.splitlines()[1]
    assert any(line.startswith('Coverage: feed: ') and not line.endswith(': complete') for line in text.splitlines())
    assert day['record']['degraded'] is True
    # Coverage did not advance: the next run re-reads from the same window start.
    first_start = src.calls[0]['start']
    P.set_clock(host, DAY1 + dt.timedelta(days=1))
    src.pages = [[]]
    P.run_day(host)
    assert src.calls[-1]['start'] == first_start


def test_c3_failed_window_after_prior_complete_run_is_reread(world, host_factory):
    host = host_factory()
    P.setup_stream(host)
    P.set_clock(host, DAY1 - dt.timedelta(days=1))
    src = host.source
    src.pages = [[]]
    P.run_day(host)                      # complete day 0: a watermark exists
    P.set_clock(host, DAY1)
    src.pages = ['ERROR']
    P.run_day(host)                      # day 1 fails
    failed_start = src.calls[-1]['start']
    P.set_clock(host, DAY1 + dt.timedelta(days=1))
    src.pages = [[]]
    P.run_day(host)
    assert src.calls[-1]['start'] == failed_start


def test_c4_item_in_failed_first_window_is_surfaced_by_the_next_run(world, host_factory):
    """First-ever run fails to read; an item dated inside that window must not vanish."""
    host = started_host(host_factory)
    src = host.source
    lost_at = (DAY1 - dt.timedelta(hours=6)).isoformat()   # inside the day-1 window only
    src.timed = [(lost_at, src.item('301', 'Answer auditor request'))]
    src.pages = ['ERROR']
    day1 = P.run_day(host)
    assert 'degraded' in header(day1)
    P.set_clock(host, DAY1 + dt.timedelta(days=1))
    src.pages = [[]]
    day2 = P.run_day(host)
    assert [i['title'] for i in day2['digest']['items']] == ['Answer auditor request'], day2['digest']['text']
    assert 'No new follow-ups found.' not in day2['digest']['text']
    assert 'Coverage: feed: complete' in day2['digest']['text']


# --------------------------------------------------------------------------- d
def test_d_one_child_fails_siblings_preserved_failure_visible(world, host_factory):
    host = started_host(host_factory)
    seed_normal(world, host)
    host.behaviors = {'102': 'fail', '101': {1: 'invalid', 2: 'valid'}}
    day = P.run_day(host)
    text = day['digest']['text']
    assert header(day) == 'Tuesday: 1 new proposals; 1 existing-task outcomes; 1 failures; degraded'
    assert list(proposal_titles(day['digest']).values()) == ['Draft Q1 vendor contract']  # repaired on the 2nd ordinal
    assert any(line.startswith('Attention: Plan onboarding for new analyst: ') for line in text.splitlines())
    assert 'Existing task: Fix login timeout: complete' in text
    rec = day['record']
    assert rec['summary']['failures'] == 1 and rec['degraded'] is True
    assert any(f.get('title') == 'Plan onboarding for new analyst' for f in rec['failures'])
    launched = [entry['ordinal'] for entry in host.subagent_lifecycle.launched]
    assert sorted(launched) == [1, 1, 1, 2, 2]  # at most 2 children per failing candidate, sibling not rerun


# --------------------------------------------------------------------------- e
def test_e_cap_defers_overflow_to_next_run_not_lost(world, host_factory):
    host = started_host(host_factory, research_cap=2)
    src = host.source
    src.pages = [[src.item(o, t) for o, t in ITEMS]]
    day1 = P.run_day(host)
    assert len(day1['digest']['items']) == 2 and len(host.subagent_lifecycle.launched) == 2
    researched = set(proposal_titles(day1['digest']).values())
    deferred_title = ({t for _, t in ITEMS} - researched).pop()
    assert deferred_title in day1['digest']['text']  # visible, not silently dropped
    # Next day: the source still lists all three; only the deferred item is researched now.
    P.set_clock(host, DAY1 + dt.timedelta(days=1))
    day2 = P.run_day(host)
    assert [i['title'] for i in day2['digest']['items']] == [deferred_title]
    assert day2['digest']['items'][0]['number'] == 1
    assert len(host.subagent_lifecycle.launched) == 3


def test_e2_deferred_item_survives_when_source_no_longer_lists_it(world, host_factory):
    """Durable backlog, not re-listing: the day-2 window no longer contains the deferred item."""
    host = started_host(host_factory, research_cap=2)
    src = host.source
    src.pages = [[src.item(o, t) for o, t in ITEMS]]
    day1 = P.run_day(host)
    deferred_title = ({t for _, t in ITEMS} - set(proposal_titles(day1['digest']).values())).pop()
    P.set_clock(host, DAY1 + dt.timedelta(days=1))
    src.pages = [[]]
    day2 = P.run_day(host)
    assert [i['title'] for i in day2['digest']['items']] == [deferred_title], day2['digest']['text']
    assert 'No new follow-ups found.' not in day2['digest']['text']


def test_e3_cap_deferral_is_a_distinct_state_not_a_failure(world, host_factory):
    """adaptation-plan: deferred is a distinct state, never success or a fabricated failure."""
    host = started_host(host_factory, research_cap=2)
    src = host.source
    src.pages = [[src.item(o, t) for o, t in ITEMS]]
    day1 = P.run_day(host)
    deferred_title = ({t for _, t in ITEMS} - set(proposal_titles(day1['digest']).values())).pop()
    head = header(day1)
    assert '0 failures' in head and 'degraded' not in head, head
    assert day1['record']['summary']['failures'] == 0 and day1['record']['failures'] == []
    deferred_lines = [line for line in day1['digest']['text'].splitlines() if deferred_title in line]
    assert deferred_lines and all('eferred' in line for line in deferred_lines), day1['digest']['text']
    assert not any(line.startswith('Attention: ' + deferred_title) for line in deferred_lines)


# --------------------------------------------------------------------------- f
def semantic_world(world, host):
    tid, path = world.add_task('vendor-contract-renewal', 'Vendor contract renewal', notes='Earlier contract thread, no source ids.')
    host.research_specs['101'] = {**research_spec_default('101', 'Draft Q1 vendor contract'),
                                  'existing_task_candidates': [{'path': world.rel(path), 'match_basis': 'related_only'}]}
    host.source.pages = [[host.source.item('101', 'Draft Q1 vendor contract')]]
    return tid, path


def test_f1_semantic_update_refused_after_concurrent_user_edit(world, host_factory):
    host = started_host(host_factory)
    tid, path = semantic_world(world, host)
    day = P.run_day(host)
    item = day['digest']['items'][0]
    assert item['kind'] == 'semantic' and 'Task type: Potential existing task update' in day['digest']['text']
    target = item['targets'][0]
    # The user edits the task in their editor after the digest arrives.
    edited = path.read_text() + '\nUser added a line after the digest.\n'
    path.write_text(edited)
    before = snapshot(world)
    out = P.approve(host, ['1'], edits={'1': {'choice': 'update', 'target_task_id': target['task_id'],
                                              'expected_revision': target['revision']}})
    assert out['ok'] is False and out.get('needs') == 'retry', out
    assert path.read_text() == edited and snapshot(world)['commits'] == before['commits']
    assert proposal_states(host, day['run_id']) == {1: 'pending'}


def _edit_before_first_auto_decision(host, existing):
    original_call = host.call
    seen = []

    def call(name, args, **kw):
        if name == 'discovery_decision' and args.get('decision') == 'auto' and not seen:
            existing.write_text(existing.read_text() + '\nConcurrent user edit.\n')
            out = original_call(name, args, **kw)
            seen.append(out)
            return out
        return original_call(name, args, **kw)
    host.call = call
    return seen


def test_f2_auto_enrichment_refused_when_task_changed_after_match(world, host_factory):
    host = started_host(host_factory)
    tid, existing = seed_normal(world, host)
    _edit_before_first_auto_decision(host, existing)
    commits = world.commit_count()
    with pytest.raises(P.ToolError):
        P.run_day(host)
    text = existing.read_text()
    assert text.endswith('Concurrent user edit.\n') and dossier_ids(text) == []
    assert world.commit_count() == commits


def test_f3_stale_auto_decision_returns_structured_refusal(world, host_factory):
    """Registered tools promise {ok:false,error}; a stale CAS must not escape the plugin wrapper."""
    host = started_host(host_factory)
    tid, existing = seed_normal(world, host)
    seen = _edit_before_first_auto_decision(host, existing)
    with pytest.raises(P.ToolError):
        P.run_day(host)
    assert host.raised == [], host.raised
    out = seen[0]
    assert out.get('ok') is False and out['error']['code'] == 'stale_revision', out


def test_f4_parent_rematches_after_stale_refusal_and_run_completes(world, host_factory):
    host = started_host(host_factory)
    tid, existing = seed_normal(world, host)
    _edit_before_first_auto_decision(host, existing)
    day = P.run_day(host, retry_stale=True)
    assert [entry[0] for entry in day['log']] == ['decision_refused']
    text = existing.read_text()
    assert 'Concurrent user edit.' in text and 'User wrote this.' in text
    assert len(dossier_ids(text)) == 1 and text.count('Discovery context added') == 1
    assert header(day) == NORMAL_HEADER
    snap = snapshot(world)
    assert snap['remote'][world.rel(existing)] == existing.read_bytes() and snap['dirty'] == ''


# --------------------------------------------------------------------------- g
def test_g_push_failure_local_task_kept_git_pending_then_retry_once(world, host_factory):
    host = started_host(host_factory)
    host.source.pages = [[host.source.item('101', 'Draft Q1 vendor contract')]]
    day = P.run_day(host)
    hidden = world.remote.with_name('remote-offline.git')
    world.remote.rename(hidden)  # the remote becomes unreachable
    before_files = {world.rel(p) for p in world.task_files()}
    out = P.approve(host, ['1'])
    assert out['ok'], out
    receipt = out['results'][0]
    assert receipt['state'] == 'git_pending' and receipt['local']['state'] == 'verified'
    assert receipt['git']['state'] == 'pending' and receipt['git'].get('reason')
    created = [p for p in world.task_files() if world.rel(p) not in before_files]
    assert len(created) == 1
    record = run_record(host, day['run_id'])
    assert record['proposals'][0]['state'] == 'approved' and record['proposals'][0]['result']['state'] == 'git_pending'
    hidden.rename(world.remote)
    retry = P.approve(host, ['1'])
    assert retry['ok'], retry
    assert retry['results'][0]['state'] == 'complete' and retry['results'][0]['git']['state'] == 'verified'
    snap = snapshot(world)
    assert [p for p in world.task_files() if world.rel(p) not in before_files] == created
    assert snap['remote'][world.rel(created[0])] == created[0].read_bytes() and snap['head'] == snap['remote_head']
    assert proposal_states(host, day['run_id']) == {1: 'complete'}


# --------------------------------------------------------------------------- h
def test_h_completed_exact_task_is_enriched_not_duplicated_or_reopened(world, host_factory):
    host = started_host(host_factory)
    tid, existing = seed_normal(world, host, existing_status='done')
    host.source.pages = [[host.source.item('103', 'Fix login timeout', revision='v2')]]
    files_before = len(world.task_files())
    day = P.run_day(host)
    assert day['digest']['items'] == []
    assert 'Existing task: Fix login timeout: complete' in day['digest']['text']
    text = existing.read_text()
    assert frontmatter(text)['status'] == 'done' and len(dossier_ids(text)) == 1
    assert len(world.task_files()) == files_before
    assert snapshot(world)['remote'][world.rel(existing)] == existing.read_bytes()


# --------------------------------------------------------------------------- i
@pytest.mark.parametrize('offset,allowed', [(7, True), (8, False)])
def test_i_seven_day_reply_window(world, host_factory, offset, allowed):
    host = started_host(host_factory)
    host.source.pages = [[host.source.item('101', 'Draft Q1 vendor contract')]]
    P.run_day(host)
    P.set_clock(host, DAY1 + dt.timedelta(days=offset))
    before = snapshot(world)
    out = P.approve(host, ['1'])
    assert out['ok'] is allowed, out
    assert len(world.task_files()) == len(before['local']) + (1 if allowed else 0)
    if not allowed:
        assert 'expired' in out['message']
        out = P.approve(host, ['1'], day='2026-11-03')
        assert out['ok'] is False and 'expired' in out['message']
        assert snapshot(world) == before


# --------------------------------------------------------------------------- j / k: existing-task-only days
def test_j_noop_only_completed_check_says_no_new_followups(world, host_factory):
    host = started_host(host_factory)
    tid, existing = seed_normal(world, host)
    host.source.pages = [[host.source.item('103', 'Fix login timeout')]]
    before = snapshot(world)
    day = P.run_day(host, decisions={'103': 'noop'})
    text = day['digest']['text']
    assert snapshot(world) == before  # noop: no task byte change, log, sync or commit
    assert 'No new follow-ups found.' in text.splitlines(), text
    assert 'noop' not in text and 'Fix login timeout' not in text, text
    assert 'degraded' not in text and 'Reply with the numbers' not in text


def test_k_multiple_exact_destinations_are_blocked_not_failures(world, host_factory):
    host = started_host(host_factory)
    for slug in ('fix-login-timeout', 'fix-login-timeout-copy'):
        world.add_task(slug, 'Fix login timeout', notes='Tracked from source:feed:acct:issue:103 on the board.')
    host.source.pages = [[host.source.item('103', 'Fix login timeout', revision='v2')]]
    before = snapshot(world)
    day = P.run_day(host)
    text = day['digest']['text']
    assert snapshot(world) == before  # never a guessed mutation
    assert day['digest']['items'] == []  # unnumbered
    head = header(day)
    assert '0 failures' in head and 'degraded' not in head, text
    assert any('Fix login timeout' in line and not line.startswith('Attention:') for line in text.splitlines()), text
    assert day['record']['summary']['conflicts'] == 1 and day['record']['summary']['failures'] == 0
