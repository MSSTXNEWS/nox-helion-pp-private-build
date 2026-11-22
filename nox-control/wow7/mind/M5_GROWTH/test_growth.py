import json
import os
import random
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import growth as G

ANCH = os.path.join(HERE, "anchors_seed.jsonl")
T0 = 1_700_000_000 - (1_700_000_000 + 3 * 3600) % 86400 + 12 * 3600      # 12:00 МСК (не тихие часы)
NIGHT = T0 + 12 * 3600                                                 # 00:00 МСК (тихие часы)
DAY = 86400


class FakeSolver:
    """Фейк модели с «уровнем умения»: решает задачи уровня <= skill, на уровне skill+1 - только с подсказкой."""
    def __init__(self, skill=1, anchors=ANCH):
        self.skill = skill
        self.by_prompt = {t["prompt"]: t for t in G.jl(anchors)}
        self.calls = 0
        self.log = []

    def __call__(self, prompt):
        self.calls += 1
        base = prompt.split("\n\nПодсказка:")[0]
        t = self.by_prompt.get(base)
        if t is None:
            return "не знаю"
        hinted = "Подсказка:" in prompt
        self.log.append((t["level"], hinted))
        if t["level"] <= self.skill or (hinted and t["level"] == self.skill + 1):
            return t["reference"]
        return "не знаю"


class Drv:
    def __init__(self):
        self.errs, self.sat, self.level = [], [], {"knowledge": 0.5}

    def observe(self, topic, err):
        self.errs.append((topic, err))

    def satisfy(self, name, amount):
        self.sat.append((name, amount))


def mk(td, solver=None, **kw):
    kw.setdefault("rng", random.Random(7))
    return G.Growth(td, solver or FakeSolver(), anchors_path=ANCH, **kw)


class Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)


class Verify(Base):
    def test_kinds(self):
        c = G.check_answer
        self.assertEqual(c({"kind": "number", "value": 391}, "17*23 = 391")[0], 1.0)
        self.assertEqual(c({"kind": "number", "value": 391}, "около 390")[0], 0.0)
        self.assertEqual(c({"kind": "number", "value": 1, "tol": 0.01}, "1,005")[0], 1.0)
        self.assertEqual(c({"kind": "contains_all", "items": ["23", "08"]}, "с 23:00 до 08:00")[0], 1.0)
        self.assertEqual(c({"kind": "contains_all", "items": ["23", "08"]}, "с 23:00")[0], 0.5)
        self.assertEqual(c({"kind": "regex", "pattern": "^\\W*нет\\W*$"}, " Нет. ")[0], 1.0)

    def test_python_tests(self):
        t = "assert f(2) == 4"
        self.assertEqual(G.run_python_tests("```python\ndef f(x):\n    return x*2\n```", t), 1.0)
        self.assertEqual(G.run_python_tests("def f(x):\n    return x+1", t), 0.0)
        self.assertEqual(G.run_python_tests("import os\ndef f(x):\n    return 4", t), 0.0)           # denylist
        self.assertEqual(G.run_python_tests("def f(x):\n    while True: pass", t, timeout=1.0), 0.0)    # таймаут
        self.assertEqual(G.run_python_tests("", t), 0.0)

    def test_judge_needs_judge_and_is_weak(self):
        with self.assertRaises(G.Unscorable):
            G.check_answer({"kind": "judge", "criteria": "x"}, "a")
        s, how = G.check_answer({"kind": "judge", "criteria": "x"}, "a", judge=lambda p, a, c: 0.8)
        self.assertEqual((s, how), (0.8, "judge"))
        j = G.make_judge(lambda q: 'мысли {"score": 0.7} конец')
        self.assertEqual(j("p", "a", "c"), 0.7)
        self.assertIsNone(G.make_judge(lambda q: "не json")("p", "a", "c"))

    def test_all_seed_anchors_valid(self):
        seen = []
        for t in G.jl(ANCH):
            t["id"] = "x"
            ok, why = G.validate_task(t)
            self.assertTrue(ok, "%s: %s" % (t["prompt"][:40], why))


