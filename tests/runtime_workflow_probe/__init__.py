"""Synthetic fixture only. Actual pinned integration/handlers, no engine rewrite."""
import copy,json,os,hashlib,subprocess,threading
from pathlib import Path
from . import runtime, task_tools, discovery_integration as di
from .core.config import Settings

ALIASES={'discovery_start':'workflow_probe_discovery_start','discovery_decide':'workflow_probe_discovery_decide'}

def register(ctx):
    class Adapter:
        def __getattr__(self,k): return getattr(ctx,k)
        def get_config(self,k,default=None):
            root=Path(ctx.state.data_dir)/'final-cloud-fixture'
            return {'workspace_root':str(root/'workspace'),'areas':['work'],'default_area':'work','timezone':'UTC','research_by_default':False,'git_transport':'system','git_remote':'origin','git_branch':'main','git_run_hooks':False,'discovery_transport_receipt':json.dumps({'sequential_call':2040,'concurrent_batch':2040})}.get(k,default)
        def register_tool(self,**kw):
            kw=copy.copy(kw); name=ALIASES.get(kw['name'],kw['name']); kw['name']=name
            kw['schema']=copy.deepcopy(kw['schema']);kw['schema']['name']=name
            return ctx.register_tool(**kw)
        def register_hook(self,name,fn):
            if name!='pre_tool_call': return ctx.register_hook(name,fn)
            def guarded(**kw):
                result=fn(**kw)
                s=service()
                if not result and s.runner._child_for(kw.get('session_id',''),kw.get('task_id','')):
                    allowed={'tool_search','tool_describe','tool_call','discovery_research_fetch','discovery_research_submit'}
                    tool=kw.get('tool_name','');nested=(kw.get('args') or {}).get('calls',[]) if tool=='tool_call' else []
                    if isinstance(nested,str):
                        try:nested=json.loads(nested)
                        except ValueError:nested=[None]
                    if tool not in allowed or not isinstance(nested,list) or any(not isinstance(c,dict) or c.get('name') not in allowed for c in nested):
                        return {'action':'block','message':'TEST ONLY containment: synthetic child may fetch frozen full context and submit only. No terminal/code/network/private sources. This is not a production sandbox.'}
                return result
            return ctx.register_hook(name,guarded)
    adapter=Adapter(); runtime.bind(adapter)
    def service():
        rt=runtime.Runtime(adapter)
        key=(id(adapter),str(rt.data_dir))
        if key not in di._services:
            di._services[key]=di.DiscoveryIntegration(rt,profile_home=rt.data_dir/'final-cloud-fixture'/'fixture-profile')
        return di._services[key]
    class RunnerProxy:
        def __getattr__(self,k): return lambda *a,**kw:getattr(service().runner,k)(*a,**kw)
    class ServiceProxy:
        runner=RunnerProxy()
        def __getattr__(self,k):return getattr(service(),k)
    di.register(adapter,integration=ServiceProxy())
    for schema,handler in [(task_tools.DISCOVERY_START_SCHEMA,task_tools.discovery_start),(task_tools.DISCOVERY_DECIDE_SCHEMA,task_tools.discovery_decide)]:
        adapter.register_tool(name=schema['name'],schema=schema,handler=handler,description=schema['description'],toolset='alchemy-task-discovery')
    def add(name,fn,props=None,required=None):
        schema={'name':name,'description':fn.__doc__ or name,'parameters':{'type':'object','properties':props or {},'required':required or []}}
        ctx.register_tool(name=name,schema=schema,handler=fn,description=schema['description'],toolset='workflow-probe-fixture')
    def bootstrap(args,session_id='',**kw):
        """Initialize ONLY canonical fake tasks, bare remote, fixture skill and stream origin. No run/research fabrication."""
        if not session_id:raise ValueError('real host session required')
        s=service();rt=s.rt;root=rt.data_dir/'final-cloud-fixture';ws=rt.settings.root() if (root/'workspace').exists() else root/'workspace'
        if not (root/'initialized.json').exists():
            ws.mkdir(parents=True,exist_ok=True);(ws/'areas/work/tasks').mkdir(parents=True,exist_ok=True)
            remote=root/'remote.git';subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
            def git(*a):return subprocess.run(['git','-C',str(ws),*a],check=True,capture_output=True,text=True).stdout.strip()
            git('init','-b','main');git('config','user.name','Synthetic Canary');git('config','user.email','canary@example.test');git('remote','remove','origin') if 'origin' in git('remote').splitlines() else None;git('remote','add','origin',str(remote))
            existing_titles={d.title for d in rt.store().scan().tasks}
            for i in range(36):
                title=('Archive %02d '%i+('unrelated fixture inventory padding '*4)).strip()
                if title not in existing_titles:rt.store().create(title=title,area='work',undated=True,research=False,confirm_new=True,notes='Unrelated archived project. '+('padding '*100),plan='Unrelated plan.')
            d=rt.store().create(title='ZZZ Order banner',area='work',undated=True,research=False,notes='Original request to buy banner; this was cancelled and completed. source:feed:account:issue:print',plan='ROUTING_FACT_COBALT: Proof approvals must go to the cobalt review queue, NOT the amber purchasing queue. The completed banner must stay completed. New proof approval is a separate action. Follow the installed synthetic-print skill.')
            # Use public store update rather than editing the engine or forging research.
            rt.store().update(d.task_id,{'status':'done'})
            skill=root/'fixture-profile/skills/synthetic-print/SKILL.md';skill.parent.mkdir(parents=True,exist_ok=True)
            skill.write_text('---\nname: synthetic-print\ndescription: Synthetic print approval routing.\n---\nSKILL_FACT_VIOLET: Proof approval needs a 3mm bleed check and the violet verification code. Never order a cancelled banner. Cobalt queue routing is in the full completed task Plan, not the inventory title.\n')
            git('add','.');git('commit','-m','Synthetic canonical task baseline');git('push','-u','origin','main')
            (root/'initialized.json').write_text(json.dumps({'completed_task':d.task_id,'baseline':git('rev-parse','HEAD')}))
        history=root/'messages.json'
        if not history.exists():
            history.write_text(json.dumps([{'id':'fake-existing-binding-proof','target':'synthetic-private-file','text':'FAKE EXISTING HISTORY ONLY: binding verification, not a discovery digest.'}]))
            os.chmod(history,0o600)
        stream=args.get('stream','workflow')
        if not stream.startswith('workflow'):raise ValueError('fixture-only stream name')
        old=ctx.state.get('streams',default={}) or {}
        if stream in old and old[stream]['origin_session']!=session_id:raise ValueError('fixture already bound to actual other parent')
        old[stream]={'name':stream,'mode':'production','areas':['work'],'research_cap':50,'sources':[{'name':'Feed','scope':['synthetic-board'],'method':'workflow_probe_reader'}],'deliver':'origin','origin_session':session_id,'label':'','timezone':'UTC'}
        ctx.state.set('streams',old)
        return json.dumps({'initialized':True,'origin_session':session_id,'tasks':len(rt.store().scan().tasks),'fixture_identity':'Sample User is explicitly approved synthetic fixture owner; no credentials consulted','source_config':{'source_key':'feed','name':'Feed','account_key':'account','scope':['synthetic-board'],'read_method':'workflow_probe_reader','relevance':{'identity_requirements':[],'rules':'Retain unresolved asks assigned to Sample User; distinguish cancelled banner and asks resolved by Other User. Read latest primary, full plausible task Plan and installed skill BEFORE submitting. Record routing and verification facts from those actual resources. Do not imply unfinished work is done.'},'binding':{'tool':'workflow_probe_reader','arguments':{},'request_fields':{'account':'account_key','scope':'scope','start':'start','end':'end','cursor':'cursor'},'response_fields':{k:k for k in ['account_key','scope','start','end','items','next_cursor','pagination_exhausted']}}},'delivery_config':{'delivery_owner':'verified_sender','scheduled_approved':True,'toolsets':['workflow-probe-fixture'],'verification_message_id':'fake-existing-binding-proof','verification_text':'FAKE EXISTING HISTORY ONLY: binding verification, not a discovery digest.','origin_session':session_id,'target':'synthetic-private-file','send_tool':'workflow_probe_sender','read_tool':'workflow_probe_message','send_fields':{'target':'target','text':'text'},'send_id_path':'id','read_fields':{'id':'message_id'},'read_response':{'message_id':'id','target':'target','text':'text'}},'next':'Configure source and delivery with actual discovery_config, alias start, collect both reader pages, context with required research guidance; actual research_run. Fetch entire child payload without token/binding; do not repair missing child facts.'})
    add('workflow_probe_bootstrap',bootstrap,{'stream':{'type':'string'}})
    def reader(a,**kw):
        """Configured fake raw provider pages; never dereferences .test URLs. Full provider fields retained by actual generic binding."""
        item={'source_ids':['source:feed:account:issue:print'],'title':'Print project latest decisions','source_revision':'old-v1','body':'PRIMARY_PAGE_ONE: Order banner immediately. This historical request is superseded by page two.','messages':[{'id':'old','body':'Order banner immediately.'}], 'provider_details':{'raw':True}}
        if a.get('cursor'):
            item.update(source_revision='final-v2',body='PRIMARY_PAGE_TWO: Latest primary cancels banner order. Sample User must approve the print proof. Other User already resolved the supplier chase; do not assign that chase to Sample User. Read the full completed Order banner task Plan for mandatory routing; read installed synthetic-print skill for bleed and verification code. Approval is sufficient research, NOT finished execution.',messages=[{'id':'old','body':'Order banner immediately.'},{'id':'latest','body':'Cancel banner order. Sample User owns print-proof approval; Other User completed supplier chase. Approval needs full task Plan routing and installed skill verification.'}])
        calls=ctx.state.get('provider-calls',default=[]) or [];calls.append(a);ctx.state.set('provider-calls',calls)
        return json.dumps({'account_key':a['account'],'scope':a['scope'],'start':a['start'],'end':a['end'],'items':[item],'next_cursor':None if a.get('cursor') else 'page-two','pagination_exhausted':bool(a.get('cursor'))})
    add('workflow_probe_reader',reader,{k:{'type':'string'} for k in ['account','start','end','cursor']}|{'scope':{'type':'array'}},['account','scope','start','end'])
    def sender(a,**kw):
        """Approved fake sender with actual private fixture-file side effect; no real messaging target."""
        if a['target']!='synthetic-private-file':raise ValueError('nonfixture target')
        p=service().rt.data_dir/'final-cloud-fixture/messages.json';data=json.loads(p.read_text()) if p.exists() else []
        data.append({'id':'fake-message-'+str(len(data)+1),'target':a['target'],'text':a['text']});p.write_text(json.dumps(data));os.chmod(p,0o600)
        return json.dumps({'id':data[-1]['id']})
    add('workflow_probe_sender',sender,{'target':{'type':'string'},'text':{'type':'string'}},['target','text'])
    def message(a,**kw):
        """Read back exact synthetic message from fixture-file side effect."""
        p=service().rt.data_dir/'final-cloud-fixture/messages.json';data=json.loads(p.read_text()) if p.exists() else []
        return json.dumps(next((x for x in data if x['id']==a['id']),{'error':'unknown message'}))
    add('workflow_probe_message',message,{'id':{'type':'string'}},['id'])
    def receipt(a,**kw):
        """Read canonical fake task tree, exact bare-remote tree, delivery file and engine hashes independently."""
        s=service();root=s.rt.data_dir/'final-cloud-fixture';ws=root/'workspace'
        def git(*args):return subprocess.run(['git','-C',str(ws),*args],capture_output=True,text=True).stdout.strip()
        remote=subprocess.run(['git','--git-dir',str(root/'remote.git'),'rev-parse','refs/heads/main'],capture_output=True,text=True).stdout.strip()
        docs=[{'id':d.task_id,'title':d.title,'status':str(d.fm.get('status')),'body':d.body,'path':s.rt.store().rel(d.path)} for d in s.rt.store().scan().tasks if d.title.startswith('ZZZ') or 'discovery-dossier:start' in d.body]
        return json.dumps({'runtime':{'pid':os.getpid(),'thread':threading.current_thread().name},'local_head':git('rev-parse','HEAD'),'remote_head':remote,'local_tree':git('rev-parse','HEAD^{tree}'),'remote_tree':subprocess.run(['git','--git-dir',str(root/'remote.git'),'rev-parse','refs/heads/main^{tree}'],capture_output=True,text=True).stdout.strip(),'status':git('status','--short'),'tasks':len(s.rt.store().scan().tasks),'relevant_docs':docs,'provider_calls':ctx.state.get('provider-calls',default=[]),'messages':json.loads((root/'messages.json').read_text()) if (root/'messages.json').exists() else [],'engine_hashes':{f:hashlib.sha256((Path(__file__).parent/f).read_bytes()).hexdigest() for f in ['discovery_runner.py','discovery_integration.py','core/discovery_state.py']}})
    add('workflow_probe_receipt',receipt)
