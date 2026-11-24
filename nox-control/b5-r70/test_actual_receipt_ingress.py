"""Actual R86 and B5 retained-chain regression. Synthetic evidence; no mocks/POST."""
import unittest
from receipted_outcome import review_attempt
from test_b5_bound_failed_poststate import BoundPendingTests
from test_b5_chain_guard import checkpoint, raw, sha

class ActualReceiptIngress(unittest.TestCase):
    def check_hold(self, outcome, evidence, reason):
        result = review_attempt(outcome=outcome, review_inputs={"stale": True},
                                failed_attempt=evidence)
        self.assertEqual(result["route"], "HOLD")
        self.assertEqual(result["reason"], reason)
        self.assertIsNone(result["quality_sample"])
        for flag in ("retry_allowed", "next_post_allowed", "training_admitted", "native_accepted"):
            self.assertIs(result[flag], False)

    def test_real_retained_chain_pending_and_receipt(self):
        for n in (1, 2):
            rows = checkpoint(n+1)[0][:-1]
            evidence = BoundPendingTests().args(n, rows)
            doc = dict(schema="nox.s03.failed-attempt-binding.v1",
                       **{k:evidence[k] for k in ("dialog_id","session_id","attempt_id","snapshot_sha256")},
                       user_message_id=rows[-1]["message_id"])
            wire = raw(doc)
            valid = dict(evidence, admission_raw=wire, admission_sha256=sha(wire))
            foreign = raw(dict(doc, user_message_id="foreign-id"))
            wrong_scope = raw(dict(doc, attempt_id="another-attempt"))
            for outcome in ("failed", "uncertain"):
                for supplied, expected in (
                    (valid, "HOLD_S03_FAILURE_PENDING_USER"),
                    (evidence, "HOLD_S03_FAILURE_ADMISSION_PIN"),
                    (dict(valid, admission_sha256="0"*64), "HOLD_S03_FAILURE_ADMISSION_PIN"),
                    (dict(valid, expected_user_message_id=doc["user_message_id"]), "HOLD_S03_FAILURE_EVIDENCE_SCHEMA"),
                    (dict(valid, admission_raw=foreign, admission_sha256=sha(foreign)), "HOLD_S03_FAILURE_PENDING_ID_MISMATCH"),
                    (dict(valid, admission_raw=wrong_scope, admission_sha256=sha(wrong_scope)), "HOLD_S03_FAILURE_ADMISSION_SCOPE"),
                ):
                    with self.subTest(turn=n+1, outcome=outcome, expected=expected):
                        self.check_hold(outcome, supplied, expected)

    def test_actual_prefix_and_unexpected_rows(self):
        for n in (1, 2):
            prefix = BoundPendingTests().args(n, checkpoint(n)[0])
            extra = BoundPendingTests().args(n, checkpoint(n+1)[0])
            changed = checkpoint(n+1)[0][:-1]
            changed[0]["content"] = "Переписано / cambiado"
            drift = BoundPendingTests().args(n, changed)
            for outcome in ("failed", "uncertain"):
                self.check_hold(outcome, prefix, "HOLD_S03_FAILURE_PREFIX_INTACT")
                self.check_hold(outcome, extra, "HOLD_S03_FAILURE_UNEXPECTED_ROWS")
                self.check_hold(outcome, drift, "HOLD_S03_FAILURE_PREFIX_CHANGED")
                self.check_hold(outcome, dict(prefix, prior_chain=()), "HOLD_S03_FAILURE_PREFIX")
            self.check_hold("completed", prefix, "HOLD_D3_CONTRADICTORY_ATTEMPT")