class Validate(Base):
    def base(self, **kw):
        t = {"area": "тест", "level": 2, "prompt": "Сколько будет шесть умножить на семь? Ответь числом.",
             "check": {"kind": "number", "value": 42}, "reference": "42", "hints": []}
        t.update(kw)
        return t

    def test_ok_and_rejections(self):
        self.assertTrue(G.validate_task(self.base())[0])
        self.assertFalse(G.validate_task(self.base(reference="41"))[0])                       # эталон не проходит
        self.assertFalse(G.validate_task(self.base(level=9))[0])
        self.assertFalse(G.validate_task(self.base(hints=["a", "b", "c"]))[0])
        self.assertFalse(G.validate_task(self.base(check={"kind": "bogus"}))[0])
        self.assertFalse(G.validate_task(self.base(check={"kind": "judge", "criteria": "ok"}), allow_judge=False)[0])

    def test_anti_hacking(self):
        # ключ в условии: проверка тривиальна
        t = self.base(prompt="Назови слово «картофель» в ответе, пожалуйста.", check={"kind": "contains_all", "items": ["картофель"]}, reference="картофель")
        self.assertEqual(G.validate_task(t), (False, "ключ проверки содержится в условии"))
        # regex, принимающий пустой ответ
        t = self.base(check={"kind": "regex", "pattern": ".*"}, reference="что угодно")
        self.assertFalse(G.validate_task(t)[0])
        # regex, принимающий эхо условия
        t = self.base(check={"kind": "regex", "pattern": "число"}, reference="число")
        self.assertIn("эхо", G.validate_task(t)[1])
        # тесты без assert
        t = self.base(check={"kind": "python_tests", "tests": "print(1)"}, reference="def f(): pass")
        self.assertFalse(G.validate_task(t)[0])

    def test_duplicate_and_exam_leak(self):
        t = self.base()
        st = sorted(G.stems(t["prompt"]))
        self.assertEqual(G.validate_task(t, seen=[st]), (False, "дубль"))
        self.assertIn("экзамен", G.validate_task(t, exam_stems=[st])[1])


class Maths(Base):
    def test_learning_progress(self):
        rising = [(0.0, 1)] * 5 + [(1.0, 1)] * 5
        flat = [(0.6, 1)] * 10
        noisy = [(s, 1) for s in (0, 1, 0, 1, 1, 0, 1, 0, 0, 1)]
        falling = [(1.0, 1)] * 5 + [(0.0, 1)] * 5
        self.assertGreater(G.learning_progress(rising), 0.9)
        self.assertEqual(G.learning_progress(flat), 0.0)
        self.assertLess(G.learning_progress(noisy), 0.2)             # шум без тренда не интересен
        self.assertGreater(G.learning_progress(falling), 0.9)        # забывание тоже замечается (абсолютный LP)
        self.assertEqual(G.learning_progress([(1, 1)] * 3), 0.0)     # мало данных

    def test_zpd_and_prior(self):
        self.assertAlmostEqual(G.zpd_fit(0.6), 1.0)
        self.assertEqual(G.zpd_fit(1.0), 0.0)
        self.assertEqual(G.zpd_fit(0.1), 0.0)
        self.assertGreater(G.prior_p(1), G.prior_p(5))

    def test_forgetting_curve_and_srs(self):
        self.assertAlmostEqual(G.retrievability(3, 3), 0.9)
        self.assertAlmostEqual(G.interval_days(3), 3.0)
        self.assertGreater(G.retrievability(1, 5), G.retrievability(10, 5))

        def item():
            return {"S": 2.0, "D": 5.0, "reps": 1, "lapses": 0, "last": 0, "due": 0}
        early, late, bad = item(), item(), item()
        G.srs_update(early, True, 0.5 * 2 * DAY)       # повтор рано (R высокая)
        G.srs_update(late, True, 8 * 2 * DAY)          # повтор поздно (R низкая) -> желательная трудность -> больше прирост
        G.srs_update(bad, False, 2 * DAY)
        self.assertGreater(late["S"], early["S"])
        self.assertGreater(early["S"], 2.0)
        self.assertLess(bad["S"], 2.0)
        self.assertEqual(bad["lapses"], 1)
        self.assertGreater(bad["D"], 5.0)

    def test_ols(self):
        b, t = G.ols([0, 1, 2, 3, 4], [0.1, 0.2, 0.3, 0.4, 0.5])
        self.assertAlmostEqual(b, 0.1)
        b, t = G.ols([0, 1, 2, 3, 4, 5], [0.5, 0.52, 0.48, 0.5, 0.51, 0.49])
        self.assertLess(abs(t), 2)


