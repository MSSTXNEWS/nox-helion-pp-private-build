"""Synthetic same-page bindings and scheduler only; no browser/network action."""
import asyncio
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import types
import unittest
import urllib.parse
from unittest.mock import patch

import owner_workspace_browser_acceptance_v5 as prior
import owner_workspace_browser_acceptance_v6 as m

HERE = Path(__file__).resolve().parent
FILES = {name: HERE / name for name in m.PINS}
FILES['owner_browser_stream_only_entry.py'] = HERE / 'pinned/browser_normal_v1/owner_browser_stream_only_entry.py'
BUNDLE = {name: base64.b64encode(path.read_bytes()).decode() for name, path in FILES.items()}
BASE = 'http://192.0.2.1:8080'
PAGE = '/nox-web-v29/pc/resonance.html'


class Page:
    def __init__(self):
        self.main_frame = types.SimpleNamespace(url=BASE + PAGE)
        self.calls = []

    async def expose_binding(self, name, callback):
        self.calls.append(('expose_binding', name, callback))

    async def add_init_script(self, script=None, *, path=None):
        if path is not None:
            raise AssertionError('File injection is not used')
        self.calls.append(('add_init_script', script))


def fixture():
    namespace = {'os': os, 'time': time, 'json': json, 'asyncio': asyncio}
    exec(compile(m.SAMPLER_SOURCE, '<passive-sampler>', 'exec'), namespace)
    context = object(); page = Page(); report = {}
    collector = types.SimpleNamespace(bound_generation=2,navigation_generation=2,
        frame='frame-main',failure=None,detached=False,
        request={'id':'request-public','loader':'loader-main'},
        document={'loader':'loader-main','url':BASE+PAGE},proof={'phase':'GET_RESPONSE_BODY'})
    sampler = namespace['PassiveUIThreadSampler'](context, page, collector, BASE, report)
    source = {'context': context, 'page': page, 'frame': page.main_frame}
    return sampler, source, report, collector


def sample(sampler, sequence=1, elapsed=None):
    elapsed = (sequence - 1) * 1000 if elapsed is None else elapsed
    return {'schema': 'NOX_UI_THREAD_SAMPLE_V1', 'nonce': sampler.nonce, 'sequence': sequence,
        'elapsed_ms': elapsed, 'sample_window_elapsed': elapsed >= 5000,
        'timer_lateness_ms': max(0, elapsed - (sequence - 1) * 1000),
        'visibility': 'visible', 'ready_state': 'complete',
        'raf': {'callbacks': sequence * 30, 'max_gap_ms': 18, 'silence_ms': 4},
        'long_tasks': {'supported': True, 'count': 1, 'total_ms': 70, 'max_ms': 70},
        'motion': {'preference_reduced': False, 'preference_no_preference': True,
            'runtime_reduced': False, 'runtime_eco': False, 'runtime_stop': False},
        'core': {'present': True, 'version_matches': True, 'read_error': False, 'fps': 39,
            'frames': 140, 'tier': 'FULL', 'budget': 'MAX', 'pixel_ratio': 1, 'adaptive': 1, 'worker': True}}


