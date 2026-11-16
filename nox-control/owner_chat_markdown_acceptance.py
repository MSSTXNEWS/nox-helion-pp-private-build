#!/usr/bin/env python3
"""One real public model answer: native NDJSON -> S03 -> final Markdown DOM.

No assistant DOM is injected. No production source, permission, service, model,
settings or training state changes. Existing auth/runtime are source-pinned;
only a single public test dialog and one native generation POST are admitted.
"""
from __future__ import annotations
import ast
import asyncio
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
import time
import types
import urllib.parse

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ENTRY='owner_browser_stream_only_entry.py'
CORE='owner_chat_browser_qa.py'
PINS={ENTRY:'2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
      CORE:'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587'}
PROXY=Path('/root/nox/scripts/chat_proxy.py')
PROXY_SHA='a427aa68ed7760380880c5d1c9ddb0714bef367ee5162a20602dbe43b6722d90'
SCHEMA='NOX_OWNER_REAL_MARKDOWN_ACCEPTANCE_V1'
KIND='real_markdown_acceptance'
PREFIX='NOX_MAINT_REPAIR='
TOTAL_TIMEOUT=140
PUBLIC_CHAT_PATH='/nox-web-v29/pc/v24/nox-v24-chat.js'
OWNER_BRIDGE_PATH='/nox-web-v29/nox-v135-resonance-owner-bridge.js'
PUBLIC_SOURCES={PUBLIC_CHAT_PATH:('PUBLIC_CHAT','3427be9e0a497ad0dd120daaa5007f0daa32f3c97271a10ee3b5f1567abcdd8a',32074),
                OWNER_BRIDGE_PATH:('OWNER_BRIDGE','02d6a0fe1d67dd6d19c020d9cb7540611b1c5ed1dbefa304e483277d140ebffc',20171)}
FIXTURE='# NOX public Markdown fixture\n\n**Verified formatting**\n\n- alpha\n- beta\n\n| key | value |\n| --- | --- |\n| sample | 7 |\n\n```javascript\nconst sample = 7;\n```'
PUBLIC_INSTRUCTION='Выведи точно следующий Markdown, без предисловия, заключения и внешней обёртки из тройных кавычек. Это публичная проверка отображения; инструменты не вызывай. Сохрани все строки:\n\n'

def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_REAL_MARKDOWN_' + code)

def safe(exc):
    value = str(exc)
    return value if re.fullmatch(r'HOLD_[A-Z0-9_]{1,130}', value) else type(exc).__name__

def module(name, raw):
    value = types.ModuleType('_nox_page_' + name.removesuffix('.py'))
    value.__file__ = '<' + name + '>'
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value

def sources():
    out = {}
    for name, pin in PINS.items():
        encoded = BUNDLE.get(name)
        require(isinstance(encoded, str) and 0 < len(encoded) <= 262144, 'BUNDLE_BOUND')
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        out[name] = raw
    return out

def proxy_pin():
    import stat
    fd = os.open(PROXY, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        a = os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_uid == os.geteuid() and not a.st_mode & 0o022
                and 0 < a.st_size <= 262144, 'PROXY_METADATA')
        raw = os.read(fd, 262145); b = os.fstat(fd); named = PROXY.stat(follow_symlinks=False)
        identity = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode)
        require(identity(a) == identity(b) == identity(named) and len(raw) == a.st_size
                and hashlib.sha256(raw).hexdigest() == PROXY_SHA, 'PROXY_PIN')
    finally:
        os.close(fd)

def child_identity(pid):
    with open('/proc/' + str(pid) + '/stat', 'rb') as stream:
        raw = stream.read(8193)
    require(len(raw) <= 8192, 'CHILD_IDENTITY_BOUND')
    fields = raw[raw.rfind(b')') + 2:].split()
    return tuple(int(fields[index]) for index in (1, 2, 3, 19))

def stop_owned_child(proc, identity):
    # Do not poll/wait/reap after TERM until the final group KILL. An exited
    # unreaped leader pins the PGID while a Chromium descendant ignores TERM.
    require(identity is not None and identity[:3] == (os.getpid(), proc.pid, proc.pid)
            and child_identity(proc.pid) == identity, 'CHILD_OWNERSHIP')
    os.killpg(proc.pid, signal.SIGTERM)
    time.sleep(2)
    require(child_identity(proc.pid) == identity, 'CHILD_IDENTITY_CHANGED')
    try: os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    proc.communicate(timeout=3)


PROJECTORS = r'''
def request_gate(method, url, origin, body, did, prompt, admitted):
    try:
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http','https') or parsed.netloc!=origin:
            return 'EXTERNAL_ORIGIN'
        if parsed.path=='/api/nox/chat/stream':
            if (method!='POST' or parsed.query or not isinstance(body,dict)
                    or set(body)!={'message','dialog_id','task','history'}
                    or body.get('message')!=prompt or body.get('dialog_id')!=did
                    or body.get('task')!='general' or body.get('history')!=[]):
                return 'NON_FIXTURE_GENERATION'
            return 'DUPLICATE_GENERATION' if admitted else None
        if method not in ('GET','HEAD'):
            return 'APPLICATION_MUTATION'
        if parsed.path in ('/api/nox/chat','/api/nox/voice/speech','/api/nox/stop'):
            return 'OTHER_MODEL_OR_CONTROL_ROUTE'
        if parsed.path=='/api/nox/history':
            return 'LEGACY_UNSCOPED_HISTORY'
        if parsed.path=='/api/ui/memory/dialogs/history':
            query=urllib.parse.parse_qs(parsed.query,keep_blank_values=True)
            limits=query.get('limit',[])
            if (query.get('dialog_id')!=[did] or set(query)-{'dialog_id','limit'}
                    or len(limits)!=1 or not limits[0].isdigit()
                    or not 1<=int(limits[0])<=100):
                return 'NON_FIXTURE_HISTORY'
        return None
    except Exception:
        return 'UNKNOWN_REQUEST'


def public_answer_valid(answer, fixture):
    return isinstance(answer,str) and len(answer)<=4096 and answer.strip()==fixture


def s03_pair_valid(history,did,prompt,answer,exchange):
    if (not isinstance(history,dict) or history.get('status')!='READY'
            or history.get('dialog_id')!=did or not isinstance(exchange,str)
            or not 6<=len(exchange)<=160):return False
    rows=history.get('messages')
    return (isinstance(rows,list) and len(rows)==2
        and all(isinstance(row,dict) for row in rows)
        and rows[0].get('role')=='user' and rows[0].get('content')==prompt
        and rows[1].get('role')=='assistant' and rows[1].get('content')==answer
        and all(row.get('exchange_id')==exchange for row in rows))


async def observed_await(report,label,operation,timeout):
    if label not in _md_await_labels:raise RuntimeError('HOLD_REAL_MARKDOWN_AWAIT_LABEL')
    rows=report.setdefault('await_diagnostics',[])
    if len(rows)>=64:raise RuntimeError('HOLD_REAL_MARKDOWN_AWAIT_BOUND')
    row={'label':label,'state':'WAITING'};rows.append(row)
    report['browser_stage']=label;started=time.monotonic()
    try:
        if _md_stop():raise RuntimeError('HOLD_OWNER_STOP')
        value=await asyncio.wait_for(operation(),timeout=timeout)
        if _md_stop():raise RuntimeError('HOLD_OWNER_STOP')
        row['state']='RETURNED';return value
    except asyncio.CancelledError:
        row['state']='CANCELLED';raise
    except TimeoutError:
        row.update(state='TIMEOUT',error_category='TIMEOUT')
        raise RuntimeError('HOLD_REAL_MARKDOWN_'+label+'_TIMEOUT') from None
    except BaseException as exc:
        row.update(state='ERROR',error_category=type(exc).__name__)
        raise
    finally:
        row['elapsed_ms']=round((time.monotonic()-started)*1000,3)

'''
exec(compile(PROJECTORS,'<real-markdown-projectors>','exec'),globals())

