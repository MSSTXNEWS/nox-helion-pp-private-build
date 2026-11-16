#!/usr/bin/env python3
"""V5 plus bounded, passive main-thread samples; acceptance gates unchanged."""
import base64
import hashlib
import json
import re
import textwrap
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

BASE = 'owner_workspace_browser_acceptance_v5.py'
BASE_SHA = '2284ff0607e74c430cbfedfda48674a7ae295acccdf4ab4ab910612aa4007a32'
SCHEMA = 'NOX_OWNER_WORKSPACE_BROWSER_ACCEPTANCE_V6'
KIND = 'workspace_browser_acceptance_v6'
PINS = {
    BASE: BASE_SHA,
    'owner_workspace_browser_acceptance_v2.py': 'b94fe3d57f81a582cf3bedc62bc2f6bff88a369cfb6189d65f09ff98dd49ffc4',
    'owner_workspace_browser_acceptance.py': '83cb9a19c2be4112b2f1c4fda40b838550a59524b1d3ac475b92e9f283f3548a',
    'owner_chat_page_diagnose.py': '9587860e23ee3617bd47afb3dd15ba677e4e9f3f6d80774599de59cb1a14dc8a',
    'owner_browser_stream_only_entry.py': '2ec4dde5563dd5307b9c2136b97fe3079709253f7b9617ad1037efd7f260d999',
    'owner_chat_browser_qa.py': 'b76198d8117c3912fb7e1a1ef19c01abc41aa3ac87f4ad919612342edf593587',
}


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_WORKSPACE_BROWSER_V6_' + code)


def change_once(text, old, new):
    require(text.count(old) == 1, 'COMPOSITION_SEAM')
    return text.replace(old, new, 1)


