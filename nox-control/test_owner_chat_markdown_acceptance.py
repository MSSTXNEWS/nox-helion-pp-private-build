import asyncio
import ast
import base64
import copy
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
import urllib.parse
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('markdown_candidate',HERE/'owner_chat_markdown_acceptance.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def blobs():
    return {m.ENTRY:(HERE/'pinned/browser_normal_v1'/m.ENTRY).read_bytes(),m.CORE:(HERE/m.CORE).read_bytes()}


CDP_PAYLOAD=b'// public synthetic script\n'+b'/'*32048
CDP_BASE='http://127.0.0.2:8080'
CDP_PAGE=CDP_BASE+'/nox-web-v29/pc/resonance.html'


class CDPSession:
    def __init__(self,payload=CDP_PAYLOAD,encoded=False,during_body=None,hang=False):
        self.payload=payload;self.encoded=encoded;self.during_body=during_body;self.hang=hang
        self.calls=[];self.listeners={};self.frames=0;self.detached=False
    async def send(self,method,params=None):
        self.calls.append((method,params))
        if method=='Page.getFrameTree':
            self.frames+=1
            if self.frames!=1:raise AssertionError('No after-navigation FrameTree is permitted')
            return {'frameTree':{'frame':{'id':'main-frame','loaderId':'blank-loader','url':'about:blank'}}}
        if method in ('Page.enable','Network.enable'):return {}
        if method=='Network.getResponseBody':
            if self.hang:await asyncio.Event().wait()
            if self.during_body:self.during_body()
            return {'body':base64.b64encode(self.payload).decode() if self.encoded else self.payload.decode(),
                    'base64Encoded':self.encoded}
        raise AssertionError('Unapproved protocol method')
    def on(self,name,callback):self.listeners[name]=callback
    def remove_listener(self,name,callback):
        if self.listeners.get(name) is callback:del self.listeners[name]
    async def detach(self):self.detached=True


def cdp_collector(session,path=None,report=None):
    path=path or m.PUBLIC_CHAT_PATH
    namespace={'asyncio':asyncio,'re':re,'urllib':urllib,
               'digest':lambda raw:hashlib.sha256(raw).hexdigest()}
    exec(compile(m.CDP_SOURCE,'<markdown-cdp>','exec'),namespace)
    report={} if report is None else report
    expected=(m.PUBLIC_SOURCES[path][0],hashlib.sha256(CDP_PAYLOAD).hexdigest(),len(CDP_PAYLOAD))
    collector=namespace['MarkdownCDPProof'](CDP_BASE,report,path,expected)
    async def new_session(page):return session
    asyncio.run(collector.attach(types.SimpleNamespace(new_cdp_session=new_session),object()))
    return collector,report,expected


def cdp_events(collector,*,url=None,frame='main-frame',loader='page-loader',kind='Script',
               method='GET',redirect=False,response_extra=None,navigation=True,finish=True,request_fragment=None):
    url=url or CDP_BASE+collector.PATH
    if navigation:collector.event('navigated',{'frame':{'id':'main-frame','loaderId':'page-loader','url':CDP_PAGE}})
    request={'requestId':'asset-request','frameId':frame,'loaderId':loader,'type':kind,
             'request':{'url':url,'method':method,'headers':{'Authorization':'private-not-exported'}}}
    if request_fragment is not None:request['request']['urlFragment']=request_fragment
    if redirect:request['redirectResponse']={'status':302}
    collector.event('request',request)
    response={'url':url,'status':200,'fromServiceWorker':False,
              'headers':{'Content-Length':str(len(CDP_PAYLOAD)),'Set-Cookie':'private-not-exported'}}
    response.update(response_extra or {})
    collector.event('response',{'requestId':'asset-request','frameId':frame,'loaderId':loader,'type':kind,'response':response})
    collector.event('data',{'requestId':'asset-request','dataLength':len(CDP_PAYLOAD),'encodedDataLength':len(CDP_PAYLOAD)})
    if finish:collector.event('finished',{'requestId':'asset-request','encodedDataLength':len(CDP_PAYLOAD)+300})
    return request


def source_check_function(collectors,expected,report):
    raw=m.browser_source(blobs()[m.CORE]);tree=ast.parse(raw)
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='source_checks')
    async def observe(report,label,operation,timeout):return await operation()
    namespace={'asset_collectors':collectors,'_md_public_sources':expected,'report':report,'observed_await':observe}
    exec(compile(textwrap.dedent(ast.get_source_segment(raw,node)),'<actual-source-checks>','exec'),namespace)
    return namespace['source_checks']