AWAIT_LABELS=frozenset(('CREATE_DIALOG','NAVIGATION','LIVE_MARKERS','SOURCE_CHAT_ATTACH','SOURCE_BRIDGE_ATTACH','SOURCE_CHAT_BEFORE',
    'SOURCE_BRIDGE_BEFORE','LIBRARY_METHODS','DIALOG_ATTACHED','DIALOG_HIT','RAIL_CLICK',
    'RAIL_VISIBLE','DIALOG_SCROLL','DIALOG_CLICK','DIALOG_FALLBACK_HIT','DIALOG_POINTER',
    'DIALOG_SELECTED','EMPTY_HISTORY','PROMPT_FILL','SEND_ENABLED','SEND_CLICK',
    'SEND_NATIVE_COUNT','SEND_FALLBACK_HIT','SEND_POINTER','STREAM_FINISH',
    'SEND_RELEASE','FINAL_HISTORY','FINAL_DOM','SOURCE_CHAT_AFTER','SOURCE_BRIDGE_AFTER'))

OBSERVE_JS=r'''(() => {
 'use strict';const cfg=__CONFIG__;
 const q=window.__NOX_MARKDOWN_QA={nativeCalls:0,status:null,started:null,first:null,
   doneAt:null,answer:'',done:null,eof:false,error:null,bytes:0,deltas:0,uiBody:null,
   tokenSpanPeak:0,literalMarkdownDuringStream:false,cancelOwn:null};
 const original=window.fetch.bind(window);
 const fail=code=>{throw Error(code);};
 async function observe(response){
   if(!response.body){q.error='HOLD_MARKDOWN_NATIVE_BODY';return;}
   const reader=response.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});
   let buffer='',preparing=false,start=false,done=false,frames=0;
   const line=text=>{
     if(!text.trim())return;if(++frames>1024)fail('HOLD_MARKDOWN_NATIVE_FRAME_BOUND');
     const f=JSON.parse(text);
     if(!f||typeof f!=='object'||Array.isArray(f)||done)fail('HOLD_MARKDOWN_NATIVE_FRAME_ORDER');
     if(f.type==='preparing'){
       if(preparing||start||f.stream_mode!=='NATIVE_TOKEN_STREAM')fail('HOLD_MARKDOWN_NATIVE_PREPARING');
       preparing=true;
     }else if(f.type==='start'){
       if(!preparing||start)fail('HOLD_MARKDOWN_NATIVE_START');start=true;
     }else if(f.type==='delta'){
       if(!start||typeof f.text!=='string'||q.answer.length+f.text.length>4096)fail('HOLD_MARKDOWN_NATIVE_DELTA');
       q.answer+=f.text;q.deltas++;
       if(q.first===null&&f.text.trim())q.first=performance.now()-q.started;
     }else if(f.type==='done'){
       if(!start||f.saved!==true||f.s03_integrated!==true||f.dialog_id!==cfg.did||
          typeof f.exchange_id!=='string'||f.exchange_id.length<6||f.exchange_id.length>160)
         fail('HOLD_MARKDOWN_NATIVE_DONE');
       done=true;q.done={exchange_id:f.exchange_id,saved:true,s03_integrated:true,dialog_matches:true};
       q.doneAt=performance.now()-q.started;
     }else fail('HOLD_MARKDOWN_NATIVE_FRAME');
   };
   try{
     for(;;){
       const part=await reader.read();if(part.done)break;
       q.bytes+=part.value.length;if(q.bytes>65536)fail('HOLD_MARKDOWN_NATIVE_BYTES');
       buffer+=decoder.decode(part.value,{stream:true});let n;
       while((n=buffer.indexOf('\n'))>=0){if(n>8192)fail('HOLD_MARKDOWN_NATIVE_LINE');line(buffer.slice(0,n));buffer=buffer.slice(n+1);}
       if(buffer.length>8192)fail('HOLD_MARKDOWN_NATIVE_LINE');
     }
     buffer+=decoder.decode();if(buffer.trim()||!done||!q.answer.trim())fail('HOLD_MARKDOWN_NATIVE_INCOMPLETE');
     q.eof=true;
   }catch(e){q.error=/^HOLD_[A-Z_]+$/.test(e.message)?e.message:'HOLD_MARKDOWN_NATIVE_OBSERVER';}
   finally{try{void reader.cancel().catch(()=>{});}catch{}}
 }
 window.fetch=async function(input,init){
   let u;try{u=new URL(input instanceof Request?input.url:String(input),location.href);}catch{}
   const own=u&&u.origin===location.origin&&u.pathname==='/api/nox/chat/stream';
   if(!own)return original(input,init);
   q.nativeCalls++;if(q.nativeCalls!==1){q.error='HOLD_MARKDOWN_DUPLICATE_NATIVE';return original(input,init);}
   q.started=performance.now();
   const nodes=document.querySelectorAll('#messages .v24-msg.nox.streaming .body');
   q.uiBody=nodes.length===1?nodes[0]:null;
   const controller=new AbortController(),prior=init?.signal||(input instanceof Request?input.signal:null);
   const stop=()=>controller.abort();q.cancelOwn=stop;
   if(prior?.aborted)stop();else prior?.addEventListener?.('abort',stop,{once:true});
   const next={...(init||{}),signal:controller.signal};
   try{const response=await original(input,next);q.status=response.status;
     if(response.status!==200){q.error='HOLD_MARKDOWN_NATIVE_HTTP';return response;}
     void observe(response.clone());return response;
   }catch(e){q.error='HOLD_MARKDOWN_NATIVE_FETCH';throw e;}
 }
 addEventListener('DOMContentLoaded',()=>{
   const mount=document.getElementById('messages');if(!mount)return;
   new MutationObserver(()=>{
     const node=q.uiBody;if(!node||!mount.contains(node)||q.nativeCalls!==1||q.eof)return;
     q.tokenSpanPeak=Math.min(512,Math.max(q.tokenSpanPeak,node.querySelectorAll('span.tok').length));
     if(node.textContent.includes('# NOX public Markdown fixture'))q.literalMarkdownDuringStream=true;
   }).observe(mount,{subtree:true,childList:true,characterData:true});
 },{once:true});
})();'''