class Curriculum(Base):
    def test_new_area_starts_at_frontier_not_extremes(self):
        g = mk(self.td)
        top = g.rank()[0]
        self.assertIn(top["level"], (1, 2))
        self.assertTrue(all(c["level"] <= 2 for c in g.rank()))                  # ЗБР: дальше освоенного+2 не ходим

    def test_zpd_moves_up_with_skill_and_never_skips(self):
        s = FakeSolver(skill=3)
        g = mk(self.td, s, eps=0.05)
        for i in range(14):                                                        # якорей мало: повтор только после паузы (3 суток)
            g.session(max_tasks=5, now=T0 + i * 3 * DAY)
        for area in g.st["areas"]:
            self.assertLessEqual(g.mastered_level(area), 3, area)               # выше умения не «освоено»
        self.assertTrue(any(g.mastered_level(a) >= 2 for a in g.st["areas"]))
        levels = [l for l, _ in s.log]
        self.assertGreaterEqual(sum(1 for l in levels if l <= 4) / len(levels), 0.99)
        self.assertGreater(sum(1 for l in levels if l >= 3), 0)                  # дошёл до границы умения

    def test_lp_focus_prefers_area_with_progress(self):
        g = mk(self.td)
        a = g._area("арифметика")
        b = g._area("python")
        for i in range(10):                                                        # арифметика: ровно хорошо (насыщена)
            a["ev"].append({"t": T0 + i, "l": 2, "s": 1.0, "w": 0.7, "a": 0, "src": "rule", "id": "a%d" % i})
        for i in range(10):                                                        # python: растёт 0 -> 1 на уровне 2
            b["ev"].append({"t": T0 + i, "l": 2, "s": 0.0 if i < 5 else 1.0, "w": 0.7, "a": 0, "src": "rule", "id": "b%d" % i})
        self.assertGreater(g.lp_cell("python", 2), g.lp_cell("арифметика", 2))
        cells = {(c["area"], c["level"]): c for c in g.rank()}
        self.assertGreater(cells[("python", 2)]["score"], cells[("арифметика", 2)]["score"])

    def test_scaffold_assisted_credit_and_scar(self):
        s = FakeSolver(skill=1)
        g = mk(self.td, s)
        task = next(t for t in g.anchors if t["level"] == 2 and t["hints"] and t["area"] == "арифметика")
        o = g.run_task(dict(task, src="anchor"), T0)
        self.assertTrue(o["assisted"])
        self.assertFalse(o["independent"])
        self.assertEqual(o["score"], 0.5)
        self.assertTrue(o["scar"])                                                  # помощью решил -> ещё не моё -> шрам
        self.assertIn(task["id"], g.st["srs"])
        self.assertEqual(g.st["srs"][task["id"]]["kind"], "scar")

    def test_busy_stops_without_penalty_and_errors_do_not_poison(self):
        class Deferred(Exception):
            pass
        calls = {"n": 0}

        def busy(p):
            calls["n"] += 1
            raise Deferred("чат занят")
        g = mk(self.td, busy)
        r = g.session(max_tasks=4, now=T0)
        self.assertEqual(r["stopped"], "busy")
        self.assertEqual(r["n"], 0)
        self.assertEqual(calls["n"], 1)
        self.assertTrue(all(not A["ev"] for A in g.st["areas"].values()))

        def boom(p):
            raise RuntimeError("модель упала")
        g2 = mk(tempfile.mkdtemp(), boom)
        r = g2.session(max_tasks=5, now=T0)
        self.assertEqual(r["stopped"], "errors")
        self.assertTrue(all(not A["ev"] for A in g2.st["areas"].values()))

    def test_unscorable_judge_task_is_skipped(self):
        g = mk(self.td)
        t = {"id": "j1", "area": "взгляды", "level": 2, "prompt": "Объясни своими словами, что такое калибровка уверенности.",
             "check": {"kind": "judge", "criteria": "верно и по существу"}, "src": "gen"}
        with self.assertRaises(G.Unscorable):
            g.run_task(t, T0)
        self.assertEqual(g._area("взгляды")["ev"], [])

    def test_day_cap_and_hunger_budget(self):
        d = Drv()
        d.level["knowledge"] = 0.0
        g = mk(self.td, hooks=G.Hooks(G.DrivesHooks(d)), day_cap=3)
        r = g.session(now=T0)
        self.assertEqual(r["budget"], 1)                                            # сыт -> 1 задача
        d.level["knowledge"] = 1.0
        r = g.session(now=T0 + 10)
        self.assertEqual(r["budget"], 2)                                            # голоден, но потолок суток: 3-1
        g.session(now=T0 + 20)
        self.assertEqual(g.session(now=T0 + 30)["skipped"], "day_cap")