class MarkdownScope(unittest.TestCase):
    def setUp(self):
        self.did='a'*32;self.origin='127.0.0.2:8080';self.prompt='public fixture'
        self.body={'message':self.prompt,'dialog_id':self.did,'task':'general','history':[]}

    def gate(self,path,method='GET',body=None,count=0):
        return m.request_gate(method,'http://'+self.origin+path,self.origin,body,self.did,self.prompt,count)

    def test_compact_closure_and_generated_program_compile_without_execution(self):
        bs=blobs()
        self.assertEqual(len(bs),2)
        for name,raw in bs.items():self.assertEqual(hashlib.sha256(raw).hexdigest(),m.PINS[name])
        body=m.browser_source(bs[m.CORE]);compile(body,'fixture','exec')
        program=m.child_program(bs,'123','b'*40,Path('/root/nox/state/owner_browser_qa/markdown_123'))
        compile(program,'child','exec');self.assertLess(len(program),150000)
        self.assertIn("anonymous.status!=401",body);self.assertIn("login.status!=200",body)
        self.assertIn("session.status!=200",body);self.assertIn("reduced_motion='no-preference'",body)
        self.assertEqual(body.count("post(base+'/api/ui/memory/dialogs/create'"),1)
        for forbidden in ('capture_private_screenshot(', 'check_report_layout(', 'set_viewport_size(',
                          "request.post(base+'/api/nox/stop'",'.innerHTML='):
            self.assertNotIn(forbidden,body)
        self.assertIn('q.cancelOwn()',body)
        self.assertNotIn('response.body()',body)
        self.assertNotIn('loaded_source_proof',body)
        self.assertEqual(m.CDP_SOURCE.count("'Page.getFrameTree'"),1)
        self.assertEqual(m.CDP_SOURCE.count("'Network.getResponseBody'"),1)
        self.assertNotIn('Network.loadNetworkResource',m.CDP_SOURCE)
        with self.assertRaisesRegex(RuntimeError,'CORE_PIN'):m.browser_source(bs[m.CORE]+b' ')

    def test_one_native_public_post_and_no_tools_or_mutations(self):
        self.assertIsNone(self.gate('/api/nox/chat/stream','POST',self.body))
        self.assertEqual(self.gate('/api/nox/chat/stream','POST',self.body,1),'DUPLICATE_GENERATION')
        for key,value in [('message','private'),('dialog_id','b'*32),('task','admin'),('history',[{}]),('confirmed',True)]:
            changed=self.body|{key:value}
            self.assertEqual(self.gate('/api/nox/chat/stream','POST',changed),'NON_FIXTURE_GENERATION')
        for path in ('/api/settings','/api/nox/stop','/api/ui/admin','/api/ui/memory/dialogs/create','/api/nox/media/generate'):
            self.assertEqual(self.gate(path,'POST',{}),'APPLICATION_MUTATION')
        self.assertEqual(self.gate('/api/nox/chat/stream?extra=1','POST',self.body),'NON_FIXTURE_GENERATION')

    def test_history_and_origin_stay_scoped(self):
        self.assertIsNone(self.gate('/api/ui/memory/dialogs/history?dialog_id='+self.did+'&limit=100'))
        for query in ('dialog_id='+'b'*32+'&limit=6','dialog_id='+self.did+'&limit=101',
                      'dialog_id='+self.did+'&dialog_id='+self.did+'&limit=6',
                      'dialog_id='+self.did+'&limit=6&owner=private'):
            self.assertEqual(self.gate('/api/ui/memory/dialogs/history?'+query),'NON_FIXTURE_HISTORY')
        self.assertEqual(self.gate('/api/nox/history'),'LEGACY_UNSCOPED_HISTORY')
        self.assertEqual(m.request_gate('GET','https://outside.invalid/private',self.origin,None,self.did,self.prompt,0),'EXTERNAL_ORIGIN')
        self.assertIsNone(self.gate(m.PUBLIC_CHAT_PATH))

    def test_s03_same_pair_and_model_fixture_are_independent(self):
        answer=m.FIXTURE;exchange='public-exchange'
        history={'status':'READY','dialog_id':self.did,'store_scope':'OWNER_DIALOG_TABLES_ONLY',
                 'canonical_s03_readback_verified':False,'messages':[
            {'role':'user','content':self.prompt,'exchange_id':exchange},
            {'role':'assistant','content':answer,'exchange_id':exchange}]}
        # A dialog-table pair is not canonical S03, even with exact exchange IDs.
        self.assertFalse(m.s03_pair_valid(history,self.did,self.prompt,answer,exchange))
        self.assertTrue(m.public_answer_valid(answer+'\n',m.FIXTURE))
        for path in ('dialog','exchange','answer','extra','scope','canonical'):
            row=copy.deepcopy(history)
            if path=='dialog':row['dialog_id']='b'*32
            if path=='exchange':row['messages'][1]['exchange_id']='different'
            if path=='answer':row['messages'][1]['content']='not the actual native answer'
            if path=='extra':row['messages'].append(dict(row['messages'][1]))
            if path=='scope':row['store_scope']='S03_ITEMS'
            if path=='canonical':row['canonical_s03_readback_verified']=True
            self.assertFalse(m.s03_pair_valid(row,self.did,self.prompt,answer,exchange))
        self.assertFalse(m.public_answer_valid('```\n'+answer+'\n```',m.FIXTURE))
        self.assertFalse(m.public_answer_valid(answer.replace('sample','other'),m.FIXTURE))

    def test_await_reports_never_export_result_or_error_arguments(self):
        async def run():
            report={}
            async def ok():return {'private':'not exported'}
            async def bad():raise ValueError('SECRET user text bearer header')
            async def slow():await asyncio.sleep(10)
            with patch.dict(m.__dict__,{'_md_await_labels':m.AWAIT_LABELS,'_md_stop':lambda:False}):
                self.assertEqual(await m.observed_await(report,'EMPTY_HISTORY',ok,.1),{'private':'not exported'})
                with self.assertRaises(ValueError):await m.observed_await(report,'FINAL_HISTORY',bad,.1)
                with self.assertRaisesRegex(RuntimeError,'FINAL_DOM_TIMEOUT'):
                    await m.observed_await(report,'FINAL_DOM',slow,.001)
            encoded=json.dumps(report)
            self.assertNotIn('SECRET',encoded);self.assertNotIn('not exported',encoded)
            self.assertEqual([r['state'] for r in report['await_diagnostics']],['RETURNED','ERROR','TIMEOUT'])
        asyncio.run(run())

    def test_await_cancellation_and_stop_propagate(self):
        async def run():
            async def cancelled():raise asyncio.CancelledError()
            report={}
            with patch.dict(m.__dict__,{'_md_await_labels':m.AWAIT_LABELS,'_md_stop':lambda:False}):
                with self.assertRaises(asyncio.CancelledError):await m.observed_await(report,'FINAL_DOM',cancelled,1)
            self.assertEqual(report['await_diagnostics'][0]['state'],'CANCELLED')
            called=[]
            async def action():called.append(True)
            with patch.dict(m.__dict__,{'_md_await_labels':m.AWAIT_LABELS,'_md_stop':lambda:True}):
                with self.assertRaisesRegex(RuntimeError,'HOLD_OWNER_STOP'):await m.observed_await({},'SEND_CLICK',action,1)
            self.assertEqual(called,[])
        asyncio.run(run())

    def test_two_same_page_assets_have_one_body_read_each_and_cached_finish(self):
        report={};collectors={};expected={};sessions=[]
        for index,path in enumerate(m.PUBLIC_SOURCES):
            session=CDPSession(encoded=bool(index));sessions.append(session)
            collector,_,value=cdp_collector(session,path,report);cdp_events(collector)
            collectors[path]=collector;expected[path]=value
        checks=source_check_function(collectors,expected,report)
        before=asyncio.run(checks('BEFORE'));after=asyncio.run(checks('AFTER'))
        self.assertEqual(len(before),2);self.assertTrue(all(row['verified'] for row in before+after))
        self.assertTrue(all(row['body_read_scope']=='CACHED_BODY_HASH_WITH_CURRENT_EVENT_RECHECK' for row in after))
        for session in sessions:
            self.assertEqual([method for method,_ in session.calls],
                ['Page.getFrameTree','Page.enable','Network.enable','Network.getResponseBody'])
            self.assertEqual(session.calls[2][1],{'maxTotalBufferSize':1048576,'maxResourceBufferSize':65536,'maxPostDataSize':0})
            self.assertEqual(session.frames,1)
        for private in ('private-not-exported','asset-request','main-frame','page-loader',CDP_BASE):
            self.assertNotIn(private,json.dumps(report))
        for collector in collectors.values():asyncio.run(collector.close())
        self.assertTrue(all(s.detached and not s.listeners for s in sessions))

    def test_asset_identity_guards_fail_before_any_body_retrieval(self):
        cases=({'url':CDP_BASE+m.PUBLIC_CHAT_PATH+'?variant=1'},
               {'url':CDP_BASE+m.PUBLIC_CHAT_PATH+'#variant'},{'request_fragment':'#variant'},
               {'url':'https://127.0.0.2:8080'+m.PUBLIC_CHAT_PATH},
               {'frame':'foreign-frame'},{'loader':'foreign-loader'},{'kind':'Fetch'},
               {'method':'POST'},{'redirect':True},{'navigation':False},{'finish':False},
               {'response_extra':{'status':302}},
               {'response_extra':{'fromServiceWorker':True}},
               {'response_extra':{'fromDiskCache':True}},
               {'response_extra':{'fromPrefetchCache':True}})
        for options in cases:
            with self.subTest(options=options):
                session=CDPSession();collector,_,_=cdp_collector(session);cdp_events(collector,**options)
                with self.assertRaises(RuntimeError):asyncio.run(collector.read_body())
                self.assertNotIn('Network.getResponseBody',[method for method,_ in session.calls])

    def test_late_first_asset_duplicate_during_second_body_is_rechecked(self):
        report={};collectors={};expected={};requests={};sessions=[]
        for path in m.PUBLIC_SOURCES:
            session=CDPSession();sessions.append(session)
            collector,_,value=cdp_collector(session,path,report);requests[path]=cdp_events(collector)
            collectors[path]=collector;expected[path]=value
        first=collectors[m.PUBLIC_CHAT_PATH];request=dict(requests[m.PUBLIC_CHAT_PATH],requestId='late-asset')
        sessions[1].during_body=lambda:first.event('request',request)
        checks=source_check_function(collectors,expected,report)
        with self.assertRaisesRegex(RuntimeError,'REQUEST_SCOPE'):asyncio.run(checks('BEFORE'))
        self.assertEqual([sum(method=='Network.getResponseBody' for method,_ in session.calls) for session in sessions],[1,1])
        with self.assertRaises(RuntimeError):asyncio.run(checks('AFTER'))

    def test_frame_changes_during_or_after_body_cannot_promote_old_asset_hash(self):
        changes=(('navigated',{'frame':{'id':'main-frame','loaderId':'new-loader','url':CDP_PAGE}}),
                 ('detached',{'frameId':'main-frame'}),
                 ('within_document',{'frameId':'main-frame','url':CDP_PAGE+'#changed'}))
        for phase in ('during','after'):
            for kind,event in changes:
                with self.subTest(phase=phase,kind=kind):
                    session=CDPSession();collector,_,_=cdp_collector(session);cdp_events(collector)
                    if phase=='during':
                        session.during_body=lambda:collector.event(kind,event)
                        with self.assertRaises(RuntimeError):asyncio.run(collector.read_body())
                    else:
                        asyncio.run(collector.read_body());collector.event(kind,event)
                    with self.assertRaises(RuntimeError):collector.final_check()
                    self.assertEqual(session.frames,1)
                    self.assertEqual(sum(method=='Network.getResponseBody' for method,_ in session.calls),1)

    def test_asset_body_bounds_cancellation_and_hash_errors_never_fallback(self):
        for payload in (b'',b'x'*len(CDP_PAYLOAD),b'x'*65537):
            with self.subTest(length=len(payload)):
                session=CDPSession(payload=payload);collector,report,_=cdp_collector(session);cdp_events(collector)
                with self.assertRaises(RuntimeError):asyncio.run(collector.read_body())
                with self.assertRaises(RuntimeError):asyncio.run(collector.read_body())
                self.assertEqual(sum(method=='Network.getResponseBody' for method,_ in session.calls),1)
                self.assertFalse(report['loaded_asset_cdp']['PUBLIC_CHAT']['body_sha_verified'])
        session=CDPSession();collector,_,_=cdp_collector(session);cdp_events(collector,finish=False)
        collector.event('data',{'requestId':'asset-request','dataLength':65537,'encodedDataLength':1})
        with self.assertRaisesRegex(RuntimeError,'DATA_BOUND'):asyncio.run(collector.read_body())
        self.assertNotIn('Network.getResponseBody',[method for method,_ in session.calls])
        session=CDPSession(hang=True);collector,report,_=cdp_collector(session);cdp_events(collector)
        async def cancel_and_close():
            with self.assertRaises(TimeoutError):await asyncio.wait_for(collector.read_body(),.01)
            await collector.close()
        asyncio.run(cancel_and_close())
        self.assertTrue(session.detached)
        self.assertEqual(sum(method=='Network.getResponseBody' for method,_ in session.calls),1)
        self.assertFalse(report['loaded_asset_cdp']['PUBLIC_CHAT']['body_sha_verified'])

    def test_scope_does_not_promote_no_post_or_partial_proof(self):
        value={'schema':m.SCHEMA,'request':'123','source_sha':'b'*40,'state':'REAL_MARKDOWN_END_TO_END_VERIFIED',
            'dialog_posts_attempted':1,'native_posts_admitted':1,'dialogs_created':1,'maximum_native_posts':1,'maximum_new_dialogs':1,
            'markdown_end_to_end_verified':True,'public_fixture_model_output_verified':True,'s03_readback_verified':True,
            'canonical_s03_scope':'S03_ITEMS','canonical_s03_write_verified':True,
            'canonical_s03_readback_verified':True,'final_dom':{'all_checks':True}}
        for k in ('production_changes','private_content_exported','raw_model_answer_exported','assistant_dom_injected',
                  'screenshots_exported','full_browser_qa_evaluated','full_browser_qa_promoted','upstream_model_inference_verified','upstream_model_request_bound'):value[k]=False
        self.assertTrue(m.scope_valid(value,'123','b'*40))
        for k,v in [('native_posts_admitted',0),('s03_readback_verified',False),('canonical_s03_scope','OWNER_DIALOG_TABLES_ONLY'),
                    ('canonical_s03_write_verified',False),('canonical_s03_readback_verified',False),
                    ('dialogs_created',None),('maximum_native_posts',True),('assistant_dom_injected',True)]:
            self.assertFalse(m.scope_valid(value|{k:v},'123','b'*40),(k,v))
        held=value|{'state':'HOLD','markdown_end_to_end_verified':False,'native_posts_admitted':0,'dialogs_created':0,'dialog_posts_attempted':0}
        self.assertTrue(m.scope_valid(held,'123','b'*40))

    def test_private_intent_is_no_clobber_and_read_back(self):
        bs=blobs();core=m.module(m.CORE,bs[m.CORE]);entry=m.module(m.ENTRY,bs[m.ENTRY])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'intent.json';value={'request':'123','maximum_native_posts':1}
            proof=m.private_record(core,entry,path,value)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),proof['sha256'])
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):m.private_record(core,entry,path,value)

    def test_read_only_dom_inspection_and_no_auth_material_in_report_template(self):
        for text in (m.OBSERVE_JS,m.SNAPSHOT_JS,m.FINAL_DOM_JS):
            for forbidden in ('.innerHTML=', '.innerHTML =', 'appendChild(', 'replaceChildren(', 'insertAdjacentHTML('):self.assertNotIn(forbidden,text)
        self.assertIn('ACTUAL_RETAINED_ASSISTANT_MESSAGE',m.FINAL_DOM_JS)
        self.assertIn('node=q?.uiBody',m.FINAL_DOM_JS)
        program=m.child_program(blobs(),'123','b'*40,Path('/root/nox/state/owner_browser_qa/markdown_123')).decode()
        self.assertNotIn("report['password']",program);self.assertNotIn("report['cookie']",program)
        self.assertIn('if cleanup_cancelled:raise asyncio.CancelledError',m.PAGE_TAIL)

    def test_composed_frozen_auth_and_create_path_stops_before_generation(self):
        """Run the generated coroutine, including actual frozen json_response.

        Browser/network are local fakes. The test ends deliberately at goto,
        before any model response or assistant DOM can be manufactured.
        """
        calls=[]
        class Response:
            def __init__(self,status,data=None):self.status=status;self.data=data
            async def body(self):return json.dumps(self.data).encode()
        class Request:
            async def get(self,url,**kw):
                calls.append(('GET',url))
                return Response(401 if url.endswith('/api/ui/executors') else 200,{})
            async def post(self,url,**kw):
                calls.append(('POST',url))
                return Response(200,{'dialog_id':'a'*32} if url.endswith('/dialogs/create') else {})
        class Page:
            def on(self,*args):pass
            async def goto(self,*args,**kwargs):raise RuntimeError('HOLD_TEST_BEFORE_NAVIGATION')
            async def evaluate(self,*args):return None
        class Context:
            request=Request()
            def set_default_timeout(self,*args):pass
            async def add_init_script(self,*args):pass
            async def route(self,*args):pass
            async def new_page(self):return Page()
            async def new_cdp_session(self,page):return CDPSession()
            async def close(self):pass
        class Browser:
            version='140.0'
            async def new_context(self,**kwargs):return Context()
            async def close(self):pass
        class Runtime:
            def __init__(self):self.chromium=self
            async def launch(self,**kwargs):return Browser()
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
        api=types.ModuleType('playwright.async_api');api.async_playwright=Runtime;api.TimeoutError=TimeoutError
        package=types.ModuleType('playwright');package.async_api=api
        proxy=types.ModuleType('chat_proxy');proxy._read_chat_password=lambda:'public-test-password'
        core=m.module(m.CORE,blobs()[m.CORE])
        core.__dict__.update(_md_stop=lambda:False,_md_budget=lambda:{},_md_await_labels=m.AWAIT_LABELS,
            _md_public_sources=m.PUBLIC_SOURCES,_md_observer_js=m.OBSERVE_JS,_md_snapshot_js=m.SNAPSHOT_JS,
            _md_libraries_js=m.LIBRARIES_JS,_md_final_dom_js=m.FINAL_DOM_JS,_md_fixture=m.FIXTURE,
            _md_instruction=m.PUBLIC_INSTRUCTION,local_base=lambda:'http://127.0.0.2:8080',sys=types.SimpleNamespace(path=[]))
        exec(compile(m.PROJECTORS,'helpers','exec'),core.__dict__)
        exec(compile(m.CDP_SOURCE,'cdp-helpers','exec'),core.__dict__)
        exec(compile(m.browser_source(blobs()[m.CORE]),'composed-browser','exec'),core.__dict__)
        report={'request':'123','source_sha':'b'*40,'native_posts_admitted':0}
        with tempfile.TemporaryDirectory() as folder,patch.dict(sys.modules,{'playwright':package,'playwright.async_api':api,'chat_proxy':proxy}):
            with self.assertRaisesRegex(RuntimeError,'HOLD_TEST_BEFORE_NAVIGATION'):
                asyncio.run(core.browser_run(report,Path(folder),{'system_browser_candidates':[]}))
            record=json.loads((Path(folder)/'dialog.json').read_text())
            self.assertEqual(record['dialog_id'],'a'*32)
        self.assertEqual(report['owner_auth_verified'],{'anonymous_status':401,'login_status':200,'session_status':200})
        self.assertEqual(report['dialogs_created'],1);self.assertEqual(report['native_posts_admitted'],0)
        self.assertEqual(sum(method=='POST' and url.endswith('/dialogs/create') for method,url in calls),1)
        self.assertFalse(any('/chat/stream' in url or '/api/nox/stop' in url for _,url in calls))

    def test_real_stream_observer_protocol_abort_and_safe_errors(self):
        harness=r'''
const vm=require('node:vm');const assert=require('node:assert/strict');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,2));
async function run(frames,mode){
 const body={querySelectorAll:()=>[],textContent:''};const mount={contains:x=>x===body};
 let received=null,streamController=null,signal=null;
 const sandbox={URL,Request,Response,ReadableStream,TextDecoder,AbortController,performance,
   location:{href:'http://127.0.0.2:8080/',origin:'http://127.0.0.2:8080'},
   document:{querySelectorAll:()=>[body],getElementById:()=>mount},
   MutationObserver:class{observe(){}},addEventListener:()=>{},
   fetch:async(_url,init)=>{received=init;signal=init.signal;
     const source=new ReadableStream({start(c){streamController=c;
       if(mode==='pending'){signal.addEventListener('abort',()=>c.error(Error('SECRET raw request material')));return;}
       const raw=frames.map(x=>typeof x==='string'?x:JSON.stringify(x)+'\n').join('');
       const encoded=new TextEncoder().encode(raw);
       for(let i=0;i<encoded.length;i+=7)c.enqueue(encoded.slice(i,i+7));c.close();
     }});return new Response(source,{status:200});}};
 sandbox.window=sandbox;vm.createContext(sandbox);
 vm.runInContext(input.observer.replace('__CONFIG__',JSON.stringify({did:'a'.repeat(32)})),sandbox);
 const response=await sandbox.fetch('/api/nox/chat/stream',{method:'POST',body:'PUBLIC',headers:{'X-Public':'fixture'}});
 assert.equal(response.status,200);assert.equal(received.body,'PUBLIC');assert.equal(received.headers['X-Public'],'fixture');
 if(mode==='pending'){sandbox.__NOX_MARKDOWN_QA.cancelOwn();assert.equal(signal.aborted,true);}
 for(let i=0;i<200&&!sandbox.__NOX_MARKDOWN_QA.eof&&!sandbox.__NOX_MARKDOWN_QA.error;i++)await tick();
 return sandbox.__NOX_MARKDOWN_QA;
}
(async()=>{
 const prep={type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},start={type:'start'},delta={type:'delta',text:input.fixture},
   done={type:'done',saved:true,s03_integrated:true,dialog_id:'a'.repeat(32),exchange_id:'public-exchange'};
 let q=await run([prep,start,delta,done]);assert.equal(q.eof,false);assert.equal(q.error,'HOLD_MARKDOWN_CANONICAL_S03_WRITE_UNBOUND');
 const dialogOnly={...done,owner_dialog_saved:true,store_scope:'OWNER_DIALOG_TABLES_ONLY',canonical_s03_write_verified:false};
 q=await run([prep,start,delta,dialogOnly]);assert.equal(q.eof,false);assert.equal(q.error,'HOLD_MARKDOWN_CANONICAL_S03_WRITE_UNBOUND');
 const proven={...done,store_scope:'S03_ITEMS',canonical_s03_write_verified:true};
 q=await run([prep,start,delta,proven]);assert.equal(q.eof,true);assert.equal(q.answer,input.fixture);assert.equal(q.nativeCalls,1);assert.equal(q.error,null);
 q=await run([prep,start,delta,proven,{type:'delta',text:'SECRET trailing'}]);assert.equal(q.eof,false);assert.equal(q.error,'HOLD_MARKDOWN_NATIVE_FRAME_ORDER');
 q=await run([delta,proven]);assert.equal(q.eof,false);assert.equal(q.error,'HOLD_MARKDOWN_NATIVE_DELTA');
 q=await run([prep,start,delta,JSON.stringify(proven)]);assert.equal(q.eof,false);assert.equal(q.error,'HOLD_MARKDOWN_NATIVE_INCOMPLETE');
 q=await run([], 'pending');assert.equal(q.error,'HOLD_MARKDOWN_NATIVE_OBSERVER');assert.equal(q.eof,false);
 console.log('real split streams, terminal ordering, incomplete line, scoped abort and sanitized failure PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',harness],input=json.dumps({'observer':m.OBSERVE_JS,'fixture':m.FIXTURE}),text=True,capture_output=True,timeout=12)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('SECRET',result.stdout)


if __name__=='__main__':unittest.main()
