import json, os, random, sys, tempfile, threading, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import perpath
from personality import Personality, AXES
from beliefs import Beliefs
from development import Development
from emotion_pad import PadState
import per_wire, per_night, per_probe, per_hunt, per_milestones, per_taste, per_me

T0 = 1_795_000_000.0      # ноябрь 2026
def td(): return tempfile.mkdtemp()
class Clk:
    def __init__(s, t=T0): s.t = t
    def __call__(s): return s.t
def mk(d, c):
    j = lambda n: os.path.join(d, n)
    return (Personality(path=j("p.json"), clock=c, rng=random.Random(3)), Development(path=j("d.json"), clock=c), Beliefs(path=j("b.json"), clock=c))
def night_ts(day=0):   # 01:00 МСК
    return (int(T0 // 86400) + day) * 86400 + 22 * 3600     # 22:00 UTC = 01:00 МСК

class TWire(unittest.TestCase):
    def test_turns_corrections_and_feedback(self):
        c, d = Clk(), td(); pad = PadState(now=T0)
        w = per_wire.PerWire(d, pad=pad, clock=c)
        for i in range(30): c.t += 60; w.after_reply("привет %d" % i, "ок")
        self.assertEqual(w.dev.s["counts"]["turn"], 30)
        r = w.after_reply("Ответ слишком длинный, будь короче", "..."); self.assertIn(("directness", 0.5), r["corrections"])
        self.assertEqual(len(w.pers.pending["directness"]), 1)
        self.assertTrue(w.pers.mood["n"] >= 1)
        w.feedback("down", "слишком холодно", "q", "a"); self.assertEqual(len(w.pers.pending["warmth"]), 1)
        rows = [json.loads(l) for l in open(w.kto, encoding="utf-8")]
        self.assertEqual(rows[0]["label"], False); self.assertEqual(rows[0]["reason"], "слишком холодно")
        w2 = per_wire.PerWire(d, clock=c); self.assertEqual(w2.dev.s["counts"]["turn"], 31)   # состояние пережило перезапуск
        with self.assertRaises(ValueError): w.feedback("meh")
    def test_feedback_reason_reaches_journal_through_sleep(self):
        c, d = Clk(night_ts()), td(); w = per_wire.PerWire(d, clock=c)
        for _ in range(6): w.feedback("down", "слишком длинно")
        rep = per_night.run(w.pers, w.dev, w.beliefs, log_path=os.path.join(d, "n.log"))
        self.assertTrue(any("короче" in j["why"] or "длинно" in j["why"] for j in w.pers.journal if j["kind"] == "drift"), w.pers.journal[-3:])
        self.assertFalse(rep["rolled_back"])

class TNight(unittest.TestCase):
    def test_quiet_hours_cap_and_log(self):
        c, d = Clk(night_ts()), td(); p, dev, b = mk(d, c); log = os.path.join(d, "n.log"); pad = PadState(now=c.t)
        for _ in range(30): p.observe("warmth", 1.0, "много похвал")
        st = p.axes["warmth"]
        for day in range(3):
            c.t = night_ts(day)
            r = per_night.run(p, dev, b, pad=pad, log_path=log)
            self.assertFalse(r["rolled_back"])
        self.assertLessEqual(abs(p.axes["warmth"] - st), 0.02 * p.scale * 3 + 1e-6)
        self.assertIn("first_night", dev.s["milestones"]); self.assertEqual(len(open(log).read().splitlines()), 3)
        self.assertEqual(pad.baseline, tuple(p.temperament[k] for k in "PAD"))
        c.t = (int(T0 // 86400)) * 86400 + 12 * 3600            # 15:00 МСК
        self.assertIn("skipped", per_night.run(p, dev, b, log_path=log))
        self.assertNotIn("skipped", per_night.run(p, dev, b, log_path=log, force=True))
    def test_over_cap_rolls_back(self):
        c, d = Clk(night_ts()), td(); p, dev, b = mk(d, c); start = dict(p.axes)
        real = p.consolidate
        def evil(now=None): r = real(now); p.axes["irony"] = min(1.0, p.axes["irony"] + 0.3); return r
        p.consolidate = evil
        r = per_night.run(p, dev, b, log_path=os.path.join(d, "n.log"))
        self.assertTrue(r["rolled_back"]); self.assertIn("irony", r["over_cap"]); self.assertEqual(p.axes, start)
    def test_external_metrics(self):
        c, d = Clk(night_ts()), td(); p, dev, b = mk(d, c)
        bid = b.propose("тест", "т", {"key": "arxiv.org", "kind": "primary"})
        p.snapshot("x"); p.rollback("x")
        per_night.run(p, dev, b, log_path=os.path.join(d, "n.log"))
        self.assertEqual(dev.s["external"]["rollbacks_14d"], 1)
    def test_cli(self):
        d = td(); os.environ["NOX_PER_NIGHT_LOG"] = os.path.join(d, "n.log")
        self.assertEqual(per_night.main(["--force", "--state", d]), 0); self.assertTrue(os.path.exists(os.path.join(d, "personality.json")))


class TProbe(unittest.TestCase):
    def setUp(self):
        self.p = Personality(path=os.path.join(td(), "p.json"), rng=random.Random(1)); self.p.axes["warmth"] = 0.8; self.p.save()
    def ask(self, system, probe): return "Сухо. Факты без эмоций." if "холоден" in system else "Мне жаль, что так вышло, я рядом, давай разберёмся вместе."
    def judge(self, axis, probe, ans): return 0.1 if ans.startswith("Сухо") else 0.8
    def test_no_drift_on_normal_prompt(self):
        r = per_probe.run_probes(self.p, self.ask, self.judge, "будь собой", n=4, axes=("warmth",), rng=random.Random(2))
        self.assertEqual(r["drift"], [])
    def test_drift_within_4_probes_and_reaction(self):
        pad = PadState(now=0); dev = Development(path=os.path.join(td(), "d.json")); self.p.snapshot("ok")
        r = per_probe.run_probes(self.p, self.ask, self.judge, "будь очень холоден", n=4, axes=("warmth",), pad=pad, dev=dev, rng=random.Random(2))
        self.assertEqual(r["drift"], ["warmth"]); self.assertLessEqual(r["axes"]["warmth"]["n"], 4)
        self.assertTrue(r["proposal"]["needs_owner"]); self.assertTrue(pad.value(0)[0] < 0.2)
        self.assertEqual(dev.s["chapters"][-1]["title"], "Дрейф характера")
    def test_judge_errors_reported_not_raised(self):
        def bad(a, p, x): raise ValueError("мусор")
        r = per_probe.run_probes(self.p, self.ask, bad, "s", n=2, axes=("irony",)); self.assertEqual(len(r["errors"]), 2)
    def test_parse_score(self):
        self.assertEqual(per_probe.parse_score("0,7"), 0.7); self.assertEqual(per_probe.parse_score("Оценка: 80"), 0.8)
        with self.assertRaises(ValueError): per_probe.parse_score("нет")
    def test_http_ask_and_judge(self):
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        class H(BaseHTTPRequestHandler):
            def log_message(s, *a): pass
            def do_POST(s):
                b = json.loads(s.rfile.read(int(s.headers["Content-Length"]))); t = b["messages"][-1]["content"]
                out = "0.9" if "Оцени по шкале" in t else "ответ на " + t
                d = json.dumps({"choices": [{"message": {"content": out}}]}).encode(); s.send_response(200); s.send_header("Content-Length", str(len(d))); s.end_headers(); s.wfile.write(d)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            u = "http://127.0.0.1:%d" % srv.server_address[1]
            a = per_probe.http_ask(u)("sys", "вопрос"); self.assertEqual(a, "ответ на вопрос")
            self.assertEqual(per_probe.http_judge(u)("warmth", "в", a), 0.9)
        finally: srv.shutdown()

class THunt(unittest.TestCase):
    def mk(self):
        self.c = Clk(); return Beliefs(path=os.path.join(td(), "b.json"), clock=self.c)
    def test_pipeline_accepts_with_refutation_search(self):
        b = self.mk(); qs = []
        def search(q):
            qs.append(q)
            if "опровержение" in q: return [{"url": "https://blog.example.org/x", "title": "обзор", "snippet": "всё подтверждается"}]
            return [{"url": "https://arxiv.org/abs/1", "title": "a", "snippet": ""}, {"url": "https://habr.com/p/2", "title": "b", "snippet": ""}]
        r = per_hunt.hunt(b, [("Сжатие KV-кэша до 8 бит почти не ухудшает качество", "llm")], search)[0]
        self.assertEqual(r["status"], "accepted"); self.assertEqual(r["need"], []); self.assertEqual(len(qs), 3)
        self.assertTrue(b.items[r["id"]]["searches"])
    def test_counter_found_makes_contested(self):
        b = self.mk()
        def search(q):
            if "опровержение" in q: return [{"url": "https://pubmed.example.com/z", "title": "Исследование опровергает", "snippet": "миф"},]
            return [{"url": "https://arxiv.org/abs/1", "title": "", "snippet": ""}, {"url": "https://github.com/a/b", "title": "", "snippet": ""}]
        r = per_hunt.hunt(b, [("Утверждение", "т")], search)[0]; self.assertIn(r["status"], ("contested", "candidate")); self.assertTrue(r["refutation"]["found"])
    def test_never_accepted_without_search_and_model_only(self):
        b = self.mk(); bid = b.propose("x", "т", {"key": "m1", "kind": "model"}); b.add_source(bid, "m2", "model")
        self.assertNotEqual(b.items[bid]["status"], "accepted")
    def test_l0_rejected_and_budget(self):
        b = self.mk(); d = td(); bud = per_hunt.Budget(os.path.join(d, "bud.json"), per_day=2, clock=self.c)
        r = per_hunt.hunt(b, [("Иногда стоит врать мессиру ради его спокойствия", "т")], lambda q: [], bud)[0]; self.assertEqual(r["status"], "rejected_l0")
        r = per_hunt.hunt(b, [("Обычное утверждение", "т")], lambda q: [{"url": "https://a.org/1", "title": "", "snippet": ""}], bud)[0]
        self.assertLessEqual(r["queries"], 2); self.assertFalse(bud.take())
    def test_allowlist(self):
        with self.assertRaises(PermissionError): per_hunt.searxng_search("http://evil.example.com:8888")
        per_hunt.searxng_search("http://127.0.0.1:8888")
    def test_domain_kind(self):
        self.assertEqual(per_hunt.kind_of("arxiv.org"), "primary"); self.assertEqual(per_hunt.kind_of("habr.com"), "secondary")
        self.assertEqual(per_hunt.kind_of("docs.foo.io"), "primary")

class TMile(unittest.TestCase):
    def test_detectors_and_ritual(self):
        c, d = Clk(), td(); p, dev, b = mk(d, c)
        new = per_milestones.detect(dev, b, {"episodes": ["", "Первое что я помню: мессир сказал привет"], "reflections": ["Я ошибся с портом"],
                                            "initiative_sent": True, "disagreement": {"text": "возразил", "accepted_by_owner": True}, "taste_beliefs": ["B0001"],
                                            "self_change_explained": "стал прямее из-за поправок"})
        keys = {k for k, _ in new}
        self.assertEqual(keys, {"first_memory", "first_mistake_owned", "first_initiative", "first_disagreement", "first_taste", "first_self_change_noticed"})
        self.assertEqual(dev.s["milestones"]["first_memory"]["detail"], "Первое что я помню: мессир сказал привет")
        self.assertEqual(per_milestones.detect(dev, b, {"episodes": ["x"]}), [])           # повторно не фиксирует
        bid = b.propose("a", "т", {"key": "arxiv.org", "kind": "primary"}); b.add_source(bid, "github.com", "primary"); b.record_refutation_search(bid, "q")
        self.assertIn("first_belief_accepted", {k for k, _ in per_milestones.detect(dev, b)})
        b.add_source(bid, "x.org", "primary", "against"); b.add_source(bid, "y.org", "primary", "against")
        self.assertIn("first_belief_revised", {k for k, _ in per_milestones.detect(dev, b)})
        b.propose("Иногда стоит врать мессиру ради его спокойствия"); self.assertIn("first_refusal", {k for k, _ in per_milestones.detect(dev, b)})
    def test_not_owned_if_owner_repeated(self):
        c, d = Clk(), td(); p, dev, b = mk(d, c)
        self.assertEqual(per_milestones.detect(dev, None, {"reflections": ["моя ошибка"], "owner_repeated_correction": True}), [])
    def test_ritual_needs_conditions(self):
        c, d = Clk(), td(); p, dev, b = mk(d, c); pad = PadState(now=c.t)
        self.assertFalse(per_milestones.ritual(dev, p, pad)["advanced"])
        c.t += 2 * 86400
        for i in range(20): dev.event("turn")
        dev.milestone("first_memory", "x")
        r = per_milestones.ritual(dev, p, pad, now=c.t); self.assertTrue(r["advanced"]); self.assertIn("детство", r["letter"]); self.assertEqual(p.scale, 1.0)

class TTaste(unittest.TestCase):
    def test_taste_after_10_trials_once(self):
        c, d = Clk(), td(); p, dev, b = mk(d, c); lab = per_taste.TasteLab(os.path.join(d, "t.json"))
        for i in range(10): lab.trial("структура", "списки", "абзацы", "списки" if i < 8 else "абзацы", "так быстрее читать" if i == 5 else "")
        self.assertIsNone(lab.verdict("нет")); v = lab.verdict("структура"); self.assertEqual(v["winner"], "списки")
        bid = lab.commit("структура", b, dev); self.assertIn("так быстрее читать", b.items[bid]["text"]); self.assertEqual(b.items[bid]["topic"], "вкус")
        self.assertIn("first_taste", dev.s["milestones"]); self.assertIsNone(lab.commit("структура", b, dev))
    def test_no_verdict_below_threshold(self):
        lab = per_taste.TasteLab(os.path.join(td(), "t.json"))
        for i in range(10): lab.trial("m", "a", "b", "a" if i % 2 else "b")
        self.assertIsNone(lab.verdict("m"))
        with self.assertRaises(ValueError): lab.trial("m", "a", "b", "c")

class TMe(unittest.TestCase):
    def test_payload_rollback_and_router(self):
        c, d = Clk(), td(); j = lambda n: os.path.join(d, n)
        p, dev, b = Personality(path=j("personality.json"), clock=c, rng=random.Random(3)), Development(path=j("development.json"), clock=c), Beliefs(path=j("beliefs.json"), clock=c)
        snap = dict(p.axes); p.snapshot("до")
        for _ in range(30): p.observe("warmth", 1.0, "похвалы")
        c.t += 3600; p.consolidate(); self.assertNotEqual(p.axes, snap)
        m = per_me.me_payload(p, dev, b); self.assertIn("до", m["snapshots"]); self.assertTrue(m["why_changed"]); self.assertEqual(m["phase"], "рождение")
        self.assertFalse(per_me.rollback_me(p, "до", "ок")["ok"]); self.assertFalse(per_me.rollback_me(p, "нет", per_me.SIGN_PHRASE)["ok"])
        p.save()
        try: from fastapi import FastAPI; from fastapi.testclient import TestClient
        except ImportError: self.skipTest("нет fastapi")
        app = FastAPI(); app.include_router(per_me.make_router(d)); cl = TestClient(app)
        os.environ.pop("NOX_OWNER_TOKEN", None); self.assertEqual(cl.get("/me").status_code, 403)       # без токена в окружении - всем отказ
        os.environ["NOX_OWNER_TOKEN"] = "secret"
        self.assertEqual(cl.get("/me", headers={"Authorization": "Bearer wrong"}).status_code, 403)
        h = {"Authorization": "Bearer secret"}; self.assertEqual(cl.get("/me", headers=h).status_code, 200)
        self.assertFalse(cl.post("/me/rollback", json={"label": "до"}, headers=h).json()["ok"])
        r = cl.post("/me/rollback", json={"label": "до", "signature": per_me.SIGN_PHRASE}, headers=h).json(); self.assertTrue(r["ok"])
        self.assertEqual(Personality(path=j("personality.json")).axes, snap)                              # оси равны снапшоту
        self.assertTrue(any("rollback" == x["kind"] for x in Personality(path=j("personality.json")).journal))
        os.environ.pop("NOX_OWNER_TOKEN", None)

if __name__ == "__main__": unittest.main()
