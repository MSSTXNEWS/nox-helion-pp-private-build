"""E06 R05: real owner-module contract for ONE physical Ollama listener.

Runs only after pinned P02/P04 sources and onehost module are in sys.path,
exactly as test_onehost_p02_p04.py requires. Offline wire; no real GPU claim.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import test_onehost_p02_p04 as owner_tests


class E06ListenerIdentityContract(unittest.TestCase):
    def setUp(self):
        # Reuse the exact E06 + real-owner fixture (SQLite :memory: only in TEST).
        self.fixture = owner_tests.OneHostOwnerContract(
            "test_01_same_existing_sqlite_and_owner_instances")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def _bind(self, client_base: str, rag_base: str):
        f = self.fixture
        wire = owner_tests.OfflineOllamaWire()
        wire.base = client_base
        chat = owner_tests.ChatBridge(f.store, wire)
        rag = owner_tests.LocalRag(
            rag_base, "offline-embed", Path(f.tmp.name) / "rag-listener.json")
        return owner_tests.P02P04OneHost(
            chat=chat, store=f.store, rag=rag, **f.native)

    def test_same_port_localhost_vs_ipv4_requires_owner_receipt(self):
        with self.assertRaisesRegex(owner_tests.OneHostHold,
                                    "ONE_OLLAMA_LISTENER_IDENTITY_REQUIRED"):
            self._bind("http://127.0.0.1:11434", "http://localhost:11434")

    def test_same_port_ipv6_vs_ipv4_requires_owner_receipt(self):
        with self.assertRaisesRegex(owner_tests.OneHostHold,
                                    "ONE_OLLAMA_LISTENER_IDENTITY_REQUIRED"):
            self._bind("http://127.0.0.1:11434", "http://[::1]:11434")

    def test_identical_ipv4_listener_uses_existing_owner_instances(self):
        f = self.fixture
        seam = self._bind("http://127.0.0.1:11434", "http://127.0.0.1:11434")
        self.assertIs(seam.store, f.store)
        self.assertIsNotNone(seam.chat.rag_context)

    def test_identical_localhost_listener_allowed_without_new_server(self):
        seam = self._bind("http://localhost:11434", "http://localhost:11434")
        self.assertTrue(callable(seam.chat.rag_context))

    def test_different_port_keeps_existing_port_guard(self):
        with self.assertRaisesRegex(owner_tests.OneHostHold,
                                    "ONE_OLLAMA_ENDPOINT_PORT_REQUIRED"):
            self._bind("http://127.0.0.1:11434", "http://127.0.0.1:11435")


if __name__ == "__main__":
    unittest.main()
