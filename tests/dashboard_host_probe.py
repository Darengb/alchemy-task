"""Executed only in a disposable subprocess with synthetic HERMES_HOME."""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

root, home, core_root = map(Path, sys.argv[1:])
sys.path.insert(0, str(core_root))
from hermes_constants import get_hermes_home
assert get_hermes_home().resolve() == home.resolve()
from hermes_cli import profiles
profiles._get_default_hermes_home = lambda: home
profiles._get_profiles_root = lambda: home / 'profiles'

installed = home / 'plugins' / 'alchemy-task'
shutil.copytree(root, installed, ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache', 'tests'))
(home / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['alchemy-task'], 'isolation': 'in_process',
    'entries': {'alchemy-task': {'settings': {'timezone': 'UTC'}}}}}))
from hermes_cli import web_server
from hermes_cli.web_server_dashboard import _mount_plugin_api_routes
from hermes_cli.plugins import PluginContext, PluginManifest
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from gateway.runtime_bootstrap import TicketStore
from gateway.session_authorities import SessionAuthorities
from starlette.testclient import TestClient

# Actual native credentials, minted by the host's TicketStore for served profiles.
beta = home / 'profiles' / 'beta'; beta.mkdir(parents=True)
(beta / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': [], 'isolation': 'in_process'}}))
authorities = SessionAuthorities(home, multiplexed=True)
for profile in (home, beta):
    authorities.add(profile, SimpleNamespace(profile_id=str(profile), instance_id='synthetic-daemon'))
tickets = TicketStore('synthetic-daemon', authorities.profile_ids())
web_server.app.state.gateway_runner = SimpleNamespace(session_authorities=authorities, session_ticket_store=tickets,
    _draining=False, session_runtime_descriptor={'state': 'ready', 'instance_id': 'synthetic-daemon', 'served_profiles': authorities.served_profiles()})

async def socket_peer(scope, receive, send):
    scope['hermes.gateway_socket_peer'] = ('127.0.0.1', 50000)
    await web_server.app(scope, receive, send)

client = TestClient(socket_peer)
owner = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}
def native(profile):
    return {'X-Hermes-Gateway-Ticket': tickets.mint(profile_id=str(profile), subject='desktop', purpose='native-http')}

_mount_plugin_api_routes()
import importlib
mounted = sys.modules['hermes_dashboard_plugin_alchemy-task']
discovery_api = importlib.import_module(mounted._name + '.dashboard.discovery_api')
for profile, streams in ((home, ['alpha', 'second']), (beta, ['beta'])):
    token = set_hermes_home_override(str(profile))
    try:
        service = discovery_api._service()
        for stream in streams:
            service.store.init_run(stream=stream, business_date='2030-01-01',
                config={'stream_name': stream, 'mode': 'production', 'timezone': 'UTC', 'sources': []},
                origin={'session_id': 'synthetic-origin-' + stream})
    finally:
        reset_hermes_home_override(token)
base = '/api/plugins/alchemy-task'
unauthorized = client.get(base + '/runs')
assert unauthorized.status_code == 401, unauthorized.text
for claims in ({'dashboard_owner': 'true'}, {'authenticated': 'true'}, {'session_id': 'parent'}):
    response = client.get(base + '/runs', params=claims, headers={'X-Hosted-Http-Authenticated': 'true'})
    assert response.status_code == 401, response.text
response = client.get(base + '/runs', headers=owner)
assert response.status_code == 200 and {r['stream'] for r in response.json()['runs']} == {'alpha', 'second'}, response.text
assert {r['stream'] for r in client.get(base + '/runs', headers=native(home)).json()['runs']} == {'alpha', 'second'}
assert client.get(base + '/runs', headers=native(beta)).status_code == 404
assert client.get(base + '/runs?profile=beta', headers=native(home)).status_code == 403
for query in ('profile=beta', 'session_id=parent', 'origin_session=parent', 'owner=true'):
    assert client.get(base + '/runs?' + query, headers=owner).status_code in {400, 404}
for body in ({'profile': str(beta)}, {'session_id': 'parent'}, {'dashboard_owner': True}):
    response = client.post(base + '/proposals/p_missing/approve', headers=owner, json=body)
    assert response.status_code == 400 and response.json()['error']['code'] == 'invalid_request', response.text
# Request scoping cannot leak into the next launch-profile request.
assert {r['stream'] for r in client.get(base + '/runs', headers=owner).json()['runs']} == {'alpha', 'second'}
# Enable the secondary copy, then exercise the actual private plugin-host IPC
# and host-issued profile credential, not a fake request.state principal.
(beta / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['alchemy-task'], 'isolation': 'in_process'}}))
from hermes_cli.web_server_plugin_profiles import profile_dashboard_plugins
profile_dashboard_plugins(beta, force_rescan=True)
try:
    response = client.get(base + '/runs', headers=native(beta))
    assert response.status_code == 200 and {r['stream'] for r in response.json()['runs']} == {'beta'}, response.text
    assert {r['stream'] for r in client.get(base + '/runs', headers=native(home)).json()['runs']} == {'alpha', 'second'}
finally:
    from hermes_cli.plugins import get_plugin_manager
    token = set_hermes_home_override(str(beta))
    try:
        get_plugin_manager()._plugin_host().shutdown()
    finally:
        reset_hermes_home_override(token)
print('actual host mount/auth/profile PASS')
