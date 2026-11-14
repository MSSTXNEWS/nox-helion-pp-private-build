"""R15 native mobile boundary regressions against the real E06 module.
No network listener, paid calls, fake prices, or second host is created.
Run: python -m unittest tests/e06/adapters/test_g2_mobile_final_attestation_r15.py
Not Windows EXE acceptance; all transport/owner dependencies are test doubles.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
from g2_space_mobile import PrivateMobileContract, G2Hold, G2Denied

SAFE_REQUEST = {"want": ["space.news", "helion.chat"]}

class Host:
    def __init__(self, on_advertise=None, broken=False):
        self.on_advertise = on_advertise
        self.broken = broken
        self.calls = 0

    def advertise(self, _session):
        self.calls += 1
        if self.broken:
            raise RuntimeError("private-provider-sensitive-diagnostics")
        if self.on_advertise is not None:
            self.on_advertise()
        return {"space.news": {"enabled": True},
                "helion.chat": {"enabled": True}}

class NativeHarness:
    def __init__(self, *, peer_revoke=False, policy_revoke=False,
                 host_revoke=False, broken_host=False, peer_rotate=False,
                 live=True):
        self.live = live
        self.peer_calls = 0
        self.policy_calls = 0
        self.peer_revoke = peer_revoke
        self.policy_revoke = policy_revoke
        self.peer_rotate = peer_rotate
        def peer(_session):
            self.peer_calls += 1
            if self.peer_calls == 2 and self.peer_revoke:
                self.live = False
            native_approved = not (self.peer_calls == 2 and self.peer_rotate)
            return {"identity": "native-user", "verified_private_peer": True,
                    "trusted_origin": "https://private.example",
                    "observed_origin": "https://private.example",
                    "expected_csrf": b"a" * 32, "received_csrf": b"a" * 32,
                    "native_session_approved": native_approved,
                    "expires_at": 200.0}
        def policy(identity, **proof):
            self.policy_calls += 1
            if self.policy_calls == 2 and self.policy_revoke:
                self.live = False
            # In production the owner verifies these fields; for epoch rotation
            # we deliberately model an over-permissive owner to check E06 defense.
            return identity == "native-user"
        def revoke_host():
            self.live = False
        self.host = Host(on_advertise=revoke_host if host_revoke else None,
                         broken=broken_host)
        self.contract = PrivateMobileContract(
            policy, peer, self.host, lambda: 100.0,
            gateway_ready=lambda: self.live)

class MobileFinalRecheckTests(unittest.TestCase):
    def test_01_gateway_revoked_during_second_peer_check(self):
        h = NativeHarness(peer_revoke=True)
        with self.assertRaisesRegex(G2Hold, "REVOKED_AFTER_ATTESTATION"):
            h.contract.connect(None, SAFE_REQUEST)
        self.assertEqual(h.peer_calls, 2)

    def test_02_gateway_revoked_during_second_policy_check(self):
        h = NativeHarness(policy_revoke=True)
        with self.assertRaisesRegex(G2Hold, "REVOKED_AFTER_ATTESTATION"):
            h.contract.connect(None, SAFE_REQUEST)
        self.assertEqual(h.policy_calls, 2)

    def test_03_host_advertise_exception_is_controlled_hold(self):
        h = NativeHarness(broken_host=True)
        with self.assertRaisesRegex(G2Hold, "advertisement failed") as caught:
            h.contract.connect(None, SAFE_REQUEST)
        self.assertNotIn("sensitive", str(caught.exception))

    def test_04_native_approval_epoch_rotates_not_accepted(self):
        h = NativeHarness(peer_rotate=True)
        with self.assertRaisesRegex(G2Denied, "epoch changed"):
            h.contract.connect(None, SAFE_REQUEST)

    def test_05_private_safe_caps_keep_existing_behavior(self):
        h = NativeHarness()
        out = h.contract.connect(None, SAFE_REQUEST)
        self.assertEqual(out["mode"], "PRIVATE_NATIVE_ATTESTED")
        self.assertEqual(out["allowed"], SAFE_REQUEST["want"])
        self.assertTrue(out["gatewayListening"])

    def test_06_gateway_revoked_during_host_advertise(self):
        h = NativeHarness(host_revoke=True)
        with self.assertRaises(G2Hold):
            h.contract.connect(None, SAFE_REQUEST)

    def test_07_gateway_initially_offline_has_no_host_call(self):
        h = NativeHarness(live=False)
        with self.assertRaises(G2Hold):
            h.contract.connect(None, SAFE_REQUEST)
        self.assertEqual(h.host.calls, 0)

    def test_08_unsafe_remote_sip_never_advertised(self):
        h = NativeHarness()
        with self.assertRaises(G2Denied):
            h.contract.connect(None, {"want": ["calls.dial"]})
        self.assertEqual(h.host.calls, 0)

if __name__ == "__main__":
    unittest.main()
