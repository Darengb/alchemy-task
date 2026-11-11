"""Transcript sources: sender list, keyword gate, full body, per-mailbox opt-in."""
import json
import pytest
from alchemy_task.core.discovery_identity import UserError
from test_discovery_collectors import CFG, START, END, AT, message, envelope, collect
from test_discovery_integration import service

NOTES = {**CFG, 'source_key': 'notes', 'kind': 'transcript'}


def _one_thread(msgs):
    return lambda c, s, e, k: envelope(c, s, e, [{'id': 't1', 'messages': msgs, 'complete': True}])


def _ids(state):
    return [b['candidate']['source_ids'][0].rsplit(':', 1)[-1] for b in state['backlog']]


def test_default_senders_admit_every_shipped_note_taker(tmp_path):
    from alchemy_task.discovery_sources import DEFAULT_TRANSCRIPT_SENDERS
    for expected in ('gemini-notes@google.com', 'meetings-noreply@google.com', 'meet-recordings-noreply@google.com',
                     'no-reply@zoom.us', 'fred@fireflies.ai', 'no-reply@otter.ai', 'notifications@mail.granola.ai'):
        assert expected in DEFAULT_TRANSCRIPT_SENDERS
    msgs = [message(f'm{i}', f'Notes <{s.upper()}>', subject='Meeting recap') for i, s in enumerate(DEFAULT_TRANSCRIPT_SENDERS)]
    msgs.append(message('mx', 'webinars@e.zoom.us', subject='Webinar recap'))
    receipt, state, _ = collect(tmp_path, NOTES, _one_thread(msgs))
    assert receipt['status'] == 'complete'
    assert len(state['backlog']) == len(DEFAULT_TRANSCRIPT_SENDERS)
    assert 'mx' not in _ids(state)


def test_custom_sender_list_domain_entries_and_legacy_single_sender(tmp_path):
    msgs = [message('m1', 'summary@otter.ai', subject='Recap'), message('m2', 'notes@service.test', subject='Recap'),
            message('m3', 'gemini-notes@google.com', subject='Recap'), message('m4', 'x@nototter.ai', subject='Recap')]
    _, state, _ = collect(tmp_path / 'a', {**NOTES, 'service_senders': ['@otter.ai', 'NOTES@service.test']}, _one_thread(msgs))
    assert _ids(state) == ['m1', 'm2']
    _, legacy, _ = collect(tmp_path / 'b', {**NOTES, 'service_sender': 'notes@service.test'}, _one_thread(msgs))
    assert _ids(legacy) == ['m2']


def test_keyword_gate_is_case_insensitive_over_subject_and_body(tmp_path):
    s = 'gemini-notes@google.com'
    msgs = [message('m1', s, subject='Your invoice', text='Thanks for paying.'),
            message('m2', s, subject='ACTION ITEMS from sync', text='x'),
            message('m3', s, subject='Hello', text='Here are the Next Steps we agreed.'),
            message('m4', s, subject='Hello', text='Please followup on pricing'),
            message('m5', s, subject='Hello', text='One TODO for Sam'),
            message('m6', s, subject='Hello', text='to do: send deck'),
            message('m7', s, subject='Hello', text='Key takeaways'),
            message('m8', s, subject='Hello', text='follow up with legal')]
    _, state, _ = collect(tmp_path / 'a', NOTES, _one_thread(msgs))
    assert _ids(state) == ['m2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8']
    _, custom, _ = collect(tmp_path / 'b', {**NOTES, 'keywords': ['invoice']}, _one_thread(msgs))
    assert _ids(custom) == ['m1']


def test_empty_keyword_list_refused_unless_admit_all(tmp_path):
    from alchemy_task.discovery_collectors import make_daily_reader
    for bad in ({'keywords': []}, {'keywords': ['  ']}, {'service_senders': []}, {'service_senders': [' ']}):
        with pytest.raises(UserError):
            make_daily_reader({**NOTES, **bad}, lambda *a: None, snapshot_root=tmp_path)
    msgs = [message('m1', 'gemini-notes@google.com', subject='Invoice', text='Paid')]
    _, state, _ = collect(tmp_path, {**NOTES, 'keywords': [], 'admit_all': True}, _one_thread(msgs))
    assert _ids(state) == ['m1']


