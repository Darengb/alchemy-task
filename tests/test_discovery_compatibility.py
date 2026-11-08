"""Compatibility names cannot bypass source-first acceptance and global join."""
import json
from alchemy_task import task_tools
from test_setup import home
from test_discovery import ctx, make_stream, tool, CANDS


def test_legacy_freeform_submit_does_not_propose_or_create(ctx):
    make_stream()
    result = tool(task_tools.discovery_submit, stream='work', candidates=CANDS, coverage=[])
    assert result['ok'] is False
    assert 'research' in str(result).lower() or 'run_id' in str(result)
    assert not (ctx.state.get('proposals:work') or {}).get('items')


def test_legacy_decide_cannot_turn_unresearched_candidates_into_tasks(ctx):
    make_stream()
    tool(task_tools.discovery_submit, stream='work', candidates=CANDS, coverage=[])
    before = list(__import__('pathlib').Path(ctx.get_config('workspace_root')).rglob('*.md'))
    result = tool(task_tools.discovery_decide, approve=['1'])
    assert result['ok'] is False
    assert list(__import__('pathlib').Path(ctx.get_config('workspace_root')).rglob('*.md')) == before
