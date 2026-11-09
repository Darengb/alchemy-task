"""Executed only in a disposable subprocess with synthetic HERMES_HOME.

The host dashboard SPA appends ?profile=<serving profile> to every
/api/plugins/ request. Through the real host mount, real auth and a real Git
workspace with a local bare remote, every discovery route must accept the
serving profile's own selector and keep refusing a different profile.

argv: plugin_root synthetic_home core_root [extra_sys_path]
"""
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

root, home, core_root = map(Path, sys.argv[1:4])
sys.path.insert(0, str(core_root))
if len(sys.argv) > 4:
    sys.path.extend(x for x in sys.argv[4].split(os.pathsep) if x)


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


(home / 'userhome').mkdir()
(home / 'userhome' / '.gitconfig').write_text('[user]\n\tname = Probe\n\temail = probe@example.test\n[init]\n\tdefaultBranch = main\n')
os.environ['HOME'] = str(home / 'userhome')
remote, ws = home / 'remote.git', home / 'ws'
ws.mkdir()
subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
git(ws, 'init', '-q', '-b', 'main')
for area in ('work', 'home'):
    (ws / 'areas' / area / 'tasks').mkdir(parents=True)
    (ws / 'areas' / area / 'tasks' / '.keep').write_text('')
git(ws, 'add', '-A'); git(ws, 'commit', '-q', '-m', 'init')
git(ws, 'remote', 'add', 'origin', str(remote)); git(ws, 'push', '-q', 'origin', 'main')

from hermes_cli import profiles
profiles._get_default_hermes_home = lambda: home
profiles._get_profiles_root = lambda: home / 'profiles'
installed = home / 'plugins' / 'alchemy-task'
shutil.copytree(root, installed, ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache', 'tests'))
(home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['alchemy-task'], 'isolation': 'in_process',
    'entries': {'alchemy-task': {'settings': {'timezone': 'America/New_York', 'workspace_root': str(ws)}}}}}))
beta = home / 'profiles' / 'beta'; beta.mkdir(parents=True)
(beta / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': [], 'isolation': 'in_process'}}))

from hermes_cli import web_server
from hermes_cli.web_server_dashboard import _mount_plugin_api_routes
from hermes_cli.web_server_profiles import serving_profile_name
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from starlette.testclient import TestClient


async def socket_peer(scope, receive, send):
    scope['hermes.gateway_socket_peer'] = ('127.0.0.1', 50000)
    await web_server.app(scope, receive, send)


client = TestClient(socket_peer)
owner = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}
_mount_plugin_api_routes()
mounted = sys.modules['hermes_dashboard_plugin_alchemy-task']
api = importlib.import_module(mounted._name + '.dashboard.discovery_api')

# Seed one real joined production run holding two proposals, using the
# repository's own synthetic helpers (a second package copy, files only).
spec = importlib.util.spec_from_file_location('alchemy_task', root / '__init__.py', submodule_search_locations=[str(root)])
module = importlib.util.module_from_spec(spec); sys.modules['alchemy_task'] = module; spec.loader.exec_module(module)
sys.path.insert(0, str(root / 'tests'))
from test_discovery_state import setup, prepare, read_all
from test_discovery_schema import bundle

token = set_hermes_home_override(str(home))
try:
    service = api._service()
    store, run, items = setup(service.rt.data_dir, count=2)
    for index, item in enumerate(items):
        attempt = prepare(store, run, item['candidate_id'])
        payload = bundle(); payload['candidate_id'] = item['candidate_id']
        payload['workstreams'][0]['exact_source_ids'][0]['message_ts'] = f'171.{index + 2}'
        payload['workstreams'][0]['title'] = f'Independent action {index}'
        receipt = store.spool_payload(run, attempt['token'], payload)
        store.observe_terminal(run, attempt['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
        read_all(store, run, receipt['resource'], 'parent')
        store.accept_attempt(run, attempt['token'], payload_sha256=receipt['payload_sha256'],
                             assessment={'accepted': True, 'reason': 'Distinct substantive action fully verified.'}, reader='parent')
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [x['candidate_id'] for x in items], 'failures': []})
    service = api._service()
    service.rt.ctx.state.set('streams', {'work': {'name': 'work', 'label': '', 'origin_session': 'parent'}})
    with service.store._lock(service.store._run_lock_name(run)):
        ledger = service.store.get_run(run); ledger['origin'] = {'session_id': 'parent', 'deliver': 'origin'}
        ledger['config']['timezone'] = 'America/New_York'; service.store._save(run, ledger)
    for candidate in service.store.get_run(run)['candidates']:
        if candidate.get('parent_candidate_id'):
            service.record_decision(run, candidate['candidate_id'], decision='propose', reason='Independent untracked ask.', session_id='parent')
    digest = service.finalize(run, session_id='parent')
