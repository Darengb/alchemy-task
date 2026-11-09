"""COL-043 outcome tests: source metadata never wedges a discovery stream.

Real path: approved reader binding -> make_daily_reader -> SourceAdapter ->
durable backlog -> freeze -> candidate index -> join -> digest. Synthetic only.
"""
import copy
import datetime as dt
import json

from test_discovery_integration import service, configure

WITHHELD = 'Follow-up (title withheld; see source)'


def slack_service(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    config.update(kind='slack', seed_queries=['<@U1>'])
    config['binding']['request_fields'].update({'query': 'collector_request.query', 'count': 'collector_request.count'})
    config['primary_bindings'] = {}
    for operation in ('before', 'after', 'between', 'replies'):
        bound = copy.deepcopy(config['binding']); bound['tool'] = 'slack_primary'
        bound['request_fields'] = {'account': 'account_key', 'scope': 'scope', 'start': 'start', 'end': 'end',
                                   'request': 'collector_request'}
        bound['response_fields']['recipe_complete'] = 'recipe_complete'
        config['primary_bindings'][operation] = bound
    integration.configure('work', config, user_approved=True)
    return integration, rt, ctx


def envelope(args, items, **kw):
    base = {'account_key': args['account'], 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
            'next_cursor': None, 'pagination_exhausted': True, 'recipe_complete': True, 'items': items}
    base.update(kw)
    return base


def ts_in(args, offset):
    return '%.6f' % (dt.datetime.fromisoformat(args['end']).timestamp() - offset)


def test_long_control_and_secret_titles_are_projected_and_every_candidate_is_indexed(settings, data_dir, tmp_path):
    integration, rt, ctx = slack_service(settings, data_dir, tmp_path)
    long_text = 'Please review the launch plan and confirm budget numbers. ' * 10
    texts = {'C1': long_text, 'C2': 'Line one\nline\x07two\x7f', 'C3': 'Password: reset flow broken on staging, can you look?',
             'C4': '\x01\x02  '}
    def dispatch(tool, args):
        if tool == 'reader':
            return envelope(args, [{'channel_id': c, 'ts': ts_in(args, 7200 + 3600 * i), 'text': t}
                                   for i, (c, t) in enumerate(texts.items())])
        return envelope(args, [])
    ctx.dispatch_tool = dispatch
    run = integration.start('work', session_id='parent')['run_id']
    assert integration.collect(run, 'feed', session_id='parent')['status'] == 'complete'
    frozen = integration.freeze(run, session_id='parent')
    assert frozen.get('index_revision')
    ledger = integration.store.get_run(run)
    titles = {c['source_ids'][0].split(':')[2]: c['title'] for c in ledger['candidates']}
    assert set(titles) == {'C1', 'C2', 'C3', 'C4'}
    assert titles['C1'] == long_text[:300] and len(titles['C1']) == 300
    assert titles['C2'] == 'Line onelinetwo'
    assert titles['C3'] == WITHHELD
    assert titles['C4'] == WITHHELD
    # The lossless primary body still carries the full, unclipped source text.
    bodies = [json.loads((integration.store.run_dir(run) / 'resources' / info['sha256']).read_text())
              for name, info in ledger['resources'].items() if name.startswith('source-body-')]
    assert len(bodies) == 4
    assert any(m.get('text') == long_text for body in bodies for version in body for m in version.get('messages', []))


def test_unindexable_source_item_is_reported_and_next_run_is_not_wedged(settings, data_dir, tmp_path):
    """A candidate the shared index cannot hold is withheld, shown in the digest, and not retried forever."""
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    configure(integration)
    bad_ids = ['source:feed:account:issue:%02d' % i for i in range(16)]
    def reader(tool, args):
        return json.dumps({'account_key': 'account', 'scope': args['scope'], 'start': args['start'], 'end': args['end'],
                           'items': [{'title': 'Huge merged thread', 'source_ids': bad_ids, 'source_revision': 'v1'}],
                           'next_cursor': None, 'pagination_exhausted': True})
    ctx.dispatch_tool = reader
    run = integration.start('work', session_id='parent')['run_id']
    assert integration.collect(run, 'feed', session_id='parent')['status'] == 'complete'
    frozen = integration.freeze(run, session_id='parent')
    assert frozen.get('index_revision')
    assert integration.store.get_run(run)['candidates'] == []
    backlog = integration.store.source_state('work', 'feed')['backlog']
    assert [b['status'] for b in backlog] == ['blocked']
    assert integration.runner.join(run, session_id='parent')['joined'] is True
    digest = integration.finalize(run, session_id='parent')
    text = json.dumps(digest)
    assert 'Huge merged thread' in text or WITHHELD in text
    assert any('could not be indexed' in f.get('reason', '') for f in digest['failures'])
    # The next run is a fresh run, not a resume of a run that can never freeze.
    nxt = integration.start('work', session_id='parent')
    assert nxt['resumed'] is False and nxt['run_id'] != run
