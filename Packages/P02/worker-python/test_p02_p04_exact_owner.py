"""NOX V16 E02: exact original P04 LocalRag through P02 store / ChatBridge / route.

Windows component proof only; original Windows host and physical Ollama remain unverified.
The P04 module is loaded READ-ONLY from an immutable owner checkout, never copied
into another running RAG service. No model, provider or dataset downloads.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from p02_capabilities import Identity
from p02_chat_bridge import ChatBridge
from p02_owner_route_ports import NativeScope, OwnerTwoPorts, RouteHold
from p02_runtime import P02Store

P04_SOURCE = os.environ.get("NOX_P04_SOURCE_DIR", "")
SID_A = "S-1-5-21-1100"
SID_B = "S-1-5-21-2200"


class EmbedFixture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != "/api/embed":
            self.send_error(404)
            return
        amount = int(self.headers.get("Content-Length", "0"))
        if amount < 1 or amount > 64 * 1024:
            self.send_error(413)
            return
        raw = json.loads(self.rfile.read(amount))
        if raw.get("model") != "fixture-embed" or raw.get("truncate") is not False:
            self.send_error(400)
            return
        rows = []
        for text in raw["input"]:
            rows.append([1.0, 0.0, 0.0] if "alpha" in text.lower() else [0.0, 1.0, 0.0])
        result = json.dumps({"embeddings": rows}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)


@unittest.skipUnless(P04_SOURCE, "P04 exact owner checkout required")
class OneRagOneChatWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(P04_SOURCE).resolve(strict=True) / "rag_python_compat.py"
        if not source.is_file():
            raise RuntimeError("P04 exact owner RAG implementation missing")
        spec = importlib.util.spec_from_file_location("nox_exact_p04", source)
        if spec is None or spec.loader is None:
            raise RuntimeError("P04 source loader unavailable")
        cls.rag_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.rag_module)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), EmbedFixture)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.worker.join(timeout=5)
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = P02Store(self.db, Path(self.tmp.name) / "attachments")
        self.store.initialize()
        self.store.create_chat("tenant", "alice", "chat")
        self.store.create_chat("tenant", "alice", "other")
        self.index_path = Path(self.tmp.name) / "existing_index.json"
        self.rag = self.rag_module.LocalRag(
            f"http://127.0.0.1:{self.server.server_port}/",
            "fixture-embed", self.index_path)
        self.rag.ingest_text(SID_A, "chat", "src-alpha", "facts.md", "alpha fact document")
        self.rag.ingest_text(SID_B, "chat", "src-private", "secret.md", "alpha private other owner")
        self.scope = NativeScope("tenant", "alice", "chat", SID_A, "session",
                                 Identity("tenant", "alice", "core-1", "persona-1", "session"))
        self.ready = True
        self.routes = OwnerTwoPorts(
            store=self.store,
            native_authorize=lambda scope, route: scope == self.scope and route == "chat.rag",
            rag_index=self.rag,
            owner_ready=lambda route: self.ready and route == "chat.rag")

    def test_real_p04_local_index_bound_through_one_p02_store(self):
        result = self.routes.rag_context(self.scope, {"query": "alpha", "top_k": 5})
        self.assertEqual([s["source_id"] for s in result["sources"]], ["src-alpha"])
        self.assertIn("alpha fact document", result["context"])
        self.assertNotIn("alpha private other owner", result["context"])
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.json"))), 1)
        self.assertEqual(self.store.history("tenant", "alice", "chat"), [])

    def test_same_existing_rag_in_real_p02_chatbridge(self):
        callback = self.rag_module.p02_callback(
            self.rag, lambda tenant, principal: SID_A if (tenant, principal) == ("tenant", "alice") else SID_B)

        class ChatFixture:
            def models(self):
                return ["installed-fixture"]
            def stop(self):
                pass
            def stream(self, model, messages, stop):
                self.seen = messages
                yield {"delta": "confirmed", "done": False}
                yield {"delta": "", "done": True}

        llm = ChatFixture()
        chat = ChatBridge(self.store, llm, rag_context=callback)
        events = list(chat.send("tenant", "alice", "chat", "installed-fixture", "alpha?"))
        self.assertEqual([e["type"] for e in events],
                         ["chat.start", "chat.sources", "chat.delta", "chat.complete"])
        self.assertEqual([s["source_id"] for s in events[1]["sources"]], ["src-alpha"])
        self.assertEqual([x["role"] for x in self.store.history("tenant", "alice", "chat")],
                         ["user", "assistant"])
        self.assertTrue(any("Untrusted reference excerpts" in m["content"]
                            for m in llm.seen))
        self.assertEqual(self.store.history("tenant", "alice", "other"), [])

    def test_acl_and_owner_provider_holds_without_side_effects(self):
        denied = NativeScope("tenant", "alice", "other", SID_A, "session",
                             Identity("tenant", "alice", "core-1", "persona-1", "session"))
        with self.assertRaises(PermissionError):
            self.routes.rag_context(denied, {"query": "alpha"})
        self.ready = False
        with self.assertRaises(RouteHold):
            self.routes.rag_context(self.scope, {"query": "alpha"})
        self.assertEqual(self.store.history("tenant", "alice", "chat"), [])

    def test_exact_pack01_native_dispatcher_uses_existing_rag_owner_port(self):
        """The real unchanged 50-route PACK01 dispatcher executes our P04 owner port."""
        pack_root = os.environ.get("NOX_PACK01_CHECKOUT")
        if not pack_root:
            self.skipTest("Immutable PACK01 dispatcher checkout required")
        src = Path(pack_root).resolve(strict=True)
        spec = importlib.util.spec_from_file_location("nox_pinned_pack01", src / "native_bridge.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Pinned native PACK01 dispatcher missing")
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        from p02_owner_route_ports import register_with_existing_pack01
        dispatcher = module.NoxPackHost(json.loads((src / "catalog.json").read_text("utf-8")))
        session = module.NativeSession(
            "tenant", "alice", "chat", allowed=frozenset({"chat.rag"}))
        def native_scope(s):
            if (s.tenant, s.principal, s.chat_id) != ("tenant", "alice", "chat"):
                raise PermissionError("Foreign native session")
            return self.scope
        bound = register_with_existing_pack01(
            dispatcher, module.BoundPort, native_scope, self.routes,
            receipt="E02-P04-CROSSOWNER-PINNED")
        self.assertEqual(bound, frozenset({"chat.rag", "chat.voice", "calls.history"}))
        answer = dispatcher.execute("chat.rag", {"query": "alpha"}, session)
        self.assertEqual([x["source_id"] for x in answer["sources"]], ["src-alpha"])
        self.assertIn("alpha fact document", answer["context"])
        with self.assertRaises(PermissionError):
            dispatcher.execute("chat.rag", {"query": "alpha"},
                module.NativeSession("other", "unknown", "chat", allowed=frozenset({"chat.rag"})))
        self.assertEqual(dispatcher.advertise(session)["chat.voice"]["state"], "HOLD")
        self.assertEqual(dispatcher.advertise(session)["calls.history"]["state"], "HOLD")

    def test_p04_index_deletion_uses_same_p02_authorized_scope(self):
        self.assertTrue(self.rag.delete_source(SID_A, "chat", "src-alpha"))
        self.assertEqual(self.routes.rag_context(self.scope, {"query": "alpha"})["sources"], [])
        self.assertEqual([x["source_id"] for x in self.rag.search(SID_B, "chat", "alpha")],
                         ["src-private"])
        self.assertEqual(self.store.history("tenant", "alice", "chat"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