class Generator(Base):
    def llm_ok(self, q):
        return json.dumps({"prompt": "Сколько будет 12 умножить на 12? Ответь числом.", "check": {"kind": "number", "value": 144}, "reference": "144", "hints": ["12*10+12*2"]})

    def test_generated_task_used_when_no_anchor(self):
        g = mk(self.td, llm=self.llm_ok)
        t = g._generate("арифметика", 2, T0)
        self.assertEqual(t["src"], "gen")
        self.assertEqual(t["check"]["value"], 144)

    def test_bad_generator_output_rejected(self):
        outs = iter(["не json", json.dumps({"prompt": "Скажи слово «банан» пожалуйста.", "check": {"kind": "contains_all", "items": ["банан"]}, "reference": "банан"}),
                     json.dumps({"prompt": "Сколько будет 12 умножить на 12? Ответь числом.", "check": {"kind": "number", "value": 144}, "reference": "145"})])
        g = mk(self.td, llm=lambda q: next(outs))
        self.assertIsNone(g._generate("арифметика", 2, T0, tries=3))                 # мусор, взлом проверки, неверный эталон

    def test_duplicate_of_seen_rejected(self):
        g = mk(self.td, llm=self.llm_ok)
        g.st["seen"].append(sorted(G.stems("Сколько будет 12 умножить на 12? Ответь числом.")))
        self.assertIsNone(g._generate("арифметика", 2, T0, tries=2))

    def test_exam_leak_rejected(self):
        ex = next(t for t in G.jl(ANCH) if t.get("exam") and t["area"] == "арифметика" and t["level"] == 1)
        g = mk(self.td, llm=lambda q: json.dumps({"prompt": ex["prompt"], "check": ex["check"], "reference": ex["reference"], "hints": []}))
        self.assertIsNone(g._generate("арифметика", 1, T0, tries=1))

    def test_busy_llm_propagates(self):
        class Busy(Exception):
            pass

        def llm(q):
            raise Busy()
        g = mk(self.td, llm=llm)
        with self.assertRaises(Busy):
            g._generate("арифметика", 2, T0)

    def test_lesson_from_evidence_keywords_must_be_in_quote(self):
        quote = "Порт быстрой модели NOX равен 8083, а основной модели GLM порт 8081."
        ok = lambda q: json.dumps({"prompt": "Какой порт у быстрой модели?", "items": ["8083"]})
        g = mk(self.td, llm=ok)
        r = g.learn_from_resolved("нокс", "порт быстрой модели", quote, "https://example.org/x", T0)
        self.assertTrue(r["ok"])
        self.assertEqual(g.st["srs"][r["id"]]["kind"], "lesson")
        self.assertEqual(len(G.jl(g.p_lessons)), 1)
        bad = lambda q: json.dumps({"prompt": "Какой порт у третьей модели?", "items": ["9999"]})
        g2 = mk(tempfile.mkdtemp(), llm=bad)
        self.assertFalse(g2.learn_from_resolved("нокс", "порт", quote, "", T0)["ok"])  # выдуманный ключ не из цитаты


