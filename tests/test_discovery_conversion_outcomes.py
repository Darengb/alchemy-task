"""Outcome tests for discovery conversion and task mutation.

Each test asserts what a user can observe: task files on disk, frontmatter and
body text, proposal state, conversion receipts and Git objects. Fixtures are
synthetic.
"""
import json
import re
import subprocess
from types import SimpleNamespace

import pytest

from alchemy_task.core import taskfile as tf
from alchemy_task.core.config import Settings
from alchemy_task.core.discovery_dossiers import content_revision
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.discovery_state import read_json
from alchemy_task.core.gitops import GitDelivery
from alchemy_task.core.store import TaskStore

SLACK_ID = {'type': 'slack', 'workspace_id': 'T1', 'channel_id': 'C1', 'thread_root_ts': '171.1', 'message_ts': '171.2'}


# ---------------------------------------------------------------- fixtures
def _accept(store, run, cid, payload):
    from test_discovery_state import prepare, read_all
    attempt = prepare(store, run, cid)
    receipt = store.spool_payload(run, attempt['token'], payload)
    store.observe_terminal(run, attempt['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
    read_all(store, run, receipt['resource'], 'parent')
    store.accept_attempt(run, attempt['token'], payload_sha256=receipt['payload_sha256'],
                         assessment={'accepted': True, 'reason': 'Synthetic full evidence verified.'}, reader='parent')
    return store.accepted_bundle(run, cid)['workstream_ids']


def _conversion(settings, data_dir, store):
    from alchemy_task.discovery_conversion import DiscoveryConversion
    rt = SimpleNamespace(data_dir=data_dir, settings=settings, store=lambda: TaskStore(settings, data_dir),
                         git=lambda: GitDelivery(settings, data_dir))
    return rt, DiscoveryConversion(rt, store)


def _one_unit(settings, data_dir, **changes):
    from test_discovery_state import setup
    from test_discovery_schema import bundle
    store, run, items = setup(data_dir)
    payload = bundle(); payload['candidate_id'] = items[0]['candidate_id']; payload['workstreams'][0].update(**changes)
    wid = _accept(store, run, items[0]['candidate_id'], payload)[0]
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [items[0]['candidate_id']], 'failures': []})
    rt, conv = _conversion(settings, data_dir, store)
    return rt, store, run, wid, conv


def _next_day_same_unit(store, wid, new_information, understanding):
    from test_discovery_schema import bundle
    run = store.init_run(stream='work', business_date='2030-01-02', config={'sources': ['work'], 'mode': 'production'})
    items = store.add_candidates(run, [{'title': 'Ask 0', 'source_ids': [dict(SLACK_ID)]}])
    store.freeze_index(run, rubric='Read complete sources.')
    payload = bundle(); payload['candidate_id'] = items[0]['candidate_id']
    payload['workstreams'][0].update(new_information=new_information, current_understanding=understanding)
    assert _accept(store, run, items[0]['candidate_id'], payload)[0] == wid  # stable dossier identity
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [items[0]['candidate_id']], 'failures': []})
    return run


def _integration(settings, data_dir, tmp_path, count=2):
    """Production run whose accepted units are independent new proposals in one digest."""
    from test_discovery_integration import service
    from test_discovery_state import setup
    from test_discovery_schema import bundle
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    store, run, items = setup(data_dir, count=count)
    integration.store = store; integration.conversion.store = store
    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run); ledger['origin'] = {'session_id': 'parent'}; store._save(run, ledger)
    for index, item in enumerate(items):
        payload = bundle(); payload['candidate_id'] = item['candidate_id']
        payload['workstreams'][0]['exact_source_ids'][0]['message_ts'] = f'171.{index + 2}'
        payload['workstreams'][0]['title'] = f'Independent action {index}'
        _accept(store, run, item['candidate_id'], payload)
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [x['candidate_id'] for x in items], 'failures': []})
    return integration, rt, ctx, store, run


