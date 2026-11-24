"""Regression of the exact R83/R81/R79 boundary, with a synthetic ingress.
Run with PYTHONPATH containing d3-r83, b2-r81, b2-r79, and b2-r84.
The lower-level R78 review and failed-attempt classifier are mocked, not native.
"""
import hashlib
import importlib
import json
import os
import tempfile
import types
import unittest
from contextlib import ExitStack
from unittest.mock import patch


class FinalFeedback(unittest.TestCase):
    def test_feedback_window(self):
        with ExitStack() as stack:
            fds = [stack.enter_context(tempfile.TemporaryFile()) for _ in range(6)]
            for fd in fds:
                fd.write(b"initial"); fd.flush()
            descriptors = tuple((fds[i].fileno(), fds[i+1].fileno(), "a", "b")
                                for i in (0, 2, 4))
            decisions = [dict(turn=2, answer_sha256="a"*64, verdict="correct", reason="Исправлено"),
                         dict(turn=3, answer_sha256="b"*64, verdict="uncertain", reason="Faltan datos")]
            raw = json.dumps(dict(decisions=decisions)).encode()
            pin = hashlib.sha256(raw).hexdigest()
            inputs = dict(descriptor_sets=descriptors, submission_a_raw=raw, submission_a_pin=pin,
                          submission_b_raw=raw, submission_b_pin=pin)
            def ingress(**kw):
                return dict(review_summary=dict(submission_sha256=[pin,pin], decisions_bound=4,
                                                rubric_sha256="c"*64, readback_sha256="d"*64))
            def read_pinned(data, digest):
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                return json.loads(data)
            stubs = dict(retained_snapshot_review=types.SimpleNamespace(verify_joint_reviews=ingress),
                         b2_existing_dialog_review=types.SimpleNamespace(read_pinned=read_pinned),
                         b5_bound_failed_poststate=types.SimpleNamespace(classify_bound_failed_turn=lambda **kw: "HOLD_SYNTHETIC"),
                         review_release=types.SimpleNamespace())
            names = ("quality_closure", "review_feedback", "outcome_review", "final_feedback")
            import sys
            with patch.dict(sys.modules, stubs):
                for name in names:
                    sys.modules.pop(name, None)
                closure = importlib.import_module("quality_closure")
                stubs["review_release"].verify_joint_reviews = closure.verify_joint_reviews
                feedback = importlib.import_module("review_feedback")
                router = importlib.import_module("outcome_review")
                fixed = importlib.import_module("final_feedback")
                clean = fixed.route_closed_review(outcome="completed", review_inputs=inputs)
                self.assertEqual(clean["route"], "REVIEW_DATA_ONLY")
                self.assertEqual(len(clean["quality_sample"]["correction_evidence"]["entries"]), 4)
                def mutate(data, digest):
                    os.write(fds[0].fileno(), b"x")
                    return read_pinned(data, digest)
                with patch.object(feedback, "read_pinned", mutate):
                    self.assertEqual(router.route_review(outcome="completed", review_inputs=inputs)["route"],
                                     "REVIEW_DATA_ONLY")  # reproduces gap after R79 returns
                    held = fixed.route_closed_review(outcome="completed", review_inputs=inputs)
                    self.assertEqual(held["reason"], "HOLD_B2_FINAL_FEEDBACK_FD_DRIFT")
                    self.assertIsNone(held["quality_sample"])
                    for flag in ("retry_allowed", "next_post_allowed", "training_admitted", "native_accepted"):
                        self.assertFalse(held[flag])
                self.assertEqual(fixed.route_closed_review(outcome="failed", review_inputs=inputs,
                                    failed_attempt={})["reason"], "HOLD_SYNTHETIC")
                self.assertEqual(fixed.route_closed_review(outcome="completed", review_inputs={})["reason"],
                                 "HOLD_B2_FINAL_FEEDBACK_FD_UNPROVEN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
