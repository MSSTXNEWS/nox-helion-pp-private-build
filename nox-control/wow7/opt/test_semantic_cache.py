import json, random, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import semantic_cache as sc


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


class T(unittest.TestCase):
    def mk(self, **kw):
        self.clk = Clock()
        kw.setdefault("explore_p", 0.0)
        return sc.SemanticCache(":memory:", clock=self.clk, rng=random.Random(1), **kw)

    def test_exact_after_normalization(self):
        c = self.mk(); k = sc.make_ctx_key("s", 1)
        c.put("Что такое RAID массив?", "RAID объединяет диски.", k)
        h = c.get("что  такое raid МАССИВ", k)
        self.assertTrue(h and h.exact and h.sim == 1.0)

    def test_near_duplicate_hit_and_different_miss(self):
        c = self.mk(base_thr=0.80); k = sc.make_ctx_key("s", 1)
        c.put("Расскажи про архитектуру памяти системы NOX", "Память S03 ...", k)
        h = c.get("Расскажи про архитектуру памяти системы NOX пожалуйста", k)
        self.assertIsNotNone(h); self.assertFalse(h.exact); self.assertGreaterEqual(h.sim, 0.80)
        self.assertIsNone(c.get("Расскажи про расписание ночного обучения адаптеров", k))

    def test_ctx_key_isolation_memory_epoch(self):
        c = self.mk(); k1, k2 = sc.make_ctx_key("s", 1), sc.make_ctx_key("s", 2)
        c.put("Кто мой создатель и что он любит", "ответ", k1)
        self.assertIsNone(c.get("Кто мой создатель и что он любит", k2))
        self.assertEqual(c.purge(k1), 1)
        self.assertIsNone(c.get("Кто мой создатель и что он любит", k1))

    def test_volatile_and_bad_answers_not_cached(self):
        c = self.mk(); k = "k"
        self.assertEqual(c.put("Какая сегодня погода в Мадриде", "солнечно", k)[1], "volatile_query")
        self.assertEqual(c.put("Объясни закон Ома подробно", "x", k, truncated=True)[1], "empty_or_truncated")
        self.assertEqual(c.put("да", "ответ", k)[1], "query_too_short")
        self.assertEqual(c.put("Объясни закон Ома подробно", "Ошибка: таймаут шлюза", k)[1], "error_like_answer")
        self.assertIsNone(c.get("сколько сейчас времени у тебя", k))
        self.assertEqual(c.stats()["entries"], 0)

    def test_ttl_expiry(self):
        c = self.mk(); k = "k"
        c.put("Объясни закон Ома подробно", "U=IR", k, ttl=100)
        self.assertIsNotNone(c.get("Объясни закон Ома подробно", k))
        self.clk.t += 101
        self.assertIsNone(c.get("Объясни закон Ома подробно", k))
        self.assertEqual(c.purge(), 1)

    def test_feedback_raises_threshold_then_disables(self):
        c = self.mk(base_thr=0.80); k = "k"
        eid, _ = c.put("Расскажи про архитектуру памяти системы NOX", "Память S03 хранит факты", k)
        q = "Расскажи про архитектуру памяти системы NOX пожалуйста"
        h = c.get(q, k); self.assertIsNotNone(h)
        c.feedback(eid, h.sim, False)
        self.assertIsNone(c.get(q, k))  # порог поднят выше sim
        c.feedback(eid, 0.5, False); c.feedback(eid, 0.5, False)
        self.assertEqual(c.stats()["disabled"], 1)
        self.assertIsNone(c.get(q, k))

    def test_feedback_ok_lowers_but_not_below_floor(self):
        c = self.mk(base_thr=0.90, floor_thr=0.88); k = "k"
        eid, _ = c.put("Расскажи про архитектуру памяти системы NOX", "Память S03 хранит факты", k)
        for _ in range(10): c.feedback(eid, 0.95, True)
        thr = c.db.execute("SELECT thr FROM e WHERE id=?", (eid,)).fetchone()[0]
        self.assertAlmostEqual(thr, 0.88)

    def test_explore_flag_and_agreed(self):
        c = self.mk(base_thr=0.80, explore_p=1.0); k = "k"
        c.put("Расскажи про архитектуру памяти системы NOX", "Память S03 хранит факты", k)
        h = c.get("Расскажи про архитектуру памяти системы NOX пожалуйста", k)
        self.assertTrue(h.explore)
        self.assertTrue(c.agreed("RAID объединяет диски в массив", "RAID объединяет диски в массив для надёжности"))
        self.assertFalse(c.agreed("RAID объединяет диски в массив", "Сегодня хорошая прогулка по парку"))

    def test_persistence_file(self):
        import os, tempfile
        d = tempfile.mkdtemp(); p = os.path.join(d, "c.sqlite")
        c = sc.SemanticCache(p); c.put("Объясни закон Ома подробно", "U=IR", "k"); c.db.close()
        c2 = sc.SemanticCache(p)
        self.assertEqual(c2.get("Объясни закон Ома подробно", "k").answer, "U=IR")

    def test_http_embedder_with_local_server(self):
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers["Content-Length"]); body = json.loads(self.rfile.read(n))
                v = [1.0, 0.0] if "ом" in body["input"].lower() else [0.0, 1.0]
                out = json.dumps({"data": [{"embedding": v}]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(out)
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            emb = sc.HttpEmbedder(f"http://127.0.0.1:{srv.server_port}", "bge-m3")
            c = sc.SemanticCache(":memory:", emb, base_thr=0.9, explore_p=0.0)
            c.put("Объясни закон Ома подробно", "U=IR", "k")
            h = c.get("Сформулируй закон Ома простыми словами", "k")
            self.assertIsNotNone(h); self.assertAlmostEqual(h.sim, 1.0)
            self.assertIsNone(c.get("Расскажи про устройство блока питания", "k"))
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
