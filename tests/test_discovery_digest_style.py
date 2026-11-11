"""Digest layout, authored short fields, nothing-new matches and attested coverage."""
import json
import re
from pathlib import Path

import pytest

from alchemy_task.core import discovery_research as research
from alchemy_task.discovery_digest import DiscoveryDigest, coverage_degraded

ORIGIN = {'session_id': 'chat'}
LONG_STATE = 'Ailsa asked whether the homepage edit is the full film. Daren replied that he does not know. The task records a 31-second edit.'
LONG_NEXT = 'Confirm with Alex whether this is the complete film. Then tell Ailsa what to link.'


def item(unit, kind='semantic', **extra):
    base = {'unit_id': unit, 'research_revision': unit, 'title': 'Title ' + unit, 'kind': kind,
            'targets': [{'task_id': 't1', 'title': 'Campaign task'}] if kind != 'new' else [],
            'current_understanding': LONG_STATE, 'substantive_next_action': LONG_NEXT,
            'new_information': ['The film question is new. It was not in the task.', 'Second detail.'],
            'source_links': ['https://example.slack.com/archives/C1/p1', 'https://mail.google.com/mail/u/0/#inbox/1', 'https://docs.google.com/d/x']}
    return {**base, **extra}


def test_layout_matches_mbg_daily_and_keeps_full_research(tmp_path):
    authored = item('u1', digest_current_state='Ailsa asked if the homepage edit is the full film; nobody has answered.',
                    digest_next_action='Ask Alex whether a longer cut exists, then tell Ailsa what to link.',
                    digest_addition='Adds the open full-film question.')
    d = DiscoveryDigest(tmp_path).prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, label='M',
                                          items=[authored, item('u2', kind='new')])
    text = d['text']
    assert text.startswith('## mbg Task Discovery\n\n**Wednesday, November 11**\n**Review:** `')
    assert '**2 follow-ups** · **0 need attention**' in text
    assert '### M1. Title u1\n\n**Task type:** Potential existing task update\n**Existing task:** Campaign task' in text
    assert '**Current state:** Ailsa asked if the homepage edit is the full film; nobody has answered.' in text
    assert '**Proposed addition:** Adds the open full-film question.' in text
    assert '**Choice:** Reply "M1, update" to add this to the existing task, or "M1, create" for a separate task.' in text
    assert '[Open Slack thread \u2192](https://example.slack.com/archives/C1/p1)' in text
    assert '[Open email \u2192](https://mail.google.com/mail/u/0/#inbox/1)' in text
    assert 'docs.google.com' not in text  # at most two links per item
    # New tasks show no addition line.
    assert text.split('### M2.')[1].count('Proposed addition') == 0
    assert 'Reply with the item numbers you want, like "M2, create". Items stay open for seven days.' in text
    assert text.rstrip().endswith('No tasks were created or changed.')
    assert '\u2014' not in text
    # The Review code stays 12 hex and the reply parser still finds it in the Markdown.
    code = re.search(r'\bReview:(?:\*\*)?\s*`?([0-9a-fA-F]{12})\b', text)
    assert code and len(code.group(1)) == 12
    # Only the rendered text is short: the stored item keeps the full research for task creation.
    assert d['items'][0]['current_understanding'] == LONG_STATE
    assert d['items'][0]['new_information'][1] == 'Second detail.'


def test_fallback_is_first_whole_sentence_without_ellipsis(tmp_path):
    d = DiscoveryDigest(tmp_path).prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, label='M', items=[item('u1')])
    text = d['text']
    assert '**Current state:** Ailsa asked whether the homepage edit is the full film.\n' in text
    assert '**Next action:** Confirm with Alex whether this is the complete film.\n' in text
    assert '**Proposed addition:** The film question is new.\n' in text
    assert 'Daren replied' not in text and '\u2026' not in text


def test_already_current_matches_are_listed_once_without_a_proposal(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    items = [item('u1', existing_task_already_current=True), item('u2', existing_task_already_current=True),
             item('u3', kind='new'), item('u4', kind='new', existing_task_already_current=True)]
    d = digest.prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, label='M', items=items)
    assert [i['ref'] for i in d['items']] == ['M1', 'M2']  # a new-task flag without a target is ignored
    assert [i['unit_id'] for i in d['items']] == ['u3', 'u4']
    assert '**Already in your tasks:** Title u1 \u00b7 Title u2 (in "Campaign task")' in d['text']
    ledger = json.loads((tmp_path / 'digest-ledger.json').read_text())
    assert {p['binding']['unit_id'] for p in ledger['proposals'].values()} == {'u3', 'u4'}
    assert [a['unit_id'] for a in d['already_current']] == ['u1', 'u2']
    # The optional schema fields validate; older bundles without them stay valid.
    bundle = json.loads((Path(__file__).parent / 'fixtures/discovery/bundle.json').read_text())
    assert research.validate_bundle(bundle, bundle['candidate_id'], ['slack:T1:C1:171.1'])
    bundle['workstreams'][0].update(existing_task_already_current=True, digest_current_state='State.', digest_next_action='Next.', digest_addition='New.')
    unit = research.validate_bundle(bundle, bundle['candidate_id'], ['slack:T1:C1:171.1'])[0][1]
    assert unit['existing_task_already_current'] is True and unit['digest_next_action'] == 'Next.'
    for bad in ({'existing_task_already_current': 'yes'}, {'digest_current_state': 'x' * 301}):
        broken = json.loads(json.dumps(bundle)); broken['workstreams'][0].update(bad)
        with pytest.raises(research.UserError):
            research.validate_bundle(broken, broken['candidate_id'], ['slack:T1:C1:171.1'])


def test_attested_coverage_is_one_plain_line_and_not_degraded(tmp_path):
    attested = [{'source_key': 'mbg-slack', 'name': 'mbg Slack', 'status': 'partial', 'verification': 'agent_attested', 'error': 'Agent-read partial coverage'},
                {'source_key': 'mbg-gmail', 'name': 'mbg Gmail', 'status': 'partial', 'verification': 'agent_attested', 'error': 'Agent-read'}]
    failed = {'source_key': 'feed', 'status': 'failed', 'verification': 'adapter_verified', 'error': 'boom'}
    skipped = {'source_key': 'chan', 'status': 'partial', 'verification': 'adapter_verified', 'primary_partial': ['T1 skipped: too large']}
    assert not any(coverage_degraded(c) for c in attested)
    assert coverage_degraded(failed) and coverage_degraded(skipped)
    digest = DiscoveryDigest(tmp_path)
    clean = digest.prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, items=[], coverage=attested,
                           failures=[{'title': 'TONI25', 'reason': 'lifecycle terminal INTERRUPTED'}])
    assert '**Coverage:** mbg Slack and mbg Gmail were read with your own tools, so completeness is not verified.' in clean['text']
    assert '**Needs attention:** TONI25: research was interrupted before it finished' in clean['text']
    assert 'diagnostics' not in clean['text'] and 'partial' not in clean['text']
    quiet = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN, items=[], coverage=attested)
    assert 'No new follow-ups found.' in quiet['text']  # attested reads alone are not degraded
    bad = digest.prepare('run3', stream='mbg', day='2026-11-13', origin=ORIGIN, items=[], coverage=[failed, skipped])
    assert '**Coverage:** feed: could not be read' in bad['text']
    assert '**Coverage:** chan: skipped thread: too large' in bad['text']
    assert 'No new proposals to review.' in bad['text']