def _propose_all(integration, store, run):
    for candidate in store.get_run(run)['candidates']:
        if candidate.get('parent_candidate_id'):
            integration.record_decision(run, candidate['candidate_id'], decision='propose', reason='Independent untracked ask.', session_id='parent')
    return integration.finalize(run, session_id='parent')


def _proposal_states(integration, run):
    return {str(p['number']): p['state'] for p in integration.backend(run, session_id='parent')['proposals']}


def _plain_workspace(tmp_path, *, git_repo):
    ws = tmp_path / 'plainws'
    (ws / 'areas' / 'work' / 'tasks').mkdir(parents=True)
    (ws / 'areas' / 'work' / 'tasks' / '.keep').write_text('')
    if git_repo:
        for args in (['init', '-q', '-b', 'main'], ['add', '-A'], ['commit', '-qm', 'init']):
            subprocess.run(['git', *args], cwd=ws, check=True)
    return ws, Settings(workspace_root=str(ws), timezone='America/New_York', git_run_hooks=True)


def _register_tools(integration, ctx):
    from alchemy_task.discovery_integration import register
    tools = {}
    ctx.register_tool = lambda **kw: tools.update({kw['name']: kw['handler']})
    ctx.register_hook = lambda *a, **kw: None
    register(ctx, integration=integration)
    return tools


# ---------------------------------------------------------------- F1 local_only / no_git
@pytest.mark.parametrize('git_repo,expected', [(True, 'local_only'), (False, 'no_git')], ids=['repo_without_remote', 'not_a_git_repo'])
def test_conversion_in_workspace_without_remote_or_git_completes_honestly(tmp_path, workspace, data_dir, git_repo, expected):
    ws, settings = _plain_workspace(tmp_path, git_repo=git_repo)
    core_task = TaskStore(settings, data_dir).create(title='Core task', area='work', undated=True, research=False)
    core = GitDelivery(settings, data_dir).deliver([TaskStore(settings, data_dir).rel(core_task.path)], 'task: create')
    assert core['state'] == expected
    integration, rt, ctx, store, run = _integration(settings, data_dir / 'discovery', tmp_path, count=1)
    _propose_all(integration, store, run)
    out = integration.decide({'approve': ['1'], 'day': '2030-01-01', 'edits': {'1': {'area': 'work', 'undated': True}}},
                             session_id='parent', today='2030-01-02')
    receipt = out['results'][0]
    path = ws / receipt['path']
    assert path.is_file() and tf.content_hash(path.read_bytes()) == receipt['local']['sha256']
    assert receipt['state'] == 'complete' and receipt['git']['state'] == expected, receipt
    assert 'ls-remote' not in json.dumps(receipt) and 'rev-parse failed' not in json.dumps(receipt)
    assert _proposal_states(integration, run) == {'1': 'complete'}
    if git_repo:  # committed locally, exact bytes at HEAD
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ws, capture_output=True, text=True, check=True).stdout.strip()
        blob = subprocess.run(['git', 'show', 'HEAD:' + receipt['path']], cwd=ws, capture_output=True, check=True).stdout
        assert receipt['git']['commit'] == head and blob == path.read_bytes()
    # Resume is idempotent and stays terminal.
    again = integration.conversion.deliver_git(receipt['run_id'], receipt['unit_id'])
    assert again['state'] == 'complete' and again['git']['state'] == expected
    assert len(list((ws / 'areas' / 'work' / 'tasks').glob('*.md'))) == 2


