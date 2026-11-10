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
