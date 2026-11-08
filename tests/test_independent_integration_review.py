"""Scratch-only independent ordinary-use contract probes against 0be48eb."""
import pytest
from test_discovery_conversion import custom_joined
from test_discovery_integration import service, configure
from alchemy_task.core import taskfile as tf
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.store import TaskStore


def test_semantic_prepared_update_refuses_new_exact_elsewhere(settings, data_dir, tmp_path):
    tasks = TaskStore(settings, data_dir)
    selected = tasks.create(title='Semantically related original', area='work', undated=True, research=False)
    rt, store, run, wid, conversion = custom_joined(settings, data_dir, tmp_path,
        [{'path': tasks.rel(selected.path), 'match_basis': 'related_only'}])
    conversion.prepare(run, wid, choice='update', user_approved=True,
        reason='User selected semantic original.', target_task_id=selected.task_id,
        expected_revision=tf.content_hash(selected.raw))
    exact = tasks.create(title='Exact source task added before conversion resume', area='work', undated=True,
        research=False, notes='slack:T1:C1:171.1:171.2')
    current = conversion.match(run, wid)
    assert current['kind'] == 'exact' and current['targets'][0]['task_id'] == exact.task_id
    before = selected.path.read_bytes()
    with pytest.raises(UserError, match='destination|exact|conflict'):
        conversion.apply(run, wid)
    assert selected.path.read_bytes() == before


def test_new_scan_cannot_use_source_scope_removed_by_stream_update(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    from alchemy_task.discovery import create_args_sources, update_stream
    streams = ctx.state.get('streams')
    streams['work'].update(sources=create_args_sources([{'name':'Feed', 'scope':'board', 'method':'reader'}]),
                          job_id='job1', schedule='0 18 * * *', when='daily', time='6 PM', frequency='daily')
    ctx.state.set('streams', streams)
    ctx.cron['job1'] = {'name': 'alchemy-task: discovery work'}
    config = {'source_key':'feed', 'name':'Feed', 'account_key':'account', 'scope':'board', 'read_method':'reader',
              'relevance':{'identity_requirements':[], 'rules':'All unresolved project issues'}}
    integration.configure('work', config, user_approved=True)
    update_stream(rt, {'name':'work', 'sources':[{'name':'Feed', 'scope':'replacement-board', 'method':'reader'}],
                       'user_approved':True}, 'parent')
    assert ctx.state.get('streams')['work']['sources'][0]['scope'] == 'replacement-board'
    with pytest.raises(UserError, match='scope|config|approved'):
        integration.start('work', session_id='parent')


def test_explicit_semantic_update_edits_not_silently_ignored(settings, data_dir, tmp_path):
    tasks = TaskStore(settings, data_dir)
    selected = tasks.create(title='Old title', area='work', due='2030-01-04', research=False)
    rt, store, run, wid, conversion = custom_joined(settings, data_dir, tmp_path,
        [{'path':tasks.rel(selected.path), 'match_basis':'related_only'}])
    integration, _, _ = service(settings, data_dir, tmp_path)
    with store._lock(store._run_lock_name(run)):
        ledger=store.get_run(run);ledger['origin']={'session_id':'parent'};store._save(run,ledger)
    integration.record_decision(run,wid,decision='propose',reason='Related task requires user choice.',session_id='parent')
    integration.finalize(run,session_id='parent')
    receipt=integration.decide({'approve':['1'],'day':'2030-01-01','edits':{'1':{
        'choice':'update','target_task_id':selected.task_id,'expected_revision':tf.content_hash(selected.raw),
        'title':'User corrected title','due':'2030-02-01'}}},session_id='parent',today='2030-01-02')
    assert receipt['results'][0]['state']=='complete'
    updated = tf.parse_file(selected.path)
    assert updated.title == 'User corrected title'
    assert str(updated.fm['due']) == '2030-02-01'


def test_automatic_git_pending_remains_visible_in_digest(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from types import SimpleNamespace
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    _, store, run, wid, _ = joined(tmp_path, settings, data_dir)
    with store._lock(store._run_lock_name(run)):
        ledger=store.get_run(run);ledger['origin']={'session_id':'parent'};store._save(run,ledger)
    task=rt.store().create(title='Existing task',area='work',undated=True,research=False,
                           notes='slack:T1:C1:171.1:171.2')
    def fail(*a,**k):raise OSError('Synthetic remote unavailable')
    rt.git=lambda:SimpleNamespace(deliver=fail)
    integration.record_decision(run,wid,decision='auto',reason='New useful approved context.',session_id='parent',
        target_task_id=task.task_id,expected_revision=tf.content_hash(task.raw),useful_delta=True)
    from alchemy_task.core.discovery_state import read_json
    _,receipt=integration.conversion._paths(run,wid)
    assert read_json(receipt)['state']=='git_pending'
    digest=integration.finalize(run,session_id='parent')
    assert 'pending' in digest['text'].lower() or 'unavailable' in digest['text'].lower()
