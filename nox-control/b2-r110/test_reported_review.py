"""Use the existing A3 fixture producer; only the final Node assertions change."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from test_frozen_ordered import FrozenOrderedCallsite

JS = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const {makeReportedReview:make}=require(process.argv[1]);
const {makeFrozenOrderedReview:baseline}=require(process.argv[2]);
const d=JSON.parse(fs.readFileSync(0,'utf8'));
for(const t of d.host.turns)for(const k of ['observation','reservation','disposition'])t.receipts[k]=Buffer.from(t.receipts[k],'utf8');
const bytes=Buffer.from(d.frozen,'utf8');
const evidence={packet_sha256:d.host.packet_sha256,payload_sha256:d.detached_fixture_pin,host:d.host};
const old=baseline(()=>evidence)(bytes,d.packet);
assert.equal(old.status,'MATCHED_FROZEN_ORDERED_OFFLINE');
assert.equal(old.reported_review_diagnostics,undefined);
const run=make(()=>evidence), out=run(bytes,d.packet), diag=out.reported_review_diagnostics;
assert.equal(out.status,old.status,JSON.stringify(out));
assert.equal(diag.status,'REPORTED_UNVERIFIED_DATA_ONLY');
assert.equal(diag.summary,'INCORRECT_REPORTED_UNVERIFIED');
assert.deepEqual(diag.disagreements,[3]);
assert.deepEqual(diag.reported_incorrect,[3]);
assert.deepEqual(diag.reported_uncertain,[3]);
const summary=JSON.parse(d.packet).review.quality_sample.review_summary;
for(const k of ['rubric_sha256','readback_sha256','submission_sha256'])assert.deepEqual(diag[k],summary[k]);
assert.equal(diag.packet_sha256,evidence.packet_sha256);
assert.equal(diag.frozen_payload_sha256,evidence.payload_sha256);
for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])assert.equal(out[k],false);
for(const k of ['reviewer_identity_verified','model_instruction','training_admitted','native_accepted'])assert.equal(diag[k],false);
assert.equal(out.quality_sample,null);assert.equal(out.metrics,null);
assert.equal(diag.entries,undefined);assert.equal(diag.reason,undefined);
assert.equal(make()(bytes,d.packet).reported_review_diagnostics,null);
assert.equal(run(Buffer.concat([bytes,Buffer.from(' ')]),d.packet).reported_review_diagnostics,null);
const altered=JSON.parse(d.packet);
altered.turns[0].disposition[0]=altered.turns[0].disposition[0].replace('FINALIZED','ABORTED');
assert.equal(run(bytes,JSON.stringify(altered)).reported_review_diagnostics,null);
console.log('R110: exact A3 fixture; diagnostic summary preserved, 3 HOLDs emit no review data; no authority');
"""

class ReportedReview(unittest.TestCase):
    def test_reported_review(self):
        actual = subprocess.run
        module = Path(__file__).with_name("reported_review.cjs")
        fixture = FrozenOrderedCallsite("test_frozen_ordered_callsite")
        self.addCleanup(fixture.doCleanups)
        reached = []
        def run(args, *a, **kw):
            if len(args) > 3 and args[0:2] == ["node", "-e"] and str(args[3]).endswith("/joint_frozen.cjs"):
                reached.append(True)
                return actual(["node","-e",JS,str(module),args[3]], *a, **kw)
            return actual(args,*a,**kw)
        with patch("subprocess.run", side_effect=run):
            fixture.test_frozen_ordered_callsite()
        self.assertEqual(reached,[True])