SAMPLER_JS = r'''(() => {
 'use strict';
 const cfg=__CONFIG__;
 if(window.top!==window || location.origin!==cfg.base || location.pathname!==cfg.path || location.search || location.hash)return;
 const MAX_MS=5000, MAX_DELIVERY_MS=32000, MAX_SAMPLES=4, INTERVAL=1000;
 let active=false, stopped=false, started=0, sequence=0, frame=null, timer=null, cutoff=null;
 let rafs=0, lastRaf=null, maxGap=0, longCount=0, longTotal=0, longMax=0, observer=null, longSupported=false;
 const finite=(value,min,max)=>typeof value==='number'&&Number.isFinite(value)&&value>=min&&value<=max?value:null;
 const pick=(value,allowed)=>allowed.includes(value)?value:null;
 const round=value=>Math.round(value*1000)/1000;
 function stop(){
   stopped=true;active=false;
   if(frame!==null)cancelAnimationFrame(frame);
   if(timer!==null)clearTimeout(timer);
   if(cutoff!==null)clearTimeout(cutoff);
   frame=timer=cutoff=null;
   if(observer)observer.disconnect();
 }
 function alive(){return active&&!stopped&&performance.now()-started<=MAX_MS;}
 function raf(now){
   frame=null;if(!active||stopped)return;
   if(!alive())return sample(true);
   const stamp=performance.now();
   if(lastRaf!==null)maxGap=Math.max(maxGap,stamp-lastRaf);
   lastRaf=stamp;rafs=Math.min(10000,rafs+1);frame=requestAnimationFrame(raf);
 }
 function core(){
   const api=window.NoxCoreBg;
   const out={present:!!api,version_matches:!!api&&api.version==='NOX_CORE_BG_V22_FINAL2',
     read_error:false,fps:null,frames:null,tier:null,budget:null,pixel_ratio:null,adaptive:null,worker:null};
   if(!out.version_matches)return out;
   try{
     const state=typeof api.state==='function'?api.state():null;
     const d=typeof api.diagnostics==='function'?api.diagnostics():null;
     out.fps=finite(state?.fps,0,1000);
     out.tier=pick(state?.tier,['FULL','LIGHT','ECO','OFF']);out.budget=pick(state?.budget,['MAX','ECO']);
     out.frames=Number.isSafeInteger(d?.frames)&&d.frames>=0&&d.frames<=1000000000?d.frames:null;
     out.pixel_ratio=finite(d?.pixelRatio,0,8);out.adaptive=finite(d?.adaptive,0,1);
     out.worker=typeof d?.worker==='boolean'?d.worker:null;
   }catch{out.read_error=true;}
   return out;
 }
 function consume(entries){
   if(!active||stopped)return;
   for(let i=0;i<entries.length&&i<256;i++){
     const duration=finite(entries[i].duration,0,MAX_DELIVERY_MS);
     const at=finite(entries[i].startTime,started,started+MAX_MS);
     if(duration===null||at===null)continue;
     longCount=Math.min(4096,longCount+1);longTotal=Math.min(MAX_DELIVERY_MS*4096,longTotal+duration);
     longMax=Math.max(longMax,duration);
   }
 }
 function sample(final=false){
   if(timer!==null)clearTimeout(timer);timer=null;if(!active||stopped)return;
   const now=performance.now(),elapsed=round(now-started);
   if(elapsed>MAX_DELIVERY_MS)return stop();
   if(location.origin!==cfg.base||location.pathname!==cfg.path||location.search||location.hash)return stop();
   if(observer)try{consume(observer.takeRecords());}catch{}
   sequence++;
   const payload={schema:'NOX_UI_THREAD_SAMPLE_V1',nonce:cfg.nonce,sequence,
     elapsed_ms:elapsed,sample_window_elapsed:elapsed>=MAX_MS,
     timer_lateness_ms:round(Math.max(0,elapsed-(sequence-1)*INTERVAL)),
     visibility:document.visibilityState,ready_state:document.readyState,
     raf:{callbacks:rafs,max_gap_ms:round(Math.max(maxGap,now-(lastRaf===null?started:lastRaf))),
       silence_ms:round(now-(lastRaf===null?started:lastRaf))},
     long_tasks:{supported:longSupported,count:longCount,total_ms:round(longTotal),max_ms:round(longMax)},
     motion:{preference_reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,
       preference_no_preference:matchMedia('(prefers-reduced-motion: no-preference)').matches,
       runtime_reduced:document.documentElement.dataset.reducedMotion==='reduce',
       runtime_eco:document.body?.dataset.noxGfx==='ECO',runtime_stop:document.body?.dataset.noxFx==='stop'},
     core:core()};
   try{Promise.resolve(window[cfg.binding](payload)).catch(()=>{});}catch{}
   if(final||elapsed>=MAX_MS||sequence>=MAX_SAMPLES)return stop();
   timer=setTimeout(sample,Math.max(0,started+sequence*INTERVAL-performance.now()));
 }
 function begin(){
   if(active||stopped)return;
   active=true;started=performance.now();
   try{
     if(typeof PerformanceObserver==='function'&&PerformanceObserver.supportedEntryTypes?.includes('longtask')){
       observer=new PerformanceObserver(list=>consume(list.getEntries()));
       observer.observe({type:'longtask'});longSupported=true;
     }
   }catch{longSupported=false;if(observer)observer.disconnect();observer=null;}
   cutoff=setTimeout(()=>sample(true),MAX_MS);
   frame=requestAnimationFrame(raf);sample();
 }
 window.addEventListener('pagehide',stop,{once:true});
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',begin,{once:true});else begin();
})();'''


