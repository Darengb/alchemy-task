"""Identity setup gates and truncated-primary coverage outcomes (ported review prototypes P3, P4).

Each test asserts what the user would see: a refused setup saves nothing, a
truncated read earns no coverage, no backlog and no reusable snapshot, and a
narrow-scope scan is never reused as whole-mailbox evidence.
"""
import base64

import pytest

from test_discovery_integration import service, configure
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.discovery_collectors import make_daily_reader
from alchemy_task.discovery_sources import SourceAdapter
from alchemy_task.discovery_context import resolve_identity

START, END = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
AT = 1767225600000 + 1000  # one second after START


def msg(mid, sender, subject, text, **extra):
    return {'id': mid, 'internalDate': str(AT), **extra, 'payload': {'mimeType': 'text/plain',
            'headers': [{'name': 'From', 'value': sender}, {'name': 'Subject', 'value': subject}],
            'body': {'data': base64.urlsafe_b64encode(text.encode()).decode()}}}


def env(c, s, e, items, **kw):
    return {'account_key': c['account_key'], 'scope': c['scope'], 'start': s, 'end': e, 'items': items,
            'next_cursor': None, 'pagination_exhausted': True, **kw}


def saved_state(ctx):
    return {key: ctx.state.get(key) for key in ('streams', 'discovery_sources', 'discovery_identity_accounts')}


def test_identity_setup_requires_user_confirmation_same_account_and_unambiguous(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    config = configure(integration)
    config['relevance']['identity_requirements'] = ['name']
    before = saved_state(ctx)
    with pytest.raises(UserError, match='confirm'):
        integration.confirm_identity('account', {'name': 'Example Person'})  # the model did not ask the user
    assert saved_state(ctx) == before
    with pytest.raises(UserError, match='identity'):
        integration.configure('work', config, user_approved=True)  # the refused confirmation saved nothing
    integration.confirm_identity('other-account', {'name': 'Other Person'}, user_confirmed=True)
    with pytest.raises(UserError, match='identity'):
        integration.configure('work', config, user_approved=True)  # never borrow another account's identity
    with pytest.raises(UserError, match='identity'):
        SourceAdapter(DiscoveryStore(tmp_path / 's'),
                      {**config, 'identity': {'name': 'X', 'confirmed': True, 'account_key': 'other-account'}},
                      read_page=lambda *a: None)
    ambiguous = resolve_identity({'account_key': 'account'}, [{'account_key': 'account', 'name': 'A', 'confirmed': True},
                                                              {'account_key': 'account', 'name': 'B', 'confirmed': True}])
    assert ambiguous['status'] == 'needs_input' and ambiguous['ambiguous'] is True
    email_only = resolve_identity({'account_key': 'account', 'email': 'first.last@example.test', 'confirmed': True}, [])
    assert email_only['status'] == 'needs_input'


@pytest.mark.parametrize('where', ['thread', 'message'])
def test_truncated_primary_thread_yields_no_coverage_no_candidates_no_snapshot(tmp_path, where):
    cfg = {'source_key': 'mail', 'account_key': 'acct', 'scope': 'inbox', 'read_method': 'gmail', 'kind': 'mail',
           'sender_domains': ['example.test']}
    m = msg('m1', 'peer@example.test', 'Approve', 'Please approve', **({'truncated': True} if where == 'message' else {}))

    def thread(c, s, e, tid):
        return env(c, s, e, [{'id': tid, 'messages': [m], 'complete': True, **({'truncated': True} if where == 'thread' else {})}])
    store = DiscoveryStore(tmp_path / 'state')
    reader = make_daily_reader(cfg, lambda c, s, e, k: env(c, s, e, [{'id': 'm1', 'threadId': 't1'}]),
                               snapshot_root=tmp_path / 'snap', read_thread=thread)
    receipt = SourceAdapter(store, cfg, read_page=reader).collect('st', start=START, end=END)
    state = store.source_state('st', 'mail')
    assert receipt['status'] != 'complete' and receipt['covered_intervals'] == []
    assert not state.get('watermark') and state['backlog'] == []
    assert not list((tmp_path / 'snap').glob('mail-*.json'))


def test_narrow_scope_mail_snapshot_not_reused_for_broader_mailbox_scope(tmp_path):
    """Two mail sources on one account: a narrow label scan never stands in for the whole inbox."""
    inbox = {'source_key': 'mail', 'account_key': 'acct', 'scope': 'inbox', 'read_method': 'gmail', 'kind': 'mail',
             'sender_domains': ['example.test']}
    narrow = {**inbox, 'source_key': 'receipts', 'scope': 'label:receipts'}
    threads = {'tn': [msg('n1', 'billing@example.test', 'Receipt', 'Approve the renewal invoice')],
               'tm': [msg('m1', 'peer@example.test', 'Please approve', 'Approve the proof')]}
    thread = lambda c, s, e, tid: env(c, s, e, [{'id': tid, 'messages': threads[tid], 'complete': True}])
    store = DiscoveryStore(tmp_path / 'state')
    first = SourceAdapter(store, narrow, read_page=make_daily_reader(
        narrow, lambda c, s, e, k: env(c, s, e, [{'id': 'n1', 'threadId': 'tn'}]),
        snapshot_root=tmp_path / 'snap', read_thread=thread)).collect('st', start=START, end=END)
    assert first['status'] == 'complete'
    calls = []

    def inbox_list(c, s, e, k):
        calls.append(k)
        return env(c, s, e, [{'id': 'n1', 'threadId': 'tn'}, {'id': 'm1', 'threadId': 'tm'}])
    r = SourceAdapter(store, inbox, read_page=make_daily_reader(inbox, inbox_list, snapshot_root=tmp_path / 'snap',
                                                                read_thread=thread)).collect('st', start=START, end=END)
    assert r['status'] == 'complete' and calls == [None]  # the inbox listed its own mailbox
    backlog = sorted(tuple(b['source_ids']) for b in store.source_state('st', 'mail')['backlog'])
    assert backlog == [('gmail:acct:tm',), ('gmail:acct:tn',)]