def test_full_body_reaches_research_with_link_urls_and_no_section_extraction(tmp_path):
    html = ('<p>Summary</p><p>We discussed launch.</p><p>Suggested next steps</p><ul><li>Ship it</li></ul>'
            '<p>Details</p><p>Late follow-up: email the vendor</p><p><a href="https://docs.example.test/d/abc">Open transcript</a></p>')
    msgs = [message('m1', 'gemini-notes@google.com', subject='Notes: launch', text=html, mime='text/html'),
            message('m2', 'gemini-notes@google.com', subject='Notes: no heading', text='Recap without any next steps heading')]
    _, state, _ = collect(tmp_path, NOTES, _one_thread(msgs))
    assert _ids(state) == ['m1', 'm2']
    first = state['backlog'][0]['candidate']['messages'][0]
    assert 'suggested_next_steps' not in first
    assert 'Late follow-up: email the vendor' in first['body'] and 'We discussed launch.' in first['body']
    assert 'Open transcript (https://docs.example.test/d/abc)' in first['body']


def test_research_rubric_keeps_inline_follow_ups_when_link_unreadable():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    skill = (root / 'skills' / 'discovery' / 'SKILL.md').read_text()
    para = next(p for p in skill.split('\n\n') if p.startswith('**Meeting transcripts.**'))
    assert 'sources_unavailable' in para and 'never' in para.lower() and 'inline' in para.lower()
    schema = json.loads((root / 'schemas' / 'discovery-child-output.schema.json').read_text())
    assert 'inline follow-up' in json.dumps(schema)


def _mail(integration, ctx, key, name, account, scope):
    streams = ctx.state.get('streams')
    streams['work']['sources'].append({'name': name, 'scope': scope, 'method': 'reader', 'toolsets': ['mail']})
    ctx.state.set('streams', streams)
    return integration.configure('work', {'source_key': key, 'name': name, 'kind': 'mail', 'account_key': account, 'scope': scope,
        'read_method': 'reader', 'sender_domains': ['example.test'], 'toolsets': ['mail'],
        'relevance': {'identity_requirements': [], 'rules': 'Follow-ups'}}, user_approved=True)


def test_opt_in_creates_one_transcript_source_per_mailbox_with_exclusions(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {**ctx.state.get('streams'), 'work': {**ctx.state.get('streams')['work'], 'sources': []}})
    _mail(integration, ctx, 'mbg', 'Work email', 'acct-a', 'all mail')
    _mail(integration, ctx, 'band', 'Band email', 'acct-b', 'inbox')
    _mail(integration, ctx, 'side', 'Side email', 'acct-c', 'inbox')
    with pytest.raises(UserError):
        integration.configure_transcripts('work', user_approved=False)
    out = integration.configure_transcripts('work', exclude=['side'], user_approved=True)
    configs = ctx.state.get('discovery_sources')['work']
    created = {k: v for k, v in configs.items() if v.get('kind') == 'transcript'}
    assert sorted(created) == ['band-transcripts', 'mbg-transcripts'] == sorted(out['created'])
    t = created['mbg-transcripts']
    assert (t['account_key'], t['scope'], t['read_method']) == ('acct-a', 'all mail', 'reader')
    assert 'gemini-notes@google.com' in t['service_senders'] and 'action items' in t['keywords']
    stream = ctx.state.get('streams')['work']
    assert {(s['name'], s['scope']) for s in stream['sources']} >= {(t['name'], 'all mail'), (created['band-transcripts']['name'], 'inbox')}
    # The mail source now skips transcript senders, so one email never yields two candidates.
    assert configs['mbg']['transcript_senders'] == t['service_senders']
    assert 'transcript_senders' not in configs['side']
    # Re-running is idempotent.
    integration.configure_transcripts('work', exclude=['side'], user_approved=True)
    assert len(ctx.state.get('streams')['work']['sources']) == 5


def test_mail_source_skips_transcript_senders_so_one_email_is_one_candidate(tmp_path):
    mail = {**CFG, 'admit_all': True, 'sender_domains': [], 'transcript_senders': ['gemini-notes@google.com', '@otter.ai']}
    notes = {**NOTES, 'service_senders': mail['transcript_senders']}
    threads = [{'id': 't1', 'messages': [message('m1', 'gemini-notes@google.com', subject='Notes: recap')], 'complete': True},
               {'id': 't2', 'messages': [message('m2', 'summary@otter.ai', subject='Recap')], 'complete': True},
               {'id': 't3', 'messages': [message('m3', 'peer@example.test', subject='Please approve')], 'complete': True}]
    _, mstate, _ = collect(tmp_path, mail, lambda c, s, e, k: envelope(c, s, e, threads))
    assert [b['candidate']['title'] for b in mstate['backlog']] == ['Please approve']
    _, tstate, _ = collect(tmp_path, notes, lambda *a: pytest.fail('must reuse the mail snapshot'))
    assert _ids(tstate) == ['m1', 'm2']


