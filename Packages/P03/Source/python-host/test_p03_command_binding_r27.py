"""Actual P03 module command/consent regressions; native callbacks are fixtures."""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortDenied, P03PortHold


class CommandBindingR27(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace(tenant="t", principal="p", chat_id="c",
            allowed=frozenset({"models.pull"}), private_approved=frozenset({"models.pull"}))
        self.calls = []
        self.port = object.__new__(P03OneHostPort)
        self.port.native_approve = lambda s, r, p: True
        self.port.backend = SimpleNamespace(available=lambda: True,
            pull=lambda s, p: self.calls.append(p) or {"queued": True})
        self.payload = {"modelTag": "qwen3:4b", "proof": {"sha": "a" * 64}}

    def test_mutating_approved_model_rejected(self):
        def approve(s, r, p):
            p["modelTag"] = "unapproved:latest"
            return True
        self.port.native_approve = approve
        with self.assertRaises(P03PortDenied):
            self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertEqual(self.calls, [])

    def test_mutating_nested_digest_rejected(self):
        def approve(s, r, p):
            p["proof"]["sha"] = "b" * 64
            return True
        self.port.native_approve = approve
        with self.assertRaises(P03PortDenied):
            self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertEqual(self.calls, [])

    def test_payload_retained_by_callback_cannot_change_execution(self):
        held = []
        self.port.native_approve = lambda s, r, p: held.append(p) or True
        def probe():
            held[0]["proof"]["sha"] = "b" * 64
            return True
        self.port.backend.available = probe
        with self.assertRaises(P03PortDenied):
            self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertEqual(self.calls, [])

    def test_original_caller_payload_detached_before_native_callback(self):
        def approve(s, r, p):
            self.payload["modelTag"] = "unapproved:latest"
            return True
        self.port.native_approve = approve
        self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertEqual(self.calls[0]["modelTag"], "qwen3:4b")

    def test_invalid_json_never_reaches_consent_or_backend(self):
        invalid = [{"x": float("nan")}, {"x": float("inf")}, {1: "coerced"},
                   {"x": (1, 2)}, {"x": "a" * 65537}, {"x": "\ud800"}]
        deep = {}
        for _ in range(40): deep = {"x": deep}
        invalid.append(deep)
        circular = {}; circular["self"] = circular; invalid.append(circular)
        seen = []
        self.port.native_approve = lambda *a: seen.append(a) or True
        for payload in invalid:
            with self.subTest(payload_type=type(payload).__name__):
                with self.assertRaises(P03PortDenied):
                    self.port.execute_backend(self.session, "models.pull", payload)
        self.assertFalse(seen)
        self.assertFalse(self.calls)

    def test_native_identity_change_rejected_before_backend(self):
        def approve(s, r, p):
            s.principal = "other"
            return True
        self.port.native_approve = approve
        with self.assertRaises(P03PortDenied):
            self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertFalse(self.calls)

    def test_revocation_during_health_probe_rejected(self):
        def probe():
            self.session.allowed = frozenset()
            return True
        self.port.backend.available = probe
        with self.assertRaises(P03PortDenied):
            self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertFalse(self.calls)

    def test_valid_nested_json_and_native_denial_preserved(self):
        self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertEqual(self.calls, [self.payload])
        self.assertIsNot(self.calls[0], self.payload)
        self.assertIsNot(self.calls[0]["proof"], self.payload["proof"])
        self.port.native_approve = lambda *args: False
        with self.assertRaises(P03PortDenied):
            self.port.execute_backend(self.session, "models.pull", self.payload)
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
