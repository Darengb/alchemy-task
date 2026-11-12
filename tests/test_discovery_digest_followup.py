from alchemy_task.discovery_digest import DiscoveryDigest

ORIGIN = {'session_id': 'chat'}
MAIL = 'https://mail.google.com/mail/u/0/#inbox/1a1c555ddbbe3f20'
SLACK = 'https://example.slack.com/archives/C111/p1794325208261679'


def _item(unit, rev, title, link, **extra):
    return {'unit_id': unit, 'research_revision': rev, 'title': title, 'kind': 'new', 'targets': [], 'source_links': [link], **extra}


def test_queued_items_are_one_line_and_only_real_problems_need_attention(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    failures = [{'title': 'Cartograph notes', 'reason': "not finished within this run's research time: Repair the split"},
                {'title': 'Twelve units', 'reason': 'Repair represented_candidate_ids for c_3975fd960c04173e7f32'},
                {'title': 'TONI25', 'reason': 'lifecycle terminal INTERRUPTED'},
                {'title': 'Supplier', 'reason': 'not reviewed in this run'}]
    deferred = [{'title': 'Veterans Day', 'reason': 'Research time ran out; queued for the next run'}]
    coverage = [{'source_key': 'mbg-slack', 'name': 'mbg Slack', 'status': 'partial', 'verification': 'agent_attested'},
                {'source_key': 'feed', 'name': 'Feed', 'status': 'failed'}]
    text = digest.prepare('run', stream='mbg', day='2026-11-11', origin=ORIGIN, items=[], failures=failures,
                          deferred=deferred, coverage=coverage, follow_up_started=True)['text']
    assert '**Still researching:** 3 items are queued for the next run, which starts within 30 minutes.' in text
    assert 'Cartograph' not in text and 'Twelve units' not in text and 'Veterans Day' not in text
    assert '**Deferred:**' not in text and 'deferred**' not in text and '**Coverage:**' not in text
    assert text.count('**Needs attention:**') == 1 and 'TONI25: research was interrupted before it finished' in text
    assert 'Supplier: not reviewed in this run' in text
    assert 'Feed could not be read' in text
    assert '**3 need attention**' in text and '\u2014' not in text
    one = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN, items=[], deferred=deferred[:1])['text']
    assert '**Still researching:** 1 item is queued for the next scheduled run.' in one and '**0 need attention**' in one
    given = digest.prepare('run3', stream='mbg', day='2026-11-13', origin=ORIGIN, items=[], deferred=deferred, queued_count=4)['text']
    assert '**Still researching:** 4 items are queued for the next scheduled run.' in given


def test_open_proposal_from_same_source_is_not_numbered_again(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    first = digest.prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, label='M',
                           items=[_item('w_a', 'r1', 'Decide whether to apply for the CommerceNext Consumer Tech Playground', MAIL)])
    assert [i['ref'] for i in first['items']] == ['M1']
    # A fresh run over the same email: new unit id, new revision, a differently shaped link.
    again = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN, label='M',
                           items=[_item('w_b', 'r2', 'Apply for CommerceNext', 'https://mail.google.com/mail/u/x@y.com/#all/1a1c555ddbbe3f20'),
                                  _item('w_c', 'r1', 'Something new', SLACK)])
    assert [i['title'] for i in again['items']] == ['Something new'] and again['items'][0]['ref'] == 'M1'
    assert '**Still open from earlier:** M1 from November 11 (Decide whether to apply for the CommerceNext Consumer Tech ...)' in again['text']
    assert again['repeats'][0]['earlier_proposal_id'] == first['items'][0]['proposal_id']
    assert len(digest._load()['proposals']) == 2
    # Once that proposal expires the same source may be proposed again.
    late = digest.prepare('run3', stream='mbg', day='2026-11-19', origin=ORIGIN, label='M',
                          items=[_item('w_d', 'r3', 'Apply for CommerceNext', MAIL)])
    assert [i['title'] for i in late['items']] == ['Apply for CommerceNext']


def test_dismissed_proposal_stays_quiet_unless_the_source_has_a_new_message(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    first = digest.prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN,
                           items=[_item('w_a', 'r1', 'Creative Strategist referral', MAIL), _item('w_s', 'r1', 'Thread ask', SLACK)])
    for item in first['items']:
        digest.decide(item['proposal_id'], 'dismissed')
    same = digest.prepare('run2', stream='visions', day='2026-11-30', origin=ORIGIN,
                          items=[_item('w_a', 'r2', 'Creative Strategist referral', MAIL), _item('w_s2', 'r2', 'Thread ask', SLACK)])
    assert same['items'] == [] and 'Still open from earlier' not in same['text']
    reply = 'https://example.slack.com/archives/C111/p1794399999000001?thread_ts=1794325208.261679'
    newer = digest.prepare('run3', stream='mbg', day='2026-12-01', origin=ORIGIN, items=[_item('w_s3', 'r3', 'Thread ask, new reply', reply)])
    assert [i['title'] for i in newer['items']] == ['Thread ask, new reply']


def test_separate_asks_from_one_source_are_both_kept(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    run1 = digest.prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN,
                          items=[_item('w_map', 'r1', 'Approve the map', MAIL), _item('w_story', 'r1', 'Extend the Brand Story', MAIL)])
    assert len(run1['items']) == 2
    run2 = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN,
                          items=[_item('w_map', 'r2', 'Approve the map', MAIL), _item('w_other', 'r1', 'A third ask', MAIL)])
    # The same unit repeats; a different unit from a source known to hold several asks is new.
    assert [i['title'] for i in run2['items']] == ['A third ask']


def test_coverage_lines_only_for_real_gaps():
    from alchemy_task.discovery_digest import _source_problem
    attested = {'source_key': 'mail', 'status': 'partial', 'verification': 'agent_attested', 'error': '', 'backlog_ids': ['b'], 'pages': []}
    assert _source_problem(attested) is None
    assert _source_problem({**attested, 'error': 'Agent-read partial coverage, not a verified structured binding.'}) is None
    assert _source_problem({**attested, 'gaps': ['the search stopped at 500 results']}) == 'was only partly read: the search stopped at 500 results'
    bounded = {'status': 'partial', 'verification': 'adapter_verified', 'error': 'bounded read pass; continuation retained', 'backlog_ids': ['b'], 'pages': [{}]}
    assert _source_problem(bounded).startswith('was only partly read before the page limit')
    assert _source_problem({'status': 'failed', 'error': 'x'}) == 'could not be read'