def test_config_tool_exposes_transcript_opt_in():
    from alchemy_task.discovery_integration import SCHEMAS
    schema = SCHEMAS['discovery_config']
    assert 'transcripts' in schema['parameters']['properties']['action']['enum']


# ---- review fixes: kept customization, skip-list derivation, exclusions, legacy, bounded links


def _three(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {**ctx.state.get('streams'), 'work': {**ctx.state.get('streams')['work'], 'sources': []}})
    _mail(integration, ctx, 'mbg', 'Work email', 'acct-a', 'all mail')
    _mail(integration, ctx, 'band', 'Band email', 'acct-b', 'inbox')
    return integration, rt, ctx


def test_rerun_keeps_customized_transcript_source_and_applies_only_passed_fields(settings, data_dir, tmp_path):
    integration, rt, ctx = _three(settings, data_dir, tmp_path)
    integration.configure_transcripts('work', keywords=['custom'], user_approved=True)
    out = integration.configure_transcripts('work', user_approved=True)
    configs = ctx.state.get('discovery_sources')['work']
    assert configs['mbg-transcripts']['keywords'] == ['custom']
    assert sorted(out['kept']) == ['band-transcripts', 'mbg-transcripts'] and out['created'] == []
    out = integration.configure_transcripts('work', senders=['@otter.ai'], user_approved=True)
    configs = ctx.state.get('discovery_sources')['work']
    assert configs['mbg-transcripts']['service_senders'] == ['@otter.ai']
    assert configs['mbg-transcripts']['keywords'] == ['custom']
    assert configs['mbg']['transcript_senders'] == ['@otter.ai']
    assert sorted(out['updated']) == ['band-transcripts', 'mbg-transcripts']


def test_reconfiguring_mail_source_keeps_transcript_skip_list(settings, data_dir, tmp_path):
    integration, rt, ctx = _three(settings, data_dir, tmp_path)
    integration.configure_transcripts('work', senders=['@otter.ai'], user_approved=True)
    # Path 1: action=source re-saves the mail config without transcript_senders.
    _mail_cfg = {'source_key': 'mbg', 'name': 'Work email', 'kind': 'mail', 'account_key': 'acct-a', 'scope': 'all mail',
                 'read_method': 'reader', 'sender_domains': ['example.test'], 'toolsets': ['mail'],
                 'relevance': {'identity_requirements': [], 'rules': 'Follow-ups'}}
    integration.configure('work', dict(_mail_cfg), user_approved=True)
    assert ctx.state.get('discovery_sources')['work']['mbg']['transcript_senders'] == ['@otter.ai']
    # Path 2: a stored config lost the field (older save); the run derives it anyway.
    all_configs = ctx.state.get('discovery_sources')
    all_configs['work']['mbg'].pop('transcript_senders')
    all_configs['work']['band'].pop('transcript_senders')
    ctx.state.set('discovery_sources', all_configs)
    run = integration.start('work', session_id='parent')
    frozen = {c['source_key']: c for c in run['sources']}
    assert frozen['mbg']['transcript_senders'] == ['@otter.ai']
    assert frozen['band']['transcript_senders'] == ['@otter.ai']


def test_rerun_reports_existing_source_of_excluded_mailbox_and_removes_only_on_request(settings, data_dir, tmp_path):
    integration, rt, ctx = _three(settings, data_dir, tmp_path)
    integration.configure_transcripts('work', user_approved=True)
    out = integration.configure_transcripts('work', exclude=['band'], user_approved=True)
    configs = ctx.state.get('discovery_sources')['work']
    assert out['excluded_existing'] == ['band-transcripts'] and 'band-transcripts' in configs
    assert out.get('removed', []) == []
    names = [s['name'] for s in ctx.state.get('streams')['work']['sources']]
    out = integration.configure_transcripts('work', exclude=['band'], remove=True, user_approved=True)
    configs = ctx.state.get('discovery_sources')['work']
    assert out['removed'] == ['band-transcripts'] and 'band-transcripts' not in configs
    assert 'transcript_senders' not in configs['band'] and 'mbg-transcripts' in configs
    after = [s['name'] for s in ctx.state.get('streams')['work']['sources']]
    assert len(after) == len(names) - 1 and 'Band email meeting transcripts' not in after


