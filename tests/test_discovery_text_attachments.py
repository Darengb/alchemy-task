"""Small text attachments (.md/.txt/.csv) reach research as labeled blocks; other types stay filename-only."""
import base64

from alchemy_task import discovery_sources as S
from alchemy_task.core import discovery_filters as F
from alchemy_task.core.discovery_state import DiscoveryStore

MAIL = {'source_key': 'mail', 'account_key': 'acct', 'kind': 'mail', 'scope': 'me@example.test inbox threads',
        'read_method': 'approved_reader', 'name': 'Work mail'}


def b64(text):
    data = text.encode() if isinstance(text, str) else text
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def payload(body, *attachments, subject='Weekly notes'):
    parts = [{'mimeType': 'multipart/alternative', 'parts': [
        {'mimeType': 'text/plain', 'body': {'data': b64(body)}},
        {'mimeType': 'text/html', 'body': {'data': b64('<p>' + body + '</p>')}}]}]
    for name, mime, data in attachments:
        part = {'mimeType': mime, 'filename': name, 'body': {'attachmentId': 'att-' + name, 'size': len(data or '')}}
        if data is not None:
            part['body']['data'] = b64(data)
        parts.append(part)
    return {'mimeType': 'multipart/mixed', 'headers': [{'name': 'From', 'value': 'Pat <pat@example.test>'},
                                                     {'name': 'Subject', 'value': subject}], 'parts': parts}


def thread(*payloads):
    return {'id': 't1', 'messages': [{'id': f'm{i}', 'internalDate': str(1767225600000 + i), 'payload': p}
                                     for i, p in enumerate(payloads)]}


def test_markdown_attachment_is_labeled_and_pdf_stays_out():
    p = payload('See the attached report.', ('report.md', 'text/markdown', '# Findings\n- latency up'),
                ('scan.pdf', 'application/pdf', b'%PDF-1.4 binary'))
    text = S.extract_message_text(p)
    assert text.startswith('See the attached report.')
    assert '\n\n[Attachment: report.md]\n# Findings\n- latency up' in text
    assert 'PDF' not in text and 'scan.pdf' not in text
    # The body itself never picks up a text attachment as its plain-text part.
    txt = payload('Body only.', ('notes.txt', 'text/plain', 'attached words'))
    assert S.extract_body_text(txt) == 'Body only.'
    assert S.extract_message_text(txt).endswith('[Attachment: notes.txt]\nattached words')
    # A text attachment without inline data (the reader left it out) adds nothing.
    assert S.extract_message_text(payload('Hi.', ('big.csv', 'text/csv', None))) == 'Hi.'


def test_csv_by_type_and_both_collector_paths():
    p = payload('Numbers attached.', ('export', 'text/csv', 'a,b\n1,2'))
    [item] = S._select_for_item([thread(p)], {'source_ids': ['gmail:acct:t1']})
    assert '[Attachment: export]\na,b\n1,2' in item['text']
    normalized = S.normalize_mail_threads([thread(p)], {**MAIL, 'owner_email': 'me@example.test'})
    bodies = [m['body'] for c in normalized for m in c.get('messages') or []]
    assert any('[Attachment: export]' in b for b in bodies)


def test_oversize_attachment_is_truncated_with_a_note():
    big = ('line of report text\n' * 4000)  # about 80 KB
    text = S.extract_message_text(payload('Long one.', ('long.md', 'text/markdown', big)))
    block = text.split('[Attachment: long.md]\n', 1)[1]
    assert len(block.encode()) < S.ATTACHMENT_MAX_BYTES + 200
    assert block.rstrip().endswith('KB shown)') and 'attachment truncated: first 50 KB' in block
    # Per-message total: the third 50 KB attachment is noted, not included.
    full = 'x' * S.ATTACHMENT_MAX_BYTES
    many = S.extract_message_text(payload('Three.', *[(f'p{i}.txt', 'text/plain', full) for i in range(3)]))
    assert many.count('[Attachment: ') == 3
    assert "(not included: this message's attachment text limit was reached)" in many
    assert sum(len(x) for x in many.split('[Attachment: ')[1:]) < S.ATTACHMENTS_MAX_BYTES + 1000


