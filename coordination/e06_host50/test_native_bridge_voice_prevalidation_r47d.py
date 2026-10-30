"""R47 G2-A: invalid voice selectors cannot capture native microphone (source-only)."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "proposals" / "NOX-PACK01-50" / "native_bridge.py"
spec = importlib.util.spec_from_file_location("nox_r47d_native_bridge", SOURCE)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

class VoiceStub:
    approved_models = True
    permitted_voices = frozenset({"voice-installed"})
    def __init__(self, calls): self.calls = calls
    def run(self, *_args, **kwargs):
        self.calls.append(("run", kwargs))
        return SimpleNamespace(transcript="ok", response="ok", audio=b"pcm",
                               source_lang="ru", target_lang="es", mode="translate")

class SipStub:
    def place(self, *_args): raise AssertionError("No SIP call expected")

class VoicePreValidationTests(unittest.TestCase):
    @staticmethod
    def adapter():
        calls = []
        adapter = bridge.ExistingP02VoiceAdapter(
            VoiceStub(calls), SipStub(),
            native_identity=lambda session: calls.append(("identity", session)) or "native-user",
            native_microphone_sample=lambda session: calls.append(("microphone", session)) or b"sample",
            native_provider_quote=lambda *_: None)
        return adapter, calls
    def test_invalid_direction_denied_before_native_capture(self):
        adapter, calls = self.adapter()
        with self.assertRaises(bridge.HostDenied):
            adapter.speak("scope", {"direction":"invalid","voiceId":"voice-installed"}, mode="translate")
        self.assertEqual(calls, [])
    def test_unapproved_voice_denied_before_native_capture(self):
        adapter, calls = self.adapter()
        with self.assertRaises(bridge.HostDenied):
            adapter.speak("scope", {"direction":"ru-es","voiceId":"not-installed"}, mode="translate")
        self.assertEqual(calls, [])
    def test_invalid_cefr_is_denied_without_native_capture(self):
        # P02 LocalVoicePipeline checks CEFR AFTER microphone input: gate first.
        for level in ("D9", ["A2"], None):
            with self.subTest(level=repr(level)):
                adapter, calls = self.adapter()
                with self.assertRaises(bridge.HostDenied):
                    adapter.speak("scope", {"direction":"ru-es",
                        "voiceId":"voice-installed", "level":level}, mode="maestro")
                self.assertEqual(calls, [])
    def test_approved_cefr_keeps_single_native_capture(self):
        adapter, calls = self.adapter()
        adapter.speak("scope", {"direction":"ru-es", "voiceId":"voice-installed",
                               "level":"C2"}, mode="maestro")
        self.assertEqual([x[0] for x in calls], ["identity","microphone","run"])
        self.assertEqual(calls[-1][1]["level"], "C2")
    def test_valid_voice_preserves_one_native_capture_and_pipeline(self):
        adapter, calls = self.adapter()
        result = adapter.speak("scope", {"direction":"ru-es","voiceId":"voice-installed"}, mode="translate")
        self.assertEqual([x[0] for x in calls], ["identity","microphone","run"])
        self.assertEqual(result["transcript"], "ok")
        self.assertIs(calls[-1][1]["microphone_consent"], True)

if __name__ == "__main__": unittest.main()
