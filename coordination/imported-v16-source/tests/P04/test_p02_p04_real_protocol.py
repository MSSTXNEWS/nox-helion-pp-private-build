"""Exercise REAL P02+P04 source and SQLite against local Ollama-wire fixture.

No network beyond 127.0.0.1, no installed Ollama/GPU, no new backend/database.
This is a component test; native WebView2->Python IPC remains E06-only.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

P04 = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "rag_python_compat.py"
spec = importlib.util.spec_from_file_location("nox_p04_real_protocol", P04)
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)
OWNER = "S-1-5-21-1100"
OTHER = "S-1-5-21-2200"


class OllamaWireFixture(BaseHTTPRequestHandler):
    """Real HTTP semantics of /api/tags, /api/embed and streamed /api/chat."""

    def reply(self, data: bytes, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/api/tags":
            self.send_error(404)
            return
        self.reply(b'{"models":[{"name":"fixture-chat"}]}')

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 128_000:
                self.send_error(413)
                return
            body = json.loads(self.rfile.read(length))
        except (ValueError, TypeError):
            self.send_error(400)
            return
        if self.path == "/api/embed":
            if body.get("model") != "fixture-embed" or body.get("truncate") is not False:
                self.send_error(400)
                return
            values = body.get("input")
            if not isinstance(values, list) or not values:
                self.send_error(400)
                return
            embeddings = [[1.0, 0.0, 0.0] if "alpha" in x.lower() else
                          [0.0, 1.0, 0.0] for x in values]
            self.reply(json.dumps({"embeddings": embeddings}).encode("utf-8"))
            return
        if self.path == "/api/chat":
            messages = body.get("messages")
            if (body.get("model") != "fixture-chat" or body.get("stream") is not True
                    or not isinstance(messages, list)
                    or not any("Untrusted reference excerpts" in m.get("content", "")
                               for m in messages if isinstance(m, dict))):
                self.send_error(400)
                return
            ndjson = (
                b'{"message":{"content":"fixture answer"},"done":false}\n'
                b'{"message":{"content":""},"done":true}\n'
            )
            self.reply(ndjson, "application/x-ndjson")
            return
        self.send_error(404)

    def log_message(self, *_args):
        pass


@unittest.skipUnless(os.environ.get("NOX_P02_SOURCE_DIR"), "P02 actual source not staged")
class P02P04ActualWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p02_root = os.environ["NOX_P02_SOURCE_DIR"]
        if not Path(cls.p02_root, "p02_runtime.py").is_file() or not Path(
                cls.p02_root, "p02_chat_bridge.py").is_file():
            raise AssertionError("NOX_PINNED_P02_SOURCE_INCOMPLETE")
        sys.path.insert(0, cls.p02_root)
        from p02_runtime import OllamaClient, P02Store
        from p02_chat_bridge import ChatBridge
        cls.OllamaClient, cls.P02Store, cls.ChatBridge = OllamaClient, P02Store, ChatBridge
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaWireFixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=4)
        cls.server.server_close()
        sys.path.remove(cls.p02_root)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = self.P02Store(self.db, Path(self.temp.name) / "attachments")
        self.store.initialize()
        self.store.create_chat("tenant", "principal", "chat")
        base = f"http://127.0.0.1:{self.server.server_port}"
        self.client = self.OllamaClient(base, timeout=4)
        self.index = rag.LocalRag(base + "/", "fixture-embed",
                                  Path(self.temp.name) / "rag-index.json")
        self.index.ingest_text(OWNER, "chat", "ref1", "facts.md", "alpha evidence")
        self.chat = self.ChatBridge(self.store, self.client,
                                   rag.p02_callback(self.index,
                                                    lambda tenant, principal:
                                                    OWNER if (tenant, principal) ==
                                                    ("tenant", "principal") else OTHER))

    def test_real_http_stream_rag_citations_and_sqlite_history(self):
        events = list(self.chat.send("tenant", "principal", "chat",
                                     "fixture-chat", "alpha?"))
        self.assertEqual([e["type"] for e in events],
                         ["chat.start", "chat.sources", "chat.delta", "chat.complete"])
        self.assertEqual(events[1]["sources"][0]["source_id"], "ref1")
        self.assertEqual(events[2]["text"], "fixture answer")
        history = self.store.history("tenant", "principal", "chat")
        self.assertEqual([x["role"] for x in history], ["user", "assistant"])
        self.assertEqual(history[-1]["content"], "fixture answer")
        self.assertEqual(self.index.search(OTHER, "chat", "alpha"), [])

    def test_real_sqlite_acl_rejects_before_embedding_or_chat(self):
        with self.assertRaises(PermissionError):
            list(self.chat.send("tenant", "intruder", "chat",
                                "fixture-chat", "alpha?"))
        self.assertEqual(self.store.history("tenant", "principal", "chat"), [])

    def test_pre_requested_stop_keeps_history_empty(self):
        from p02_runtime import Cancelled
        stopped = threading.Event()
        stopped.set()
        with self.assertRaises(Cancelled):
            list(self.chat.send("tenant", "principal", "chat",
                                "fixture-chat", "alpha?", stopped))
        self.assertEqual(self.store.history("tenant", "principal", "chat"), [])

    def test_missing_installed_model_never_persists_prompt(self):
        from p02_runtime import P02Error
        with self.assertRaisesRegex(P02Error, "not installed"):
            list(self.chat.send("tenant", "principal", "chat",
                                "missing-model", "alpha?"))
        self.assertEqual(self.store.history("tenant", "principal", "chat"), [])

    def test_p04_upsert_and_delete_remain_one_owner_scoped_index(self):
        self.index.ingest_text(OWNER, "chat", "ref1", "facts.md", "alpha revised")
        self.assertEqual(len(self.index.search(OWNER, "chat", "alpha")), 1)
        self.assertFalse(self.index.delete_source(OTHER, "chat", "ref1"))
        self.assertTrue(self.index.delete_source(OWNER, "chat", "ref1"))
        self.assertEqual(self.index.search(OWNER, "chat", "alpha"), [])


if __name__ == "__main__":
    unittest.main()
