"""R30 G2-B focused SOURCE tests: native RU/ES consent, STOP cleanup and SIP quote freshness.

No network, microphone, SIP dialing, model downloads or Windows builds.
Run from Packages/P02/worker-python:
  python -m unittest -v test_p02_g2b_r30_voice_sip
"""
import sqlite3
import sys
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from p02_capabilities import CallQuote, ConsentGatedSip, Identity, LocalVoicePipeline
from p02_owner_route_ports import NativeScope, OwnerTwoPorts, RouteHold
from p02_original_voice_port import OriginalVoicePort
from p02_runtime import Cancelled, P02Store


class G2BVoiceSipR30(unittest.TestCase):
    def setUp(self):
        self.scope_identity = Identity("t", "alice", "core-1", "persona-1", "session")
        self.calls = []
        self.pipeline = LocalVoicePipeline(
            lambda *_: self.calls.append("asr") or "Привет",
            lambda *_: self.calls.append("llm") or "Hola",
            lambda *_: self.calls.append("tts") or b"LOCAL",
            approved_models=True, permitted_voices=frozenset({"es-v"}))

    def voice(self, **kwargs):
        request = dict(source="ru", target="es", voice="es-v", microphone_consent=True)
        request.update(kwargs)
        return self.pipeline.run(self.scope_identity, b"CAPTURED", **request)

    def test_01_requires_exact_true_mic_consent_before_asr(self):
        for value in (False, None, "true", 1):
            with self.subTest(value=value):
                with self.assertRaises(PermissionError):
                    self.voice(microphone_consent=value)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.voice().response, "Hola")

    def test_02_rejects_bad_asr_text_before_llm(self):
        self.pipeline.asr = lambda *_: " "
        with self.assertRaisesRegex(Exception, "ASR_INVALID_RESULT"):
            self.voice()
        self.assertEqual(self.calls, [])

    def test_03_stop_after_asr_blocks_llm_tts(self):
        stop = threading.Event()
        self.pipeline.asr = lambda *_: stop.set() or "Привет"
        with self.assertRaises(Cancelled):
            self.voice(stop=stop)
        self.assertEqual(self.calls, [])

    def test_04_sip_expiry_during_quote_verification_never_dials(self):
        clock = [100.0]
        dialled = []
        quote = CallQuote("+34612345678", "consented test", Decimal("1.00"), "EUR", "q-1", 105.0)
        def verify(*_):
            clock[0] = 106.0
            return True
        sip = ConsentGatedSip(lambda *_: dialled.append("dial"), user_approval=lambda *_: True,
                              provider_quote_verify=verify)
        with patch("p02_capabilities.time.time", lambda: clock[0]):
            with self.assertRaisesRegex(PermissionError, "Expired SIP quote"):
                sip.place(self.scope_identity, quote)
        self.assertEqual(dialled, [])

    def test_05_sip_stop_during_native_consent_never_dials(self):
        stop = threading.Event()
        dialled = []
        def approve(*_):
            stop.set()
            return True
        sip = ConsentGatedSip(lambda *_: dialled.append("dial"), user_approval=approve,
                              provider_quote_verify=lambda *_: True)
        quote = CallQuote("+34612345678", "consented test", Decimal("1.00"), "EUR", "q-2", 105.0)
        with patch("p02_capabilities.time.time", lambda: 100.0):
            with self.assertRaises(Cancelled):
                sip.place(self.scope_identity, quote, stop)
        self.assertEqual(dialled, [])

    def test_06_missing_original_native_package_is_explicit_hold(self):
        with patch.dict(sys.modules, {"helion_voice": None}):
            with self.assertRaisesRegex(RouteHold, "ORIGINAL_VOICE_NATIVE_MODULES_HOLD"):
                OriginalVoicePort(None, None, None, lambda *_: None, use_local_model=False)


class G2BHostCaptureR30(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = sqlite3.connect(":memory:")
        self.store = P02Store(self.db, Path(self.tmp.name) / "store")
        self.store.initialize()
        self.store.create_chat("t", "alice", "chat")
        self.identity = Identity("t", "alice", "core-1", "persona-1", "session")
        self.scope = NativeScope("t", "alice", "chat", "S-1-5-21-123-456-789",
                                 "session", self.identity)
        self.captured = {"a"*32: b"CAPTURED"}
        self.discarded = []
        self.pipeline = LocalVoicePipeline(lambda *_: "Привет", lambda *_: "Hola",
                                           lambda *_: b"LOCAL", approved_models=True,
                                           permitted_voices=frozenset({"es-v"}))
        self.ports = OwnerTwoPorts(
            store=self.store, native_authorize=lambda *_: True,
            voice_pipeline=self.pipeline, native_take_audio=lambda _, cap: self.captured.pop(cap),
            native_mic_consent=lambda *_: True,
            native_store_output_audio=lambda *_: "b"*32,
            native_discard_output_audio=lambda _, receipt: self.discarded.append(receipt) or True,
            owner_ready=lambda *_: True)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def request(self, **kwargs):
        args = dict(capture_id="a"*32, source="ru", target="es", voice="es-v")
        args.update(kwargs)
        return args

    def test_07_rejects_page_consent_before_consuming_capture(self):
        with self.assertRaises(PermissionError):
            self.ports.captured_voice(self.scope, self.request(microphone_consent=True))
        self.assertIn("a"*32, self.captured)

    def test_08_rejects_missing_native_mic_permission_before_consumption(self):
        self.ports.mic_consent = lambda *_: False
        with self.assertRaisesRegex(PermissionError, "NATIVE_MIC_CONSENT_REQUIRED"):
            self.ports.captured_voice(self.scope, self.request())
        self.assertIn("a"*32, self.captured)

    def test_09_invalid_language_does_not_consume_capture(self):
        with self.assertRaises(ValueError):
            self.ports.captured_voice(self.scope, self.request(source="en"))
        self.assertIn("a"*32, self.captured)

    def test_10_stop_during_output_persistence_discards_receipt(self):
        stop = threading.Event()
        def store(*_):
            stop.set()
            return "b"*32
        self.ports.store_output_audio = store
        with self.assertRaisesRegex(RouteHold, "NATIVE_VOICE_STOPPED_DURING_OUTPUT_PERSISTENCE"):
            self.ports.captured_voice(self.scope, self.request(), stop=stop)
        self.assertEqual(self.discarded, ["b"*32])

    def test_11_missing_discard_ack_remains_hold(self):
        stop = threading.Event()
        def store(*_):
            stop.set()
            return "b"*32
        self.ports.store_output_audio = store
        self.ports.discard_output_audio = lambda *_: False
        with self.assertRaisesRegex(RouteHold, "CLEANUP_HOLD"):
            self.ports.captured_voice(self.scope, self.request(), stop=stop)

    def test_12_nonboolean_model_approval_never_advertises_ready(self):
        self.pipeline.approved_models = "yes"
        self.assertFalse(self.ports.available("chat.voice"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
