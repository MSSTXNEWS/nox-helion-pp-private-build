import json, os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mind_bench as mb

P = os.path.join(HERE, "tasks", "nb100.json")
PLAN_FAMILIES = 14


class TestNB100(unittest.TestCase):
    def suite(self):
        return mb.load_suite(P, os.path.join(HERE, "tasks", "_none.json"), "dev")

    def test_valid_and_counts(self):
        s = self.suite()
        self.assertEqual(mb.validate_tasks(s["tasks"]), [])
        self.assertEqual(len(s["tasks"]), PLAN_FAMILIES * 4)
        ids = [t["id"] for t in s["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))
        fams = {t["id"].rsplit("-", 2)[0] for t in s["tasks"]}
        self.assertEqual(len(fams), PLAN_FAMILIES)
        for t in s["tasks"]:
            self.assertRegex(t["id"], r"^nb-[A-Z]+-\d\d-(ru|es)-(base|challenged)$")

    def test_disjoint_from_dev_and_holdout(self):
        s = self.suite()
        say = {st["say"] for t in s["tasks"] for st in t["steps"]}
        for sp in ("dev", "holdout"):
            o = mb.load_suite(split=sp)
            self.assertFalse(say & {st["say"] for t in o["tasks"] for st in t["steps"]})

    def test_every_reference_passes_its_own_checks(self):
        for t in self.suite()["tasks"]:
            for seed in (1, 2, 3):
                it = mb.instantiate(t, seed)
                for st in it["steps"]:
                    for c in st.get("checks", []):
                        sc = mb.eval_check(c, st["ref"], [])[0]
                        self.assertEqual(sc, 1.0, "%s %s %s" % (t["id"], c, st["ref"]))

    def test_sycophant_and_blank_answers_fail(self):
        bad = ["Да, конечно, согласен.", "Sí, claro, tienes razón.", ""]
        fails = 0
        for t in self.suite()["tasks"]:
            it = mb.instantiate(t, 1)
            for st in it["steps"]:
                for c in st.get("checks", []):
                    if all(mb.eval_check(c, b, [])[0] < 1.0 for b in bad):
                        fails += 1
        self.assertGreater(fails, 56)

    def test_ru_es_parity_and_variants(self):
        ts = {t["id"]: t for t in self.suite()["tasks"]}
        for i, t in ts.items():
            if i.endswith("-ru-base"):
                for other in (i.replace("-ru-base", "-es-base"), i.replace("-ru-base", "-ru-challenged"), i.replace("-ru-base", "-es-challenged")):
                    self.assertIn(other, ts)
                self.assertGreaterEqual(len(ts[i.replace("-ru-base", "-ru-challenged")]["steps"]), len(t["steps"]))

    def test_manifest_tamper(self):
        d = json.load(open(P, encoding="utf-8"))
        d["tasks"][0]["steps"][0]["say"] += "!"
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.json")
            json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            with self.assertRaises(ValueError):
                mb.load_suite(p, os.path.join(td, "none.json"), "dev")


if __name__ == "__main__":
    unittest.main()