SNAPSHOT_JS=r'''() => {
 const q=window.__NOX_MARKDOWN_QA;if(!q)return null;
 return {native_calls:q.nativeCalls,native_status:q.status,native_first_ms:q.first,
   native_done_ms:q.doneAt,native_delta_count:q.deltas,native_bytes:q.bytes,native_eof:q.eof,
   native_done_verified:!!q.done&&q.done.saved&&q.done.s03_integrated&&q.done.dialog_matches,
   answer_characters:q.answer.length,error:q.error,token_span_peak:q.tokenSpanPeak,
   literal_markdown_during_stream:q.literalMarkdownDuringStream,
   assistant_body_bound:!!q.uiBody&&document.getElementById('messages')?.contains(q.uiBody),
   motion_no_preference:matchMedia('(prefers-reduced-motion: no-preference)').matches,
   motion_reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,
   runtime_reduce:document.documentElement.dataset.reducedMotion==='reduce',
   runtime_eco:document.body.dataset.noxGfx==='ECO',runtime_stop:document.body.dataset.noxFx==='stop'};
}'''

LIBRARIES_JS=r'''() => {
 const version=x=>typeof x==='string'&&/^\d{1,3}(?:\.\d{1,3}){1,3}(?:[-+][A-Za-z0-9._-]{1,20})?$/.test(x)?x:null;
 return {marked_parse:typeof window.marked?.parse==='function',
   dompurify_sanitize:typeof window.DOMPurify?.sanitize==='function',
   highlight_element:typeof window.hljs?.highlightElement==='function',
   marked_version:version(window.marked?.version||window.marked?.VERSION),
   dompurify_version:version(window.DOMPurify?.version),highlight_version:version(window.hljs?.versionString)};
}'''

FINAL_DOM_JS=r'''() => {
 const q=window.__NOX_MARKDOWN_QA,mount=document.getElementById('messages'),node=q?.uiBody;
 if(!q||!node||!mount?.contains(node))return {actual_assistant_body:false,all_checks:false};
 const box=node.getBoundingClientRect(),article=node.closest('article.v24-msg.nox');
 const text=selector=>[...node.querySelectorAll(selector)].map(n=>n.textContent.trim());
 const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 const code=node.querySelector('pre code.language-javascript');
 const checks={actual_assistant_body:!!article&&mount.querySelectorAll('article.v24-msg.nox').length===1,
   visible:box.width>0&&box.height>0&&!document.hidden,
   no_streaming_or_stopped:!!article&&!['streaming','thinking','stopped'].some(c=>article.classList.contains(c)),
   heading:equal(text('h1'),['NOX public Markdown fixture']),
   strong:equal(text('strong'),['Verified formatting']),
   unordered_list:node.querySelectorAll('ul').length===1&&equal(text('ul > li'),['alpha','beta']),
   table:node.querySelectorAll('table').length===1&&equal(text('thead th'),['key','value'])&&equal(text('tbody td'),['sample','7']),
   fenced_code:node.querySelectorAll('pre code').length===1&&!!code&&code.textContent.trim()==='const sample = 7;',
   code_highlight:!!code&&code.classList.contains('hljs')&&!!code.querySelector('.hljs-keyword'),
   no_literal_markdown:!node.textContent.includes('# NOX public Markdown fixture')&&!node.textContent.includes('**Verified formatting**')&&!node.textContent.includes('```'),
   no_active_content:!node.querySelector('script,iframe,object,embed,svg,img,a,form,input,button')&&
     ![node,...node.querySelectorAll('*')].some(n=>[...n.attributes].some(a=>/^on/i.test(a.name)||['src','href','srcdoc'].includes(a.name)))};
 return {actual_assistant_body:true,checks,all_checks:Object.values(checks).every(v=>v===true),
   scope:'ACTUAL_RETAINED_ASSISTANT_MESSAGE_AFTER_NATIVE_EOF_AND_S03',
   assistant_dom_injected:false,raw_html_exported:false};
}'''