def test_opt_in_refuses_when_legacy_transcript_source_covers_same_mailbox(settings, data_dir, tmp_path):
    integration, rt, ctx = _three(settings, data_dir, tmp_path)
    streams = ctx.state.get('streams')
    streams['work']['sources'].append({'name': 'Gemini notes', 'scope': 'all mail', 'method': 'reader'})
    ctx.state.set('streams', streams)
    integration.configure('work', {'source_key': 'gemini', 'name': 'Gemini notes', 'kind': 'transcript', 'account_key': 'acct-a',
        'scope': 'all mail', 'read_method': 'reader', 'service_sender': 'gemini-notes@google.com',
        'relevance': {'identity_requirements': [], 'rules': 'Follow-ups'}}, user_approved=True)
    with pytest.raises(UserError, match='gemini'):
        integration.configure_transcripts('work', user_approved=True)
    # And action=source refuses a second transcript source on the same account and scope.
    streams = ctx.state.get('streams')
    streams['work']['sources'].append({'name': 'Otter notes', 'scope': 'all mail', 'method': 'reader'})
    ctx.state.set('streams', streams)
    with pytest.raises(UserError, match='gemini'):
        integration.configure('work', {'source_key': 'otter', 'name': 'Otter notes', 'kind': 'transcript', 'account_key': 'acct-a',
            'scope': 'all mail', 'read_method': 'reader', 'service_senders': ['@otter.ai'],
            'relevance': {'identity_requirements': [], 'rules': 'Follow-ups'}}, user_approved=True)


def test_long_mailbox_names_get_distinct_transcript_names_and_sweep_reverified(settings, data_dir, tmp_path, monkeypatch):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {**ctx.state.get('streams'), 'work': {**ctx.state.get('streams')['work'], 'sources': []}})
    long = 'Shared mailbox for the regional operations and partner coordination team number'
    _mail(integration, ctx, 'one', long + ' one', 'acct-a', 'inbox')
    _mail(integration, ctx, 'two', long + ' two', 'acct-b', 'inbox')
    calls = []
    import alchemy_task.jobs as jobs
    monkeypatch.setattr(jobs, 'reverify_sweep', lambda rt: calls.append(1) or {})
    integration.configure_transcripts('work', user_approved=True)
    configs = ctx.state.get('discovery_sources')['work']
    names = {configs['one-transcripts']['name'], configs['two-transcripts']['name']}
    assert len(names) == 2 and all(len(n) <= 80 for n in names)
    assert len(ctx.state.get('streams')['work']['sources']) == 4
    assert calls


def test_mailbox_read_once_when_transcript_source_collects_first(tmp_path):
    mail = {**CFG, 'admit_all': True, 'sender_domains': [], 'transcript_senders': ['gemini-notes@google.com']}
    notes = {**NOTES, 'service_senders': ['gemini-notes@google.com'], 'mailbox_source': 'mail'}
    threads = [{'id': 't1', 'messages': [message('m1', 'gemini-notes@google.com', subject='Notes: recap')], 'complete': True},
               {'id': 't3', 'messages': [message('m3', 'peer@example.test', subject='Please approve')], 'complete': True}]
    _, tstate, _ = collect(tmp_path, notes, lambda c, s, e, k: envelope(c, s, e, threads))
    assert _ids(tstate) == ['m1']
    _, mstate, _ = collect(tmp_path, mail, lambda *a: pytest.fail('must reuse the transcript pass snapshot'))
    assert [b['candidate']['title'] for b in mstate['backlog']] == ['Please approve']


def test_opt_in_marks_transcript_source_as_sharing_the_mailbox(settings, data_dir, tmp_path):
    integration, rt, ctx = _three(settings, data_dir, tmp_path)
    integration.configure_transcripts('work', user_approved=True)
    run = integration.start('work', session_id='parent')
    frozen = {c['source_key']: c for c in run['sources']}
    assert frozen['mbg-transcripts']['mailbox_source'] == 'mbg'


def test_unclosed_anchor_flood_is_linear():
    import time
    from alchemy_task.discovery_sources import _html_to_text
    flood = '<a href="https://x.test/p">label ' * 20000
    t = time.monotonic()
    _html_to_text(flood)
    assert time.monotonic() - t < 2
    assert _html_to_text('<a data-href="https://bad.test" href="https://good.test/d">Doc</a>') == 'Doc (https://good.test/d)'
    assert _html_to_text('<a data-href="https://bad.test" href="javascript:1">Doc</a>') == 'Doc'
