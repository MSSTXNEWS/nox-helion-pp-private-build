import os, sys, json, time, tempfile, unittest, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import life_time as L
MSK = L.MSK
def at(h, m=0, day=10): return dt.datetime(2026, 11, day, h, m, tzinfo=MSK).timestamp()
def mk(root, convs=None, sn=None):
    for d in ("state/web/web_conv", "state/core", "state/mind"): os.makedirs(root + "/" + d, exist_ok=True)
    json.dump(sn or {"telemetry": {"vram_pct": 50, "gpu_temp": 60, "disk_free_gb": 40}, "last_talk": {"hours_ago": 30}}, open(root + "/state/core/self_now.json", "w"))
    for i, ms in enumerate(convs or []): json.dump({"id": "c%d" % i, "messages": ms}, open(root + "/state/web/web_conv/c%d.json" % i, "w"))
class T(unittest.TestCase):
    def setUp(self): self.r = tempfile.mkdtemp()
    def test_quiet(self):
        self.assertTrue(L.is_quiet(dt.datetime(2026, 1, 1, 23, 0, tzinfo=MSK))); self.assertTrue(L.is_quiet(dt.datetime(2026, 1, 1, 7, 59, tzinfo=MSK)))
        self.assertFalse(L.is_quiet(dt.datetime(2026, 1, 1, 8, 0, tzinfo=MSK))); self.assertFalse(L.is_quiet(dt.datetime(2026, 1, 1, 22, 59, tzinfo=MSK)))
    def test_threads_and_return(self):
        t0 = at(10)
        mk(self.r, [[{"role": "user", "content": "давай обсудим архитектуру памяти позже", "ts": t0}, {"role": "assistant", "content": "хорошо", "ts": t0 + 5}, {"role": "user", "content": "кстати, как работает консолидация памяти?", "ts": t0 + 9}]])
        reg = L.update_registry(self.r, t0 + 60); self.assertEqual(len(reg["threads"]), 1); th = reg["threads"][0]; self.assertEqual(len(th["id"]), 10)
        self.assertEqual(L.due_threads(reg, t0 + 3 * 3600), []); self.assertEqual(len(L.due_threads(reg, t0 + 9 * 3600)), 1)
    def test_no_text_in_registry(self):
        t0 = at(10); mk(self.r, [[{"role": "user", "content": "секретная фраза номер один проверка?", "ts": t0}, {"role": "assistant", "content": "ок", "ts": t0 + 1}, {"role": "user", "content": "секретная фраза номер один проверка?", "ts": t0 + 2}]])
        L.update_registry(self.r, t0 + 9); s = open(self.r + "/state/mind/threads.json").read(); self.assertNotIn("номер один проверка?", s)
    def test_done_closes(self):
        t0 = at(10); mk(self.r, [[{"role": "user", "content": "потом посмотрим логи", "ts": t0}, {"role": "assistant", "content": "ок", "ts": t0 + 1}, {"role": "user", "content": "готово, закрыто", "ts": t0 + 2}]])
        self.assertEqual(L.update_registry(self.r, t0 + 9)["threads"], [])
    def test_no_initiative_in_quiet(self):
        mk(self.r)
        for h in (23, 0, 3, 7): self.assertIsNone(L.decide(at(h, 30), self.r))
    def test_limit_3_and_gap(self):
        mk(self.r, sn={"telemetry": {"disk_free_gb": 40}, "last_talk": {"hours_ago": 30}, "morning_thought": {"text": "гипотеза про связь сна и памяти"}})
        sent = 0
        for k in range(0, 24 * 60, 5):
            ts = at(0) + k * 60
            r = L.tick(ts, self.r)
            if r.get("sent"): sent += 1; self.assertFalse(L.is_quiet(L.msk(ts)))
        self.assertLessEqual(sent, 3); self.assertGreaterEqual(sent, 1)
    def test_red_at_night(self):
        mk(self.r, sn={"telemetry": {"disk_free_gb": 5}, "last_talk": {"hours_ago": 1}})
        d = L.decide(at(2), self.r); self.assertEqual(d["reason"], "red"); L.commit(d, at(2), self.r)
        self.assertIsNone(L.decide(at(2, 10), self.r))
    def test_off_flags(self):
        mk(self.r); open(self.r + "/state/life_time.off", "w").close(); self.assertTrue(L.tick(at(12), self.r)["off"])
    def test_morning_max5_and_real(self):
        mk(self.r, sn={"telemetry": {"vram_pct": 61, "gpu_temp": 55, "disk_free_gb": 33}, "morning_thought": {"text": "связь между сном и ошибками ворот требует проверки"}})
        m = L.morning_lines(at(8), self.r); self.assertLessEqual(len(m), 5); self.assertTrue(any("61" in x for x in m)); self.assertTrue(any("гипотеза" in x for x in m))
    def test_evening_gratitude(self):
        mk(self.r, sn={"telemetry": {"disk_free_gb": 40}, "gratitude": {"text": "за терпение"}}); e = L.evening_lines(at(22, 30), self.r)
        self.assertTrue(any("за терпение" in x for x in e)); self.assertTrue(any(x.startswith("Что вышло плохо") for x in e))
    def test_memory_blocks(self):
        mk(self.r); b = L.memory_blocks("creator", at(12), self.r); self.assertEqual(set(b), {"persona", "creator", "goals", "now"}); self.assertIn("МСК", b["now"])
    def test_address_rotation(self):
        self.assertIn("без обращения", L.address_hint(["Да, Создатель, сделано."], "creator", 3))
        n = sum(1 for t in range(200) if L.address_hint([], "creator", t)); self.assertTrue(40 < n < 160)
if __name__ == "__main__": unittest.main()
