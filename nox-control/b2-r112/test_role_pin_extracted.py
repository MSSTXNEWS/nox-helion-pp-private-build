"""Actual R110 packet fixture on immutable extracted bytes, not a native quality grade."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from stage_verdict import stage_verdict, blob
from test_frozen_ordered import FrozenOrderedCallsite

JS = r"""
const fs=require('node:fs'),a=require('node:assert/strict'),{createHash}=require('node:crypto');
const {checkReviewRolePins:check}=require(process.argv[1]);
const {checkReportedVerdicts:old}=require(process.argv[2]);
const {makeReportedReview:make}=require(process.argv[3]);
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8');
const hash=x=>createHash('sha256').update(x).digest('hex');
function invoke(mutate){
 const doc=JSON.parse(d.packet),s=doc.review.quality_sample.review_summary;
 if(mutate)mutate(s);
 const packet=JSON.stringify(doc),pin=hash(Buffer.from(packet,'utf8'));
 const e={packet_sha256:pin,payload_sha256:d.detached_fixture_pin,host:{...d.host,packet_sha256:pin,quality:doc.review}};
 let reads=0;
 const result=make(()=>{reads++;return e})(bytes,packet);
 a.equal(reads,1);a.equal(result.status,'MATCHED_FROZEN_ORDERED_OFFLINE',JSON.stringify(result));
 a.equal(old(result),result);
 a.equal(result.reported_review_diagnostics.packet_sha256,pin);
 const out=check(result);
 for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])a.equal(out[k],false);
 return {result,out};
}
const good=invoke();
a.equal(good.out,good.result);
a.equal(good.out.reported_review_diagnostics.summary,'INCORRECT_REPORTED_UNVERIFIED');
a.deepEqual(good.out.reported_review_diagnostics.disagreements,[3]);
let rejected=0;
for(let i=0;i<2;i++)for(let j=0;j<3;j++){
 const {out}=invoke(s=>{s.submission_sha256[i]=[s.rubric_sha256,...s.readback_sha256][j]});
 a.equal(out.status,'HOLD_REPORTED_REVIEW_ROLE_PIN');
 a.equal(out.reported_review_diagnostics,null);
 a.equal(out.offline_metrics,undefined);
 rejected++;
}
const missing=make()(bytes,d.packet);a.equal(check(missing),missing);
a.equal(rejected,6);
for(const p of Object.keys(require.cache))a.ok(p.startsWith(require('node:path').resolve(process.argv[1],'../../..')+require('node:path').sep),p);
console.log('B2 role-pin actual extracted R110 fixture: 1 positive, 6 cross-role HOLD, 1 missing-provider HOLD; one provider read per valid packet; no native authority');
"""

class RolePinExtracted(unittest.TestCase):
    def test_role_pin_extracted(self):
        root = Path(os.environ["B2_STAGE_ROOT"]).resolve()
        before = {p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
        verdict = stage_verdict(root)
        candidate = verdict.with_name("candidate.cjs")
        raw = Path(__file__).with_name("candidate.cjs").read_bytes()
        self.assertEqual(blob(raw), "8af0944cb5dcc33b9f1433c2dd9b80fcddb50ebf")
        with candidate.open("xb") as f:
            f.write(raw)
        self.assertEqual(set(p.relative_to(root) for p in root.rglob("*") if p.is_file())-set(before), {candidate.relative_to(root), verdict.relative_to(root)})
        for p,b in before.items():
            self.assertEqual((root/p).read_bytes(),b,str(p))
        actual=subprocess.run
        fixture=FrozenOrderedCallsite("test_frozen_ordered_callsite")
        self.addCleanup(fixture.doCleanups)
        reached=[]
        def run(args,*a,**kw):
            if len(args)>3 and args[:2]==["node","-e"] and str(args[3]).endswith("/joint_frozen.cjs"):
                reached.append(True)
                return actual(["node","-e",JS,str(candidate),str(verdict),str(root/"nox-control/b2-r110/reported_review.cjs")],*a,**kw)
            return actual(args,*a,**kw)
        with patch("subprocess.run",side_effect=run):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
