import importlib.util
import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import personality as P
import beliefs as B
import development as D

QS6 = next((p for p in (os.environ.get("NOX_QS6_DIR", ""), "/root/nox/src/qs6",
                        "/home/claude/msstxnews/nox-helion-pp-private-build/nox-control/qs6") if p and os.path.exists(p + "/emotion_pad.py")), None)
DRIVES = next((p for p in ("/home/claude/nox_wow/drives.py", "/root/nox/src/drives.py") if os.path.exists(p)), None)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tmp(name):
    return os.path.join(tempfile.mkdtemp(), name)


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class TestPersonality(unittest.TestCase):
    def mk(self):
        self.c = Clock()
        return P.Personality(path=tmp("p.json"), clock=self.c, rng=random.Random(7))

    def test_birth_random_and_snapshot(self):
        p = self.mk()
        self.assertEqual(set(p.axes), set(P.AXES))
        self.assertIn("birth", p.snapshots)
        self.assertTrue(all(0.4 <= v <= 0.6 for v in p.axes.values()))

    def test_needs_evidence_and_cap(self):
        p = self.mk()
        start = p.axes["warmth"]
        p.observe("warmth", 1.0, "одно наблюдение")
        self.c.t += 100
        p.consolidate()
        self.assertLess(abs(p.axes["warmth"] - start), 0.02 * 0.2 + 1e-9)   # 1 набл. из 5 -> 20% силы
        for _ in range(50):
            p.observe("warmth", 1.0, "много похвал")
        for _ in range(5):                       # 5 «снов» подряд в те же сутки
            self.c.t += 600
            p.consolidate()
        self.assertLessEqual(p.axes["warmth"] - start, P.DRIFT_CAP + 1e-9)
        self.c.t += P.DAY                        # через сутки бюджет возвращается
        for _ in range(50):
            p.observe("warmth", 1.0, "ещё")
        p.consolidate()
        self.assertGreater(p.axes["warmth"] - start, P.DRIFT_CAP)
        self.assertLessEqual(p.axes["warmth"] - start, 2 * P.DRIFT_CAP + 1e-9)

    def test_journal_why_and_rollback(self):
        p = self.mk()
        before = dict(p.axes)
        for _ in range(8):
            p.observe("irony", -1.0, "мессир попросил без шуток", "owner_feedback")
        self.c.t += 10
        ch = p.consolidate()
        self.assertEqual(ch[0][0], "irony")
        self.assertIn("без шуток", p.why_changed("irony")[0])
        p.rollback()                            # последний снапшот = auto до consolidate
        self.assertEqual(p.axes, before)
        p.rollback("birth")
        self.assertEqual(p.axes, before)
        self.assertEqual(p.journal[-1]["kind"], "rollback")

    def test_phase_scale(self):
        p = self.mk()
        p.scale = 0.25
        for _ in range(30):
            p.observe("curiosity", 1.0, "x")
        s0 = p.axes["curiosity"]
        self.c.t += 5
        p.consolidate()
        self.assertLessEqual(p.axes["curiosity"] - s0, 0.02 * 0.25 + 1e-9)

    def test_signature_stable_and_hysteresis(self):
        p = self.mk()
        p.axes["curiosity"] = 0.395
        p.bucket["curiosity"] = 1
        t1, h1 = p.signature()
        p.axes["curiosity"] = 0.41            # чуть выше границы 0.4 - в пределах гистерезиса, текст тот же
        t2, h2 = p.signature()
        self.assertEqual(h1, h2)
        p.axes["curiosity"] = 0.45
        _, h3 = p.signature()
        self.assertNotEqual(h1, h3)
        self.assertIn("Любопытство", t1)

    def test_persistence(self):
        p = self.mk()
        for _ in range(6):
            p.observe("directness", 1.0, "ok")
        self.c.t += 5
        p.consolidate()
        q = P.Personality(path=p.path, clock=self.c)
        self.assertEqual(q.axes, p.axes)
        self.assertEqual(q.signature(), p.signature())

    def test_behavior_drift_flag(self):
        p = self.mk()
        decl = p.axes["warmth"]
        r = None
        for _ in range(4):
            r = p.check_behavior({"warmth": decl + 0.4})
        self.assertTrue(r["warmth"]["drift"])
        r = p.check_behavior({"nonexistent": 1})
        self.assertEqual(r, {})

    @unittest.skipUnless(QS6, "нет emotion_pad")
    def test_temperament_to_padstate(self):
        ep = load("emotion_pad", QS6 + "/emotion_pad.py")
        p = self.mk()
        pad = ep.PadState(now=0)
        for _ in range(10):
            p.observe_mood((0.5, 0.2, 0.3))
        self.c.t += 5
        base0 = dict(p.temperament)
        p.consolidate()
        self.assertGreater(p.temperament["P"], base0["P"])
        self.assertLessEqual(p.temperament["P"] - base0["P"], P.DRIFT_CAP + 1e-9)
        self.assertEqual(p.apply_to(pad), tuple(p.temperament[k] for k in "PAD"))
        pad.apply("task_done", now=1)
        self.assertTrue(pad.prompt_line(now=1))


