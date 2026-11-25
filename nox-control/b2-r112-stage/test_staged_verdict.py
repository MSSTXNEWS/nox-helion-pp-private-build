"""Use the existing A3 fixture producer; only the final Node assertions change."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from test_frozen_ordered import FrozenOrderedCallsite
from stage_verdict import stage_verdict, PINS, DEST

JS = r"""
const fs=require('node:fs'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const {checkReportedVerdicts:check}=require(process.argv[1]);
const {makeReportedReview:make}=require(process.argv[2]);
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8');
let count=0,passed=0,rejected=0;
const valid=new Set(['000','010','001','110','101','111']);
for(let a=0;a<8;a++)for(let b=0;b<8;b++){
 const doc=JSON.parse(d.packet),s=doc.review.quality_sample.review_summary;
 const bits=[a.toString(2).padStart(3,'0'),b.toString(2).padStart(3,'0')];
 for(const [i,k] of ['disagreements','reported_incorrect','reported_uncertain'].entries())
  s[k]=[2,3].filter((n,j)=>bits[j][i]==='1');
 s.review_summary=s.reported_incorrect.length?'INCORRECT_REPORTED_UNVERIFIED':
  (s.disagreements.length||s.reported_uncertain.length)?'ADJUDICATION_REQUIRED':'TWO_REVIEWER_CONSENSUS_REPORTED_UNVERIFIED';
 const packet=JSON.stringify(doc), pin=createHash('sha256').update(packet,'utf8').digest('hex');
 const evidence={packet_sha256:pin,payload_sha256:d.detached_fixture_pin,host:{...d.host,packet_sha256:pin,quality:doc.review}};
 let reads=0;
 const old=make(()=>{reads++;return evidence})(bytes,packet);
 assert.equal(reads,1);
 assert.equal(old.status,'MATCHED_FROZEN_ORDERED_OFFLINE',JSON.stringify(old));
 const out=check(old); count++;
 if(bits.every(x=>valid.has(x))){assert.equal(out,old);passed++;}
 else {assert.equal(out.status,'HOLD_REPORTED_VERDICT_INCONSISTENT');assert.equal(out.reported_review_diagnostics,null);assert.equal(out.offline_metrics,undefined);rejected++;}
 for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])assert.equal(out[k],false);
}
assert.deepEqual([count,passed,rejected],[64,36,28]);
const noProvider=make()(bytes,d.packet);assert.equal(check(noProvider),noProvider);
for(const p of Object.keys(require.cache))assert.ok(p.startsWith(require('node:path').resolve(process.argv[1],'../../..')+require('node:path').sep),p);
console.log('R112 extracted actual R110 fixture: 64 combinations; 36 feasible unchanged / 28 impossible HOLD; one provider read each; no native authority');
"""

class VerdictConsistency(unittest.TestCase):
    def test_verdict_consistency(self):
        actual = subprocess.run
        root = Path(os.environ["B2_STAGE_ROOT"]).resolve()
        before = {p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(len(PINS), 19)
        for name in PINS:
            with self.subTest(tampered_dependency=name):
                q = root / name
                raw = q.read_bytes()
                try:
                    q.write_bytes(raw+b" ")
                    with self.assertRaisesRegex(ValueError, "HOLD_VERDICT_DEPENDENCY"):
                        stage_verdict(root)
                    self.assertFalse((root/DEST).exists())
                finally:
                    q.write_bytes(raw)
        print("R112 stage: 19 pinned dependencies, each tamper rejected")
        module = stage_verdict(root)
        with self.assertRaisesRegex(ValueError, "HOLD_VERDICT_OVERWRITE"):
            stage_verdict(root)
        self.assertEqual(set(p.relative_to(root) for p in root.rglob("*") if p.is_file())-set(before),{Path(DEST)})
        for p,b in before.items():
            self.assertEqual((root/p).read_bytes(),b,str(p))
        r110 = root / "nox-control/b2-r110/reported_review.cjs"
        fixture = FrozenOrderedCallsite("test_frozen_ordered_callsite")
        self.addCleanup(fixture.doCleanups)
        reached = []
        def run(args, *a, **kw):
            if len(args) > 3 and args[0:2] == ["node", "-e"] and str(args[3]).endswith("/joint_frozen.cjs"):
                reached.append(True)
                return actual(["node","-e",JS,str(module),str(r110)], *a, **kw)
            return actual(args,*a,**kw)
        with patch("subprocess.run", side_effect=run):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
