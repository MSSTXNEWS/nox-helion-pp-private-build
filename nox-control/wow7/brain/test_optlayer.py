import asyncio, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NOX_STATE", tempfile.mkdtemp())
import conscience as C
import optlayer as OL
import nox_core


class St:
    intent, opts, council, advice, speaker, user_text = "question", {}, False, "", "owner", "расскажи подробно как устроена память ядра"
    mem = {"core": "память: A"}


class T(unittest.TestCase):
    def test_address(self):
        self.assertEqual(C.fix_address("Привет, брат! Бро, как ты, Брат?"), "Привет, мессир! Мессир, как ты, Мессир?")
        self.assertEqual(C.fix_address("обратно и братство"), "обратно и братство")

    def test_status_question(self):
        for q in ("как сервер?", "Как там сервер", "что с сервером", "как железо"):
            self.assertTrue(C.is_status_question(q), q)

    def test_telemetry_render(self):
        txt = OL.render_telemetry({"ts": 0, "gpus": [{"name": "X", "util": 12, "mem_used_mib": 2048, "mem_total_mib": 8192, "temp_c": 50}],
                                   "load": [1, 2, 3], "cpus": 8, "ram_total_gb": 64, "ram_avail_gb": 32, "glm": "жива", "glm_busy": 0,
                                   "memory": {"facts": 5, "episodes": 2, "profile": 1}})
        for s in ("загрузка 12%", "2.0 из 8.0 ГБ", "50°C", "свободно 32 из 64", "фактов 5", "занятых слотов 0"):
            self.assertIn(s, txt)
        o = OL.OptLayer(tempfile.mkdtemp()); o._tele = {"ts": 9e12, "load": [1, 1, 1], "cpus": 2}
        self.assertIn("<замеры_сервера>", o.telemetry_block("как сервер?"))

    def test_cache(self):
        o = OL.OptLayer(tempfile.mkdtemp()); st = St()
        self.assertIsNone(o.lookup(st))
        self.assertTrue(o.store(st, "Память ядра - это слои фактов и эпизодов."))
        h = o.lookup(st)
        self.assertTrue(h and h.exact)
        st.mem = {"core": "память: B"}                  # другая память хода -> другой ключ -> промаха
        self.assertIsNone(o.lookup(st))
        st2 = St(); st2.opts = {"eval": True}
        self.assertIsNone(o.lookup(st2))

    def test_prio(self):
        async def go():
            L, order = nox_core.PrioLock(), []
            await L.acquire(0)
            async def w(n, p):
                await L.acquire(p); order.append(n); L.release()
            ts = [asyncio.create_task(w("bg", 2)), asyncio.create_task(w("chat", 0))]
            await asyncio.sleep(0.05); L.release(); await asyncio.gather(*ts)
            return order
        self.assertEqual(asyncio.run(go()), ["chat", "bg"])


if __name__ == "__main__":
    unittest.main()
