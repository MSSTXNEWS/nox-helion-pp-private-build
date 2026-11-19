#!/usr/bin/env python3
"""Bounded native Chromium QA of the existing owner's Resonance UI.

No browser, package, service, model or training configuration is installed or
changed here. One synthetic dialog is created through the real owner API. The
browser submits its real form and observes the real model stream and exact owner-dialog receipt.
Screenshots stay in mode-0600 files on NOX; no pixels, credentials, private dialog
titles, model text, console text, response bodies or cookies go to stdout.
The separately pinned ``original_card`` mode verifies one frozen-card UI trace;
its dialog history is supplemental and canonical S03 remains explicitly HOLD.
"""
from __future__ import annotations

import asyncio
import collections
import fcntl
import hashlib
import importlib.metadata
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import struct
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path('/root/nox')
STATE = ROOT/'state/owner_browser_qa'
PAGE = '/nox-web-v29/pc/resonance.html'
BUILD = 'NOX_OWNER_LIVE_RESONANCE_20261116'
PLAYWRIGHT_PIN = '1.65.2'  # Official PyPI metadata checked 2026-11-16.
EXPECTED = '1,2,3,4,5,6,7,8,9,10'
SAFE_API = {'/api/nox/status','/api/nox/chat/stream','/api/nox/stop',
            '/api/ui/executors','/api/ui/memory/dialogs',
            '/api/ui/memory/dialogs/create','/api/ui/memory/dialogs/history',
            '/api/ui/memory/dialogs/exchange-readback',
            '/api/nox/self/observations','/chat/login','/chat/logout','/chat/session'}
SENSITIVE_MASKS = ('#nativeChats','#v24ArchiveList','#noxV22MemoryFull',
                   '#v24System','#chatHold','#noxV22RenameInput')


def emit(kind, value):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},
          separators=(',',':'),allow_nan=False), flush=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_error(exc):
    text = str(exc)
    return text if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', text) else type(exc).__name__


def safe_route(url):
    path = urllib.parse.urlsplit(url).path
    if path in SAFE_API or path in (PAGE,'/','/chat'):
        return path
    if path in ('/pc/v25/nox-shell-v25.css','/pc/v25/nox-ia-v25.json',
                '/pc/vendor/fonts/tektur/tektur.css'):
        return path
    if (path.startswith('/nox-web-v29/') and len(path) <= 220
            and re.fullmatch(r'/[A-Za-z0-9_./-]+', path)
            and path.endswith(('.js','.mjs','.css','.woff','.woff2','.ttf','.svg','.png','.jpg','.webp'))):
        return path
    return '[OTHER_ROUTE]'


def public_numeric_answer(value):
    if not isinstance(value,str) or len(value)>100 or not re.fullmatch(r'[0-9,\s]+',value):
        return None
    return re.sub(r'\s+','',value)


def progressive_stream_valid(value):
    """Require growing visible prefixes while the real native stream is open."""
    if not isinstance(value, dict):
        return False
    lengths = value.get('ui_prefix_lengths_before_done')
    first, done = value.get('ui_first_ms'), value.get('native_done_ms')
    return (value.get('ui_measurement_kind') == 'CUMULATIVE_VISIBLE_ASSISTANT_BODY'
            and type(value.get('native_delta_count')) is int and value['native_delta_count'] >= 2
            and value.get('ui_before_native_done') is True
            and isinstance(lengths, list) and 2 <= len(lengths) <= 80
            and all(type(n) is int and 3 <= n <= 4096 for n in lengths)
            and all(a < b for a, b in zip(lengths, lengths[1:]))
            and type(first) in (int, float) and type(done) in (int, float)
            and 0 <= first < done)


def original_card_ui_trace_projection(trace):
    """Return only fixed, typed fields from the page-controlled UI trace."""
    if not isinstance(trace, list) or len(trace) != 4:
        return []
    specs = (
        ('accepted_input', ('state', 'at_ms', 'user_bubble_visible', 'composer_cleared')),
        ('waiting', ('state', 'at_ms', 'phase', 'indicator_visible')),
        ('answer', ('state', 'at_ms', 'visible_prefix', 'prefix_characters')),
        ('completed', ('state', 'at_ms', 'phase', 'native_done', 'native_eof', 'send_released')),
    )
    projected = []
    for row, (state, fields) in zip(trace, specs):
        if not isinstance(row, dict) or row.get('state') != state:
            return []
        item = {'state': state}
        at_ms = row.get('at_ms')
        if type(at_ms) not in (int, float) or not 0 <= at_ms <= 120000:
            return []
        item['at_ms'] = at_ms
        for key in fields[2:]:
            value = row.get(key)
            if key in ('user_bubble_visible', 'composer_cleared', 'indicator_visible',
                       'visible_prefix', 'native_done', 'native_eof', 'send_released'):
                if type(value) is not bool:
                    return []
            elif key == 'phase':
                allowed = ('thinking', 'waiting') if state == 'waiting' else ('done',)
                if value not in allowed:
                    return []
            elif key == 'prefix_characters':
                if type(value) is not int or not 3 <= value <= 4096:
                    return []
            item[key] = value
        projected.append(item)
    return projected


def original_card_ui_trace_valid(value):
    """Require exact, typed, ordered UI-state rows; reject injected extra fields."""
    if not isinstance(value, dict):
        return False
    trace = value.get('original_card_ui_states')
    if not isinstance(trace, list) or len(trace) != 4:
        return False
    names = ('accepted_input', 'waiting', 'answer', 'completed')
    expected_keys = (
        {'state', 'at_ms', 'user_bubble_visible', 'composer_cleared'},
        {'state', 'at_ms', 'phase', 'indicator_visible'},
        {'state', 'at_ms', 'visible_prefix', 'prefix_characters'},
        {'state', 'at_ms', 'phase', 'native_done', 'native_eof', 'send_released'},
    )
    if any(not isinstance(row, dict) or row.get('state') != name or set(row) != keys
           for row, name, keys in zip(trace, names, expected_keys)):
        return False
    times = [row.get('at_ms') for row in trace]
    if (any(type(item) not in (int, float) for item in times)
            or any(not 0 <= item <= 120000 for item in times)
            or any(left >= right for left, right in zip(times, times[1:]))):
        return False
    accepted, waiting, answer, completed = trace
    native_first = value.get('native_first_ms')
    native_done = value.get('native_done_ms')
    if (type(value.get('native_calls')) is not int or value['native_calls'] != 1
            or type(value.get('total_native_calls')) is not int or value['total_native_calls'] != 1
            or type(value.get('native_delta_count')) is not int or not 2 <= value['native_delta_count'] <= 2048
            or value.get('native_eof') is not True
            or accepted.get('user_bubble_visible') is not True
            or accepted.get('composer_cleared') is not True
            or waiting.get('indicator_visible') is not True
            or waiting.get('phase') not in ('thinking', 'waiting')
            or type(native_first) not in (int, float)
            or not 0 <= native_first <= 120000
            or not times[1] < native_first
            or answer.get('visible_prefix') is not True
            or type(answer.get('prefix_characters')) is not int
            or not 3 <= answer['prefix_characters'] <= 4096
            or type(native_done) not in (int, float)
            or not 0 <= native_done <= 120000
            or not times[2] < native_done
            or completed.get('phase') != 'done'
            or times[3] < native_done
            or completed.get('native_done') is not True
            or completed.get('native_eof') is not True
            or completed.get('send_released') is not True):
        return False
    return True


def original_card_stream_projection(value):
    """Build a bounded report from fixed scalar types and a projected UI trace."""
    if not isinstance(value, dict):
        return {}
    def number(key):
        item = value.get(key)
        return item if type(item) in (int, float) and 0 <= item <= 120000 else None
    def count(key, maximum):
        item = value.get(key)
        return item if type(item) is int and 0 <= item <= maximum else 0
    def boolean(key):
        item = value.get(key)
        return item if type(item) is bool else False
    lengths = value.get('ui_prefix_lengths_before_done')
    if (not isinstance(lengths, list) or len(lengths) > 80
            or any(type(item) is not int or not 3 <= item <= 4096 for item in lengths)):
        lengths = []
    return {
        'native_calls': count('native_calls', 1),
        'total_native_calls': count('total_native_calls', 1),
        'native_delta_count': count('native_delta_count', 2048),
        'native_first_ms': number('native_first_ms'),
        'native_done_ms': number('native_done_ms'),
        'native_eof': boolean('native_eof'),
        'dom_answer_matches_native': boolean('dom_answer_matches_native'),
        'ui_before_native_done': boolean('ui_before_native_done'),
        'ui_prefix_lengths_before_done': list(lengths),
        'original_card_ui_states': original_card_ui_trace_projection(
            value.get('original_card_ui_states')),
    }

