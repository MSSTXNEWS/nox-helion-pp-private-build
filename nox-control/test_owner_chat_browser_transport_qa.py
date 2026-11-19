"""Focused diagnostic regressions; no native server or model calls."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,patch

import owner_chat_browser_transport_qa as diagnostic
import owner_browser_transport_qa_entry as entry


def installed():
    raw=Path(__file__).with_name('owner_chat_browser_qa.py').read_bytes()
    module=types.ModuleType('frozen_browser_qa_test')
    exec(compile(raw,'<frozen-browser>','exec'),module.__dict__)
    return diagnostic.install(module,raw)


class TransportDiagnosticTests(unittest.TestCase):
    def test_composed_child_rechecks_both_sources_and_uses_frozen_entry(self):
        folder=Path(__file__).parent
        bundle={name:base64.b64encode((folder/name).read_bytes()).decode() for name in entry.PINS}
        with patch.object(entry,'BUNDLE',bundle):
            blobs=entry.sources();program=entry.child_program(blobs)
            compile(program,'<transport-child>','exec')
        self.assertIn(b'HOLD_BROWSER_DIAGNOSTIC_CHILD_PIN',program)
        self.assertIn(b'raise SystemExit(core.main())',program)
        bundle['owner_chat_browser_transport_qa.py']=base64.b64encode(b'unreviewed').decode()
        with patch.object(entry,'BUNDLE',bundle),self.assertRaisesRegex(RuntimeError,'BUNDLE_PIN'):
            entry.sources()

    def test_source_overlay_preserves_original_and_strict_acceptance(self):
        core=installed()
        self.assertEqual(core.EXPECTED,','.join(map(str,range(1,41))))
        self.assertEqual(core.public_numeric_answer(', '.join(map(str,range(1,41)))),core.EXPECTED)
        self.assertIsNone(core.public_numeric_answer('private text'))
        self.assertFalse(core.progressive_stream_valid({'native_delta_count':100}))
        self.assertEqual(hashlib.sha256(Path(__file__).with_name('owner_chat_browser_qa.py').read_bytes()).hexdigest(),diagnostic.BASE_SHA)
        with self.assertRaisesRegex(RuntimeError,'BASE_PIN'):
            diagnostic.install(types.ModuleType('bad'),b'print("unreviewed")')

    def test_actual_viewport_mismatch_is_not_accepted_as_requested_resize(self):
        dom={'width':1440,'height':1000}
        metrics={'cssLayoutViewport':{'clientWidth':1440,'clientHeight':1000},
                 'cssVisualViewport':{'clientWidth':1440,'clientHeight':1000}}
        self.assertFalse(diagnostic.viewport_projection(dom,metrics,{'width':1280,'height':720})['matches'])
        self.assertTrue(diagnostic.viewport_projection(dom,metrics,{'width':1440,'height':1000})['matches'])
        metrics['cssVisualViewport']['clientWidth']=1280
        self.assertFalse(diagnostic.viewport_projection(dom,metrics,{'width':1440,'height':1000})['matches'])

    def test_wire_projection_tracks_only_native_request_without_body_or_headers(self):
        tracker=diagnostic.WireTiming('127.0.0.1:8080')
        tracker.request({'requestId':'secret-id','timestamp':10,'request':{
            'url':'http://127.0.0.1:8080/api/nox/chat/stream','method':'POST',
            'postData':'private prompt','headers':{'Cookie':'private cookie'}}})
        tracker.response({'requestId':'secret-id','timestamp':10.1,'response':{'status':200,'headers':{'secret':'value'}}})
        tracker.data({'requestId':'unrelated','timestamp':10.15,'dataLength':999,'encodedDataLength':999})
        for stamp,size in ((10.2,10),(10.6,20)):
            tracker.data({'requestId':'secret-id','timestamp':stamp,'dataLength':size,'encodedDataLength':size})
        tracker.finished({'requestId':'secret-id','timestamp':10.7})
        value=tracker.snapshot();wire=json.dumps(value)
        self.assertEqual(value['target_requests'],1)
        self.assertEqual(value['data_event_count'],2)
        self.assertEqual(value['decoded_bytes'],30)
        self.assertEqual([row['at_ms'] for row in value['data_events']],[200,600])
        self.assertEqual(value['finished_ms'],700)
        for private in ('private prompt','private cookie','secret-id','headers','http://'):
            self.assertNotIn(private,wire.replace('response_bodies_or_headers_exported',''))

    def test_log_projection_excludes_private_rows_and_does_not_claim_llm(self):
        prompt='[NOX UI QA abcdef] '+('public numeric fixture '*5)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'proxy.log';path.write_bytes(b'older private conversation\n')
            tracker=diagnostic.RouteEvidence.__new__(diagnostic.RouteEvidence)
            tracker.path=path;tracker.fd=os.open(path,os.O_RDONLY);tracker.start=os.fstat(tracker.fd)
            tracker.prompt=prompt;tracker.result={'source_verified':True,'upstream_model_request_bound':False}
            with path.open('ab') as stream:
                stream.write(b"chat_timing build_ms=999 cedr_ready=True seed=1 cache_prompt=True user='private secret'\n")
                stream.write(('chat_timing build_ms=12 cedr_ready=False seed=123 cache_prompt=True user='+repr(prompt[:80])+'\n').encode())
                stream.write(('chat_ttft ttft_s=0.25 user='+repr(prompt[:80])+'\n').encode())
            value=tracker.finish()
            self.assertTrue(value['early_understanding_return_excluded'])
            self.assertEqual(value['build_ms'],12);self.assertEqual(value['proxy_first_stream_byte_ms'],250)
            self.assertFalse(value['upstream_model_request_bound']);self.assertIsNone(tracker.fd)
            self.assertNotIn('private',json.dumps(value));self.assertNotIn('abcdef',json.dumps(value))

    @unittest.skipUnless(shutil.which('node'),'Node is required for actual reader observation')
    def test_one_wire_read_and_many_frames_remain_distinct_in_actual_observer(self):
        core=installed()
        setup=r"""
