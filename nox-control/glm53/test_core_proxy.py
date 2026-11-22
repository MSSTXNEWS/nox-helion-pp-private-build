import json, os, sys, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_proxy
import urllib.request


class Core(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers["Content-Length"]); body = self.rfile.read(n)
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(b"event: nox_phase\ndata: {\"phase\":\"plan\"}\n\n"); self.wfile.flush()
        self.wfile.write(b"data: " + json.dumps({"echo": json.loads(body), "ev": self.headers.get("X-NOX-Eval")}).encode() + b"\n\n")


def make_gw():
    class GW(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            n = int(self.headers["Content-Length"]); raw = self.rfile.read(n)
            if not core_proxy.proxy(self, self.path, raw, connect_timeout=1):
                b = b'{"old":"path"}'; self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    s = ThreadingHTTPServer(("127.0.0.1", 0), GW); threading.Thread(target=s.serve_forever, daemon=True).start(); return s


class T(unittest.TestCase):
    def test_stream_passthrough_and_fallback(self):
        core = HTTPServer(("127.0.0.1", 0), Core); threading.Thread(target=core.serve_forever, daemon=True).start()
        os.environ["NOX_CORE_URL"] = "http://127.0.0.1:%d" % core.server_port
        gw = make_gw(); u = "http://127.0.0.1:%d/v1/chat/completions" % gw.server_port
        body = json.dumps({"messages": [{"role": "user", "content": "привет"}]}, ensure_ascii=False).encode()
        req = urllib.request.Request(u, body, {"Content-Type": "application/json", "X-NOX-Eval": "1"})
        txt = urllib.request.urlopen(req, timeout=5).read().decode()
        self.assertIn("event: nox_phase", txt); self.assertIn("\\u043f\\u0440\\u0438\\u0432\\u0435\\u0442", txt); self.assertIn('"ev": "1"', txt)
        core.shutdown(); core.server_close()
        os.environ["NOX_CORE_URL"] = "http://127.0.0.1:1"
        self.assertEqual(urllib.request.urlopen(urllib.request.Request(u, body), timeout=5).read(), b'{"old":"path"}')
        gw.shutdown()


if __name__ == "__main__":
    unittest.main()
