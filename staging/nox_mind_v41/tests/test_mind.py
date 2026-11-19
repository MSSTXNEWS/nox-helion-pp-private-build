import unittest, sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nox_mind_v41.warm_cache import ScopedFTS, WarmS03Cache
from nox_mind_v41.graph_memory import GraphMemory
from nox_mind_v41.bitemporal import BiTemporalStore
from nox_mind_v41.decision_context import DecisionContext
from nox_mind_v41.persona import Persona, EmotionState, validate_reply, ConsistencyChecker
from nox_mind_v41 import reflection as R
from nox_mind_v41.control import PRESETS, request_body, Hysteresis
from nox_mind_v41.idle_consolidate import run as idle_run

class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t

class TestWarm(unittest.TestCase):
    def test_scope_cache_invalidate(self):
        f = ScopedFTS(); c = WarmS03Cache(f, ttl_s=100, clock=Clock())
        f.add("1", "P1", "persona", "любит чёрный кофе"); f.add("2", "P2", "persona", "любит зелёный чай кофе")
        f.add("3", "P1", "global", "кофе общая заметка")
        r = c.recall("кофе", "P1"); self.assertEqual({x["id"] for x in r}, {"1", "3"})  # no P2 leak
        c.recall("кофе", "P1"); self.assertEqual(c.hits, 1)
        c.write("4", "P1", "persona", "перешёл на кофе без сахара")
        r = c.recall("кофе", "P1"); self.assertIn("4", {x["id"] for x in r}); self.assertEqual(c.misses, 2)
    def test_ttl(self):
        clk = Clock(); f = ScopedFTS(); c = WarmS03Cache(f, ttl_s=10, clock=clk); f.add("1", "P", "persona", "альфа")
        c.recall("альфа", "P"); clk.t += 11; c.recall("альфа", "P"); self.assertEqual(c.misses, 2)

class TestGraph(unittest.TestCase):
    def test_types_edges_affect_consolidate_checkpoint(self):
        clk = Clock(); g = GraphMemory(clock=clk)
        a = g.write("P", "поссорился с братом из-за машины", valence=-0.8, arousal=0.7); clk.t += 1
        b = g.write("P", "брат вернул машину, помирились", valence=0.6, arousal=0.3); clk.t += 1
        g.write("P", "машина снова сломалась", valence=-0.4, arousal=0.4); clk.t += 1
        sad = g.recall("P", "машина брат", mood=(-0.8, 0.7)); self.assertEqual(sad[0]["id"], a)
        res = g.consolidate("P"); self.assertGreaterEqual(res["facts"], 1)
        self.assertTrue(any(r["type"] == "semantic" for r in g.recall("P", "машина", types=("semantic",))))
        self.assertEqual(g.consolidate("P")["episodes"], 0)
        for i in range(10): clk.t += 1; g.write("P", f"w{i}", mtype="working")
        self.assertEqual(g.db.execute("SELECT COUNT(*) FROM node WHERE mtype='working'").fetchone()[0], 7)
        g.checkpoint("task1", 3, {"x": 1}); self.assertEqual(g.resume("task1")["step"], 3)

class TestBiTemporal(unittest.TestCase):
    def test_supersession_asof(self):
        clk = Clock(100); s = BiTemporalStore(clock=clk)
        f1 = s.assert_fact("P", "owner", "city", "Москва", valid_at=50); clk.t = 200
        f2 = s.assert_fact("P", "owner", "city", "Казань", valid_at=180)
        cur = s.current("P", "owner", "city"); self.assertEqual([c["object"] for c in cur], ["Казань"])
        self.assertEqual(len(s.history("P", "owner", "city")), 2)  # nothing deleted
        self.assertEqual([r["object"] for r in s.as_of("P", "owner", "city", world_t=100)], ["Москва"])
        self.assertEqual([r["object"] for r in s.as_of("P", "owner", "city", world_t=190, known_t=150)], ["Москва"])
        old = [h for h in s.history("P", "owner", "city") if h["id"] == f1][0]
        self.assertEqual(old["invalid_at"], 180); self.assertEqual(old["expired_at"], 200)
        self.assertEqual(s.db.execute("SELECT new_id FROM supersession WHERE old_id=?", (f1,)).fetchone()[0], f2)
        self.assertEqual(s.assert_fact("P", "owner", "city", "Казань"), f2)  # idempotent
    def test_ucb(self):
        s = BiTemporalStore(clock=Clock()); a = s.assert_fact("P", "x", "p", "1", functional=False); b = s.assert_fact("P", "y", "p", "2", functional=False)
        for _ in range(5): s.feedback(a, 1.0)
        self.assertEqual(s.rank("P", c=0.0)[0]["id"], a)

