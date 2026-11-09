import datetime as dt
import pytest
from alchemy_task.core.discovery_identity import UserError


def test_immutable_new_only_day_numbers_cross_stream_and_reply_week(tmp_path):
    from alchemy_task.discovery_digest import DiscoveryDigest
    digest = DiscoveryDigest(tmp_path)
    origin = {'session_id': 'chat', 'deliver': 'origin'}
    first = digest.prepare('run1', stream='work', day='2030-01-01', origin=origin,
                           items=[{'unit_id': 'w_one', 'research_revision': 'rev1', 'title': 'First', 'kind': 'new', 'targets': []}], label='W')
    second = digest.prepare('run2', stream='home', day='2030-01-01', origin=origin,
                            items=[{'unit_id': 'w_two', 'research_revision': 'rev2', 'title': 'Second', 'kind': 'semantic', 'targets': [{'task_id': 'uuid'}]}])
    assert first['items'][0]['number'] == 1
    assert second['items'][0]['number'] == 2
    assert 'First' not in second['text']
    assert digest.prepare('run1', stream='work', day='2030-01-01', origin=origin, items=[]) == first
    assert digest.resolve('1', day='2030-01-01', session_id='chat', today='2030-01-07')['unit_id'] == 'w_one'
    digest.decide(first['items'][0]['proposal_id'], 'approved')
    assert digest.resolve('2', day='2030-01-01', session_id='chat', today='2030-01-07')['unit_id'] == 'w_two'
    with pytest.raises(UserError, match='expired'):
        digest.resolve('2', day='2030-01-01', session_id='chat', today='2030-01-09')
    assert digest.delivery('run1')['state'] == 'prepared'
    next_day = digest.prepare('run3', stream='work', day='2030-01-02', origin=origin,
        items=[{'unit_id': 'w_three', 'research_revision': 'rev3', 'title': 'Third', 'kind': 'new', 'targets': []}])
    assert next_day['items'][0]['number'] == 1
    assert digest.resolve('1', session_id='chat', today='2030-01-03')['unit_id'] == 'w_three'
    with pytest.raises(UserError, match='missing'):
        digest.resolve('2', session_id='chat', today='2030-01-02')


def test_unknown_delivery_retains_number_and_cannot_blind_resend(tmp_path):
    from alchemy_task.discovery_digest import DiscoveryDigest
    digest = DiscoveryDigest(tmp_path)
    d = digest.prepare('run', stream='work', day='2030-01-01', origin={'session_id': 'chat'},
                       items=[{'unit_id': 'w_x', 'research_revision': 'r', 'title': 'X', 'kind': 'new', 'targets': []}],
                       failures=[{'reason': 'Research exhausted'}], coverage=[{'status': 'partial', 'source_key': 'feed'}])
    assert 'Research exhausted' in d['text'] and 'partial' in d['text']
    digest.begin_delivery('run')
    assert digest.delivery('run')['state'] == 'inflight'
    digest.delivery_unknown('run', 'transport lost')
    with pytest.raises(UserError, match='unknown'):
        digest.begin_delivery('run')
    assert digest.get('run')['items'][0]['number'] == 1