SAMPLER_SOURCE = r'''
class PassiveUIThreadSampler:
    PAGE='/nox-web-v29/pc/resonance.html'
    def __init__(self,context,page,collector,base,report):
        self.context=context;self.page=page;self.collector=collector;self.base=base
        self.nonce=os.urandom(16).hex();self.binding='__nox_ui_thread_'+self.nonce[:16]
        self.started=time.monotonic();self.closed=False;self.window_ended=False;self.generation=None;self.last_elapsed=-1
        self.report={'schema':'NOX_PASSIVE_UI_THREAD_OBSERVATION_V1','state':'ARMING',
            'samples':[],'samples_limit':4,'scheduled_sample_window_ms':5000,'sampling_interval_ms':1000,
            'late_delivery_cap_ms':32000,'extra_wait_for_samples':False,
            'callback_scope_verified':False,'rejected_callbacks':0,'callbacks_after_close':0,
            'additional_http_requests':0,'application_posts':0,'dom_writes':0,'effects_changed':False,
            'body_timeout_changed':False,'root_cause_proven':False,'user_gpu_performance_evaluated':False,
            'raw_urls_or_errors_exported':False,'nonce_exported':False,
            'render_metrics_scope':'READ_ONLY_PUBLIC_CORE_API_WITH_VERSION_CHECK_NOT_SOURCE_SHA_PROOF',
            'main_thread_fps_scope':'RAF_CALLBACK_CADENCE_NOT_DISPLAY_OR_GPU_FPS'}
        report['ui_thread_observation']=self.report
    def reject(self,code):
        self.report['rejected_callbacks']=min(32,self.report['rejected_callbacks']+1)
        self.report.setdefault('first_rejection',code)
        return False
    def record(self,source,value):
        if self.closed:
            self.report['callbacks_after_close']=min(32,self.report['callbacks_after_close']+1);return False
        if self.window_ended:return self.reject('SAMPLE_WINDOW_ENDED')
        if len(self.report['samples'])>=4:return self.reject('SAMPLE_LIMIT')
        if time.monotonic()-self.started>32:return self.reject('CALLBACK_LIFETIME')
        if (not isinstance(source,dict) or source.get('context') is not self.context
                or source.get('page') is not self.page or source.get('frame') is not self.page.main_frame
                or self.page.main_frame.url!=self.base+self.PAGE):return self.reject('CALLBACK_FRAME_SCOPE')
        # Read the pinned collector's event snapshot only. Its validation methods
        # latch asset failures and must never be called by this passive sampler.
        collector=self.collector
        request=getattr(collector,'request',None);document=getattr(collector,'document',None)
        frame=getattr(collector,'frame',None);generation=getattr(collector,'bound_generation',None)
        navigation=getattr(collector,'navigation_generation',None)
        if (getattr(collector,'failure','UNKNOWN') is not None
                or getattr(collector,'detached',None) is not False
                or not isinstance(frame,str) or not 1<=len(frame)<=160
                or not isinstance(request,dict) or not isinstance(document,dict)
                or not isinstance(request.get('id'),str) or not 1<=len(request['id'])<=160
                or not isinstance(request.get('loader'),str) or not 1<=len(request['loader'])<=160
                or document.get('loader')!=request['loader'] or document.get('url')!=self.base+self.PAGE
                or type(generation) is not int or not 1<=generation<=16
                or type(navigation) is not int or navigation!=generation):
            return self.reject('FRAME_EVENT_SCOPE')
        if self.generation not in (None,generation):return self.reject('DOCUMENT_GENERATION')
        def fields(row,names):return isinstance(row,dict) and len(row)==len(names) and set(row)==set(names)
        def number(n,low,high):return type(n) in (int,float) and low<=n<=high
        def integer(n,low,high):return type(n) is int and low<=n<=high
        def optional(n,low,high):return n is None or number(n,low,high)
        if not fields(value,('schema','nonce','sequence','elapsed_ms','sample_window_elapsed','timer_lateness_ms','visibility','ready_state',
                             'raf','long_tasks','motion','core')):return self.reject('SAMPLE_SCHEMA')
        if value['schema']!='NOX_UI_THREAD_SAMPLE_V1' or value['nonce']!=self.nonce:return self.reject('SAMPLE_BINDING')
        previous_sequence=self.report['samples'][-1]['sequence'] if self.report['samples'] else 0
        if (not integer(value['sequence'],1,4) or value['sequence']<=previous_sequence
                or not number(value['elapsed_ms'],0,32000) or value['elapsed_ms']<self.last_elapsed
                or type(value['sample_window_elapsed']) is not bool
                or value['sample_window_elapsed']!=(value['elapsed_ms']>=5000)
                or not number(value['timer_lateness_ms'],0,32000)
                or value['visibility'] not in ('visible','hidden')
                or value['ready_state'] not in ('loading','interactive','complete')):return self.reject('SAMPLE_ORDER_OR_TIME')
        r=value['raf'];l=value['long_tasks'];m=value['motion'];c=value['core']
        if not fields(r,('callbacks','max_gap_ms','silence_ms')) or not integer(r['callbacks'],0,10000) or not all(
                number(r[k],0,32000) for k in ('max_gap_ms','silence_ms')):return self.reject('RAF_SCHEMA')
        if (not fields(l,('supported','count','total_ms','max_ms')) or type(l['supported']) is not bool
                or not integer(l['count'],0,4096) or not number(l['total_ms'],0,32000*4096)
                or not number(l['max_ms'],0,32000)):return self.reject('LONG_TASK_SCHEMA')
        if not fields(m,('preference_reduced','preference_no_preference','runtime_reduced','runtime_eco','runtime_stop')) or not all(
                type(v) is bool for v in m.values()):return self.reject('MOTION_SCHEMA')
        if (not fields(c,('present','version_matches','read_error','fps','frames','tier','budget','pixel_ratio','adaptive','worker'))
                or not all(type(c[k]) is bool for k in ('present','version_matches','read_error'))
                or not optional(c['fps'],0,1000) or not (c['frames'] is None or integer(c['frames'],0,1000000000))
                or c['tier'] not in (None,'FULL','LIGHT','ECO','OFF') or c['budget'] not in (None,'MAX','ECO')
                or not optional(c['pixel_ratio'],0,8) or not optional(c['adaptive'],0,1)
                or c['worker'] is not None and type(c['worker']) is not bool):return self.reject('CORE_SCHEMA')
        if (not c['present'] and c['version_matches'] or not c['version_matches'] and any(
                c[k] is not None for k in ('fps','frames','tier','budget','pixel_ratio','adaptive','worker'))):
            return self.reject('CORE_VERSION_SCOPE')
        row={key:value[key] for key in ('sequence','elapsed_ms','sample_window_elapsed','timer_lateness_ms','visibility','ready_state')}
        phase=getattr(self.collector,'proof',{}).get('phase')
        if phase not in ('ARMED_BEFORE_NAVIGATION','CURRENT_FRAME_EVENT_BINDING','GET_RESPONSE_BODY',
                         'DECODE_AND_HASH','BODY_VERIFIED'):phase='NOT_CLASSIFIED'
        row.update(raf=dict(r),long_tasks=dict(l),motion=dict(m),core=dict(c),
                   callback_received_ms=round((time.monotonic()-self.started)*1000,3),
                   cdp_phase=phase,
                   same_page_main_frame_generation_verified=True)
        self.report['samples'].append(row);self.generation=generation;self.last_elapsed=value['elapsed_ms']
        self.window_ended=value['sample_window_elapsed']
        self.report.update(state='OBSERVED',callback_scope_verified=True)
        return True
    async def arm(self,script):
        await asyncio.wait_for(self.page.expose_binding(self.binding,self.record),timeout=1)
        configuration={'base':self.base,'path':self.PAGE,'binding':self.binding,'nonce':self.nonce}
        if script.count('__CONFIG__')!=1:raise RuntimeError('HOLD_WORKSPACE_BROWSER_V6_SAMPLER_CONFIG')
        await asyncio.wait_for(self.page.add_init_script(script=script.replace('__CONFIG__',json.dumps(configuration))),timeout=1)
        self.report['state']='ARMED_BEFORE_NAVIGATION'
    def stop(self):
        self.closed=True
        self.report['callback_collection_closed']=True
        self.report['samples_observed']=len(self.report['samples'])
        if not self.report['samples']:self.report['state']='NOT_OBSERVED'
'''


