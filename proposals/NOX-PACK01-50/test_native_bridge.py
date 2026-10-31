"""Focused Windows integration test: real owner #2 Ollama client + SQLite store, no second backend."""
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import threading
import socketserver
import http.server
import sqlite3
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nox_native_bridge", ROOT/"native_bridge.py")
bridge=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=bridge
spec.loader.exec_module(bridge)

P02_ROOT=os.environ.get("NOX_P02_OWNER_PATH")
if not P02_ROOT:
    raise RuntimeError("Owner #2 exact pinned checkout path required; no synthetic substitute allowed.")
sys.path.insert(0,P02_ROOT)
from p02_runtime import OllamaClient, P02Store
from unittest.mock import patch
from types import SimpleNamespace

class Server(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path!="/api/tags":self.send_error(404);return
        raw=json.dumps({"models":[{"name":"qwen3:4b"},{"name":"llama3.2:1b"}]}).encode()
        self.send_response(200);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        if self.path!="/api/chat":self.send_error(404);return
        n=int(self.headers.get("Content-Length","0"))
        req=json.loads(self.rfile.read(n))
        assert req["model"] in ("qwen3:4b","llama3.2:1b")
        assert req["messages"][-1]["role"]=="user"
        parts=[
          {"done":False,"message":{"content":"Hola"}},
          {"done":True,"message":{"content":"!"}}
        ]
        raw=b"".join((json.dumps(x)+"\n").encode() for x in parts)
        self.send_response(200);self.send_header("Content-Type","application/x-ndjson")
        self.send_header("Content-Length",str(len(raw)));self.end_headers()
        self.wfile.write(raw)

class ThreadingHTTP(socketserver.ThreadingMixIn,http.server.HTTPServer):
    daemon_threads=True
    allow_reuse_address=True

class BridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTP(("127.0.0.1",0),Server)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.endpoint="http://127.0.0.1:"+str(cls.server.server_port)
        cls.catalog=json.loads((ROOT/"catalog.json").read_text("utf-8"))
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=sqlite3.connect(":memory:",check_same_thread=False)
        self.store=P02Store(self.db,pathlib.Path(self.temp.name))
        self.store.initialize()
        self.store.create_chat("t1","p1","room1")
        self.store.create_chat("t2","p2","room2")
        self.client=OllamaClient(self.endpoint,timeout=8)
        self.dispatch=bridge.NoxPackHost(self.catalog)
        self.owner=bridge.ExistingP02Adapter(self.client,self.store,
            native_selected_file=lambda session:("text/plain",io.BytesIO(b"NOX approved sample")))
        self.bound=self.owner.register(self.dispatch,receipt="NOX-P02-SOURCE-PINNED-TEST")
        self.session=bridge.NativeSession("t1","p1","room1",
            allowed=frozenset(self.bound),private_approved=frozenset({"chat.history","chat.attach"}))
    def tearDown(self):
        self.client.stop();self.db.close();self.temp.cleanup()
    def test_p02_store_without_atomic_exchange_fails_before_registration(self):
        # Native acceptance must reject old P02Store contracts before live chat.
        old_store=SimpleNamespace(history=lambda *a:[],add_message=lambda *a:None,
                                  store_file=lambda *a:None)
        with self.assertRaisesRegex(ValueError,"Existing P02Store required"):
            bridge.ExistingP02Adapter(self.client,old_store)
        self.assertEqual(len(self.dispatch.ports),8)

    def test_catalog_fifty_and_only_eight_real_bindings(self):
        self.assertEqual(len(self.dispatch.routes),50)
        self.assertEqual(len(self.bound),8)
        self.assertEqual(len(self.dispatch.ports),8)
        self.assertEqual(len(self.dispatch.advertise(self.session)),50)
        self.assertEqual(sum(x["enabled"] for x in self.dispatch.advertise(self.session).values()),8)
    def test_installed_models_via_real_owner_ollama(self):
        answer=self.dispatch.execute("chat.model",{},self.session)
        self.assertEqual(answer["models"],["qwen3:4b","llama3.2:1b"])
    def test_live_protocol_and_existing_sqlite_history(self):
        result=self.dispatch.execute("helion.chat",{"model":"qwen3:4b","text":"Привет"},self.session)
        self.assertEqual(result,{"answer":"Hola!","done":True})
        h=self.dispatch.execute("chat.history",{"limit":5},self.session)["messages"]
        # Owner P02 history currently has a same-second ordering regression; don't fake its fix.
        self.assertCountEqual([x["role"] for x in h],["user","assistant"])
        self.assertIn("Hola!",[x["content"] for x in h])
    def test_core_persona_same_engine_but_scoped(self):
        result=self.dispatch.execute("persona.chat",{"model":"qwen3:4b","text":"Hola"},self.session)
        self.assertEqual(result["answer"],"Hola!")
        wrong=bridge.NativeSession("t2","p2","room1",
            allowed=frozenset(self.bound),private_approved=frozenset({"chat.history"}))
        with self.assertRaises(PermissionError):
            self.dispatch.execute("chat.history",{},wrong)
    def test_stop_invokes_actual_owner_stop(self):
        self.assertTrue(self.dispatch.execute("chat.stop",{},self.session)["stopRequested"])
    def test_stop_remains_ready_when_ollama_model_inventory_is_offline(self):
        # Native ACL/route checks remain in NoxPackHost.execute; only STOP's
        # availability is decoupled from Ollama /api/tags.
        with patch.object(self.client,"models",side_effect=OSError("Ollama offline")), \
             patch.object(self.client,"stop",wraps=self.client.stop) as stop:
            self.assertTrue(self.dispatch.advertise(self.session)["chat.stop"]["enabled"])
            self.assertFalse(self.dispatch.advertise(self.session)["helion.chat"]["enabled"])
            self.assertTrue(self.dispatch.execute("chat.stop",{},self.session)["stopRequested"])
            stop.assert_called_once_with()
            with self.assertRaises(bridge.HostHold):
                self.dispatch.execute("helion.chat",{"text":"Hi","model":"qwen3:4b"},self.session)
            with self.assertRaises(bridge.HostDenied):
                self.dispatch.execute("chat.stop",{},bridge.NativeSession(
                    "t1","p1","room1",allowed=frozenset()))
    def test_revoked_native_scope_during_stream_never_persists_chat(self):
        # Regression: trusted Ollama/owner callback revokes current principal's
        # chat route AFTER NoxPackHost pre-dispatch approval but BEFORE commit.
        before=self.store.history("t1","p1","room1")
        def revoked_stream(*_):
            object.__setattr__(self.session,"allowed",frozenset({"chat.history"}))
            yield {"delta":"must-not-persist","done":True}
        with patch.object(self.client,"stream",side_effect=revoked_stream):
            with self.assertRaisesRegex(bridge.HostDenied,"revoked during streaming"):
                self.dispatch.execute("helion.chat",{"model":"qwen3:4b","text":"Hi"},self.session)
        self.assertEqual(self.store.history("t1","p1","room1"),before)

    def test_atomic_exchange_rolls_back_if_native_revoke_between_rows(self):
        before=self.store.history("t1","p1","room1")
        calls=[]
        def scope():
            calls.append(True)
            if len(calls)==2:
                raise bridge.HostDenied("native revoke between rows")
        with self.assertRaisesRegex(bridge.HostDenied,"revoke between rows"):
            self.store.add_exchange("t1","p1","room1","question","answer",authorize=scope)
        self.assertEqual(self.store.history("t1","p1","room1"),before)
        self.assertEqual(len(calls),2)

    def test_stop_in_stream_never_persists_exchange(self):
        before=self.store.history("t1","p1","room1")
        def cancelled_stream(*_):
            self.dispatch.execute("chat.stop",{},self.session)
            yield {"delta":"late answer","done":True}
        with patch.object(self.client,"stream",side_effect=cancelled_stream):
            with self.assertRaisesRegex(bridge.HostDenied,"STOP revoked"):
                self.dispatch.execute("helion.chat",{"model":"qwen3:4b","text":"question"},self.session)
        self.assertEqual(self.store.history("t1","p1","room1"),before)

    def test_owner_p02_same_second_history_order_is_stable(self):
        # P02 owner fixed the same-second ordering bug with SQLite insertion
        # order (rowid for V1, stable_seq for approved V2). Never keep this
        # decorated expectedFailure: a correct owner result becomes an
        # unexpectedSuccess and falsely fails the whole native bridge suite.
        with patch("p02_runtime.time.time",return_value=1730000000), \
             patch("p02_runtime.uuid.uuid4",side_effect=[
                 SimpleNamespace(hex="f"*32),SimpleNamespace(hex="0"*32)]):
            self.store.add_message("t1","p1","room1","user","first")
            self.store.add_message("t1","p1","room1","assistant","second")
        roles=[x["role"] for x in self.store.history("t1","p1","room1")]
        self.assertEqual(roles,["user","assistant"])

    def test_native_attachment_uses_existing_scoped_sqlite_and_blob_storage(self):
        attached=self.dispatch.execute("chat.attach",{},self.session)
        self.assertIsInstance(attached["storedAttachment"],dict)
        self.assertEqual(attached["storedAttachment"]["mime"],"text/plain")
        self.assertEqual(attached["storedAttachment"]["bytes"],len(b"NOX approved sample"))

    def test_quick_commands_only_return_host_enabled_native_routes(self):
        result=self.dispatch.execute("chat.commands",{},self.session)
        self.assertIn("helion.chat",result["commands"])
        self.assertIn("chat.attach",result["commands"])
        self.assertNotIn("models.pull",result["commands"])
        self.assertNotIn("system.pc_control",result["commands"])

    def test_uninstalled_model_denied(self):
        with self.assertRaises(bridge.HostHold):
            self.dispatch.execute("helion.chat",{"model":"not-installed","text":"Hi"},self.session)
    def test_unbound_forty_two_actions_hold(self):
        self.assertEqual(len(bridge.ALLOWED_ROUTES-self.bound),42)
        with self.assertRaises(bridge.HostHold):
            self.dispatch.execute("models.pull",{},bridge.NativeSession("t1","p1","room1",
                allowed=frozenset({"models.pull"}),private_approved=frozenset({"models.pull"})))
    def test_native_access_denies_unscoped_or_private(self):
        with self.assertRaises(bridge.HostDenied):
            self.dispatch.execute("chat.history",{},bridge.NativeSession("t1","p1","room1",
                allowed=frozenset({"chat.history"})))
        with self.assertRaises(bridge.HostDenied):
            self.dispatch.execute("chat.stop",{},bridge.NativeSession("t1","p1","room1",
                allowed=frozenset()))
    def test_duplicate_handler_rejected(self):
        with self.assertRaises(bridge.HostDenied):
            self.owner.register(self.dispatch,receipt="NOX-P02-SECOND-CONFLICT")
    def test_wrong_owner_handler_rejected(self):
        with self.assertRaises(bridge.HostHold):
            self.dispatch.bind("models.pull",bridge.BoundPort(lambda s,a:True,lambda:True,"r",2))
    def test_dangerous_requires_fresh_native_approval_even_if_bound(self):
        native_permission={"enabled":False}
        host=bridge.NoxPackHost(self.catalog,native_approve=lambda session,route,args:native_permission["enabled"])
        hit=[]
        port=bridge.BoundPort(lambda s,a:hit.append("called"),lambda:True,"NATIVE-INSTALL-RECEIPT",1)
        host.bind("system.update",port)
        s=bridge.NativeSession("t1","p1","room1",
              allowed=frozenset({"system.update"}),private_approved=frozenset({"system.update"}))
        self.assertFalse(host.advertise(s)["system.update"]["enabled"])
        with self.assertRaises(bridge.HostDenied):
            host.execute("system.update",{},s)
        self.assertEqual(hit,[])
        native_permission["enabled"]=True
        host.execute("system.update",{"untrustedPayloadIgnored":True},s)
        self.assertEqual(hit,["called"])
    def test_oversize_untrusted_payload_rejected(self):
        with self.assertRaises(bridge.HostDenied):
            self.dispatch.execute("helion.chat",{"text":"x"*(2*1024*1024+1)},self.session)
    def test_bad_catalog_not_admitted(self):
        data=dict(self.catalog)
        data["actions"]=self.catalog["actions"][:-1]
        with self.assertRaises(ValueError):
            bridge.NoxPackHost(data)
    def test_no_unapproved_network_or_user_data_side_effect_in_init(self):
        self.assertEqual(self.store.host_schema_inventory(),("p02_attachments","p02_chats","p02_gc","p02_messages","p02_meta"))
        self.assertTrue(self.owner.available())

if __name__=="__main__":unittest.main()
