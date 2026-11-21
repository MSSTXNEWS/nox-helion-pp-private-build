import json
import os
import stat
import tempfile
import unittest
from unittest import mock

import nox_advisors as na
from test_nox_advisors import make_server, chat, url


class Remote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = os.path.join(self.tmp, "u.json")
        self.srvs = []

    def tearDown(self):
        for s in self.srvs:
            s.shutdown(); s.server_close()

    def srv(self, fn):
        s = make_server(fn); self.srvs.append(s); return s

    def test_key_from_env_only_and_not_leaked(self):
        seen = {}

        def h(path, body):
            seen["path"] = path; seen["model"] = body.get("model")
            return 500, {"error": "bad key sk-SECRETSECRETSECRET1234"}
        s = self.srv(chat("x"))
        s2 = make_server(lambda p, b: (200, {"choices": [{"message": {"content": "hi"}}]}))
        self.srvs.append(s2)
        adv = {"name": "r", "url": url(s2) + "/v1", "api_key_env": "TEST_KEY_X", "model": "m:free"}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_KEY_X", None)
            r = na._ask_one(adv, "q", None, self.state)
            self.assertFalse(r["ok"]); self.assertIn("TEST_KEY_X", r["blocked"]); self.assertTrue(r["need"])
            os.environ["TEST_KEY_X"] = "topsecretvalue123"
            r = na._ask_one(adv, "q", None, self.state)
        self.assertTrue(r["ok"])
        self.assertTrue(r["answer"].startswith("[мнение советника, не NOX: r]"))
        self.assertNotIn("topsecretvalue123", json.dumps(r))

    def test_auth_header_sent(self):
        got = {}

        class Cap:
            pass
        import http.server, threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                got["auth"] = self.headers.get("Authorization")
                got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                d = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers()
                self.wfile.write(d)

            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H); self.srvs.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with mock.patch.dict(os.environ, {"K1": "abc-key-123456"}):
            r = na._ask_one({"name": "r", "url": url(srv) + "/v1", "api_key_env": "K1"},
                            "my token=ghp_abcdefghijklmnopqrstuvwx in /home/claude/x.py", None, self.state)
        self.assertTrue(r["ok"])
        self.assertEqual(got["auth"], "Bearer abc-key-123456")
        sent = got["body"]["messages"][-1]["content"]
        self.assertNotIn("ghp_", sent); self.assertNotIn("/home/claude", sent)
        self.assertGreaterEqual(r["redacted"], 2)

    def test_retries_then_ok(self):
        calls = {"n": 0}

        def h(path, body):
            calls["n"] += 1
            return (503, {}) if calls["n"] < 3 else (200, {"choices": [{"message": {"content": "fine"}}]})
        s = self.srv(h)
        sleeps = []
        r = na._ask_one({"name": "r", "url": url(s), "retries": 2, "remote": True}, "q", None,
                        self.state, sleeps.append)
        self.assertTrue(r["ok"]); self.assertEqual(calls["n"], 3); self.assertEqual(len(sleeps), 2)

    def test_no_retry_on_4xx(self):
        calls = {"n": 0}

        def h(path, body):
            calls["n"] += 1
            return 401, {}
        s = self.srv(h)
        r = na._ask_one({"name": "r", "url": url(s), "retries": 3}, "q", None, self.state, lambda x: None)
        self.assertFalse(r["ok"]); self.assertEqual(calls["n"], 1)

    def test_daily_limit(self):
        s = self.srv(chat("a"))
        adv = {"name": "or", "url": url(s), "daily_limit": 2}
        rs = [na._ask_one(adv, "q", None, self.state) for _ in range(3)]
        self.assertEqual([r["ok"] for r in rs], [True, True, False])
        self.assertIn("daily limit", rs[2]["blocked"]); self.assertTrue(rs[2]["need"])
        self.assertEqual(json.load(open(self.state))[na._today()]["or"], 2)

    def test_usage_resets_next_day(self):
        self.assertEqual(na.usage_take(self.state, "a", 1, "2026-01-01"), (True, 1))
        self.assertEqual(na.usage_take(self.state, "a", 1, "2026-01-01"), (False, 1))
        self.assertEqual(na.usage_take(self.state, "a", 1, "2026-01-02"), (True, 1))

    def test_sanitize(self):
        t, n = na.sanitize_outgoing("password: hunter2abc and C:\\Users\\me\\x ~/.ssh/id_rsa AIza" + "a" * 35)
        self.assertNotIn("hunter2abc", t); self.assertNotIn("Users", t); self.assertNotIn(".ssh", t)
        self.assertNotIn("AIza", t); self.assertGreaterEqual(n, 4)
        self.assertEqual(na.sanitize_outgoing("обычный текст про CSS")[1], 0)

    def test_cli_allowlist_and_missing(self):
        r = na._ask_one({"name": "x", "kind": "cli", "cli": "rm"}, "q", None, self.state)
        self.assertIn("allowlist", r["blocked"])
        with mock.patch("shutil.which", return_value=None):
            r = na._ask_one({"name": "c", "kind": "cli", "cli": "copilot"}, "q", None, self.state)
        self.assertFalse(r["ok"]); self.assertIn("not installed", r["blocked"]); self.assertIn("sign in", r["need"])

    def test_cli_runs_fake_binary_readonly(self):
        bindir = tempfile.mkdtemp()
        p = os.path.join(bindir, "gemini")
        with open(p, "w") as f:
            f.write('#!/bin/sh\necho "args=$1 cwd=$(pwd)"; echo "key=${GEMINI_API_KEY:-none} leak=${SECRET_X:-none}"\n')
        os.chmod(p, 0o755)
        with mock.patch.dict(os.environ, {"PATH": bindir + ":" + os.environ["PATH"], "SECRET_X": "zzz"}):
            r = na._ask_one({"name": "g", "kind": "cli", "cli": "gemini", "daily_limit": 5},
                            "hi /root/secret.txt", None, self.state)
        self.assertTrue(r["ok"], r)
        self.assertIn("leak=none", r["answer"]); self.assertNotIn("/root/secret", r["answer"])
        self.assertIn("мнение советника, не NOX", r["answer"])
        self.assertNotIn(os.getcwd(), r["answer"].split("cwd=")[1].split()[0])

    def test_cli_timeout(self):
        bindir = tempfile.mkdtemp()
        p = os.path.join(bindir, "copilot")
        with open(p, "w") as f:
            f.write("#!/bin/sh\nsleep 5\n")
        os.chmod(p, 0o755)
        with mock.patch.dict(os.environ, {"PATH": bindir + ":" + os.environ["PATH"]}):
            r = na._ask_one({"name": "c", "kind": "cli", "cli": "copilot", "timeout_s": 0.5}, "q", None, self.state)
        self.assertFalse(r["ok"]); self.assertEqual(r["error"], "timeout")

    def test_searxng(self):
        import http.server, threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                d = json.dumps({"results": [{"title": "T", "url": "http://e/x", "content": "C"}] * 9}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers()
                self.wfile.write(d)

            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H); self.srvs.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        r = na._ask_one({"name": "s", "kind": "searxng", "url": url(srv), "max_results": 3}, "css grid", None, self.state)
        self.assertTrue(r["ok"]); self.assertEqual(r["answer"].count("\n- "), 2)

    def test_code_consensus_proposal_not_applied(self):
        d = "```diff\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n```\nfix"
        ss = [self.srv(chat(d)), self.srv(chat(d + " ok")), self.srv(chat("no idea"))]
        advs = [{"name": f"a{i}", "url": url(s)} for i, s in enumerate(ss)]
        r = na.code_consensus("fix x", "/nonexistent.json", "http://127.0.0.1:1/e", _advisors=advs)
        self.assertFalse(r["applied"]); self.assertIn("+++ b/x.py", r["proposal"])
        self.assertIn("a2", r["dissenters"]); self.assertEqual(r["status"], "split")
        one = na.code_consensus("fix x", "/n.json", _advisors=advs[:1])
        self.assertEqual(one["status"], "insufficient")

    def test_extract_patch(self):
        self.assertIsNone(na.extract_patch("just words"))
        self.assertIn("@@", na.extract_patch("x\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-1\n+2\n"))


if __name__ == "__main__":
    unittest.main()
