import unittest
import test_p02_owner_route_ports as fixture

class RequestTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixture.RouteTests(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.args = dict(capture_id='a'*32, source='ru', target='es', voice='es-v')

    def test_invalid_request_never_consumes_or_prompts(self):
        called = []
        self.fx.ports.mic_consent = lambda *a: called.append(a) or True
        for key, value in [('source', 'en'), ('target', 'ru'), ('voice', 'unknown'),
                           ('mode', 'bad'), ('level', []), ('source', {'ru': True})]:
            with self.subTest(key=key, value=value), self.assertRaises((ValueError, PermissionError)):
                self.fx.ports.captured_voice(self.fx.scope, {**self.args, key: value})
        self.assertIn('a'*32, self.fx.audio); self.assertEqual(called, [])

    def test_authorization_callback_cannot_replace_request(self):
        def authorize(*a):
            self.args.update(source='es', target='ru', voice='not-approved')
            return True
        self.fx.ports.authorize = authorize
        result = self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertEqual(result['target_lang'], 'es')

    def test_native_capture_callback_cannot_replace_request(self):
        original = self.fx.ports.take_audio
        def take(scope, cap_id):
            self.args.update(source='en', mode='arbitrary', capture_id='f'*32)
            return original(scope, cap_id)
        self.fx.ports.take_audio = take
        result = self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertEqual(result['mode'], 'translate'); self.assertEqual(result['target_lang'], 'es')

    def test_both_directions_and_maestro_still_supported(self):
        for source, target, mode in [('ru', 'es', 'translate'), ('es', 'ru', 'maestro')]:
            self.fx.audio['a'*32] = b'voice'
            result = self.fx.ports.captured_voice(self.fx.scope,
                {**self.args, 'source': source, 'target': target, 'mode': mode, 'level': 'B2'})
            self.assertEqual(result['target_lang'], target); self.assertEqual(result['mode'], mode)
