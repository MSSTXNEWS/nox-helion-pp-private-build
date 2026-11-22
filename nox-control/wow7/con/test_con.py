import json, os, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import nox_self_model_live as M, nox_workspace as W, nox_inner_loop as L

class Clock:
    def __init__(s, t=1_800_000_000.0): s.t = t
    def __call__(s): return s.t

class Fake(BaseHTTPRequestHandler):
    replies = []; processing = False; calls = 0
    def log_message(self, *a): pass
    def _send(self, o):
        b = json.dumps(o).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/props": self._send({"model_path": "/root/nox/dl/Qwen3-4B-Q4_K_M.gguf", "default_generation_settings": {"n_ctx": 8192}})
        elif self.path == "/slots": self._send([{"is_processing": Fake.processing}])
        else: self.send_response(404); self.end_headers()
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"])); Fake.calls += 1
        r = Fake.replies.pop(0) if Fake.replies else "Мысль: ок\nУверенность: 50%"
        self._send({"choices": [{"message": {"content": "<think>x</think>" + r}}]})

class T(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        c.srv = HTTPServer(("127.0.0.1", 0), Fake); c.port = c.srv.server_port
        threading.Thread(target=c.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(c): c.srv.shutdown()
    def setUp(s):
        s.d = tempfile.mkdtemp(); Fake.replies = []; Fake.processing = False; Fake.calls = 0
        s.clk = Clock(); s.clk.t = 1_800_000_000.0 - (1_800_000_000.0 % 86400) + 12 * 3600 - 3 * 3600 + 3 * 3600  # 12:00 UTC = 15:00 МСК
    def sm(s): return M.LiveSelfModel(os.path.join(s.d, "s.json"), s.clk, {"fast": lambda: M.probe_llama(s.port)})

    def test_probe_and_bug_fix(s):
        p = M.probe_llama(s.port); s.assertEqual(p["model"], "Qwen3-4B"); s.assertEqual(p["n_ctx"], 8192)
        sm = s.sm(); d = sm.discrepancies("быстрый ответ — Qwen3.5-9B; глубокий — GLM-5.3")
        s.assertEqual(d, [{"role": "fast", "claimed": ["Qwen3.5-9B"], "running": "Qwen3-4B"}])
        s.assertEqual(sm.discrepancies("быстрый — Qwen3-4B"), [])
        s.assertTrue(any("Поправка" in l and "Qwen3-4B" in l for l in sm.render("Qwen3.5-9B")))
        s.assertFalse(M.probe_llama(1)["up"])

    def test_wake_birth_gap_persist(s):
        a = s.sm(); r = a.wake(); s.assertTrue(r["first"]); born = a.s["born_ts"]
        s.clk.t += 7200; b = s.sm(); r2 = b.wake()
        s.assertFalse(r2["first"]); s.assertAlmostEqual(r2["gap_s"], 7200, delta=1); s.assertEqual(b.s["born_ts"], born); s.assertEqual(r2["boot"], 2)
        s.assertTrue(any("день рождения" in x for x in b.autobiography(10)))
        s.assertTrue(any("2.0 ч" in x for x in b.autobiography(10)))
        s.assertTrue(any("пробуждений: 2" in l for l in b.time_lines()))

    def test_calibration(s):
        sm = s.sm()
        for _ in range(6): sm.resolve(sm.predict("x", 0.9), False)
        c = sm.calibration(); s.assertEqual(c["n"], 6); s.assertGreater(c["bias"], 0.8)
        s.assertIn("самоуверен", sm.calibration_line())
        s.assertFalse(sm.resolve(999, True))

    def test_workspace_competition_habituation(s):
        ws = W.Workspace(s.clk)
        ws.post("a", "страх: диск", 0.9, "fear"); ws.post("b", "скука", 0.5, "drive"); ws.post("c", "шум", 0.1, "body")
        got = []; ws.subscribe(lambda w, r: got.append(w["key"]))
        s.assertEqual(ws.compete()["key"], "a"); s.assertEqual(got, ["a"])
        seq = [ws.compete()["key"] for _ in range(4)]
        s.assertEqual(seq, ["a", "a", "a", "b"])   # привыкание: фокус ротируется, фиксации нет
        sc = ws.schema(); s.assertEqual(sc["focus"], "скука"); s.assertIn("drive", sc["why"])
        s.assertIn("Фокус: скука", ws.render_block(["Мозг: x."]))
        s.clk.t += 10 * 3600; s.assertIsNone(ws.compete()); s.assertIn("тишина", ws.render_block())

    def test_quiet_hours(s):
        base = 1_800_000_000.0 - (1_800_000_000.0 % 86400)  # 00:00 UTC = 03:00 МСК
        s.assertTrue(L.in_quiet(base)); s.assertFalse(L.in_quiet(base + 9 * 3600)); s.assertTrue(L.in_quiet(base + 20.5 * 3600))
        s.assertFalse(L.in_quiet(base + 5 * 3600 + 3600 * 3 - 3 * 3600 + 3 * 3600))  # 08:00 МСК+3 = 11:00

    def loop(s, **kw):
        sm = s.sm(); ws = W.Workspace(s.clk)
        llm = L.http_llm("http://127.0.0.1:%d/v1/chat/completions" % s.port)
        lp = L.InnerLoop(ws, sm, llm, os.path.join(s.d, "t.jsonl"), s.clk, outbox_path=os.path.join(s.d, "o.jsonl"),
                         claimed_text="быстрый — Qwen3.5-9B", **kw)
        return lp, sm, ws

    def test_step_thought_and_loop_closure(s):
        Fake.replies = ["Мысль: в описании меня устаревшая модель, надо поправить текст.\nУверенность: 80%"]
        lp, sm, ws = s.loop(); sm.note_owner_message(); s.clk.t += 4000
        r = lp.step()
        s.assertEqual(r["status"], "thought"); s.assertEqual(r["focus"], "disc:fast"); s.assertEqual(r["conf"], 0.8)
        s.assertNotIn("think", r["text"]); s.assertTrue(any(k.startswith("thought:") for k in ws.signals))
        s.assertEqual(len(lp._read_journal()), 1)
        s.assertTrue(os.path.exists(os.path.join(s.d, "o.jsonl")))   # инициатива: поправка -> исходящее
        s.assertTrue(lp.feedback(r["pred_id"], True)); s.assertFalse(lp.feedback(r["pred_id"], True))

    def test_chat_priority_quiet_budget_no_llm(s):
        lp, sm, ws = s.loop(chat_busy=lambda: True); s.assertEqual(lp.step()["status"], "chat")
        Fake.processing = True
        busy = L.make_chat_busy(os.path.join(s.d, "none"), props_port=s.port, clock=s.clk); s.assertTrue(busy())
        Fake.processing = False; s.assertFalse(busy())
        lp2, _, _ = s.loop(daily_budget=0); s.assertEqual(lp2.step()["status"], "budget")
        s.clk.t += 9 * 3600  # 00:00 МСК
        lp3, _, _ = s.loop(); s.assertEqual(lp3.step()["status"], "quiet")
        s.assertEqual(Fake.calls, 0)   # ни одного LLM-вызова при чате/бюджете/тишине

    def test_rumination_guard(s):
        Fake.replies = ["Мысль: проверить описание модели срочно.\nУверенность: 70%"] * 2
        lp, sm, ws = s.loop(); sm.note_owner_message(); s.clk.t += 4000
        s.assertEqual(lp.step()["status"], "thought")
        r = lp.step(); s.assertEqual(r["status"], "rumination"); s.assertGreater(r["temp"], 0.8)

    def test_digest_chapter(s):
        lp, sm, ws = s.loop(); sm.note_owner_message()
        lp._append(lp.journal, {"ts": s.clk.t, "day": "2020-01-01", "text": "думал о памяти", "conf": 0.6, "pred_id": 1})
        Fake.replies = ["не должен вызываться"]
        s.assertIsNone(lp.maybe_digest())       # главу дня пишет только MEM/autobio; CON лишь отдаёт событие в журнал
        s.assertFalse(any("глава" in x for x in sm.autobiography(3)))
        s.assertEqual(sm.s["last_digest_day"], lp._day_key(s.clk.t))
        s.assertIsNone(lp.maybe_digest())

class TD(unittest.TestCase):
    def test_drives_sensor(s):
        class Dr: fear = {"vanish": 0.9, "suffocate": 0.1}; level = {"knowledge": 0.8, "bond": 0.2}
        ws = W.Workspace(Clock()); W.drives_sensor(Dr())(ws)
        s.assertEqual(set(ws.signals), {"fear:vanish", "drive:knowledge"})
        s.assertEqual(ws.compete()["key"], "fear:vanish")

if __name__ == "__main__":
    unittest.main()