class Srs(Base):
    def test_scar_review_cycle_and_heal(self):
        s = FakeSolver(skill=0)
        g = mk(self.td, s)
        task = next(t for t in g.anchors if t["area"] == "логика" and t["level"] == 3)
        g.run_task(dict(task, src="anchor"), T0)
        it = g.st["srs"][task["id"]]
        self.assertEqual(it["kind"], "scar")
        self.assertEqual(g.due_items(T0), [])                                       # сразу не пора
        self.assertEqual(len(g.due_items(T0 + 2 * DAY)), 1)
        s.skill = 5
        now = T0 + 2 * DAY
        for _ in range(12):
            if not g.due_items(now):
                now += 5 * DAY
            g.session(max_tasks=1, now=now) if False else None
            for it2 in g.due_items(now):
                g.run_task(it2["task"], now, srs_id=it2["id"])
            now += 1 * DAY * max(1.0, g.st["srs"][task["id"]]["S"])
            if g.st["srs"][task["id"]].get("healed"):
                break
        it = g.st["srs"][task["id"]]
        self.assertTrue(it.get("healed"))
        self.assertGreaterEqual(it["S"], 21)
        self.assertEqual(g.due_items(now + 100 * DAY), [])                          # зажившие не повторяются
        kinds = [r["kind"] for r in g.diary.read()]
        self.assertIn("scar", kinds)
        self.assertIn("scar_healed", kinds)

    def test_interleaving(self):
        g = mk(self.td)
        for i, a in enumerate(["a", "a", "a", "b", "b"]):
            g.st["srs"]["i%d" % i] = {"id": "i%d" % i, "kind": "scar", "area": a, "level": 1, "S": 1.0 + i * 0.01, "D": 5, "reps": 0, "lapses": 1,
                                      "last": T0, "due": T0 + 1, "task": {}}
        order = [x["area"] for x in g.due_items(T0 + 5 * DAY)]
        self.assertEqual(order[0:2].count("a"), 1)                                   # не две подряд из одной области, пока есть выбор


class Sleep(Base):
    def test_training_rows_rule_only_no_exam_capped(self):
        s = FakeSolver(skill=1)
        g = mk(self.td, s)
        fail = next(t for t in g.anchors if t["area"] == "python" and t["level"] == 3)
        g.run_task(dict(fail, src="anchor"), T0)                                      # провал: (неверный, 0) + (эталон, 1)
        rows = G.jl(g.p_train)
        self.assertEqual(sorted(r["v"] for r in rows), [0, 1])
        self.assertTrue(any(r["a"] == fail["reference"] and r["v"] == 1 for r in rows))
        ok2 = next(t for t in g.anchors if t["area"] == "арифметика" and t["level"] == 1 and not t.get("exam"))
        g.run_task(dict(ok2, src="anchor"), T0 + 1)                                   # успех на уровне 1 - не обучаем (тривиально)
        self.assertEqual(len(G.jl(g.p_train)), 2)
        ex = next(t for t in g.anchors if t.get("exam") and t["level"] >= 3)
        g.run_task(dict(ex, src="anchor"), T0 + 2)                                    # экзаменационная - никогда в обучение
        self.assertEqual(len(G.jl(g.p_train)), 2)
        j = {"id": "j", "area": "x", "level": 3, "prompt": "Объясни, что такое калибровка?", "check": {"kind": "judge", "criteria": "по существу"}}
        g.judge = lambda p, a, c: 0.1
        g.run_task(j, T0 + 3)                                                         # судейская - не в обучение (слабый источник)
        self.assertEqual(len(G.jl(g.p_train)), 2)
        for i in range(30):
            statefile_line = json.dumps({"q": "q%d" % i, "a": "a", "v": 1, "t": T0 + 10, "level": 2})
            G.statefile.append_line(g.p_train, statefile_line)
        self.assertEqual(len(g.sleep_batch(T0, owner_rows=0)), 10)                    # потолок: не более max(10, 43% от строк Создателя)
        self.assertEqual(len(g.sleep_batch(T0, owner_rows=100)), 32)
        self.assertEqual(len(g.sleep_batch(T0 + 11, owner_rows=100)), 0)


