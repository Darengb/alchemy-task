"""Structured (verified) readers get the same pre-research screening as attested envelopes."""
import base64

from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.discovery_collectors import make_daily_reader
from alchemy_task.discovery_sources import SourceAdapter

START, END = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
AT = 1767225600000
HUMAN = 'Pat Lee <pat@example.test>'


def _page(cfg, items):
    return {'account_key': cfg['account_key'], 'scope': cfg['scope'], 'start': START, 'end': END,
            'items': items, 'next_cursor': None, 'pagination_exhausted': True}


def _item(n, title, author, text, **extra):
    return {'source_ids': [f'source:feed:account:thread:t{n}'], 'source_revision': 'r1', 'title': title,
            'messages': [{'id': f'm{n}', 'author': author, 'time': START, 'text': text}], **extra}


def test_generic_structured_reader_screens_noise(tmp_path):
    cfg = {'source_key': 'feed', 'account_key': 'account', 'scope': 'all', 'read_method': 'reader', 'kind': 'generic'}
    items = [_item(1, 'Can you send the rider?', HUMAN, 'Can you send the rider by Friday?'),
             _item(2, 'Invitation: Weekly sync', HUMAN, 'Join the call'),
             _item(3, 'Mood nutrients', 'News <news@brand.test>', 'Read more', headers={'List-Unsubscribe': '<mailto:x>'}),
             _item(4, 'Automatic reply: rider', HUMAN, 'I am out of the office until Monday.')]
    store = DiscoveryStore(tmp_path / 'state')
    reader = make_daily_reader(cfg, lambda c, s, e, cur: _page(cfg, items), snapshot_root=tmp_path / 'cache')
    receipt = SourceAdapter(store, cfg, read_page=reader).collect('stream', start=START, end=END)
    assert receipt['status'] == 'complete'
    backlog = {x['candidate']['title']: x for x in store.source_state('stream', 'feed')['backlog']}
    assert backlog['Can you send the rider?']['status'] == 'queued'
    for title in ('Invitation: Weekly sync', 'Mood nutrients', 'Automatic reply: rider'):
        assert backlog[title]['status'] == 'excluded', title
    assert sorted(x['reason'] for x in receipt['screened']) == ['auto-reply', 'calendar notice', 'newsletter or bulk mail']
    assert set(receipt['backlog_ids']) == {x['backlog_id'] for x in backlog.values()}


def _raw(tid, mid, sender, subject, text, headers=()):
    hdrs = [{'name': 'From', 'value': sender}, {'name': 'Subject', 'value': subject}, *headers]
    msg = {'id': mid, 'internalDate': str(AT), 'payload': {'mimeType': 'text/plain', 'headers': hdrs,
           'body': {'data': base64.urlsafe_b64encode(text.encode()).decode()}}}
    return {'id': tid, 'messages': [msg], 'complete': True}


def test_mail_collector_screens_bulk_and_calendar_threads(tmp_path):
    cfg = {'source_key': 'mail', 'account_key': 'account', 'scope': 'inbox', 'read_method': 'reader', 'kind': 'mail',
           'sender_domains': ['example.test']}
    threads = [_raw('t1', 'a', 'pat@example.test', 'Approve proof', 'Can you approve the proof today?'),
               _raw('t2', 'b', 'news@example.test', 'Weekly roundup', 'Stories. Unsubscribe here.',
                    [{'name': 'List-Unsubscribe', 'value': '<mailto:x>'}]),
               _raw('t3', 'c', 'pat@example.test', 'Invitation: Sync @ Mon', 'Invitation from Google Calendar')]
    store = DiscoveryStore(tmp_path / 'state')
    reader = make_daily_reader(cfg, lambda c, s, e, cur: _page(cfg, threads), snapshot_root=tmp_path / 'cache')
    receipt = SourceAdapter(store, cfg, read_page=reader).collect('stream', start=START, end=END)
    backlog = {x['candidate']['title']: x['status'] for x in store.source_state('stream', 'mail')['backlog']}
    assert backlog == {'Approve proof': 'queued', 'Weekly roundup': 'excluded', 'Invitation: Sync @ Mon': 'excluded'}
    assert receipt['status'] == 'complete' and len(receipt['screened']) == 2
