"""Source integration proof against pinned REAL owner2 P02 and PACK01 Python host.
Only a local /api/tags loopback fixture. No model download, installer or GPU.
"""
import importlib
import io
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
from unittest.mock import Mock, patch

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
            {"name": "qwen3:4b", "digest": "sha256:" + "a" * 64},
            {"name": "tinyllama:1.1b"}
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
        self.assertEqual(self.registered, frozenset({"models.catalog","models.installed","models.digest"}))
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

    def test_09_digest_is_only_local_ollama_claim(self):
        result = self.dispatch.execute("models.digest", {"modelTag": "qwen3:4b"}, self.session)
        self.assertEqual(result["ollamaReportedManifestDigest"], "sha256:" + "a" * 64)
        self.assertFalse(result["independentlyVerified"])
        self.assertFalse(result["licenseVerified"])
        self.assertEqual(result["source"], "existing P02 transport /api/tags")

    def test_10_missing_digest_is_unknown_not_installed_rights(self):
        result = self.dispatch.execute("models.digest", {"modelTag": "tinyllama:1.1b"}, self.session)
        self.assertIsNone(result["ollamaReportedManifestDigest"])
        self.assertFalse(result["independentlyVerified"])
        self.assertFalse(result["licenseVerified"])

    def test_11_digest_malformed_local_response_holds(self):
        raw = b'{"models":[{"name":"qwen3:4b","digest":"sha256:broken"}]}'
        with patch.object(self.client, "_open", side_effect=lambda path: io.BytesIO(raw)):
            with self.assertRaises(P03PortHold):
                self.port.digest(self.session, {"modelTag": "qwen3:4b"})

    def test_12_digest_duplicate_or_missing_local_model_holds(self):
        raw = (b'{"models":[{"name":"qwen3:4b","digest":"sha256:' +
               b'a' * 64 + b'"},{"name":"qwen3:4b","digest":"sha256:' + b'b' * 64 + b'"}]}')
        with patch.object(self.client, "_open", side_effect=lambda path: io.BytesIO(raw)):
            with self.assertRaises(P03PortHold):
                self.port.digest(self.session, {"modelTag": "qwen3:4b"})
        with self.assertRaises(P03PortHold):
            self.port.digest(self.session, {"modelTag": "not-installed:1b"})

    def test_13_digest_route_denies_browser_unscoped_user(self):
        other = pack01.NativeSession("tenant", "principal", "chat", allowed=frozenset())
        with self.assertRaises(pack01.HostDenied):
            self.dispatch.execute("models.digest", {"modelTag": "qwen3:4b"}, other)

    def test_03_unbound_actions_hold_no_second_downloader(self):
        self.assertEqual(len(self.registered),3)
        self.assertEqual(len(self.dispatch.ports),3)
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
        self.assertEqual(bound, frozenset(("models.catalog","models.installed","models.digest","models.pull","models.queue")))
        session = pack01.NativeSession("tenant","principal","chat",
            allowed=frozenset(ROUTES),private_approved=frozenset({"models.pull"}))
        with self.assertRaises(P03PortDenied):
            host.execute("models.pull",{"userApproval":True},session)
        self.assertEqual(backend.calls,[])
        state["approved"]=True  # native out-of-band test fixture, not JS
        result = host.execute("models.pull",{},session)
        self.assertEqual(result["status"],"HOLD_EXTERNAL_OWNER_EXECUTION")
        self.assertEqual(backend.calls,[("pull","principal")])

    def test_07_without_native_approval_never_advertise_pull(self):
        backend = Backend()
        port = P03OneHostPort(self.client, owner3_backend=backend)
        host = pack01.NoxPackHost(self.catalog)
        bound = port.register(host,pack01.BoundPort,receipt="P03_NO_NATIVE_CONSENT_TEST")
        self.assertNotIn("models.pull",bound)
        self.assertIn("models.queue",bound)
        self.assertFalse(host.advertise(self.session)["models.pull"]["enabled"])
        self.assertEqual(backend.calls,[])

    def test_07_catalog_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=json.loads((HERE/"catalog30.discovery.json").read_text(encoding="utf-8"))
            base["models"][0]["downloadEligible"]=True
            path=pathlib.Path(tmp)/"catalog.json"
            path.write_text(json.dumps(base),encoding="utf-8")
            with self.assertRaises(P03PortHold):
                P03OneHostPort(self.client,catalog_path=path)

    def test_14_collision_rejects_without_partial_registration(self):
        other = pack01.NoxPackHost(self.catalog)
        other.bind("models.digest", pack01.BoundPort(
            lambda s, p: {"already": True}, lambda: True, "owner3-old", 3))
        before = dict(other.ports)
        with self.assertRaises(P03PortHold):
            self.port.register(other, pack01.BoundPort, receipt="P03_TEST_LOCK")
        self.assertEqual(other.ports, before)
        self.assertNotIn("models.catalog", other.ports)
        self.assertNotIn("models.installed", other.ports)

    def test_15_wrong_owner_map_rejects_without_mutation(self):
        other = pack01.NoxPackHost(self.catalog)
        # Explicit legacy mutable fixture: the modern native host's
        # MappingProxyType owner map must remain read-only in production.
        other.routes = {key: dict(value) for key, value in other.routes.items()}
        other.routes["models.installed"]["owner"] = 2
        with self.assertRaises(P03PortHold):
            self.port.register(other, pack01.BoundPort, receipt="P03_TEST_LOCK")
        self.assertEqual(other.ports, {})

    def test_17_host_bind_failure_after_write_rolls_back(self):
        host = pack01.NoxPackHost(self.catalog)
        host.bind("chat.model", pack01.BoundPort(
            lambda s, p: {"models": []}, lambda: True, "owner2-existing", 2))
        preserved = host.ports["chat.model"]
        native_bind = host.bind
        def reject_after_second(route, port):
            native_bind(route, port)
            if route == "models.installed":
                raise RuntimeError("native host rejected after partial write")
        host.bind = reject_after_second
        with self.assertRaises(P03PortHold):
            self.port.register(host, pack01.BoundPort, receipt="P03_LOCK_TEST")
        self.assertEqual(host.ports, {"chat.model": preserved})

    def test_18_rollback_cannot_delete_foreign_replacement(self):
        host = pack01.NoxPackHost(self.catalog)
        foreign = pack01.BoundPort(
            lambda s, p: {"foreign": True}, lambda: True, "another-owner", 3)
        native_bind = host.bind
        def replace_then_reject(route, port):
            if route == "models.installed":
                host.ports[route] = foreign
                raise RuntimeError("concurrent host inserted port")
            native_bind(route, port)
        host.bind = replace_then_reject
        with self.assertRaises(P03PortHold):
            self.port.register(host, pack01.BoundPort, receipt="P03_LOCK_TEST")
        self.assertEqual(host.ports, {"models.installed": foreign})

    def test_19_port_constructor_failure_cannot_partially_register(self):
        host = pack01.NoxPackHost(self.catalog)
        calls = [0]
        def partial_constructor(*args):
            calls[0] += 1
            if calls[0] == 2:
                raise RuntimeError("cannot construct owner port")
            return pack01.BoundPort(*args)
        with self.assertRaises(RuntimeError):
            self.port.register(host, partial_constructor, receipt="P03_LOCK_TEST")
        self.assertEqual(host.ports, {})

    def test_16_existing_dispatcher_preserved_on_bad_receipt(self):
        other = pack01.NoxPackHost(self.catalog)
        with self.assertRaises(P03PortHold):
            self.port.register(other, pack01.BoundPort, receipt="   ")
        self.assertEqual(other.ports, {})

    def test_08_existing_50_route_host_not_replaced(self):
        self.assertEqual(len(self.dispatch.routes),50)
        self.assertEqual(len(self.dispatch.ports),3)
        self.assertEqual(sum(v["enabled"] for v in self.dispatch.advertise(self.session).values()),3)

if __name__ == "__main__":
    unittest.main()
