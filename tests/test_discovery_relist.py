"""relist_repeats: a test stream lists every finding again, and never hides another stream's findings."""
from alchemy_task import discovery
from alchemy_task.discovery_digest import DiscoveryDigest
from test_discovery_integration import service
from test_setup import home  # noqa: F401  (fixture)

ORIGIN = {'session_id': 'chat'}
MAIL = 'https://mail.google.com/mail/u/0/#inbox/1a1c555ddbbe3f20'


def _item(unit, rev, title, link=MAIL):
    return {'unit_id': unit, 'research_revision': rev, 'title': title, 'kind': 'new', 'targets': [], 'source_links': [link]}


def test_relist_stream_numbers_a_repeat_again(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    digest.prepare('run1', stream='mbg', day='2026-11-12', origin=ORIGIN, items=[_item('w_a', 'r1', 'Apply for CommerceNext')])
    again = digest.prepare('run2', stream='mbg-test', day='2026-11-12', origin=ORIGIN, relist=True,
                           items=[_item('w_b', 'r2', 'Apply for CommerceNext')])
    assert [i['title'] for i in again['items']] == ['Apply for CommerceNext'] and not again['repeats']
    assert 'Still open from earlier' not in again['text']


def test_relist_stream_proposals_do_not_hide_another_streams_items(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    digest.prepare('run1', stream='mbg-test', day='2026-11-12', origin=ORIGIN, relist=True,
                   items=[_item('w_a', 'r1', 'Apply for CommerceNext')])
    real = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN, items=[_item('w_b', 'r2', 'Apply for CommerceNext')])
    assert [i['title'] for i in real['items']] == ['Apply for CommerceNext'] and not real['repeats']


def test_default_still_suppresses_repeats(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    digest.prepare('run1', stream='mbg', day='2026-11-12', origin=ORIGIN, items=[_item('w_a', 'r1', 'Apply')])
    again = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN, items=[_item('w_b', 'r2', 'Apply')])
    assert again['items'] == [] and again['repeats']


def test_stream_option_and_mode_are_saved_and_updatable(settings, data_dir, tmp_path, home):  # noqa: F811
    _, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    out = discovery.create_stream(rt, {'name': 'work-test', 'areas': ['work'], 'mode': 'shadow', 'relist_repeats': True,
                                       'sources': [{'name': 'Feed', 'scope': 'board', 'method': 'reader'}], 'user_approved': True}, 'parent')
    stream = ctx.state.get('streams')['work-test']
    assert stream['mode'] == 'shadow' and stream['relist_repeats'] is True
    assert out['stream']['mode'] == 'shadow' and out['stream']['relist_repeats'] is True
    discovery.update_stream(rt, {'name': 'work-test', 'relist_repeats': False, 'user_approved': True}, 'parent')
    assert ctx.state.get('streams')['work-test']['relist_repeats'] is False
    assert ctx.state.get('streams')['work-test']['mode'] == 'shadow'
    plain = discovery.create_stream(rt, {'name': 'work', 'areas': ['work'], 'user_approved': True,
                                         'sources': [{'name': 'Feed', 'scope': 'board', 'method': 'reader'}]}, 'parent')
    assert plain['stream']['mode'] == 'production' and plain['stream']['relist_repeats'] is False
    import pytest
    with pytest.raises(discovery.DiscoveryError):
        discovery.create_stream(rt, {'name': 'bad', 'mode': 'research', 'user_approved': True,
                                     'sources': [{'name': 'Feed', 'scope': 'board', 'method': 'reader'}]}, 'parent')
