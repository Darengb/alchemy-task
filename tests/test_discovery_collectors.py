"""Synthetic source-derived regressions through the real SourceAdapter boundary."""
import base64
import copy
import pytest
from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.discovery_sources import SourceAdapter

START, END = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
AT = 1767225600000
CFG = {'source_key': 'mail', 'account_key': 'account', 'scope': {'folder': 'all'},
       'read_method': 'approved', 'kind': 'mail', 'sender_domains': ['example.test'],
       'excluded_senders': ['support@example.test', 'shared@example.test'],
       'owner_email': 'owner@example.test',
       'owner_report_pattern': r'(?:\bRPT\b|\bweekly\s+status\s+review\b)'}

def message(mid, sender='owner@example.test', subject='Approve proof', at=AT, text='Full body', mime='text/plain'):
    return {'id': mid, 'internalDate': str(at), 'payload': {'mimeType': mime,
        'headers': [{'name': 'From', 'value': sender}, {'name': 'To', 'value': 'owner@example.test'}, {'name': 'Subject', 'value': subject}],
        'body': {'data': base64.urlsafe_b64encode(text.encode()).decode()}}}

def envelope(c, s, e, items, **kw):
    return {'account_key': c['account_key'], 'scope': c['scope'], 'start': s, 'end': e,
            'items': items, 'next_cursor': None, 'pagination_exhausted': True, **kw}

def collect(tmp_path, cfg, raw, **callbacks):
    from alchemy_task.discovery_collectors import make_daily_reader
    store = DiscoveryStore(tmp_path / 'state')
    reader = make_daily_reader(cfg, raw, snapshot_root=tmp_path / 'cache', **callbacks)
    receipt = SourceAdapter(store, cfg, read_page=reader).collect('stream', start=START, end=END)
    return receipt, store.source_state('stream', cfg['source_key']), reader

@pytest.mark.parametrize('senders,subject,count', [
    (['support@example.test', 'shared@example.test'], 'Question', 0),
    (['external@outside.test'], 'Question', 0),
    (['support@example.test', 'peer@example.test'], 'Question', 1),
    (['  OWNER@EXAMPLE.TEST  '], 'Question', 1),
    (['owner@example.test'], 'RPT', 0),
    (['owner@example.test'], 'weekly STATUS review', 0),
    (['owner@example.test'], 'RPTish', 1),
    (['owner@example.test', 'external@outside.test'], 'RPT', 1),
    (['owner@example.test', 'peer@example.test'], 'RPT', 1),
    (['owner@example.test', 'owner@example.test'], 'RPT', 1),
    (['peer@example.test'], 'RPT', 1),
])
def test_source_sender_and_narrow_report_truth_table(tmp_path, senders, subject, count):
    msgs = [message('m'+str(i), sender, subject) for i, sender in enumerate(senders)]
    receipt, state, _ = collect(tmp_path, CFG, lambda c,s,e,k: envelope(c,s,e,[{'id':'t1','messages':msgs,'complete':True}]))
    assert receipt['status'] == 'complete'
    assert len(state['backlog']) == count

