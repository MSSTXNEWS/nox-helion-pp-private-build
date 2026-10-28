"""R18: stop arriving during existing native output store must not acknowledge success.
Focused same-source test with injected owner providers; NOT microphone/ASR/TTS runtime.
"""
import threading
import unittest
from test_p02_native_voice_permission_ci_r17 import VoiceConsentGate


class LateNativeVoiceStop(unittest.TestCase):
    def setUp(self):
        self.fx = VoiceConsentGate('test_true_proof_scoped_and_forwarded')
        self.fx.setUp()

    def _ports(self, output):
        ports = self.fx.ports(lambda scope, capture_id: True)
        ports.store_output_audio = output
        return ports

    def test_stop_during_native_output_store_fails_closed_ru_es(self):
        self._stop_during_output('ru', 'es')

    def test_stop_during_native_output_store_fails_closed_es_ru(self):
        self._stop_during_output('es', 'ru')

    def _stop_during_output(self, source, target):
        stop = threading.Event()
        written = []
        def write(scope, audio):
            written.append((scope, audio))
            stop.set()  # Realistic native-storage callback blocks while STOP arrives.
            return 'f' * 32
        args = dict(self.fx.args, source=source, target=target)
        with self.assertRaisesRegex(self.fx.m.RouteHold, 'NATIVE_VOICE_STOPPED_DURING_OUTPUT_PERSISTENCE'):
            self._ports(write).captured_voice(self.fx.scope, args, stop)
        self.assertEqual(len(written), 1)
        self.assertEqual(len(self.fx.voice.calls), 1)
        self.assertEqual(self.fx.consumed, ['e'*32])
        # Existing native storage may already have committed: cleanup requires host contract.

    def test_output_persist_without_stop_still_succeeds(self):
        stop = threading.Event()
        saved = []
        def write(scope, audio):
            saved.append(audio)
            return 'f'*32
        result = self._ports(write).captured_voice(self.fx.scope, self.fx.args, stop)
        self.assertEqual(result['output_audio_id'], 'f'*32)
        self.assertEqual(saved, [b'wav'])

    def test_stop_after_asr_before_output_does_not_persist(self):
        stop = threading.Event()
        saved = []
        def voice_run(*a, **kw):
            stop.set()
            return type('R',(),dict(audio=b'wav', transcript='a',response='b',target_lang='es',mode='translate'))()
        self.fx.voice.run = voice_run
        def write(*args):
            saved.append(args)
            return 'f'*32
        with self.assertRaisesRegex(self.fx.m.RouteHold, 'NATIVE_VOICE_STOPPED_BEFORE_OUTPUT'):
            self._ports(write).captured_voice(self.fx.scope, self.fx.args, stop)
        self.assertEqual(saved, [])


if __name__ == '__main__':
    unittest.main()