class Creator(Base):
    def stuck_growth(self):
        g = mk(self.td, FakeSolver(skill=0))
        for i in range(7):
            e = {"t": T0 + i, "l": 3, "s": 0.0, "w": 0.7, "a": 0, "src": "rule", "id": "f%d" % i}
            g._area("логика")["ev"].append(e)
        g._check_stuck("логика", 3, T0 + 10)
        return g

    def test_stuck_creates_one_ask_and_respects_quiet_and_rate(self):
        g = self.stuck_growth()
        self.assertEqual(len([a for a in g.st["ask"] if a["status"] == "open"]), 1)
        g._check_stuck("логика", 3, T0 + 20)
        self.assertEqual(len(g.st["ask"]), 1)                                         # без дублей
        self.assertEqual(g.pending_asks(NIGHT), [])                                   # тихие часы
        p = g.pending_asks(T0 + 100)
        self.assertEqual(len(p), 1)
        self.assertIn("застрял", p[0]["question"])
        g.mark_asked(p[0]["id"], T0 + 100)
        self.assertEqual(g.pending_asks(T0 + 200), [])                                # не чаще раза в сутки

    def test_creator_example_becomes_pinned_anchor_and_closes_ask(self):
        g = self.stuck_growth()
        aid = g.st["ask"][0]["id"]
        bad = g.add_creator_task("логика", 3, "Скажи слово «банан» пожалуйста.", {"kind": "contains_all", "items": ["банан"]}, "банан", ask_id=aid, now=T0)
        self.assertFalse(bad["ok"])
        r = g.add_creator_task("логика", 3, "Если все A это B, а все B это C, то все A это C? Ответь «да» или «нет».",
                               {"kind": "regex", "pattern": "^\\W*да\\W*$"}, "да", hints=["Построй цепочку."], ask_id=aid, now=T0)
        self.assertTrue(r["ok"])
        self.assertEqual(g.st["ask"][0]["status"], "answered")
        self.assertGreater(g.need("логика"), 0.2)                                     # область закреплена
        g2 = G.Growth(self.td, FakeSolver(), anchors_path=ANCH)                        # переживает перезапуск
        self.assertTrue(any(t.get("src") == "creator" for t in g2.anchors))
        t = next(t for t in g2.anchors if t.get("src") == "creator")
        s = FakeSolver()
        s.by_prompt[t["prompt"]] = t
        g2.solver = s
        s.skill = 5
        o = g2.run_task(t, T0 + 5)
        self.assertEqual(o["src"], "creator")
        self.assertEqual(g2._area("логика")["ev"][-1]["w"], 1.0)                      # вес Создателя 1.0

    def test_ingest_real_life_raises_need_when_progress(self):
        g = mk(self.td)
        for i in range(10):
            g.ingest("навык:backup", 0.0 if i < 5 else 1.0, "rule", now=T0 + i)
        self.assertGreater(g.need("навык:backup"), 0.4)
        self.assertEqual(g.need("арифметика"), 0.0)


class ExamAndReport(Base):
    def test_exam_frozen_and_report(self):
        s = FakeSolver(skill=1)
        g = mk(self.td, s)
        r0 = g.run_exam(T0, "base")
        self.assertTrue(r0["ok"])
        n_exam = sum(1 for t in g.anchors if t.get("exam"))
        self.assertEqual(r0["n"], n_exam)
        for skill, k in ((1, 1), (2, 2), (3, 3), (4, 4), (5, 5)):
            s.skill = skill
            g.run_exam(T0 + k * 7 * DAY, "w%d" % k)
        for _ in range(10):                                                           # обычные занятия не трогают экзамен
            g.session(max_tasks=3, now=T0 + 100)
        exam_ids = {t["id"] for t in g.anchors if t.get("exam")}
        used = set(g.st["used"])
        self.assertFalse(exam_ids & used)
        self.assertFalse(any(r.get("q") in {t["prompt"] for t in g.anchors if t.get("exam")} for r in G.jl(g.p_train)))
        rep = g.growth_report(T0 + 40 * DAY)
        self.assertEqual(rep["verdict"], "growth")
        self.assertGreater(rep["slope_per_week"], 0.05)

    def test_report_stagnation_and_insufficient(self):
        s = FakeSolver(skill=2)
        g = mk(self.td, s)
        self.assertEqual(g.growth_report(T0)["verdict"], "insufficient")
        for k in range(6):
            g.run_exam(T0 + k * 7 * DAY)
        self.assertEqual(g.growth_report(T0 + 50 * DAY)["verdict"], "stagnation")
        s.skill = 0
        for k in range(6, 12):
            g.run_exam(T0 + k * 7 * DAY)
        self.assertEqual(g.growth_report(T0 + 90 * DAY)["verdict"], "regression")


