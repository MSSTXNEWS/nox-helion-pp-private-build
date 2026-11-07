"""NOX WEB 11–22: executable, isolated tests of original-source patches.

An HTTP protocol stub models Ollama for TESTS ONLY. No mock is installed in NOX;
these checks are not a substitute for real installed Qwen, AMD, S03 or training.
"""
from __future__ import annotations
import json, pathlib, sys, tempfile, threading, time, types, unittest
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib import request, error
from patch_live import read_original,patch_source,sha256

HERE=pathlib.Path(__file__).resolve().parent
BASE=HERE.parent
PAYLOAD=BASE/"NOX_LIVE_PAYLOAD.json"
VOICE=HERE/"voice-live.js"

class SourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files=patch_source(read_original(PAYLOAD),VOICE)
    def test_original_files_and_byte_count(self):
        self.assertEqual(len(self.files),27)
        self.assertTrue(all(len(x)>0 for x in self.files.values()))
        self.assertIn("server_live.py",self.files)
    def test_python_syntax(self):
        compile(self.files["server_live.py"],"server_live.py","exec")
    def test_stop_has_real_terminal_receipt(self):
        s=self.files["server_live.py"].decode()
        for term in ("item['stop'].is_set()", "NOX_STREAM_INCOMPLETE_HOLD",
                     "'think': False", "if event.get('done') is True:",
                     "ACTIVE.pop(request_id, None)", "NOX_LOCAL_LIVE_V1"):
            self.assertIn(term,s)
    def test_ui_refuses_partial_chat(self):
        s=self.files["chat-live.js"].decode()
        self.assertIn("if(!completed)throw new Error('NOX_STREAM_INCOMPLETE_HOLD')",s)
        self.assertIn("if(data.done===true)completed=true",s)
    def test_local_only_mic_and_no_auto_send(self):
        s=self.files["voice-live.js"].decode()
        for term in ("processLocally:true","r.processLocally=true",
                     "NOX_VOICE_LOCAL_STT_UNAVAILABLE_HOLD",
                     "lastRecognized=words", "prompt.value=", "old?.abort()", "localService===true"):
            self.assertIn(term,s)
        self.assertNotIn("fetch('https://",s)
        self.assertNotIn("requestSubmit()",s)
        self.assertIn("voice-live.js",self.files["chat.html"].decode())

class StreamProtocol(unittest.TestCase):
    def test_local_real_http_stream_completes(self):
        # Set up an actual HTTP loopback to fake the model *only in tests*.
        model_events=[
          json.dumps({"message":{"content":"Привет"},"done":False}).encode()+b"\n",
          json.dumps({"message":{"content":" NOX"},"done":False}).encode()+b"\n",
          json.dumps({"done":True}).encode()+b"\n"
        ]
        class Upstream(BaseHTTPRequestHandler):
            def do_POST(self):
                n=int(self.headers.get("Content-Length","0"))
                self.rfile.read(n)
                self.send_response(200);self.send_header("Content-Type","application/x-ndjson");self.end_headers()
                for e in model_events:
                    self.wfile.write(e);self.wfile.flush()
            def log_message(self,*args):pass
        upstream=ThreadingHTTPServer(("127.0.0.1",0),Upstream)
        thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
        fake_server=types.ModuleType("server")
        fake_server.OLLAMA=f"http://127.0.0.1:{upstream.server_port}"
        fake_server.PORT=18775
        fake_server.models=lambda:[{"name":"qwen-test:local"}]
        class HandlerBase(SimpleHTTPRequestHandler):
            def _json(self,status,data):
                blob=json.dumps(data).encode("utf-8")
                self.send_response(status);self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(blob)));self.end_headers();self.wfile.write(blob)
            def do_GET(self):
                return self._json(404,{"status":"NOT_FOUND"})
            def do_POST(self):
                return self._json(404,{"status":"NOT_FOUND"})
            def log_message(self,*args):pass
        fake_server.Handler=HandlerBase
        svc=types.ModuleType("nox_services")
        svc.truth_metrics=lambda:{"status":"HOLD"}
        svc.training_status=lambda:{"status":"HOLD"}
        svc.s03_status=lambda:{"status":"HOLD"}
        svc.push_status=lambda:{"webpush_server":"HOLD"}
        svc.load_config=lambda:{}
        push=types.ModuleType("nox_push")
        push.add=lambda d:False
        push.send=lambda *x:{"status":"HOLD"}
        class NoWatcher:
            def start(self):pass
        push.TrainerLogWatcher=NoWatcher
        orig={name:sys.modules.get(name) for name in ("server","nox_services","nox_push")}
        server=None
        try:
            sys.modules.update({"server":fake_server,"nox_services":svc,"nox_push":push})
            module=types.ModuleType("nox_live_test")
            module.__file__=str(BASE/"server_live.py")
            code=patch_source(read_original(PAYLOAD),VOICE)["server_live.py"]
            exec(compile(code,"server_live.py","exec"),module.__dict__)
            server=ThreadingHTTPServer(("127.0.0.1",0),module.Handler)
            th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
            origin=f"http://127.0.0.1:{server.server_port}"
            with request.urlopen(origin+"/api/mega/health",timeout=4) as r:
                health=json.load(r)
            self.assertEqual(health["identity"],"NOX_LOCAL_LIVE_V1")
            self.assertFalse(health["releaseAccepted"])
            body=json.dumps({"request_id":"REQ-123456789","model":"qwen-test:local",
                "messages":[{"role":"user","content":"test"}]}).encode()
            req=request.Request(origin+"/api/chat",data=body,method="POST",
                   headers={"Content-Type":"application/json"})
            with request.urlopen(req,timeout=5) as r:
                lines=[json.loads(x) for x in r if x.strip()]
            self.assertTrue(lines[-1].get("done"))
            self.assertEqual("".join(x.get("message",{}).get("content","") for x in lines),"Привет NOX")
            self.assertEqual(module.ACTIVE,{})
            req=request.Request(origin+"/api/chat",data=body,method="POST",
                   headers={"Origin":"https://evil.example"})
            with self.assertRaises(error.HTTPError) as e:request.urlopen(req,timeout=5)
            self.assertEqual(e.exception.code,403)
        finally:
            if server:server.shutdown();server.server_close()
            upstream.shutdown();upstream.server_close()
            for name,item in orig.items():
                if item is None:sys.modules.pop(name,None)
                else:sys.modules[name]=item

if __name__=="__main__":
    unittest.main()
