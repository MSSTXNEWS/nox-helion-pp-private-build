import os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import outcome_stats as o


class TestOutcomeStats(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(tempfile.mkdtemp(), "out.json")

    def test_prior_and_updates(self):
        self.assertEqual(o.predict("deploy", self.p)["success_probability"], 0.5)
        for i in range(8):
            self.assertTrue(o.record("deploy", True, "тест зелёный", "e%d" % i, self.p))
        self.assertAlmostEqual(o.predict("deploy", self.p)["success_probability"], 9 / 10)
        self.assertTrue(o.record("deploy", False, "откат", "f1", self.p))
        r = o.predict("deploy", self.p)
        self.assertEqual(r["observations"], 9)
        self.assertAlmostEqual(r["success_probability"], 9 / 11)

    def test_idempotent_event(self):
        self.assertTrue(o.record("x", True, "ev", "same", self.p))
        self.assertFalse(o.record("x", True, "ev", "same", self.p))
        self.assertEqual(o.predict("x", self.p)["observations"], 1)

    def test_requires_evidence_and_bool(self):
        for bad in (dict(success=1, evidence="e"), dict(success=True, evidence=""), dict(success=True, evidence="  ")):
            with self.assertRaises(ValueError):
                o.record("k", event_id="id", path=self.p, **bad)
        with self.assertRaises(ValueError):
            o.record("", True, "e", "id", self.p)
        self.assertEqual(o.predict("k", self.p)["observations"], 0)

    def test_kinds_isolated_and_persist(self):
        o.record("a", False, "e", "1", self.p); o.record("a", False, "e", "2", self.p)
        self.assertLess(o.predict("a", self.p)["success_probability"], 0.5)
        self.assertEqual(o.predict("b", self.p)["success_probability"], 0.5)
        self.assertEqual(o.signal("a", self.p), {"work.pred_success": 0.25})

    def test_cli(self):
        os.environ["NOX_OUTCOMES"] = self.p
        o.DEFAULT = self.p
        self.assertEqual(o.main(["record", "k", "ok", "доказательство", "c1"]), 0)
        self.assertEqual(o.main(["predict", "k"]), 0)


if __name__ == "__main__":
    unittest.main()
