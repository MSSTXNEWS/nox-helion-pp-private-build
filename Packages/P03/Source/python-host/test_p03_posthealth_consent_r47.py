"""Bound request/scope must survive the final backend readiness callback.

Run with `python -m unittest -v test_p03_posthealth_consent_r47` in the real
P03 Python source directory. No Ollama, model weights, network or host needed.
"""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortDenied


class HealthProbeRaceR47(unittest.TestCase):
    def run_case(self, mutation):
        session = SimpleNamespace(tenant="tenant", principal="owner", chat_id="c",
                                  allowed={"models.pull"}, private_approved={"models.pull"})
        args = {"modelTag": "verified:latest", "options": {"mode": "safe"}}
        class Backend:
            def __init__(self):
                self.health_calls = 0
                self.actions = 0
            def available(self):
                self.health_calls += 1
                if self.health_calls == 2:
                    mutation(session, args)
                return True
            def pull(self, _session, _args):
                self.actions += 1
                return {"accepted": True}
        backend = Backend()
        port = object.__new__(P03OneHostPort)
        port.backend = backend
        port.native_approve = lambda *_: True
        return port, session, args, backend

    def test_unchanged_approved_payload_executes_once(self):
        port, session, args, backend = self.run_case(lambda *_: None)
        self.assertEqual(port.execute_backend(session, "models.pull", args), {"accepted": True})
        self.assertEqual(backend.actions, 1)

    def test_health_probe_mutating_nested_payload_denied_without_queue(self):
        def alter(_session, args):
            args["options"]["mode"] = "dangerous"
        port, session, args, backend = self.run_case(alter)
        with self.assertRaises(P03PortDenied):
            port.execute_backend(session, "models.pull", args)
        self.assertEqual(backend.actions, 0)

    def test_health_probe_revoking_permission_denied_without_queue(self):
        def revoke(session, _args):
            session.private_approved.clear()
        port, session, args, backend = self.run_case(revoke)
        with self.assertRaises(P03PortDenied):
            port.execute_backend(session, "models.pull", args)
        self.assertEqual(backend.actions, 0)


if __name__ == "__main__":
    unittest.main()
