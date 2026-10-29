import unittest
from types import SimpleNamespace
from free_local_backends_r34 import (
    bind_faster_whisper_asr, bind_installed_argos_translation, FreeBackendHold,
)

class Stop:
    def __init__(self, active=False): self.active=active
    def is_set(self): return self.active

class Whisper:
    def __init__(self, stop=None): self.calls=0; self.stop=stop
    def transcribe(self, audio, **kwargs):
        self.calls+=1
        assert audio.read()==b'RIFF'
        assert kwargs['language']=='ru' and kwargs['beam_size']==1
        def segments():
            yield SimpleNamespace(text='Привет')
            if self.stop: self.stop.active=True
            yield SimpleNamespace(text='мир')
        return segments(), None

class Translate:
    def translate(self, text): return 'Hola'

class Tests(unittest.TestCase):
    def guard(self, _scope, _route): return True
    def model(self, _scope, _source, _target): return True
    def test_valid_asr(self):
        model=Whisper();fn=bind_faster_whisper_asr(model,native_authorize=self.guard,snapshot_approved=self.model)
        self.assertEqual(fn('native',b'RIFF','ru',Stop()),'Привет мир')
        self.assertEqual(model.calls,1)
    def test_stop_prevents_engine_invocation(self):
        model=Whisper();fn=bind_faster_whisper_asr(model,native_authorize=self.guard,snapshot_approved=self.model)
        with self.assertRaises(FreeBackendHold):fn('native',b'RIFF','ru',Stop(True))
        self.assertEqual(model.calls,0)
    def test_stop_during_lazy_asr(self):
        stop=Stop();model=Whisper(stop);fn=bind_faster_whisper_asr(model,native_authorize=self.guard,snapshot_approved=self.model)
        with self.assertRaisesRegex(FreeBackendHold,'STOP_REQUESTED'):fn('native',b'RIFF','ru',stop)
    def test_acl_denial(self):
        model=Whisper();fn=bind_faster_whisper_asr(model,native_authorize=lambda *_:False,snapshot_approved=self.model)
        with self.assertRaises(PermissionError):fn('native',b'RIFF','ru',Stop())
        self.assertEqual(model.calls,0)
    def test_rights_denial(self):
        model=Whisper();fn=bind_faster_whisper_asr(model,native_authorize=self.guard,snapshot_approved=lambda *_:False)
        with self.assertRaises(PermissionError):fn('native',b'RIFF','ru',Stop())
        self.assertEqual(model.calls,0)
    def test_language_denial(self):
        model=Whisper();fn=bind_faster_whisper_asr(model,native_authorize=self.guard,snapshot_approved=self.model)
        with self.assertRaises(FreeBackendHold):fn('native',b'RIFF','en',Stop())
    def test_audio_bounds(self):
        fn=bind_faster_whisper_asr(Whisper(),native_authorize=self.guard,snapshot_approved=self.model)
        for value in ('bad',b'',b'a'*(16*1024*1024+1)):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ValueError):fn('native',value,'ru',Stop())
    def test_valid_installed_argos_translation(self):
        fn=bind_installed_argos_translation(installed_translation=lambda *_:Translate(),native_authorize=self.guard,snapshot_approved=self.model)
        self.assertEqual(fn('native','Привет','ru','es','RU_ES_TRANSLATE',Stop()),'Hola')
    def test_reject_maestro_fallback(self):
        fn=bind_installed_argos_translation(installed_translation=lambda *_:Translate(),native_authorize=self.guard,snapshot_approved=self.model)
        with self.assertRaises(FreeBackendHold):fn('native','Привет','ru','es','MAESTRO_CEFR_A2',Stop())
    def test_missing_installed_package(self):
        fn=bind_installed_argos_translation(installed_translation=lambda *_:None,native_authorize=self.guard,snapshot_approved=self.model)
        with self.assertRaises(FreeBackendHold):fn('native','Привет','ru','es','RU_ES_TRANSLATE',Stop())
    def test_bad_language_direction(self):
        fn=bind_installed_argos_translation(installed_translation=lambda *_:Translate(),native_authorize=self.guard,snapshot_approved=self.model)
        with self.assertRaises(FreeBackendHold):fn('native','Hola','es','es','RU_ES_TRANSLATE',Stop())
    def test_non_callable_engine_rejected(self):
        with self.assertRaises(TypeError):bind_faster_whisper_asr(object(),native_authorize=self.guard,snapshot_approved=self.model)

if __name__=='__main__':unittest.main()