# Event correlation adapted from V4 f7e1: only fixed-asset parameters,
# 64 KiB body bounds and exact URL/query rejection differ. No library body fallback.
CDP_SOURCE=r'''
class MarkdownCDPProof:
    PAGE='/nox-web-v29/pc/resonance.html'
    def __init__(self,base,report,path,expected):
        self.base=base;self.origin=urllib.parse.urlsplit(base).netloc
        self.PATH=path;self.label,self.SHA,self.SIZE=expected
        self.frame=None;self.session=None;self.request=None;self.response=False
        self.finished=False;self.failure=None;self.decoded=0;self.encoded=0;self.listeners=[]
        self.document=None;self.navigation_generation=0;self.bound_generation=None;self.detached=False
        self.proof={'schema':'NOX_SAME_PAGE_MARKDOWN_ASSET_CDP_V1','label':self.label,'phase':'SETUP',
            'request_count':0,'response_count':0,'loading_finished':False,
            'get_response_body_calls':0,'body_sha_verified':False,'same_frame_loader_request':False,
            'additional_http_requests':0,'fallbacks_allowed':False,'private_content_exported':False,
            'prior_body_timeout_cause_proven':False,'frame_binding_source':'PRE_GOTO_PAGE_EVENTS',
            'main_frame_navigation_events':0,'main_frame_detached':False}
        report.setdefault('loaded_asset_cdp',{})[self.label]=self.proof
    def valid_id(self,value):
        return isinstance(value,str) and re.fullmatch('[A-Za-z0-9_.:-]{1,160}',value) is not None
    def match_url(self,value,path):
        if not isinstance(value,str) or len(value)>2048:return False
        return value==self.base+path
    def same_asset_path(self,value):
        if not isinstance(value,str) or len(value)>2048:return False
        parsed=urllib.parse.urlsplit(value)
        return parsed.netloc==self.origin and parsed.path==self.PATH
    def reject(self,code):
        if self.failure is None:self.failure=code;self.proof['failure']=code
    def check(self,condition=True,code='EVIDENCE'):
        if not condition:self.reject(code)
        if self.failure is not None:raise RuntimeError('HOLD_REAL_MARKDOWN_CDP_'+self.failure)
    def event(self,kind,event):
        try:
            if not isinstance(event,dict):self.reject('EVENT_SCHEMA');return
            getattr(self,'on_'+kind)(event)
        except Exception:self.reject('EVENT_SCHEMA')
    def on_navigated(self,event):
        frame=event.get('frame')
        if not isinstance(frame,dict):self.reject('FRAME_SCHEMA');return
        if frame.get('id')!=self.frame:
            if frame.get('parentId') is None:self.reject('TOP_FRAME_CHANGED')
            return
        if (frame.get('parentId') is not None or not self.valid_id(frame.get('loaderId'))
                or not isinstance(frame.get('url'),str) or len(frame['url'])>2048
                or frame.get('urlFragment') not in (None,'') or frame.get('unreachableUrl') not in (None,'')):
            self.reject('FRAME_SCHEMA');return
        self.navigation_generation+=1
        self.proof['main_frame_navigation_events']=self.navigation_generation
        if self.navigation_generation>16:self.reject('NAVIGATION_BOUND');return
        if self.request is not None:self.reject('FRAME_NAVIGATED_AFTER_REQUEST')
        self.document={'loader':frame['loaderId'],'url':frame['url']}
    def on_detached(self,event):
        if event.get('frameId')==self.frame:
            self.detached=True;self.proof['main_frame_detached']=True
            self.reject('MAIN_FRAME_DETACHED')
    def on_within_document(self,event):
        if event.get('frameId')!=self.frame:return
        self.navigation_generation+=1
        self.proof['main_frame_navigation_events']=self.navigation_generation
        if self.request is not None:self.reject('SAME_DOCUMENT_NAVIGATION_AFTER_REQUEST');return
        if (self.document is None or self.navigation_generation>16
                or not isinstance(event.get('url'),str) or len(event['url'])>2048):
            self.reject('SAME_DOCUMENT_SCOPE');return
        self.document={'loader':self.document['loader'],'url':event['url']}
    def current_document(self):
        self.check(self.request is not None and self.document is not None and not self.detached
            and self.document['loader']==self.request['loader']
            and self.match_url(self.document['url'],self.PAGE)
            and self.bound_generation==self.navigation_generation,'CURRENT_FRAME_EVENT_CHANGED')
    def on_request(self,event):
        item=event.get('request') or {};rid=event.get('requestId')
        target=self.match_url(item.get('url'),self.PATH)
        if self.same_asset_path(item.get('url')) and (not target or item.get('urlFragment') not in (None,'')):
            self.reject('ASSET_URL_SCOPE');return
        if self.request is not None and rid==self.request['id']:
            self.reject('REDIRECT_OR_DUPLICATE_REQUEST');return
        if not target:return
        self.proof['request_count']+=1
        if (self.proof['request_count']!=1 or not self.valid_id(rid) or item.get('method')!='GET'
                or event.get('type')!='Script' or event.get('frameId')!=self.frame
                or not self.valid_id(event.get('loaderId')) or 'redirectResponse' in event):
            self.reject('REQUEST_SCOPE');return
        self.request={'id':rid,'loader':event['loaderId']}
        self.bound_generation=self.navigation_generation
        self.current_document()
    def on_response(self,event):
        response=event.get('response') or {};rid=event.get('requestId')
        target=self.match_url(response.get('url'),self.PATH)
        if self.same_asset_path(response.get('url')) and not target:
            self.reject('ASSET_URL_SCOPE');return
        if self.request is None or rid!=self.request['id']:
            if target:self.reject('UNBOUND_RESPONSE')
            return
        self.proof['response_count']+=1
        if (self.proof['response_count']!=1 or not target or event.get('type')!='Script'
                or event.get('frameId')!=self.frame or event.get('loaderId')!=self.request['loader']
                or type(response.get('status')) not in (int,float) or response['status']!=200
                or response.get('fromServiceWorker',False) is not False
                or response.get('fromDiskCache',False) is not False
                or response.get('fromPrefetchCache',False) is not False):
            self.reject('RESPONSE_SCOPE');return
        headers=response.get('headers')
        if not isinstance(headers,dict):self.reject('HEADERS');return
        selected={}
        for key,value in headers.items():
            if isinstance(key,str) and key.lower() in ('content-length','content-encoding'):
                key=key.lower()
                if key in selected or not isinstance(value,str) or len(value)>128:self.reject('HEADERS');return
                selected[key]=value
        length=selected.get('content-length');encoding=selected.get('content-encoding','identity').lower()
        if (encoding not in ('identity','gzip','br','deflate') or length is not None
                and (not re.fullmatch('[0-9]{1,8}',length) or not 0<int(length)<=65536)):
            self.reject('HEADER_BOUND');return
        self.response=True;self.proof['response_status']=200
    def on_data(self,event):
        if self.request is None or event.get('requestId')!=self.request['id']:return
        decoded=event.get('dataLength');encoded=event.get('encodedDataLength')
        if self.finished or type(decoded) is not int or type(encoded) is not int or decoded<0 or encoded<0:
            self.reject('DATA_SCOPE');return
        self.decoded+=decoded;self.encoded+=encoded
        if self.decoded>65536 or self.encoded>65536:self.reject('DATA_BOUND')
    def on_finished(self,event):
        if self.request is None or event.get('requestId')!=self.request['id']:return
        size=event.get('encodedDataLength')
        if (self.finished or not self.response or type(size) not in (int,float)
                or not 0<size<=131072):self.reject('FINISHED_BOUND');return
        self.finished=True;self.proof['loading_finished']=True
        self.proof['received_total_bytes']=size
        self.proof['decoded_data_bytes']=self.decoded;self.proof['encoded_data_bytes']=self.encoded
    def on_failed(self,event):
        if self.request is not None and event.get('requestId')==self.request['id']:self.reject('LOADING_FAILED')
    async def attach(self,context,page):
        self.session=await context.new_cdp_session(page)
        self.proof['phase']='INITIAL_FRAME_ID'
        tree=await asyncio.wait_for(self.session.send('Page.getFrameTree'),timeout=1)
        frame=tree.get('frameTree',{}).get('frame',{});self.frame=frame.get('id')
        self.check(self.valid_id(self.frame) and frame.get('parentId') is None,'MAIN_FRAME')
        for event,kind in (('Page.frameNavigated','navigated'),('Page.frameDetached','detached'),
                ('Page.navigatedWithinDocument','within_document'),
                ('Network.requestWillBeSent','request'),('Network.responseReceived','response'),
                ('Network.dataReceived','data'),('Network.loadingFinished','finished'),('Network.loadingFailed','failed')):
            callback=lambda value,k=kind:self.event(k,value)
            self.session.on(event,callback);self.listeners.append((event,callback))
        self.proof['phase']='ENABLE_PAGE_EVENTS'
        await asyncio.wait_for(self.session.send('Page.enable'),timeout=1)
        self.proof['phase']='ENABLE_NETWORK_EVENTS'
        await asyncio.wait_for(self.session.send('Network.enable',{'maxTotalBufferSize':1048576,
            'maxResourceBufferSize':65536,'maxPostDataSize':0}),timeout=1.5)
        self.proof['phase']='ARMED_BEFORE_NAVIGATION'
    async def read_body(self):
        self.check(self.request is not None and self.response and self.finished
            and self.proof['request_count']==self.proof['response_count']==1,'COMPLETE_RESPONSE_REQUIRED')
        self.check(0<self.decoded<=65536 and 0<=self.encoded<=65536,'DATA_EVIDENCE_REQUIRED')
        self.proof['phase']='CURRENT_FRAME_EVENT_BINDING'
        self.current_document()
        self.proof['same_frame_loader_request']=True
        self.check(self.proof['get_response_body_calls']==0,'BODY_ALREADY_REQUESTED')
        self.proof['get_response_body_calls']=1;self.proof['phase']='GET_RESPONSE_BODY'
        value=await asyncio.wait_for(self.session.send('Network.getResponseBody',{'requestId':self.request['id']}),timeout=2.5)
        self.current_document()
        self.check(isinstance(value,dict) and set(value)=={'body','base64Encoded'}
            and isinstance(value.get('body'),str) and type(value.get('base64Encoded')) is bool,'BODY_SCHEMA')
        self.check(len(value['body'])<=(87384 if value['base64Encoded'] else 65536),'BODY_BOUND')
        self.proof['phase']='DECODE_AND_HASH'
        try:
            raw=__import__('base64').b64decode(value['body'],validate=True) if value['base64Encoded'] else value['body'].encode('utf-8')
        except (ValueError,UnicodeError):
            self.reject('BODY_ENCODING');self.check()
        self.proof['returned_body_bytes']=len(raw)
        self.check(0<len(raw)<=65536,'BODY_EMPTY_OR_OVERSIZE')
        self.check(len(raw)==self.SIZE and digest(raw)==self.SHA,'BODY_SHA')
        self.proof['body_sha_verified']=True;self.proof['phase']='BODY_VERIFIED'
        return raw
    def final_check(self):
        self.current_document()
        self.check(self.proof['body_sha_verified'] is True and self.proof['get_response_body_calls']==1
            and self.proof['request_count']==self.proof['response_count']==1,'FINAL_EVIDENCE')
    async def close(self):
        if self.session is None:return
        for event,callback in self.listeners:
            try:self.session.remove_listener(event,callback)
            except Exception:self.proof['own_listener_removal_completed']=False
        try:
            await asyncio.wait_for(self.session.detach(),timeout=1)
            self.proof['own_session_detached']=True
        except Exception:self.proof['own_session_detached']=False
'''