class TestDecision(unittest.TestCase):
    def test_correction_learning(self):
        clk = Clock(); dc = DecisionContext(BiTemporalStore(clock=clk))
        dc.learn_correction("P", "отчёт для владельца по серверу", "длинный английский отчёт", "короткий отчёт на русском"); clk.t += 1
        self.assertIn("короткий отчёт на русском", dc.prompt_block("P", "сделай отчёт по серверу"))
        dc.learn_correction("P", "отчёт для владельца по серверу", "короткий отчёт на русском", "таблица + 3 строки")
        blk = dc.prompt_block("P", "отчёт сервер"); self.assertIn("таблица", blk); self.assertNotIn("ДА: короткий", blk)
        self.assertEqual(dc.prompt_block("P", "погода"), "")

class TestPersona(unittest.TestCase):
    def test_persona_emotion(self):
        p = Persona("C01", "NOX", {"тепло": 0.8}, {"язык": "ru"}, ["не выдаёт себя за человека"])
        es = EmotionState().update("sadness").update("sadness"); self.assertLess(es.v, -0.3)
        self.assertIn("C01", p.system_block(es))
        self.assertTrue(validate_reply("Давай разберёмся.", "sadness").startswith("Понимаю"))
        self.assertEqual(validate_reply("Ок.", "neutral"), "Ок.")
        cc = ConsistencyChecker(p, {"human_claim": r"я (живой )?человек"})
        self.assertFalse(cc.check("Я человек, честно")["ok"])
        p2 = Persona("C01", "NOX", {"тепло": 0.1}, {"язык": "ru"}, ["не выдаёт себя за человека"])
        self.assertIn("persona_card_drift", cc.check("ок", p2)["issues"])

class TestReflection(unittest.TestCase):
    def test_loops(self):
        calls = iter(["черновик", "ошибка в шаге 2", "исправлено", "OK"])
        self.assertEqual(R.self_refine(lambda p: next(calls), "t")["answer"], "исправлено")
        seq = iter(["плохо", "урок: проверяй единицы", "хорошо"])
        rx = R.Reflexion(lambda p: next(seq), lambda a: (a == "хорошо", "нет")).run("t"); self.assertEqual(rx["trials"], 2)
        sc = R.self_consistency(iter(["a\n42", "b\n42", "c\n41"]).__next__ and (lambda it: (lambda p: next(it)))(iter(["a\n42", "b\n42", "c\n41"])), "q", n=3)
        self.assertEqual(sc["answer"], "42")
        steps = iter(["Мысль: нужно посчитать\nДействие: calc[2+2]", "Ответ: 4"])
        self.assertEqual(R.react(lambda p: next(steps), "2+2?", {"calc": lambda x: str(eval(x))})["answer"], "4")
        cps = []; pe = R.plan_then_execute(lambda p: "calc(1+1)\nсделать вывод" if "план" in p else "вывод", "g", {"calc": lambda x: str(eval(x))}, checkpoint=lambda i, s: cps.append(i))
        self.assertEqual(pe["results"][0]["out"], "2"); self.assertEqual(cps, [0, 1])
        m = R.CoTMonitor(max_tokens=100, loop_window=3)
        self.assertEqual([m.feed(t) for t in "ab"][-1], "CONTINUE")
        m2 = R.CoTMonitor(loop_window=2); r = [m2.feed(t) for t in "xyxy"]; self.assertEqual(r[-1], "INTERRUPT:loop")
        self.assertTrue(R.system2_needed("почему падает сервер?")); self.assertFalse(R.system2_needed("привет"))
        self.assertEqual(R.budget_to_effort(0), {"reasoning": "off"}); self.assertEqual(R.budget_to_effort(2048)["reasoning_effort"], "50")

class TestControl(unittest.TestCase):
    def test_presets_hysteresis(self):
        b = request_body("coding", [{"role": "user", "content": "x"}]); self.assertEqual(b["reasoning_effort"], "75")
        self.assertIn("chat_template_kwargs", request_body("chat_fast", []))
        clk = Clock(); h = Hysteresis(hi=0.6, lo=0.2, alpha=0.5, min_dwell_s=10, clock=clk)
        for _ in range(3): clk.t += 1; st = h.observe("e1", True)
        self.assertEqual(st, "hot"); clk.t += 1; self.assertEqual(h.observe("e1", False), "hot")  # dwell holds
        for _ in range(5): clk.t += 5; st = h.observe("e1", False)
        self.assertEqual(st, "cold")

class TestIdle(unittest.TestCase):
    def test_idle_job(self):
        d = tempfile.mkdtemp(); db = os.path.join(d, "m.db"); g = GraphMemory(db)
        g.write("P", "кофе утром"); g.write("P", "кофе вечером")
        self.assertEqual(idle_run(db, "P", last_activity_ts=0, now=60)["status"], "SKIP_NOT_IDLE")
        self.assertEqual(idle_run(db, "P", last_activity_ts=0, now=4000)["pending_episodes"], 2)
        r = idle_run(db, "P", last_activity_ts=0, now=4000, dry_run=False)
        self.assertEqual(r["status"], "DONE"); self.assertGreaterEqual(r["facts"], 1)

if __name__ == "__main__":
    unittest.main()
