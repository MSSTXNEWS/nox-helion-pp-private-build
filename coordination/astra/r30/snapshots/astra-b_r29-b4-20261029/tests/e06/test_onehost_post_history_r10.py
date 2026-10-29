"""E06 R10: existing SQLite history is an untrusted wait boundary.

Offline owner stub tests. Passing these DOES NOT establish real SQLite/WPF/GPU E2E.
"""
from __future__ import annotations

import threading
import unittest

from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope, SEAM


class PostHistoryAdmissionGate(unittest.TestCase):
    def setUp(self):
        fixture = E06StopInterlock("test_05_normal_frame_and_owner_stop_token_survive")
        fixture.setUp()
        self.f = fixture
        self.seam = fixture.seam
        self.scope = NativeScope()
        self.advanced = []

        def owner(*_):
            self.advanced.append("owner_next")
            yield {"type": "chat.sources", "sources": [{"id": "private"}]}
        fixture.chat.send = owner

    def _run(self):
        stream = self.seam.stream_chat(self.scope, "installed", "prompt", threading.Event())
        return next(stream)

    def test_01_history_mutates_p02_rag_callback_before_owner_next(self):
        def history(*_):
            self.f.chat.rag_context = lambda *_: None
            return []
        self.f.chat.store.history = history
        with self.assertRaisesRegex(SEAM.OneHostHold, "OWNER_RUNTIME_BINDING_CHANGED"):
            self._run()
        self.assertEqual(self.advanced, [])

    def test_02_history_mutates_existing_p04_ollama_endpoint(self):
        def history(*_):
            self.seam.rag.endpoint = "http://127.0.0.1:9999/api/embed"
            return []
        self.f.chat.store.history = history
        with self.assertRaisesRegex(SEAM.OneHostHold, "OWNER_RUNTIME_BINDING_CHANGED"):
            self._run()
        self.assertEqual(self.advanced, [])

    def test_03_history_revokes_native_chat_permission_before_owner_next(self):
        state = {"allowed": True}
        def history(*_):
            state["allowed"] = False
            return []
        self.f.chat.store.history = history
        self.seam._authorize = lambda *_: state["allowed"]
        with self.assertRaisesRegex(PermissionError, "NATIVE_OWNER_ROUTE_DENIED"):
            self._run()
        self.assertEqual(self.advanced, [])

    def test_04_history_changes_session_sid_before_owner_next(self):
        state = {"sid": "S-1-5-21-1234"}
        def history(*_):
            state["sid"] = "S-1-5-21-9876"
            return []
        self.f.chat.store.history = history
        self.seam._native_sid = lambda *_: state["sid"]
        with self.assertRaisesRegex(PermissionError, "NATIVE_WINDOWS_SID_MISMATCH"):
            self._run()
        self.assertEqual(self.advanced, [])

    def test_05_history_changes_context_chat_before_owner_next(self):
        state = {"chat": "existing"}
        def history(*_):
            state["chat"] = "unapproved-conversation"
            return []
        self.f.chat.store.history = history
        self.seam._native_context_chat = lambda *_: state["chat"]
        with self.assertRaisesRegex(PermissionError, "NATIVE_CONTEXT_NOT_BOUND_TO_EXISTING_CHAT"):
            self._run()
        self.assertEqual(self.advanced, [])

    def test_06_normal_history_still_streams_private_citations(self):
        self.assertEqual(self._run()["type"], "chat.sources")
        self.assertEqual(self.advanced, ["owner_next"])

    def test_07_gpu_ack_owner_history_wait_revocation_is_not_returned(self):
        state = {"allowed": True}
        self.seam._authorize = lambda *_: state["allowed"]
        def history(*_):
            state["allowed"] = False
            return []
        self.f.chat.store.history = history
        executed = []
        def owner_gpu(*_):
            executed.append("executed")
            return {"worker_id": "w1", "command": "gpu.pause", "status": "ACK_ONLY"}
        self.seam._gpu = owner_gpu
        self.seam._verify_ack = lambda *_: True
        with self.assertRaisesRegex(PermissionError, "NATIVE_OWNER_ROUTE_DENIED"):
            self.seam.gpu_command(self.scope, "gpu.pause", "w1")
        self.assertEqual(executed, [], "revoked permission must never invoke P04 worker")

    def test_08_event_publish_owner_history_wait_revocation_is_not_sent(self):
        state = {"allowed": True}
        self.seam._authorize = lambda *_: state["allowed"]
        def history(*_):
            state["allowed"] = False
            return []
        self.f.chat.store.history = history
        published = []
        verified = []
        def verify_v3(*_):
            verified.append("verified")
            return True
        self.seam._verify_v3 = verify_v3
        self.seam._publish_v3 = lambda event: published.append(event)
        event = {"schema": "NOX-INSTALLER-EVENT-v3", "package_id": "P04",
                 "event_type": "training.step", "evidence_verified": True}
        with self.assertRaisesRegex(PermissionError, "NATIVE_OWNER_ROUTE_DENIED"):
            self.seam.publish_owner_gpu_event(self.scope, event)
        self.assertEqual(published, [])
        self.assertEqual(verified, [], "revoked permission must not even verify owner event")


if __name__ == "__main__":
    unittest.main()
