"""Final bounded ordinary-flow probes, archive 4261525; no provider claims."""
import datetime as dt
import copy
import pytest
from test_discovery_integration import service
from test_discovery_conversion import custom_joined
from test_discovery_state import setup
from test_setup import home
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core import taskfile as tf


def test_fresh_default_stream_has_a_working_origin_delivery_path(settings, data_dir, tmp_path, home):
    from alchemy_task import discovery
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.state.set('streams', {})
    ctx.state.set('timezone_confirmed', True)
    result = discovery.create_stream(rt, {'name': 'fresh', 'areas': ['work'],
        'sources': [{'name': 'Feed', 'scope': 'board', 'method': 'reader'}],
        'user_approved': True}, 'parent')
    # No exact reader is needed for native host ownership; no delivery proof invented.
    assert result['stream']['activation_state'] == 'ACTIVE'
    assert result['stream']['delivery_owner'] == 'native_origin'
    assert ctx.cron[result['job_id']]['deliver'] == 'origin'
    integration.digest.prepare('native-proof', stream='fresh', day='2030-01-01', origin={'session_id': 'parent'}, items=[])
    delivery = integration.deliver('native-proof', session_id='parent')
    assert delivery['state'] == 'host_pending' and delivery['delivered'] is False
    assert delivery['final_text'] == integration.digest.get('native-proof')['text']


def test_user_correction_does_not_keep_rejected_recommendation_active(settings, data_dir, tmp_path):
    rt, store, run, wid, conversion = custom_joined(settings, data_dir, tmp_path, [],
        substantive_next_action='Deploy the experimental pilot.',
        decisions_and_open_questions={'decisions': [], 'open_questions': ['Should we deploy the experimental pilot?']},
        implementation_context=['Prepare the experimental pilot deployment.'])
    conversion.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True,
        reason='User rejected the pilot and approved verification only.',
        active_goal='Verify the existing production proof only; do not deploy a pilot.',
        notes='The pilot is rejected.', plan='Read-only verification of the existing proof.',
        checklist=['Verify the existing proof'])
    receipt = conversion.apply(run, wid)
    body = rt.store().resolve(receipt['task_id']).body
    active = body.split('### Historical Accepted Recommendation', 1)[0]
    assert 'Prepare the experimental pilot deployment.' not in active, active
    assert 'Should we deploy the experimental pilot?' not in active, active


def test_digest_keeps_known_internal_paths_and_task_ids_out_of_normal_text(data_dir):
    from alchemy_task.discovery_digest import DiscoveryDigest
    text = DiscoveryDigest(data_dir/'discovery').prepare('final-output', stream='work', day='2030-01-01',
        origin={'session_id': 'parent'}, items=[],
        outcomes=[{'title': 'Approve proof', 'task_id': 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', 'status':'git_pending',
                   'git': {'state':'pending', 'reason': "fatal: /private/cache/correspondence.txt unavailable"}}],
        failures=[{'title':'Read primary', 'reason': 'OSError: /private/cache/source.json unavailable'}])['text']
    assert '/private/cache/' not in text, text
    assert 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee' not in text, text


def test_expired_live_supervisor_not_reclaimed_and_attempt_unchanged(data_dir):
    store, run, items = setup(data_dir)
    attempt = store.reserve_attempt(run, items[0]['candidate_id'], owner_session='parent')
    before = copy.deepcopy(store.get_attempt(run, attempt['token']))
    expiry = (dt.datetime.now(dt.timezone.utc)+dt.timedelta(milliseconds=100)).isoformat()
    store.claim_lease(run, owner='live-owner', expires_at=expiry)
    import time
    time.sleep(0.15)
    with pytest.raises(UserError, match='claimed'):
        store.claim_lease(run, owner='new-owner', expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5)).isoformat())
    assert store.get_attempt(run, attempt['token']) == before


def test_unknown_process_before_expiry_not_reclaimed_and_attempt_unchanged(data_dir, monkeypatch):
    store, run, items = setup(data_dir)
    attempt = store.reserve_attempt(run, items[0]['candidate_id'], owner_session='parent')
    before = copy.deepcopy(store.get_attempt(run, attempt['token']))
    expiry = (dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5)).isoformat()
    store.claim_lease(run, owner='unknown-owner', expires_at=expiry)
    monkeypatch.setattr(store, '_lease_process_proof', lambda evidence: {'state': 'unknown'})
    with pytest.raises(UserError, match='claimed'):
        store.claim_lease(run, owner='new-owner', expires_at=expiry)
    assert store.get_attempt(run, attempt['token']) == before


def test_real_dead_process_recovery_keeps_exact_attempt_deadline(data_dir):
    import multiprocessing
    from test_discovery_state import prepare
    store, run, items = setup(data_dir)
    attempt = prepare(store, run, items[0]['candidate_id'])
    start = dt.datetime.now(dt.timezone.utc)
    store.mark_running(run, attempt['token'], started_at=start.isoformat(), deadline_utc=(start+dt.timedelta(minutes=30)).isoformat())
    before = copy.deepcopy(store.get_attempt(run, attempt['token']))
    expiry = (dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=40)).isoformat()
    ctx = multiprocessing.get_context('fork'); ready, writer = ctx.Pipe(duplex=False)
    def hold():
        store.claim_lease(run, owner='dead-owner', expires_at=expiry)
        writer.send(True)
        import time
        time.sleep(60)
    child = ctx.Process(target=hold); child.start()
    try:
        assert ready.poll(10) and ready.recv()
        child.terminate(); child.join(10)
        store.claim_lease(run, owner='new-owner', expires_at=expiry)
        assert store.get_run(run)['lease_recoveries'][-1]['proof']['state'] == 'dead'
        assert store.get_attempt(run, attempt['token']) == before
    finally:
        if child.is_alive(): child.terminate()
        child.join(10)