def exact_owner_dialog_readback(value, done, dialog_id, prompt, answer):
    """Accept exact supplemental dialog rows; never treat them as canonical S03."""
    if not isinstance(value,dict) or not isinstance(done,dict):
        return False
    ids=('turn_id','receipt_id','lease_epoch','exchange_id')
    if (value.get('status')!='READY' or value.get('durable') is not True
            or value.get('verified') is not True or value.get('dialog_id')!=dialog_id
            or value.get('store_scope')!='OWNER_DIALOG_TABLES_ONLY'
            or value.get('canonical_s03_verified') is not False
            or value.get('writer')!='V112_OWNER_DIALOG_WRITER'
            or done.get('writer')!='V112_OWNER_DIALOG_WRITER'
            or done.get('owner_dialog_saved') is not True
            or done.get('s03_integrated') is not False
            or done.get('canonical_s03_write_verified') is not False
            or any(not isinstance(done.get(key),str) or not re.fullmatch(r'[a-f0-9]{32}',done[key])
                   for key in ('turn_id','receipt_id','lease_epoch'))
            or not isinstance(done.get('exchange_id'),str)
            or not 6<=len(done['exchange_id'])<=160
            or not re.fullmatch(r'[a-f0-9]{64}',str(done.get('receipt_sha256','')))):
        return False
    if any(value.get(key)!=done.get(key) for key in ids) or value.get('receipt_sha256')!=done.get('receipt_sha256'):
        return False
    messages=value.get('messages')
    return (isinstance(messages,list) and len(messages)==2
            and messages[0]=={'role':'user','content':prompt,'exchange_id':done['exchange_id']}
            and messages[1]=={'role':'assistant','content':answer,'exchange_id':done['exchange_id']})


def local_base():
    for _, name in socket.if_nameindex():
        if name=='lo':
            continue
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                value=fcntl.ioctl(sock.fileno(),0x8915,struct.pack('256s',name.encode()[:15]))
            address=socket.inet_ntoa(value[20:24])
            if not ipaddress.ip_address(address).is_loopback:
                return 'http://'+address+':8080'
        except OSError:
            pass
    raise RuntimeError('HOLD_NONLOOPBACK_OWNER_AUTH_REQUIRED')


def stop_paths():
    return tuple(ROOT/name for name in
                 ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')) + (
                     Path('/workspace/NOX_STOP'),)


def stop_present():
    return any(path.exists() or path.is_symlink() for path in stop_paths())


def idle_slots():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline=time.monotonic()+12
    while True:
        if stop_present():
            raise RuntimeError('HOLD_OWNER_STOP')
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise RuntimeError('HOLD_FOREGROUND_CHAT_BUSY')
        with opener.open('http://127.0.0.1:8081/slots',timeout=min(4,remaining)) as response:
            raw=response.read(100001)
        if len(raw)>100000:
            raise RuntimeError('HOLD_SLOTS_RESPONSE_LIMIT')
        slots=json.loads(raw)
        if not isinstance(slots,list) or not 1<=len(slots)<=64:
            raise RuntimeError('HOLD_SLOTS_STATE_UNVERIFIED')
        busy=[]
        for row in slots:
            flags=[row[key] for key in ('is_processing','processing') if isinstance(row,dict) and key in row]
            if not flags or any(type(flag) is not bool for flag in flags) or len(set(flags))!=1:
                raise RuntimeError('HOLD_SLOTS_STATE_UNVERIFIED')
            busy.append(flags[0])
        if stop_present():
            raise RuntimeError('HOLD_OWNER_STOP')
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise RuntimeError('HOLD_FOREGROUND_CHAT_BUSY')
        if not any(busy):
            return len(slots)
        time.sleep(min(1,remaining))


def budget():
    if stop_present():
        raise RuntimeError('HOLD_OWNER_STOP')
    free=shutil.disk_usage(ROOT).free
    if free<1024**3:
        raise RuntimeError('HOLD_BROWSER_DISK_RESERVE')
    headroom=None
    try:
        maximum=(Path('/sys/fs/cgroup')/'memory.max').read_text().strip()
        current=int((Path('/sys/fs/cgroup')/'memory.current').read_text())
        if maximum!='max':
            headroom=int(maximum)-current
            if headroom<3*1024**3:
                raise RuntimeError('HOLD_BROWSER_RAM_RESERVE')
    except (OSError,ValueError):
        raise RuntimeError('HOLD_BROWSER_RAM_UNKNOWN')
    return {'disk_free_bytes':free,'cgroup_headroom_bytes':headroom,'model_slots':idle_slots()}


def inventory():
    paths=[]
    for name in ('chromium','chromium-browser','google-chrome','google-chrome-stable'):
        path=shutil.which(name)
        if path and path not in paths:
            paths.append(path)
    try:
        version=importlib.metadata.version('playwright')
    except importlib.metadata.PackageNotFoundError:
        version=None
    present=importlib.util.find_spec('playwright') is not None
    return {'schema':'NOX_OWNER_BROWSER_AVAILABILITY_V1','python':sys.executable,
            'playwright_installed':present,'playwright_version':version,
            'system_browser_candidates':paths,
            'browser_cache_present':any(p.is_dir() for p in (
                ROOT/'browser_qa/browsers',Path('/root/.cache/ms-playwright'))),
            'proposed_isolated_python':str(ROOT/'browser_qa/venv/bin/python'),
            'proposed_playwright_pin':PLAYWRIGHT_PIN,
            'installs_performed':False,'torch_imported':False}


def write_private(path, content):
    if path.parent.is_symlink() or path.is_symlink():
        raise RuntimeError('HOLD_BROWSER_ARTIFACT_SYMLINK')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())