class DiaryTests(Base):
    def test_chain_and_tamper(self):
        g = mk(self.td, FakeSolver(skill=5))
        g.session(max_tasks=3, now=T0)
        g.run_exam(T0 + 10, "t")
        self.assertTrue(g.diary.verify()[0])
        rows = g.diary.read()
        self.assertGreaterEqual(len(rows), 2)
        rows[0]["data"]["n"] = 99
        with open(g.diary.path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        ok, bad = g.diary.verify()
        self.assertFalse(ok)
        self.assertEqual(bad, 0)

    def test_daily_text_only_facts(self):
        g = mk(self.td, FakeSolver(skill=2))
        for i in range(4):
            g.session(max_tasks=5, now=T0 + i * 600)
        txt = g.daily_text(now=T0)
        self.assertIn("Решал задач", txt)
        self.assertIn("Дневник роста", txt)
        self.assertEqual(g.daily_text(day="1999-01-01"), "1999-01-01: занятий не было.")


class Persistence(Base):
    def test_state_survives_restart(self):
        g = mk(self.td, FakeSolver(skill=2))
        g.session(max_tasks=5, now=T0)
        n = sum(len(A["ev"]) for A in g.st["areas"].values())
        self.assertGreater(n, 0)
        g2 = G.Growth(self.td, FakeSolver(), anchors_path=ANCH)
        self.assertEqual(sum(len(A["ev"]) for A in g2.st["areas"].values()), n)


class Integration(Base):
    def setUp(self):
        super().setUp()
        root = os.path.abspath(os.path.join(HERE, "..", ".."))
        for d in ("EMO", "ACT"):
            sys.path.insert(0, os.path.join(root, d))
        try:
            import drives as dv
            import gap_map as gm
            self.dv, self.gm = dv, gm
        except Exception as e:  # pragma: no cover
            self.skipTest("нет EMO/ACT рядом: %s" % e)

    def test_real_drives_and_gapmap(self):
        d = self.dv.Drives(os.path.join(self.td, "drives.json"))
        d.level["knowledge"] = 1.0
        gmap = self.gm.GapMap(os.path.join(self.td, "gaps.json"), allow_hosts=["example.org"])
        gmap.add_unknown("как работает квантование кэша ключей и значений", topic="llm")
        gmap.add_unknown("почему падает квантование кэша при длинном контексте", topic="llm")
        hooks = G.Hooks(G.DrivesHooks(d), G.GapHooks(gmap))
        g = mk(self.td, FakeSolver(skill=2), hooks=hooks)
        self.assertEqual(hooks.hunger(), 1.0)
        r = g.session(now=T0)
        self.assertEqual(r["budget"], 5)
        self.assertIn("llm", g.st["areas"])                                           # область из карты незнания
        self.assertGreater(g.need("llm"), 0.0)
        self.assertTrue(d.errs)                                                       # ошибки ушли в observe -> любопытство по прогрессу
        for _ in range(4):
            g.session(now=T0 + 60)
        self.assertIn("learning_progress", d.error_signals())

    def test_cli_report_empty(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = G.main(["report", "--state", self.td, "--anchors", ANCH])
        self.assertEqual(rc, 0)
        self.assertIn("insufficient", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
