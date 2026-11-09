import pytest
from alchemy_task.discovery_digest import DiscoveryDigest


@pytest.mark.parametrize('kind', ['complete', 'partial', 'failure', 'existing'])
def test_empty_discovery_reports_result_without_hiding_incomplete_work(tmp_path, kind):
    digest = DiscoveryDigest(tmp_path)
    kwargs = {'coverage': [{'source_key': 'inbox', 'status': 'complete'}]}
    if kind == 'partial':
        kwargs['coverage'][0]['status'] = 'partial'
    elif kind == 'failure':
        kwargs['failures'] = [{'title': 'Supplier response', 'error': 'research failed'}]
    elif kind == 'existing':
        kwargs['outcomes'] = [{'title': 'Review supplier proof', 'status': 'updated'}]
    result = digest.prepare('empty-' + kind, stream='work', day='2030-01-01',
                            origin={'session_id': 'origin'}, items=[], **kwargs)
    text = result['text']
    assert text.strip() and '[SILENT]' not in text
    assert not result['items']
    if kind == 'complete':
        assert 'No new follow-ups found.' in text
    else:
        assert 'No new follow-ups found.' not in text
        assert 'No new proposals to review.' in text
    if kind in {'partial', 'failure'}:
        assert 'degraded' in text
    if kind == 'existing':
        assert 'Review supplier proof: updated' in text
    assert 'Reply with the numbers you want.' not in text
    assert digest.prepare('empty-' + kind, stream='work', day='2030-01-01',
                          origin={'session_id': 'origin'}, items=[], **kwargs) == result
