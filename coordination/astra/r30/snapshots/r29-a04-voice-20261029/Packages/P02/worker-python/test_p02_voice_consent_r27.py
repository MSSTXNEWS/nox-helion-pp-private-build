"""R17 consent contract replay against real imported owner modules."""
import threading
import unittest
import test_p02_owner_route_ports as fixture
from p02_owner_route_ports import RouteHold

class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixture.RouteTests()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.args = dict(capture_id='a'*32, source='ru', target='es', voice='es-v')

    def test_missing_native_proof_holds_without_consumption(self):
        self.fx.ports.mic_consent = None
        self.assertFalse(self.fx.ports.available('chat.voice'))
        with self.assertRaises(RouteHold):
            self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertIn('a'*32, self.fx.audio)

    def test_only_exact_true_native_proof_authorizes(self):
        for value in (False, 1, 'yes', None):
            self.fx.ports.mic_consent = lambda *args, value=value: value
            with self.subTest(value=value), self.assertRaises(PermissionError):
                self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertIn('a'*32, self.fx.audio)

    def test_native_proof_receives_exact_scope_and_capture(self):
        seen = []
        self.fx.ports.mic_consent = lambda *args: seen.append(args) or True
        result = self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertEqual(seen, [(self.fx.scope, 'a'*32)])
        self.assertEqual(result['response'], 'hola')

    def test_native_exception_holds_before_capture(self):
        def fail(*args):
            raise RuntimeError('native proof unavailable')
        self.fx.ports.mic_consent = fail
        with self.assertRaisesRegex(RouteHold, 'NATIVE_MIC_PERMISSION_CHECK_HOLD'):
            self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertIn('a'*32, self.fx.audio)

    def test_stop_inside_consent_preserves_capture(self):
        stop = threading.Event()
        self.fx.ports.mic_consent = lambda *args: stop.set() or True
        with self.assertRaisesRegex(RouteHold, 'STOPPED_BEFORE_CAPTURE'):
            self.fx.ports.captured_voice(self.fx.scope, self.args, stop)
        self.assertIn('a'*32, self.fx.audio)

    def test_page_cannot_supply_consent_or_audio(self):
        for key in ('mic_consent', 'microphone_consent', 'audio', 'audio_path'):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                self.fx.ports.captured_voice(self.fx.scope, {**self.args, key: True})
        self.assertIn('a'*32, self.fx.audio)
