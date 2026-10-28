"""SOURCE-ONLY STOP race tests. No microphone, ASR/TTS, Windows or E07 evidence.

Checked out owner repo test:
  NOX_P02_SOURCE=Packages/P02/worker-python/p02_owner_route_ports.py \
    python tests/e07/test_p02_voice_output_stop_r19.py -v
Uses method from the *exact owner bytes* on the branch under test.
"""
from __future__ import annotations
import importlib.util
import os
import sys
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest

SOURCE = Path(os.environ.get("NOX_P02_SOURCE", Path(__file__).resolve().parents[2] / "Packages/P02/worker-python/p02_owner_route_ports.py"))
sys.path.insert(0, str(SOURCE.parent))  # import existing P02 owner dependencies, do not install packages
spec = importlib.util.spec_from_file_location("nox_p02_owner_voice_r19",SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
TOKEN = 'b'*32
class TestVoiceStoreStopRace(unittest.TestCase):
    def setUp(self):
        self.stop=threading.Event()
        self.scope=SimpleNamespace(identity="synthetic")  # _session is deliberately stubbed for this source-only callback race
        self.p=module.OwnerTwoPorts.__new__(module.OwnerTwoPorts)
        self.p._session=lambda scope,route: None
        self.p.available=lambda route: True
        self.p.mic_consent=lambda scope,cap_id: True
        self.p.take_audio=lambda scope,cap_id: b'fixture-audio-not-hardware'
        self.run_calls=[]
        def voice_run(*a,**kw):
            self.run_calls.append(True)
            return SimpleNamespace(audio=b'fixture-output',transcript='test',response='test',target_lang='es',mode='translate')
        self.p.voice=SimpleNamespace(run=voice_run)
        self.outputs=[]
        self.p.store_output_audio=lambda scope,audio: (self.outputs.append(audio) or TOKEN)
        self.args={'capture_id':'a'*32,'source':'ru','target':'es'}
    def call(self):
        return self.p.captured_voice(self.scope,self.args,self.stop)
    def test_01_normal_output_receipt(self):
        self.assertEqual(self.call()['output_audio_id'],TOKEN)
        self.assertEqual(len(self.outputs),1)
    def test_02_stop_before_native_capture(self):
        self.stop.set()
        with self.assertRaises(module.RouteHold): self.call()
        self.assertEqual(len(self.outputs),0)
    def test_03_stop_during_pipeline(self):
        def voice_run(*a,**kw):
            self.stop.set()
            return SimpleNamespace(audio=b'fixture-output',transcript='t',response='r',target_lang='es',mode='translate')
        self.p.voice.run=voice_run
        with self.assertRaises(module.RouteHold): self.call()
        self.assertEqual(len(self.outputs),0)
    def test_04_stop_during_output_store_must_block_receipt(self):
        def store(scope,audio):
            self.outputs.append(audio)
            self.stop.set()   # deterministic cancellation race inside native callback
            return TOKEN
        self.p.store_output_audio=store
        with self.assertRaisesRegex(module.RouteHold,'NATIVE_VOICE_STOPPED_DURING_OUTPUT_STORE'):
            self.call()
        self.assertEqual(len(self.outputs),1)  # storage cleanup is separate owner contract
    def test_05_native_permission_deny_no_store(self):
        self.p.mic_consent=lambda scope,cap_id: False
        with self.assertRaises(PermissionError): self.call()
        self.assertEqual(len(self.outputs),0)
    def test_06_invalid_output_receipt_denied(self):
        self.p.store_output_audio=lambda scope,audio: 'not-a-token'
        with self.assertRaises(module.RouteHold): self.call()

if __name__=='__main__':
    unittest.main()
