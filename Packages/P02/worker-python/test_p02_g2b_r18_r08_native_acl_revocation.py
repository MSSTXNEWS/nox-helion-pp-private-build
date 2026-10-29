"""G2-B R08 focused owner-source regressions; no microphone, SIP, host or network.

Run from Packages/P02/worker-python:
  python -m unittest -v test_p02_g2b_r18_r08_native_acl_revocation
Requires the real p02_owner_route_ports.py and existing original P02 modules.
"""
import threading
import unittest
from types import SimpleNamespace

from p02_capabilities import Identity, LocalVoicePipeline
from p02_owner_route_ports import NativeScope, OwnerTwoPorts, RouteHold


class G2BR08NativeACL(unittest.TestCase):
    def setUp(self):
        self.allowed = {'calls.history': True, 'chat.voice': True}
        self.consent = {'active': True}
        self.captured = []
        self.saved = []
        self.discarded = []
        self.history = [{'tenant': 't', 'principal': 'u', 'call_id': 'call-1',
                         'started_epoch': 1000, 'status': 'completed'}]
        self.scope = NativeScope('t', 'u', 'c', 'S-1-5-21-123-456-789', 's',
                                 Identity('t', 'u', 'core', 'persona', 's'))
        self.port = object.__new__(OwnerTwoPorts)
        self.port.store = SimpleNamespace(history=lambda *args: [])
        self.port.authorize = lambda scope, route: self.allowed[route]
        self.port.owner_ready = lambda route: True
        self.port.rag = None
        self.port.voice = LocalVoicePipeline(lambda *args: 'privet',
                       lambda *args: 'hola', lambda *args: b'out',
                       approved_models=True, permitted_voices=frozenset({'es-v'}))
        self.port.take_audio = lambda scope, cap: self.captured.append(cap) or b'in'
        self.port.mic_consent = lambda scope, cap: self.consent['active']
        self.port.store_output_audio = lambda scope, audio: self.saved.append(audio) or 'b'*32
        self.port.discard_output_audio = lambda scope, oid: self.discarded.append(oid) or True
        self.port.call_history = lambda scope, n: self.history[:n]

    def voice_args(self):
        return {'capture_id': 'a'*32, 'source': 'ru', 'target': 'es', 'voice': 'es-v'}

    def test_history_acl_revoked_by_provider_before_reply(self):
        def provider(scope, limit):
            self.allowed['calls.history'] = False
            return self.history[:limit]
        self.port.call_history = provider
        with self.assertRaises(PermissionError):
            self.port.calls_history(self.scope, {})

    def test_history_owner_provider_rebound_before_reply(self):
        def provider(scope, limit):
            self.port.call_history = lambda *_: self.history
            return self.history[:limit]
        self.port.call_history = provider
        with self.assertRaisesRegex(RouteHold, 'CALL_HISTORY_NATIVE_BINDING_CHANGED_HOLD'):
            self.port.calls_history(self.scope, {})

    def test_history_scope_mutation_rejected(self):
        def provider(scope, limit):
            object.__setattr__(scope, 'conversation_id', 'other-chat')
            return self.history[:limit]
        self.port.call_history = provider
        with self.assertRaisesRegex(RouteHold, 'CALL_HISTORY_NATIVE_BINDING_CHANGED_HOLD'):
            self.port.calls_history(self.scope, {})

    def test_history_sanitizes_provider_extras(self):
        self.history[0]['secret'] = 'HIDDEN'
        self.assertEqual(self.port.calls_history(self.scope, {})['calls'],
                         [{'call_id': 'call-1', 'started_epoch': 1000, 'status': 'completed'}])

    def test_voice_consent_revoked_during_asr_never_persists(self):
        self.port.voice.asr = lambda *args: self.consent.update(active=False) or 'privet'
        with self.assertRaisesRegex(PermissionError, 'NATIVE_MIC_CONSENT_REVOKED_BEFORE_OUTPUT'):
            self.port.captured_voice(self.scope, self.voice_args(), stop=threading.Event())
        self.assertEqual(self.saved, [])

    def test_voice_consent_revoked_during_storage_discards(self):
        def store(scope, audio):
            self.saved.append(audio)
            self.consent['active'] = False
            return 'b'*32
        self.port.store_output_audio = store
        with self.assertRaisesRegex(RouteHold, 'NATIVE_VOICE_CONSENT_OR_ACL_REVOKED_DURING_OUTPUT'):
            self.port.captured_voice(self.scope, self.voice_args(), stop=threading.Event())
        self.assertEqual(self.discarded, ['b'*32])

    def test_voice_native_stop_during_storage_discards(self):
        stop = threading.Event()
        def store(scope, audio):
            stop.set()
            return 'b'*32
        self.port.store_output_audio = store
        with self.assertRaisesRegex(RouteHold, 'NATIVE_VOICE_STOPPED_DURING_OUTPUT_PERSISTENCE'):
            self.port.captured_voice(self.scope, self.voice_args(), stop=stop)
        self.assertEqual(self.discarded, ['b'*32])

    def test_missing_audio_discard_never_consumes_capture(self):
        self.port.discard_output_audio = None
        with self.assertRaisesRegex(RouteHold, 'INSTALLED_LOCAL_ASR_TTS_OR_HOST_CAPTURE_HOLD'):
            self.port.captured_voice(self.scope, self.voice_args(), stop=threading.Event())
        self.assertEqual(self.captured, [])

    def test_mic_consent_hook_rebound_during_asr_rejected(self):
        def asr(*args):
            self.port.mic_consent = lambda *_: True
            return 'privet'
        self.port.voice.asr = asr
        with self.assertRaisesRegex(RouteHold, 'NATIVE_VOICE_HOOK_REBOUND_HOLD'):
            self.port.captured_voice(self.scope, self.voice_args(), stop=threading.Event())
        self.assertEqual(self.saved, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
