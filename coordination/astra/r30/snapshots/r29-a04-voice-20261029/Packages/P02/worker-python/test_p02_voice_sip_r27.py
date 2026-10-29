"""Real imported owner contracts with offline providers; no live audio or calls."""
import threading
import unittest
from decimal import Decimal
from unittest.mock import patch
from p02_capabilities import CallQuote, ConsentGatedSip, Identity
from p02_owner_route_ports import RouteHold, register_with_existing_pack01
import test_p02_owner_route_ports as owner_fixture
from types import MappingProxyType
from dataclasses import dataclass, replace


class SipExpiryTests(unittest.TestCase):
    def setUp(self):
        self.scope = Identity('tenant', 'alice', 'core-1', 'persona-1', 'session')
        self.quote = CallQuote('+34123456789', 'appointment', Decimal('1'), 'EUR', 'quote-1', 110.0)
        self.clock = 100.0
        self.called = []

    def adapter(self, verify, approve):
        return ConsentGatedSip(lambda *args: self.called.append(args) or 'connected',
                               user_approval=approve, provider_quote_verify=verify)

    def test_quote_expiring_during_approval_never_dials(self):
        def approval(*args):
            self.clock = 111.0
            return True
        adapter = self.adapter(lambda *args: True, approval)
        with patch('p02_capabilities.time.time', side_effect=lambda: self.clock):
            with self.assertRaisesRegex(PermissionError, 'Expired SIP quote'):
                adapter.place(self.scope, self.quote)
        self.assertEqual(self.called, [])

    def test_quote_expiring_during_verification_never_prompts_or_dials(self):
        prompted = []
        def verify(*args):
            self.clock = 111.0
            return True
        adapter = self.adapter(verify, lambda *args: prompted.append(args) or True)
        with patch('p02_capabilities.time.time', side_effect=lambda: self.clock):
            with self.assertRaisesRegex(PermissionError, 'Expired SIP quote'):
                adapter.place(self.scope, self.quote)
        self.assertEqual(prompted, [])
        self.assertEqual(self.called, [])

    def test_fresh_quote_still_dials_only_once(self):
        adapter = self.adapter(lambda *args: True, lambda *args: True)
        with patch('p02_capabilities.time.time', return_value=100.0):
            self.assertEqual(adapter.place(self.scope, self.quote), 'connected')
            with self.assertRaisesRegex(PermissionError, 'already consumed'):
                adapter.place(self.scope, self.quote)
        self.assertEqual(len(self.called), 1)

    def test_nonfinite_or_boolean_quote_never_reaches_provider(self):
        for expiry in (float('nan'), float('inf'), True):
            with self.subTest(expiry=expiry):
                adapter = self.adapter(lambda *args: True, lambda *args: True)
                with self.assertRaisesRegex(PermissionError, 'Expired SIP quote'):
                    adapter.place(self.scope, replace(self.quote, expires_at=expiry))
        self.assertEqual(self.called, [])


class VoiceOutputTests(unittest.TestCase):
    def setUp(self):
        self.fixture = owner_fixture.RouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.stop = threading.Event()
        self.discarded = []
        self.args = dict(capture_id='a'*32, source='ru', target='es', voice='es-v')
        def write(scope, audio):
            self.stop.set()
            return 'b'*32
        self.fixture.ports.store_output_audio = write

    def test_stop_during_output_revokes_native_receipt_without_success(self):
        def discard(scope, receipt):
            self.discarded.append((scope, receipt))
            return True
        self.fixture.ports.discard_output_audio = discard
        with self.assertRaisesRegex(RouteHold, 'PERSISTENCE$'):
            self.fixture.ports.captured_voice(self.fixture.scope, self.args, self.stop)
        self.assertEqual(self.discarded, [(self.fixture.scope, 'b'*32)])

    def test_stop_without_cleanup_callback_is_explicit_hold(self):
        with self.assertRaisesRegex(RouteHold, 'CLEANUP_HOLD'):
            self.fixture.ports.captured_voice(self.fixture.scope, self.args, self.stop)

    def test_cleanup_failure_never_claims_revocation(self):
        for callback in (lambda *args: False, lambda *args: 1):
            with self.subTest(callback=callback):
                self.fixture.audio['a'*32] = b'voice'
                self.stop.clear()
                self.fixture.ports.discard_output_audio = callback
                with self.assertRaisesRegex(RouteHold, 'CLEANUP_HOLD'):
                    self.fixture.ports.captured_voice(self.fixture.scope, self.args, self.stop)

    def test_cleanup_exception_is_wrapped_as_hold(self):
        def fail(*args):
            raise OSError('native failure')
        self.fixture.ports.discard_output_audio = fail
        with self.assertRaisesRegex(RouteHold, 'CLEANUP_HOLD'):
            self.fixture.ports.captured_voice(self.fixture.scope, self.args, self.stop)

    def test_successful_output_is_not_discarded(self):
        self.fixture.ports.store_output_audio = lambda *args: 'b'*32
        self.fixture.ports.discard_output_audio = lambda *args: self.discarded.append(args) or True
        result = self.fixture.ports.captured_voice(self.fixture.scope, self.args, self.stop)
        self.assertEqual(result['output_audio_id'], 'b'*32)
        self.assertEqual(self.discarded, [])

    def test_immutable_three_port_registry_accepts_r22_donor_contract(self):
        @dataclass(frozen=True)
        class BoundPort:
            call: object
            available: object
            evidence_id: str
            owner: int
        class Dispatcher:
            def __init__(self):
                self.routes = MappingProxyType({name: MappingProxyType({'owner': 2})
                    for name in ('chat.rag', 'chat.voice', 'calls.history')})
                self.ports = {}
            def bind(self, route, port):
                self.ports[route] = port
        dispatcher = Dispatcher()
        bound = register_with_existing_pack01(dispatcher, BoundPort,
            lambda _: self.fixture.scope, self.fixture.ports, receipt='ASTRA-R27-A05')
        self.assertEqual(bound, frozenset(dispatcher.routes))
        self.assertEqual(dispatcher.ports['calls.history'].call(None, {})['calls'][0]['call_id'], 'id1')


if __name__ == '__main__':
    unittest.main()
