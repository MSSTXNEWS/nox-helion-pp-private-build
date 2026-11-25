"""One differential at the existing A3/R110 release boundary; fixture only."""
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from test_frozen_ordered import FrozenOrderedCallsite

JS=r"""
const fs=require('node:fs'),a=require('node:assert/strict'),{createHash}=require('node:crypto');
const {makeTimingEvidenceReview:make}=require(process.argv[1]);
const {makeTimingEvidenceReview:old}=require(process.argv[2]);
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8');
const evidence={packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,host:d.host};
const expected=[[2,10,50,70],[3,10,50,70]];
function invoke(fn,field,index){
 const row=d.host.turns[index].trusted, parent=field==='dom_commit_ms'?row.proof:row.sample;
 const value=parent[field];let reads=0,calls=0;
 Object.defineProperty(parent,field,{configurable:true,enumerable:true,get(){return ++reads===1?value-1:value;}});
 try{const result=fn(()=>{calls++;return evidence;})(bytes,d.packet);return {result,calls};}
 finally{Object.defineProperty(parent,field,{configurable:true,enumerable:true,writable:true,value});}
}
const valid=make(()=>evidence)(bytes,d.packet);
a.equal(valid.status,'MATCHED_FROZEN_ORDERED_OFFLINE',JSON.stringify(valid));
a.deepEqual(valid.offline_browser_timing.samples.map(x=>[x.turn,x.first_visible_delay_ms,x.stream_eof_delay_ms,x.dom_completion_delay_ms]),expected);
let contradictions=0,consistent=0;
for(const field of ['first_visible_ms','eof_ms','dom_commit_ms'])for(const i of [0,1]){
 const before=invoke(old,field,i);a.equal(before.result.status,'MATCHED_FROZEN_ORDERED_OFFLINE',JSON.stringify(before.result));
 const x=before.result.offline_browser_timing.samples[i]; const delay={first_visible_ms:'first_visible_delay_ms',eof_ms:'stream_eof_delay_ms',dom_commit_ms:'dom_completion_delay_ms'}[field];
 a.notEqual(x[field]-x.begin_ms,x[delay]);contradictions++;
 const after=invoke(make,field,i);
 // Candidate may HOLD (getter first read no longer consumed before validation), or project only matching timestamps.
 if(after.result.status==='MATCHED_FROZEN_ORDERED_OFFLINE'){
   const y=after.result.offline_browser_timing.samples[i];a.equal(y[field]-y.begin_ms,y[delay]);
 }else a.equal(after.result.offline_browser_timing,null);
 a.equal(after.calls,1);a.equal(after.result.native_accepted,false);consistent++;
}
console.log(JSON.stringify({baseline_contradictions:contradictions,candidate_safe:consistent,normal_fixture:1,native_accepted:false}));
"""
class TimingProjection(unittest.TestCase):
    def test_release_timing(self):
        actual=subprocess.run
        here=Path(__file__).resolve().parent
        fixture=FrozenOrderedCallsite("test_frozen_ordered_callsite")
        self.addCleanup(fixture.doCleanups)
        reached=[]
        def run(args,*a,**kw):
            if len(args)>3 and args[:2]==["node","-e"] and str(args[3]).endswith("/joint_frozen.cjs"):
                reached.append(True)
                return actual(["node","-e",JS,str(here/"timing_review_projection.cjs"),str(here/"timing_review.cjs")],*a,**kw)
            return actual(args,*a,**kw)
        with patch("subprocess.run",side_effect=run):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