# Instrumentation forwards each genuine app WebGL call and fetch unchanged.
# It records only the synthetic generation; it never fabricates response bytes.
OBSERVER_JS = r"""
(() => {
 'use strict';
 const cfg=__CONFIG__;
 const q=window.__NOX_BROWSER_QA={totalNativeCalls:0,turns:[],current:null,contexts:[],draws:0};
 const normalize=s=>s.replace(/\s+/g,'');
 const get=HTMLCanvasElement.prototype.getContext;
 HTMLCanvasElement.prototype.getContext=function(...args){
   const ctx=Reflect.apply(get,this,args);
   if(ctx&&!q.contexts.some(item=>item.canvas===this)){
     q.contexts.push({canvas:this,kind:String(args[0]),ctx});
   }
   return ctx;
 };
 for(const name of ['WebGLRenderingContext','WebGL2RenderingContext']){
   const type=window[name];if(!type)continue;
   for(const method of ['drawArrays','drawElements','drawArraysInstanced','drawElementsInstanced']){
     const original=type.prototype[method];if(typeof original!=='function')continue;
     type.prototype[method]=function(...args){q.draws++;return Reflect.apply(original,this,args);};
   }
 }
 let sampleStop=()=>{},sampleUi=()=>{},uiFramePending=false;
 const queueUi=()=>{
   if(uiFramePending||!q.current)return;
   uiFramePending=true;
   requestAnimationFrame(()=>{uiFramePending=false;sampleUi();});
 };
 function visibleBody(node,mount){
   if(!node||!mount.contains(node)||document.hidden)return false;
   const box=node.getBoundingClientRect();
   if(box.width<=0||box.height<=0)return false;
   let left=Math.max(0,box.left),right=Math.min(innerWidth,box.right);
   let top=Math.max(0,box.top),bottom=Math.min(innerHeight,box.bottom),current=node;
   for(let depth=0;current&&depth<24;depth++,current=current.parentElement){
     const style=getComputedStyle(current);
     if(style.display==='none'||['hidden','collapse'].includes(style.visibility)||
        Number(style.opacity)===0||style.contentVisibility==='hidden')return false;
     const clip=current.getBoundingClientRect();
     if(current!==node&&/^(auto|scroll|hidden|clip)$/.test(style.overflowX)){
       left=Math.max(left,clip.left);right=Math.min(right,clip.right);
     }
     if(current!==node&&/^(auto|scroll|hidden|clip)$/.test(style.overflowY)){
       top=Math.max(top,clip.top);bottom=Math.min(bottom,clip.bottom);
     }
   }
   return right>left&&bottom>top;
 }
 function hasState(t,name){return t.originalCardUiStates.some(item=>item.state===name);}
 function recordState(t,name,fields){
   if(t.originalCardUiStates.length>=4||hasState(t,name))return;
   t.originalCardUiStates.push(Object.assign({state:name,
     at_ms:Math.max(0,Math.round(performance.now()-t.started))},fields));
 }
 function lifecycleSample(){
   const t=q.current,mount=document.getElementById('messages');
   if(!cfg.originalCard||!t||t.nativeCalls!==1||!mount)return;
   const prompt=document.getElementById('prompt');
   const user=[...mount.querySelectorAll('.v24-msg.me .body')]
     .find(node=>node.textContent===cfg.expectedPrompt&&visibleBody(node,mount));
   if(!hasState(t,'accepted_input')&&user&&prompt&&prompt.value==='')
     recordState(t,'accepted_input',{user_bubble_visible:true,composer_cleared:true});
   const phase=String(document.body?.dataset?.noxPhase||'');
   const waitingNode=mount.querySelector('.v24-msg.nox.thinking .v24-dots[aria-label="NOX печатает"]');
   const waitingVisible=!!waitingNode&&visibleBody(waitingNode,mount);
   const acceptedState=t.originalCardUiStates.find(item=>item.state==='accepted_input');
   if(acceptedState&&!hasState(t,'waiting')&&performance.now()-t.started>acceptedState.at_ms
      &&t.nativeFirst===null
      &&['thinking','waiting'].includes(phase)&&waitingVisible)
     recordState(t,'waiting',{phase,indicator_visible:true});
   if(t.originalCardUiStates.length===3&&!hasState(t,'completed')&&t.done&&t.nativeEof
      &&phase==='done'&&document.querySelector('#chatForm [type=submit]')?.disabled===false){
     const body=t.uiBody,answerVisible=visibleBody(body,mount)&&typeof body.innerText==='string'
       &&normalize(body.innerText)===normalize(t.answer);
     if(answerVisible)recordState(t,'completed',{phase:'done',native_done:true,
       native_eof:true,send_released:true});
   }
   if(hasState(t,'completed')&&t.lifecycleTimer!==null){
     clearInterval(t.lifecycleTimer);t.lifecycleTimer=null;
   }
 }
 function watch(){
   const mount=document.getElementById('messages');if(!mount)return;
   const form=document.getElementById('chatForm'),stop=form?.querySelector('[data-action=stop]');
   if(form&&stop){sampleStop=()=>{
     const t=q.current;if(!t||t.nativeCalls!==1||stop.disabled||t.stopSamples>=100)return;
     const b=stop.getBoundingClientRect(),x=b.x+b.width/2,y=b.y+b.height/2;
     const visible=b.width>0&&b.height>0&&b.top>=0&&b.bottom<=innerHeight&&b.left>=0&&b.right<=innerWidth;
     const hit=visible?document.elementFromPoint(x,y):null;
     t.stopSamples++;if(visible)t.stopVisibleSamples++;
     if(!hit||!(hit===stop||stop.contains(hit)))t.stopOccludedSamples++;
   };new MutationObserver(sampleStop).observe(form,{subtree:true,attributes:true,attributeFilter:['disabled','style','class']});}
   sampleUi=()=>{
     const t=q.current;if(!t)return;
     lifecycleSample();
     t.uiVisible=visibleBody(t.uiBody,mount);
     if(t.started===null||t.nativeCalls!==1||!t.answer||!t.uiVisible)return;
     const text=t.uiBody.innerText;
     if(typeof text!=='string'||text.length>4096)return;
     const spans=t.uiBody.querySelectorAll('.tok');
     if(spans.length>512)return;
     t.uiMaxTokenSpans=Math.max(t.uiMaxTokenSpans,spans.length);
     if([...spans].some(node=>/[0-9,]/.test(node.textContent)&&!visibleBody(node,mount)))return;
     const actual=normalize(text),wanted=normalize(t.answer);
     if(actual.length<3||!wanted.startsWith(actual))return;
     const now=performance.now()-t.started;
     if(cfg.originalCard&&t.nativeFirst!==null&&!hasState(t,'answer'))
       recordState(t,'answer',{visible_prefix:true,prefix_characters:actual.length});
     if(t.uiFirst===null)t.uiFirst=now;
     if(t.nativeDone===null){
       t.uiBeforeDone=true;
       const before=t.uiPrefixLengthsBeforeDone;
       if(before.length<80&&actual.length>(before.at(-1)||0))before.push(actual.length);
     }
     if(t.uiLengths.length<80&&actual.length>(t.uiLengths.at(-1)||0))t.uiLengths.push(actual.length);
   };
   new MutationObserver(queueUi).observe(mount,{subtree:true,childList:true,characterData:true});
 }
 addEventListener('DOMContentLoaded',watch,{once:true});
 const fetch0=window.fetch.bind(window);
 async function observe(response,t){
   if(!response.body){t.error='HOLD_NO_NATIVE_RESPONSE_BODY';return;}
   const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
   try{
     for(let count=0;count<2048;count++){
       const part=await reader.read();if(part.done){t.nativeEof=true;lifecycleSample();break;}
       t.nativeBytes+=part.value.length;
       if(t.nativeBytes>65536)throw Error('HOLD_QA_STREAM_LIMIT');
       buffer+=decoder.decode(part.value,{stream:true});
       let end;
       while((end=buffer.indexOf('\n'))>=0){
         const line=buffer.slice(0,end);buffer=buffer.slice(end+1);
         if(!line.trim())continue;
         const frame=JSON.parse(line);
         if(frame.type==='delta'){
           if(typeof frame.text!=='string'||t.answer.length+frame.text.length>4096)throw Error('HOLD_QA_ANSWER_LIMIT');
           t.answer+=frame.text;t.nativeDeltas++;
           if(t.nativeFirst===null&&/[^\s.…]/.test(frame.text))t.nativeFirst=performance.now()-t.started;
           // The tee observer and the UI consume independently. A DOM change
           // may precede this clone's frame; retry on the next real paint.
           queueUi();
         }else if(frame.type==='done'){
           t.done={saved:frame.saved===true,owner_dialog_saved:frame.owner_dialog_saved===true,
                   s03_integrated:frame.s03_integrated,
                   canonical_s03_write_verified:frame.canonical_s03_write_verified,
                   dialog_matches:frame.dialog_id===cfg.did,turn_id:frame.turn_id,
                   writer:frame.writer,
                   receipt_id:frame.receipt_id,lease_epoch:frame.lease_epoch,
                   exchange_id:frame.exchange_id,receipt_sha256:frame.receipt_sha256};
           t.nativeDone=performance.now()-t.started;
           lifecycleSample();
         }else if(frame.type==='error'){t.error='HOLD_NATIVE_STREAM_ERROR';}
       }
     }
   }catch(e){t.error=/^HOLD_[A-Z_]+$/.test(e.message)?e.message:'HOLD_QA_STREAM_OBSERVER';}
   finally{try{await reader.cancel();}catch{}}
 }
 window.fetch=async function(input,init){
   let url;try{url=new URL(input instanceof Request?input.url:String(input),location.href);}catch{}
   const own=url&&url.origin===location.origin&&url.pathname==='/api/nox/chat/stream';
   let t=null;
   if(own){
     q.totalNativeCalls++;
     t={nativeCalls:1,started:performance.now(),nativeFirst:null,nativeDone:null,
       nativeDeltas:0,nativeBytes:0,answer:'',done:null,error:null,
       uiFirst:null,uiBeforeDone:false,uiLengths:[],uiPrefixLengthsBeforeDone:[],uiBody:null,
       uiVisible:false,uiMaxTokenSpans:0,stopSamples:0,stopVisibleSamples:0,stopOccludedSamples:0,
       nativeEof:false,originalCardUiStates:[],lifecycleTimer:null};
     q.turns.push(t);q.current=t;
     const pending=document.querySelectorAll('#messages .v24-msg.nox.streaming .body');
     t.uiBody=pending.length===1?pending[0]:null;
     requestAnimationFrame(sampleStop);
     lifecycleSample();
     if(cfg.originalCard){
       t.lifecycleTimer=setInterval(lifecycleSample,20);
       setTimeout(()=>{if(t.lifecycleTimer!==null){clearInterval(t.lifecycleTimer);t.lifecycleTimer=null;}},120000);
     }
   }
   const response=await fetch0(input,init);
   if(own){void observe(response.clone(),t);}
   return response;
 };
})();
"""

