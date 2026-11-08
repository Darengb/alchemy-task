import pytest
from alchemy_task.core import discovery_identity as m


def test_scoped_identity_direction_and_legacy_hashes():
    broad = {'type': 'gmail', 'account': 'work', 'thread_id': 'thread'}
    message = {**broad, 'message_id': 'message'}
    assert m.source_identity_covers(m.canonical_source_id(broad), m.canonical_source_id(message))
    assert not m.source_identity_covers(m.canonical_source_id(message), m.canonical_source_id(broad))
    assert not m.source_identity_covers('gmail:other:thread', m.canonical_source_id(message))
    assert m.candidate_id([broad, broad]) == m.candidate_id([broad])
    assert m.workstream_id('c_parent', [message]) == m.workstream_id('c_parent', [message])


@pytest.mark.parametrize('value', ['slack:W:C', 'gmail:a:t:m:extra', 'gmail: a:t', 'notion:aa-bbccddeeff00112233445566778899', {'type': 'gmail', 'account': 'work', 'thread_id': 't', 'message_id': None}, {'type': 'gmail', 'account': 'work', 'account_slug': 'work', 'thread_id': 't'}])
def test_malformed_identity_is_not_repaired(value):
    with pytest.raises(m.UserError):
        m.canonical_source_id(value)


def test_generic_source_refinement_and_accounts():
    obj = {'type': 'source', 'source_key': 'tickets', 'account_key': 'team', 'object_kind': 'issue', 'object_id': '42'}
    msg = {**obj, 'message_id': '8'}
    assert m.canonical_source_id(msg) == 'source:tickets:team:issue:42:8'
    assert m.source_identity_covers(m.canonical_source_id(obj), m.canonical_source_id(msg))
    assert not m.source_identity_covers('source:tickets:other:issue:42', m.canonical_source_id(msg))


def test_action_registry_stability_and_independence():
    sources = ['gmail:work:thread:message']
    anchors = [{'locator': 'bullet:1', 'outcome': 'Approve date'}, {'locator': 'bullet:2', 'outcome': 'Deliver artwork'}]
    first = m.freeze_actions('c_parent', sources, anchors)
    again = m.freeze_actions('c_parent', sources, list(reversed(anchors)), existing=first)
    assert first == again
    ids = [entry['action_id'] for entry in first]
    assert len(set(ids)) == 2
    assert m.workstream_id('c_parent', sources, action_id=ids[0]) != m.workstream_id('c_parent', sources, action_id=ids[1])
    with pytest.raises(m.UserError, match='duplicate'):
        m.freeze_actions('c_parent', sources, [anchors[0], {**anchors[1], 'outcome': 'Approve date'}])


def test_legacy_tokens_have_boundaries_and_urls_need_mapping():
    assert m.extract_identities('gmail:work:t:m-extra') == {'gmail:work:t:m-extra'}
    url = 'https://workspace.example.test/archives/C/p171000002?thread_ts=171.000001'
    assert m.url_identities(url) == set()
    assert m.url_identities(url, slack_workspaces={'workspace.example.test': 'W'}) == {'slack:W:C:171.000001', 'slack:W:C:171.000001:171.000002'}
    assert m.extract_identities('xgmail:work:t:m') == set()