finally:
    reset_hermes_home_override(token)
assert len(digest['items']) == 2, digest['items']
prop_a, prop_b = digest['items']
wid_a = prop_a['unit_id']

serving = serving_profile_name()
assert serving == 'default', serving
base = '/api/plugins/alchemy-task'
mine = '?profile=' + serving
other = '?profile=beta'


def snapshot():
    files = sorted(str(p.relative_to(ws)) for p in ws.glob('areas/*/tasks/*.md'))
    return files, git(ws, 'rev-parse', 'HEAD'), git(remote, 'rev-parse', 'main')


start = snapshot()
run_a = run

# A different profile is still refused and writes nothing.
for method, path in (('get', '/runs'), ('get', '/runs/' + run_a), ('post', '/proposals/' + prop_a['proposal_id'] + '/approve'),
                     ('post', '/proposals/' + prop_b['proposal_id'] + '/dismiss'), ('post', '/runs/' + run_a + '/units/' + wid_a + '/resume')):
    kwargs = {'json': {'choice': 'create', 'due': '2030-01-09', 'area': 'work'}} if path.endswith('approve') else ({'json': {}} if method == 'post' else {})
    response = getattr(client, method)(base + path + other, headers=owner, **kwargs)
    assert response.status_code >= 400, (path, response.status_code, response.text)
assert snapshot() == start

# The serving profile's own selector is accepted on every route.
listed = client.get(base + '/runs' + mine, headers=owner)
assert listed.status_code == 200 and [r['run_id'] for r in listed.json()['runs']] == [run_a], listed.text
listed = client.get(base + '/runs' + mine + '&stream=work', headers=owner)
assert listed.status_code == 200 and len(listed.json()['runs']) == 1, listed.text
detail = client.get(base + '/runs/' + run_a + mine, headers=owner)
assert detail.status_code == 200 and detail.json()['run_id'] == run_a, detail.text

approved = client.post(base + '/proposals/' + prop_a['proposal_id'] + '/approve' + mine, headers=owner,
                       json={'choice': 'create', 'due': '2030-01-09', 'area': 'work'})
assert approved.status_code == 200 and approved.json()['receipt']['state'] == 'complete', approved.text
after = snapshot()
new_files = sorted(set(after[0]) - set(start[0]))
assert len(new_files) == 1 and new_files[0].startswith('areas/work/'), new_files
assert git(ws, 'rev-list', '--count', start[1] + '..' + after[1]) == '1' and after[1] == after[2]
assert 'discovery-dossier:start' in (ws / new_files[0]).read_text()

resumed = client.post(base + '/runs/' + run_a + '/units/' + wid_a + '/resume' + mine, headers=owner, json={})
assert resumed.status_code == 200 and resumed.json()['receipt']['state'] == 'complete', resumed.text
assert snapshot() == after

dismissed = client.post(base + '/proposals/' + prop_b['proposal_id'] + '/dismiss' + mine, headers=owner, json={})
assert dismissed.status_code == 200 and dismissed.json()['state'] == 'dismissed', dismissed.text
assert snapshot() == after
states = {p['proposal_id']: p['state'] for p in client.get(base + '/runs/' + run_a + mine, headers=owner).json()['proposals']}
assert states == {prop_a['proposal_id']: 'complete', prop_b['proposal_id']: 'dismissed'}, states
print('serving profile selector PASS')
