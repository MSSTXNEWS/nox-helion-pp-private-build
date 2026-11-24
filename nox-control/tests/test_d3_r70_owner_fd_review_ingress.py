"""Exact cross-source descriptor integration, synthetic artifacts only."""
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from d3_r70_owner_fd_review_ingress import prepare_descriptor_review, verify_descriptor_reviews
from test_b2_r69_strict_review_ingress import inputs, mutate
from test_d3_r68_review_binding import raw, digest


class DescriptorIntegration(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

    def artifact(self, data):
        f = self.stack.enter_context(tempfile.TemporaryFile())
        f.write(data)
        f.flush()
        f.seek(1)
        return f.fileno()

    def args(self, base=None):
        base = inputs() if base is None else base
        descriptors = []
        for name in ("prior_witnesses", "turn2_witnesses", "turn3_witnesses"):
            w, r, wp, rp = base[name]
            descriptors.append((self.artifact(w), self.artifact(r), wp, rp))
        return dict(descriptor_sets=tuple(descriptors), **{
            k: base[k] for k in ("dialog_id", "session_id", "rubric_raw", "rubric_pin",
                                 "pair_raw", "pair_pin")})

    def test_complete_descriptor_review_and_closure(self):
        args = self.args()
        result = prepare_descriptor_review(**args)
        self.assertTrue(result["native_acceptance"].startswith("HOLD"))
        self.assertEqual(result["review_packet"]["readback_sha256"],
                         [x[3] for x in args["descriptor_sets"][1:]])
        submissions = {}
        for side in ("a", "b"):
            doc = copy.deepcopy(result["review_packet"]["submission"])
            doc["reviewer_id"] = "fixture-" + side
            for row in doc["decisions"]:
                row.update(verdict="correct", reason="Synthetic fixture only")
            data = raw(doc)
            submissions.update({f"submission_{side}_raw": data,
                                f"submission_{side}_pin": digest(data)})
        final = verify_descriptor_reviews(**args, **submissions)
        self.assertEqual(final["review_summary"]["decisions_bound"], 4)
        self.assertFalse(final["review_summary"]["reviewer_identity_verified"])
        for pair in args["descriptor_sets"]:
            for fd in pair[:2]:
                self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 1)
        sets = list(args["descriptor_sets"])
        w, r, wp, rp = sets[2]
        sets[2] = (w, r, wp, "0"*64)
        with self.assertRaisesRegex(ValueError, "ARTIFACT_PIN"):
            verify_descriptor_reviews(**dict(args, descriptor_sets=tuple(sets)), **submissions)

    def test_cross_pair_descriptor_alias(self):
        args = self.args()
        sets = list(args["descriptor_sets"])
        w, r, wp, rp = sets[2]
        alias = os.dup(sets[0][0])
        self.stack.callback(os.close, alias)
        sets[2] = (alias, r, wp, rp)
        with self.assertRaisesRegex(ValueError, "DESCRIPTOR_ALIAS"):
            prepare_descriptor_review(**dict(args, descriptor_sets=tuple(sets)))

    def test_nonadjacent_event_or_turn_reuse(self):
        for key, value in (("event_id", "event-1"), ("turn_id", "turn-1")):
            base = inputs()
            base["turn3_witnesses"] = mutate(
                mutate(base["turn3_witnesses"], 0, **{key:value}), 1, **{key:value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "NONADJACENT_ID_REUSE"):
                prepare_descriptor_review(**self.args(base))


if __name__ == "__main__":
    unittest.main(verbosity=2)
