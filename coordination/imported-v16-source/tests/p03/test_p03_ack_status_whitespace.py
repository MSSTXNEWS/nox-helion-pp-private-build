"""Fail closed on whitespace-/prefix-disguised native P03 refusal ACKs."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / "Packages" / "P03" /
          "Source" / "python-host" / "p03_onehost_port.py")
spec = importlib.util.spec_from_file_location("original_p03_whitespace_ack", SOURCE)
assert spec and spec.loader
p03 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p03)

class Backend:
    def __init__(self, receipt):
        self.receipt = receipt
    def available(self):
        return True
    def pull(self, session, args):
        return self.receipt

class WhitespaceNativeAckTest(unittest.TestCase):
    def invoke(self, receipt):
        port = p03.P03OneHostPort.__new__(p03.P03OneHostPort)
        port.backend = Backend(receipt)
        port.native_approve = lambda _session, _route, _args: True
        session = SimpleNamespace(
            tenant="t", principal="p", chat_id="c",
            allowed={"models.pull"}, private_approved={"models.pull"})
        return port.execute_backend(session, "models.pull", {"modelTag": "safe:7b"})

    def test_native_refusal_status_never_success(self):
        for status in (" HOLD_LICENSE", "\nERROR_UPSTREAM", "FAILED ",
                       "\tDENIED\n", " Rejected "):
            with self.subTest(status=status):
                with self.assertRaises(p03.P03PortHold):
                    self.invoke({"status": status})

    def test_existing_positive_ack_preserved(self):
        for receipt in ({"ok": True}, {"status": "QUEUED", "jobId": "j1"},
                        {"status": "CANCELLED", "jobId": "j2"}):
            with self.subTest(receipt=receipt):
                self.assertEqual(self.invoke(receipt), receipt)

if __name__ == "__main__":
    unittest.main()
