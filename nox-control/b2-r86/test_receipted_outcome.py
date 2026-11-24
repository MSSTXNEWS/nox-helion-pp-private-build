"""Boundary regression, synthetic pending rows; no native admission."""
import hashlib
import json
import unittest
from unittest.mock import patch
import b5_bound_failed_poststate as bound
import receipted_outcome as new
from integrated_outcome import review_attempt as old


def raw(obj):
    return json.dumps(obj, ensure_ascii=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReceiptIngress(unittest.TestCase):
    def test_failed_attempt_cannot_use_bare_id_or_enter_quality(self):
        for n, prompt in ((2, "Уточни бюджет"), (3, "¿Qué falta?")):
            mid = f"user-{n}"
            snapshot = raw({"messages": [{"message_id": mid}]})
            evidence = dict(dialog_id="dialog", session_id="session", attempt_id=f"attempt-{n}",
                            prompt=prompt, prior_chain=(), snapshot_raw=snapshot,
                            snapshot_sha256=sha(snapshot))
            receipt = raw(dict(schema="nox.s03.failed-attempt-binding.v1", dialog_id="dialog",
                               session_id="session", attempt_id=f"attempt-{n}",
                               snapshot_sha256=sha(snapshot), user_message_id=mid))
            bare = dict(evidence, expected_user_message_id=mid)
            with patch.object(bound, "classify_failed_turn", return_value="HOLD_S03_FAILURE_PENDING_USER"):
                self.assertEqual(old(outcome="failed", failed_attempt=bare)["reason"],
                                 "HOLD_S03_FAILURE_PENDING_USER")
                cases = [(bare, "HOLD_S03_FAILURE_EVIDENCE_SCHEMA"),
                         (evidence, "HOLD_S03_FAILURE_ADMISSION_PIN"),
                         (dict(evidence, admission_raw=receipt, admission_sha256="0"*64),
                          "HOLD_S03_FAILURE_ADMISSION_PIN"),
                         (dict(evidence, admission_raw=receipt, admission_sha256=sha(receipt)),
                          "HOLD_S03_FAILURE_PENDING_USER")]
                for args, expected in cases:
                    for outcome in ("failed", "uncertain"):
                        result = new.review_attempt(outcome=outcome, review_inputs={"stale": True},
                                                    failed_attempt=args)
                        self.assertEqual(result["reason"], expected)
                        self.assertEqual(result["route"], "HOLD")
                        self.assertIsNone(result["quality_sample"])
                        for flag in ("retry_allowed", "next_post_allowed", "training_admitted", "native_accepted"):
                            self.assertFalse(result[flag])

    def test_completed_and_other_outcomes_preserve_r85(self):
        envelope = {"descriptor_sets": "opaque"}
        sentinel = object()
        for outcome in ("completed", "unknown", None):
            with patch.object(new, "review_r85", return_value=sentinel) as delegate:
                self.assertIs(new.review_attempt(outcome=outcome, review_inputs=envelope), sentinel)
                delegate.assert_called_once_with(outcome=outcome, review_inputs=envelope, failed_attempt=None)
        result = new.review_attempt(outcome="completed", review_inputs=envelope, failed_attempt={})
        self.assertEqual(result["reason"], "HOLD_D3_CONTRADICTORY_ATTEMPT")


if __name__ == "__main__":
    unittest.main()
