"""Native quote/consent cancellation boundaries; no outbound calls."""
import threading
import unittest
from unittest.mock import patch
from p02_runtime import Cancelled
import test_p02_voice_sip_r27 as donor

class SipStopBoundaries(unittest.TestCase):
    setUp = donor.SipExpiryTests.setUp
    adapter = donor.SipExpiryTests.adapter

    def test_stop_during_quote_verification_prevents_consent_prompt(self):
        stop = threading.Event(); prompts = []
        adapter = self.adapter(lambda *args: stop.set() or True,
                               lambda *args: prompts.append(args) or True)
        with patch('p02_capabilities.time.time', return_value=100.0):
            with self.assertRaises(Cancelled): adapter.place(self.scope, self.quote, stop)
        self.assertEqual(prompts, [])
        self.assertEqual(self.called, [])
        self.assertNotIn(self.quote.quote_id, adapter._used)

    def test_stop_during_consent_never_dials_or_consumes_quote(self):
        stop = threading.Event()
        adapter = self.adapter(lambda *args: True, lambda *args: stop.set() or True)
        with patch('p02_capabilities.time.time', return_value=100.0):
            with self.assertRaises(Cancelled): adapter.place(self.scope, self.quote, stop)
        self.assertEqual(self.called, [])
        self.assertNotIn(self.quote.quote_id, adapter._used)