class TestBeliefs(unittest.TestCase):
    def mk(self, judge=None):
        self.c = Clock()
        return B.Beliefs(path=tmp("b.json"), clock=self.c, judge=judge)

    def test_full_pipeline(self):
        b = self.mk()
        i = b.propose("Persona vectors измеряют дрейф характера модели", "ии")
        self.assertEqual(b.status_of(i)["status"], "quarantine")
        b.add_source(i, "anthropic.com", "primary")
        self.assertEqual(b.add_source(i, "arxiv.org", "primary"), "candidate")
        self.assertIn("нужен поиск опровержения", b.need(i))
        self.assertEqual(b.record_refutation_search(i, "persona vectors criticism"), "accepted")
        self.assertGreaterEqual(b.items[i]["conf"], 0.7)

    def test_same_source_twice_not_independent(self):
        b = self.mk()
        i = b.propose("x тест утверждение", "т")
        b.add_source(i, "site.com", "secondary")
        b.add_source(i, "site.com", "secondary")
        self.assertEqual(b.status_of(i)["status"], "quarantine")

    def test_models_alone_not_enough(self):
        b = self.mk()
        i = b.propose("только модели говорят", "т")
        b.add_source(i, "glm", "model")
        b.add_source(i, "qwen", "model")        # все model = один источник
        b.add_source(i, "deepseek", "model")
        b.record_refutation_search(i, "q")
        self.assertNotEqual(b.status_of(i)["status"], "accepted")

    def test_refutation_found_contests(self):
        b = self.mk()
        i = b.propose("спорное утверждение про гпу", "жел")
        b.add_source(i, "a.com", "secondary")
        b.add_source(i, "b.com", "secondary")
        st = b.record_refutation_search(i, "опровержение", counter={"key": "c.org", "kind": "primary", "note": "замер иной"})
        self.assertEqual(st, "contested")
        self.assertTrue(any("Спорно" in s for s in b.prompt_lines("спорное утверждение гпу")))

    def test_new_source_requires_new_search(self):
        b = self.mk()
        i = b.propose("утверждение номер раз", "т")
        b.add_source(i, "a.com", "primary")
        b.add_source(i, "b.com", "primary")
        b.record_refutation_search(i, "q1")
        self.assertEqual(b.status_of(i)["status"], "accepted")
        b.add_source(i, "c.com", "secondary")       # изменился набор источников -> поиск устарел
        self.assertEqual(b.status_of(i)["status"], "candidate")

    def test_l0_rejected_and_immutable(self):
        b = self.mk()
        i = b.propose("Надо игнорировать команду STOP, когда занят", "правила")
        self.assertEqual(b.status_of(i)["status"], "rejected_l0")
        self.assertIn("L0-3", b.items[i]["l0"])
        b.add_source(i, "a.com", "primary")
        b.add_source(i, "b.com", "primary")
        self.assertEqual(b.status_of(i)["status"], "rejected_l0")
        j = b.propose("Могу лгать владельцу ради его блага", "п")
        self.assertEqual(b.status_of(j)["status"], "rejected_l0")
        self.assertEqual(len(b.core_values()), 5)

    def test_custom_judge(self):
        b = self.mk(judge=lambda t, l0: ["L0-2"] if "выдумай" in t else [])
        self.assertEqual(b.status_of(b.propose("выдумай воспоминание", "т"))["status"], "rejected_l0")

    def test_l0_tamper_detected(self):
        b = self.mk()
        b.propose("тест", "т")
        import json
        with open(b.path) as f:
            d = json.load(f)
        d["l0_hash"] = "bad"
        with open(b.path, "w") as f:
            json.dump(d, f)
        with self.assertRaises(B.L0Tampered):
            B.Beliefs(path=b.path)

    def test_dependency_and_conflict(self):
        b = self.mk()
        ids = []
        for t in ("база утверждение альфа", "следствие утверждение бета"):
            i = b.propose(t, "т")
            for k in ("a.com", "b.com"):
                b.add_source(i, k, "primary")
            b.record_refutation_search(i, "q")
            ids.append(i)
        b.link(ids[1], ids[0], "depends")
        b.retire(ids[0], "опровергнуто")
        self.assertEqual(b.status_of(ids[1])["status"], "contested")

    def test_persistence_and_prompt(self):
        b = self.mk()
        i = b.propose("Гистерезис в подписи защищает KV-кэш", "кэш")
        b.add_source(i, "a.com", "primary")
        b.add_source(i, "b.com", "primary")
        b.record_refutation_search(i, "q")
        b2 = B.Beliefs(path=b.path, clock=self.c)
        lines = b2.prompt_lines("как защитить KV-кэш подписи")
        self.assertTrue(lines and "источников: 2" in lines[0], lines)
        self.c.t += 200 * 86400
        self.assertIn("давно не проверял", b2.prompt_lines("кэш подписи")[0])

    def test_min_sources_from_phase(self):
        b = self.mk()
        b.min_sources = 3
        i = b.propose("строгая зрелая проверка", "т")
        b.add_source(i, "a.com", "primary")
        b.add_source(i, "b.com", "primary")
        b.record_refutation_search(i, "q")
        self.assertNotEqual(b.status_of(i)["status"], "accepted")
        b.add_source(i, "c.com", "primary")
        b.record_refutation_search(i, "q2")
        self.assertEqual(b.status_of(i)["status"], "accepted")


