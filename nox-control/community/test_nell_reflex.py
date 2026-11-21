import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nell_reflex import (MemoryStore, dream, EmotionDiary, BodyModel, current_weight, reinforce,
                         forget_sweep, keywords, DAY, _read_jsonl)

T0 = 1_700_000_000.0
MEMS = [
    {"id": "1", "text": "Мы гуляли у реки вечером", "emotion": "радость", "intensity": 0.5, "ts": T0},
    {"id": "2", "text": "Река замёрзла зимой", "emotion": "грусть", "intensity": 0.4, "ts": T0},
    {"id": "3", "text": "Починил сервер ночью", "emotion": "радость", "intensity": 0.8, "ts": T0},
    {"id": "4", "text": "Купил хлеб", "emotion": "", "intensity": 0.1, "ts": T0},
]


class Stores(unittest.TestCase):
    def test_jsonl_and_sqlite(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("m.jsonl", "m.db"):
                s = MemoryStore(os.path.join(d, name))
                for m in MEMS:
                    s.add(m)
                self.assertEqual([m["id"] for m in s.all()], ["1", "2", "3", "4"])
                s.add({"id": "4", "text": "Купил хлеб и молоко"})
                self.assertEqual(s.get("4")["text"], "Купил хлеб и молоко")
                self.assertEqual(len(s.all()), 4)
                s.close()
                s2 = MemoryStore(os.path.join(d, name))     # перечитывание с диска
                self.assertEqual(len(s2.all()), 4); s2.close()


class Dreams(unittest.TestCase):
    def test_pairs_shared_keywords(self):
        self.assertIn("река", keywords("Река замёрзла"))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "dreams.jsonl")
            out = dream([dict(m, weight=1) for m in MEMS], p, seed=1)
            self.assertEqual(len(out), 1)               # единственная пара с общим словом «река»
            self.assertEqual(out[0]["pair"], ["1", "2"]); self.assertEqual(out[0]["shared"], ["рек"])
            self.assertEqual(len(_read_jsonl(p)), 1)
            top = dream(MEMS, seed=1, min_shared=0, max_pairs=5)
            self.assertEqual(top[0]["pair"], ["1", "3"])  # одна эмоция (1.5) выше одного общего слова (1.0)
            self.assertIn(["1", "2"], [x["pair"] for x in top])
            self.assertTrue(all(len(x["pair"]) == 2 for x in dream(MEMS, seed=2, min_shared=0, max_pairs=10)))
            self.assertEqual(dream([MEMS[3]]), [])


class Diary(unittest.TestCase):
    def test_threshold_and_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            di = EmotionDiary(os.path.join(d, "diary.jsonl"), threshold=0.7)
            self.assertIsNone(di.observe(MEMS[0]))
            r = di.observe(MEMS[2]); self.assertEqual(r["memory_id"], "3")
            self.assertIsNone(di.observe(MEMS[2]))
            self.assertEqual(len(di.entries()), 1)


class Body(unittest.TestCase):
    def test_energy_cycle(self):
        b = BodyModel()
        self.assertEqual(b.mode(15), "active")
        for _ in range(20):
            b.activity(2, hour=15)
        self.assertEqual(b.energy, 0.0 if b.energy == 0 else b.energy)
        self.assertEqual(b.mode(15), "low")
        e0 = b.energy; b.sleep(8)
        self.assertGreater(b.energy, e0); self.assertEqual(b.mode(15), "active")

    def test_circadian_and_night_cost(self):
        self.assertAlmostEqual(BodyModel.circadian(15), 1.0); self.assertAlmostEqual(BodyModel.circadian(3), 0.6)
        a, c = BodyModel(), BodyModel()
        a.activity(5, hour=15); c.activity(5, hour=3)
        self.assertLess(c.energy, a.energy)
        self.assertEqual(BodyModel(energy=0.4).mode(15), "active")
        self.assertEqual(BodyModel(energy=0.4).mode(3), "low")      # ночью порог выше из-за ритма

    def test_persist(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.json"); b = BodyModel(path=p); b.activity(10, 15)
            self.assertAlmostEqual(BodyModel(path=p).energy, b.energy)


class Forgetting(unittest.TestCase):
    def mem(self, **kw):
        return dict({"id": "x", "text": "t", "intensity": 0.0, "ts": T0, "weight": 1.0, "last_access": T0, "half_life_days": 10.0}, **kw)

    def test_decay_half_life_and_emotion(self):
        m = self.mem()
        self.assertAlmostEqual(current_weight(m, T0 + 10 * DAY), 0.5)
        self.assertAlmostEqual(current_weight(m, T0 + 20 * DAY), 0.25)
        self.assertGreater(current_weight(self.mem(intensity=1.0), T0 + 10 * DAY), 0.7)

    def test_reinforce(self):
        m = self.mem(); now = T0 + 10 * DAY
        reinforce(m, now)
        self.assertAlmostEqual(m["weight"], 0.8); self.assertEqual(m["last_access"], now); self.assertEqual(m["half_life_days"], 15.0)
        self.assertLessEqual(reinforce(self.mem(), T0, boost=5)["weight"], 1.0)

    def test_sweep_deletes_with_journal(self):
        with tempfile.TemporaryDirectory() as d:
            s = MemoryStore(os.path.join(d, "m.db")); j = os.path.join(d, "j.jsonl")
            s.add(self.mem(id="old", text="старое")); s.add(self.mem(id="touched", text="часто", half_life_days=10.0))
            m = s.get("touched"); reinforce(m, T0 + 40 * DAY, boost=0.9); s.add(m)
            gone = forget_sweep(s, now=T0 + 50 * DAY, threshold=0.05, journal_path=j)
            self.assertEqual(gone, ["old"])
            self.assertEqual([x["id"] for x in s.all()], ["touched"])
            log = _read_jsonl(j); self.assertEqual(log[0]["id"], "old"); self.assertEqual(log[0]["text"], "старое")
            self.assertEqual(forget_sweep(s, now=T0 + 50 * DAY, journal_path=j), [])
            s.close()


if __name__ == "__main__":
    unittest.main()
