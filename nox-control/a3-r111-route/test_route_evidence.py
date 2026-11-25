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
 bridge_sha256:ph.bridge_sha256,browser_sha256:pin.assets['browser/b1_browser_bundle.js']};
function evidence(desc=descriptor){const route_bytes=Buffer.from(JSON.stringify(desc));return {
 packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,host:d.host,route_bytes,route_sha256:sha(route_bytes)};}
const run=(desc)=>make(()=>evidence(desc))(bytes,packet);
const good=run(descriptor);
assert.equal(good.status,'MATCHED_R111_ROUTE_OFFLINE',JSON.stringify(good));
assert.equal(good.reported_review_diagnostics.status,'REPORTED_UNVERIFIED_DATA_ONLY');
for(const k of ['native_accepted','authentication_verified','host_provider_bound','ack_allowed','next_post_allowed','training_admitted','route_authenticated','production_ready'])assert.equal(good[k],false);
assert.equal(good.quality_sample,null);assert.equal(good.metrics,null);
assert.equal(make()(bytes,packet).status,'HOLD_ROUTE_PROVIDER');
assert.equal(run({...descriptor,raw_chunk_writer:true}).status,'HOLD_ROUTE_FRAMING');
assert.equal(run({...descriptor,browser_sha256:'f'.repeat(64)}).status,'HOLD_ROUTE_SERVED_BROWSER');
assert.equal(run({...descriptor,physical_route:'/foreign'}).status,'HOLD_ROUTE_PHYSICAL');
assert.equal(run({...descriptor,assets:{...descriptor.assets,'browser/b1_browser_bundle.js':'f'.repeat(64)}}).status,'HOLD_ROUTE_RELEASE_PIN');
const bad=evidence();bad.route_bytes=Buffer.concat([bad.route_bytes,Buffer.from(' ')]);
assert.equal(make(()=>bad)(bytes,packet).status,'HOLD_ROUTE_DIGEST');
console.log('R111 exact release route evidence: 1 offline match; 6 HOLD; no production authority');
"""
class RouteEvidence(unittest.TestCase):
    def test_route_evidence(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'a3-r109-r80/test_frozen_ordered.py'
        browser=(root/'d3-r111/browser/b1_browser_bundle.js').read_bytes()
        source=path.read_text(encoding='utf8')
        assert source.count('browser=h(77)')==1
        # Use the exact R86 browser digest in the synthetic fixture, not a production assertion.
        source=source.replace('browser=h(77)',f'browser="{hashlib.sha256(browser).hexdigest()}"')
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
                return actual(['node','-e',JS,str(Path(__file__).with_name('route_evidence.cjs'))],*a,**kw)
            return actual(args,*a,**kw)
        with patch('subprocess.run',side_effect=intercept):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
