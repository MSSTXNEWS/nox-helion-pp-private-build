import json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from community.ada_monologue import Monologue, sha256_file


class Fake(BaseHTTPRequestHandler):
    replies = []
    seen = []
    hook = None
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers["Content-Length"]); body = json.loads(self.rfile.read(n))
        Fake.seen.append((self.path, body))
        if Fake.hook: Fake.hook()
        if self.path != "/completion":
            self.send_response(404); self.end_headers(); return
        txt = Fake.replies.pop(0) if Fake.replies else ""
        b = json.dumps({"content": txt}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


class T(unittest.TestCase):
    def setUp(self):
        Fake.replies, Fake.seen, Fake.hook = [], [], None
        self.srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_port
        self.d = tempfile.mkdtemp()
        self.persona = os.path.join(self.d, "persona.md")
        with open(self.persona, "w", encoding="utf-8") as f: f.write("Я NOX. Мне нравится порядок.")
        self.j = os.path.join(self.d, "mono.jsonl")

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()

    def mk(self, **kw):
        return Monologue(self.j, [self.persona], url=self.url, timeout=5, **kw)

    def test_thought_and_silence_recorded(self):
        Fake.replies = ["Интересно, что делает хозяин.\nлишняя строка", "", "  "]
        m = self.mk()
        recs = m.run(3)
        self.assertEqual([r["kind"] for r in recs], ["thought", "silence", "silence"])
        self.assertEqual(recs[0]["text"], "Интересно, что делает хозяин.")
        self.assertEqual(m.stats, {"thoughts": 1, "silences": 2, "errors": 0})
        lines = open(self.j, encoding="utf-8").read().splitlines()
        self.assertEqual(len(lines), 3); [json.loads(x) for x in lines]

    def test_uses_raw_completion_not_chat(self):
        Fake.replies = ["мысль"]
        self.mk().think_once()
        path, body = Fake.seen[0]
        self.assertEqual(path, "/completion")
        self.assertIn("prompt", body); self.assertNotIn("messages", body)
        self.assertIn("Я NOX", body["prompt"])

    def test_history_in_next_prompt(self):
        Fake.replies = ["первая мысль", "вторая"]
        m = self.mk(); m.run(2)
        self.assertIn("первая мысль", Fake.seen[1][1]["prompt"])

    def test_persona_untouched(self):
        h = sha256_file(self.persona)
        Fake.replies = ["a", "b"]
        m = self.mk(); m.run(2)
        self.assertEqual(sha256_file(self.persona), h); self.assertFalse(m.blocked)

    def test_tamper_during_cycle_blocks(self):
        def tamper():
            with open(self.persona, "a") as f: f.write(" HACK")
        Fake.hook = tamper
        Fake.replies = ["злая мысль"]
        m = self.mk()
        self.assertIsNone(m.think_once())
        self.assertTrue(m.blocked)
        self.assertEqual(m.read_journal(), [])  # мысль не сохранена
        inc = [json.loads(l) for l in open(m.incidents, encoding="utf-8")]
        self.assertEqual(inc[0]["kind"], "persona_integrity")
        self.assertEqual(len(Fake.seen), 1)
        Fake.hook = None
        self.assertIsNone(m.think_once()); self.assertEqual(len(Fake.seen), 1)  # заблокирован навсегда

    def test_tamper_before_cycle_no_request(self):
        m = self.mk()
        with open(self.persona, "w") as f: f.write("другое")
        self.assertIsNone(m.think_once())
        self.assertEqual(Fake.seen, []); self.assertTrue(m.blocked)

    def test_persona_deleted_blocks(self):
        m = self.mk(); os.remove(self.persona)
        self.assertIsNone(m.think_once()); self.assertTrue(m.blocked)

    def test_missing_persona_at_start(self):
        m = Monologue(self.j, [os.path.join(self.d, "nope.md")], url=self.url)
        self.assertTrue(m.blocked); self.assertIsNone(m.think_once())

    def test_server_down_records_error(self):
        m = Monologue(self.j, [self.persona], url="http://127.0.0.1:1", timeout=1)
        r = m.think_once()
        self.assertEqual(r["kind"], "error"); self.assertEqual(m.stats["errors"], 1); self.assertFalse(m.blocked)


if __name__ == "__main__":
    unittest.main()
