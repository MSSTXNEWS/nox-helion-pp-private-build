import unittest
from test_b5_chain_guard import checkpoint, DIALOG, SESSION, raw, sha
from test_b5_bound_failed_poststate import BoundPendingTests
from b5_bound_failed_poststate import classify_bound_failed_turn
from b5_receipted_failed_poststate import classify_receipted_failed_turn

class ReceiptTests(unittest.TestCase):
    def fixture(self, n):
        rows = checkpoint(n+1)[0][:-1]
        evidence = BoundPendingTests().args(n, rows)
        doc = dict(schema="nox.s03.failed-attempt-binding.v1",
                   dialog_id=DIALOG, session_id=SESSION,
                   attempt_id=evidence["attempt_id"],
                   snapshot_sha256=evidence["snapshot_sha256"],
                   user_message_id=rows[-1]["message_id"])
        return evidence, doc

    def run_receipt(self, evidence, doc):
        wire = raw(doc)
        return classify_receipted_failed_turn(admission_raw=wire,
                 admission_sha256=sha(wire), **evidence)

    def test_exact_and_missing(self):
        for n in (1, 2):
            evidence, doc = self.fixture(n)
            self.assertEqual(classify_bound_failed_turn(
                expected_user_message_id=doc["user_message_id"], **evidence),
                "HOLD_S03_FAILURE_PENDING_USER")
            self.assertEqual(classify_receipted_failed_turn(**evidence),
                "HOLD_S03_FAILURE_ADMISSION_PIN")
            self.assertEqual(self.run_receipt(evidence, doc),
                "HOLD_S03_FAILURE_PENDING_USER")

    def test_stale_or_foreign_receipt(self):
        for n in (1, 2):
            evidence, doc = self.fixture(n)
            for key, value in (("attempt_id", "other"), ("session_id", "other"),
                               ("dialog_id", "other"), ("snapshot_sha256", "a"*64),
                               ("schema", "v0")):
                self.assertEqual(self.run_receipt(evidence, dict(doc, **{key:value})),
                    "HOLD_S03_FAILURE_ADMISSION_SCOPE", key)
            self.assertEqual(self.run_receipt(evidence, dict(doc, user_message_id="other")),
                "HOLD_S03_FAILURE_PENDING_ID_MISMATCH")

    def test_bad_detached_pin_and_malformed(self):
        evidence, doc = self.fixture(1)
        self.assertEqual(classify_receipted_failed_turn(admission_raw=raw(doc),
             admission_sha256="0"*64, **evidence), "HOLD_S03_FAILURE_ADMISSION_PIN")
        malformed = b'{"schema":"a","schema":"b"}'
        self.assertEqual(classify_receipted_failed_turn(admission_raw=malformed,
             admission_sha256=sha(malformed), **evidence), "HOLD_S03_FAILURE_ADMISSION_INVALID")
        self.assertEqual(self.run_receipt(evidence, dict(doc, extra=True)),
             "HOLD_S03_FAILURE_ADMISSION_SCOPE")

    def test_preserve_nonpending(self):
        for n in (1, 2):
            evidence = BoundPendingTests().args(n, checkpoint(n)[0])
            self.assertEqual(classify_receipted_failed_turn(**evidence),
                "HOLD_S03_FAILURE_PREFIX_INTACT")
            evidence = BoundPendingTests().args(n, checkpoint(n+1)[0])
            self.assertEqual(classify_receipted_failed_turn(**evidence),
                "HOLD_S03_FAILURE_UNEXPECTED_ROWS")