def test_body_filter_matches_attachment_text_even_after_quoted_reply():
    reply = 'Thanks.\n\nOn Mon, Jan 1, 2026 at 9:00 AM Sam <me@example.test> wrote:\n> earlier text'
    text = S.extract_message_text(payload(reply, ('friction.md', 'text/markdown', 'Friction report for the week')))
    assert '[Attachment: friction.md]' in F.strip_quoted(text)
    assert 'earlier text' not in F.strip_quoted(text)
    item = {'source_ids': ['gmail:acct:t1'], 'source_revision': 'r1', 'title': 'Weekly notes',
            'messages': [{'id': 'm0', 'from': 'pat@example.test', 'subject': 'Weekly notes', 'text': text}]}
    rule = F.normalize_rule({'name': 'Friction', 'body': 'friction report'})
    _, matched, all_out = F.apply_to_item(item, [rule], config=MAIL, me={})
    assert len(matched) == 1 and all_out
    quoted_only = F.normalize_rule({'body': 'earlier text'})
    assert F.apply_to_item(item, [quoted_only], config=MAIL, me={})[1] == []


def test_preview_reads_epoch_millisecond_strings():
    now = 1794611161.0
    item = {'source_ids': ['gmail:acct:t9'], 'source_revision': 'r1', 'title': 'Daily report',
            'messages': [{'id': 'm9', 'from': 'me@example.test', 'subject': 'Daily report', 'date': '1794611161000', 'body': 'x'}]}
    assert F.message_time(item['messages'][0]) == now
    assert F.message_time({'date': '1794611161'}) == now
    out = F.preview([F.normalize_rule({'subject': 'daily report'})], [(MAIL, {}, [item])], now=now + 3600)
    assert out['items_scanned'] == 1 and out['messages_matched'] == 1


def test_waiting_items_are_rechecked_against_new_filters(tmp_path):
    store = DiscoveryStore(tmp_path / 'discovery')
    def item(n, *texts):
        return {'source_ids': [f'gmail:acct:t{n}'], 'source_revision': 'r1', 'title': f'Item {n}',
                'messages': [{'id': f'm{n}-{i}', 'from': 'pat@example.test', 'subject': 'Hello', 'text': t} for i, t in enumerate(texts)]}
    items = [item(1, 'daily robot report'), item(2, 'daily robot report', 'real question'), item(3, 'unrelated')]
    store.enqueue_backlog('s', 'mail', [{'source_ids': i['source_ids'], 'source_revision': 'r1', 'candidate': i} for i in items])
    rules = [F.normalize_rule({'name': 'Robot', 'body': 'robot report'})]
    out = store.refilter_pending('s', 'mail', lambda c: F.apply_to_item(c, rules, config=MAIL, me={}))
    backlog = {x['candidate']['title']: x for x in store.source_state('s', 'mail')['backlog']}
    assert backlog['Item 1']['status'] == 'resolved' and backlog['Item 1']['lineage']['reason'] == 'filtered by your rules'
    assert backlog['Item 2']['status'] == 'queued' and backlog['Item 2']['candidate']['messages'][0]['filtered']['name'] == 'Robot'
    assert 'filtered' not in backlog['Item 2']['candidate']['messages'][1]
    assert backlog['Item 3']['status'] == 'queued'
    assert out['resolved'] == [backlog['Item 1']['backlog_id']] and out['updated'] == [backlog['Item 2']['backlog_id']]
    assert out['messages'] == 2
    # Idempotent: a second pass changes nothing and counts nothing.
    assert store.refilter_pending('s', 'mail', lambda c: F.apply_to_item(c, rules, config=MAIL, me={})) == {'resolved': [], 'updated': [], 'messages': 0}


def test_service_rechecks_waiting_items_and_counts_them(settings, data_dir, tmp_path):
    import copy
    from test_discovery_integration import service
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('discovery_sources', {'work': {'mail': copy.deepcopy(MAIL)}})
    candidate = {'source_ids': ['gmail:acct:t5'], 'source_revision': 'r1', 'title': 'Robot',
                 'messages': [{'id': 'm5', 'from': 'pat@example.test', 'subject': 'Hello', 'text': 'daily robot report'}]}
    integration.store.enqueue_backlog('work', 'mail', [{'source_ids': candidate['source_ids'], 'source_revision': 'r1', 'candidate': candidate}])
    integration.filters('filter_add', stream='work', rule={'name': 'Robot', 'body': 'robot report'}, user_approved=True)
    ledger = {'stream': 'work', 'config': {'stream_name': 'work'}}
    out = integration.refilter_waiting(ledger, MAIL)
    assert len(out['resolved']) == 1 and out['messages'] == 1
    [entry] = integration.store.source_state('work', 'mail')['backlog']
    assert entry['status'] == 'resolved'
