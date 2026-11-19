"""3B05: ambiguous or nonfinite JSON cannot certify learned skill evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_dispatcher_mentor as mentor


class StrictSkillEvidenceTests(unittest.TestCase):
    def ranking(self, record_transform=None, marker_transform=None, nonfinite=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ids=root/'memory/dispatcher_mentor/accepted_ids';ids.mkdir(parents=True)
            (ids.parent/'ledger.lock').write_bytes(b'LOCK')
            target=root/'distill/queue/owner_verified_experience.jsonl'
            target.parent.mkdir(parents=True)
            proof={'kind':'native_verified_receipt','scope':'fixture'}
            if nonfinite: proof['measurement']=float('nan')
            group=mentor.digest({'task':'fixture-task','handler':'fixture-handler'})
            key=mentor.digest({'group':group,'verification':proof})
            row={'schema':'NOX_VERIFIED_EXPERIENCE_V1','partition':'train','accepted':True,
                 'task_id':'fixture-task','handler':'fixture-handler','verification':proof,
                 'group_sha256':group,'dedup_sha256':key}
            raw=json.dumps(row)
            if record_transform: raw=record_transform(raw)
            target.write_text(raw+'\n')
            marker=json.dumps({'partition':'train','target':str(target)})
            if marker_transform: marker=marker_transform(marker)
            (ids/key).write_text(marker)
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(mentor,'ROOT',root):
                try: return mentor.read_verified_skill_rankings()
                finally:
                    after={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    self.assertEqual(after,before,'read-side verification may not mutate history')

    def test_duplicate_accepted_key_does_not_become_verified(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_SKILL_RANK_CORRUPT'):
            self.ranking(record_transform=lambda raw:raw.replace('"accepted": true','"accepted": false, "accepted": true'))

    def test_duplicate_marker_partition_is_not_a_receipt(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_SKILL_RANK_MARKER_INVALID'):
            self.ranking(marker_transform=lambda raw:raw.replace('"partition": "train"','"partition": "holdout", "partition": "train"'))

    def test_nonfinite_proof_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_SKILL_RANK_CORRUPT'):
            self.ranking(nonfinite=True)

    def test_unique_finite_evidence_still_ranks_once(self):
        result=self.ranking()
        self.assertEqual(result['state'],'SOURCE_READ_ONLY_VERIFIED')
        self.assertEqual(result['unique_receipts'],1)
        self.assertEqual(result['rankings'][0]['verified_successes'],1)
        self.assertFalse(result['native_accepted'])


if __name__ == '__main__': unittest.main()