def test_actual_factory_two_pages_thread_fetch_and_shared_snapshot(tmp_path,monkeypatch):
    from alchemy_task import discovery_collectors as module
    from alchemy_task.discovery_sources import QuotaReader
    class Clock:
        now=0
        def monotonic(self): return self.now
        def sleep(self,d): self.now+=d
    clock=Clock()
    monkeypatch.setattr(module,'QuotaReader',lambda:QuotaReader(clock=clock,jitter=lambda:0))
    class Response(dict): status=429
    class Error(Exception): resp=Response({'Retry-After':'7'}); content=b'{}'
    calls = []
    threads = {'t1': [message('m1', 'external@outside.test'), message('m2')],
               't2': [message('m3', 'notes@service.test', text='Suggested next steps\nApprove proof\nSummary\nOld') ]}
    def raw(c,s,e,k):
        calls.append(('page', k))
        if len(calls)==1: raise Error()
        refs = [{'id':'r1','threadId':'t1'}] if k is None else [{'id':'r2','threadId':'t1'}, {'id':'r3','threadId':'t2'}]
        return envelope(c,s,e,refs,next_cursor='p2' if k is None else None,pagination_exhausted=k is not None)
    def thread(c,s,e,tid):
        calls.append(('thread',tid))
        return envelope(c,s,e,[{'id':tid,'messages':threads[tid],'complete':True}])
    receipt, state, _ = collect(tmp_path, {**CFG,'reader_policy':{'structured_errors':True,'owns_retries':False}}, raw, read_thread=thread)
    assert receipt['status'] == 'complete'
    assert clock.now==7 and len(list((tmp_path/'cache').glob('mail-*.json')))==1
    assert calls == [('page',None),('page',None),('page','p2'),('thread','t1'),('thread','t2')]
    assert len(state['backlog']) == 1
    cfg = {**CFG, 'source_key':'notes', 'kind':'transcript', 'service_sender':'notes@service.test'}
    receipt2, state2, _ = collect(tmp_path, cfg, lambda *a: pytest.fail('must load shared snapshot'))
    assert receipt2['status'] == 'complete'
    assert len(state2['backlog']) == 1
    assert state2['backlog'][0]['candidate']['source_ids'] == ['gmail:account:t2:m3']


@pytest.mark.parametrize('defect',['account','window','incomplete','readable'])
def test_shared_snapshot_validation_refuses_without_fallback_reads(tmp_path,defect):
    import json
    collect(tmp_path,CFG,lambda c,s,e,k: envelope(c,s,e,[]))
    path=next((tmp_path/'cache').glob('mail-*.json'))
    data=json.loads(path.read_text())
    if defect=='account': data['account']='other'
    if defect=='window': data['window_end']=START
    if defect=='incomplete': data['complete']=False
    path.write_text(json.dumps(data))
    if defect=='readable': path.chmod(0o644)
    cfg={**CFG,'kind':'transcript','source_key':'notes','service_sender':'notes@service.test'}
    r,state,_=collect(tmp_path,cfg,lambda *a: pytest.fail('invalid snapshot must not silently fall back'))
    assert r['status']!='complete' and not state.get('watermark')


def test_factory_http_date_retry_after_and_240_second_gate(tmp_path,monkeypatch):
    from alchemy_task import discovery_collectors as module
    from alchemy_task import discovery_sources as source
    class Clock:
        now=0
        sleeps=[]
        def monotonic(self): return self.now
        def sleep(self,d): self.sleeps.append(d); self.now+=d
    clock=Clock()
    monkeypatch.setattr(source.time,'time',lambda:0)
    monkeypatch.setattr(module,'QuotaReader',lambda: source.QuotaReader(clock=clock,jitter=lambda:0))
    class Response(dict): status=429
    class Error(Exception): resp=Response({'Retry-After':'Thu, 01 Jan 1970 00:04:00 GMT'}); content=b'{}'
    calls=[]
    def raw(*a): calls.append(1); raise Error()
    cfg={**CFG,'reader_policy':{'structured_errors':True,'owns_retries':False}}
    r,_,_=collect(tmp_path,cfg,raw)
    assert calls==[1] and clock.sleeps==[] and r['error']=='source_quota_exhausted'


def test_generic_reader_preserves_existing_normalized_adapter_route(tmp_path):
    cfg={**CFG,'kind':'generic'}
    candidate={'source_ids':['source:mail:account:thread:t1'],'title':'Synthetic','source_revision':'r1'}
    r,state,_=collect(tmp_path,cfg,lambda c,s,e,k:envelope(c,s,e,[candidate]))
    assert r['status']=='complete' and state['backlog'][0]['candidate']==candidate


def test_standalone_transcript_full_messages_need_no_thread_expansion(tmp_path):
    cfg={**CFG,'kind':'transcript','service_sender':'notes@service.test','scope':{'sender':'notes@service.test'}}
    msgs=[{**message('m1','notes@service.test',text='Suggested next steps\nApprove'),'threadId':'t1'},
          {**message('m2','notes@service.test',text='Suggested next steps\nPublish'),'threadId':'t1'}]
    r,state,_=collect(tmp_path,cfg,lambda c,s,e,k:envelope(c,s,e,msgs))
    assert r['status']=='complete' and len(state['backlog'])==2
    assert [b['candidate']['source_ids'] for b in state['backlog']]==[['gmail:account:t1:m1'],['gmail:account:t1:m2']]
    # A full message is not proof of all historical messages in its thread.
    assert not list((tmp_path/'cache').glob('mail-*.json'))


