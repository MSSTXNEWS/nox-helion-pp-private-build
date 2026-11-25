import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from stage_role_pin import stage_role_pin, blob, REL, SOURCE, CANDIDATE, VERDICT


class StageRolePin(unittest.TestCase):
    def test_stage_and_consume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / REL
            target.mkdir(parents=True)
            verdict = target / 'verdict_consistency.cjs'
            raw = (SOURCE.parent / verdict.name).read_bytes()
            self.assertEqual(blob(raw), VERDICT)
            verdict.write_bytes(raw)
            dst = stage_role_pin(root)
            self.assertEqual(blob(dst.read_bytes()), CANDIDATE)
            self.assertEqual(verdict.read_bytes(), raw)
            with self.assertRaises(ValueError):
                stage_role_pin(root)
            self.assertEqual(blob(dst.read_bytes()), CANDIDATE)
            result = subprocess.run(['node', '-e', '''
const assert=require('node:assert/strict');
const {checkReviewRolePins:check}=require(process.argv[1]);
const p=n=>String(n).repeat(64);
const d={status:'REPORTED_UNVERIFIED_DATA_ONLY',decisions_bound:4,
 disagreements:[],reported_incorrect:[],reported_uncertain:[],
 rubric_sha256:p(1),readback_sha256:[p(2),p(3)],submission_sha256:[p(4),p(5)]};
const r={status:'MATCHED_FROZEN_ORDERED_OFFLINE',reported_review_diagnostics:d,native_accepted:false};
assert.equal(check(r),r);
for(const pin of [p(1),p(2),p(3)])for(const i of [0,1]){
 const a=[...d.submission_sha256];a[i]=pin;
 const h=check({...r,reported_review_diagnostics:{...d,submission_sha256:a}});
 assert.equal(h.status,'HOLD_REPORTED_REVIEW_ROLE_PIN');
 assert.equal(h.native_accepted,false);
}
console.log(JSON.stringify({positive:1,aliases_rejected:6}));
''', str(dst)], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), {'positive': 1, 'aliases_rejected': 6})
            dst.unlink()
            verdict.write_bytes(raw + b'\n')
            with self.assertRaises(ValueError):
                stage_role_pin(root)
            self.assertFalse(dst.exists())
            verdict.unlink()
            with self.assertRaises(ValueError):
                stage_role_pin(root)
            self.assertFalse(dst.exists())
            verdict.symlink_to(SOURCE.parent / verdict.name)
            with self.assertRaises(ValueError):
                stage_role_pin(root)
            self.assertFalse(dst.exists())


if __name__ == '__main__':
    unittest.main()