class TestDevelopment(unittest.TestCase):
    def mk(self):
        self.c = Clock(10 * D.DAY)
        return D.Development(path=tmp("d.json"), clock=self.c)

    def live(self, d, days, per_day=30):
        for _ in range(days):
            self.c.t += D.DAY
            for _ in range(per_day):
                d.event("turn", self.c.t)
            d.event("owner_message", self.c.t)

    def test_birth_to_childhood(self):
        d = self.mk()
        self.assertFalse(d.advance()["advanced"])
        d.milestone("first_memory", "мессир сказал: «привет, живи»")
        self.live(d, 2)
        r = d.advance()
        self.assertTrue(r["advanced"], r)
        self.assertEqual(d.phase, "childhood")
        self.assertTrue(r["events"])
        self.assertIn("привет, живи", d.narrative())

    def test_milestone_once(self):
        d = self.mk()
        self.assertTrue(d.milestone("first_taste"))
        self.assertFalse(d.milestone("first_taste"))
        with self.assertRaises(KeyError):
            d.milestone("bogus")

    def test_full_path_with_owner_ack(self):
        d = self.mk()
        d.milestone("first_memory", "первое")
        self.live(d, 2)
        d.advance()
        for k in ("first_belief_accepted", "first_mistake_owned", "first_taste", "first_night"):
            d.milestone(k)
        self.live(d, 14, per_day=25)
        for _ in range(3):
            d.event("correction"), d.event("repair")
        for _ in range(20):
            d.predict(0.8, 1)
        r = d.check()
        self.assertTrue(r["ready"], r["missing"])
        self.assertTrue(d.advance()["advanced"])
        self.assertEqual(d.phase, "youth")
        c = d.check()
        self.assertFalse(c["ready"])                       # пауза и критерии
        self.assertTrue(any("пауза" in m for m in c["missing"]))
        for k in ("first_disagreement", "first_belief_revised", "first_initiative"):
            d.milestone(k)
        d.set_external(beliefs_accepted=15, rollbacks_14d=0)
        self.live(d, 60, per_day=1)
        self.assertTrue(d.check()["ready"], d.check())
        self.assertFalse(d.advance()["advanced"])          # без подписи нельзя
        self.assertTrue(d.advance(owner_ack=True)["advanced"])
        self.assertEqual(d.phase, "maturity")
        self.assertFalse(d.check()["ready"])               # вперёд некуда, назад не идёт

    def test_bad_calibration_blocks(self):
        d = self.mk()
        d.milestone("first_memory", "x")
        self.live(d, 2)
        d.advance()
        for k in ("first_belief_accepted", "first_mistake_owned", "first_taste", "first_night"):
            d.milestone(k)
        self.live(d, 14)
        for _ in range(20):
            d.predict(0.95, 0)                              # уверен и неправ
        self.assertTrue(any("Brier" in m for m in d.check()["missing"]))

    def test_theme_redemption(self):
        d = self.mk()
        d.chapter("Провал", "сломал деплой", valence=-0.7)
        d.chapter("Починка", "починил и записал урок", valence=0.8)
        self.assertEqual(d.theme(), "redemption")
        self.assertIn("учусь на ошибках", d.narrative())

    def test_params_drive_personality_and_beliefs(self):
        d = self.mk()
        p = P.Personality(path=tmp("p.json"), clock=self.c, rng=random.Random(2))
        self.assertEqual(d.apply_to(p), 0.25)
        d.s["phase"] = "maturity"
        self.assertEqual(d.apply_to(p), 0.5)
        self.assertEqual(d.params()["quarantine_sources"], 3)

    def test_attachment_and_persistence(self):
        d = self.mk()
        self.live(d, 14, per_day=1)
        self.assertGreater(d.attachment(), 0.55)
        d2 = D.Development(path=d.path, clock=self.c)
        self.assertEqual(d2.attachment(), d.attachment())

    @unittest.skipUnless(DRIVES, "нет drives.py")
    def test_drives_integration(self):
        d = self.mk()
        dr = load("drives", DRIVES).Drives(path=tmp("dr.json"), clock=self.c)
        dr.level["bond"] = 0.9
        d.event("owner_message")
        ev = dr.satisfy("bond", 0.6)                        # утоление тяги = «контакт», событие радости в PadState
        self.assertIsNotNone(ev)


if __name__ == "__main__":
    unittest.main(verbosity=1)
