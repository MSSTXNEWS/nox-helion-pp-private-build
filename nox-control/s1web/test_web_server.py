import unittest, threading, json, http.client, os, sys, tempfile, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
class FakeGW(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n))
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for t in ["При", "вет"]:
            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": t}}]}) + "\n\n").encode()); self.wfile.flush()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"reasoning_content": "мысль"}, "finish_reason": "stop"}]}) + "\n\ndata: [DONE]\n\n").encode())
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gw = ThreadingHTTPServer(("127.0.0.1", 0), FakeGW); threading.Thread(target=cls.gw.serve_forever, daemon=True).start()
        d = tempfile.mkdtemp(); open(os.path.join(d, "chat.html"), "w").write("<html>ok</html>")
        os.environ["NOX_WEB_ROOT"] = d; os.environ["NOX_GW"] = "127.0.0.1:%d" % cls.gw.server_port
        import importlib, web_server; importlib.reload(web_server); cls.ws = web_server
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.H); threading.Thread(target=cls.srv.serve_forever, daemon=True).start(); time.sleep(.1)
    def req(self, m, p, b=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10); c.request(m, p, body=b, headers={"Content-Type": "application/json"}); r = c.getresponse(); return r.status, r.read()
    def test_static(self):
        s, d = self.req("GET", "/web/chat.html"); self.assertEqual(s, 200); self.assertIn(b"ok", d)
        self.assertIn(self.req("GET", "/web/../x")[0], (403, 404))
        self.assertEqual(self.req("GET", "/api/status")[0], 503)
    def test_chat_ndjson(self):
        s, d = self.req("POST", "/api/chat", json.dumps({"request_id": "r1", "model": "x", "messages": [{"role": "user", "content": "hi"}]}))
        self.assertEqual(s, 200); fr = [json.loads(l) for l in d.decode().strip().split("\n")]
        self.assertEqual("".join(f["message"]["content"] for f in fr), "Привет"); self.assertTrue(fr[-1]["done"]); self.assertEqual(fr[0]["model"], "nox-helion:latest")
        self.assertNotIn("мысль", d.decode())
    def test_gw_down(self):
        self.ws.GW = "127.0.0.1:1"; s, d = self.req("POST", "/api/chat", json.dumps({"messages": []})); self.assertEqual(s, 502); self.ws.GW = "127.0.0.1:%d" % self.gw.server_port
if __name__ == "__main__": unittest.main()