const assert=require('node:assert/strict');
global.window=global;global.location={origin:'http://127.0.0.1:8080',href:'http://127.0.0.1:8080/'};
global.document={querySelectorAll:()=>[]};
global.HTMLCanvasElement=function(){};HTMLCanvasElement.prototype.getContext=function(){};
global.addEventListener=()=>{};global.requestAnimationFrame=()=>1;
const payload=[{type:'delta',text:'1'},{type:'delta',text:','},{type:'delta',text:'2'},
 {type:'done',saved:true,s03_integrated:true,dialog_id:'a'.repeat(32)}].map(x=>JSON.stringify(x)+'\n').join('');
global.fetch=async()=>new Response(payload,{headers:{'Content-Type':'application/x-ndjson'}});
"""
        tail=r"""
(async()=>{
 await fetch('/api/nox/chat/stream');
 await new Promise(resolve=>setTimeout(resolve,20));
 const q=window.__NOX_BROWSER_QA;
 assert.equal(q.nativeCalls,1);assert.equal(q.nativeDeltas,3);assert.equal(q.nativeReadCount,1);
 assert.equal(q.nativeReadEvents[0].delta_frames,3);assert.equal(q.nativeReadEvents[0].contains_done,true);
 assert.equal(q.answer,'1,2');assert.ok(q.nativeResponseAt>=0);assert.ok(q.nativeLastDelta>=q.nativeResponseAt);
 console.log('PASS: one wire read contains three logical deltas');
})().catch(error=>{console.error(error.name);process.exitCode=1;});
"""
        script=setup+core.OBSERVER_JS.replace('__CONFIG__',json.dumps({'did':'a'*32}))+tail
        result=subprocess.run([shutil.which('node')],input=script,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS:',result.stdout)


class ViewportTests(unittest.IsolatedAsyncioTestCase):
    async def test_unapplied_resize_stops_layout_acceptance_and_keeps_actual_metrics(self):
        core=installed();page=types.SimpleNamespace(set_viewport_size=AsyncMock(),
            evaluate=AsyncMock(return_value={'width':1440,'height':1000}),
            _nox_transport_cdp=types.SimpleNamespace(send=AsyncMock(return_value={
                'cssLayoutViewport':{'clientWidth':1440,'clientHeight':1000},
                'cssVisualViewport':{'clientWidth':1440,'clientHeight':1000}})))
        report={}
        clock=iter([0,4])
        with patch.object(core,'stop_present',return_value=False),patch.object(diagnostic,'time',types.SimpleNamespace(monotonic=lambda:next(clock))):
            with self.assertRaisesRegex(RuntimeError,'VIEWPORT_NOT_APPLIED'):
                await diagnostic.layout_cases(core,page,report,[(1280,720,True)])
        row=report['report_layout_cases'][0]
        self.assertEqual(row['viewport_proof']['state'],'NOT_APPLIED')
        self.assertEqual(row['viewport_proof']['last']['dom']['width'],1440)
        self.assertNotIn('geometry',row)


if __name__=='__main__':unittest.main()
