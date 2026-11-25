"""Run one new R111 evidence-ingress target using the existing synthetic A3 producer."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import hashlib
import types

JS=r"""
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {makeReleaseEvidenceReview:make,releasePins}=require(process.argv[1]);
const {stageSelectedBrowser}=require(require('node:path').join(require('node:path').dirname(process.argv[1]),'browser_selection.cjs'));
const selected=stageSelectedBrowser();
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8'),packet=d.packet,p=JSON.parse(d.frozen)[0];
const ph=p.receipts.expected,w=p.turns[0].wire;
const pin=releasePins(),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const descriptor={schema:'NOX_A3_R111_ROUTE_EVIDENCE_V1',packet_sha256:d.host.packet_sha256,
 payload_sha256:d.detached_fixture_pin,...pin,framing:'framework_managed',raw_chunk_writer:false,framework_framing:true,
 physical_route:ph.route,model_id:ph.model_id,physical_dialog_id:ph.dialog_id,process:ph.process,
 turn_request_ids:ph.turn_request_ids,owner_admission_receipt_sha256:ph.owner_admission_receipt_sha256,
 symbolic_route:w.route,served_sha256:w.served_sha256,server_sha256:w.server_sha256,
 bridge_sha256:ph.bridge_sha256,browser_sha256:selected.browser_sha256,successor_role_sha256:selected.role_sha256};
const admittedBytes=Buffer.from(d.admitted_fixture,'utf8');
function evidence(desc=descriptor){const route_bytes=Buffer.from(JSON.stringify(desc));return {
 packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,host:d.host,route_bytes,route_sha256:sha(route_bytes),admitted_envelope_bytes:admittedBytes,admitted_envelope_sha256:sha(admittedBytes)};}
const run=(desc)=>make(()=>evidence(desc))(bytes,packet);
let reads=0;
const good=make(()=>{reads++;return evidence();})(bytes,packet);
assert.equal(reads,1);
assert.equal(good.offline_browser_timing.status,'OFFLINE_BROWSER_TIMING_ONLY');
assert.deepEqual(good.offline_browser_timing.samples.map(x=>[x.turn,x.first_visible_delay_ms,x.stream_eof_delay_ms,x.dom_completion_delay_ms]),[[2,10,50,70],[3,10,50,70]]);
assert.equal(good.offline_browser_timing.model_tokens_per_second,null);
const broken=evidence();broken.host=structuredClone(d.host);
for(const t of broken.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k]);
broken.host.turns[0].trusted.proof.reservation_sha256='f'.repeat(64);
const denied=make(()=>broken)(bytes,packet);
assert.equal(denied.status,'HOLD_TIMING_PROOF_PIN');
assert.equal(denied.offline_browser_timing,null);
assert.equal(denied.reported_review_diagnostics,null);
for(const [state,stop] of [['PENDING','CLEAR'],['FINALIZED','STOPPED']]){
 const changed=evidence();changed.host={...d.host,turns:d.host.turns.map(t=>({...t,receipts:{...t.receipts}}))};
 const disp=JSON.parse(changed.host.turns[0].receipts.disposition.toString('utf8'));
 changed.host.turns[0].receipts.disposition=Buffer.from(JSON.stringify({...disp,state,stop_recheck:stop}));
 const rejected=make(()=>changed)(bytes,packet);
 assert.notEqual(rejected.status,'MATCHED_R114_JOINT_OFFLINE');
 assert.equal(rejected.reported_review_diagnostics,null);
}
assert.equal(good.status,'MATCHED_R114_JOINT_OFFLINE',JSON.stringify(good));
assert.equal(good.reported_review_diagnostics.status,'REPORTED_UNVERIFIED_DATA_ONLY');
for(const k of ['native_accepted','authentication_verified','host_provider_bound','ack_allowed','next_post_allowed','training_admitted','route_authenticated','production_ready'])assert.equal(good[k],false);
assert.equal(good.selected_browser_sha256,selected.browser_sha256);
assert.equal(good.admitted_envelope_sha256,sha(admittedBytes));
const absent=evidence();delete absent.admitted_envelope_bytes;
assert.equal(make(()=>absent)(bytes,packet).status,'HOLD_R83_INPUT');
const drift=evidence();const independent=JSON.parse(d.admitted_fixture);independent.expected.process.pid+=1;
drift.admitted_envelope_bytes=Buffer.from(JSON.stringify(independent));drift.admitted_envelope_sha256=sha(drift.admitted_envelope_bytes);
assert.equal(make(()=>drift)(bytes,packet).status,'HOLD_R83_PHYSICAL_DRIFT');
assert.equal(good.quality_sample,null);assert.equal(good.metrics,null);
assert.equal(make()(bytes,packet).status,'HOLD_ROUTE_PROVIDER');
assert.equal(run({...descriptor,raw_chunk_writer:true}).status,'HOLD_ROUTE_FRAMING');
assert.equal(run({...descriptor,browser_sha256:'f'.repeat(64)}).status,'HOLD_R88_ROUTE_PIN');
assert.equal(run({...descriptor,physical_route:'/foreign'}).status,'HOLD_ROUTE_PHYSICAL');
assert.equal(run({...descriptor,assets:{...descriptor.assets,'browser/b1_browser_bundle.js':'f'.repeat(64)}}).status,'HOLD_R88_ROUTE_PIN');
const bad=evidence();bad.route_bytes=Buffer.concat([bad.route_bytes,Buffer.from(' ')]);
assert.equal(make(()=>bad)(bytes,packet).status,'HOLD_ROUTE_DIGEST');
console.log('R114 typed producer -> independent physical -> selected R88 route -> timing -> single R110 -> verdict: fixture only; provider reads=1; no production authority');
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
                return actual(['node','-e',JS,str(Path(__file__).with_name('joint_release.cjs'))],*a,**kw)
            return actual(args,*a,**kw)
        with patch('subprocess.run',side_effect=intercept):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