SNAPSHOT_JS = r"""() => {
 const q=window.__NOX_BROWSER_QA;if(!q)return null;
 const t=q.current;
 const normalize=s=>s.replace(/\s+/g,'');
 const mount=document.getElementById('messages'),body=t?.uiBody;
 const rendered=!!(mount&&body&&mount.contains(body)&&t?.answer&&
   typeof body.innerText==='string'&&normalize(body.innerText)===normalize(t.answer));
 const contexts=q.contexts.map(({canvas,kind,ctx})=>{
   let renderer='unknown';
   try{const ext=ctx.getExtension('WEBGL_debug_renderer_info');
     const value=ext?ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL):ctx.getParameter(ctx.RENDERER);
     renderer=/swiftshader/i.test(String(value))?'swiftshader':'other';
   }catch{}
   const box=canvas.getBoundingClientRect();
   return {kind,width:canvas.width,height:canvas.height,visible:box.width>40&&box.height>40,renderer};
 }).slice(0,8);
 return {native_first_ms:t?.nativeFirst??null,native_done_ms:t?.nativeDone??null,native_delta_count:t?.nativeDeltas??0,
   native_bytes:t?.nativeBytes??0,native_calls:t?.nativeCalls??0,total_native_calls:q.totalNativeCalls,
   native_eof:t?.nativeEof??false,original_card_ui_states:t?.originalCardUiStates??[],
   done:t?.done??null,error:t?.error??null,
   ui_first_ms:t?.uiFirst??null,ui_before_native_done:t?.uiBeforeDone??false,ui_lengths:t?.uiLengths??[],
   ui_prefix_lengths_before_done:t?.uiPrefixLengthsBeforeDone??[],ui_body_visible:t?.uiVisible??false,
   ui_token_span_peak:t?.uiMaxTokenSpans??0,
   ui_measurement_kind:'CUMULATIVE_VISIBLE_ASSISTANT_BODY',
   intl_segmenter_available:typeof Intl!=='undefined'&&typeof Intl.Segmenter==='function',
   stop_samples:t?.stopSamples??0,stop_visible_samples:t?.stopVisibleSamples??0,stop_occluded_samples:t?.stopOccludedSamples??0,
   answer_characters:t?.answer?.length??0,dom_answer_matches_native:rendered,contexts,draw_calls:q.draws,
   native_owner:window.NOX_NATIVE_OWNER===true,v135:window.__NOX_V135_OWNER_RESONANCE==='OWNER_NATIVE_ONLY',
   v137:window.__NOX_V137_SELF_STATUS==='READ_ONLY',owner_live:window.__NOX_OWNER_LIVE_UI===true,
   build:document.querySelector('meta[name="nox-live-build"]')?.content||null,
   prompt_visible:!!document.querySelector('#prompt')&&document.querySelector('#prompt').getBoundingClientRect().width>100,
   executor_chips:document.querySelectorAll('.nox-live-chip').length,
   photo_button:!![...document.querySelectorAll('.nox-live-btn')].find(x=>x.textContent==='Фото'),
   video_button:!![...document.querySelectorAll('.nox-live-btn')].find(x=>x.textContent==='Видео')};
}"""

CONTROL_JS = r"""el => {
 const button=el.closest('button')||el,rail=document.getElementById('v24Rail');
 const box=button.getBoundingClientRect(),style=getComputedStyle(button);
 const rs=rail?getComputedStyle(rail):null,rb=rail?.getBoundingClientRect();
 const x=box.x+box.width/2,y=box.y+box.height/2;
 const inView=x>0&&x<innerWidth&&y>0&&y<innerHeight;
 const hit=inView?document.elementFromPoint(x,y):null;
 const known=new Set(['v24Rail','nativeChats','v24Cursor','noxCoreEntry','n25Menu','v24System','messages','chatForm']);
 const publicClasses=['nox-v28-pc-return','v24-stage','v24-app','v24-rail','v24-main','v24-top','v24-chat-item','v24-chats','n25-menu'];
 const banner=document.querySelector('body.nox-v24 > .nox-v28-pc-return'),bb=banner?.getBoundingClientRect();
 const stage=document.querySelector('body.nox-v24 .v24-stage'),sb=stage?.getBoundingClientRect();
 const layers=inView?document.elementsFromPoint(x,y).slice(0,6).map(node=>({
   tag:node.tagName,known_id:known.has(node.id)?node.id:'OTHER',
   known_classes:publicClasses.filter(name=>node.classList.contains(name)),
   z_index:/^-?\d+$/.test(getComputedStyle(node).zIndex)?Number(getComputedStyle(node).zIndex):null})):[];
 return {x,y,width:box.width,height:box.height,in_view:inView,
   pointer_hit_own_button:!!hit&&(hit===button||button.contains(hit)),
   hit_tag:hit?.tagName||null,hit_known_id:hit?(known.has(hit.id)?hit.id:'OTHER'):null,
   hit_in_other_dialog:!!hit&&!!hit.closest('#nativeChats')&&!button.contains(hit),
   hit_in_header:!!hit&&!!hit.closest('header'),
   hit_in_return_banner:!!hit&&!!hit.closest('.nox-v28-pc-return'),hit_layers:layers,
   return_banner_present:!!banner,return_banner_bottom:bb?.bottom||0,return_banner_height:bb?.height||0,
   stage_top:sb?.top||0,layout_fix:window.__NOX_OWNER_LAYOUT_FIX==='RETURN_BANNER_INSET_V1',
   target_pointer_events:style.pointerEvents,rail_present:!!rail,
   rail_collapsed:rail?.dataset.collapsed==='true',rail_width:rb?.width||0,
   rail_opacity:rs?Number(rs.opacity):null,rail_pointer_events:rs?.pointerEvents||null};
}"""


def click_error_projection(exc):
    message=str(exc).casefold()
    return {name:needle in message for name,needle in (
        ('not_stable','not stable'),('not_visible','not visible'),
        ('outside_viewport','outside of the viewport'),
        ('pointer_intercepted','intercepts pointer events'),('detached','detached'))}


def status_projection(value):
    """Legacy-control compatibility only; never export arbitrary model/status text."""
    if not isinstance(value, dict):
        return {'object': False}
    return {'object': True, 'legacy_model_field': 'model' in value,
            'legacy_model_truthy': bool(value.get('model')),
            'primary_model_present': isinstance(value.get('primary_model'), str) and bool(value['primary_model']),
            'native_p02_bound': value.get('native_p02_bound') is True,
            'native_backend': value.get('backend') == 'EXISTING_NATIVE_ONEHOST',
            'native_dialogs_ready': value.get('native_dialogs_ready') is True,
            'status_ready': value.get('status') == 'READY', 'owner_stop': value.get('stop_flag') is True}


COMPOSER_JS = r"""() => {
 const prompt=document.getElementById('prompt'),send=document.querySelector('#chatForm [type=submit]'),stop=document.querySelector('#chatForm [data-action=stop]');
 const project=node=>{
  if(!node)return {present:false};
  const box=node.getBoundingClientRect(),style=getComputedStyle(node);
  const x=box.x+box.width/2,y=box.y+box.height/2,inView=x>0&&x<innerWidth&&y>0&&y<innerHeight;
  const hit=inView?document.elementFromPoint(x,y):null;
  return {present:true,x,y,width:box.width,height:box.height,in_view:inView,
   fully_in_view:box.top>=0&&box.bottom<=innerHeight&&box.left>=0&&box.right<=innerWidth,
   disabled:node.disabled===true,read_only:node.readOnly===true,
   pointer_events:style.pointerEvents,visible:style.display!=='none'&&style.visibility!=='hidden'&&box.width>0&&box.height>0,
   pointer_hit_own_control:!!hit&&(hit===node||node.contains(hit))};
 };
 const reports=[...document.querySelectorAll('.nox-owner-reports')].slice(0,2).map(node=>{
  const box=node.getBoundingClientRect();return {open:node.open===true,height:box.height,top:box.top};});
 const stack=document.querySelector('.nox-owner-status-stack'),stackBox=stack?.getBoundingClientRect();
 const statusStack=stack?{height:stackBox.height,top:stackBox.top,bottom:stackBox.bottom,
  client_height:stack.clientHeight,scroll_height:stack.scrollHeight,overflow_y:getComputedStyle(stack).overflowY}:null;
 const knownPhases=['idle','thinking','speaking','stopped','error','done'];
 return {prompt:project(prompt),send:project(send),stop:project(stop),prompt_characters:prompt?.value?.length||0,
  phase:knownPhases.includes(document.body.dataset.noxPhase)?document.body.dataset.noxPhase:'OTHER',
  reports,status_stack:statusStack,viewport_height:innerHeight,viewport_width:innerWidth,
  reports_layout:window.__NOX_OWNER_COMPOSER_LAYOUT==='BOUNDED_REPORTS_SCROLL_V1'};
}"""