def prepared():
    blobs = {}
    for name, pin in PINS.items():
        encoded = BUNDLE.get(name)
        require(isinstance(encoded, str) and 0 < len(encoded) <= 262144, 'BUNDLE_BOUND')
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        blobs[name] = raw
    wrapper = types.ModuleType('_workspace_v5_frozen')
    wrapper.__file__ = '<' + BASE + '>'
    wrapper.__dict__['__NOX_' + 'BUNDLE_JSON__'] = dict(BUNDLE)
    exec(compile(blobs[BASE], wrapper.__file__, 'exec'), wrapper.__dict__)
    require(wrapper.PINS == {k: v for k, v in PINS.items() if k != BASE}, 'FROZEN_CLOSURE')
    base = wrapper.prepared()
    tail = base.PAGE_TAIL
    marker = "            report['browser_stage']='NAVIGATION'\n"
    setup = textwrap.indent(SAMPLER_SOURCE, '            ') + (
        "            workspace_sampler=PassiveUIThreadSampler(context,page,workspace_cdp,base,report)\n"
        "            await asyncio.wait_for(workspace_sampler.arm(" + repr(SAMPLER_JS) + "),timeout=3)\n")
    tail = change_once(tail, marker, setup + marker)
    tail = change_once(tail, "        finally:\n            if 'workspace_cdp' in locals():await workspace_cdp.close()\n",
        "        finally:\n            if 'workspace_sampler' in locals():workspace_sampler.stop()\n"
        "            if 'workspace_cdp' in locals():await workspace_cdp.close()\n")
    base.PAGE_TAIL = tail
    base.SCHEMA = SCHEMA
    base.KIND = KIND
    compile(base.browser_source(blobs[base.CORE]), '<workspace-v6-browser>', 'exec')
    return base


def main():
    return prepared().main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]{1,140}', reason):
            reason = 'HOLD_WORKSPACE_BROWSER_V6_PREFLIGHT'
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': KIND, 'data': {
            'schema': SCHEMA, 'state': 'HOLD', 'reason': reason, 'private_content_exported': False}},
            separators=(',', ':')), flush=True)
        raise SystemExit(2)
