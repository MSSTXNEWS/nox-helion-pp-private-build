import unittest
from dataclasses import replace
import test_p02_owner_route_ports as fixture
from p02_capabilities import VoiceResult
from p02_runtime import P02Error

class ResultTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixture.RouteTests(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.args = dict(capture_id='a'*32, source='ru', target='es', voice='es-v')
        self.stored = []
        self.fx.ports.store_output_audio = lambda *a: self.stored.append(a) or 'b'*32
    def test_invalid_asr_text_never_reaches_llm_or_storage(self):
        llm = []
        self.fx.voice.chat = lambda *a: llm.append(a) or 'hola'
        for text in (' ', '\ud800', 'x'*20001):
            self.fx.audio['a'*32] = b'voice'; self.fx.voice.asr = lambda *a, text=text: text
            with self.subTest(text=text[:4]), self.assertRaisesRegex(P02Error, 'ASR_INVALID_RESULT'):
                self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertEqual(llm, []); self.assertEqual(self.stored, [])
    def test_invalid_llm_text_never_reaches_tts_or_storage(self):
        tts = []; self.fx.voice.tts = lambda *a: tts.append(a) or b'audio'
        for text in ('\n\t', '\udfff', 'x'*30001):
            self.fx.audio['a'*32] = b'voice'; self.fx.voice.chat = lambda *a, text=text: text
            with self.subTest(text=text[:4]), self.assertRaisesRegex(P02Error, 'LLM_INVALID_RESULT'):
                self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertEqual(tts, []); self.assertEqual(self.stored, [])
    def test_native_owner_rejects_mismatched_or_oversized_adapter_result(self):
        valid = VoiceResult('привет', 'hola', b'audio', 'ru', 'es', 'translate')
        for result in (replace(valid, target_lang='ru'), replace(valid, mode='maestro'),
                       replace(valid, transcript='\ud800'), replace(valid, audio=b'x'*(16*1024*1024+1))):
            self.fx.audio['a'*32] = b'voice'; self.fx.voice.run = lambda *a, result=result, **kw: result
            with self.subTest(field=result.mode), self.assertRaises(P02Error):
                self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertEqual(self.stored, [])
    def test_unicode_spanish_russian_and_emoji_roundtrip(self):
        self.fx.voice.asr = lambda *a: 'Привет 👋\nКак дела?'
        self.fx.voice.chat = lambda *a: '¡Hola! 👋\nMuy bien.'
        result = self.fx.ports.captured_voice(self.fx.scope, self.args)
        self.assertIn('👋', result['transcript']); self.assertIn('¡Hola!', result['response'])
        self.assertEqual(len(self.stored), 1)