# ---------------------------------------------------------------- F2 batch with an already-complete proposal
def test_batch_approval_reports_complete_item_as_done_and_still_creates_new_item(settings, data_dir, tmp_path):
    integration, rt, ctx, store, run = _integration(settings, data_dir, tmp_path)
    _propose_all(integration, store, run)
    edits = {'1': {'area': 'work', 'undated': True}, '2': {'area': 'work', 'undated': True}}
    first = integration.decide({'approve': ['1'], 'day': '2030-01-01', 'edits': {'1': edits['1']}}, session_id='parent', today='2030-01-02')
    assert first['results'][0]['state'] == 'complete'
    task_id = first['results'][0]['task_id']
    rt.store().update(task_id, {'notes_append': 'My own follow-up note.'})  # normal user edit afterwards
    edited = rt.store().resolve(task_id).path.read_bytes()
    before = len(rt.store().scan().tasks)
    out = integration.decide({'approve': ['1', '2'], 'day': '2030-01-01', 'edits': edits}, session_id='parent', today='2030-01-02')
    done, created = out['results']
    assert done['task_id'] == task_id and done['state'] == 'complete' and done.get('already_complete') is True
    assert rt.store().resolve(task_id).path.read_bytes() == edited
    assert created['state'] == 'complete' and created['task_id'] != task_id and not created.get('already_complete')
    assert len(rt.store().scan().tasks) == before + 1
    assert _proposal_states(integration, run) == {'1': 'complete', '2': 'complete'}


# ---------------------------------------------------------------- F3 repeat enrichment keeps earlier context
def test_later_enrichment_of_same_unit_appends_context_and_keeps_earlier(settings, data_dir, tmp_path):
    tasks = TaskStore(settings, data_dir)
    task = tasks.create(title='Launch work', area='work', undated=True, research=False, notes='User words. slack:T1:C1:171.1:171.2')
    rt, store, run1, wid, conv = _one_unit(settings, data_dir, new_information=['Earlier finding: vendor approved budget.'])
    conv.prepare(run1, wid, choice='auto', useful_delta=True, reason='Useful verified delta.', target_task_id=task.task_id,
                 expected_revision=tf.content_hash(tf.parse_file(task.path).raw))
    conv.apply(run1, wid)
    run2 = _next_day_same_unit(store, wid, ['Later finding: launch moved to Friday.'], 'Launch is Friday.')
    outcome = conv.match(run2, wid)
    assert outcome['kind'] == 'exact'
    plan2 = conv.prepare(run2, wid, choice='auto', useful_delta=True, reason='New verified delta.', target_task_id=task.task_id,
                         expected_revision=outcome['targets'][0]['revision'])
    conv.apply(run2, wid)
    body = tf.parse_file(task.path).body
    notes = body.split('## Notes', 1)[1].split('\n## ', 1)[0]
    assert 'User words.' in notes
    assert 'Earlier finding: vendor approved budget.' in notes and 'Later finding: launch moved to Friday.' in notes
    assert notes.index('Earlier finding') < notes.index('Later finding')
    assert notes.count('### Discovery context') == 2
    assert body.count('Discovery context added') == 2
    dossier = 'dos-' + wid[2:]
    assert body.count(f'<!-- discovery-dossier:start {dossier} -->') == 1
    assert f"**Content revision:** `{plan2['dossier_revision']}`" in body


# ---------------------------------------------------------------- M6 visible Log line
def test_enrichment_adds_one_dated_log_line_naming_the_revision(settings, data_dir, tmp_path):
    tasks = TaskStore(settings, data_dir)
    task = tasks.create(title='Launch work', area='work', undated=True, research=False, notes='slack:T1:C1:171.1:171.2')
    rt, store, run, wid, conv = _one_unit(settings, data_dir, new_information=['Vendor approved budget.'])
    plan = conv.prepare(run, wid, choice='auto', useful_delta=True, reason='Useful verified delta.', target_task_id=task.task_id,
                        expected_revision=tf.content_hash(tf.parse_file(task.path).raw))
    conv.apply(run, wid)
    log = tf.parse_file(task.path).body.split('## Log', 1)[1].split('\n## ', 1)[0]
    assert f"- {settings.today()}: Discovery context added ({plan['dossier_revision']})." in log
    conv.apply(run, wid)  # idempotent resume adds nothing
    assert tf.parse_file(task.path).body.count('Discovery context added') == 1


