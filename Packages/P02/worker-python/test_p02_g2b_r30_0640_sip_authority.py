"""G2-B R30 R02: SIP native approval and provider bindings must be immutable per dial.

SOURCE-ONLY regression. No actual dialing, microphone or Windows CI.
Run from Packages/P02/worker-python:
    python -m unittest -v test_p02_g2b_r30_0640_sip_authority
"""
import threading
import unittest
from decimal import Decimal
from unittest.mock import patch

from p02_capabilities import CallQuote, ConsentGatedSip, Identity
from p02_runtime import P02Error, Cancelled


class G2BSipNativeAuthorityR30R02(unittest.TestCase):
    def setUp(self):
        self.identity = Identity("tenant", "owner", "core", "persona", "session")
        self.quote = CallQuote("+34612345678", "native owner test",
                               Decimal("1.00"), "EUR", "g2b-r02-quote", 110.0)
        self.dials = []
        self.events = []

    def sip(self, verify=None, approval=None):
        def dial(*_):
            self.events.append("dial")
            self.dials.append("dial")
            return "ACCEPTED"
        def allowed_verify(*_):
            self.events.append("verify")
            return True
        def allowed_approval(*_):
            self.events.append("approve")
            return True
        return ConsentGatedSip(
            dial,
            user_approval=approval or allowed_approval,
            provider_quote_verify=verify or allowed_verify)

    def test_01_quote_verifier_cannot_replace_native_approval(self):
        original_approval = lambda *_: self.events.append("original_approval") or True
        def verify(*_):
            sip.user_approval = lambda *_: True
            return True
        sip = self.sip(verify, original_approval)
        with patch("p02_capabilities.time.time", return_value=100.0):
            with self.assertRaisesRegex(P02Error, "SIP_NATIVE_HOOK_REBOUND_HOLD"):
                sip.place(self.identity, self.quote, threading.Event())
        self.assertEqual(self.dials, [])
        self.assertEqual(self.events, [])
        self.assertNotIn(self.quote.quote_id, sip._used)

    def test_02_approval_cannot_swap_dialer(self):
        def approve(*_):
            sip.provider = lambda *_: self.dials.append("unapproved") or "wrong"
            return True
        sip = self.sip(approval=approve)
        with patch("p02_capabilities.time.time", return_value=100.0):
            with self.assertRaisesRegex(P02Error, "SIP_NATIVE_HOOK_REBOUND_HOLD"):
                sip.place(self.identity, self.quote, threading.Event())
        self.assertEqual(self.dials, [])
        self.assertNotIn(self.quote.quote_id, sip._used)

    def test_03_quote_mutation_cannot_redirect_dial(self):
        def verify(*_):
            object.__setattr__(self.quote, "number", "+34687654321")
            return True
        sip = self.sip(verify=verify)
        with patch("p02_capabilities.time.time", return_value=100.0):
            with self.assertRaisesRegex(PermissionError, "SIP_SCOPE_OR_QUOTE_REBOUND_HOLD"):
                sip.place(self.identity, self.quote, threading.Event())
        self.assertEqual(self.dials, [])
        self.assertNotIn(self.quote.quote_id, sip._used)

    def test_04_native_principal_mutation_cannot_redirect_dial(self):
        def verify(*_):
            object.__setattr__(self.identity, "principal", "foreign")
            return True
        sip = self.sip(verify=verify)
        with patch("p02_capabilities.time.time", return_value=100.0):
            with self.assertRaisesRegex(PermissionError, "SIP_SCOPE_OR_QUOTE_REBOUND_HOLD"):
                sip.place(self.identity, self.quote, threading.Event())
        self.assertEqual(self.dials, [])

    def test_05_correct_native_flow_dials_only_once(self):
        sip = self.sip()
        with patch("p02_capabilities.time.time", return_value=100.0):
            self.assertEqual(sip.place(self.identity, self.quote, threading.Event()), "ACCEPTED")
            with self.assertRaisesRegex(PermissionError, "Call quote already consumed"):
                sip.place(self.identity, self.quote, threading.Event())
        self.assertEqual(self.events, ["verify", "approve", "dial"])
        self.assertEqual(self.dials, ["dial"])

    def test_06_stop_during_native_approval_never_dials(self):
        stop = threading.Event()
        def approve(*_):
            stop.set()
            return True
        sip = self.sip(approval=approve)
        with patch("p02_capabilities.time.time", return_value=100.0):
            with self.assertRaises(Cancelled):
                sip.place(self.identity, self.quote, stop)
        self.assertEqual(self.dials, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
