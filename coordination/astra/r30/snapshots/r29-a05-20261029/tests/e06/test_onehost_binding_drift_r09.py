"""E06 R09: proof that pinned P02/P04 owner wiring survives callback waits.

Offline owner-stub contract tests only. No Windows/Ollama/GPU/SQLite E2E proof.
"""
from __future__ import annotations
import threading
import unittest
from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope, SEAM, P02Store, OllamaClient


class OneHostRuntimeBindingRegression(unittest.TestCase):
    def setUp(self):
        f = E06StopInterlock("test_01_cancel_before_first_next_skips_owner")
        f.setUp()
        self.f = f
        self.seam = f.seam
        self.scope = NativeScope()
        self.advanced = []
        def owner(*args):
            self.advanced.append("advanced")
            yield {"type": "chat.start", "run_id": "p02-existing"}
        f.chat.send = owner

    def _assert_blocked_prewrite(self):
        with self.assertRaisesRegex(SEAM.OneHostHold, "OWNER_RUNTIME_BINDING_CHANGED"):
            stream = self.seam.stream_chat(self.scope, "model", "prompt", threading.Event())
            next(stream)
        self.assertEqual(self.advanced, [])

    def test_01_replace_p02_store_is_hold(self):
        self.f.chat.store = P02Store()
        self._assert_blocked_prewrite()

    def test_02_replace_p02_ollama_instance_is_hold(self):
        self.f.chat.ollama = OllamaClient()
        self._assert_blocked_prewrite()

    def test_03_change_ollama_endpoint_is_hold(self):
        self.f.chat.ollama.base = "http://127.0.0.1:44444"
        self._assert_blocked_prewrite()

    def test_04_change_p04_embed_endpoint_is_hold(self):
        self.seam.rag.endpoint = "http://127.0.0.1:44444/api/embed"
        self._assert_blocked_prewrite()

    def test_05_replace_rag_callback_is_hold(self):
        self.f.chat.rag_context = lambda *a: {"context": "injected"}
        self._assert_blocked_prewrite()

    def test_06_native_authorize_switches_callback_is_hold_before_history(self):
        calls = []
        def authorization(scope, op):
            self.f.chat.rag_context = lambda *a: None
            calls.append(op)
            return True
        self.seam._authorize = authorization
        self._assert_blocked_prewrite()
        self.assertEqual(calls, ["chat.send"])

    def test_07_owner_changes_ollama_during_await_is_not_yielded(self):
        def owner(*args):
            self.advanced.append("advanced")
            self.f.chat.ollama.base = "http://127.0.0.1:44444"
            yield {"type": "chat.sources", "sources": [{"source_id": "private"}]}
        self.f.chat.send = owner
        stream = self.seam.stream_chat(self.scope, "model", "prompt", threading.Event())
        with self.assertRaisesRegex(SEAM.OneHostHold, "OWNER_RUNTIME_BINDING_CHANGED"):
            next(stream)
        self.assertEqual(self.advanced, ["advanced"])

    def test_08_gpu_ack_owner_mutates_binding_is_hold(self):
        self.seam._authorize = lambda *a: True
        def worker(scope, cmd, wid):
            self.f.chat.rag_context = lambda *a: None
            return {"worker_id": wid, "command": cmd, "status": "ACK_ONLY"}
        self.seam._gpu = worker
        self.seam._verify_ack = lambda ack: True
        with self.assertRaisesRegex(SEAM.OneHostHold, "OWNER_RUNTIME_BINDING_CHANGED"):
            self.seam.gpu_command(self.scope, "gpu.pause", "w1")

    def test_09_verified_event_owner_mutates_binding_is_not_published(self):
        self.seam._authorize = lambda *a: True
        published = []
        def verify(event):
            self.seam.rag.endpoint = "http://127.0.0.1:44444/api/embed"
            return True
        self.seam._verify_v3 = verify
        self.seam._publish_v3 = lambda event: published.append(event)
        event = {"schema":"NOX-INSTALLER-EVENT-v3", "package_id":"P04",
                 "event_type":"training.step", "evidence_verified":True}
        with self.assertRaisesRegex(SEAM.OneHostHold, "OWNER_RUNTIME_BINDING_CHANGED"):
            self.seam.publish_owner_gpu_event(self.scope, event)
        self.assertEqual(published, [])

    def test_10_original_owner_bindings_still_serve_live_frames(self):
        frames = list(self.seam.stream_chat(self.scope, "model", "prompt"))
        self.assertEqual([frame["type"] for frame in frames], ["chat.start"])
        self.assertEqual(self.advanced, ["advanced"])

if __name__ == "__main__":
    unittest.main()
