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
class FakeVoice(BaseHTTPRequestHandler):
    """Имитация STT (8093) и TTS (8094): эхо метаданных запроса, SSE и chunked PCM."""
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/session/s1/audio"):
            fmt = "pcm" if "format=pcm" in self.path else "sse"
            self.send_response(200); self.send_header("Content-Type", "audio/L16" if fmt == "pcm" else "text/event-stream"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
            parts = [b"\x01\x02" * 4, b"\x03\x04" * 4] if fmt == "pcm" else [b"event: audio\ndata: {\"seq\":0}\n\n", b"event: end\ndata: {}\n\n"]
            for ch in parts: self.wfile.write(("%x\r\n" % len(ch)).encode() + ch + b"\r\n"); self.wfile.flush(); time.sleep(.05)
            self.wfile.write(b"0\r\n\r\n"); return
        b = json.dumps({"ok": True, "path": self.path}).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); d = self.rfile.read(n)
        b = json.dumps({"path": self.path, "ctype": self.headers.get("Content-Type"), "len": n, "head": d[:4].hex()}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gw = ThreadingHTTPServer(("127.0.0.1", 0), FakeGW); threading.Thread(target=cls.gw.serve_forever, daemon=True).start()
        d = tempfile.mkdtemp(); open(os.path.join(d, "chat.html"), "w").write("<html>ok</html>")
        cls.vs = ThreadingHTTPServer(("127.0.0.1", 0), FakeVoice); threading.Thread(target=cls.vs.serve_forever, daemon=True).start()
        os.environ["NOX_STT"] = os.environ["NOX_TTS"] = "127.0.0.1:%d" % cls.vs.server_port
        os.environ["NOX_WEB_ROOT"] = d; os.environ["NOX_GW"] = "127.0.0.1:%d" % cls.gw.server_port
        import importlib, web_server; importlib.reload(web_server); cls.ws = web_server
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.H); threading.Thread(target=cls.srv.serve_forever, daemon=True).start(); time.sleep(.1)
    def req(self, m, p, b=None, ct="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10); c.request(m, p, body=b, headers={"Content-Type": ct}); r = c.getresponse(); return r.status, r.read()
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
    def test_stt_binary_webm(self):
        blob = bytes.fromhex("1a45dfa3") + b"\x00" * 2000
        s, d = self.req("POST", "/stt/transcribe?language=ru&words=1", blob, "audio/webm;codecs=opus"); j = json.loads(d)
        self.assertEqual(s, 200); self.assertEqual(j["path"], "/transcribe?language=ru&words=1"); self.assertEqual(j["len"], len(blob))
        self.assertEqual(j["head"], "1a45dfa3"); self.assertTrue(j["ctype"].startswith("audio/webm"))
    def test_stt_health_get(self):
        s, d = self.req("GET", "/stt/health"); self.assertEqual(s, 200); self.assertEqual(json.loads(d)["path"], "/health")
    def test_tts_json_and_stop(self):
        s, d = self.req("POST", "/tts/session", json.dumps({"lang": "ru"})); self.assertEqual((s, json.loads(d)["path"]), (200, "/session"))
        s, d = self.req("POST", "/tts/session/s1/stop", "{}"); self.assertEqual(json.loads(d)["path"], "/session/s1/stop")
    def test_tts_sse_and_pcm_stream(self):
        s, d = self.req("GET", "/tts/session/s1/audio?format=sse"); self.assertEqual(s, 200); self.assertIn(b"event: audio", d); self.assertIn(b"event: end", d)
        s, d = self.req("GET", "/tts/session/s1/audio?format=pcm"); self.assertEqual(s, 200); self.assertEqual(d, b"\x01\x02" * 4 + b"\x03\x04" * 4)
    def test_voice_down_honest_502(self):
        old = self.ws.STT; self.ws.STT = "127.0.0.1:1"
        s, d = self.req("POST", "/stt/transcribe", b"x", "audio/webm"); self.assertEqual(s, 502); self.assertIn("STT", json.loads(d)["error"]); self.ws.STT = old
    def test_body_limit(self):
        old = self.ws.MAX_BODY; self.ws.MAX_BODY = 10
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10); c.request("POST", "/stt/transcribe", body=b"x" * 50, headers={"Content-Type": "audio/webm"}); r = c.getresponse(); self.assertEqual(r.status, 413); self.ws.MAX_BODY = old
if __name__ == "__main__": unittest.main()