PAGE_TAIL=r'''
            report['owner_auth_verified']={'anonymous_status':401,'login_status':200,'session_status':200}
            report['auth_login_posts']=1
            admitted=0;blocked=collections.Counter();console=collections.Counter();errors=collections.Counter()
            asset_collectors={}
            report.update(dialog_posts_attempted=1,dialogs_created=None,
                dialog_creation_state='REQUESTED_OUTCOME_UNVERIFIED')
            async def create_public_dialog():
                response=await context.request.post(base+'/api/ui/memory/dialogs/create',
                    data={'title':title,'confirmed':True},max_redirects=0,timeout=8000)
                return await json_response(response,32768)
            created=await observed_await(report,'CREATE_DIALOG',create_public_dialog,10)
            did=created.get('dialog_id')
            if not isinstance(did,str) or not re.fullmatch(r'[a-f0-9]{32}',did):
                raise RuntimeError('HOLD_SYNTHETIC_DIALOG_SCOPE')
            report.update(dialogs_created=1,dialog_creation_state='CREATED_ID_VERIFIED')
            write_private(directory/'dialog.json',json.dumps({'schema':'NOX_PUBLIC_MARKDOWN_DIALOG_V1',
                'request':report['request'],'source_sha':report['source_sha'],'dialog_id':did,
                'prompt_sha256':digest(prompt.encode()),'generation_limit':1},sort_keys=True).encode())
            await context.add_init_script(_md_observer_js.replace('__CONFIG__',json.dumps({'did':did})))
            async def guard(route):
                nonlocal admitted
                request=route.request;parsed=urllib.parse.urlsplit(request.url)
                try:body=request.post_data_json if request.method=='POST' else None
                except Exception:body=None
                code=request_gate(request.method,request.url,origin,body,did,prompt,admitted)
                if _md_stop():code='OWNER_STOP'
                if code:
                    blocked[code]+=1;return await route.abort()
                if parsed.path=='/api/nox/chat/stream':admitted+=1
                return await route.continue_()
            await context.route('**/*',guard)
            page=await context.new_page()
            def console_seen(message):
                if message.type in ('error','warning'):console[message.type]+=1
            def error_seen(error):
                found=re.match(r'(TypeError|ReferenceError|SyntaxError|RangeError|Error)\b',str(error))
                errors[found[1] if found else 'JAVASCRIPT_EXCEPTION']+=1
            page.on('console',console_seen);page.on('pageerror',error_seen)
            page.on('dialog',lambda dialog:asyncio.create_task(dialog.dismiss()))
            for path,expected in _md_public_sources.items():
                collector=MarkdownCDPProof(base,report,path,expected)
                asset_collectors[path]=collector
                label='SOURCE_CHAT_ATTACH' if expected[0]=='PUBLIC_CHAT' else 'SOURCE_BRIDGE_ATTACH'
                await observed_await(report,label,lambda c=collector:c.attach(context,page),5)
            response=await observed_await(report,'NAVIGATION',lambda:page.goto(
                base+'/',wait_until='domcontentloaded',timeout=20000),22)
            if response is None or response.status!=200 or urllib.parse.urlsplit(page.url).path!=PAGE:
                raise RuntimeError('HOLD_GRAPHICAL_OWNER_ROUTE')
            await observed_await(report,'LIVE_MARKERS',lambda:page.wait_for_function(
                "window.__NOX_OWNER_LIVE_UI===true && window.__NOX_V135_OWNER_RESONANCE==='OWNER_NATIVE_ONLY' && !!document.querySelector('#prompt')",
                timeout=12000),13)
            async def source_checks(phase):
                values=[]
                for path,expected in _md_public_sources.items():
                    collector=asset_collectors[path]
                    if phase=='BEFORE':
                        label='SOURCE_CHAT_BEFORE' if expected[0]=='PUBLIC_CHAT' else 'SOURCE_BRIDGE_BEFORE'
                        await observed_await(report,label,collector.read_body,4)
                    collector.final_check()
                    values.append({'label':expected[0],'bytes':expected[2],'sha256':expected[1],
                        'verified':True,'body_read_scope':'ONE_SAME_PAGE_CDP_READ' if phase=='BEFORE'
                            else 'CACHED_BODY_HASH_WITH_CURRENT_EVENT_RECHECK'})
                # Recheck both after the second body await: a late duplicate or
                # navigation invalidates even the first asset's previous hash.
                for collector in asset_collectors.values():collector.final_check()
                return values
            report['loaded_sources_before']=await source_checks('BEFORE')
            report['libraries']=await observed_await(report,'LIBRARY_METHODS',lambda:page.evaluate(_md_libraries_js),3)
            if not all(report['libraries'].get(k) is True for k in ('marked_parse','dompurify_sanitize','highlight_element')):
                raise RuntimeError('HOLD_REAL_MARKDOWN_LIBRARY_METHODS')
            mode=await page.evaluate(_md_snapshot_js)
            if (mode is None or mode.get('motion_no_preference') is not True
                    or any(mode.get(k) is not False for k in ('motion_reduced','runtime_reduce','runtime_eco','runtime_stop'))):
                raise RuntimeError('HOLD_REAL_MARKDOWN_NORMAL_MODE')
            report['normal_motion_preference_verified']=True
            target=page.locator('#nativeChats button[role="listitem"]').filter(has=page.get_by_text(title,exact=True)).first
            await observed_await(report,'DIALOG_ATTACHED',lambda:target.wait_for(state='attached',timeout=10000),11)
            control=await observed_await(report,'DIALOG_HIT',lambda:target.evaluate(CONTROL_JS),3)
            if (control['rail_collapsed'] or control['rail_width']<2
                    or control['rail_opacity']==0 or control['rail_pointer_events']=='none'):
                await observed_await(report,'RAIL_CLICK',lambda:page.locator('[data-action="toggle-rail"]').first.click(timeout=3500),4)
                await observed_await(report,'RAIL_VISIBLE',lambda:page.wait_for_function(
                    "document.getElementById('v24Rail')?.dataset.collapsed!=='true' && Number(getComputedStyle(document.getElementById('v24Rail')).opacity)>.95",timeout=5000),6)
            await observed_await(report,'DIALOG_SCROLL',lambda:target.evaluate(
                "el=>el.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'})"),3)
            try:
                await observed_await(report,'DIALOG_CLICK',lambda:target.click(timeout=3500),4)
            except Exception as exc:
                if _md_stop():raise RuntimeError('HOLD_OWNER_STOP') from None
                report['dialog_click_wait']=click_error_projection(exc)
                control=await observed_await(report,'DIALOG_FALLBACK_HIT',lambda:target.evaluate(CONTROL_JS),3)
                if not control['in_view'] or not control['pointer_hit_own_button']:
                    raise RuntimeError('HOLD_QA_DIALOG_POINTER_OCCLUDED') from None
                await observed_await(report,'DIALOG_POINTER',lambda:page.mouse.click(control['x'],control['y']),3)
            await observed_await(report,'DIALOG_SELECTED',lambda:page.wait_for_function(
                "title=>[...document.querySelectorAll('#nativeChats button[role=listitem]')].some(b=>b.getAttribute('aria-current')==='true'&&b.querySelector('.t')?.textContent===title)",
                arg=title,timeout=7000),8)
            async def own_history():
                response=await context.request.get(base+'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6',max_redirects=0,timeout=6000)
                return await json_response(response,32768)
            initial=await observed_await(report,'EMPTY_HISTORY',own_history,7)
            if initial.get('status')!='READY' or initial.get('dialog_id')!=did or initial.get('messages')!=[]:
                raise RuntimeError('HOLD_SYNTHETIC_DIALOG_NOT_EMPTY')
            report['empty_dialog_history_verified']=True
            await observed_await(report,'PROMPT_FILL',lambda:page.locator('#prompt').fill(prompt),4)
            await observed_await(report,'SEND_ENABLED',lambda:page.wait_for_function(
                "!document.querySelector('#chatForm [type=submit]').disabled",timeout=8000),9)
            report['resources_at_submit']=_md_budget()
            started=time.monotonic();send=page.locator('#chatForm [type=submit]')
            try:
                await observed_await(report,'SEND_CLICK',lambda:send.click(timeout=3500),4)
            except Exception as exc:
                if _md_stop():raise RuntimeError('HOLD_OWNER_STOP') from None
                report['send_click_wait']=click_error_projection(exc)
                snap=await observed_await(report,'SEND_NATIVE_COUNT',lambda:page.evaluate(_md_snapshot_js),3)
                if admitted==1 and snap and snap.get('native_calls')==1:
                    report['send_timeout_after_native_request']=True
                else:
                    control=await observed_await(report,'SEND_FALLBACK_HIT',lambda:send.evaluate(CONTROL_JS),3)
                    if admitted!=0 or not snap or snap.get('native_calls')!=0 or not await send.is_enabled() or not control['in_view'] or not control['pointer_hit_own_button']:
                        raise RuntimeError('HOLD_QA_SEND_POINTER_OR_STATE') from None
                    await observed_await(report,'SEND_POINTER',lambda:page.mouse.click(control['x'],control['y']),3)
            async def completed():
                while True:
                    if _md_stop():raise RuntimeError('HOLD_OWNER_STOP')
                    value=await page.evaluate(_md_snapshot_js)
                    if value and value.get('error'):raise RuntimeError(value['error'])
                    if value and value.get('native_eof') and value.get('native_done_verified'):return value
                    await asyncio.sleep(.12)
            report['native_stream']=await observed_await(report,'STREAM_FINISH',completed,80)
            await observed_await(report,'SEND_RELEASE',lambda:page.wait_for_function(
                "!document.querySelector('#chatForm [type=submit]').disabled",timeout=10000),11)
            history=await observed_await(report,'FINAL_HISTORY',own_history,7)
            # Only this newly created public test dialog is read. No raw answer
            # or exchange/dialog identifier is included in the public report.
            wire=await page.evaluate("()=>({answer:window.__NOX_MARKDOWN_QA.answer,exchange:window.__NOX_MARKDOWN_QA.done?.exchange_id})")
            report['s03_readback_verified']=s03_pair_valid(history,did,prompt,wire.get('answer'),wire.get('exchange'))
            answer=wire.get('answer');report['public_fixture_model_output_verified']=public_answer_valid(answer,_md_fixture)
            if isinstance(answer,str):report.update(answer_sha256=digest(answer.encode()),answer_characters=len(answer))
            report['final_dom']=await observed_await(report,'FINAL_DOM',lambda:page.evaluate(_md_final_dom_js),4)
            report['loaded_sources_after']=await source_checks('AFTER')
            report['elapsed_turn_ms']=round((time.monotonic()-started)*1000,3)
            if (admitted!=1 or report['native_stream'].get('native_calls')!=1
                    or report['native_stream'].get('native_status')!=200
                    or report['native_stream'].get('native_done_verified') is not True):
                raise RuntimeError('HOLD_REAL_MARKDOWN_NATIVE_STREAM')
            if not report['s03_readback_verified']:raise RuntimeError('HOLD_REAL_MARKDOWN_S03_PAIR')
            if not report['public_fixture_model_output_verified']:raise RuntimeError('HOLD_REAL_MARKDOWN_MODEL_FIXTURE')
            if report['final_dom'].get('all_checks') is not True:raise RuntimeError('HOLD_REAL_MARKDOWN_FINAL_DOM')
            if errors:raise RuntimeError('HOLD_REAL_MARKDOWN_PAGE_EXCEPTION')
            if _md_stop():raise RuntimeError('HOLD_OWNER_STOP')
            report['markdown_end_to_end_verified']=True
        finally:
            cleanup_cancelled=False
            if 'admitted' in locals():report['native_posts_admitted']=admitted
            if 'blocked' in locals():report['blocked_request_counts']=dict(blocked)
            if 'console' in locals():report['console_counts']=dict(console)
            if 'errors' in locals():report['page_exception_counts']=dict(errors)
            if page is not None:
                try:
                    report['final_stream_snapshot']=await asyncio.wait_for(page.evaluate(_md_snapshot_js),timeout=2)
                    report['session_stop_requested_for_own_pending_stream']=await asyncio.wait_for(page.evaluate(
                        "()=>{const q=window.__NOX_MARKDOWN_QA;if(q?.nativeCalls===1&&!q.eof&&typeof q.cancelOwn==='function'){q.cancelOwn();return true;}return false;}"),timeout=2)
                except asyncio.CancelledError:cleanup_cancelled=True
                except Exception:report['session_cleanup_observation']='UNAVAILABLE'
            if 'asset_collectors' in locals():
                for collector in asset_collectors.values():
                    try:await collector.close()
                    except asyncio.CancelledError:cleanup_cancelled=True
                    except Exception:report['asset_session_cleanup_verified']=False
            try:
                await context.request.post(base+'/chat/logout',data={},max_redirects=0,timeout=3000)
                report['auth_logout_posts']=1
            except asyncio.CancelledError:cleanup_cancelled=True
            except Exception:report['auth_logout_completed']=False
            password=None
            try:await asyncio.wait_for(context.close(),timeout=3)
            except asyncio.CancelledError:cleanup_cancelled=True
            except Exception:report['context_close_verified']=False
            try:await asyncio.wait_for(browser.close(),timeout=3)
            except asyncio.CancelledError:cleanup_cancelled=True
            except Exception:report['browser_close_verified']=False
            if cleanup_cancelled:raise asyncio.CancelledError
'''


