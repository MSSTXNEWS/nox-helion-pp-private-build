"""G2-B R06: source-only native STOP + SIP consent regression (no real devices).

Run against repository Packages/P02/worker-python; live SIP/Windows is NOT covered.
"""
import threading
import time
import unittest
from decimal import Decimal
from p02_capabilities import Identity, CallQuote, ConsentGatedSip, LocalVoicePipeline
from p02_owner_route_ports import OwnerTwoPorts, RouteHold
from p02_runtime import P02Error, Cancelled

SCOPE = Identity('tenant', 'user', 'HELION', 'persona', 'session')


def quote(name='unique'):
    return CallQuote('+34123456789', 'local-source-regression', Decimal('0.01'),
                     'EUR', name, time.time() + 60)


class NativeStopOwnerRegression(unittest.TestCase):
    def test_direct_owner_route_fails_before_capture_if_token_missing(self):
        # No functional owner/store is needed: STOP must be checked FIRST.
        port = object.__new__(OwnerTwoPorts)
        with self.assertRaisesRegex(RouteHold, 'NATIVE_VOICE_STOP_TOKEN_REQUIRED'):
            port.captured_voice(object(), {})

    def test_voice_rejects_missing_token_before_asr(self):
        visited = []
        p = LocalVoicePipeline(lambda *a: visited.append('asr') or 'hola',
                               lambda *a: visited.append('chat') or 'привет',
                               lambda *a: visited.append('tts') or b'output',
                               approved_models=True, permitted_voices=frozenset({'local'}))
        with self.assertRaisesRegex(P02Error, 'VOICE_NATIVE_STOP_TOKEN_REQUIRED'):
            p.run(SCOPE, b'captured', source='ru', target='es', voice='local',
                  microphone_consent=True)
        self.assertEqual([], visited)

    def test_voice_native_stop_during_asr_prevents_next_provider(self):
        stop = threading.Event()
        visited = []
        def asr(*args):
            visited.append('asr')
            stop.set()
            return 'hola'
        p = LocalVoicePipeline(asr,
                               lambda *a: visited.append('chat') or 'привет',
                               lambda *a: visited.append('tts') or b'output',
                               approved_models=True, permitted_voices=frozenset({'local'}))
        with self.assertRaises(Cancelled):
            p.run(SCOPE, b'captured', source='ru', target='es', voice='local',
                  microphone_consent=True, stop=stop)
        self.assertEqual(['asr'], visited)

    def test_voice_consent_denied_no_provider_calls(self):
        visited = []
        p = LocalVoicePipeline(lambda *a: visited.append('asr') or 'hola',
                               lambda *a: visited.append('chat') or 'привет',
                               lambda *a: visited.append('tts') or b'output',
                               approved_models=True, permitted_voices=frozenset({'local'}))
        with self.assertRaises(PermissionError):
            p.run(SCOPE, b'captured', source='ru', target='es', voice='local',
                  microphone_consent=False, stop=threading.Event())
        self.assertEqual([], visited)

    def test_sip_missing_stop_token_no_verifier_or_dial(self):
        visited = []
        sip = ConsentGatedSip(lambda *a: visited.append('dial'),
                              user_approval=lambda *a: visited.append('consent') or True,
                              provider_quote_verify=lambda *a: visited.append('verify') or True)
        with self.assertRaisesRegex(P02Error, 'SIP_NATIVE_STOP_TOKEN_REQUIRED'):
            sip.place(SCOPE, quote('missing'))
        self.assertEqual([], visited)

    def test_sip_reentrant_verifier_fails_closed_no_deadlock(self):
        dials, nested = [], []
        sip = ConsentGatedSip(lambda s,q,stop: dials.append(q.quote_id),
                              user_approval=lambda *a: True,
                              provider_quote_verify=None)
        def verifier(scope, q):
            try:
                sip.place(SCOPE, quote('inner'), threading.Event())
            except P02Error as exc:
                nested.append(str(exc))
            return True
        sip.provider_quote_verify = verifier
        sip.place(SCOPE, quote('outer'), threading.Event())
        self.assertEqual(['SIP_CONCURRENT_OR_REENTRANT_CONFIRMATION_HOLD'], nested)
        self.assertEqual(['outer'], dials)

    def test_sip_stop_during_consent_never_calls_dialer(self):
        stop, dials = threading.Event(), []
        def native_consent(*args):
            stop.set()
            return True
        sip = ConsentGatedSip(lambda *a: dials.append('dial'),
                              user_approval=native_consent,
                              provider_quote_verify=lambda *a: True)
        with self.assertRaises(Cancelled):
            sip.place(SCOPE, quote('stop'), stop)
        self.assertEqual([], dials)


if __name__ == '__main__':
    unittest.main()
