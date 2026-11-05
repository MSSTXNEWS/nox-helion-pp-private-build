"""P03 native owner ACKs must be real non-ambiguous receipts, never placeholder JSON."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[2] / "Packages" / "P03" / "Source"
          / "python-host" / "p03_onehost_port.py")
spec = importlib.util.spec_from_file_location("original_p03_onehost_ack", SOURCE)
assert spec and spec.loader
p03 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p03)


class Backend:
    def __init__(self, receipt):
        self.receipt = receipt
        self.calls = 0

    def available(self):
        return True

    def pull(self, session, args):
        self.calls += 1
        return self.receipt

    def import_gguf(self, session, args):
        return self.pull(session, args)

    def cancel(self, session, args):
        return self.pull(session, args)

    def retry(self, session, args):
        return self.pull(session, args)


class P03BackendAckReceiptTest(unittest.TestCase):
    def invoke(self, receipt, route="models.pull"):
        port = p03.P03OneHostPort.__new__(p03.P03OneHostPort)
        backend = Backend(receipt)
        port.backend = backend
        port.native_approve = lambda session, route, payload: True
        session = SimpleNamespace(tenant="t", principal="p", chat_id="c",
                                  allowed={route}, private_approved={route})
        payload = ({"jobId": "j1"} if route in ("models.cancel", "models.retry")
                   else {"modelTag": "safe:7b"})
        return port.execute_backend(session, route, payload), backend

    def test_ambiguous_receipts_hold(self):
        invalid = ({}, {"ok": "false"}, {"ok": 0}, {"ok": None},
                   {"status": None}, {"status": 0}, {"status": " "},
                   {"ok": False}, {"status": "HOLD_LICENSE"},
                   {"status": "ERROR_REMOTE"})
        for receipt in invalid:
            with self.subTest(receipt=receipt):
                with self.assertRaises(p03.P03PortHold):
                    self.invoke(receipt)

    def test_explicit_native_denials_cannot_be_success_acks(self):
        denied = (
            {"ok": True, "error": "LICENSE_REVOKED"},
            {"error": {"code": "STOP_PENDING"}},
            {"accepted": False, "status": "QUEUED"},
            {"success": False, "jobId": "j1"},
            {"ack": 1, "status": "QUEUED"},
            {"status": "REVIEW_REQUIRED"},
            {"status": "CONSENT_REQUIRED"},
            {"status": "NOT_AUTHORIZED"},
            {"status": "STOP_PENDING"},
            {"status": "BUSY"},
            {"status": "NOT_READY"},
        )
        for receipt in denied:
            with self.subTest(receipt=receipt):
                with self.assertRaises(p03.P03PortHold):
                    self.invoke(receipt)

    def test_metadata_only_result_is_not_mutating_owner_ack(self):
        for route in ("models.pull", "models.gguf.import",
                      "models.cancel", "models.retry"):
            for receipt in ({"jobId": "j1"},
                            {"jobId": "j1", "metadata": "not-an-ack"},
                            {"jobId": "j1", "queued": False}):
                with self.subTest(route=route, receipt=receipt):
                    with self.assertRaisesRegex(p03.P03PortHold,
                                                "no affirmative job acknowledgement"):
                        self.invoke(receipt, route=route)

    def test_cancel_retry_positive_ack_and_identity_kept(self):
        for route, status in (("models.cancel", "CANCEL_REQUESTED"),
                              ("models.retry", "QUEUED")):
            with self.subTest(route=route):
                receipt = {"jobId": "j1", "status": status}
                self.assertEqual(self.invoke(receipt, route=route)[0], receipt)
                with self.assertRaises(p03.P03PortHold):
                    self.invoke({"jobId": "foreign", "status": status}, route=route)

    def test_positive_boolean_legacy_receipt_kept(self):
        for route in ("models.pull", "models.gguf.import"):
            with self.subTest(route=route):
                self.assertEqual(self.invoke({"ack": True}, route=route)[0],
                                 {"ack": True})

    def test_existing_positive_receipts_preserved(self):
        accepted = ({"ok": True}, {"status": "QUEUED", "jobId": "j1"},
                    {"queued": True, "jobId": "j2"},
                    {"ack": True, "status": "QUEUED"},
                    {"accepted": True, "status": "QUEUED"},
                    {"success": True, "status": "QUEUED"},
                    {"status": "QUEUED", "error": None})
        for receipt in accepted:
            with self.subTest(receipt=receipt):
                output, backend = self.invoke(receipt)
                self.assertEqual(output, receipt)
                self.assertEqual(backend.calls, 1)


if __name__ == "__main__":
    unittest.main()
