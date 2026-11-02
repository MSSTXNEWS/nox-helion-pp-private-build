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


class P03BackendAckReceiptTest(unittest.TestCase):
    def invoke(self, receipt):
        port = p03.P03OneHostPort.__new__(p03.P03OneHostPort)
        backend = Backend(receipt)
        port.backend = backend
        port.native_approve = lambda session, route, payload: True
        session = SimpleNamespace(tenant="t", principal="p", chat_id="c",
                                  allowed={"models.pull"},
                                  private_approved={"models.pull"})
        return port.execute_backend(session, "models.pull", {"modelTag": "safe:7b"}), backend

    def test_ambiguous_receipts_hold(self):
        invalid = ({}, {"ok": "false"}, {"ok": 0}, {"ok": None},
                   {"status": None}, {"status": 0}, {"status": " "},
                   {"ok": False}, {"status": "HOLD_LICENSE"},
                   {"status": "ERROR_REMOTE"})
        for receipt in invalid:
            with self.subTest(receipt=receipt):
                with self.assertRaises(p03.P03PortHold):
                    self.invoke(receipt)

    def test_existing_positive_receipts_preserved(self):
        accepted = ({"ok": True}, {"status": "QUEUED", "jobId": "j1"},
                    {"queued": True, "jobId": "j2"})
        for receipt in accepted:
            with self.subTest(receipt=receipt):
                output, backend = self.invoke(receipt)
                self.assertEqual(output, receipt)
                self.assertEqual(backend.calls, 1)


if __name__ == "__main__":
    unittest.main()
