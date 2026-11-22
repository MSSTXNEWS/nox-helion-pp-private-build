"""Страница «Ядро»: /v1/core/traces, /summary, /view/<id>, v0 в /health. Фейковые fast/GLM из test_core."""
import json, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_core as TC
import core_view as V


class TestCoreView(TC.Base):
    fast_fn = staticmethod(lambda s, u, n: "Ответ готов, мессир, номер %d." % n)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.ids = []
        for q in ("как устроена твоя память", "привет", "что ты умеешь"):
            r = await self.post(q)
            self.ids.append(r["nox"]["turn_id"])
            await self.chron(self.ids[-1])

    async def test_traces_list_newest_first_and_filter(self):
        st, d = await self.get("/v1/core/traces?limit=2")
        self.assertEqual(st, 200)
        rows = d["traces"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], self.ids[-1])
        for k in ("id", "ts", "user", "path", "arm", "verdict", "total_ms", "recall_n", "degraded", "council", "status"):
            self.assertIn(k, rows[0])
        _, none = await self.get("/v1/core/traces?path=НЕТ-ТАКОГО")
        self.assertEqual(none["traces"], [])
        _, big = await self.get("/v1/core/traces?limit=99999")
        self.assertEqual(len(big["traces"]), 3)

    async def test_eval_hidden_unless_asked(self):
        r = await self.post("тестовый вопрос бенча", headers={"X-NOX-Eval": "1", "X-NOX-Bench": "t"})
        _, d = await self.get("/v1/core/traces")
        self.assertNotIn(r["nox"]["turn_id"], [x["id"] for x in d["traces"]])
        _, d = await self.get("/v1/core/traces?eval=1")
        self.assertIn(r["nox"]["turn_id"], [x["id"] for x in d["traces"]])

    async def test_summary_aggregates_and_v0(self):
        st, s = await self.get("/v1/core/summary")
        self.assertEqual(st, 200)
        self.assertEqual(s["turns"], 3)
        self.assertEqual(sum(s["paths"].values()), 3)
        self.assertEqual(sum(s["verdicts"].values()), 3)
        self.assertLessEqual(s["total_ms"]["p50"], s["total_ms"]["max"])
        self.assertIn("v0", s); self.assertIn("ok", s["v0"])
        self.assertEqual(s["conscience_mode"], "enforce")

    async def test_view_has_ordered_steps_and_404(self):
        st, v = await self.get("/v1/core/view/" + self.ids[0])
        self.assertEqual(st, 200)
        names = [x["name"] for x in v["steps"]]
        self.assertEqual(names[0], "perception"); self.assertIn("conscience", names)
        self.assertTrue(all("ms" in x for x in v["steps"]))
        st, _ = await self.get("/v1/core/view/nope")
        self.assertEqual(st, 404)

    async def test_health_has_v0_cached(self):
        _, h = await self.get("/health")
        self.assertIn("v0", h)
        _, h2 = await self.get("/health")
        self.assertEqual(h["v0"], h2["v0"])

    async def test_disk_traces_after_restart(self):
        self.core.turns.clear()                        # как после рестарта ядра: остались только файлы трасс
        _, d = await self.get("/v1/core/traces")
        self.assertEqual({x["id"] for x in d["traces"]}, set(self.ids))


class TestUnits(unittest.TestCase):
    def test_summarize_tolerates_sparse_trace(self):
        r = V.summarize({"turn_id": "x"})
        self.assertEqual((r["id"], r["council"], r["degraded"], r["verdict"]), ("x", None, [], None))

    def test_query_parsing(self):
        self.assertEqual(V.query_int("a=1&limit=7", "limit", 30), 7)
        self.assertEqual(V.query_int("limit=abc", "limit", 30), 30)
        self.assertIsNone(V.query_str("path=../../etc", "path") if False else V.query_str("x=1", "path"))


if __name__ == "__main__":
    unittest.main()
