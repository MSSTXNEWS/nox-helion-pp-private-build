"""One differential at the existing A3/R110 release boundary; fixture only."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from test_frozen_ordered import FrozenOrderedCallsite

JS=r"""
const fs=require('node:fs'),a=require('node:assert/strict'),{createHash}=require('node:crypto');
const {makeTimingEvidenceReview:make}=require(process.argv[1]);
const {makeReportedReview:old}=require(process.argv[2]);
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8');
const evidence={packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,host:d.host};
const valid=make(()=>evidence)(bytes,d.packet);
a.equal(valid.status,'MATCHED_FROZEN_ORDERED_OFFLINE',JSON.stringify(valid));
const timing=valid.offline_browser_timing;
a.equal(timing.status,'OFFLINE_BROWSER_TIMING_ONLY');
a.deepEqual(timing.samples.map(x=>[x.turn,x.first_visible_delay_ms,x.stream_eof_delay_ms,x.dom_completion_delay_ms]),[[2,10,50,70],[3,10,50,70]]);
a.equal(timing.packet_sha256,evidence.packet_sha256);
a.equal(timing.frozen_payload_sha256,evidence.payload_sha256);
a.equal(timing.model_ttft_ms,null);a.equal(timing.model_tokens_per_second,null);
for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])a.equal(valid[k],false);
a.equal(valid.metrics,null);a.equal(valid.quality_sample,null);
let prior=0,blocked=0;
for(const field of ['reservation_sha256','disposition_sha256']){
 for(let i=0;i<2;i++){
  const candidate=JSON.parse(d.packet);
  const host={...d.host,turns:d.host.turns.map(t=>({...t,trusted:{...t.trusted,proof:{...t.trusted.proof}}}))};
  candidate.turns[i].proof[field]='f'.repeat(64);
  host.turns[i].trusted.proof[field]='f'.repeat(64);
  const packet=JSON.stringify(candidate), packet_sha256=createHash('sha256').update(packet).digest('hex');
  host.packet_sha256=packet_sha256;
  const altered={...evidence,packet_sha256,host};
  a.equal(old(()=>altered)(bytes,packet).status,'MATCHED_FROZEN_ORDERED_OFFLINE');prior++;
  const result=make(()=>altered)(bytes,packet);
  a.equal(result.status,'HOLD_TIMING_PROOF_PIN');a.equal(result.offline_browser_timing,null);a.equal(result.offline_metrics,undefined);blocked++;
 }
}
a.equal(make()(bytes,d.packet).status,'HOLD_RELEASE_PROVIDER');
a.equal(make(()=>evidence)(Buffer.concat([bytes,Buffer.from(' ')]),d.packet).offline_browser_timing,null);
console.log(JSON.stringify({fixture_positive:1,old_contradictory_matches:prior,new_contradictory_holds:blocked,browser_fixture_ms:[10,50,70],native_accepted:false}));
"""
class TimingRelease(unittest.TestCase):
    def test_release_timing(self):
        actual=subprocess.run
        here=Path(__file__).resolve().parent
        fixture=FrozenOrderedCallsite("test_frozen_ordered_callsite")
        self.addCleanup(fixture.doCleanups)
        reached=[]
        def run(args,*a,**kw):
            if len(args)>3 and args[:2]==["node","-e"] and str(args[3]).endswith("/joint_frozen.cjs"):
                reached.append(True)
                return actual(["node","-e",JS,str(here/"timing_review.cjs"),str(here.parent/"b2-r110"/"reported_review.cjs")],*a,**kw)
            return actual(args,*a,**kw)
        with patch("subprocess.run",side_effect=run):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
