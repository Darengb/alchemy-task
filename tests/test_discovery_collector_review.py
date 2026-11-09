"""Collector review B1: real multipart alternatives through the adapter."""
import base64
from alchemy_task.discovery_sources import SourceAdapter, extract_body_text
from alchemy_task.discovery_collectors import make_daily_reader
from alchemy_task.core.discovery_state import DiscoveryStore
from test_discovery_collectors import CFG, START, END, message, envelope


def test_whitespace_plain_alternative_does_not_hide_html_transcript(tmp_path):
    cfg = {**CFG, 'kind': 'transcript', 'service_sender': 'notes@service.test'}
    msg = message('m1', 'notes@service.test', text='<p>Suggested next steps</p><p>Approve proof</p>', mime='text/html')
    html_payload = msg['payload']
    msg['payload'] = {'mimeType': 'multipart/alternative', 'headers': html_payload['headers'], 'parts': [
        {'mimeType': 'text/plain', 'body': {'data': base64.urlsafe_b64encode(b' \r\n\t ').decode()}}, html_payload]}
    store = DiscoveryStore(tmp_path / 'state')
    reader = make_daily_reader(cfg, lambda c, s, e, k: envelope(c, s, e, [{'id': 't1', 'messages': [msg], 'complete': True}]), snapshot_root=tmp_path / 'cache')
    receipt = SourceAdapter(store, cfg, read_page=reader).collect('s', start=START, end=END)
    assert receipt['status'] == 'complete'
    assert len(store.source_state('s', cfg['source_key'])['backlog']) == 1
    assert extract_body_text({'mimeType': 'text/plain', 'body': {'data': base64.urlsafe_b64encode(b' \r\n\t ').decode()}}) == ''
