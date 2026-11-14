"""E06 W4-03 R16: real-module native ACL epoch and peer proof tests.
Uses in-process owner doubles only. No listener, voice, paid SIP or external feed.
Run: python -m unittest tests/e06/adapters/test_g2_mobile_acl_epoch_r16.py
Real installed Windows/E07 acceptance: NOT_RUN.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
from g2_space_mobile import PrivateMobileContract, G2Denied, G2Hold

WANT = {"want": ["space.news"]}

class ExistingHost:
    def __init__(self):
        self.news = True
        self.live = True
        self.calls = 0
        self.fail_second = False
        self.revoke_gateway_second = False

    def advertise(self, _session):
        self.calls += 1
        if self.fail_second and self.calls == 2:
            raise RuntimeError("private-native-internal-diagnostics")
        if self.revoke_gateway_second and self.calls == 2:
            self.live = False
        return {"space.news": {"enabled": self.news}}

class ExistingOwner:
    def __init__(self, **flags):
        self.host = ExistingHost()
        self.flags = flags
        self.proofs = 0
        self.policies = 0

    def peer(self, _session):
        self.proofs += 1
        if self.proofs == 2:
            if self.flags.get("revoke_route"):
                self.host.news = False
            if self.flags.get("grant_route"):
                self.host.news = True
        return {
            "identity": "native-user",
            "verified_private_peer": not self.flags.get("fake_peer", False),
            "trusted_origin": ("http://private.example" if self.flags.get("http_origin")
                               else "https://private.example"),
            "observed_origin": ("https://wrong.example" if self.flags.get("wrong_origin")
                                else "http://private.example" if self.flags.get("http_origin")
                                else "https://private.example"),
            "expected_csrf": b"a" * 32,
            "received_csrf": b"b" * 32 if self.flags.get("wrong_csrf") else b"a" * 32,
            "native_session_approved": not (self.flags.get("rotated_approval")
                                            and self.proofs == 2),
            "expires_at": 200.0,
        }

    def policy(self, _identity, **_proof):
        self.policies += 1
        return True  # deliberately over-permissive existing native policy

    def contract(self):
        return PrivateMobileContract(self.policy, self.peer, self.host,
                                     lambda: 100.0,
                                     gateway_ready=lambda: self.host.live)

class MobileAclEpochR16(unittest.TestCase):
    def test_false_private_peer_rejected_even_if_policy_returns_true(self):
        o = ExistingOwner(fake_peer=True)
        with self.assertRaises(G2Denied):
            o.contract().connect(None, WANT)
        self.assertEqual(o.host.calls, 0)

    def test_csrf_mismatch_rejected_even_if_policy_returns_true(self):
        o = ExistingOwner(wrong_csrf=True)
        with self.assertRaises(G2Denied):
            o.contract().connect(None, WANT)

    def test_observed_origin_mismatch_rejected(self):
        o = ExistingOwner(wrong_origin=True)
        with self.assertRaises(G2Denied):
            o.contract().connect(None, WANT)

    def test_http_remote_origin_not_misreported_as_private_https(self):
        o = ExistingOwner(http_origin=True)
        with self.assertRaises(G2Denied):
            o.contract().connect(None, WANT)

    def test_owner_acl_revocation_during_second_attest_is_hold(self):
        o = ExistingOwner(revoke_route=True)
        with self.assertRaisesRegex(G2Hold, "CAPABILITY_EPOCH_CHANGED"):
            o.contract().connect(None, WANT)
        self.assertEqual(o.host.calls, 2)

    def test_owner_acl_grant_during_second_attest_is_hold_not_escalation(self):
        o = ExistingOwner(grant_route=True)
        o.host.news = False
        with self.assertRaisesRegex(G2Hold, "CAPABILITY_EPOCH_CHANGED"):
            o.contract().connect(None, WANT)

    def test_second_owner_advertisement_error_is_sanitized(self):
        o = ExistingOwner()
        o.host.fail_second = True
        with self.assertRaises(G2Hold) as caught:
            o.contract().connect(None, WANT)
        self.assertNotIn("private-native-internal-diagnostics", str(caught.exception))

    def test_prior_lesson_gateway_recheck_after_final_advertise(self):
        o = ExistingOwner()
        o.host.revoke_gateway_second = True
        with self.assertRaisesRegex(G2Hold, "REVOKED_AFTER_FINAL_ADVERTISEMENT"):
            o.contract().connect(None, WANT)

    def test_native_session_keeps_real_safe_capability(self):
        o = ExistingOwner()
        result = o.contract().connect(None, WANT)
        self.assertEqual(result["mode"], "PRIVATE_NATIVE_ATTESTED")
        self.assertEqual(result["allowed"], ["space.news"])
        self.assertTrue(result["gatewayListening"])
        self.assertEqual(o.host.calls, 2)

    def test_paid_sip_route_still_denied_without_native_owner(self):
        o = ExistingOwner()
        with self.assertRaises(G2Denied):
            o.contract().connect(None, {"want": ["calls.dial"]})
        self.assertEqual(o.host.calls, 0)

    def test_second_native_session_approval_epoch_rotation_still_denied(self):
        o = ExistingOwner(rotated_approval=True)
        with self.assertRaisesRegex(G2Denied, "epoch changed"):
            o.contract().connect(None, WANT)

if __name__ == "__main__":
    unittest.main()
