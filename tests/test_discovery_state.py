import concurrent.futures
import hashlib
import json
import stat
from pathlib import Path
import pytest
from alchemy_task.core import discovery_state as m
from test_discovery_schema import bundle


def setup(tmp_path, count=1):
    store=m.DiscoveryStore(tmp_path/'discovery')
    run=store.init_run(stream='work',business_date='2030-01-01',config={'sources':['work']})
    items=store.add_candidates(run,[{'title':f'Ask {i}','source_ids':[{'type':'slack','workspace_id':'T1','channel_id':'C1','thread_root_ts':'171.1','message_ts':f'171.{i+2}'}]} for i in range(count)])
    store.freeze_index(run,rubric='Read complete sources.')
    return store,run,items


def read_all(store,run,name,reader):
    rev=store.resource_info(run,name)['sha256'];cursor=None;parts=[]
    while True:
        page=store.fetch_resource(run,name,revision=rev,reader=reader,cursor=cursor,limit=137)
        assert hashlib.sha256(page['content'].encode()).hexdigest()==page['page_sha256']
        parts.append(page['content'])
        if not page['has_more']:break
        cursor=page['next_cursor']
    return ''.join(parts)


def prepare(store,run,cid):
    attempt=store.reserve_attempt(run,cid,owner_session='parent',daily_limit=1000)
    store.record_start(run,parent_session='parent',child_session='child-'+attempt['token'],subagent_id='sa-'+attempt['token'])
    store.bind_attempt(run,attempt['token'],{'subagent_id':'sa-'+attempt['token']},owner_session='parent')
    for name in attempt['required_resources']:
        read_all(store,run,name,attempt['token'])
    return attempt


def test_ledger_no_truncation_cohorts_immutable_revisions_and_modes(tmp_path):
    store,run,items=setup(tmp_path,201)
    assert len(items)==201
    cohorts=store.get_run(run)['cohorts'];assert [len(x['candidate_ids']) for x in cohorts]==[200,1]
    manifest=json.loads(read_all(store,run,'manifest','parent'))
    assert len(manifest['candidates'])==201
    assert stat.S_IMODE(store.run_dir(run).stat().st_mode)==0o700
    with pytest.raises(m.UserError):store.add_candidates(run,[{'source_ids':['gmail:a:t']}])
    with pytest.raises(m.UserError):store.fetch_resource(run,'manifest',revision='wrong',reader='parent')
    assert m.DiscoveryStore(store.state_root).get_run(run)['config']=={'sources':['work']}


def test_attempt_fences_and_two_fresh_maximum(tmp_path):
    store,run,items=setup(tmp_path);cid=items[0]['candidate_id']
    a=prepare(store,run,cid)
    with pytest.raises(m.UserError):store.reserve_attempt(run,cid,owner_session='parent')
    store.observe_terminal(run,a['token'],state='FAILED',receipt={'status':'FAILED'})
    store.reject_attempt(run,a['token'],reason='provider failure',retryable=True)
    b=prepare(store,run,cid)
    assert b['ordinal']==2 and b['token']!=a['token']
    store.fence_attempt(run,b['token'],reason='execution_unknown')
    with pytest.raises(m.UserError):store.reserve_attempt(run,cid,owner_session='parent')
    with pytest.raises(m.UserError):store.spool_payload(run,b['token'],bundle())


