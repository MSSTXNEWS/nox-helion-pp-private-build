"""R18 P0/P1 source-only native mobile contract (no host/server/EXE)."""
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
from g2_space_mobile import PrivateMobileContract, G2Denied, G2Hold


class ExistingNativeHost:
    def __init__(self, now=100.0, expiry=200.0, received=b"a"*32):
        self.now, self.expiry, self.received = now, expiry, received
        self.calls, self.policies, self.live = 0, 0, True
        self.expire_at_final_advertise = False
        self.mutate_request = False
        self.request = {"want": ["space.news"]}

    def peer(self, _session):
        if self.mutate_request:
            self.request["want"][:] = ["chat.model"]
        return {"identity": "native-user", "verified_private_peer": True,
                "trusted_origin": "https://private.example",
                "observed_origin": "https://private.example",
                "expected_csrf": b"a"*32, "received_csrf": self.received,
                "native_session_approved": True, "expires_at": self.expiry}

    def policy(self, _identity, **_proof):
        self.policies += 1
        return True

    def advertise(self, _session):
        self.calls += 1
        if self.calls == 2 and self.expire_at_final_advertise:
            self.now = 201.0
        return {"space.news": {"enabled": True}, "chat.model": {"enabled": True}}

    def contract(self):
        return PrivateMobileContract(self.policy, self.peer, self,
                                     lambda: self.now,
                                     gateway_ready=lambda: self.live)


class MobileR18(unittest.TestCase):
    def test_expired_at_final_native_advertise_does_not_publish_allowed(self):
        host = ExistingNativeHost()
        host.expire_at_final_advertise = True
        with self.assertRaisesRegex(G2Denied, "expired before capability"):
            host.contract().connect(None, host.request)
        self.assertEqual(host.calls, 2)

    def test_bool_clock_rejected_before_owner_policy(self):
        host = ExistingNativeHost(now=True)
        with self.assertRaises(G2Hold):
            host.contract().connect(None, host.request)
        self.assertEqual(host.policies, 0)

    def test_nonfinite_clock_rejected_before_owner_policy(self):
        host = ExistingNativeHost(now=float("nan"))
        with self.assertRaises(G2Hold):
            host.contract().connect(None, host.request)
        self.assertEqual(host.policies, 0)

    def test_oversized_presented_csrf_short_circuits_compare_digest(self):
        host = ExistingNativeHost(received=b"z" * 100000)
        with patch("g2_space_mobile.hmac.compare_digest",
                   side_effect=AssertionError("oversized csrf compared")):
            with self.assertRaises(G2Denied):
                host.contract().connect(None, host.request)
        self.assertEqual(host.policies, 0)

    def test_previous_r17_immutable_request_lesson_applied(self):
        host = ExistingNativeHost()
        host.mutate_request = True
        self.assertEqual(host.contract().connect(None, host.request)["allowed"],
                         ["space.news"])

    def test_normal_native_private_capability_remains(self):
        host = ExistingNativeHost()
        self.assertEqual(host.contract().connect(None, host.request)["allowed"],
                         ["space.news"])

    def test_no_paid_sip_route(self):
        host = ExistingNativeHost()
        with self.assertRaises(G2Denied):
            host.contract().connect(None, {"want": ["calls.dial"]})
        self.assertEqual(host.policies, 0)


if __name__ == "__main__":
    unittest.main()
