"""Source integration proof against pinned REAL owner2 P02 and PACK01 Python host.
Only a local /api/tags loopback fixture. No model download, installer or GPU.
"""
import importlib
import json
import os
import pathlib
import socketserver
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from p03_onehost_port import P03OneHostPort, P03PortDenied, P03PortHold, ROUTES

P02 = os.environ.get("NOX_PINNED_P02_PATH")
PACK = os.environ.get("NOX_PINNED_PACK01_PATH")
if not P02 or not PACK:
    raise RuntimeError("Pinned owner2 and PACK01 source paths required; no substitute")
sys.path.insert(0, str(pathlib.Path(P02).resolve()))
sys.path.insert(0, str(pathlib.Path(PACK).resolve()))
from p02_runtime import OllamaClient  # actual owner #2 code
import native_bridge as pack01  # actual existing E06 PACK01 dispatcher

class TagsHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args): return
    def do_GET(self):
        if self.path != "/api/tags":
            self.send_error(404); return
        payload = json.dumps({"models": [
            {"name": "qwen3:4b"}, {"name": "tinyllama:1.1b"}
        ]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

class Server(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class Backend:
    """Only to test binding and native consent. Not a downloader implementation."""
    def __init__(self): self.calls = []
    def available(self): return True
    def pull(self, session, payload):
        self.calls.append(("pull", session.principal))
        return {"status": "HOLD_EXTERNAL_OWNER_EXECUTION"}
    def queue(self, session, payload): return {"jobs": []}

class P03HostPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = Server(("127.0.0.1", 0), TagsHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.catalog = json.loads((pathlib.Path(PACK)/"catalog.json").read_text(encoding="utf-8"))
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join(timeout=3)

    def setUp(self):
        self.client = OllamaClient("http://127.0.0.1:" + str(self.http.server_port), timeout=5)
        self.port = P03OneHostPort(self.client)
        self.dispatch = pack01.NoxPackHost(self.catalog)
        self.registered = self.port.register(self.dispatch, pack01.BoundPort, receipt="P03_SOURCE_PROVENANCE_TEST_ONLY")
        self.session = pack01.NativeSession("tenant", "principal", "chat",
            allowed=frozenset(ROUTES), private_approved=frozenset())

    def test_01_original_catalog_not_installable(self):
        self.assertEqual(self.registered, frozenset({"models.catalog","models.installed"}))
        r = self.dispatch.execute("models.catalog", {"query":"qwen"}, self.session)
        self.assertGreater(len(r["models"]), 0)
        self.assertTrue(all(not x["downloadEligible"] and
                            x["reviewStatus"] == "REVIEW_REQUIRED" for x in r["models"]))
        self.assertEqual(len(self.dispatch.execute("models.catalog", {}, self.session)["models"]),30)

    def test_02_existing_p02_ollama_actual_tags(self):
        r = self.dispatch.execute("models.installed",{},self.session)
        self.assertEqual([x["tag"] for x in r["models"]],["qwen3:4b","tinyllama:1.1b"])
        self.assertTrue(all(x["installed"] and x["digest"] is None for x in r["models"]))
        self.assertFalse(r["digestVerified"])

    def test_03_unbound_actions_hold_no_second_downloader(self):
        self.assertEqual(len(self.registered),2)
        self.assertEqual(len(self.dispatch.ports),2)
        with self.assertRaises(pack01.HostHold):
            self.dispatch.execute("models.pull",{},pack01.NativeSession(
                "tenant","principal","chat",allowed=frozenset({"models.pull"}),
                private_approved=frozenset({"models.pull"})))

    def test_04_unapproved_session_denied(self):
        with self.assertRaises(pack01.HostDenied):
            self.dispatch.execute("models.installed",{},pack01.NativeSession(
                "tenant","principal","chat",allowed=frozenset()))
        with self.assertRaises(P03PortDenied):
            self.port.installed(SimpleNamespace(tenant="tenant",principal="p",chat_id="c",
                                                 allowed=frozenset()),{})

    def test_05_owner3_port_needs_real_existing_client(self):
        with self.assertRaises(ValueError):
            P03OneHostPort(object())

    def test_06_backend_requires_native_approval(self):
        backend = Backend()
        state = {"approved": False}
        port = P03OneHostPort(self.client,owner3_backend=backend,
             native_approve=lambda session,route,payload: state["approved"])
        host = pack01.NoxPackHost(self.catalog,native_approve=lambda s,r,p:state["approved"])
        bound = port.register(host,pack01.BoundPort,receipt="P03_BACKEND_MOCK_SOURCE_ONLY")
        self.assertEqual(bound, frozenset(("models.catalog","models.installed","models.pull","models.queue")))
        session = pack01.NativeSession("tenant","principal","chat",
            allowed=frozenset(ROUTES),private_approved=frozenset({"models.pull"}))
        with self.assertRaises(pack01.HostDenied):
            host.execute("models.pull",{"userApproval":True},session)
        self.assertEqual(backend.calls,[])
        state["approved"]=True  # native out-of-band test fixture, not JS
        result = host.execute("models.pull",{},session)
        self.assertEqual(result["status"],"HOLD_EXTERNAL_OWNER_EXECUTION")
        self.assertEqual(backend.calls,[("pull","principal")])

    def test_07_catalog_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=json.loads((HERE/"catalog30.discovery.json").read_text(encoding="utf-8"))
            base["models"][0]["downloadEligible"]=True
            path=pathlib.Path(tmp)/"catalog.json"
            path.write_text(json.dumps(base),encoding="utf-8")
            with self.assertRaises(P03PortHold):
                P03OneHostPort(self.client,catalog_path=path)

    def test_08_existing_50_route_host_not_replaced(self):
        self.assertEqual(len(self.dispatch.routes),50)
        self.assertEqual(len(self.dispatch.ports),2)
        self.assertEqual(sum(v["enabled"] for v in self.dispatch.advertise(self.session).values()),2)

if __name__ == "__main__":
    unittest.main()
