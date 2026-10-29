"""Actual original voice + immutable PACK01; native/OS effects remain fixtures."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Packages/P02/worker-python'))
import test_p02_original_voice_port_r29 as fixture
from helion_voice.control import VoiceSession
from p02_native_ingress import ProtocolHold


class OriginalVoiceLastScopeBoundary(unittest.TestCase):
    setUp = fixture.OriginalVoiceContract.setUp
    call = fixture.OriginalVoiceContract.call
    speak = fixture.OriginalVoiceContract.speak

    def final_translation_scope(self, action):
        calls = 0
        def resolve(session):
            nonlocal calls
            if self.workers == ['asr', 'translate']:
                calls += 1
                if calls == 2:
                    action()
            return self.fx.scope
        self.port.scope_from_session = resolve

    def test_stop_inside_last_scope_callback_prevents_native_review(self):
        self.final_translation_scope(lambda: self.ingress.voice_session_from_native(self.session).stop())
        with self.assertRaisesRegex(ProtocolHold, 'NATIVE_VOICE_STOPPED'):
            self.speak()
        self.assertEqual(self.reviewed, [], 'native preview UI must not open after STOP')
        self.assertEqual(self.spoken, [])

    def test_replaced_active_voice_inside_last_scope_callback_prevents_native_review(self):
        def replace():
            session, nonce, voice = self.ingress._active_voice
            self.ingress._active_voice = (session, nonce, VoiceSession())
        self.final_translation_scope(replace)
        with self.assertRaises(ProtocolHold):
            self.speak()
        self.assertEqual(self.reviewed, [], 'review must belong to the original active voice request')
        self.assertEqual(self.spoken, [])

    def test_stop_inside_initial_final_scope_callback_prevents_mic_consent(self):
        calls = 0
        consent_calls = []
        self.fx.ports.mic_consent = lambda *args: consent_calls.append(args) or True
        def resolve(session):
            nonlocal calls
            calls += 1
            if calls == 3:
                self.ingress.voice_session_from_native(self.session).stop()
            return self.fx.scope
        self.port.scope_from_session = resolve
        with self.assertRaisesRegex(ProtocolHold, 'NATIVE_VOICE_STOPPED'):
            self.speak()
        self.assertEqual(consent_calls, [])
        self.assertIn('a' * 32, self.fx.audio)
        self.assertEqual(self.workers, [])

    def test_unchanged_original_native_review_and_playback_contract_still_works(self):
        result = self.speak()
        self.assertEqual(result['state'], 'NATIVE_TTS_SUBPROCESS_COMPLETED')
        self.assertEqual(len(self.reviewed), 1)
        self.assertEqual(len(self.spoken), 1)
        self.assertFalse(result['physical_audio_confirmed'])
        self.assertFalse(result['audio_stored'])


if __name__ == '__main__': unittest.main()
