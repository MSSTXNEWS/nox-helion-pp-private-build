import threading
import unittest
from p02_capabilities import Identity, LocalVoicePipeline
from p02_runtime import P02Error, Cancelled

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.scope = Identity('t', 'u', 'core', 'persona', 's')
        self.seen = []
        self.stop = threading.Event()
        self.voice = LocalVoicePipeline(lambda *a: self.seen.append('asr') or 'hola',
            lambda *a: self.seen.append('llm') or 'привет',
            lambda *a: self.seen.append('tts') or b'audio',
            approved_models=True, permitted_voices=frozenset({'ru-v'}))
    def run_voice(self, consent=True):
        return self.voice.run(self.scope, b'mic', source='es', target='ru', voice='ru-v',
                              microphone_consent=consent, stop=self.stop)
    def test_truthy_flags_do_not_grant_consent_or_rights(self):
        for consent in (1, 'yes', object()):
            with self.subTest(consent=consent), self.assertRaises(PermissionError): self.run_voice(consent)
        self.voice.approved_models = 1
        with self.assertRaises(PermissionError): self.run_voice()
        self.assertEqual(self.seen, [])
    def test_model_revocation_at_each_stage_prevents_later_stages(self):
        for stage, result in [('asr', 'hola'), ('chat', 'привет'), ('tts', b'audio')]:
            self.setUp()
            def revoke(*a, result=result):
                self.voice.approved_models = False
                return result
            setattr(self.voice, stage, revoke)
            with self.subTest(stage=stage), self.assertRaisesRegex(PermissionError, 'RIGHTS_REVOKED'):
                self.run_voice()
            self.assertEqual(len(self.seen), ('asr','chat','tts').index(stage))
    def test_provider_hot_swap_cannot_redirect_inflight_audio(self):
        rogue = []
        def asr(*a):
            self.voice.chat = lambda *a: rogue.append(a) or 'rogue'
            return 'hola'
        self.voice.asr = asr
        with self.assertRaisesRegex(P02Error, 'PROVIDER_CHANGED'): self.run_voice()
        self.assertEqual(rogue, [])
    def test_stop_at_each_provider_boundary_has_no_later_call(self):
        for stage, result in [('asr', 'hola'), ('chat', 'привет'), ('tts', b'audio')]:
            self.setUp()
            def cancel(*a, result=result): self.stop.set(); return result
            setattr(self.voice, stage, cancel)
            with self.subTest(stage=stage), self.assertRaises(Cancelled): self.run_voice()
            self.assertEqual(len(self.seen), ('asr','chat','tts').index(stage))
    def test_external_voice_set_cannot_broaden_permission(self):
        permitted = {'ru-v'}
        voice = LocalVoicePipeline(lambda *a: '', lambda *a: '', lambda *a: b'',
                                   approved_models=True, permitted_voices=permitted)
        permitted.add('other')
        self.assertEqual(voice.permitted_voices, frozenset({'ru-v'}))
    def test_normal_pipeline_keeps_one_ordered_provider_chain(self):
        self.assertEqual(self.run_voice().audio, b'audio')
        self.assertEqual(self.seen, ['asr', 'llm', 'tts'])
