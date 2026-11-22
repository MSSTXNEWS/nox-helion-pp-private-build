import tempfile, unittest
import tastes as T


def feat(**k):
    d = dict(title="Track A", artist="Artist X", genres=["ambient"], bpm=60, mode="minor", energy=0.3, valence=0.4, description="ночь и тишина космоса")
    d.update(k)
    return d


class Tst(unittest.TestCase):
    def setUp(self):
        self.t = [0.0]
        self.s = T.Tastes(tempfile.mkdtemp(), clock=lambda: self.t[0])

    def test_themes(self):
        self.assertEqual(T.extract_themes("Ночью над морем, космос"), ["космос", "море", "ночь"])

    def test_own_score_without_owner(self):
        r = self.s.listen(feat())
        self.assertIsNone(r["owner"])
        self.assertTrue(r["why"])
        self.assertIn("genre:ambient", r["keys"])
        self.assertIn("theme:космос", r["keys"])

    def test_owner_bounded_influence(self):
        a = self.s.listen(feat(title="Loud", genres=["metal"], energy=0.95, valence=0.1, description=""), reaction="love", dry_run=True)
        self.assertAlmostEqual(a["final"], (1 - T.OWNER_W) * a["own"] + T.OWNER_W * 1.0, places=2)
        self.assertTrue(a["disagreement"] or a["own"] > -0.15)

    def test_disagreement_recorded(self):
        # у NOX энергия 0.45; трек очень энергичный, новизна низкая -> своё мнение отрицательное; владелец любит
        for i in range(8):
            self.s.listen(feat(title="t%d" % i, genres=["metal"], energy=0.98, valence=0.05, description=""), reaction="dislike")
        r = self.s.listen(feat(title="again", genres=["metal"], energy=0.98, valence=0.05, description=""), reaction="love", dry_run=True)
        self.assertLess(r["own"], 0)
        self.assertTrue(r["disagreement"])
        self.assertTrue(any("расхождение" in w for w in r["why"]))

    def test_taste_forms_over_time(self):
        for i in range(6):
            self.s.listen(feat(title="a%d" % i, energy=0.4), reaction="like")
        top = self.s.top("genre")
        self.assertEqual(top[0][0], "ambient")
        self.assertGreater(top[0][1], 0.3)

    def test_rollback_restores(self):
        r0 = self.s.listen(feat(title="one"), reaction="like")
        before = dict(self.s.st["items"]["genre:ambient"])
        r1 = self.s.listen(feat(title="two"), reaction="dislike")
        self.assertNotEqual(self.s.st["items"]["genre:ambient"]["v"], before["v"])
        self.assertEqual(self.s.rollback(r1["id"])["status"], "rolled_back")
        self.assertAlmostEqual(self.s.st["items"]["genre:ambient"]["v"], before["v"], places=3)
        self.assertEqual(self.s.rollback(r1["id"])["status"], "error")
        self.assertEqual(self.s.rollback(999)["status"], "error")

    def test_why_returns_reasons(self):
        self.s.listen(feat(), reaction="like")
        w = self.s.why("ambient")
        self.assertEqual(len(w), 1)
        self.assertTrue(w[0]["why"])

    def test_persist(self):
        self.s.listen(feat(), reaction="like")
        s2 = T.Tastes(self.s.dir)
        self.assertEqual(s2.st["items"].keys(), self.s.st["items"].keys())

    def test_decay_after_day(self):
        self.s.listen(feat(), reaction="love")
        v = self.s.st["items"]["genre:ambient"]["v"]
        self.assertEqual(self.s.decay(), 0)
        self.t[0] += 10 * 86400
        self.s.decay()
        self.assertLess(self.s.st["items"]["genre:ambient"]["v"], v)

    def test_mood_bias(self):
        self.assertIsNone(self.s.mood_bias())
        for i in range(4):
            self.s.listen(feat(title="m%d" % i, bpm=70, mode="dorian", energy=0.4), reaction="like")
        b = self.s.mood_bias()
        self.assertEqual(b["mode"], "dorian")
        self.assertTrue(60 <= b["bpm"] <= 80)

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.s.listen({})
        with self.assertRaises(ValueError):
            self.s.listen(feat(), reaction="wow")

    def test_temperament_changes_score(self):
        s_n = T.Tastes(tempfile.mkdtemp(), temperament={"novelty": 1.0})
        s_c = T.Tastes(tempfile.mkdtemp(), temperament={"novelty": 0.0})
        f = feat(description="")
        self.assertGreater(s_n.listen(f, dry_run=True)["own"], s_c.listen(f, dry_run=True)["own"])


if __name__ == "__main__":
    unittest.main()