def composer_layout_valid(value, opened):
    if not isinstance(value,dict) or value.get('reports_layout') is not True:
        return False
    reports=value.get('reports');stack=value.get('status_stack')
    if (not isinstance(reports,list) or len(reports)!=2 or any(row.get('open') is not opened for row in reports)
            or not isinstance(stack,dict) or stack.get('overflow_y')!='auto'):
        return False
    height=value.get('viewport_height',0)
    if not 0<stack.get('height',0)<=min(280,height*.28)+2:
        return False
    return all(isinstance(value.get(name),dict) and all(value[name].get(key) is True
               for key in ('present','visible','fully_in_view','pointer_hit_own_control')) for name in ('prompt','send'))


async def check_report_layout(page,report):
    """Exercise real layout at two viewport sizes; generate with both panels open."""
    cases=[];report['report_layout_cases']=cases
    for width,height,opened in ((1440,1000,False),(1440,1000,True),(1280,720,True),(1440,1000,True)):
        await page.set_viewport_size({'width':width,'height':height})
        await page.evaluate("""async opened=>{
          for(const node of document.querySelectorAll('.nox-owner-reports'))node.open=opened;
          const stack=document.querySelector('.nox-owner-status-stack');if(stack)stack.scrollTop=0;
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        }""",opened)
        value=await page.evaluate(COMPOSER_JS)
        cases.append({'opened':opened,'viewport_width':width,'viewport_height':height,'geometry':value})
        if not composer_layout_valid(value,opened):
            raise RuntimeError('HOLD_QA_REPORTS_COMPOSER_LAYOUT')
    report['report_scroll_verified']=await page.evaluate("""()=>{
      const node=document.querySelector('.nox-owner-status-stack');if(!node)return false;
      const old=node.scrollTop;node.scrollTop=node.scrollHeight;
      const moved=node.scrollTop>0;node.scrollTop=old;
      return node.scrollHeight<=node.clientHeight+1||moved;
    }""")
    if report['report_scroll_verified'] is not True:
        raise RuntimeError('HOLD_QA_REPORTS_SCROLL')


async def click_send(page, report):
    """Physical send, with the same fresh hit gate as the dialog selection."""
    target=page.locator('#chatForm [type=submit]')
    detail={'before':await target.evaluate(CONTROL_JS)}
    report['qa_send_control']=detail
    try:
        await target.click(timeout=3500)
    except Exception as exc:
        detail['click_wait']=click_error_projection(exc)
        snapshot=await page.evaluate(SNAPSHOT_JS)
        calls=snapshot.get('native_calls') if isinstance(snapshot,dict) else None
        if calls==1:
            # A timed-out post-click wait may follow an already delivered click.
            # Observe that real request; never submit a duplicate generation.
            detail['native_request_already_started']=True
            return
        control=await target.evaluate(CONTROL_JS)
        detail['after_wait']=control
        if calls!=0 or not await target.is_enabled() or not control['in_view'] or not control['pointer_hit_own_button']:
            raise RuntimeError('HOLD_QA_SEND_POINTER_OR_STATE') from None
        await page.mouse.click(control['x'],control['y'])
        detail['physical_pointer_click']=True


async def json_response(response, limit=200000):
    if response.status!=200:
        raise RuntimeError('HOLD_OWNER_HTTP_'+str(response.status))
    raw=await response.body()
    if len(raw)>limit:
        raise RuntimeError('HOLD_OWNER_HTTP_SIZE')
    return json.loads(raw)


async def capture_private_screenshot(page, report, directory, name, masks, content,
                                     timeout_errors=(TimeoutError,)):
    """Defer only capture timeouts; all privacy and file guards stay mandatory."""
    if name not in ('empty', 'completed'):
        raise RuntimeError('HOLD_SCREENSHOT_SCOPE')
    if stop_present():
        raise RuntimeError('HOLD_OWNER_STOP')
    started = time.monotonic()
    capture = {'stage':name, 'state':'CAPTURING', 'timeout_ms':3500}
    report.setdefault('screenshot_captures', []).append(capture)
    try:
        raw = await asyncio.wait_for(page.screenshot(
            full_page=False, mask=masks, mask_color='#121821', timeout=3500),
            timeout=4)
    except timeout_errors as exc:
        capture.update(state='CAPTURE_TIMEOUT',
                       font_wait_reported='waiting for fonts to load' in str(exc).lower(),
                       elapsed_ms=round((time.monotonic()-started)*1000))
        if stop_present():
            raise RuntimeError('HOLD_OWNER_STOP')
        return False
    if stop_present():
        raise RuntimeError('HOLD_OWNER_STOP')
    if len(raw)>6*1024**2:
        raise RuntimeError('HOLD_SCREENSHOT_SIZE')
    path = directory/(name+'.png')
    write_private(path, raw)
    report['artifacts'].append({'private_path':str(path), 'sha256':digest(raw),
                               'bytes':len(raw), 'content':content})
    capture.update(state='CAPTURED', elapsed_ms=round((time.monotonic()-started)*1000))
    return True


def require_screenshot_captures(report):
    captures = report.get('screenshot_captures', [])
    complete = (len(captures)==2
                and {row.get('stage') for row in captures}=={'empty','completed'}
                and all(row.get('state')=='CAPTURED' for row in captures))
    report['screenshot_capture_verified'] = complete
    if not complete:
        raise RuntimeError('HOLD_SCREENSHOT_CAPTURE_PENDING')