def test_submission_terminal_full_parent_read_then_acceptance_and_recovery(tmp_path,monkeypatch):
    store,run,items=setup(tmp_path);cid=items[0]['candidate_id'];a=prepare(store,run,cid)
    b=bundle();b['candidate_id']=cid
    receipt=store.spool_payload(run,a['token'],b)
    assert receipt['payload_sha256']
    assert store.get_candidate(run,cid).get('decomposition_state') is None
    with pytest.raises(m.UserError):store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Current primary and complete task inventory'},reader='parent')
    store.observe_terminal(run,a['token'],state='SUCCEEDED',receipt={'status':'SUCCEEDED'})
    with pytest.raises(m.UserError,match='pages'):store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Checked'},reader='parent')
    read_all(store,run,receipt['resource'],'parent')
    real=store._materialize_bundle_locked
    def crash(*args,**kwargs):raise RuntimeError('crash before materialization')
    monkeypatch.setattr(store,'_materialize_bundle_locked',crash)
    with pytest.raises(RuntimeError):store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Checked'},reader='parent')
    monkeypatch.setattr(store,'_materialize_bundle_locked',real)
    recovered=m.DiscoveryStore(store.state_root);recovered.recover_bundles(run)
    accepted=recovered.accepted_bundle(run,cid)
    assert len(accepted['workstream_ids'])==1
    assert recovered.get_attempt(run,a['token'])['state']=='accepted_bundle'
    assert recovered.spool_payload(run,a['token'],b)==receipt
    b['workstreams'][0]['title']='changed'
    with pytest.raises(m.UserError):recovered.spool_payload(run,a['token'],b)