# ---------------------------------------------------------------- M10 stale read at prepare
def test_prepare_with_outdated_task_revision_is_refused_without_plan(settings, data_dir, tmp_path):
    tasks = TaskStore(settings, data_dir)
    task = tasks.create(title='Launch work', area='work', undated=True, research=False, notes='slack:T1:C1:171.1:171.2')
    rt, store, run, wid, conv = _one_unit(settings, data_dir, new_information=['Vendor approved budget.'])
    old_revision = conv.match(run, wid)['targets'][0]['revision']
    tasks.update(task.task_id, {'notes_append': 'User edit after the read.'})
    edited = task.path.read_bytes()
    with pytest.raises(tf.ConcurrentEditError):
        conv.prepare(run, wid, choice='auto', useful_delta=True, reason='Useful verified delta.', target_task_id=task.task_id,
                     expected_revision=old_revision)
    assert task.path.read_bytes() == edited
    assert not (store.run_dir(run) / 'conversions' / (wid + '.plan.json')).exists()


# ---------------------------------------------------------------- M2 exact proposal cannot become a plain proposal
def test_exact_destination_cannot_be_recorded_as_a_user_proposal(settings, data_dir, tmp_path):
    integration, rt, ctx, store, run = _integration(settings, data_dir, tmp_path, count=1)
    unit = next(c['candidate_id'] for c in store.get_run(run)['candidates'] if c.get('parent_candidate_id'))
    task = rt.store().create(title='Existing action', area='work', undated=True, research=False, notes='slack:T1:C1:171.1:171.2')
    before = task.path.read_bytes()
    with pytest.raises(UserError, match='unique exact target'):
        integration.record_decision(run, unit, decision='propose', reason='Looks new.', session_id='parent')
    assert not (store.run_dir(run) / 'decisions' / (unit + '.json')).exists()
    with pytest.raises(UserError, match='decision missing'):
        integration.finalize(run, session_id='parent')
    assert task.path.read_bytes() == before and integration.digest._load()['proposals'] == {}


# ---------------------------------------------------------------- M7 chat approval completes the proposal
def test_chat_approval_marks_proposal_complete_and_remote_has_the_task(settings, data_dir, tmp_path, workspace):
    integration, rt, ctx, store, run = _integration(settings, data_dir, tmp_path, count=1)
    _propose_all(integration, store, run)
    assert _proposal_states(integration, run) == {'1': 'pending'}
    out = integration.decide({'approve': ['1'], 'day': '2030-01-01', 'edits': {'1': {'area': 'work', 'undated': True}}},
                             session_id='parent', today='2030-01-02')
    receipt = out['results'][0]
    assert receipt['state'] == 'complete' and receipt['git']['state'] == 'verified'
    assert _proposal_states(integration, run) == {'1': 'complete'}
    remote = tmp_path / 'remote.git'
    blob = subprocess.run(['git', '--git-dir', str(remote), 'show', 'main:' + receipt['path']], capture_output=True, check=True).stdout
    assert blob == (workspace / receipt['path']).read_bytes()


# ---------------------------------------------------------------- M4 committed tree must hold the exact bytes
def test_hook_rewritten_commit_is_not_reported_verified(settings, data_dir, tmp_path, workspace):
    hook = workspace / '.git' / 'hooks' / 'pre-commit'
    hook.write_text('#!/bin/sh\nfor f in $(git diff --cached --name-only); do echo "hook rewrote" >> "$f"; git add "$f"; done\n')
    hook.chmod(0o755)
    rt, store, run, wid, conv = _one_unit(settings, data_dir)
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.')
    receipt = conv.deliver_git(run, wid)
    committed = subprocess.run(['git', 'show', 'HEAD:' + receipt['path']], cwd=workspace, capture_output=True, check=True).stdout
    assert b'hook rewrote' in committed  # the fixture really rewrote the commit
    assert receipt['git']['state'] != 'verified' and receipt['state'] != 'complete'
    assert 'committed tree' in receipt['git'].get('reason', '')