def browser_source(raw):
    """Reuse the pinned launch/auth prefix; replace only the test's own tail."""
    require(hashlib.sha256(raw).hexdigest()==PINS[CORE],'CORE_PIN')
    source=raw.decode();tree=ast.parse(source)
    items=[n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='browser_run']
    require(len(items)==1,'BROWSER_FUNCTION')
    body=ast.get_source_segment(source,items[0])
    marker="            created=await json_response(await context.request.post(base+'/api/ui/memory/dialogs/create',\n"
    require(body.count(marker)==1,'AUTH_SEAM');prefix=body[:body.index(marker)]
    changes={
      "    title='NOX Browser QA '+token":"    title='NOX Markdown QA '+token",
      "    prompt='[NOX UI QA '+token+'] Напиши числа от одного до десяти через запятую. Без пояснений и без других слов.'":"    prompt='[NOX public Markdown QA '+token+']\\n'+_md_instruction+_md_fixture",
      "    report.update(nonloopback_auth=True,resources=budget(),synthetic_prompt_sha256=digest(prompt.encode()))":"    report.update(nonloopback_auth=True,resources=_md_budget(),synthetic_prompt_sha256=digest(prompt.encode()),browser_stage='AUTH_AND_BROWSER_PREFIX')",
      "                                         base_url=base,service_workers='block',accept_downloads=False)":"                                         base_url=base,service_workers='block',accept_downloads=False,reduced_motion='no-preference')",
    }
    for old,new in changes.items():require(prefix.count(old)==1,'PREFIX_SEAM');prefix=prefix.replace(old,new)
    result=prefix+PAGE_TAIL
    # The old unsafe global-stop/screenshot/layout tail is never compiled.
    require(all(x not in result for x in ('capture_private_screenshot(', 'check_report_layout(',
        'set_viewport_size(', "request.post(base+'/api/nox/stop'", '.innerHTML=')), 'EXCLUDED_ACTION')
    compile(result,'<public-markdown-browser>','exec')
    return result


