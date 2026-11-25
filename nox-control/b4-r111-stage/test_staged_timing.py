"""Exercise the actual staged B4 entrypoint using the established A3 fixture."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from test_frozen_ordered import FrozenOrderedCallsite
from stage_timing import stage_timing, PINS, DEST, JOINT_DEST, SOURCE_PIN, blob

JS=r"""
const a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=process.argv[1], entry=path.join(root,'nox-control/d3-r113/timing_review.cjs');
const {makeTimingEvidenceReview:make}=require(entry);
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])
 t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8');
const evidence={packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,host:d.host};
let reads=0;
const r=make(()=>{reads++;return evidence})(bytes,d.packet);
a.equal(reads,1);a.equal(r.status,'MATCHED_FROZEN_ORDERED_OFFLINE',JSON.stringify(r));
a.deepEqual(r.offline_browser_timing.samples.map(s=>[s.turn,s.first_visible_delay_ms,s.stream_eof_delay_ms,s.dom_completion_delay_ms]),[[2,10,50,70],[3,10,50,70]]);
a.equal(r.offline_browser_timing.model_ttft_ms,null);
a.equal(r.offline_browser_timing.model_tokens_per_second,null);
for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])a.equal(r[k],false);
a.equal(make()(bytes,d.packet).status,'HOLD_RELEASE_PROVIDER');
let safe=0;
for(const field of ['first_visible_ms','eof_ms','dom_commit_ms'])for(const i of [0,1]){
 const row=d.host.turns[i].trusted, parent=field==='dom_commit_ms'?row.proof:row.sample;
 const value=parent[field];let access=0,calls=0;
 Object.defineProperty(parent,field,{configurable:true,enumerable:true,get(){return ++access===1?value-1:value;}});
 try{
  const result=make(()=>{calls++;return evidence;})(bytes,d.packet);
  a.equal(calls,1);a.equal(result.native_accepted,false);
  if(result.status==='MATCHED_FROZEN_ORDERED_OFFLINE'){
   const s=result.offline_browser_timing.samples[i];
   const delay={first_visible_ms:'first_visible_delay_ms',eof_ms:'stream_eof_delay_ms',dom_commit_ms:'dom_completion_delay_ms'}[field];
   a.equal(s[field]-s.begin_ms,s[delay]);
  } else a.equal(result.offline_browser_timing,null);
  safe++;
 }finally{Object.defineProperty(parent,field,{configurable:true,enumerable:true,writable:true,value});}
}
a.equal(safe,6);
// Exercise the actual extracted entrypoint with immutable invalid packets and
// host getters that would later try to present a valid order. No provider read
// is necessary for packet-internal contradictions.
const hash=s=>require('node:crypto').createHash('sha256').update(s,'utf8').digest('hex');
let pairHeld=0;
for(const mode of ['clock','overlap','digest']){
 const doc=JSON.parse(d.packet), row=doc.turns[1], trusted=d.host.turns[1].trusted;
 let parent,field,value;
 if(mode==='clock'){row.proof.clock_id=row.sample.clock_id='other-clock';parent=trusted.proof;field='clock_id';value='other-clock';}
 else if(mode==='overlap'){row.sample.begin_ms=doc.turns[0].proof.dom_commit_ms-1;parent=trusted.sample;field='begin_ms';value=row.sample.begin_ms;}
 else {row.proof.disposition_sha256='f'.repeat(64);parent=trusted.proof;field='disposition_sha256';value=row.proof.disposition_sha256;}
 const old=parent[field];let accesses=0,calls=0;
 Object.defineProperty(parent,field,{configurable:true,enumerable:true,get(){return ++accesses===1?value:old;}});
 try{
  const packet=JSON.stringify(doc), result=make(()=>{calls++;return {...evidence,packet_sha256:hash(packet),host:{...d.host,packet_sha256:hash(packet)}};})(bytes,packet);
  a.equal(result.status,mode==='digest'?'HOLD_TIMING_PROOF_PIN':'HOLD_TIMING_PAIR_ORDER',JSON.stringify(result));
  a.equal(result.offline_browser_timing,null);a.equal(result.native_accepted,false);a.equal(calls,0);a.equal(accesses,0);pairHeld++;
 }finally{Object.defineProperty(parent,field,{configurable:true,enumerable:true,writable:true,value:old});}
}
a.equal(pairHeld,3);
// Positive packet with changing clock getter: either hold or keep the packet clock.
let clockReads=0,providerReads=0;
const proof=d.host.turns[1].trusted.proof,clock=proof.clock_id;
Object.defineProperty(proof,'clock_id',{configurable:true,enumerable:true,get(){return ++clockReads===1?clock:'late-other-clock';}});
try{
 const result=make(()=>{providerReads++;return evidence;})(bytes,d.packet);
 a.equal(providerReads,1);a.equal(result.native_accepted,false);
 if(result.status==='MATCHED_FROZEN_ORDERED_OFFLINE'){
  const [first,second]=result.offline_browser_timing.samples;
  a.equal(first.clock_id,second.clock_id);a.ok(second.begin_ms>=first.dom_commit_ms);
 }else a.equal(result.offline_browser_timing,null);
}finally{Object.defineProperty(proof,'clock_id',{configurable:true,enumerable:true,writable:true,value:clock});}
console.log(JSON.stringify({immutable_pair_holds:pairHeld,changing_clock_safe:1}));
console.log(JSON.stringify({staged_projection_safe:safe}));
for(const p of Object.keys(require.cache))a.ok(p.startsWith(root+path.sep),p);
console.log(JSON.stringify({staged_positive:1,provider_reads:reads,unbound_hold:1,native_accepted:false}));
"""
class StagedTiming(unittest.TestCase):
    def test_staged(self):
        root=Path(os.environ["B4_STAGE_ROOT"]).resolve()
        before={p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
        # Every direct and transitive donor is checked before the first write.
        self.assertEqual(len(PINS),17)
        for rel in PINS:
            with self.subTest(donor=rel):
                q=root/rel
                original=q.read_bytes()
                try:
                    q.write_bytes(original+b" ")
                    with self.assertRaisesRegex(ValueError,"HOLD_TIMING_DEPENDENCY"):
                        stage_timing(root,joint=True)
                    self.assertFalse((root/JOINT_DEST).exists())
                finally:
                    q.write_bytes(original)
        print("B4_EXACT_DEPENDENCY_TAMPER_HOLD=17 (12 newly pinned transitive donors)")
        target=stage_timing(root,joint=True)
        self.assertEqual(target,root/JOINT_DEST)
        original=target.read_bytes()
        self.assertEqual(blob(original),SOURCE_PIN)
        self.assertEqual(SOURCE_PIN,'dd1aaf8637c6ffa04ac45d32b05941e9446facc7')
        stat=target.stat()
        self.assertEqual(stage_timing(root,joint=True),target)
        self.assertEqual(target.stat().st_mtime_ns,stat.st_mtime_ns)
        with self.assertRaisesRegex(ValueError,"HOLD_TIMING_DUPLICATE_DESTINATION"):
            stage_timing(root)
        self.assertFalse((root/DEST).exists())
        try:
            target.write_bytes(original+b" ")
            with self.assertRaisesRegex(ValueError,"HOLD_TIMING_OVERWRITE"):
                stage_timing(root,joint=True)
            self.assertEqual(target.read_bytes(),original+b" ")
        finally:
            target.write_bytes(original)
        self.assertEqual(set(p.relative_to(root) for p in root.rglob("*") if p.is_file())-set(before),{Path(JOINT_DEST)})
        print("B4_JOINT_TIMING_DESTINATION=1 exact_reuse=1 conflicting_hold=1 duplicate_hold=1")
        for p,b in before.items():
            self.assertEqual((root/p).read_bytes(),b,str(p))
        actual=subprocess.run
        fixture=FrozenOrderedCallsite("test_frozen_ordered_callsite")
        self.addCleanup(fixture.doCleanups)
        reached=[]
        def run(args,*a,**kw):
            if len(args)>3 and args[:2]==["node","-e"] and str(args[3]).endswith("/joint_frozen.cjs"):
                reached.append(True)
                return actual(["node","-e",JS,str(root)],*a,**kw)
            return actual(args,*a,**kw)
        with patch("subprocess.run",side_effect=run):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
