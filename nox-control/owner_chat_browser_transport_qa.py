"""Exact-source diagnostic overlay for one real owner browser conversation.

The production UI, model, proxy and frozen browser acceptance are unchanged.
Only the private QA process gains wire/read timing, verified viewport sizes and
a longer public numeric fixture. Native log reads export categories/counts only.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import time
import urllib.parse

BASE_SHA='87e098cacfb4063cc9d2ff1d6d80dcba895dc6ac482789ddd2968d848454aa08'
# Includes both exact PROXY_CHANGES from installed training binding91df0894.
PROXY_FUNCTION_SHA='f849432d675eb3732076634b359ebbb6e516c3361ddba441def7f6dc7e355daf'
STREAM_SHA='5b7bafde0c25fa26d6b8f98dfbb4958f0faa42ee77292da561834a63097a2e8e'
BRIDGE_SHA='7669bf1c3158c0f30f0f4ee6302427e540618041c9a8c554320464045973dc6c'
EXPECTED=','.join(str(n) for n in range(1,41))


def digest(raw):return hashlib.sha256(raw).hexdigest()
def replace_once(source,old,new):
    if source.count(old)!=1:raise RuntimeError('HOLD_QA_DIAGNOSTIC_SOURCE_ANCHOR')
    return source.replace(old,new,1)


def public_numeric_answer(value):
    if not isinstance(value,str) or len(value)>512 or not re.fullmatch(r'[0-9,\s]+',value):return None
    return re.sub(r'\s+','',value)


VIEWPORT_JS=r"""() => ({
 width:window.innerWidth,height:window.innerHeight,
 document_width:document.documentElement.clientWidth,document_height:document.documentElement.clientHeight,
 visual_width:window.visualViewport?.width??null,visual_height:window.visualViewport?.height??null,
 device_pixel_ratio:window.devicePixelRatio,
 width_is_own_property:Object.prototype.hasOwnProperty.call(window,'innerWidth'),
 height_is_own_property:Object.prototype.hasOwnProperty.call(window,'innerHeight')
})"""


def viewport_projection(dom,metrics,requested):
    """Project numeric actual CDP/DOM values, never cached page.viewport_size."""
    result={'requested':dict(requested),'dom':{},'cdp':{},'matches':False}
    for key in ('width','height','document_width','document_height','visual_width','visual_height','device_pixel_ratio'):
        value=dom.get(key) if isinstance(dom,dict) else None
        result['dom'][key]=value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=32768 else None
    for field in ('cssLayoutViewport','cssVisualViewport'):
        source=metrics.get(field) if isinstance(metrics,dict) else None
        source=source if isinstance(source,dict) else {}
        result['cdp'][field]={}
        for key in ('clientWidth','clientHeight'):
            value=source.get(key)
            result['cdp'][field][key]=value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=32768 else None
    result['matches']=(result['dom']['width']==requested['width'] and result['dom']['height']==requested['height']
        and all(result['cdp'][field]['clientWidth']==requested['width']
                and result['cdp'][field]['clientHeight']==requested['height'] for field in result['cdp']))
    return result


async def apply_verified_viewport(page,width,height,stop):
    wanted={'width':width,'height':height}
    await asyncio.wait_for(page.set_viewport_size(wanted),timeout=3)
    deadline=time.monotonic()+3
    attempts=[]
    while True:
        if stop():raise RuntimeError('HOLD_OWNER_STOP')
        dom=await asyncio.wait_for(page.evaluate(VIEWPORT_JS),timeout=1)
        metrics=await asyncio.wait_for(page._nox_transport_cdp.send('Page.getLayoutMetrics'),timeout=1)
        proof=viewport_projection(dom,metrics,wanted)
        if len(attempts)<16:attempts.append(proof)
        if proof['matches'] or time.monotonic()>=deadline:
            return {'state':'VERIFIED' if proof['matches'] else 'NOT_APPLIED',
                    'attempts':len(attempts),'first':attempts[0],'last':proof}
        await asyncio.sleep(.2)


async def layout_cases(core,page,report,cases):
    recorded=report.setdefault('report_layout_cases',[])
    for width,height,opened in cases:
        row={'opened':opened,'viewport_width':width,'viewport_height':height}
        recorded.append(row)
        row['viewport_proof']=await apply_verified_viewport(page,width,height,core.stop_present)
        if row['viewport_proof']['state']!='VERIFIED':
            raise RuntimeError('HOLD_QA_VIEWPORT_NOT_APPLIED')
        await asyncio.wait_for(page.evaluate("""async opened=>{
          for(const node of document.querySelectorAll('.nox-owner-reports'))node.open=opened;
          const stack=document.querySelector('.nox-owner-status-stack');if(stack)stack.scrollTop=0;
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        }""",opened),timeout=2)
        value=await page.evaluate(core.COMPOSER_JS);row['geometry']=value
        if (value.get('viewport_width')!=width or value.get('viewport_height')!=height
                or not core.composer_layout_valid(value,opened)):
            raise RuntimeError('HOLD_QA_REPORTS_COMPOSER_LAYOUT')
    moved=await page.evaluate("""()=>{
      const node=document.querySelector('.nox-owner-status-stack');if(!node)return false;
      const old=node.scrollTop;node.scrollTop=node.scrollHeight;
      const moved=node.scrollTop>0;node.scrollTop=old;
      return node.scrollHeight<=node.clientHeight+1||moved;
    }""")
    report['report_scroll_verified']=moved
    if moved is not True:raise RuntimeError('HOLD_QA_REPORTS_SCROLL')


class WireTiming:
    """CDP event metadata only. No response body/header/cookie is requested."""
    def __init__(self,origin):
        self.origin=origin;self.request_id=None;self.start=None
        self.result={'scope':'ONE_SYNTHETIC_NATIVE_POST_NETWORK_EVENTS','target_requests':0,
            'response_ms':None,'finished_ms':None,'status':None,'data_events':[],
            'data_event_count':0,'decoded_bytes':0,'encoded_bytes':0,
            'failed':False,'response_bodies_or_headers_exported':False}

    def offset(self,event):
        value=event.get('timestamp')
        if self.start is None or type(value) not in (int,float) or not math.isfinite(value):return None
        value=round((value-self.start)*1000,3)
        return value if 0<=value<=180000 else None

    def request(self,event):
        request=event.get('request') or {}
        try:url=urllib.parse.urlsplit(request.get('url',''))
        except (TypeError,ValueError):return
        if url.netloc!=self.origin or url.path!='/api/nox/chat/stream' or request.get('method')!='POST':return
        self.result['target_requests']+=1
        if self.result['target_requests']!=1:return
        self.request_id=event.get('requestId')
        value=event.get('timestamp')
        self.start=value if type(value) in (int,float) and math.isfinite(value) else None

    def response(self,event):
        if event.get('requestId')!=self.request_id or self.request_id is None:return
        value=(event.get('response') or {}).get('status')
        self.result['status']=value if type(value) is int and 100<=value<=599 else None
        self.result['response_ms']=self.offset(event)

    def data(self,event):
        if event.get('requestId')!=self.request_id or self.request_id is None:return
        row={'at_ms':self.offset(event)}
        for original,key in (('dataLength','decoded_bytes'),('encodedDataLength','encoded_bytes')):
            value=event.get(original)
            row[key]=value if type(value) is int and 0<=value<=1048576 else None
            if row[key] is not None:self.result[key]+=row[key]
        self.result['data_event_count']+=1
        if len(self.result['data_events'])<96:self.result['data_events'].append(row)

    def finished(self,event):
        if event.get('requestId')==self.request_id and self.request_id is not None:
            self.result['finished_ms']=self.offset(event)

    def failed(self,event):
        if event.get('requestId')==self.request_id and self.request_id is not None:self.result['failed']=True

    def snapshot(self):return dict(self.result)


async def wire_start(context,page,origin):
    tracker=WireTiming(origin)
    client=await context.new_cdp_session(page);page._nox_transport_cdp=client
    for event,handler in (('requestWillBeSent',tracker.request),('responseReceived',tracker.response),
                          ('dataReceived',tracker.data),('loadingFinished',tracker.finished),('loadingFailed',tracker.failed)):
        client.on('Network.'+event,handler)
    await client.send('Network.enable',{'maxPostDataSize':0})
    return tracker


def read_regular(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=limit:raise ValueError('SOURCE_SIZE')
        raw=os.read(fd,limit+1);after=os.fstat(fd)
        if len(raw)!=before.st_size or (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('SOURCE_CHANGED')
        return raw
    finally:os.close(fd)


class RouteEvidence:
    """Existing log evidence excludes an early understanding return, nothing more."""
    def __init__(self,proxy,prompt):
        self.fd=None;self.start=None;self.path=None;self.prompt=prompt
        self.result={'scope':'EXISTING_PROXY_LOG_AFTER_EARLY_UNDERSTANDING_BRANCH',
            'state':'UNAVAILABLE','source_verified':False,'post_understanding_matches':0,
            'ttft_matches':0,'build_ms':None,'proxy_first_stream_byte_ms':None,
            'early_understanding_return_excluded':False,'upstream_model_request_bound':False,
            'raw_log_or_prompt_exported':False}
        try:
            scripts=Path('/root/nox/scripts')
            raw=read_regular(scripts/'chat_proxy.py',1048576);source=raw.decode()
            function=next(node for node in ast.parse(source).body
                          if isinstance(node,ast.AsyncFunctionDef) and node.name=='_proxy_completion')
            actual=digest(ast.get_source_segment(source,function).encode())
            stream=digest(read_regular(scripts/'owner_chat_stream.py',262144))
            bridge=digest(read_regular(scripts/'nox_v29_chat_bridge.py',262144))
            self.result['source_sha256']={'proxy_function':actual,'stream':stream,'bridge':bridge}
            if (actual,stream,bridge)!=(PROXY_FUNCTION_SHA,STREAM_SHA,BRIDGE_SHA):
                self.result['state']='SOURCE_CHANGED';return
            self.result['source_verified']=True
            folder=Path(proxy.LOGS)
            if folder not in (Path('/root/nox/logs'),Path('/root/nox/log')) or folder.is_symlink():
                self.result['state']='LOG_PATH_UNAVAILABLE';return
            self.path=folder/'proxy.log'
            self.fd=os.open(self.path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
            self.start=os.fstat(self.fd)
            if not stat.S_ISREG(self.start.st_mode):raise ValueError('LOG_TYPE')
            self.result['state']='WINDOW_OPEN'
        except (OSError,ValueError,TypeError,AttributeError,StopIteration,SyntaxError):
            if self.fd is not None:os.close(self.fd);self.fd=None
            self.result['state']='UNAVAILABLE'

    def finish(self):
        try:
            if self.fd is None:return self.result
            after=os.fstat(self.fd);path=self.path.stat(follow_symlinks=False)
            if (after.st_dev,after.st_ino)!=(self.start.st_dev,self.start.st_ino) or (path.st_dev,path.st_ino)!=(after.st_dev,after.st_ino):
                self.result['state']='LOG_ROTATED';return self.result
            size=after.st_size-self.start.st_size
            if not 0<=size<=262144:self.result['state']='LOG_WINDOW_BUDGET';return self.result
            raw=os.pread(self.fd,size,self.start.st_size)
            if len(raw)!=size:self.result['state']='LOG_WINDOW_CHANGED';return self.result
            suffix=' user='+repr(self.prompt.replace('\n',' ')[:80])
            builds=[];first=[]
            for line in raw.decode('utf-8','replace').splitlines():
                if not line.endswith(suffix):continue
                match=re.search(r'chat_timing build_ms=([0-9]{1,7}) cedr_ready=(?:True|False) seed=[0-9]{1,15} cache_prompt=(?:True|False) user=',line)
                if match:builds.append(int(match[1]))
                match=re.search(r'chat_ttft ttft_s=([0-9]+(?:\.[0-9]+)?) user=',line)
                if match:
                    value=float(match[1])*1000
                    if math.isfinite(value) and value<=180000:first.append(round(value,3))
            self.result.update(state='WINDOW_READ',window_bytes=size,
                post_understanding_matches=len(builds),ttft_matches=len(first),
                build_ms=builds[0] if len(builds)==1 else None,
                proxy_first_stream_byte_ms=first[0] if len(first)==1 else None,
                early_understanding_return_excluded=len(builds)==1)
            return self.result
        except (OSError,ValueError,TypeError):
            self.result['state']='LOG_READ_UNAVAILABLE';return self.result
        finally:
            if self.fd is not None:os.close(self.fd);self.fd=None


def install(core,raw):
    if digest(raw)!=BASE_SHA:raise RuntimeError('HOLD_QA_DIAGNOSTIC_BASE_PIN')
    source=raw.decode();tree=ast.parse(source)
    browser=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='browser_run')
    body=ast.get_source_segment(source,browser)
    body=replace_once(body,"Напиши числа от одного до десяти через запятую.",
                      "Напиши все целые числа от одного до сорока по порядку через запятую.")
    body=replace_once(body,'        page=None\n','        page=None;wire_timing=None;route_evidence=None\n')
    body=replace_once(body,'            page=await context.new_page()\n',
        '            page=await context.new_page()\n            wire_timing=await _nox_wire_start(context,page,origin)\n')
    body=replace_once(body,'            started=time.monotonic()\n',
        '            route_evidence=_nox_route_evidence(chat_proxy,prompt)\n            started=time.monotonic()\n')
    body=replace_once(body,'actual_native_model_stream_verified=bool(',
                      'authenticated_native_endpoint_stream_verified=bool(')
    body=replace_once(body,"            report['browser_stage']='QA_COMPLETED_SCREENSHOT'\n",
        "            report['browser_stage']='QA_RESPONSIVE_VIEWPORT'\n"
        "            await _nox_responsive_layout(page,report)\n"
        "            report['browser_stage']='QA_COMPLETED_SCREENSHOT'\n")
    body=replace_once(body,"            report['network']=network\n",
        "            report['transport_diagnostic_schema']='NOX_BROWSER_WIRE_TIMING_V1'\n"
        "            report['fixture_number_count']=40\n"
        "            report['upstream_model_inference_verified']=False\n"
        "            if wire_timing is not None:report['wire_transport']=wire_timing.snapshot()\n"
        "            if route_evidence is not None:report['backend_route_evidence']=route_evidence.finish()\n"
        "            report['network']=network\n")
    observer=core.OBSERVER_JS
    observer=replace_once(observer,'nativeDeltas:0,nativeBytes:0,nativeClosed:false,nativeTerminals:0,answer:',
        'nativeDeltas:0,nativeBytes:0,nativeClosed:false,nativeTerminals:0,nativeResponseAt:null,nativeReadEvents:[],nativeReadCount:0,nativeLastDelta:null,answer:')
    observer=replace_once(observer,'       q.nativeBytes+=part.value.length;',
        '       const readEvent={at_ms:performance.now()-q.started,bytes:part.value.length,delta_frames:0,contains_done:false};\n'
        '       q.nativeReadCount++;q.nativeBytes+=part.value.length;')
    observer=replace_once(observer,'           q.answer+=frame.text;q.nativeDeltas++;',
        '           q.answer+=frame.text;q.nativeDeltas++;readEvent.delta_frames++;q.nativeLastDelta=performance.now()-q.started;')
    observer=replace_once(observer,'           q.nativeDone=performance.now()-q.started;',
        '           q.nativeDone=performance.now()-q.started;readEvent.contains_done=true;')
    observer=replace_once(observer,"         }else if(frame.type==='error'){q.error='HOLD_NATIVE_STREAM_ERROR';}\n       }\n",
        "         }else if(frame.type==='error'){q.error='HOLD_NATIVE_STREAM_ERROR';}\n       }\n"
        '       if(q.nativeReadEvents.length<96)q.nativeReadEvents.push(readEvent);\n')
    observer=replace_once(observer,"       q.answer='';q.done=null;q.error=null;q.nativeClosed=false;q.nativeTerminals=0;",
        "       q.answer='';q.done=null;q.error=null;q.nativeClosed=false;q.nativeTerminals=0;\n"
        '        q.nativeResponseAt=null;q.nativeReadEvents=[];q.nativeReadCount=0;q.nativeLastDelta=null;')
    observer=replace_once(observer,'   if(own){void observe(response.clone());}',
        '   if(own){q.nativeResponseAt=performance.now()-q.started;void observe(response.clone());}')
    snapshot=replace_once(core.SNAPSHOT_JS,' return {native_first_ms:q.nativeFirst,',
        ' return {response_headers_ms:q.nativeResponseAt,native_read_events:q.nativeReadEvents,\n'
        '   native_read_count:q.nativeReadCount,native_last_delta_ms:q.nativeLastDelta,native_first_ms:q.nativeFirst,')
    async def initial_layout(page,report):
        await layout_cases(core,page,report,((1440,1000,False),(1440,1000,True)))
    async def responsive_layout(page,report):
        await layout_cases(core,page,report,((1280,720,True),(1440,1000,True)))
        report['responsive_viewport_verified']=True
    core.OBSERVER_JS=observer;core.SNAPSHOT_JS=snapshot;core.EXPECTED=EXPECTED
    core.public_numeric_answer=public_numeric_answer;core.check_report_layout=initial_layout
    core.__dict__.update(_nox_wire_start=wire_start,_nox_route_evidence=RouteEvidence,
                         _nox_responsive_layout=responsive_layout)
    exec(compile(body,'<reviewed-browser-transport-diagnostic>','exec'),core.__dict__)
    return core
