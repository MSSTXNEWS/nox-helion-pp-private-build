"""Guard the ORIGINAL P02 adapter against provider frames after done=True.

No real Ollama model, Windows runtime or E07 release PASS is inferred here.
Uses the existing P02 test fixtures and real adapter implementation.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

FIXTURE = Path(__file__).with_name("test_original_atomic_stream_stop_u08.py")
SPEC = importlib.util.spec_from_file_location("nox_p02_atomic_fixture_u11", FIXTURE)
fixture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fixture
SPEC.loader.exec_module(fixture)
native = fixture.native


class TerminalDoneFenceU11(unittest.TestCase):
    def setUp(self):
        self.case = fixture.NativeAtomicStreamStopU08()
        self.case.setUp()

    def test_single_terminal_chunk_still_persists_atomic_exchange(self):
        self.case.client.chunks = [{"delta": "answer", "done": True}]
        self.assertEqual(self.case.invoke(), {"answer": "answer", "done": True})
        self.assertEqual(len(self.case.store.exchanges), 1)
        self.assertEqual([x["delta"] for x in self.case.events], ["answer"])

    def test_tail_after_terminal_cannot_emit_or_persist(self):
        self.case.client.chunks = [
            {"delta": "trusted", "done": True},
            {"delta": "untrusted tail", "done": False},
        ]
        with self.assertRaisesRegex(native.HostHold, "terminal completion"):
            self.case.invoke()
        self.assertEqual(self.case.store.exchanges, [])
        self.assertEqual([x["delta"] for x in self.case.events], ["trusted"])

    def test_duplicate_terminal_cannot_commit_second_frame(self):
        self.case.client.chunks = [
            {"delta": "trusted", "done": True},
            {"delta": "", "done": True},
        ]
        with self.assertRaisesRegex(native.HostHold, "terminal completion"):
            self.case.invoke()
        self.assertEqual(self.case.store.exchanges, [])
        self.assertEqual([x["delta"] for x in self.case.events], ["trusted"])

    def test_missing_terminal_still_holds_without_persistence(self):
        self.case.client.chunks = [{"delta": "incomplete", "done": False}]
        with self.assertRaises(native.HostHold):
            self.case.invoke()
        self.assertEqual(self.case.store.exchanges, [])


if __name__ == "__main__":
    unittest.main()