def test_chunk_upload_equivalent_and_missing_part_rejected(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    b=bundle();b['candidate_id']=items[0]['candidate_id'];raw=json.dumps(b,ensure_ascii=False);digest=hashlib.sha256(raw.encode()).hexdigest()
    store.begin_upload(run,a['token'],total_bytes=len(raw.encode()),sha256=digest,part_count=2)
    store.upload_part(run,a['token'],index=1,content=raw[len(raw)//2:])
    with pytest.raises(m.UserError):store.commit_upload(run,a['token'])
    store.upload_part(run,a['token'],index=0,content=raw[:len(raw)//2])
    assert store.commit_upload(run,a['token'])['payload_sha256']
    with pytest.raises(m.UserError):store.upload_part(run,a['token'],index=0,content='different')


def test_concurrent_unique_init_and_attempt_reservation(tmp_path):
    store,run,items=setup(tmp_path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        runs=list(pool.map(lambda _:store.init_run(),range(10)))
    assert len(set(runs))==10
    def reserve(_):
        try:return store.reserve_attempt(run,items[0]['candidate_id'],owner_session='parent')
        except m.UserError:return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:attempts=list(pool.map(reserve,range(8)))
    assert len([x for x in attempts if x])==1


def test_source_backlog_budget_and_coverage_are_separate(tmp_path):
    store,run,items=setup(tmp_path,3)
    store.enqueue_backlog('work','mail',[{'source_ids':['gmail:work:t'+str(i)],'source_revision':'1'} for i in range(250)])
    assert len(store.source_state('work','mail')['backlog'])==250
    store.record_coverage('work','mail',{'status':'partial','verification':'agent_attested','end':'2030-01-01T00:00:00Z'})
    assert store.source_state('work','mail').get('watermark') is None
    with pytest.raises(m.UserError):store.reserve_attempt(run,items[0]['candidate_id'],owner_session='parent',daily_limit=0)
    a=store.reserve_attempt(run,items[0]['candidate_id'],owner_session='parent',daily_limit=1)
    with pytest.raises(m.UserError):store.reserve_attempt(run,items[1]['candidate_id'],owner_session='parent',daily_limit=1)
    assert len(store.source_state('work','mail')['backlog'])==250
    assert store.get_attempt(run,a['token'])['ordinal']==1


def test_terminal_payload_remains_reviewable_after_execution_deadline(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    b=bundle();b['candidate_id']=items[0]['candidate_id'];receipt=store.spool_payload(run,a['token'],b)
    store.observe_terminal(run,a['token'],state='SUCCEEDED',receipt={'status':'SUCCEEDED'})
    # Historical deadline is not an acceptance deadline after observed completion.
    with store._lock(store._run_lock_name(run)):
        ledger=store.get_run(run);ledger['attempts'][a['token']]['deadline_utc']='2000-01-01T00:00:00Z';store._save(run,ledger)
    read_all(store,run,receipt['resource'],'parent')
    assert store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Reviewed after restart'},reader='parent')


def test_confirmed_terminal_timeout_can_use_remaining_fresh_ordinal(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    store.fence_attempt(run,a['token'],reason='execution_timeout',cancellation={'accepted':True})
    with pytest.raises(m.UserError):store.reject_attempt(run,a['token'],reason='timed out',retryable=True)
    store.observe_terminal(run,a['token'],state='INTERRUPTED',receipt={'status':'INTERRUPTED'})
    store.reject_attempt(run,a['token'],reason='terminal timeout',retryable=True)
    assert store.reserve_attempt(run,items[0]['candidate_id'],owner_session='parent')['ordinal']==2
    with pytest.raises(m.UserError):store.authorize_attempt(run,a['token'],child_session='child-'+a['token'])


def test_concurrent_errors_review_and_retention(tmp_path):
    store,run,items=setup(tmp_path)
    def error(i):store.record_failure(run,items[0]['candidate_id'],'research',f'Failure {i}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(error,range(12)))
    assert len(store.get_run(run)['errors'])==12
    store.save_review(run,{'status':'degraded','failures':12})
    assert store.save_review(run,{'status':'degraded','failures':12})['failures']==12
    with pytest.raises(m.UserError):store.record_failure(run,items[0]['candidate_id'],'research','late')
    assert store.prune(days=0)['deleted_runs']==[]


def test_rejected_attempt_cannot_be_accepted_later(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    b=bundle();b['candidate_id']=items[0]['candidate_id'];receipt=store.spool_payload(run,a['token'],b)
    store.observe_terminal(run,a['token'],state='SUCCEEDED',receipt={'status':'SUCCEEDED'})
    read_all(store,run,receipt['resource'],'parent')
    store.reject_attempt(run,a['token'],reason='Wrong ownership',retryable=True,semantic=True)
    with pytest.raises(m.UserError):store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Changed mind'},reader='parent')


def test_handle_replay_does_not_regress_submitted_state(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    b=bundle();b['candidate_id']=items[0]['candidate_id'];store.spool_payload(run,a['token'],b)
    store.bind_attempt(run,a['token'],{'subagent_id':'sa-'+a['token']},owner_session='parent')
    assert store.get_attempt(run,a['token'])['state']=='submitted'


def test_near_full_bundle_and_utf8_paging_and_multipart(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    b=bundle();b['candidate_id']=items[0]['candidate_id'];w=b['workstreams'][0]
    w['new_information']=['x'*4000]*50;w['implementation_context']=['y'*4000]*50;w['dependencies_and_risks']=['z'*2000]*50
    raw=json.dumps(b,ensure_ascii=False);assert len(raw.encode())>490000
    receipt=store.spool_payload(run,a['token'],b)
    assert store.get_attempt(run,a['token'])['evidence']['helper']=='valid'
    assert receipt['total_bytes']<=m.MAX_BUNDLE_BYTES
    store.put_resource(run,'unicode','🙂é'*100)
    revision=store.resource_info(run,'unicode')['sha256'];cursor=None;parts=[]
    while True:
        page=store.fetch_resource(run,'unicode',revision=revision,reader='parent',cursor=cursor,limit=5);parts.append(page['content'])
        if not page['has_more']:break
        cursor=page['next_cursor']
    assert ''.join(parts)=='🙂é'*100
    # Equivalent full upload uses a fresh attempt on an independent run.
    other=m.DiscoveryStore(tmp_path/'other');r=other.init_run();item=other.add_candidates(r,[{'source_ids':['slack:T1:C1:171.1:171.2']}])[0];other.freeze_index(r,rubric='Full reads')
    attempt=prepare(other,r,item['candidate_id']);b['candidate_id']=item['candidate_id'];raw=json.dumps(b,ensure_ascii=False)
    chunks=[raw[i:i+8000] for i in range(0,len(raw),8000)]
    other.begin_upload(r,attempt['token'],total_bytes=len(raw.encode()),sha256=hashlib.sha256(raw.encode()).hexdigest(),part_count=len(chunks))
    for i,part in enumerate(chunks):other.upload_part(r,attempt['token'],index=i,content=part)
    assert other.commit_upload(r,attempt['token'])['payload_sha256']==receipt['payload_sha256']


@pytest.mark.parametrize('failure_step',[1,2,3,4])
def test_bundle_crash_between_unit_ledger_and_marker_writes_recovers_all_units(tmp_path,monkeypatch,failure_step):
    store=m.DiscoveryStore(tmp_path/'discovery');run=store.init_run()
    parent=store.add_candidates(run,[{'source_ids':['slack:T1:C1:171.1']}])[0];store.freeze_index(run,rubric='Complete research')
    a=prepare(store,run,parent['candidate_id']);b=bundle();b['candidate_id']=parent['candidate_id']
    import copy
    second=copy.deepcopy(b['workstreams'][0]);second['exact_source_ids'][0]['message_ts']='171.9';b['workstreams'].append(second)
    receipt=store.spool_payload(run,a['token'],b);store.observe_terminal(run,a['token'],state='SUCCEEDED',receipt={'state':'SUCCEEDED'});read_all(store,run,receipt['resource'],'parent')
    real=m.atomic_json;calls=[]
    def fail(path,value):
        if path.parent.name=='research' or path.name=='ledger.json':
            calls.append(str(path))
            if len(calls)==failure_step:raise OSError('simulated disk failure')
        real(path,value)
    monkeypatch.setattr(m,'atomic_json',fail)
    with pytest.raises(OSError):store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'All independent asks verified'},reader='parent')
    monkeypatch.setattr(m,'atomic_json',real)
    store=m.DiscoveryStore(store.state_root);store.recover_bundles(run)
    marker=store.accepted_bundle(run,parent['candidate_id']);assert len(marker['workstream_ids'])==2
    assert len([x for x in store.get_run(run)['candidates'] if x.get('parent_candidate_id')])==2
    before=(store.run_dir(run)/'ledger.json').read_bytes();store.recover_bundles(run)
    assert (store.run_dir(run)/'ledger.json').read_bytes()==before


def test_review_repeat_preserves_revision_and_unknown_attempt_never_pruned(tmp_path):
    store,run,items=setup(tmp_path);a=store.reserve_attempt(run,items[0]['candidate_id'],owner_session='parent')
    store.fence_attempt(run,a['token'],reason='launch_unknown')
    store.save_review(run,{'status':'degraded'});before=store.get_run(run)['revision']
    store.save_review(run,{'status':'degraded'})
    assert store.get_run(run)['revision']==before
    assert store.prune(days=0)['deleted_runs']==[]


def test_shape_and_helper_evidence_are_distinct_and_invalid_payload_retained(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    b=bundle();b['candidate_id']='c_'+'f'*20
    receipt=store.spool_payload(run,a['token'],b)
    attempt=store.get_attempt(run,a['token'])
    assert attempt['evidence']['shape']=='valid'
    assert attempt['evidence']['helper']=='rejected'
    assert store.resource_info(run,receipt['resource'])['total_bytes']>0


def test_cross_cohort_outcome_manifest_is_frozen_for_each_new_attempt(tmp_path):
    store,run,items=setup(tmp_path)
    a=prepare(store,run,items[0]['candidate_id']);before=a['outcome_revision']
    b=bundle();b['candidate_id']=items[0]['candidate_id'];receipt=store.spool_payload(run,a['token'],b)
    store.observe_terminal(run,a['token'],state='SUCCEEDED',receipt={'state':'SUCCEEDED'});read_all(store,run,receipt['resource'],'parent')
    marker=store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Verified'},reader='parent')
    after=store.get_run(run)['outcome_resource'];assert after['sha256']!=before
    outcome=json.loads(read_all(store,run,after['name'],'parent'))
    assert outcome[0]['workstream_id']==marker['workstream_ids'][0]
    assert store.get_attempt(run,a['token'])['outcome_revision']==before


def test_prune_old_resolved_empty_run_keeps_readable_tombstone(tmp_path):
    store=m.DiscoveryStore(tmp_path/'discovery');run=store.init_run();store.save_review(run,{'status':'complete','candidate_ids':[]})
    result=store.prune(days=0)
    assert result['deleted_runs']==[run]
    assert not store.run_dir(run).exists()
    assert store.get_run(run)['pruned_at']
    assert store.get_run(run)['review']['status']=='complete'
    with pytest.raises(m.UserError):store.init_run(run)


def test_malformed_full_text_is_spooled_for_audit_without_acceptance(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id'])
    receipt=store.spool_payload(run,a['token'],'{"workstreams": [ truncated')
    assert receipt['parsed'] is False
    assert store.get_attempt(run,a['token'])['evidence']['shape']=='rejected'
    assert read_all(store,run,receipt['resource'],'parent')=='{"workstreams": [ truncated'
    store.observe_terminal(run,a['token'],state='SUCCEEDED',receipt={'state':'SUCCEEDED'})
    with pytest.raises(m.UserError):store.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Cannot repair facts'},reader='parent')


def test_identical_late_submission_is_receipt_only_and_stays_fenced(tmp_path):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id']);b=bundle();b['candidate_id']=items[0]['candidate_id']
    receipt=store.spool_payload(run,a['token'],b);store.fence_attempt(run,a['token'],reason='execution_unknown')
    assert store.spool_payload(run,a['token'],b)==receipt
    assert store.get_attempt(run,a['token'])['fenced'] is True
    b['workstreams'][0]['title']='Changed'
    with pytest.raises(m.UserError):store.spool_payload(run,a['token'],b)


def test_committed_spool_receipt_recovers_after_ledger_checkpoint_failure(tmp_path,monkeypatch):
    store,run,items=setup(tmp_path);a=prepare(store,run,items[0]['candidate_id']);b=bundle();b['candidate_id']=items[0]['candidate_id']
    real=store._save
    def crash(*args,**kwargs):raise OSError('ledger checkpoint unavailable')
    monkeypatch.setattr(store,'_save',crash)
    with pytest.raises(OSError):store.spool_payload(run,a['token'],b)
    monkeypatch.setattr(store,'_save',real)
    recovered=m.DiscoveryStore(store.state_root);receipts=recovered.recover_spools(run)
    assert len(receipts)==1
    assert recovered.get_attempt(run,a['token'])['payload']['payload_sha256']==receipts[0]['payload_sha256']
    assert recovered.get_candidate(run,items[0]['candidate_id']).get('decomposition_state') is None


def test_backlog_status_update_retains_fifo_and_lineage(tmp_path):
    store=m.DiscoveryStore(tmp_path/'discovery');state=store.enqueue_backlog('work','mail',[{'source_ids':['gmail:work:t'],'source_revision':'1'},{'source_ids':['gmail:work:other'],'source_revision':'1'}])
    bid=state['backlog'][0]['backlog_id']
    store.update_backlog('work','mail',bid,status='accepted',lineage={'run_id':'run-1','candidate_id':'c_'+'a'*20})
    state=store.source_state('work','mail');assert len(state['backlog'])==2 and state['backlog'][0]['status']=='accepted'
    assert state['backlog'][0]['lineage']['run_id']=='run-1'


def test_supervisor_lease_release_is_owner_checked(tmp_path):
    import datetime as dt
    store,run,items=setup(tmp_path);expiry=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)).isoformat()
    store.claim_lease(run,owner='invocation-1',expires_at=expiry)
    with pytest.raises(m.UserError):store.claim_lease(run,owner='invocation-2',expires_at=expiry)
    with pytest.raises(m.UserError):store.release_lease(run,owner='invocation-2')
    store.release_lease(run,owner='invocation-1');store.claim_lease(run,owner='invocation-2',expires_at=expiry)


def test_foreign_binding_and_unknown_owner_fenced(tmp_path):
    store,run,items=setup(tmp_path);a=store.reserve_attempt(run,items[0]['candidate_id'],owner_session='parent')
    with pytest.raises(m.UserError):store.authorize_attempt(run,a['token'],child_session='foreign',subagent_id='sa-foreign')
    store.recover_owner(run,owner_session='new-parent')
    assert store.get_attempt(run,a['token'])['state']=='launch_unknown'
    with pytest.raises(m.UserError):store.reserve_attempt(run,items[0]['candidate_id'],owner_session='new-parent')
