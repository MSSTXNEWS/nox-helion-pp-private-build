import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smart_memory import SmartMemory, extract_claims, SECRET


class T(unittest.TestCase):
    def setUp(self):
        self.m = SmartMemory()
        self.addCleanup(self.m.close)

    def test_knowledge_map_and_visibility(self):
        a = self.m.add_fact("Аня", "день рождения", "5 мая")
        b = self.m.add_fact("Аня", "подарок", "часы", SECRET, knows=["Борис"])
        self.assertEqual(self.m.who_knows(b), ["борис"])
        self.assertEqual({r[0] for r in self.m.facts_about("аня", viewer="Вера")}, {a})
        self.assertEqual({r[0] for r in self.m.facts_about("аня", viewer="Борис")}, {a, b})
        self.assertEqual(len(self.m.facts_about("Аня")), 2)
        self.assertEqual(self.m.secrets()[0][0], b)
        self.m.share(b, "Вера")
        self.assertEqual(self.m.knowledge_map()["вера"], [b])
        self.m.set_visibility(b, "known")
        self.assertEqual(self.m.secrets(), [])
        with self.assertRaises(ValueError):
            self.m.add_fact("x", "y", "z", "weird")

    def test_extract(self):
        c = extract_claims("Сервер.порт = 8080; owner: город = Москва")
        self.assertEqual([(x[0], x[1], x[2]) for x in c], [("Сервер", "порт", "8080"), ("owner", "город", "Москва")])

    def test_contradiction_and_autocorrect(self):
        self.m.add_fact("сервер", "порт", "8080")
        self.m.add_fact("owner", "город", "Москва")
        ok = "сервер.порт = 8080"
        self.assertEqual(self.m.find_contradictions(ok), [])
        txt = "Итак: сервер.порт = 9090; owner: город = Казань."
        cs = self.m.find_contradictions(txt)
        self.assertEqual({(c["predicate"], c["stored"]) for c in cs}, {("порт", "8080"), ("город", "Москва")})
        fixed, _ = self.m.autocorrect(txt)
        self.assertEqual(fixed, "Итак: сервер.порт = 8080; owner: город = Москва.")
        self.assertEqual(self.m.find_contradictions(fixed), [])

    def test_unknown_and_multi(self):
        self.assertEqual(self.m.find_contradictions("a.b = c"), [])
        self.m.add_fact("аня", "хобби", "шахматы"); self.m.set_multi("хобби")
        self.assertEqual(self.m.find_contradictions("аня.хобби = лыжи"), [])

    def test_latest_fact_wins(self):
        self.m.add_fact("s", "p", "old", ts=1); self.m.add_fact("s", "p", "new", ts=2)
        self.assertEqual(self.m.find_contradictions("s.p = old")[0]["stored"], "new")
        self.assertEqual(self.m.find_contradictions("s.p = NEW"), [])

    def test_last_time(self):
        self.assertEqual(self.m.recall_last(now=100), [])
        self.m.record_topic("бэкап сервера", "нужно проверить диск", ts=1000)
        self.assertEqual(self.m.recall_last(now=1000 + 3600, pause_threshold=6 * 3600), [])
        ph = self.m.recall_last(now=1000 + 10 * 3600, pause_threshold=6 * 3600)
        self.assertEqual(len(ph), 2); self.assertIn("бэкап сервера", ph[0]); self.assertIn("проверить диск", ph[1])
        self.m.record_topic("музыка", "", ts=2000)
        ph = self.m.recall_last(now=2000 + 10 * 3600)
        self.assertIn("музыка", ph[0]); self.assertIn("бэкап сервера", ph[1])
        self.assertEqual(len(self.m.recall_last(now=2000 + 10 * 3600, max_phrases=1)), 1)


if __name__ == "__main__":
    unittest.main()
