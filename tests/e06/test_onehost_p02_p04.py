"""E06 real owner-module, offline contract tests. No real Ollama/GPU/EXE claims.

CI must check out pinned full P02 and P04 SOURCE commits separately.
Missing sources are a failure, never a silent skip.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
P02 = Path(os.environ.get("NOX_P02_SOURCE", str(HERE / "Packages/P02/worker-python")))
P04 = Path(os.environ.get("NOX_P04_SOURCE", str(HERE / "Packages/P04")))
for folder, sentinel in ((P02, "p02_chat_bridge.py"), (P04, "rag_python_compat.py")):
    if not (folder / sentinel).is_file():
        raise RuntimeError(f"OWNER_SOURCE_NOT_CHECKED_OUT: {folder / sentinel}")
sys.path[:0] = [str(HERE / "coordination/e06"), str(P02), str(P04)]

from onehost_p02_p04 import OneHostHold, P02P04OneHost
from p02_runtime import Cancelled, OllamaClient, P02Store
from p02_chat_bridge import ChatBridge
from p02_capabilities import Identity
from p02_owner_route_ports import NativeScope
from rag_python_compat import LocalRag


class OfflineOllamaWire(OllamaClient):
    """Deterministic override of existing owner client; no HTTP/model loaded."""
    def __init__(self):
        super().__init__(base="http://127.0.0.1:11434")
        self.seen_messages = None

    def models(self):
        return ["offline-test-model"]

    def stream(self, model, messages, stop=None):
        self.seen_messages = messages
        yield {"delta": "answer", "done": False}
        if stop is not None and stop.is_set():
            raise Cancelled("native STOP observed")
        yield {"delta": "", "done": True}


class OneHostOwnerContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = P02Store(self.db, Path(self.tmp.name) / "attachments")
        self.store.initialize()
        self.store.create_chat("tenant", "principal", "existing-chat")
        self.llm = OfflineOllamaWire()
        self.chat = ChatBridge(self.store, self.llm)
        self.rag = LocalRag("http://127.0.0.1:11434", "offline-embed",
                            Path(self.tmp.name) / "existing-owner-rag.json")
        self.rag._embeddings = lambda values: [[1.0, 0.0] for _ in values]
        self.sid = "S-1-5-21-4242"
        self.rag.ingest_text(self.sid, "existing-chat", "source-1",
                             "source.md", "Provenance-bound useful source text.")
        self.core_ids = frozenset(f"CORE-{i}" for i in range(1, 9))
        self.personas = frozenset(f"PERSONA-{i}" for i in range(1, 6))
        ident = Identity("tenant", "principal", "CORE-1", "PERSONA-1", "session1")
        self.scope = NativeScope("tenant", "principal", "existing-chat",
                                 self.sid, "session1", ident)
        self.allowed = {"chat.send", "gpu.observe", "gpu.stop", "gpu.pause",
                        "gpu.resume", "gpu.checkpoint", "gpu.status"}
        self.published = []
        self.native = dict(
            native_sid=lambda tenant, principal: self.sid,
            native_context_chat=lambda token, scope: "existing-chat",
            native_authorize=lambda scope, action: action in self.allowed,
            approved_core_ids=self.core_ids,
            approved_personas=self.personas,
            native_verify_registry=lambda cores, personas: (cores == self.core_ids and personas == self.personas),
        )
        self.seam = P02P04OneHost(chat=self.chat, store=self.store,
                                  rag=self.rag, **self.native)

    def test_01_same_existing_sqlite_and_owner_instances(self):
        self.assertIs(self.seam.store, self.store)
        self.assertIs(self.seam.chat, self.chat)
        self.assertIs(self.seam.rag, self.rag)
        self.assertIs(self.seam.store.db, self.db)

    def test_02_actual_rag_context_and_verified_sources(self):
        frames = list(self.seam.stream_chat(self.scope, "offline-test-model", "Help"))
        self.assertEqual([e["type"] for e in frames],
                         ["chat.start", "chat.sources", "chat.delta", "chat.complete"])
        self.assertEqual(frames[1]["sources"][0]["source_id"], "source-1")
        self.assertIn("SHA256:", self.llm.seen_messages[0]["content"])
        self.assertEqual(self.llm.seen_messages[0]["role"], "user")
        self.assertEqual([r["role"] for r in self.store.history(
            "tenant", "principal", "existing-chat")], ["user", "assistant"])

    def test_03_uninstalled_model_refused_before_message_write(self):
        with self.assertRaises(Exception):
            list(self.seam.stream_chat(self.scope, "not-installed", "Help"))
        self.assertEqual(self.store.history("tenant", "principal", "existing-chat"), [])

    def test_04_webview_dict_cannot_become_native_scope(self):
        with self.assertRaises(PermissionError):
            self.seam.stream_chat({"principal": "principal"}, "offline-test-model", "Help")

    def test_05_sid_change_denied(self):
        self.seam._native_sid = lambda t, p: "S-1-5-21-999"
        with self.assertRaises(PermissionError):
            self.seam.stream_chat(self.scope, "offline-test-model", "Help")

    def test_06_core_or_persona_not_in_frozen_owner_registry(self):
        wrong = NativeScope("tenant", "principal", "existing-chat", self.sid, "session1",
                            Identity("tenant", "principal", "ghost", "PERSONA-1", "session1"))
        with self.assertRaises(PermissionError):
            self.seam.stream_chat(wrong, "offline-test-model", "Help")

    def test_07_existing_chat_binding_not_guessed(self):
        self.seam._native_context_chat = lambda token, scope: "another-chat"
        with self.assertRaises(PermissionError):
            self.seam.stream_chat(self.scope, "offline-test-model", "Help")

    def test_08_native_stop_does_not_persist_partial_assistant(self):
        stopped = threading.Event()
        gen = self.seam.stream_chat(self.scope, "offline-test-model", "stop", stopped)
        self.assertEqual(next(gen)["type"], "chat.start")
        self.assertEqual(next(gen)["type"], "chat.sources")
        self.assertEqual(next(gen)["type"], "chat.delta")
        stopped.set()
        self.assertEqual(next(gen)["code"], "STOP")
        self.assertEqual([r["role"] for r in self.store.history(
            "tenant", "principal", "existing-chat")], ["user"])

    def test_09_no_second_rag_override(self):
        with self.assertRaisesRegex(OneHostHold, "RAG_ALREADY_BOUND"):
            P02P04OneHost(chat=self.chat, store=self.store, rag=self.rag, **self.native)

    def test_10_missing_real_gpu_worker_is_hold(self):
        with self.assertRaisesRegex(OneHostHold, "CONTROL_NOT_BOUND"):
            self.seam.gpu_command(self.scope, "gpu.pause", "worker-1")

    def test_11_gpu_ack_without_native_proof_is_hold(self):
        self.seam._gpu = lambda scope, action, worker: {
            "worker_id": worker, "command": action, "verified": True}
        self.seam._verify_ack = lambda ack: False
        with self.assertRaisesRegex(OneHostHold, "OBSERVED_ACK"):
            self.seam.gpu_command(self.scope, "gpu.resume", "worker-1")

    def test_12_native_verified_gpu_ack_is_not_training_completion(self):
        self.seam._gpu = lambda scope, action, worker: {
            "worker_id": worker, "command": action, "status": "ACK_ONLY"}
        self.seam._verify_ack = lambda ack: ack.get("status") == "ACK_ONLY"
        self.assertEqual(self.seam.gpu_command(self.scope, "gpu.stop", "worker-1")
                         ["status"], "ACK_ONLY")

    def test_13_forged_gpu_event_denied(self):
        self.seam._verify_v3 = lambda event: False
        self.seam._publish_v3 = self.published.append
        fake = dict(schema="NOX-INSTALLER-EVENT-v3", package_id="P04",
                    event_type="training.step", evidence_verified=True)
        with self.assertRaisesRegex(OneHostHold, "VERIFIED_EVENT"):
            self.seam.publish_owner_gpu_event(self.scope, fake)
        self.assertEqual(self.published, [])

    def test_14_verified_owner_gpu_event_forwarded_unchanged(self):
        signed = dict(schema="NOX-INSTALLER-EVENT-v3", package_id="P04",
                      event_type="gpu.sample", evidence_verified=True,
                      receipt="TRUSTED_BY_TEST_ONLY")
        self.seam._verify_v3 = lambda event: event.get("receipt") == "TRUSTED_BY_TEST_ONLY"
        self.seam._publish_v3 = self.published.append
        self.seam.publish_owner_gpu_event(self.scope, signed)
        self.assertEqual(self.published, [signed])

    def test_16_missing_original_registry_receipt_hold(self):
        options = dict(self.native)
        options["native_verify_registry"] = lambda cores, personas: False
        with self.assertRaisesRegex(OneHostHold, "ORIGINAL_P01_CORE_PERSONA_RECEIPT"):
            P02P04OneHost(chat=ChatBridge(self.store, self.llm),
                          store=self.store, rag=self.rag, **options)

    def test_17_second_ollama_port_hold(self):
        other = OfflineOllamaWire()
        other.base = "http://127.0.0.1:11435"
        with self.assertRaisesRegex(OneHostHold, "ONE_OLLAMA_ENDPOINT_PORT"):
            P02P04OneHost(chat=ChatBridge(self.store, other),
                          store=self.store, rag=self.rag, **self.native)

    def test_15_helion_target_uses_same_engine(self):
        ident = Identity("tenant", "principal", "HELION", "PERSONA-1", "session1")
        scope = NativeScope("tenant", "principal", "existing-chat",
                            self.sid, "session1", ident)
        result = list(self.seam.stream_chat(scope, "offline-test-model", "hello"))
        self.assertEqual(result[-1]["type"], "chat.complete")


    def test_18_revoked_after_call_before_lazy_first_next(self):
        frames = self.seam.stream_chat(self.scope, "offline-test-model", "Hi")
        self.seam._authorize = lambda scope, action: False
        with self.assertRaisesRegex(PermissionError, "NATIVE_OWNER_ROUTE_DENIED"):
            next(frames)
        self.assertEqual(self.store.history(
            "tenant", "principal", "existing-chat"), [])

    def test_19_revoke_during_stream_stops_before_next_delta(self):
        frames = self.seam.stream_chat(self.scope, "offline-test-model", "Hi")
        self.assertEqual(next(frames)["type"], "chat.start")
        self.seam._authorize = lambda scope, action: False
        with self.assertRaisesRegex(PermissionError, "NATIVE_OWNER_ROUTE_DENIED"):
            next(frames)
        self.assertEqual([r["role"] for r in self.store.history(
            "tenant", "principal", "existing-chat")], ["user"])

    def test_20_rebind_native_chat_midstream_is_denied(self):
        frames = self.seam.stream_chat(self.scope, "offline-test-model", "Hi")
        self.assertEqual(next(frames)["type"], "chat.start")
        self.seam._native_context_chat = lambda token, scope: "unrelated-chat"
        with self.assertRaisesRegex(PermissionError, "NATIVE_CONTEXT_NOT_BOUND"):
            next(frames)
        self.assertEqual([r["role"] for r in self.store.history(
            "tenant", "principal", "existing-chat")], ["user"])



if __name__ == "__main__":
    unittest.main()
