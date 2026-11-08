from types import SimpleNamespace
import pytest
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core import taskfile as tf
from test_discovery_state import _completed_for_review


def accepted(tmp_path, settings, data_dir):
    store, run, a, b, receipt = _completed_for_review(data_dir)
    store.accept_attempt(run, a['token'], payload_sha256=receipt['payload_sha256'], assessment={'accepted': True, 'reason': 'Full synthetic primary and canonical task bodies verified.'}, reader='parent')
    wid = store.accepted_bundle(run, a['candidate_id'])['workstream_ids'][0]
    rt = SimpleNamespace(data_dir=data_dir, settings=settings)
    from alchemy_task.core.store import TaskStore
    rt.store = lambda: TaskStore(settings, data_dir)
    return rt, store, run, wid


def test_join_barrier_and_typed_matching_includes_completed(tmp_path, settings, data_dir):
    from alchemy_task.discovery_conversion import DiscoveryConversion
    rt, store, run, wid = accepted(tmp_path, settings, data_dir)
    service = DiscoveryConversion(rt, store)
    with pytest.raises(UserError, match='join'):
        service.match(run, wid)
    parent = store.get_candidate(run, wid)['parent_candidate_id']
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [parent], 'failures': []})
    doc = rt.store().create(title='Already finished distinct title', area='work', undated=True, research=False,
                            notes='slack:T1:C1:171.1:171.2')
    rt.store().update(doc.task_id, {'status': 'done'})
    outcome = service.match(run, wid)
    assert outcome['kind'] == 'exact'
    assert outcome['targets'][0]['task_id'] == doc.task_id
    assert outcome['targets'][0]['status'] == 'done'


def joined(tmp_path, settings, data_dir):
    from alchemy_task.discovery_conversion import DiscoveryConversion
    rt, store, run, wid = accepted(tmp_path, settings, data_dir)
    parent = store.get_candidate(run, wid)['parent_candidate_id']
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [parent], 'failures': []})
    return rt, store, run, wid, DiscoveryConversion(rt, store)


def test_exact_no_delta_is_byte_preserving_noop(tmp_path, settings, data_dir):
    rt, store, run, wid, service = joined(tmp_path, settings, data_dir)
    doc = rt.store().create(title='Existing work', area='work', undated=True, research=False, notes='slack:T1:C1:171.1:171.2')
    before = doc.path.read_bytes()
    result = service.prepare(run, wid, choice='noop', reason='Full task already records this state.', target_task_id=doc.task_id,
                             expected_revision=tf.content_hash(before))
    assert result['state'] == 'noop'
    assert doc.path.read_bytes() == before
    assert not list((store.run_dir(run) / 'conversions').glob('*.json'))


def test_complete_patch_recovery_recognizes_only_full_postimage(tmp_path, settings, data_dir, monkeypatch):
    from alchemy_task import discovery_conversion as module
    rt, store, run, wid, service = joined(tmp_path, settings, data_dir)
    doc = rt.store().create(title='Existing work', area='work', undated=True, research=False, notes='User words. slack:T1:C1:171.1:171.2')
    prepared = service.prepare(run, wid, choice='auto', reason='Primary adds useful verified decision.', target_task_id=doc.task_id,
                               expected_revision=tf.content_hash(doc.raw), useful_delta=True)
    assert doc.path.read_bytes() == doc.raw
    original = module.atomic_json
    def crash(path, value):
        if path.name.endswith('.receipt.json'):
            raise RuntimeError('crash after task write before receipt')
        return original(path, value)
    monkeypatch.setattr(module, 'atomic_json', crash)
    with pytest.raises(RuntimeError, match='crash'):
        service.apply(run, wid)
    postimage = doc.path.read_bytes()
    assert b'User words.' in postimage
    assert b'discovery-dossier:start' in postimage
    assert tf.parse_file(doc.path).fm['enrichment'] == doc.fm['enrichment']
    monkeypatch.setattr(module, 'atomic_json', original)
    result = service.apply(run, wid)
    assert result['local']['state'] == 'verified'
    assert result['task_id'] == doc.task_id
    assert doc.path.read_bytes() == postimage
    assert service.apply(run, wid) == result
    assert result['google']['state'] == 'deferred'