JS_HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const cfg=JSON.parse(fs.readFileSync(0,'utf8'));
function run(mode){
 let now=0,next=1,disconnected=false,observer=null;
 const timers=new Map(),frames=new Map(),events=new Map(),samples=[];
 const root=Object.freeze({dataset:Object.freeze({reducedMotion:'system'})});
 const body=Object.freeze({dataset:Object.freeze({})});
 const doc=Object.freeze({readyState:'complete',visibilityState:'visible',documentElement:root,body,
   addEventListener:(name,fn)=>events.set(name,fn)});
 class Observer{
   static supportedEntryTypes=['longtask'];
   constructor(callback){this.callback=callback;this.pending=[];observer=this;}
   observe(options){assert.deepStrictEqual(JSON.parse(JSON.stringify(options)),{type:'longtask'});}
   takeRecords(){const rows=this.pending;this.pending=[];return rows;}
   disconnect(){disconnected=true;}
 }
 const sandbox={performance:{now:()=>now},document:doc,
   location:Object.freeze({origin:mode==='foreign'?'https://foreign.invalid':cfg.base,pathname:cfg.path,search:'',hash:''}),
   matchMedia:q=>Object.freeze({matches:q.includes('no-preference')}),PerformanceObserver:Observer,
   requestAnimationFrame:callback=>{const id=next++;frames.set(id,callback);return id;},
   cancelAnimationFrame:id=>frames.delete(id),
   setTimeout:(callback,delay)=>{const id=next++;timers.set(id,{callback,due:now+delay});return id;},
   clearTimeout:id=>timers.delete(id),addEventListener:(name,fn)=>events.set(name,fn),
   fetch:()=>{throw Error('HTTP forbidden');},XMLHttpRequest:()=>{throw Error('XHR forbidden');},
   NoxCoreBg:Object.freeze({version:'NOX_CORE_BG_V22_FINAL2',
     state:()=>({fps:40,tier:'FULL',budget:'MAX',reason:'PRIVATE_RAW_URL',safe70:{secret:'DO_NOT_EXPORT'}}),
     diagnostics:()=>({frames:Math.floor(now/25),pixelRatio:1,adaptive:1,worker:true,
       background:{error:'PRIVATE_RAW_ERROR'},reason:'PRIVATE_VALUE'})})};
 sandbox.window=sandbox;sandbox.top=sandbox;
 sandbox[cfg.binding]=value=>{samples.push(JSON.parse(JSON.stringify(value)));return Promise.resolve();};
 vm.createContext(sandbox);vm.runInContext(cfg.script.replace('__CONFIG__',JSON.stringify({base:cfg.base,path:cfg.path,binding:cfg.binding,nonce:cfg.nonce})),sandbox);
 function step(to){
   now=to;
   const due=[...timers].filter(([,row])=>row.due<=now).sort((a,b)=>a[1].due-b[1].due);
   for(const [id,row]of due)if(timers.delete(id))row.callback();
   const callbacks=[...frames];frames.clear();for(const [,fn]of callbacks)fn(now);
 }
 if(mode==='foreign'){
   assert.equal(samples.length,0);assert.equal(frames.size,0);assert.equal(timers.size,0);return {mode,samples};
 }
 if(mode==='late'){
   observer.pending.push({startTime:1,duration:6000,name:'PRIVATE_TASK',attribution:[{name:'PRIVATE_URL'}]});
   step(6500);step(9000);
   assert.equal(samples.length,2);assert.equal(samples[1].sample_window_elapsed,true);
   assert.equal(samples[1].elapsed_ms,6500);assert.equal(samples[1].timer_lateness_ms,5500);
   assert.equal(samples[1].long_tasks.max_ms,6000);assert.equal(samples[1].raf.max_gap_ms,6500);
 }else{
   observer.pending.push({startTime:1,duration:70,name:'PRIVATE_TASK',attribution:[{name:'PRIVATE_URL'}]});
   for(let t=16;t<=8000;t+=16)step(t);
   assert.equal(samples.length,4);assert.equal(samples[1].long_tasks.count,1);
   assert.equal(samples[3].core.fps,40);assert(samples[3].raf.callbacks>0);
 }
 assert.equal(frames.size,0);assert.equal(timers.size,0);assert(disconnected);
 assert(!JSON.stringify(samples).includes('PRIVATE'));
 return {mode,samples};
}
process.stdout.write(JSON.stringify([run('normal'),run('late'),run('foreign')]));
'''


class PassiveUIThreadTests(unittest.TestCase):
    def test_exact_six_file_closure_and_v5_acceptance_and_deadlines_unchanged(self):
        for name, path in FILES.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), m.PINS[name])
        self.assertEqual(len(BUNDLE), 6)
        with patch.object(m, 'BUNDLE', BUNDLE): fresh = m.prepared()
        with patch.object(prior, 'BUNDLE', BUNDLE): old = prior.prepared()
        for name in ('main','request_gate','stop_owned_child','browser_source','child_program'):
            self.assertEqual(getattr(fresh,name).__code__.co_code,getattr(old,name).__code__.co_code)
        self.assertEqual(fresh.POLL_SECONDS,old.POLL_SECONDS)
        self.assertEqual(fresh.POLL_SECONDS,32)
        self.assertEqual(fresh.PAGE_TAIL.count("'Network.getResponseBody'"),1)
        self.assertEqual(fresh.PAGE_TAIL.count("'Page.getFrameTree'"),1)
        self.assertIn('timeout=2.5',fresh.PAGE_TAIL)
        self.assertIn('timeout=3',fresh.PAGE_TAIL)
        self.assertIn('timeout=5',fresh.PAGE_TAIL)
        self.assertLess(fresh.PAGE_TAIL.index('workspace_sampler.arm('),fresh.PAGE_TAIL.index("report['browser_stage']='NAVIGATION'"))
        self.assertLess(fresh.PAGE_TAIL.index('workspace_sampler.stop()'),fresh.PAGE_TAIL.index('await workspace_cdp.close()'))
        self.assertIn('workspace_cdp.final_check()',fresh.PAGE_TAIL)
        compile(fresh.child_program(fresh.sources()),'<passive-v6-child>','exec')
        for forbidden in ('Network.loadNetworkResource','Network.replayXHR','Fetch.enable','response.body()'):
            self.assertNotIn(forbidden,fresh.PAGE_TAIL)

    def test_four_samples_are_main_frame_bound_and_only_safe_projection_is_exported(self):
        probe,source,report,_=fixture()
        for seq in range(1,5):self.assertTrue(probe.record(source,sample(probe,seq)))
        self.assertFalse(probe.record(source,sample(probe,4)))
        probe.stop();data=report['ui_thread_observation']
        self.assertEqual(data['samples_observed'],4);self.assertTrue(data['callback_scope_verified'])
        self.assertTrue(all(row['cdp_phase']=='GET_RESPONSE_BODY' for row in data['samples']))
        self.assertFalse(data['root_cause_proven']);self.assertFalse(data['user_gpu_performance_evaluated'])
        raw=json.dumps(report,allow_nan=False)
        self.assertLess(len(raw),16384)
        self.assertNotIn(probe.nonce,raw);self.assertNotIn(BASE,raw);self.assertNotIn(probe.binding,raw)
        self.assertFalse(probe.record(source,sample(probe)))
        self.assertEqual(data['callbacks_after_close'],1)

    def test_foreign_page_frame_origin_and_context_are_rejected_without_values(self):
        for key in ('context','page','frame','url'):
            with self.subTest(key=key):
                probe,source,report,_=fixture()
                if key=='url':probe.page.main_frame.url='https://PRIVATE.invalid/private'
                else:source[key]=object()
                self.assertFalse(probe.record(source,sample(probe)))
                self.assertEqual(report['ui_thread_observation']['samples'],[])
                self.assertNotIn('PRIVATE',json.dumps(report))

    def test_changed_cdp_generation_or_failed_frame_binding_rejects_next_sample(self):
        probe,source,report,collector=fixture()
        self.assertTrue(probe.record(source,sample(probe)))
        collector.bound_generation=collector.navigation_generation=3
        self.assertFalse(probe.record(source,sample(probe,2)))
        self.assertEqual(report['ui_thread_observation']['first_rejection'],'DOCUMENT_GENERATION')
        probe,source,report,collector=fixture()
        collector.failure='PRIVATE_EXCEPTION'
        self.assertFalse(probe.record(source,sample(probe)))
        self.assertEqual(report['ui_thread_observation']['first_rejection'],'FRAME_EVENT_SCOPE')
        self.assertNotIn('PRIVATE',json.dumps(report))

    def test_schema_nonce_order_numbers_and_unverified_core_cannot_leak(self):
        changes=(lambda v:v.update(nonce='PRIVATE'),lambda v:v.update(sequence=True),
            lambda v:v.update(sequence=0),lambda v:v.update(elapsed_ms=float('nan')),
            lambda v:v.update(elapsed_ms=float('inf')),lambda v:v.update(visibility='PRIVATE'),
            lambda v:v.update(private='PRIVATE'),lambda v:v['core'].update(reason='PRIVATE'),
            lambda v:v['core'].update(version_matches=False),lambda v:v['raf'].update(callbacks=True),
            lambda v:v['motion'].update(runtime_eco='PRIVATE'))
        for mutate in changes:
            probe,source,report,_=fixture();value=sample(probe);mutate(value)
            self.assertFalse(probe.record(source,value))
            self.assertEqual(report['ui_thread_observation']['samples'],[])
            self.assertNotIn('PRIVATE',json.dumps(report,allow_nan=False))

    def test_real_v5_early_callback_never_changes_asset_failure_or_proof(self):
        namespace={'asyncio':asyncio,'urllib':urllib,'re':__import__('re'),
                   'digest':lambda raw:hashlib.sha256(raw).hexdigest()}
        exec(compile(prior.CDP_SOURCE,'<real-v5-collector>','exec'),namespace)
        asset_report={};collector=namespace['WorkspaceCDPProof']('192.0.2.1:8080',asset_report)
        collector.frame='frame-main'
        probe,source,report,_=fixture();probe.collector=collector
        before=copy.deepcopy(collector.__dict__)
        self.assertFalse(probe.record(source,sample(probe,1)))
        self.assertEqual(collector.__dict__,before)
        self.assertIsNone(collector.failure)
        collector.event('navigated',{'frame':{'id':'frame-main','loaderId':'loader-main','url':BASE+PAGE}})
        collector.event('request',{'requestId':'request-public','loaderId':'loader-main',
            'frameId':'frame-main','type':'Script',
            'request':{'url':BASE+collector.PATH,'method':'GET'}})
        before=copy.deepcopy(collector.__dict__)
        # The browser does not replay seq1 after an early rejection. A later
        # bound sample keeps its original sequence and stays diagnostic only.
        self.assertTrue(probe.record(source,sample(probe,2)))
        self.assertEqual(collector.__dict__,before)
        self.assertIsNone(collector.failure)
        self.assertEqual(report['ui_thread_observation']['samples'][0]['sequence'],2)
        self.assertFalse(probe.record(source,sample(probe,2)))
        self.assertFalse(probe.record(source,sample(probe,1)))
        self.assertTrue(probe.record(source,sample(probe,3)))
        self.assertEqual(collector.__dict__,before)
        for fragment in (".current_document(",".check(","collector.reject("):
            self.assertNotIn(fragment,m.SAMPLER_SOURCE)

    def test_late_final_sample_reports_delay_but_does_not_extend_collection(self):
        probe,source,report,_=fixture()
        self.assertTrue(probe.record(source,sample(probe)))
        late=sample(probe,2,6500);late['long_tasks'].update(count=1,total_ms=6000,max_ms=6000)
        self.assertTrue(probe.record(source,late))
        self.assertFalse(probe.record(source,sample(probe,3,6600)))
        self.assertEqual(report['ui_thread_observation']['first_rejection'],'SAMPLE_WINDOW_ENDED')
        probe,source,report,_=fixture();probe.started=time.monotonic()-33
        self.assertFalse(probe.record(source,sample(probe)))
        self.assertEqual(report['ui_thread_observation']['first_rejection'],'CALLBACK_LIFETIME')

    def test_pre_goto_arm_uses_supported_binding_and_init_api_only(self):
        probe,_,report,_=fixture()
        asyncio.run(probe.arm(m.SAMPLER_JS))
        self.assertEqual([row[0] for row in probe.page.calls],['expose_binding','add_init_script'])
        self.assertIs(probe.page.calls[0][2].__self__,probe)
        self.assertIn(probe.nonce,probe.page.calls[1][1])
        self.assertNotIn('__CONFIG__',probe.page.calls[1][1])
        self.assertEqual(report['ui_thread_observation']['state'],'ARMED_BEFORE_NAVIGATION')
        for forbidden in ('fetch(','.post(','.innerHTML','.textContent=','localStorage','sessionStorage','setAttribute('):
            self.assertNotIn(forbidden,m.SAMPLER_JS)

    def test_actual_js_bounded_samples_cleanup_and_stall_metadata(self):
        cfg={'script':m.SAMPLER_JS,'base':BASE,'path':PAGE,'binding':'publicFixtureBinding','nonce':'a'*32}
        result=subprocess.run(['node','-e',JS_HARNESS],input=json.dumps(cfg),text=True,capture_output=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        rows=json.loads(result.stdout)
        self.assertEqual([len(row['samples']) for row in rows],[4,2,0])
        for row in rows[:2]:
            probe,source,report,_=fixture()
            for value in row['samples']:
                value['nonce']=probe.nonce
                self.assertTrue(probe.record(source,value),report)
            self.assertLess(len(json.dumps(report)),16384)


if __name__ == '__main__':
    unittest.main()
