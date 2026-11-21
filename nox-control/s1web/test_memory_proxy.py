import unittest, threading, json, http.client, os, sys, tempfile, importlib
from http.server import ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
from qs6.s03_store import Store
from qs6 import recall_server

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp(); db = os.path.join(d, "s03.db"); s = Store(db); s.add_fact("Порт recall равен 8095", kind="fact"); s.close()
        cls.rs = recall_server.build({"NOX_MEMORY_DB": db, "NOX_RECALL_PORT": "0"}); threading.Thread(target=cls.rs.serve_forever, daemon=True).start()
        os.environ["NOX_MEMORY_API"] = "127.0.0.1:%d" % cls.rs.server_address[1]; os.environ["NOX_WEB_ROOT"] = d
        import web_server; importlib.reload(web_server); cls.ws = web_server
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.H); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.rs.shutdown()
    def req(self, m, p, b=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10); c.request(m, p, body=b, headers={"Content-Type": "application/json"}); r = c.getresponse(); return r.status, r.read()
    def test_health(self):
        s, d = self.req("GET", "/memory/health"); self.assertEqual(s, 200); self.assertTrue(json.loads(d)["ok"])
    def test_api_search_and_remembered(self):
        s, d = self.req("POST", "/memory/api", json.dumps({"op": "recall", "query": "порт recall", "turn_id": "t9"})); j = json.loads(d)
        self.assertEqual(s, 200); self.assertTrue(j["ok"]); self.assertEqual(j["turn_id"], "t9")
        s, d = self.req("POST", "/memory/api", json.dumps({"op": "remembered", "turn_id": "t9"})); j = json.loads(d)
        self.assertGreaterEqual(j["count"], 1); self.assertIn("8095", j["items"][0]["text"])
    def test_correct_via_web(self):
        s, d = self.req("POST", "/memory/api", json.dumps({"op": "search", "query": "порт recall"})); ref = json.loads(d)["hits"][0]["ref"]
        s, d = self.req("POST", "/memory/api", json.dumps({"op": "delete", "id": ref})); self.assertTrue(json.loads(d)["ok"])
    def test_other_paths_404(self):
        self.assertEqual(self.req("GET", "/memory/api")[0], 404); self.assertEqual(self.req("POST", "/memory/health", "{}")[0], 404); self.assertEqual(self.req("GET", "/memory/../x")[0], 404)
    def test_down_honest_502(self):
        old = self.ws.MEM; self.ws.MEM = "127.0.0.1:1"
        try: s, d = self.req("GET", "/memory/health"); self.assertEqual(s, 502); self.assertIn("память", json.loads(d)["error"])
        finally: self.ws.MEM = old
if __name__ == "__main__": unittest.main()