def test_new_conversion_prebinds_uuid_and_never_queues_generic_research(tmp_path, settings, data_dir):
    rt, store, run, wid, service = joined(tmp_path, settings, data_dir)
    before = len(rt.store().scan().tasks)
    with pytest.raises(UserError, match='approval'):
        service.prepare(run, wid, choice='create', area='work', undated=True, reason='Approved separate action.')
    plan = service.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='Approved separate action.')
    assert tf.valid_task_id(plan['task_id'])
    assert not (rt.store().root / plan['path']).exists()
    result = service.apply(run, wid)
    task = rt.store().resolve(plan['task_id'])
    assert result['task_id'] == plan['task_id']
    assert len(rt.store().scan().tasks) == before + 1
    assert task.fm['enrichment']['status'] == 'complete'
    assert task.fm['enrichment']['research_origin'] == 'discovery'
    assert store.research_for(run, wid)['current_understanding'] in task.body


def test_cas_rejects_user_edit_and_multiple_exact_conflict(tmp_path, settings, data_dir):
    rt, store, run, wid, service = joined(tmp_path, settings, data_dir)
    doc = rt.store().create(title='Existing work', area='work', undated=True, research=False, notes='slack:T1:C1:171.1:171.2')
    service.prepare(run, wid, choice='auto', reason='New decision.', target_task_id=doc.task_id,
                    expected_revision=tf.content_hash(doc.raw), useful_delta=True)
    doc.path.write_bytes(doc.raw + b'\nUser edit\n')
    with pytest.raises(tf.ConcurrentEditError):
        service.apply(run, wid)
    assert doc.path.read_bytes().endswith(b'User edit\n')
    rt.store().create(title='Duplicate exact provenance', area='work', undated=True, research=False, notes='slack:T1:C1:171.1:171.2')
    assert service.match(run, wid)['kind'] == 'conflict'


def test_git_receipt_proves_committed_bytes_and_exact_remote(tmp_path, settings, data_dir):
    from alchemy_task.core.gitops import GitDelivery
    rt, store, run, wid, service = joined(tmp_path, settings, data_dir)
    rt.git = lambda: GitDelivery(settings, data_dir)
    service.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.')
    receipt = service.deliver_git(run, wid)
    assert receipt['git']['state'] == 'verified'
    delivery = rt.git()
    head = delivery.git('rev-parse', 'HEAD').stdout.strip()
    remote = delivery.git('ls-remote', 'origin', 'refs/heads/main').stdout.split()[0]
    assert receipt['git']['commit'] == head == remote
    committed = delivery.git('show', head + ':' + receipt['path']).stdout.encode()
    assert tf.content_hash(committed) == receipt['local']['sha256']
    assert service.deliver_git(run, wid) == receipt


def custom_joined(settings, data_dir, tmp_path, nominations, **changes):
    from test_discovery_state import setup, prepare, read_all
    from test_discovery_schema import bundle
    from alchemy_task.discovery_conversion import DiscoveryConversion
    from alchemy_task.core.store import TaskStore
    store, run, items = setup(data_dir)
    a = prepare(store, run, items[0]['candidate_id'])
    b = bundle(); b['candidate_id'] = a['candidate_id']
    b['workstreams'][0].update(existing_task_candidates=nominations, **changes)
    receipt = store.spool_payload(run, a['token'], b)
    store.observe_terminal(run, a['token'], state='SUCCEEDED', receipt={'state': 'SUCCEEDED'})
    read_all(store, run, receipt['resource'], 'parent')
    store.accept_attempt(run, a['token'], payload_sha256=receipt['payload_sha256'], assessment={'accepted': True, 'reason': 'Verified primary, all task bodies and independent outcomes.'}, reader='parent')
    wid = store.accepted_bundle(run, a['candidate_id'])['workstream_ids'][0]
    store.put_resource(run, 'join-record', {'joined': True, 'accepted': [a['candidate_id']], 'failures': []})
    rt = SimpleNamespace(data_dir=data_dir, settings=settings, store=lambda: TaskStore(settings, data_dir))
    return rt, store, run, wid, DiscoveryConversion(rt, store)