def child_program(blobs,request,source,directory):
    report={'schema':SCHEMA,'state':'RUNNING','scope':'ONE_PUBLIC_NATIVE_MODEL_ANSWER_S03_AND_FINAL_MARKDOWN_DOM',
        'request':request,'source_sha':source,'markdown_end_to_end_verified':False,
        'public_fixture_model_output_verified':False,'s03_readback_verified':False,
        'maximum_new_dialogs':1,'maximum_native_posts':1,'dialog_posts_attempted':0,
        'dialogs_created':0,'dialog_creation_state':'NOT_REQUESTED','native_posts_admitted':0,
        'production_changes':False,'private_content_exported':False,'raw_model_answer_exported':False,
        'assistant_dom_injected':False,'screenshots_exported':False,'full_browser_qa_evaluated':False,
        'full_browser_qa_promoted':False,'progressive_stream_acceptance_evaluated':False,
        'upstream_model_inference_verified':False,'upstream_model_request_bound':False,
        'admin_or_tool_requests_from_harness':0,'backend_tool_dispatch_independently_audited':False,
        'rendering_mode':'CPU_SWIFTSHADER_NOT_USER_GPU_BENCHMARK','browser_motion_preference':'no-preference',
        'fixture_sha256':hashlib.sha256(FIXTURE.encode()).hexdigest(),'safe_diagnostics_only':True}
    return ("import asyncio,base64,hashlib,importlib.metadata,json,os,re,sys,time,types,urllib.parse\n"
        "sys.dont_write_bytecode=True\n"
        "os.environ.pop('DEBUG',None);os.environ.pop('PWDEBUG',None)\n"
        "if sys.prefix!='/root/nox/browser_qa/venv' or importlib.metadata.version('playwright')!='1.65.2':raise RuntimeError('HOLD_REAL_MARKDOWN_RUNTIME')\n"
        +'blobs='+repr({k:base64.b64encode(v).decode() for k,v in blobs.items()})+'\n'
        +'pins='+repr(PINS)+'\nloaded={}\n'
        "for name,encoded in blobs.items():\n"
        " raw=base64.b64decode(encoded,validate=True)\n"
        " if hashlib.sha256(raw).hexdigest()!=pins[name]:raise RuntimeError('HOLD_REAL_MARKDOWN_CHILD_PIN')\n"
        " value=types.ModuleType('_markdown_'+name);value.__file__='<'+name+'>';sys.modules[value.__name__]=value\n"
        " exec(compile(raw,value.__file__,'exec'),value.__dict__);loaded[name]=value\n"
        +'core=loaded['+repr(CORE)+'];entry=loaded['+repr(ENTRY)+']\n'
        "os.nice(10)\naffinity=sorted(os.sched_getaffinity(0))\nif len(affinity)>2:os.sched_setaffinity(0,set(affinity[:2]))\n"
        "core.stop_present=entry.stop_present\n"
        "def budget_now():\n value=entry.resource_budget();value['model_slots']=core.idle_slots();return value\n"
        +'core.__dict__.update(_md_stop=entry.stop_present,_md_budget=budget_now,'
        +'_md_await_labels='+repr(AWAIT_LABELS)+',_md_public_sources='+repr(PUBLIC_SOURCES)+','
        +'_md_observer_js='+repr(OBSERVE_JS)+',_md_snapshot_js='+repr(SNAPSHOT_JS)+','
        +'_md_libraries_js='+repr(LIBRARIES_JS)+',_md_final_dom_js='+repr(FINAL_DOM_JS)+','
        +'_md_fixture='+repr(FIXTURE)+',_md_instruction='+repr(PUBLIC_INSTRUCTION)+')\n'
        +'exec(compile('+repr(PROJECTORS)+",'<markdown-projectors>','exec'),core.__dict__)\n"
        +'exec(compile('+repr(CDP_SOURCE)+",'<markdown-cdp>','exec'),core.__dict__)\n"
        +'exec(compile('+repr(browser_source(blobs[CORE]))+",'<real-markdown-browser>','exec'),core.__dict__)\n"
        +'report='+repr(report)+'\nreport["started_at"]=time.time()\n'
        "try:\n"
        +' asyncio.run(asyncio.wait_for(core.browser_run(report,core.Path('+repr(str(directory))+'),core.inventory()),timeout='+str(TOTAL_TIMEOUT)+'))\n'
        " if report['markdown_end_to_end_verified'] is not True:raise RuntimeError('HOLD_REAL_MARKDOWN_ACCEPTANCE')\n"
        " report['state']='REAL_MARKDOWN_END_TO_END_VERIFIED'\n"
        "except BaseException as exc:\n"
        " report.update(state='HOLD',reason='HOLD_REAL_MARKDOWN_TOTAL_TIMEOUT' if isinstance(exc,TimeoutError) else core.safe_error(exc),markdown_end_to_end_verified=False)\n"
        "report['finished_at']=time.time()\n"
        "report['observation_state']='VERIFIED' if report['markdown_end_to_end_verified'] else ('NOT_OBSERVED_NO_POST' if report['native_posts_admitted']==0 else 'OBSERVED_NOT_ACCEPTED')\n"
        +'core.emit('+repr(KIND)+',report)\n'
        "raise SystemExit(0 if report['markdown_end_to_end_verified'] else 2)\n").encode()


