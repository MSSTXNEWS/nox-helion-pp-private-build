import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import nox_advisors as na


def make_server(handler_fn):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code, resp = handler_fn(self.path, body)
            data = json.dumps(resp).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def chat(text):
    return lambda path, body: (200, {"choices": [{"message": {"content": text}}]})


def url(srv):
    return f"http://127.0.0.1:{srv.server_address[1]}"


def write_cfg(advs):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(advs, f)
    f.close()
    return f.name


class T(unittest.TestCase):
    def setUp(self):
        self.servers = []
        self.files = []

    def tearDown(self):
        for s in self.servers:
            s.shutdown()
            s.server_close()
        for f in self.files:
            os.unlink(f)

    def srv(self, fn):
        s = make_server(fn)
        self.servers.append(s)
        return s

    def cfg(self, advs):
        p = write_cfg(advs)
        self.files.append(p)
        return p

    def test_parallel_with_dead(self):
        s1 = self.srv(chat("hello"))
        dead = self.srv(chat("x"))
        dead_url = url(dead)
        dead.shutdown(); dead.server_close()
        cfg = self.cfg([
            {"name": "a", "url": url(s1), "timeout_s": 5, "role": "judge"},
            {"name": "b", "url": dead_url, "timeout_s": 2, "role": "checker"}])
        res = na.ask_advisors("q", cfg)
        self.assertTrue(res[0]["ok"]); self.assertEqual(res[0]["answer"], "hello")
        self.assertFalse(res[1]["ok"]); self.assertTrue(res[1]["error"])

    def test_answer_cap(self):
        s = self.srv(chat("z" * 20000))
        res = na.ask_advisors("q", self.cfg([{"name": "a", "url": url(s), "role": "judge"}]))
        self.assertEqual(len(res[0]["answer"]), 8000)

    def test_consensus_embeddings(self):
        vec = {"cat": [1, 0], "cat2": [0.99, 0.1], "dog": [0, 1]}

        def emb(path, body):
            return 200, {"data": [{"index": i, "embedding": vec[t]} for i, t in enumerate(body["input"])]}
        e = self.srv(emb)
        agree = na.consensus([{"name": "a", "answer": "cat"}, {"name": "b", "answer": "cat2"}],
                             url(e) + "/v1/embeddings")
        self.assertEqual(agree["method"], "embeddings"); self.assertGreater(agree["agreement"], 0.9)
        self.assertEqual(agree["dissenters"], [])
        dis = na.consensus([{"name": "a", "answer": "cat"}, {"name": "b", "answer": "cat2"},
                            {"name": "c", "answer": "dog"}], url(e) + "/v1/embeddings")
        self.assertEqual(dis["dissenters"], ["c"])
        self.assertIn(dis["majority_answer"], ("cat", "cat2"))

    def test_consensus_jaccard_fallback(self):
        r = na.consensus(["the sky is blue", "the sky is blue today", "pizza"],
                         "http://127.0.0.1:1/v1/embeddings")
        self.assertEqual(r["method"], "jaccard")
        self.assertEqual(r["dissenters"], [2])

    def test_extract_json_noisy(self):
        t = 'Sure! {bad json} then ```json\n{"verdict":"pass","reasons":["ok {x}"]}\n``` bye'
        self.assertEqual(na.extract_json(t)["verdict"], "pass")
        self.assertIsNone(na.extract_json("no json here"))

    def _rev(self, texts):
        advs = []
        for i, t in enumerate(texts):
            if t is None:
                s = self.srv(chat("x")); u = url(s); s.shutdown(); s.server_close()
            else:
                u = url(self.srv(chat(t)))
            advs.append({"name": f"j{i}", "url": u, "timeout_s": 2, "role": "judge"})
        return na.review("task", "acc", "cand", self.cfg(advs))

    def test_review_majority(self):
        P = 'ok {"verdict":"pass","reasons":["good"]}'
        F = '{"verdict":"fail","reasons":["bad"]}'
        self.assertEqual(self._rev([P, P, F])["verdict"], "pass")
        self.assertEqual(self._rev([P, F, F])["verdict"], "fail")

    def test_review_requires_two(self):
        P = '{"verdict":"pass","reasons":[]}'
        r = self._rev([P, None])
        self.assertEqual(r["verdict"], "fail")
        self.assertEqual(self._rev([P, "garbage"])["verdict"], "fail")
        self.assertEqual(self._rev([P])["verdict"], "fail")


if __name__ == "__main__":
    unittest.main()
