import pytest
from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.core.discovery_identity import UserError

CFG = {'source_key': 'source', 'account_key': 'account', 'scope': {'folder': 'all'}, 'read_method': 'approved_reader', 'identity': {'name': 'Example', 'confirmed': True}}
START, END = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'

def item(i):
    return {'source_ids': [f'source:source:account:thread:t{i}'], 'source_revision': f'r{i}', 'title': f'Work {i}', 'body': f'Full text of work item {i}.'}

def test_all_pages_durable_before_verified_watermark(tmp_path):
    from alchemy_task.discovery_sources import SourceAdapter
    store = DiscoveryStore(tmp_path / 'state')
    calls = []
    def read(config, start, end, cursor):
        calls.append(cursor)
        return {'account_key': 'account', 'scope': config['scope'], 'start': start, 'end': end, 'items': [item(1 if cursor is None else 2)], 'next_cursor': 'next' if cursor is None else None, 'pagination_exhausted': cursor is not None}
    adapter = SourceAdapter(store, CFG, read_page=read)
    receipt = adapter.collect('stream', start=START, end=END)
    assert calls == [None, 'next']
    state = store.source_state('stream', 'source')
    assert len(state['backlog']) == 2
    assert state['watermark'] == END
    assert receipt['verification'] == 'adapter_verified'


def test_missing_pagination_and_attestation_never_advance(tmp_path):
    from alchemy_task.discovery_sources import SourceAdapter, collect_attested
    store = DiscoveryStore(tmp_path / 'state')
    adapter = SourceAdapter(store, CFG, read_page=lambda c,s,e,k: {'account_key': 'account', 'scope': c['scope'], 'start': s, 'end': e, 'items': [item(1)]})
    receipt = adapter.collect('stream', start=START, end=END)
    assert receipt['status'] == 'partial'
    assert store.source_state('stream', 'source').get('watermark') is None
    result = collect_attested(store, 'stream', CFG, {'start': START, 'end': END, 'account_key': 'account', 'items': [item(2)], 'status': 'complete', 'pagination_exhausted': True})
    assert result['verification'] == 'agent_attested'
    assert store.source_state('stream', 'source').get('watermark') is None


def test_quota_budget_only_gates_retry_sleep_not_healthy_reads():
    from alchemy_task.discovery_sources import QuotaReader, QuotaExhausted
    from test_discovery_runner import Clock
    from types import SimpleNamespace
    clock = Clock()
    class Error(Exception):
        resp = SimpleNamespace(status=429)
        content = b'{}'
    calls = []
    def read():
        calls.append(1)
        if len(calls) < 3: raise Error()
        return 'full response'
    reader = QuotaReader(clock=clock, jitter=lambda: 0, retry_after=lambda e: 3)
    assert reader.execute(read) == 'full response'
    assert len(calls) == 3 and clock.monotonic() == 6
    clock.sleep(500)
    assert reader.execute(lambda: 'healthy after quota budget') == 'healthy after quota budget'
    with pytest.raises(QuotaExhausted): reader.execute(lambda: (_ for _ in ()).throw(Error()))


def test_private_snapshot_account_window_and_full_mail_admission(tmp_path):
    from alchemy_task.discovery_sources import publish_snapshot, load_snapshot, normalize_mail_threads
    import base64
    import os
    def message(mid, sender, at):
        return {'id': mid, 'internalDate': str(at), 'payload': {'headers': [{'name': 'From', 'value': sender}, {'name': 'Subject', 'value': 'Synthetic followup'}], 'mimeType': 'text/plain', 'body': {'data': base64.urlsafe_b64encode(b'Full latest body').decode()}}}
    threads = [{'id': 't1', 'messages': [message('m1', 'partner@example.test', 1000), message('m2', 'owner@example.test', 2000)]}]
    path = tmp_path / 'snapshot.json'
    publish_snapshot(path, account='account', start=START, end=END, threads=threads, complete=True)
    saved = load_snapshot(path, account='account', start=START, end=END)
    assert saved['threads'] == threads
    with pytest.raises(UserError): load_snapshot(path, account='foreign', start=START, end=END)
    cfg = {**CFG, 'provider': 'gmail', 'sender_domains': ['example.test'], 'owner_email': 'owner@example.test', 'owner_report_pattern': '^Weekly report'}
    normalized = normalize_mail_threads(saved['threads'], cfg)
    assert len(normalized) == 1 # full thread includes qualifying sender despite latest owner
    assert len(normalized[0]['messages']) == 2
    assert normalized[0]['candidate']['source_ids'] == ['gmail:account:t1']
    path.chmod(0o644)
    with pytest.raises(UserError, match='unsafe'): load_snapshot(path, account='account', start=START, end=END)


def test_stale_window_and_cross_account_identity_fail_closed(tmp_path):
    from alchemy_task.discovery_sources import SourceAdapter
    store = DiscoveryStore(tmp_path / 'state')
    def page(c, s, e, k):
        return {'account_key': 'account', 'scope': c['scope'], 'start': s, 'end': e, 'items': [item(1)], 'next_cursor': None, 'pagination_exhausted': True}
    adapter = SourceAdapter(store, CFG, read_page=page)
    adapter.collect('stream', start=START, end=END)
    with pytest.raises(UserError, match='stale'):
        adapter.collect('stream', start='2025-12-30T00:00:00+00:00', end=START)
    wrong = SourceAdapter(store, {**CFG, 'provider': 'gmail'}, read_page=lambda c,s,e,k: {**page(c,s,e,k), 'items': [{**item(2), 'source_ids': ['gmail:foreign:t1']}]})
    receipt = wrong.collect('stream', start=START, end=END)
    assert receipt['status'] == 'failed'
    assert store.source_state('stream', 'source')['watermark'] == END


def test_source_algorithms_keep_cluster_and_mime_boundaries():
    from alchemy_task.discovery_sources import group_slack_seeds, extract_body_text
    messages = [{'channel': {'id': 'C1'}, 'ts': ts} for ts in ['1000.000001', '2800.000001', '4601.000001']]
    groups = group_slack_seeds(messages)
    assert [len(g['seeds']) for g in groups] == [2, 1]
    assert all(g['kind'] == 'conversation' for g in groups)
    import base64
    encode = lambda s: base64.urlsafe_b64encode(s.encode()).decode()
    body = extract_body_text({'parts': [{'mimeType': 'text/html', 'body': {'data': encode('<p>Wrong</p>')}}, {'mimeType': 'text/plain', 'body': {'data': encode('Suggested next steps\n- Verify inputs\nSummary\nDo not include')}}]})
    # Plain text wins over HTML, and the whole body is kept (no section extraction).
    assert body == 'Suggested next steps\n- Verify inputs\nSummary\nDo not include'