async def browser_run(report, directory, available):
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    base=local_base()
    origin=urllib.parse.urlsplit(base).netloc
    token=secrets.token_hex(6).translate(str.maketrans('0123456789','ghijklmnop'))
    title='NOX Browser QA '+token
    original_card=os.environ.get('NOX_BROWSER_QA_MODE')=='original_card'
    if original_card:
        prompts=('[NOX 1A01 UI QA '+token+'] Ответь коротко словом ГОТОВО.',)
        report.update(original_card_one_turn=True,onehost_1a01_original_card_acceptance_state='HOLD_NATIVE_OWNER_RUN_REQUIRED',
                      canonical_s03_readback_verified=False,
                      canonical_s03_acceptance_state='HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND')
    else:
        prompts=(
            '[NOX UI QA '+token+'] Напиши числа от одного до десяти через запятую. Без пояснений и без других слов.',
            '[NOX UI QA '+token+'] Повтори дословно последовательность цифр из предыдущего ответа, без других слов.',
        )
    report.update(nonloopback_auth=True,resources=budget(),
                  synthetic_prompt_sha256=digest(prompts[0].encode()),
                  synthetic_prompt_sha256s=[digest(item.encode()) for item in prompts])
    network=[];console=collections.Counter();page_errors=[];blocked=collections.Counter();did=None
    sys.path.insert(0,str(ROOT/'scripts'))
    import chat_proxy
    password=chat_proxy._read_chat_password()
    if not isinstance(password,str) or not 6<=len(password)<=4096:
        raise RuntimeError('HOLD_EXISTING_OWNER_CREDENTIAL')
    async with async_playwright() as runtime:
        arguments=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle',
                   '--use-angle=swiftshader','--enable-unsafe-swiftshader',
                   '--disable-background-networking','--disable-extensions']
        child_env={key:os.environ[key] for key in ('PATH','LANG','LC_ALL','LD_LIBRARY_PATH') if key in os.environ}
        child_env['CUDA_VISIBLE_DEVICES']=''
        launch={'headless':True,'args':arguments,'env':child_env,'timeout':20000}
        if available['system_browser_candidates']:
            launch['executable_path']=available['system_browser_candidates'][0]
        browser=await runtime.chromium.launch(**launch)
        report['browser_version']=browser.version if re.fullmatch(r'[A-Za-z0-9 ._-]{1,80}',browser.version) else None
        context=await browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1,
                                         base_url=base,service_workers='block',accept_downloads=False)
        context.set_default_timeout(12000)
        page=None
        try:
            anonymous=await context.request.get(base+'/api/ui/executors',max_redirects=0,timeout=6000)
            if anonymous.status!=401:
                raise RuntimeError('HOLD_ANONYMOUS_OWNER_SCOPE')
            login=await context.request.post(base+'/chat/login',data={'password':password},
                                             max_redirects=0,timeout=8000)
            password=None
            if login.status!=200:
                raise RuntimeError('HOLD_EXISTING_OWNER_LOGIN')
            session=await context.request.get(base+'/chat/session',max_redirects=0,timeout=6000)
            if session.status!=200:
                raise RuntimeError('HOLD_SIGNED_OWNER_SESSION')
            report['actual_native_backend']=True
            created=await json_response(await context.request.post(base+'/api/ui/memory/dialogs/create',
                data={'title':title,'confirmed':True},max_redirects=0,timeout=8000))
            did=created.get('dialog_id')
            if not isinstance(did,str) or not re.fullmatch(r'[a-f0-9]{32}',did):
                raise RuntimeError('HOLD_SYNTHETIC_DIALOG_SCOPE')
            report['synthetic_dialog_created']=True
            config=json.dumps({'did':did,'expectedPrompt':prompts[0],
                               'originalCard':original_card},separators=(',',':'))
            await context.add_init_script(OBSERVER_JS.replace('__CONFIG__',config))

            accepted_submits=[]
            async def guard(route):
                request=route.request
                url=urllib.parse.urlsplit(request.url)
                if url.scheme not in ('http','https') or url.netloc!=origin:
                    blocked['external_origin']+=1
                    return await route.abort()
                if url.path=='/api/nox/history':
                    blocked['legacy_unscoped_history']+=1
                    return await route.abort()
                if url.path=='/api/ui/memory/dialogs/history':
                    identifier=urllib.parse.parse_qs(url.query).get('dialog_id',[])
                    if identifier!=[did]:
                        blocked['non_qa_dialog_history']+=1
                        return await route.abort()
                if url.path=='/api/ui/memory/dialogs/exchange-readback':
                    try:
                        body=request.post_data_json
                        own=isinstance(body,dict) and body.get('dialog_id')==did
                    except Exception:
                        own=False
                    if not own:
                        blocked['non_qa_receipt_readback']+=1
                        return await route.abort()
                if url.path=='/api/nox/chat/stream':
                    try:
                        body=request.post_data_json
                        expected=prompts[len(accepted_submits)] if len(accepted_submits)<len(prompts) else None
                        own=(isinstance(body,dict) and expected is not None
                             and body.get('message')==expected and body.get('dialog_id')==did)
                    except Exception:
                        own=False
                    if not own:
                        blocked['non_qa_generation']+=1
                        return await route.abort()
                    accepted_submits.append(body.get('message'))
                return await route.continue_()

            await context.route('**/*',guard)
            page=await context.new_page()

            def on_response(response):
                if len(network)>=250:
                    return
                network.append({'path':safe_route(response.url),'status':response.status,
                                'resource_type':response.request.resource_type})

            def on_console(message):
                if message.type in ('error','warning'):
                    console[message.type]+=1

            def on_page_error(error):
                if len(page_errors)<20:
                    message=str(error)
                    found=re.match(r'(TypeError|ReferenceError|SyntaxError|RangeError|Error)\b',message)
                    page_errors.append({'category':found[1] if found else 'JAVASCRIPT_EXCEPTION'})

            page.on('response',on_response)
            page.on('console',on_console)
            page.on('pageerror',on_page_error)
            page.on('dialog',lambda dialog:asyncio.create_task(dialog.dismiss()))
            response=await page.goto(base+'/',wait_until='domcontentloaded',timeout=20000)
            if response is None or response.status!=200 or urllib.parse.urlsplit(page.url).path!=PAGE:
                raise RuntimeError('HOLD_GRAPHICAL_OWNER_ROUTE')
            await page.wait_for_function("window.__NOX_OWNER_LIVE_UI===true && !!document.querySelector('#prompt')",timeout=15000)
            await page.wait_for_timeout(1200)
            before=await page.evaluate(SNAPSHOT_JS)
            report['graphics_before']=before
            if (not before or before['build']!=BUILD or not all(before.get(k) for k in ('native_owner','v135','v137','owner_live','prompt_visible'))):
                raise RuntimeError('HOLD_GRAPHICAL_MODULES_NOT_ACTIVE')
            report['browser_stage']='QA_DIALOG_LIST'
            target=page.locator('#nativeChats button[role="listitem"]').filter(has=page.get_by_text(title,exact=True))
            report['qa_dialog_controls']={'list_count':await page.locator('#nativeChats').count(),
                'title_count':await target.count(),'rail_toggle_count':await page.locator('[data-action="toggle-rail"]').count()}
            await target.first.wait_for(state='attached',timeout=10000)
            if not await target.count():
                raise RuntimeError('HOLD_SYNTHETIC_DIALOG_NOT_LISTED')
            control=await target.first.evaluate(CONTROL_JS)
            report['qa_dialog_controls']['before']=control
            # A collapsed rail can retain descendants' layout boxes despite
            # opacity:0 and pointer-events:none. Inspect the actual rail state.
            if (control['rail_collapsed'] or control['rail_width']<2
                    or control['rail_opacity']==0 or control['rail_pointer_events']=='none'):
                report['browser_stage']='QA_RAIL_OPEN'
                await page.locator('[data-action="toggle-rail"]').first.click()
                await page.wait_for_function("document.getElementById('v24Rail')?.dataset.collapsed!=='true' && Number(getComputedStyle(document.getElementById('v24Rail')).opacity)>.95",timeout=5000)
            report['browser_stage']='QA_DIALOG_CLICK'
            await target.first.evaluate("el=>el.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'})")
            try:
                await target.first.click(timeout=3500)
            except Exception as exc:
                report['qa_dialog_controls']['click_wait']=click_error_projection(exc)
                control=await target.first.evaluate(CONTROL_JS)
                report['qa_dialog_controls']['after_wait']=control
                if not control['in_view'] or not control['pointer_hit_own_button']:
                    raise RuntimeError('HOLD_QA_DIALOG_POINTER_OCCLUDED') from None
                # Decorative motion can prevent Playwright's stable-box check.
                # A real pointer click is allowed only after a fresh hit test
                # proves that the intended synthetic dialog owns that point.
                await page.mouse.click(control['x'],control['y'])
                report['qa_dialog_controls']['physical_pointer_click']=True
            await page.wait_for_function("title=>[...document.querySelectorAll('#nativeChats button[role=listitem]')].some(b=>b.getAttribute('aria-current')==='true'&&b.querySelector('.t')?.textContent===title)",arg=title,timeout=7000)
            report['browser_stage']='QA_DIALOG_HISTORY'
            await page.wait_for_timeout(350)
            initial=await json_response(await context.request.get(
                base+'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6',max_redirects=0,timeout=6000))
            if (initial.get('status')!='READY' or initial.get('dialog_id')!=did
                    or initial.get('store_scope')!='OWNER_DIALOG_TABLES_ONLY'
                    or initial.get('canonical_s03_readback_verified') is not False
                    or initial.get('messages')!=[]):
                raise RuntimeError('HOLD_SYNTHETIC_DIALOG_NOT_EMPTY')
            report['empty_owner_dialog_history_verified']=True
            report['canonical_s03_readback_verified']=False
            if not original_card:
                report['browser_stage']='QA_EMPTY_SCREENSHOT'
                masks=[page.locator(selector) for selector in (*SENSITIVE_MASKS,'#messages')]
                await capture_private_screenshot(page,report,directory,'empty',masks,
                    'EMPTY_QA_VIEW_WITH_PRIVACY_MASKS',(TimeoutError,PlaywrightTimeoutError))
                report['graphics_before']=before
                await page.wait_for_timeout(500)
                graphical=await page.evaluate(SNAPSHOT_JS)
                report['canvas_animation_observed']=graphical['draw_calls']>before['draw_calls']
                report['webgl_visible']=any(item['visible'] and item['kind'] in ('webgl','webgl2','experimental-webgl') for item in graphical['contexts'])
            if stop_present():
                raise RuntimeError('HOLD_OWNER_STOP')
            idle_slots()
            if not original_card:
                report['browser_stage']='QA_REPORTS_COMPOSER_LAYOUT'
                await check_report_layout(page,report)
            report['composer_before']=await page.evaluate(COMPOSER_JS)
            if not original_card:
                report['status_for_legacy_controls']=status_projection(await json_response(await context.request.get(
                    base+'/api/nox/status',max_redirects=0,timeout=6000)))
            verified_turns=[];history_expected=[];progressive=[];final=None
            for turn_index,prompt in enumerate(prompts):
                if stop_present():
                    raise RuntimeError('HOLD_OWNER_STOP')
                idle_slots()
                report['browser_stage']='QA_TURN_'+str(turn_index+1)+'_PROMPT_FILL'
                await page.locator('#prompt').fill(prompt)
                await page.wait_for_function("!document.querySelector('#chatForm [type=submit]').disabled",timeout=10000)
                report['browser_stage']='QA_TURN_'+str(turn_index+1)+'_SEND'
                started=time.monotonic()
                await click_send(page,report)
                report['browser_stage']='QA_TURN_'+str(turn_index+1)+'_REAL_STREAM'
                final=None
                while time.monotonic()-started<85:
                    if stop_present():
                        raise RuntimeError('HOLD_OWNER_STOP')
                    final=await page.evaluate(SNAPSHOT_JS)
                    if final and final.get('error'):
                        raise RuntimeError(final['error'])
                    if (final and final.get('done') and final.get('dom_answer_matches_native')
                            and (not original_card or (final.get('native_eof') is True
                                 and original_card_ui_trace_valid(final)
                                 and progressive_stream_valid(final)))):
                        break
                    await page.wait_for_timeout(120)
                if (not final or final.get('native_calls')!=1 or not final.get('done')
                        or not final.get('dom_answer_matches_native')):
                    raise RuntimeError('HOLD_REAL_STREAM_NOT_RENDERED')
                if original_card and (final.get('native_eof') is not True
                        or final.get('total_native_calls')!=1
                        or not original_card_ui_trace_valid(final)
                        or not progressive_stream_valid(final)):
                    raise RuntimeError('HOLD_1A01_UI_STATE_ORDER_OR_NATIVE_EOF')
                report['browser_stage']='QA_TURN_'+str(turn_index+1)+'_SEND_RELEASE'
                await page.wait_for_function("!document.querySelector('#chatForm [type=submit]').disabled",timeout=10000)
                done=final.get('done')
                if original_card:
                    if not isinstance(done,dict):
                        raise RuntimeError('HOLD_NATIVE_DONE_FRAME_MISSING')
                    if accepted_submits!=list(prompts):
                        raise RuntimeError('HOLD_ONE_TURN_SUBMIT_BINDING')
                    answer=await page.evaluate('()=>window.__NOX_BROWSER_QA.current?.answer||null')
                    if not isinstance(answer,str) or not answer.strip():
                        raise RuntimeError('HOLD_REAL_STREAM_NOT_RENDERED')
                    report.update(
                        original_card_ui_states=original_card_ui_trace_projection(final.get('original_card_ui_states')),
                        actual_native_model_stream_verified=True,
                        progressive_stream_render_verified=True,
                        stream={'native_calls':final.get('native_calls'),
                                'native_delta_count':final.get('native_delta_count'),
                                'native_first_ms':final.get('native_first_ms'),
                                'native_done_ms':final.get('native_done_ms'),
                                'native_eof':final.get('native_eof'),
                                'dom_answer_matches_native':final.get('dom_answer_matches_native'),
                                'answer_sha256':digest(answer.encode()),
                                'answer_characters':len(answer)},
                        canonical_s03_readback_verified=False,
                        canonical_s03_acceptance_state='HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND',
                        supplemental_dialog_receipt_used_for_acceptance=False,
                        two_turn_condition='NOT_RUN_SEPARATE_FROM_FROZEN_1A01_CARD')
                    break
                if not isinstance(done,dict):
                    raise RuntimeError('HOLD_OWNER_DIALOG_WRITER_RECEIPT_MISSING')
                if not (done.get('saved') is True and done.get('owner_dialog_saved') is True
                        and done.get('canonical_s03_write_verified') is False
                        and done.get('dialog_matches') is True):
                    raise RuntimeError('HOLD_OWNER_DIALOG_WRITER_RECEIPT_MISSING')
                answer=await page.evaluate('()=>window.__NOX_BROWSER_QA.current?.answer||null')
                if not isinstance(answer,str) or not answer.strip():
                    raise RuntimeError('HOLD_REAL_STREAM_NOT_RENDERED')
                receipt_request={key:done.get(key) for key in ('turn_id','receipt_id','lease_epoch')}
                receipt_request['dialog_id']=did
                report['browser_stage']='QA_TURN_'+str(turn_index+1)+'_OWNER_DIALOG_READBACK'
                readback_response=await context.request.post(
                    base+'/api/ui/memory/dialogs/exchange-readback',data=receipt_request,
                    max_redirects=0,timeout=6000)
                if readback_response.status!=200:
                    raise RuntimeError('HOLD_OWNER_DIALOG_RECEIPT_AND_INDEPENDENT_READBACK')
                proof=await json_response(readback_response)
                if not exact_owner_dialog_readback(proof,done,did,prompt,answer):
                    raise RuntimeError('HOLD_OWNER_DIALOG_RECEIPT_AND_INDEPENDENT_READBACK')
                history_expected.extend(({'role':'user','content':prompt},
                                         {'role':'assistant','content':answer}))
                history=await json_response(await context.request.get(
                    base+'/api/ui/memory/dialogs/history?dialog_id='+did+'&limit=6',
                    max_redirects=0,timeout=6000))
                rows=history.get('messages')
                if (history.get('status')!='READY' or history.get('dialog_id')!=did
                        or history.get('store_scope')!='OWNER_DIALOG_TABLES_ONLY'
                        or history.get('canonical_s03_readback_verified') is not False
                        or not isinstance(rows,list) or len(rows)!=len(history_expected)
                        or any(not isinstance(row,dict) or row.get('role')!=expected['role']
                               or row.get('content')!=expected['content']
                               for row,expected in zip(rows,history_expected))):
                    raise RuntimeError('HOLD_ORDERED_OWNER_DIALOG_HISTORY_READBACK')
                public=public_numeric_answer(answer)
                if public!=EXPECTED:
                    raise RuntimeError('HOLD_SYNTHETIC_MODEL_QUALITY')
                if turn_index==1:
                    previous_answer=history_expected[-3]['content']
                    if re.sub(r'\s+','',answer)!=re.sub(r'\s+','',previous_answer):
                        raise RuntimeError('HOLD_SECOND_TURN_CONTEXT_REPLAY')
                turn_progressive=progressive_stream_valid(final)
                progressive.append(turn_progressive)
                stop_visible=bool(final.get('stop_samples',0)>0
                    and final.get('stop_samples')==final.get('stop_visible_samples')
                    and final.get('stop_occluded_samples')==0)
                if not stop_visible:
                    raise RuntimeError('HOLD_QA_ACTIVE_STOP_LAYOUT')
                verified_turns.append({
                    'turn_id':done['turn_id'],'receipt_id':done['receipt_id'],
                    'lease_epoch':done['lease_epoch'],'exchange_id':done['exchange_id'],
                    'receipt_sha256':done['receipt_sha256'],
                    'prompt_sha256':digest(prompt.encode()),'answer_sha256':digest(answer.encode()),
                    'answer_characters':len(answer),'owner_dialog_readback_verified':True,
                    'owner_dialog_history_readback_verified':True,
                    'canonical_s03_readback_verified':False,
                    'stream_verified':True,'progressive_stream_render_verified':turn_progressive,
                    'stop_visible_during_generation':stop_visible,
                    'elapsed_turn_ms':round((time.monotonic()-started)*1000)})
            if not original_card and (len(verified_turns)!=2
                    or len({item['turn_id'] for item in verified_turns})!=2
                    or len({item['receipt_id'] for item in verified_turns})!=2
                    or len({item['exchange_id'] for item in verified_turns})!=2
                    or accepted_submits!=list(prompts)):
                raise RuntimeError('HOLD_TWO_DISTINCT_SEQUENTIAL_TURNS')
            if not original_card:
                answer=history_expected[-1]['content']
                public=public_numeric_answer(answer)
                saved=len(history_expected)==4
                dialog_readback=all(item['owner_dialog_readback_verified'] for item in verified_turns)
                report.update(stream=final,turns=verified_turns,
                sequential_two_turns_verified=True,owner_dialog_readback_verified=dialog_readback,
                owner_dialog_history_readback_verified=all(
                    item['owner_dialog_history_readback_verified'] for item in verified_turns),
                canonical_s03_readback_verified=False,
                onehost_1a01_acceptance_state='HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND',
                actual_native_model_stream_verified=bool(len(verified_turns)==2 and accepted_submits==list(prompts)),
                answer_sha256=digest(answer.encode()),answer_characters=len(answer),
                synthetic_number_sequence_pass=public==EXPECTED,
                synthetic_public_numeric_answer=public,
                progressive_stream_render_verified=all(progressive),
                stop_visible_during_generation=all(item['stop_visible_during_generation'] for item in verified_turns))
                masks=[page.locator(selector) for selector in SENSITIVE_MASKS]
                if not saved or public!=EXPECTED:
                    masks.append(page.locator('#messages'))
                report['browser_stage']='QA_COMPLETED_SCREENSHOT'
                await capture_private_screenshot(page,report,directory,'completed',masks,
                    'VERIFIED_PUBLIC_NUMERIC_DIALOG_QA' if public==EXPECTED and saved and dialog_readback else 'MASKED_QA_MESSAGES',
                    (TimeoutError,PlaywrightTimeoutError))
                core=(report['webgl_visible'] and report['canvas_animation_observed']
                  and all(final['done'].get(key) is True for key in ('saved','owner_dialog_saved','dialog_matches'))
                  and saved and dialog_readback and report['sequential_two_turns_verified']
                  and final['executor_chips']==6 and final['photo_button'] and final['video_button'])
                if not core:
                    raise RuntimeError('HOLD_GRAPHICAL_ACCEPTANCE_INCOMPLETE')
                if not report['progressive_stream_render_verified']:
                    raise RuntimeError('HOLD_PROGRESSIVE_STREAM_NOT_OBSERVED')
                if public!=EXPECTED:
                    raise RuntimeError('HOLD_SYNTHETIC_MODEL_QUALITY')
        finally:
            report['network']=network
            report['console_counts']=dict(console)
            report['page_exceptions']=page_errors
            report['privacy_guard_counts']=dict(blocked)
            report['failed_static_resources']=[row for row in network if row['status']>=400 and row['resource_type'] in ('script','stylesheet')]
            if page is not None:
                try:
                    report['composer_final']=await page.evaluate(COMPOSER_JS)
                    final_snapshot=await page.evaluate(SNAPSHOT_JS)
                    if original_card:
                        report['stream_final']=original_card_stream_projection(final_snapshot)
                    else:
                        report['stream_final']=final_snapshot
                    pending=await page.evaluate('!!window.__NOX_BROWSER_QA?.current?.nativeCalls&&!window.__NOX_BROWSER_QA?.current?.done')
                    if pending:
                        await context.request.post(base+'/api/nox/stop',data={},max_redirects=0,timeout=4000)
                except Exception:
                    pass
            try:
                await context.request.post(base+'/chat/logout',data={},max_redirects=0,timeout=4000)
            except Exception:
                pass
            password=None
            await context.close()
            await browser.close()
    if page_errors or report['failed_static_resources']:
        raise RuntimeError('HOLD_BROWSER_JAVASCRIPT_OR_RESOURCE_ERRORS')
    if original_card:
        report['onehost_1a01_original_card_acceptance_state']='ORIGINAL_CARD_UI_TRACE_VERIFIED'
        report['accepted_input_waiting_answer_completed_ui_verified']=True
        return
    report['dialog_ui_functional_checks_verified']=True
    require_screenshot_captures(report)


