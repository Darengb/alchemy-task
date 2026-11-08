import json
from pathlib import Path
import pytest
from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.core.discovery_identity import UserError


def test_inventory_freezes_all_statuses_and_full_body(settings, data_dir, tmp_path):
    from alchemy_task.discovery_context import DiscoveryContext
    from alchemy_task.runtime import Runtime
    rt = Runtime(settings=settings, data_dir=data_dir)
    store = DiscoveryStore(data_dir / 'discovery')
    run = store.init_run()
    skills = tmp_path / 'skills'
    (skills / 'guide').mkdir(parents=True)
    text = 'All relevant guidance\n' * 4000
    (skills / 'guide' / 'SKILL.md').write_text(text)
    ctx = DiscoveryContext(rt, store, installed_skills_root=skills)
    resources = ctx.freeze(run, source_config={'scope': 'approved'}, rubric='primary then tasks', skills=['guide'])
    inventory = json.loads((store.run_dir(run) / 'resources' / resources['task_inventory']['sha256']).read_text())
    assert len(inventory['tasks']) == len(rt.store().scan().tasks)
    assert {x['status'] for x in inventory['tasks']} >= {'done'}
    skill = resources['skill-guide']
    page = store.fetch_resource(run, skill['name'], revision=skill['sha256'], reader='test', limit=8192)
    chunks = [page['content']]
    while page['has_more']:
        page = store.fetch_resource(run, skill['name'], revision=skill['sha256'], reader='test', cursor=page['next_cursor'])
        chunks.append(page['content'])
    assert ''.join(chunks) == text
    assert ctx.freeze(run, source_config={'scope': 'approved'}, rubric='primary then tasks', skills=['guide']) == resources


def test_installed_skill_inventory_and_context_scopes(settings, data_dir, tmp_path):
    from alchemy_task.discovery_context import DiscoveryContext
    from alchemy_task.runtime import Runtime
    store = DiscoveryStore(data_dir / 'discovery'); run = store.init_run()
    skills = tmp_path / 'skills'; (skills / 'one').mkdir(parents=True); (skills / 'two').mkdir()
    (skills / 'one' / 'SKILL.md').write_text('Complete first skill')
    (skills / 'two' / 'SKILL.md').write_text('Complete second skill')
    ctx = DiscoveryContext(Runtime(settings=settings, data_dir=data_dir), store, installed_skills_root=skills)
    resources = ctx.freeze(run, source_config={}, rubric='Full context', skills=['one'])
    assert 'skill-inventory' in resources
    inventory = json.loads((store.run_dir(run) / 'resources' / resources['skill-inventory']['sha256']).read_text())
    assert [x['name'] for x in inventory] == ['one', 'two']
    assert inventory[1]['resource']['total_bytes'] == len('Complete second skill')


def test_identity_never_infers_local_part_or_unconfirmed_alias():
    from alchemy_task.discovery_context import resolve_identity
    result = resolve_identity({'account_key': 'account', 'email': 'somebody@example.test'}, [])
    assert result['status'] == 'needs_input'
    assert 'name' in result['missing']
    result = resolve_identity({'account_key': 'account'}, [{'account_key': 'account', 'name': 'Example Person', 'aliases': ['Example'], 'confirmed': True}])
    assert result['status'] == 'ready'
    assert result['identity']['name'] == 'Example Person'
    assert result['persist_confirmation'] is True
