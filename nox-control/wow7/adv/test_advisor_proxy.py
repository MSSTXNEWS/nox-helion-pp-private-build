"""ADV-04: прокси шлюза /v1/advisors/* (advisor_proxy) поверх настоящего хаба с фейковым транспортом + проверка применимости gateway_adv.diff."""
import json, os, shutil, subprocess, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import advisor_hub as H
import advisor_proxy as AP
from test_adv import P, reg, envf

CLONE = os.environ.get("NOX_REPO_ROOT", "/home/claude/msstxnews/nox-helion-pp-private-build")


class FakeGateway(BaseHTTPRequestHandler):
    """Минимальный шлюз с теми же двумя врезками, что в gateway_adv.diff."""
    def log_message(self, *a): pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p.startswith("/v1/advisors/") and AP.handle(self, "GET", self.path, b""): return
        self._json(200, {"gateway": "own", "path": p})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(n) or b"{}")
        p = self.path.split("?")[0].rstrip("/")
        if p.startswith("/v1/advisors/") and AP.handle(self, "POST", self.path, json.dumps(body, ensure_ascii=False).encode("utf-8")): return
        self._json(200, {"gateway": "own", "path": p})


class T(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        c.d = tempfile.mkdtemp()
        hub = H.Hub(registry=reg(P("a", "x")), env=envf("a"), transport=lambda p, m, t, *a: "Ответ от %s: используй кэш и проверь результат." % p["name"],
                    state_path=os.path.join(c.d, "st.json"), journal=os.path.join(c.d, "j.jsonl"))
        c.hub_srv = H.make_server(hub, "127.0.0.1", 0, token="hubtok")
        threading.Thread(target=c.hub_srv.serve_forever, daemon=True).start()
        c.gw = ThreadingHTTPServer(("127.0.0.1", 0), FakeGateway)
        threading.Thread(target=c.gw.serve_forever, daemon=True).start()
        c.port = c.gw.server_address[1]
        os.environ["NOX_ADV_URL"] = "http://127.0.0.1:%d" % c.hub_srv.server_address[1]
        os.environ["NOX_ADV_TOKEN"] = "hubtok"

    @classmethod
    def tearDownClass(c):
        c.hub_srv.shutdown(); c.gw.shutdown()
        for k in ("NOX_ADV_URL", "NOX_ADV_TOKEN", "NOX_ADV"): os.environ.pop(k, None)
        shutil.rmtree(c.d, ignore_errors=True)

    def call(s, method, path, body=None):
        rq = urllib.request.Request("http://127.0.0.1:%d%s" % (s.port, path), json.dumps(body).encode() if body is not None else None, method=method)
        try:
            with urllib.request.urlopen(rq, timeout=15) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

    def test_ask_command_status_through_gateway_with_hub_token(s):
        c, r = s.call("POST", "/v1/advisors/ask", {"question": "вопрос через шлюз и прокси", "n": 1})
        s.assertEqual(c, 200); s.assertTrue(r["ok"]); s.assertEqual(r["answers"][0]["advisor"], "a")      # токен хаба подставлен прокси, клиент его не знает
        c, r = s.call("POST", "/v1/advisors/command", {"text": "спроси советников: вопрос через команду"}); s.assertTrue(r["matched"])
        c, r = s.call("GET", "/v1/advisors/status"); s.assertEqual(c, 200); s.assertTrue(r["ok"])
        c, r = s.call("POST", "/v1/advisors/ask", {"question": "низкая уверенность тут", "confidence": 0.9}); s.assertEqual(r["skipped"], "confident")

    def test_other_paths_untouched_and_unknown_advisor_path_404(s):
        s.assertEqual(s.call("GET", "/v1/nox/stats")[1], {"gateway": "own", "path": "/v1/nox/stats"})
        s.assertEqual(s.call("POST", "/v1/chat/completions", {"messages": []})[1]["gateway"], "own")
        c, r = s.call("POST", "/v1/advisors/hack", {}); s.assertEqual((c, r["error"]), (404, "not_found"))
        c, r = s.call("GET", "/v1/advisors/ask"); s.assertEqual(c, 404)

    def test_too_large_disabled_and_hub_down(s):
        c, r = s.call("POST", "/v1/advisors/ask", {"question": "x" * 40000}); s.assertEqual(c, 413)
        os.environ["NOX_ADV"] = "0"
        try: s.assertEqual(s.call("GET", "/v1/advisors/status")[1]["error"], "advisors_disabled")
        finally: os.environ.pop("NOX_ADV")
        old = os.environ["NOX_ADV_URL"]; os.environ["NOX_ADV_URL"] = "http://127.0.0.1:9"
        try:
            c, r = s.call("POST", "/v1/advisors/ask", {"question": "хаб лежит"}); s.assertEqual((c, r["error"]), (503, "advisor_hub_down"))
        finally: os.environ["NOX_ADV_URL"] = old

    def test_wrong_hub_token_gives_401_from_hub(s):
        old = os.environ["NOX_ADV_TOKEN"]; os.environ["NOX_ADV_TOKEN"] = "bad"
        try: s.assertEqual(s.call("POST", "/v1/advisors/ask", {"question": "вопрос"})[0], 401)
        finally: os.environ["NOX_ADV_TOKEN"] = old

    def test_diff_applies_to_clone_and_patched_gateway_compiles(s):
        g = os.path.join(CLONE, "nox-control", "glm53", "gateway.py")
        if not os.path.isfile(g) or not shutil.which("patch"): s.skipTest("нет клона репо или patch")
        t = tempfile.mkdtemp()
        try:
            os.makedirs(t + "/nox-control/glm53"); shutil.copy(g, t + "/nox-control/glm53/gateway.py")
            rc = subprocess.run(["patch", "-p1", "-s", "-i", os.path.join(HERE, "gateway_adv.diff")], cwd=t, capture_output=True, text=True)
            s.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            src = open(t + "/nox-control/glm53/gateway.py", encoding="utf-8").read()
            s.assertIn("advisor_proxy.handle(self, \"GET\"", src); s.assertIn("advisor_proxy.handle(self, \"POST\"", src)
            compile(src, "gateway.py", "exec")
        finally: shutil.rmtree(t, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