def test_transcript_missing_sender_is_not_empty_success(tmp_path):
    from alchemy_task.discovery_collectors import make_daily_reader
    from alchemy_task.core.discovery_identity import UserError
    with pytest.raises(UserError,match='service_sender'):
        make_daily_reader({**CFG,'kind':'transcript'},lambda *a:None,snapshot_root=tmp_path)


def test_transcript_per_message_html_sections_and_inclusive_window(tmp_path):
    html = '<p>Suggested next steps</p><ul><li>Approve &amp; publish</li><li>Send proof</li></ul><p>Summary</p><p>Old action</p>'
    msgs = [message('m1','notes@service.test',text=html,mime='text/html'),
            message('m2','notes@service.test',at=AT+86400000,text=html,mime='text/html'),
            message('m3','wrong@service.test',text=html,mime='text/html'),
            message('m4','notes@service.test',at=AT+86400001,text=html,mime='text/html'),
            message('m5','notes@service.test',at=AT-1,text=html,mime='text/html'),
            message('m6','notes@service.test',text='Suggested next steps\nSummary\nOld')]
    cfg = {**CFG,'kind':'transcript','service_sender':'notes@service.test'}
    receipt, state, _ = collect(tmp_path,cfg,lambda c,s,e,k: envelope(c,s,e,[{'id':'t1','messages':msgs,'complete':True}]))
    assert receipt['status'] == 'complete'
    candidates = [b['candidate'] for b in state['backlog']]
    assert [c['source_ids'] for c in candidates] == [['gmail:account:t1:m1'],['gmail:account:t1:m2']]
    assert candidates[0]['messages'][0]['suggested_next_steps'] == '- Approve & publish\n\n- Send proof'


def test_private_durable_pass_resumes_first_page_without_dropping_admission(tmp_path):
    from alchemy_task.discovery_collectors import make_daily_reader
    calls = []
    def raw(c,s,e,k):
        calls.append(k)
        return envelope(c,s,e,[{'id':'t1' if k is None else 't2','messages':[message('m1' if k is None else 'm2')],'complete':True}], next_cursor='p2' if k is None else None,pagination_exhausted=k is not None)
    store = DiscoveryStore(tmp_path/'state')
    first = make_daily_reader(CFG,raw,snapshot_root=tmp_path/'cache')
    r = SourceAdapter(store,CFG,read_page=first).collect('stream',start=START,end=END,max_pages=1)
    assert r['status'] == 'partial' and not store.source_state('stream','mail').get('watermark')
    assert not list((tmp_path/'cache').glob('mail-*.json'))
    # Fresh factory and adapter, including caller restarting with cursor=None.
    second = make_daily_reader(CFG,raw,snapshot_root=tmp_path/'cache')
    r = SourceAdapter(store,CFG,read_page=second).collect('stream',start=START,end=END)
    assert r['status'] == 'complete' and calls == [None,'p2']
    assert len(store.source_state('stream','mail')['backlog']) == 2


@pytest.mark.parametrize('problem', ['missing_pagination','unexpanded','thread_partial','truncated','wrong_scope'])
def test_no_manufactured_provider_exhaustion(tmp_path, problem):
    def raw(c,s,e,k):
        page = envelope(c,s,e,[{'id':'r1','threadId':'t1'}])
        if problem == 'missing_pagination': page.pop('pagination_exhausted')
        if problem == 'truncated': page['truncated'] = True
        if problem == 'wrong_scope': page['scope'] = {'folder':'other'}
        return page
    kwargs = {}
    if problem == 'thread_partial':
        kwargs['read_thread'] = lambda c,s,e,k: envelope(c,s,e,[],next_cursor='more',pagination_exhausted=False)
    r, state, _ = collect(tmp_path,CFG,raw,**kwargs)
    assert r['status'] != 'complete' and not state.get('watermark')
    assert not list((tmp_path/'cache').glob('mail-*.json'))


