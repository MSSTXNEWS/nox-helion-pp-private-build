"""Focused synthetic selected-framing receipt at the actual extracted joint callsite."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import hashlib
import types

JS=r"""
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto'),path=require('node:path');
const {makeReleaseEvidenceReview:make,releasePins}=require(process.argv[1]);
const dir=path.dirname(process.argv[1]),root=path.resolve(dir,'../d3-r111');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const selected={browser_sha256:sha(fs.readFileSync(path.resolve(dir,'../d3-r111-successor/browser/b1_browser_r100.js'))),
 role_sha256:sha(fs.readFileSync(path.resolve(dir,'../a3-r113-browser/browser_role_input.json')))};
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8'),packet=d.packet,p=JSON.parse(d.frozen)[0],ph=p.receipts.expected,w=p.turns[0].wire;
const descriptor={schema:'NOX_A3_R111_ROUTE_EVIDENCE_V1',packet_sha256:d.host.packet_sha256,
 payload_sha256:d.detached_fixture_pin,...releasePins(),framing:'framework_managed',raw_chunk_writer:false,framework_framing:true,
 physical_route:ph.route,model_id:ph.model_id,physical_dialog_id:ph.dialog_id,process:ph.process,
 turn_request_ids:ph.turn_request_ids,owner_admission_receipt_sha256:ph.owner_admission_receipt_sha256,
 symbolic_route:w.route,served_sha256:w.served_sha256,server_sha256:w.server_sha256,
 bridge_sha256:ph.bridge_sha256,browser_sha256:selected.browser_sha256,successor_role_sha256:selected.role_sha256};
const admitted=Buffer.from(d.admitted_fixture,'utf8');
const managed=['wire/b0_framework_r83.py','wire/b0_framework_r80.py','wire/b0_proxy_stream_iter.py','wire/b0_named_delta_encoder.py'];
const raw=['wire/b0_http_chunked_r76.py','wire/b0_proxy_stream_iter.py','wire/b0_named_delta_encoder.py'];
function evidence(mode){
 const route={...descriptor,framing:mode,raw_chunk_writer:mode==='raw_http_1_1',framework_framing:mode==='framework_managed'};
 const route_bytes=Buffer.from(JSON.stringify(route)),route_sha256=sha(route_bytes);
 const paths=mode==='framework_managed'?managed:raw;
 const f={schema:'NOX_D3_SELECTED_FRAMING_READBACK_V1',packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,route_sha256,
 owner_admission_receipt_sha256:ph.owner_admission_receipt_sha256,framing:mode,adapter_path:paths[0],process:ph.process,
 modules:Object.fromEntries(paths.map(n=>{const h=sha(fs.readFileSync(path.join(root,n)));return [n,{expected_sha256:h,installed_sha256:h,loaded_sha256:h}]}))};
 const e={packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,host:d.host,route_bytes,route_sha256,admitted_envelope_bytes:admitted,admitted_envelope_sha256:sha(admitted)};
 attach(e,f);return {e,f};
}
function attach(e,f){e.framing_receipt_bytes=Buffer.from(JSON.stringify(f));e.framing_receipt_sha256=sha(e.framing_receipt_bytes);}
function run(e,status){let reads=0;const a=make(()=>{reads++;return e;})(bytes,packet);
 assert.equal(reads,1);assert.equal(a.status,status,JSON.stringify(a));
 for(const k of ['native_accepted','authentication_verified','host_provider_bound','ack_allowed','next_post_allowed','training_admitted'])assert.equal(a[k],false,k);
 if(status.startsWith('HOLD')){assert.equal(a.metrics,null);assert.equal(a.quality_sample,null);}
 return a;
}
for(const mode of ['framework_managed','raw_http_1_1']){
 const {e}=evidence(mode);const a=run(e,'MATCHED_R114_JOINT_OFFLINE');
 assert.equal(a.framing_authenticated,false);assert.equal(a.framing_receipt_sha256,e.framing_receipt_sha256);
 assert.equal(a.offline_browser_timing.status,'OFFLINE_BROWSER_TIMING_ONLY');
}
// Selected B3 snapshot: getters must never execute, proxy traps must never execute,
 // and shared-memory identities are not immutable host observations.
for(const field of ['packet_sha256','payload_sha256','route_sha256','route_bytes','admitted_envelope_bytes','framing_receipt_bytes','framing_receipt_sha256']){
 const {e}=evidence('framework_managed');let getterReads=0;
 Object.defineProperty(e,field,{enumerable:true,get(){getterReads++;return 'f'.repeat(64)}});
 run(e,'HOLD_ROUTE_DETACHED');assert.equal(getterReads,0);
}
{
 const {e}=evidence('framework_managed');let traps=0;
 run(new Proxy(e,{get(){traps++;throw Error('proxy')},ownKeys(){traps++;throw Error('proxy')}}),'HOLD_ROUTE_DETACHED');
 assert.equal(traps,0);
}
for(const field of ['route_bytes','admitted_envelope_bytes','framing_receipt_bytes']){
 const {e}=evidence('raw_http_1_1'), original=e[field];
 const shared=Buffer.from(new SharedArrayBuffer(original.length));original.copy(shared);e[field]=shared;
 run(e,'HOLD_ROUTE_DETACHED');
}
console.log('R115 B3 R89 snapshot: 2 mode matches, 11 getter/proxy/shared-byte HOLD; one provider read; authority false.');

"""
class RouteEvidence(unittest.TestCase):
    def test_route_evidence(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'a3-r109-r80/test_frozen_ordered.py'
        # Exact selected R88 digest; historical R86 remains unchanged.
        browser_sha='37a756fdc6544f8b5d73425c83221bb958504bd3199dd6245aa4d4b62549651f'
        source=path.read_text(encoding='utf8')
        assert source.count('browser=h(77)')==1
        # Use the exact R86 browser digest in the synthetic fixture, not a production assertion.
        assert source.count('from freeze_release import freeze_release_payload')==1
        source=source.replace('from freeze_release import freeze_release_payload','from freeze_typed_release import freeze_release_payload')
        source=source.replace('browser=h(77)',f'browser="{browser_sha}"')
        anchor='positive["frozen"]=payload.decode("utf8")'
        assert source.count(anchor)==1
        source=source.replace(anchor, 'positive["admitted_fixture"]=json.dumps(dict(schema="NOX_B3_R83_INDEPENDENT_PHYSICAL_ENVELOPE_V1",expected=physical,receipt_index=json.loads(receipts[0])["receipt_index"]),separators=(",",":"),ensure_ascii=False)\n        '+anchor)
        extracted=Path(os.environ["R115_EXTRACTED"])/"nox-control"
        assert source.count('str(source/"frozen"),str(source)')==1
        source=source.replace('str(source/"frozen"),str(source)',repr(str(extracted/"a3-r109-r80/frozen"))+','+repr(str(extracted/"a3-r109-r80")))
        namespace=types.ModuleType('route_fixture')
        namespace.__file__=str(path)
        exec(compile(source,str(path),'exec'),namespace.__dict__)
        fixture=namespace.FrozenOrderedCallsite('test_frozen_ordered_callsite')
        self.addCleanup(fixture.doCleanups)
        actual=subprocess.run
        reached=[]
        def intercept(args,*a,**kw):
            if len(args)>3 and args[:2]==['node','-e'] and str(args[3]).endswith('/joint_frozen.cjs'):
                reached.append(True)
                return actual(['node','-e',JS,str(extracted/'d3-r114/joint_extracted.cjs')],*a,**kw)
            return actual(args,*a,**kw)
        with patch('subprocess.run',side_effect=intercept):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