def test_source_semantic_update_preserves_user_metadata_and_exact_research(settings, data_dir, tmp_path):
    from alchemy_task.core.store import TaskStore
    tasks = TaskStore(settings, data_dir)
    doc = tasks.create(title='Restore seasonal item visibility', area='work', due='2030-01-04', research=False, notes='Preserve my wording.')
    raw = doc.raw.replace(b'tags:', b'# Keep this comment\ncustom_user_field: {keep: true}\ngoogle_tasks: {account: {task_id: original-id}}\ntags:')
    doc.path.write_bytes(raw)
    rt, store, run, wid, service = custom_joined(settings, data_dir, tmp_path,
        [{'path': tasks.rel(doc.path), 'match_basis': 'related_only'}],
        current_understanding='The item is hidden until Friday; restore its public name after unhiding.',
        substantive_next_action='Unhide first, rename second, verify affected surfaces.')
    assert service.match(run, wid)['kind'] == 'semantic'
    with pytest.raises(UserError, match='unique'):
        service.prepare(run, wid, choice='auto', reason='Semantic is not automatic permission.', target_task_id=doc.task_id, expected_revision=tf.content_hash(raw), useful_delta=True)
    plan = service.prepare(run, wid, choice='update', user_approved=True, reason='User chose exact nominated task.', target_task_id=doc.task_id, expected_revision=tf.content_hash(raw))
    assert doc.path.read_bytes() == raw
    service.apply(run, wid)
    after = tf.parse_file(doc.path)
    assert after.title == doc.title and str(after.fm['due']) == '2030-01-04'
    assert after.fm['google_tasks']['account']['task_id'] == 'original-id'
    assert after.fm['custom_user_field'] == {'keep': True}
    assert '# Keep this comment' in after.raw.decode() and 'Preserve my wording.' in after.body
    assert 'Unhide first, rename second' in after.body
    assert after.body.count('<!-- discovery-dossier:start ') == 1
    assert service.apply(run, wid)['task_id'] == doc.task_id
    assert plan['research_revision'] == service.prepare(run, wid, choice='update', user_approved=True,
        reason='User chose exact nominated task.', target_task_id=doc.task_id, expected_revision=tf.content_hash(raw))['research_revision']


def test_all_semantic_options_retained_and_target_binding_cannot_switch(settings, data_dir, tmp_path):
    from alchemy_task.core.store import TaskStore
    tasks = TaskStore(settings, data_dir)
    one = tasks.create(title='Original requested scope', area='work', undated=True, research=False)
    two = tasks.create(title='Completed related sibling', area='work', undated=True, research=False)
    tasks.update(two.task_id, {'status': 'done'})
    rt, store, run, wid, service = custom_joined(settings, data_dir, tmp_path,
        [{'path': tasks.rel(d.path), 'match_basis': 'related_only'} for d in [one, two]])
    result = service.match(run, wid)
    assert result['kind'] == 'selection'
    assert {x['task_id'] for x in result['targets']} == {one.task_id, two.task_id}
    with pytest.raises(UserError, match='target_task_id'):
        service.prepare(run, wid, choice='update', user_approved=True, reason='Update without guessed target.')
    service.prepare(run, wid, choice='update', user_approved=True, reason='Choose requested scope.', target_task_id=one.task_id, expected_revision=tf.content_hash(one.raw))
    with pytest.raises(UserError, match='immutable'):
        service.prepare(run, wid, choice='update', user_approved=True, reason='Switching target is forbidden.', target_task_id=two.task_id, expected_revision=result['targets'][1]['revision'])


def test_related_only_dossier_identity_and_source_substrings_never_exact(settings, data_dir, tmp_path):
    from alchemy_task.core.store import TaskStore
    tasks = TaskStore(settings, data_dir)
    tasks.create(title='Unrelated reference', area='work', undated=True, research=False,
        notes='prefixslack:T1:C1:171.1:171.2suffix\n<!-- discovery-dossier:start other -->\n### Decisive Source Identities\n- gmail:account:other\n### Related Source Identities\n- slack:T1:C1:171.1:171.2\n<!-- discovery-dossier:end other -->')
    rt, store, run, wid, service = joined(tmp_path, settings, data_dir)
    assert service.match(run, wid)['kind'] == 'new'