def test_structured_quota_retries_same_request_with_max_retry_after_jitter(tmp_path, monkeypatch):
    from alchemy_task import discovery_collectors as module
    from alchemy_task.discovery_sources import QuotaReader
    class Clock:
        now = 0
        def monotonic(self): return self.now
        def sleep(self, delay): self.now += delay
    clock = Clock()
    monkeypatch.setattr(module,'QuotaReader',lambda: QuotaReader(clock=clock,jitter=lambda: .75))
    class Response(dict): status = 429
    class Quota(Exception): resp = Response({'Retry-After':'3'}); content = b'{}'
    calls = []
    def raw(c,s,e,k):
        calls.append(k)
        if len(calls) in [1,3]: raise Quota()
        return envelope(c,s,e,[{'id':'t1','messages':[message('m1')],'complete':True}],next_cursor='p2' if k is None else None,pagination_exhausted=k is not None)
    r, state, _ = collect(tmp_path,{**CFG,'reader_policy':{'structured_errors':True,'owns_retries':False}},raw)
    assert r['status'] == 'complete' and calls == [None,None,'p2','p2']
    assert clock.now == 6 and len(state['backlog']) == 1


def test_source_first_subject_and_historical_messages_are_preserved(tmp_path):
    msgs = [message('m1','peer@example.test',subject='Original topic',at=AT-100000),
            message('m2','external@outside.test',subject='')]
    r,state,_ = collect(tmp_path,CFG,lambda c,s,e,k: envelope(c,s,e,[{'id':'t1','messages':msgs,'complete':True}]))
    candidate = state['backlog'][0]['candidate']
    assert r['status']=='complete' and candidate['title']=='Original topic'
    assert len(candidate['messages'])==2


def test_slack_padding_uses_source_local_calendar(tmp_path):
    from alchemy_task.discovery_collectors import make_daily_reader
    cfg = {**CFG,'kind':'slack','seed_queries':['approved']}
    start, end = '2026-01-01T23:00:00-05:00','2026-01-02T23:00:00-05:00'
    seen = []
    def raw(c,s,e,k):
        seen.append(c['collector_request']['query'])
        return envelope(cfg,s,e,[])
    result = make_daily_reader(cfg,raw,snapshot_root=tmp_path)(cfg,start,end,None)
    assert result['pagination_exhausted'] is True
    assert seen == ['approved after:2025-12-31 before:2026-01-03']


