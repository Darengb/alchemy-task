"""Current-runtime contract checks, skipped only when Hermes is not installed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from test_discovery_runner import setup_runner


def test_next_turn_hook_uses_public_context_contract(tmp_path):
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    pointer = runner.pre_llm_call(session_id='parent')
    assert 'context' in pointer and run in pointer['context']
    assert 'SAME' in pointer['context'] and not pool.requests
    assert runner.pre_llm_call(session_id='foreign') is None


def test_current_runtime_dataclass_contract_without_active_parent():
    api = pytest.importorskip('agent.subagent_lifecycle')
    from alchemy_task.discovery_runner import normalize
    status = api.SubagentStatus(handle=None, state=api.SubagentState.RUNNING, updated_at=12.)
    assert normalize(status)['state'] == 'RUNNING'
    service = api.SubagentLifecycleService(lambda: None)
    with pytest.raises(api.SubagentLifecycleError, match='active Hermes parent'):
        service.launch({'goal': 'Synthetic no-parent negative contract', 'role': 'leaf'})


def test_isolated_actual_host_registration_reports_unknown_not_retry(tmp_path):
    pytest.importorskip('hermes_cli.plugins')
    root = Path(__file__).resolve().parents[1]
    home = tmp_path / 'hermes-home'; plugin = home / 'plugins' / 'runner-contract'
    plugin.mkdir(parents=True)
    shutil.copytree(root / 'core', plugin / 'core')
    shutil.copytree(root / 'schemas', plugin / 'schemas')
    for n in ('discovery_runner.py',): shutil.copy2(root / n, plugin / n)
    (plugin / 'plugin.yaml').write_text('name: runner-contract\nversion: 0.1.0\ndescription: Synthetic isolated runner contract\nauthor: Test\n')
    # No parent, credentials, settings or task mutation API. Exercise the real
    # registered handler through the actual host wire; launch must fail closed.
    (plugin / '__init__.py').write_text('''import json
from pathlib import Path
from types import SimpleNamespace
from .discovery_runner import DiscoveryRunner, make_tool_handlers, make_hooks
from .core.discovery_state import DiscoveryStore

def register(ctx):
    store = DiscoveryStore(Path(ctx.state.data_dir) / 'discovery')
    def invoke(args, session_id='', **kwargs):
        run = store.init_run(origin={'session_id': session_id})
        store.add_candidates(run, [{'title': 'Synthetic work', 'source_ids': ['source:source:account:thread:one']}])
        store.freeze_index(run, rubric='Full synthetic evidence only')
        runner = DiscoveryRunner(ctx, SimpleNamespace(data_dir=ctx.state.data_dir), store=store)
        result = make_tool_handlers(runner)['discovery_research_run']({'run_id': run}, session_id=session_id)
        return json.dumps({'result': json.loads(result), 'attempts': store.get_run(run)['attempts']})
    ctx.register_tool(name='runner_contract', toolset='runner-contract', handler=invoke, schema={'name': 'runner_contract', 'description': 'Synthetic runner negative contract', 'parameters': {'type': 'object', 'properties': {}}})
''')
    (home / 'config.yaml').write_text('plugins:\n  enabled: [runner-contract]\n  isolation: host\n')
    script = '''import os,json
from hermes_cli.plugins import PluginManager
from model_tools import handle_function_call
m=PluginManager(scope_key=os.environ['HERMES_HOME']); m.discover_and_load()
try:
 print(handle_function_call('runner_contract',{},session_id='synthetic-parent'))
finally:
 m.unload()
'''
    env = {**os.environ, 'HERMES_HOME': str(home), 'HERMES_PLUGIN_HOST': '1'}
    proc = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=45)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert 'result' in data, (data, proc.stderr)
    assert data['result']['ok'] is True, data
    # The unknown launch is fenced: research is complete but join will need
    # an explicit degraded acknowledgement; nothing is relaunched.
    assert data['result']['result']['status'] == 'complete'
    assert len(data['result']['result']['unknown_candidates']) == 1
    attempts = list(data['attempts'].values())
    assert len(attempts) == 1 and attempts[0]['state'] == 'launch_unknown'
    assert attempts[0]['ordinal'] == 1 and not attempts[0]['terminal']
