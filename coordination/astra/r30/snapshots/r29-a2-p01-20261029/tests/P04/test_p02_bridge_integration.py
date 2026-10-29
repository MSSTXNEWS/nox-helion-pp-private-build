"""Pinned cross-owner P02 ChatBridge + P04 RAG fixture."""
import os
import sys
import tempfile
from pathlib import Path
from http.server import HTTPServer
from threading import Thread
import unittest
from test_python_host_rag_compat import EmbedFixture, rag, OWNER_A

@unittest.skipUnless(os.getenv("NOX_P02_SOURCE_DIR"), "P02 source not staged")
class P02BridgeIntegration(unittest.TestCase):
    def test_actual_bridge_with_provenance(self):
        root = os.getenv("NOX_P02_SOURCE_DIR")
        sys.path.insert(0, root)
        try:
            from p02_chat_bridge import ChatBridge
            class Store:
                def __init__(self): self.rows=[]
                def history(self,*args): return []
                def add_message(self,*args): self.rows.append(args)
            class Ollama:
                def models(self): return ["fixture-chat"]
                def stream(self,model,messages,stop):
                    assert any("Untrusted reference excerpts" in m["content"] for m in messages)
                    yield {"delta":"reply","done":False}
                    yield {"delta":"","done":True}
            server = HTTPServer(("127.0.0.1",0), EmbedFixture)
            worker = Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    index=rag.LocalRag("http://127.0.0.1:%d/"%server.server_port,
                        "fixture-embed",Path(tmp)/"index.json")
                    index.ingest_text(OWNER_A,"chat","source1","facts.md","alpha content")
                    store=Store()
                    bridge=ChatBridge(store,Ollama(),
                         rag_context=rag.p02_callback(index,lambda t,p:OWNER_A))
                    events=list(bridge.send("tenant","principal","chat","fixture-chat","alpha?"))
                    self.assertEqual([e["type"] for e in events],
                        ["chat.start","chat.sources","chat.delta","chat.complete"])
                    self.assertEqual(events[1]["sources"][0]["source_id"],"source1")
                    self.assertEqual(len(store.rows),2)
            finally:
                server.shutdown();worker.join(timeout=3);server.server_close()
        finally:
            sys.path.remove(root)
