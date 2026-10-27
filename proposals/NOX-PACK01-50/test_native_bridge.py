"""Focused Windows integration test: real owner #2 Ollama client + SQLite store, no second backend."""
import importlib.util
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
        self.owner=bridge.ExistingP02Adapter(self.client,self.store)
        self.bound=self.owner.register(self.dispatch,receipt="NOX-P02-SOURCE-PINNED-TEST")
        self.session=bridge.NativeSession("t1","p1","room1",
            allowed=frozenset(self.bound),private_approved=frozenset({"chat.history"}))
    def tearDown(self):
        self.client.stop();self.db.close();self.temp.cleanup()
    def test_catalog_fifty_and_only_six_real_bindings(self):
        self.assertEqual(len(self.dispatch.routes),50)
        self.assertEqual(len(self.bound),6)
        self.assertEqual(len(self.dispatch.ports),6)
        self.assertEqual(len(self.dispatch.advertise(self.session)),50)
        self.assertEqual(sum(x["enabled"] for x in self.dispatch.advertise(self.session).values()),6)
    def test_installed_models_via_real_owner_ollama(self):
        answer=self.dispatch.execute("chat.model",{},self.session)
        self.assertEqual(answer["models"],["qwen3:4b","llama3.2:1b"])
    def test_live_protocol_and_existing_sqlite_history(self):
        result=self.dispatch.execute("helion.chat",{"model":"qwen3:4b","text":"Привет"},self.session)
        self.assertEqual(result,{"answer":"Hola!","done":True})
        h=self.dispatch.execute("chat.history",{"limit":5},self.session)["messages"]
        self.assertEqual([x["role"] for x in h],["user","assistant"])
        self.assertEqual(h[-1]["content"],"Hola!")
    def test_core_persona_same_engine_but_scoped(self):
        result=self.dispatch.execute("persona.chat",{"model":"qwen3:4b","text":"Hola"},self.session)
        self.assertEqual(result["answer"],"Hola!")
        wrong=bridge.NativeSession("t2","p2","room1",
            allowed=frozenset(self.bound),private_approved=frozenset({"chat.history"}))
        with self.assertRaises(PermissionError):
            self.dispatch.execute("chat.history",{},wrong)
    def test_stop_invokes_actual_owner_stop(self):
        self.assertTrue(self.dispatch.execute("chat.stop",{},self.session)["stopRequested"])
    def test_uninstalled_model_denied(self):
        with self.assertRaises(bridge.HostHold):
            self.dispatch.execute("helion.chat",{"model":"not-installed","text":"Hi"},self.session)
    def test_unbound_forty_four_actions_hold(self):
        self.assertEqual(len(bridge.ALLOWED_ROUTES-self.bound),44)
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
