import json

import pytest

from alchemy_task import discovery_sources
from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.core.discovery_identity import UserError

CFG = {'source_key': 'source', 'account_key': 'account', 'scope': {'folder': 'all'}, 'read_method': 'approved_reader'}
START, END = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'


def envelope(item):
    return {'start': START, 'end': END, 'account_key': 'account', 'items': [item], 'status': 'complete', 'pagination_exhausted': True}


def item(**extra):
    return {'source_ids': ['source:source:account:thread:t1'], 'source_revision': 'r1', 'title': 'Reply to venue', **extra}


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / 'hermes-home'
    (home / 'cache' / 'scratch').mkdir(parents=True)
    monkeypatch.setattr(discovery_sources, '_hermes_home', lambda: home)
    store = DiscoveryStore(tmp_path / 'plugin-data' / 'alchemy-task' / 'discovery')
    return home, store


def test_cache_pointer_is_inlined_and_path_dropped(env):
    home, store = env
    cache = home / 'cache' / 'scratch' / 'C0TEST.json'
    cache.write_text(json.dumps({'messages': [{'user': 'U1', 'text': 'Can you send the rider by Friday?'}]}))
    discovery_sources.collect_attested(store, 'stream', CFG, envelope(item(primary_cache=str(cache))))
    saved = store.source_state('stream', 'source')['backlog'][0]['candidate']
    assert saved['messages'][0]['text'] == 'Can you send the rider by Friday?'
    assert saved['primary_content'] == saved['messages']
    assert saved['primary_inlined_from'] == 'C0TEST.json'
    assert 'primary_cache' not in saved
    assert str(cache) not in json.dumps(saved)


def test_item_without_content_is_refused_at_collect(env):
    _, store = env
    with pytest.raises(UserError, match='item has no primary content.*Reply to venue.*thread:t1'):
        discovery_sources.collect_attested(store, 'stream', CFG, envelope(item(snippet_only=True)))
    assert not store.source_state('stream', 'source').get('backlog')


def test_pointer_outside_allowed_dirs_is_refused(env, tmp_path):
    _, store = env
    outside = tmp_path / 'elsewhere' / 'notes.json'
    outside.parent.mkdir()
    outside.write_text(json.dumps({'messages': [{'text': 'secret'}]}))
    with pytest.raises(UserError, match='outside the Hermes cache'):
        discovery_sources.collect_attested(store, 'stream', CFG, envelope(item(primary_cache=str(outside))))
    # Text in the envelope itself is kept as is.
    kept = discovery_sources.inline_primary(item(body='Full email body'), store)
    assert kept['body'] == 'Full email body' and 'primary_inlined_from' not in kept