def test_slack_seed_queries_padding_exact_window_and_full_recipe(tmp_path):
    from datetime import datetime
    base = str(AT//1000)
    cfg = {**CFG,'source_key':'chat','kind':'slack','scope':{'channels':['C1']},
           'seed_queries':['<@U1>','from:<@U1>','"Example"']}
    calls = []
    def m(offset, **kw):
        return {'channel':{'id':'C1'},'ts':f'{int(base)+offset}.000001','text':f'Body {offset}',**kw}
    seeds = [m(0),m(1800),m(3601),m(60,permalink=f'https://chat.example.test/p?thread_ts={int(base)-50}.000001'),m(-1),m(86401)]
    def raw(c,s,e,k):
        request = c['collector_request']
        calls.append(('seed',request))
        return envelope(cfg,s,e,seeds)
    def replies(c,s,e,request):
        calls.append(('primary',request))
        branch = request['operation']
        if branch == 'replies': return envelope(c,s,e,[m(-50),m(60)])
        if branch == 'before': items = [m(-20),m(0)] if request['latest']==m(0)['ts'] else [m(3601)]
        elif branch == 'after': items = [m(1810)] if request['oldest']==m(1800)['ts'] else [m(3610)]
        elif branch == 'between': items = [m(0),m(900),m(1800)]
        return envelope(c,s,e,items,recipe_complete=True)
    r, state, _ = collect(tmp_path,cfg,raw,read_replies=replies)
    assert r['status'] == 'complete'
    searches = [req for kind,req in calls if kind=='seed']
    assert [x['query'] for x in searches] == ['<@U1> after:2025-12-31 before:2026-01-03','from:<@U1> after:2025-12-31 before:2026-01-03','"Example" after:2025-12-31 before:2026-01-03']
    ops = [req for kind,req in calls if kind=='primary']
    assert [(q['operation'],q['limit']) for q in ops] == [('replies',200),('before',6),('after',10),('between',100),('before',6),('after',10)]
    assert ops[1]['inclusive'] is True and ops[2]['inclusive'] is False
    candidates = [b['candidate'] for b in state['backlog']]
    assert len(candidates)==3
    decisive = [sid for c in candidates for sid in c['source_ids']]
    assert len(decisive)==4 and not any(f':{int(base)-1}.' in sid for sid in decisive)
    conversation = next(c for c in candidates if len(c['source_ids'])==2)
    assert [x['ts'] for x in conversation['messages']] == [m(-20)['ts'],m(0)['ts'],m(900)['ts'],m(1800)['ts'],m(1810)['ts']]


@pytest.mark.parametrize('missing',['ts','channel'])
def test_slack_unidentified_search_match_cannot_claim_full_coverage(tmp_path,missing):
    cfg={**CFG,'kind':'slack','seed_queries':['approved']}
    seed={'channel':{'id':'C1'},'ts':'1767225600.000001','text':'Ask'}
    seed.pop(missing)
    r,state,_=collect(tmp_path,cfg,lambda c,s,e,k:envelope(cfg,s,e,[seed]))
    assert r['status']!='complete' and not state.get('watermark')


def test_slack_repeated_search_ids_merge_full_content(tmp_path):
    cfg = {**CFG,'kind':'slack','seed_queries':['one','two']}
    def raw(c,s,e,k):
        text = 'Ask' if c['collector_request']['query'].startswith('one') else 'Ask for full approval'
        return envelope(cfg,s,e,[{'channel':{'id':'C1'},'ts':'1767225600.000001','text':text}])
    def primary(c,s,e,req): return envelope(c,s,e,[],recipe_complete=True)
    r,state,_ = collect(tmp_path,cfg,raw,read_replies=primary)
    assert r['status']=='complete'
    assert state['backlog'][0]['candidate']['messages'][0]['text']=='Ask for full approval'


def test_slack_subset_dedupe_preserves_every_real_seed_identity(tmp_path):
    cfg={**CFG,'kind':'slack','seed_queries':['approved']}
    root={'channel':{'id':'C1'},'ts':'1767225600.000001','text':'Root'}
    reply={'channel':{'id':'C1'},'ts':'1767225601.000001','thread_ts':root['ts'],'text':'Reply'}
    raw=lambda c,s,e,k: envelope(cfg,s,e,[root,reply])
    def primary(c,s,e,req):
        messages = [root,reply] if req['operation']=='replies' else [root,{**reply,'text':'Reply with details'}]
        return envelope(c,s,e,messages,recipe_complete=True)
    r,state,_=collect(tmp_path,cfg,raw,read_replies=primary)
    assert r['status']=='complete' and len(state['backlog'])==1
    assert state['backlog'][0]['candidate']['messages'][1]['text']=='Reply with details'
    assert set(state['backlog'][0]['candidate']['source_ids'])=={'slack:account:C1:'+root['ts'],'slack:account:C1:'+reply['ts']}


@pytest.mark.parametrize('status,reason',[(403,'domainPolicy'),(403,'dailyLimitExceeded'),(401,'authError')])
def test_nonquota_structured_errors_do_not_retry(tmp_path,status,reason):
    import json
    class Response(dict): pass
    response = Response(); response.status=status
    class Error(Exception): resp=response; content=json.dumps({'error':{'errors':[{'reason':reason}]}}).encode()
    calls=[]
    def raw(*a): calls.append(1); raise Error('provider refusal')
    r,state,_ = collect(tmp_path,{**CFG,'reader_policy':{'structured_errors':True,'owns_retries':False}},raw)
    assert r['status']!='complete' and calls==[1] and not state.get('watermark')


@pytest.mark.parametrize('owns,structured',[(True,True),(False,False)])
def test_transport_owned_or_unstructured_errors_not_wrapped(tmp_path,owns,structured):
    class Response(dict): status=429
    class Error(Exception): resp=Response(); content=b'{}'
    calls=[]
    def raw(*a): calls.append(1); raise Error('429 quota in prose is not parsed')
    r,_,_ = collect(tmp_path,{**CFG,'reader_policy':{'structured_errors':structured,'owns_retries':owns}},raw)
    assert r['status']!='complete' and calls==[1]


def test_source_nine_attempts_240_second_sleep_gate_not_whole_scan_retry(tmp_path,monkeypatch):
    from alchemy_task import discovery_collectors as module
    from alchemy_task.discovery_sources import QuotaReader
    class Clock:
        now=0
        sleeps=[]
        def monotonic(self): return self.now
        def sleep(self,d): self.sleeps.append(d); self.now+=d
    clock=Clock()
    monkeypatch.setattr(module,'QuotaReader',lambda: QuotaReader(clock=clock,jitter=lambda:0))
    class Response(dict): status=429
    class Error(Exception): resp=Response(); content=b'{}'
    calls=[]
    def raw(*a): calls.append(1); raise Error()
    r,_,_ = collect(tmp_path,{**CFG,'reader_policy':{'structured_errors':True,'owns_retries':False}},raw)
    assert r['status']!='complete' and len(calls)==9
    assert clock.sleeps==[1,2,4,8,16,32,32,32]
    assert r['error']=='source_quota_exhausted'


def test_quota_recovery_budget_is_per_window_not_per_reader_lifetime(tmp_path,monkeypatch):
    from alchemy_task import discovery_collectors as module
    made=[]
    class Quota:
        def __init__(self): made.append(1)
        def execute(self, request): return request()
    monkeypatch.setattr(module,'QuotaReader',Quota)
    cfg={**CFG,'reader_policy':{'structured_errors':True,'owns_retries':False}}
    raw=lambda c,s,e,k: envelope(c,s,e,[])
    reader=module.make_daily_reader(cfg,raw,snapshot_root=tmp_path)
    reader(cfg,START,END,None)
    reader(cfg,END,'2026-01-03T00:00:00+00:00',None)
    assert len(made)==2


def test_thread_fetch_failure_resumes_saved_list_and_successful_primary(tmp_path):
    from alchemy_task.discovery_collectors import make_daily_reader
    calls=[]
    def raw(c,s,e,k):
        calls.append('list')
        return envelope(c,s,e,[{'threadId':'t1'},{'threadId':'t2'}])
    def thread(c,s,e,tid):
        calls.append(tid)
        if tid=='t2' and calls.count(tid)==1: raise RuntimeError('transient source failure')
        return envelope(c,s,e,[{'id':tid,'messages':[message('m'+tid)],'complete':True}])
    store=DiscoveryStore(tmp_path/'state')
    for attempt in range(2):
        reader=make_daily_reader(CFG,raw,snapshot_root=tmp_path/'cache',read_thread=thread)
        r=SourceAdapter(store,CFG,read_page=reader).collect('stream',start=START,end=END)
        if attempt==0:
            assert r['status']!='complete' and not list((tmp_path/'cache').glob('mail-*.json'))
    assert r['status']=='complete' and calls==['list','t1','t2','t2']
    assert len(store.source_state('stream','mail')['backlog'])==2


@pytest.mark.parametrize('defect',['pagination','empty','missing_root'])
def test_slack_thread_pagination_and_missing_primary_remain_partial(tmp_path,defect):
    cfg = {**CFG,'kind':'slack','seed_queries':['<@U1>']}
    seed = {'channel':{'id':'C1'},'ts':'1767225600.000001','thread_ts':'1767225500.000001','text':'Ask'}
    def raw(c,s,e,k): return envelope(cfg,s,e,[seed])
    def partial(c,s,e,req):
        if defect=='empty': return envelope(c,s,e,[])
        if defect=='missing_root': return envelope(c,s,e,[seed])
        return envelope(c,s,e,[seed],pagination_exhausted=False,next_cursor='more')
    r,state,_ = collect(tmp_path,cfg,raw,read_replies=partial)
    # The returned thread lacks its root, so this one thread is skipped (source
    # logs and continues) and reported partial. Seed pages were exhausted, so the
    # window is acquired and does not repeat the same defect every day.
    assert r['status'] == 'partial' and 'C1:1767225500.000001 skipped: primary thread root missing' in r['error']
    assert state['backlog'] == [] and state.get('watermark') == END


