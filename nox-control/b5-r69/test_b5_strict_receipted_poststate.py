import unittest
from test_b5_chain_guard import checkpoint, raw, sha
from test_b5_receipted_failed_poststate import ReceiptTests
from test_b5_bound_failed_poststate import BoundPendingTests
from b5_receipted_failed_poststate import classify_receipted_failed_turn
from b5_strict_receipted_poststate import classify_strict_receipted_failed_turn as strict

class StrictReceiptTests(unittest.TestCase):
    def test_actual_r68_bare_id_bypass(self):
        for n in (1, 2):
            evidence, doc = ReceiptTests().fixture(n)
            injected = dict(evidence, expected_user_message_id=doc["user_message_id"])
            self.assertEqual(classify_receipted_failed_turn(**injected),
                             "HOLD_S03_FAILURE_PENDING_USER")
            self.assertEqual(strict(**injected), "HOLD_S03_FAILURE_EVIDENCE_SCHEMA")
            self.assertEqual(strict(admission_raw=raw(doc), admission_sha256=sha(raw(doc)),
                                    **injected), "HOLD_S03_FAILURE_EVIDENCE_SCHEMA")

    def test_receipt_required_and_valid(self):
        for n in (1, 2):
            evidence, doc = ReceiptTests().fixture(n)
            self.assertEqual(strict(**evidence), "HOLD_S03_FAILURE_ADMISSION_PIN")
            wire = raw(doc)
            self.assertEqual(strict(admission_raw=wire, admission_sha256=sha(wire),
                                    **evidence), "HOLD_S03_FAILURE_PENDING_USER")
            self.assertEqual(strict(admission_raw=wire, admission_sha256="0"*64,
                                    **evidence), "HOLD_S03_FAILURE_ADMISSION_PIN")

    def test_schema_and_nonpending(self):
        for n in (1, 2):
            evidence, _ = ReceiptTests().fixture(n)
            self.assertEqual(strict(**dict(evidence, extra=True)),
                             "HOLD_S03_FAILURE_EVIDENCE_SCHEMA")
            for key in tuple(evidence):
                self.assertEqual(strict(**{k:v for k,v in evidence.items() if k != key}),
                                 "HOLD_S03_FAILURE_EVIDENCE_SCHEMA")
            intact = BoundPendingTests().args(n, checkpoint(n)[0])
            self.assertEqual(strict(**intact), "HOLD_S03_FAILURE_PREFIX_INTACT")
            extra = BoundPendingTests().args(n, checkpoint(n+1)[0])
            self.assertEqual(strict(**extra), "HOLD_S03_FAILURE_UNEXPECTED_ROWS")