def private_record(core,entry,path,value):
    raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True,allow_nan=False).encode()
    require(0<len(raw)<=65536,'RECEIPT_BOUND')
    core.write_private(path,raw)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    require(entry.read_private(path,65536)==raw,'RECEIPT_READBACK')
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def scope_valid(value,request,source):
    if not isinstance(value,dict):return False
    if not (value.get('schema')==SCHEMA and value.get('request')==request and value.get('source_sha')==source):return False
    if any(value.get(k) is not False for k in ('production_changes','private_content_exported',
        'raw_model_answer_exported','assistant_dom_injected','screenshots_exported','full_browser_qa_evaluated',
        'full_browser_qa_promoted','upstream_model_inference_verified','upstream_model_request_bound')):return False
    if any(type(value.get(k)) is not int or value[k] not in (0,1) for k in ('dialog_posts_attempted','native_posts_admitted')):return False
    if value.get('dialogs_created') is not None and (type(value['dialogs_created']) is not int or value['dialogs_created'] not in (0,1)):return False
    if any(type(value.get(k)) is not int or value[k]!=1 for k in ('maximum_native_posts','maximum_new_dialogs')):return False
    if value.get('state')=='REAL_MARKDOWN_END_TO_END_VERIFIED':
        return (value.get('dialogs_created')==value.get('dialog_posts_attempted')==value.get('native_posts_admitted')==1
            and all(value.get(k) is True for k in ('markdown_end_to_end_verified','public_fixture_model_output_verified','s03_readback_verified'))
            and value.get('final_dom',{}).get('all_checks') is True)
    return value.get('state')=='HOLD' and value.get('markdown_end_to_end_verified') is False


def main():
    blobs=sources();entry=module(ENTRY,blobs[ENTRY]);core=module(CORE,blobs[CORE])
    request,source=entry.owner_context();python=entry.existing_runtime();entry.resource_budget();proxy_pin()
    entry.plain_directory(core.STATE,private=True)
    lock=os.open(core.STATE/'qa.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(lock)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600,'QA_LOCK')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        directory=core.STATE/('markdown_'+request)
        require(not directory.exists() and not directory.is_symlink(),'REQUEST_ALREADY_ATTEMPTED')
        directory.mkdir(mode=0o700);entry.plain_directory(directory,private=True)
        private_record(core,entry,directory/'intent.json',{'schema':'NOX_PUBLIC_MARKDOWN_INTENT_V1',
            'request':request,'source_sha':source,'created_at':time.time(),'source_pins':PINS,
            'maximum_native_posts':1,'maximum_new_dialogs':1,'automatic_retry':False})
        program=child_program(blobs,request,source,directory);compile(program,'<public-markdown-child>','exec')
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
            proc=subprocess.Popen([str(python),'-I','-B','-'],stdin=subprocess.PIPE,stdout=output,stderr=errors,
                env=entry.child_environment(request,source),start_new_session=True)
            identity=child_identity(proc.pid)
            try:proc.communicate(program,timeout=165)
            except subprocess.TimeoutExpired:
                stop_owned_child(proc,identity)
                raise RuntimeError('HOLD_REAL_MARKDOWN_CHILD_TIMEOUT') from None
            require(output.tell()<=131072 and errors.tell()<=1048576,'OUTPUT_BOUND')
            output.seek(0);lines=output.read(131073).decode('utf-8','replace').splitlines()
        rows=[json.loads(line[len(PREFIX):]) for line in lines if line.startswith(PREFIX)]
        require(len(rows)==1 and rows[0].get('kind')==KIND,'RESULT')
        value=rows[0].get('data');require(scope_valid(value,request,source),'RESULT_SCOPE')
        proxy_pin();require(not entry.stop_present(),'OWNER_STOP')
        require((proc.returncode==0)==(value.get('state')=='REAL_MARKDOWN_END_TO_END_VERIFIED'),'RESULT_STATE')
        value['source_pins']=PINS
        receipt=private_record(core,entry,directory/'receipt.json',value)
        print(PREFIX+json.dumps({'kind':KIND,'data':value|{'private_receipt':receipt}},separators=(',',':'),allow_nan=False),flush=True)
        if proc.returncode==0:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
        return 0 if proc.returncode==0 else 2
    finally:os.close(lock)


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(PREFIX+json.dumps({'kind':KIND,'data':{'schema':SCHEMA,'state':'HOLD','reason':safe(exc),
            'markdown_end_to_end_verified':False,'private_content_exported':False,
            'native_execution_outcome':'UNKNOWN_IF_CHILD_STARTED; NO_AUTOMATIC_RETRY'}},separators=(',',':')),flush=True)
        raise SystemExit(2)