def main():
    os.environ.pop('DEBUG',None)
    os.environ.pop('PWDEBUG',None)
    available=inventory()
    emit('browser_qa_dependencies',available)
    if os.environ.get('NOX_BROWSER_QA_MODE')=='inventory':
        return 0
    request=os.environ.get('NOX_OWNER_REQUEST_ID','')
    source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not re.fullmatch(r'[0-9]{1,24}',request) or not re.fullmatch(r'[a-f0-9]{40}',source):
        raise RuntimeError('HOLD_OWNER_CONTEXT')
    if not available['playwright_installed']:
        raise RuntimeError('HOLD_ISOLATED_PLAYWRIGHT_REQUIRED')
    if STATE.is_symlink():
        raise RuntimeError('HOLD_BROWSER_STATE_SYMLINK')
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(STATE,0o700)
    lock=os.open(STATE/'qa.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    directory=STATE/request
    directory.mkdir(mode=0o700)
    os.nice(10)
    affinity=sorted(os.sched_getaffinity(0))
    if len(affinity)>2:
        os.sched_setaffinity(0,set(affinity[:2]))
    report={'schema':'NOX_OWNER_NATIVE_BROWSER_QA_V1','request':request,'source_sha':source,
            'started_at':time.time(),'state':'RUNNING','artifacts':[],
            'actual_native_backend':False,'actual_native_model_stream_verified':False,'synthetic_backend_used':False,
            'dialog_ui_functional_checks_verified':False,
            'canonical_s03_readback_verified':False,
            'onehost_1a01_acceptance_state':'HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND',
            'screenshot_capture_verified':False,
            'screenshots_exported':False,'private_text_or_credentials_exported':False,
            'rendering_mode':'CPU_SWIFTSHADER_FUNCTIONAL_QA_NOT_CLIENT_GPU_BENCHMARK',
            'training_or_service_configuration_changed':False,'diagnostics_content':'COUNTS_PATHS_AND_PUBLIC_SYNTHETIC_NUMBERS_ONLY'}
    original_card=os.environ.get('NOX_BROWSER_QA_MODE')=='original_card'
    if original_card:
        report.update(schema='NOX_1A01_ORIGINAL_CARD_BROWSER_QA_V1',
            onehost_1a01_original_card_acceptance_state='HOLD_NATIVE_OWNER_RUN_REQUIRED',
            accepted_input_waiting_answer_completed_ui_verified=False,
            canonical_s03_readback_verified=False,
            canonical_s03_acceptance_state='HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND',
            supplemental_dialog_receipt_used_for_acceptance=False,
            two_turn_condition='NOT_RUN_SEPARATE_FROM_FROZEN_1A01_CARD')
    try:
        asyncio.run(asyncio.wait_for(browser_run(report,directory,available),timeout=140))
        if original_card:
            report['state']='ORIGINAL_CARD_UI_QA_PASSED_S03_UNEVALUATED'
            report['onehost_1a01_original_card_acceptance_state']='ORIGINAL_CARD_UI_ACCEPTED'
        else:
            report['state']='DIALOG_QA_PASSED_CANONICAL_S03_HOLD'
            report['onehost_1a01_acceptance_state']='HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND'
    except BaseException as exc:
        report['state']='HOLD'
        report['reason']='HOLD_BROWSER_TOTAL_TIMEOUT' if isinstance(exc,TimeoutError) else safe_error(exc)
        if original_card:
            report['onehost_1a01_original_card_acceptance_state']='HOLD_NATIVE_OWNER_RUN_REQUIRED'
            report['accepted_input_waiting_answer_completed_ui_verified']=False
            report['actual_native_model_stream_verified']=False
    finally:
        report['finished_at']=time.time()
        write_private(directory/'receipt.json',json.dumps(report,separators=(',',':'),allow_nan=False).encode())
        emit('browser_qa_receipt',report)
        os.close(lock)
    if report['state']=='DIALOG_QA_PASSED_CANONICAL_S03_HOLD':
        print('NOX_OWNER_DIALOG_QA_COMPLETE=true',flush=True)
        print('NOX_1A01_CANONICAL_S03_ACCEPTED=false',flush=True)
        print('NOX_1A01_HOLD=HOLD_CANONICAL_S03_WRITER_AND_READBACK_NOT_BOUND',flush=True)
        return 0
    if report['state']=='ORIGINAL_CARD_UI_QA_PASSED_S03_UNEVALUATED':
        print('NOX_1A01_ORIGINAL_CARD_UI_ACCEPTED=true',flush=True)
        print('NOX_1A01_CANONICAL_S03_ACCEPTED=false',flush=True)
        return 0
    return 2


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('browser_qa_hold',{'reason':safe_error(exc),'screenshots_exported':False})
        raise SystemExit(2)
