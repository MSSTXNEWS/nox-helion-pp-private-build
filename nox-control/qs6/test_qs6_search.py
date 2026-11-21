import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qs6.s03_store import Store
from qs6.core_block import build_core_block, est_tokens
from qs6.memory_search import MemorySearch, HttpEmbedder, query_stems


class FakeEmb:
    model = "fake"

    def embed(self, texts):   # «смысл»: слова-синонимы дают общую ось
        axes = [("кофе", "чай", "напиток"), ("сервер", "хост", "машина")]
        return [[float(sum(1 for w in ax if w in t.casefold())) for ax in axes] + [0.01] for t in texts]


class BadEmb:
    model = "bad"

    def embed(self, texts):
        raise OSError("connection refused")


def make():
    s = Store()
    s.add_fact("Мессир любит чёрный кофе по утрам", kind="owner", pinned=True)
    s.add_fact("Сервер S1 работает на порту 8080", kind="fact")
    s.add_fact("Режим по умолчанию: тихий", kind="setting")
    s.add_fact("Ядро личности: говорить коротко", kind="core")
    s.add_episode("Вчера мы чинили сервер и пили чай", ts=time.time() - 86400)
    s.set_profile("имя", "NOX HELION", "persona")
    s.set_profile("обращение", "мессир", "owner")
    return s


class CoreT(unittest.TestCase):
    def test_block_sections_and_budget(self):
        s = make()
        b = build_core_block(s, budget_tokens=400)
        for part in ("Ядро:", "Владелец", "Установки:", "NOX HELION", "чёрный кофе"):
            self.assertIn(part, b["text"])
        self.assertNotIn("порту 8080", b["text"])        # обычный факт уровня 0 не в ядре
        self.assertLessEqual(b["tokens"], 400)
        small = build_core_block(s, budget_tokens=25)
        self.assertLessEqual(small["tokens"], 25)
        self.assertTrue(small["dropped"])
        self.assertEqual(est_tokens(small["text"]), small["tokens"])

    def test_priority_by_confidence(self):
        s = Store()
        a = s.add_fact("Установка альфа", kind="setting")
        b = s.add_fact("Установка бета", kind="setting")
        s.ladder.add_evidence(s.get_fact(b)["ladder_id"], "x1", "owner"); s.ladder.add_evidence(s.get_fact(b)["ladder_id"], "x2", "chat")
        out = build_core_block(s, budget_tokens=12)    # влезает одна строка
        self.assertIn("f:%d" % b, out["items"])
        self.assertNotIn("f:%d" % a, out["items"])

    def test_confirmed_ordinary_fact_included(self):
        s = Store()
        f = s.add_fact("Подтверждённый обычный факт")
        s.db.execute("UPDATE mem_facts SET owner_confirmed=1"); s.db.commit()
        self.assertIn("Подтверждённое:", build_core_block(s)["text"])


class SearchT(unittest.TestCase):
    def test_fts_morphology_and_rerank(self):
        s = make()
        ms = MemorySearch(s, use_env_embedder=False)
        r = ms.search("какой порт у сервера")
        self.assertEqual(r["mode"], "fts")
        self.assertIn("порту 8080", r["hits"][0]["text"])
        self.assertTrue(any("векторный поиск выключен" in w for w in r["warnings"]))
        self.assertNotIn("vector", r["hits"][0]["parts"])

    def test_like_fallback(self):
        s = make()
        s.fts = False
        r = MemorySearch(s, use_env_embedder=False).search("кофе утром")
        self.assertEqual(r["mode"], "like")
        self.assertIn("кофе", r["hits"][0]["text"])

    def test_kinds_filter_and_empty(self):
        s = make()
        ms = MemorySearch(s, use_env_embedder=False)
        self.assertTrue(all(h["type"] == "episode" for h in ms.search("сервер", kinds=["episode"])["hits"]))
        self.assertEqual(ms.search("")["hits"], [])
        self.assertEqual(ms.search("zzzqqq")["hits"], [])

    def test_recency_and_confidence_affect_order(self):
        s = Store()
        old = s.add_fact("Тестовая запись про лампу", ts=time.time() - 400 * 86400)
        new = s.add_fact("Тестовая запись про лампу сегодня")
        r = MemorySearch(s, use_env_embedder=False).search("тестовая запись про лампу")
        self.assertEqual(r["hits"][0]["ref"], "f:%d" % new)

    def test_vector_backend(self):
        s = make()
        ms = MemorySearch(s, embedder=FakeEmb())
        n, warn = ms.index_vectors()
        self.assertEqual((n, warn), (7, None))
        self.assertEqual(ms.index_vectors(), (0, None))        # уже посчитано
        r = ms.search("напиток по утрам")                       # нет общих слов, но вектор «кофе/чай/напиток»
        self.assertIn("vector", r["mode"])
        self.assertTrue(any("кофе" in h["text"] or "чай" in h["text"] for h in r["hits"][:3]))
        self.assertIn("vector", r["hits"][0]["parts"])

    def test_vector_failure_falls_back(self):
        s = make()
        ms = MemorySearch(s, embedder=BadEmb())
        r = ms.search("сервер")
        self.assertEqual(r["mode"], "fts")
        self.assertTrue(any("вектор недоступен" in w for w in r["warnings"]))
        self.assertTrue(r["hits"])
        n, warn = ms.index_vectors()
        self.assertEqual(n, 0)
        self.assertIn("недоступен", warn)

    def test_http_embedder_from_env_and_formats(self):
        self.assertIsNone(HttpEmbedder.from_env({}))
        calls = []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.path, body))
                n = len(body.get("input") or body.get("inputs"))
                out = ({"data": [{"index": i, "embedding": [1.0, float(i)]} for i in range(n)]} if self.path == "/v1/embeddings"
                       else [[2.0, float(i)] for i in range(n)])
                b = json.dumps(out).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def log_message(self, *a):
                pass
        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_port
        e = HttpEmbedder.from_env({"NOX_EMBED_URL": base + "/v1/embeddings", "NOX_EMBED_MODEL": "bge-m3"})
        self.assertEqual(e.embed(["a", "b"]), [[1.0, 0.0], [1.0, 1.0]])
        self.assertEqual(calls[0][1]["model"], "bge-m3")
        e2 = HttpEmbedder(base + "/embed")
        self.assertEqual(e2.embed(["a"]), [[2.0, 0.0]])
        self.assertIn("inputs", calls[1][1])

    def test_stems(self):
        self.assertEqual(query_stems("Какой порт у сервера?"), ["како", "порт", "серве"])
        self.assertIn("серве", query_stems("сервера"))


if __name__ == "__main__":
    unittest.main()
