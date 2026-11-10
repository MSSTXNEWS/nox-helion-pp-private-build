"""E06 R08: fail-closed JSON wire type and Unicode admission (offline owner stubs).

Exercises the exact E06 seam, NOT genuine Windows, Ollama, GPU, SQLite or E07.
The unchanged R07 STOP contract conflict remains RELEASE HOLD.
"""
from __future__ import annotations
import threading
import unittest
from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope, SEAM


class E06WireTypeGate(unittest.TestCase):
    def setUp(self):
        # Reuse R07 owner stubs; never make another LLM/host/database.
        self.fixture = E06StopInterlock("test_01_cancel_before_first_next_skips_owner")
        self.fixture.setUp()
        self.chat = self.fixture.chat
        self.seam = self.fixture.seam
        self.scope = NativeScope()

    def test_01_gpu_list_command_is_hold_not_type_error(self):
        called = []
        self.seam._gpu = lambda *args: called.append(args)
        with self.assertRaisesRegex(SEAM.OneHostHold, "GPU_OWNER_COMMAND_OR_WORKER_INVALID"):
            self.seam.gpu_command(self.scope, ["gpu.stop"], "worker-1")
        self.assertEqual(called, [])

    def test_02_gpu_dict_command_is_hold_not_type_error(self):
        called = []
        self.seam._gpu = lambda *args: called.append(args)
        with self.assertRaisesRegex(SEAM.OneHostHold, "GPU_OWNER_COMMAND_OR_WORKER_INVALID"):
            self.seam.gpu_command(self.scope, {"gpu.stop": True}, "worker-1")
        self.assertEqual(called, [])

    def test_03_chat_frame_list_type_is_hold_not_type_error(self):
        stop = threading.Event()
        def owner(*args):
            yield {"type": ["chat.sources"], "sources": [{"source_id": "secret"}]}
        self.chat.send = owner
        stream = self.seam.stream_chat(self.scope, "installed", "hello", stop)
        with self.assertRaisesRegex(SEAM.OneHostHold, "EXISTING_P02_CHAT_FRAME_TYPE_REQUIRED"):
            next(stream)
        self.assertTrue(stop.is_set())

    def test_04_chat_frame_dict_type_is_hold_not_type_error(self):
        def owner(*args):
            yield {"type": {"chat.delta": True}}
        self.chat.send = owner
        with self.assertRaisesRegex(SEAM.OneHostHold, "EXISTING_P02_CHAT_FRAME_TYPE_REQUIRED"):
            next(self.seam.stream_chat(self.scope, "installed", "hello"))

    def test_05_event_list_type_is_hold_without_publication(self):
        self.seam._authorize = lambda *args: True
        published = []
        self.seam._verify_v3 = lambda *args: True
        self.seam._publish_v3 = lambda e: published.append(e)
        with self.assertRaisesRegex(SEAM.OneHostHold, "EXISTING_P05_V3_VERIFIED_EVENT_REQUIRED"):
            self.seam.publish_owner_gpu_event(self.scope, {
                "schema": "NOX-INSTALLER-EVENT-v3", "package_id": "P04",
                "event_type": ["task.completed"], "evidence_verified": True})
        self.assertEqual(published, [])

    def test_06_event_dict_type_is_hold_without_publication(self):
        self.seam._authorize = lambda *args: True
        published = []
        self.seam._verify_v3 = lambda *args: True
        self.seam._publish_v3 = lambda e: published.append(e)
        with self.assertRaisesRegex(SEAM.OneHostHold, "EXISTING_P05_V3_VERIFIED_EVENT_REQUIRED"):
            self.seam.publish_owner_gpu_event(self.scope, {
                "schema": "NOX-INSTALLER-EVENT-v3", "package_id": "P04",
                "event_type": {"task.completed": 1}, "evidence_verified": True})
        self.assertEqual(published, [])

    def test_07_surrogate_in_chat_payload_is_hold_not_unicode_error(self):
        def owner(*args):
            yield {"type": "chat.delta", "text": "bad\\ud800".replace("\\ud800", "\ud800")}
        self.chat.send = owner
        with self.assertRaisesRegex(SEAM.OneHostHold, "P02_CHAT_FRAME_OWNER_JSON_VALUE_INVALID"):
            next(self.seam.stream_chat(self.scope, "installed", "hello"))

    def test_08_surrogate_in_event_is_hold_without_publication(self):
        self.seam._authorize = lambda *args: True
        called = []
        self.seam._verify_v3 = lambda *args: True
        self.seam._publish_v3 = lambda e: called.append(e)
        with self.assertRaisesRegex(SEAM.OneHostHold, "P05_EVENT_OWNER_JSON_VALUE_INVALID"):
            self.seam.publish_owner_gpu_event(self.scope, {
                "schema": "NOX-INSTALLER-EVENT-v3", "package_id": "P04",
                "event_type": "task.progress", "evidence_verified": True,
                "note": "\ud800"})
        self.assertEqual(called, [])

    def test_09_valid_gpu_ack_still_passes_to_existing_owner(self):
        self.seam._authorize = lambda *args: True
        self.seam._gpu = lambda scope, command, worker: {
            "command": command, "worker_id": worker, "status": "ACK_ONLY"}
        self.seam._verify_ack = lambda payload: payload["status"] == "ACK_ONLY"
        result = self.seam.gpu_command(self.scope, "gpu.pause", "worker-1")
        self.assertEqual(result["status"], "ACK_ONLY")

    def test_10_valid_owner_event_still_publishes_snapshot(self):
        self.seam._authorize = lambda *args: True
        published = []
        self.seam._verify_v3 = lambda *args: True
        self.seam._publish_v3 = lambda e: published.append(e)
        event = {"schema": "NOX-INSTALLER-EVENT-v3", "package_id": "P04",
                 "event_type": "training.step", "evidence_verified": True}
        self.seam.publish_owner_gpu_event(self.scope, event)
        self.assertEqual(published, [event])

    def test_11_valid_chat_frame_still_passes(self):
        def owner(*args):
            yield {"type": "chat.start", "run_id": "existing"}
        self.chat.send = owner
        frame = next(self.seam.stream_chat(self.scope, "installed", "hello"))
        self.assertEqual(frame["type"], "chat.start")


if __name__ == "__main__":
    unittest.main()
