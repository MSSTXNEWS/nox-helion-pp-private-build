import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qs6.emotion_pad import PadState, appraise, impulse, BASELINE, HALF_LIFE


def names(ev):
    return [n for n, _ in appraise(ev)]


class AppraiseT(unittest.TestCase):
    def test_occ_rules(self):
        self.assertEqual(names({"goal": 0.6}), ["joy"])
        self.assertEqual(names({"goal": -0.6}), ["distress"])
        self.assertEqual(names({"goal": 0.5, "norm": 0.5, "agent": "self"}), ["gratification"])
        self.assertEqual(names({"goal": -0.5, "norm": -0.5, "agent": "self"}), ["remorse"])
        self.assertEqual(names({"goal": 0.5, "norm": 0.5, "agent": "owner"}), ["gratitude"])
        self.assertEqual(names({"goal": -0.5, "norm": -0.5, "agent": "other"}), ["anger"])
        self.assertEqual(names({"norm": 0.6, "agent": "self"}), ["pride"])
        self.assertEqual(names({"norm": -0.6, "agent": "self"}), ["shame"])
        self.assertEqual(names({"norm": 0.6, "agent": "other"}), ["admiration"])
        self.assertEqual(names({"norm": -0.6, "agent": "owner"}), ["reproach"])
        self.assertEqual(names({"taste": 0.7}), ["liking"])
        self.assertEqual(names({"taste": -0.7}), ["disliking"])
        self.assertEqual(names({"goal": 0.5, "norm": -0.5, "agent": "other"}), ["joy", "reproach"])   # знаки разные: раздельно
        self.assertEqual(names({"goal": 0.1, "norm": 0.1}), [])                                       # ниже порога
        self.assertEqual(names({}), [])

    def test_surprise_amplifies_and_caps(self):
        base = dict(appraise({"goal": 0.4}))["joy"]
        up = dict(appraise({"goal": 0.4, "unexpected": 1.0}))["joy"]
        self.assertAlmostEqual(up, base * 1.5)
        self.assertEqual(dict(appraise({"goal": 1.0, "unexpected": 1.0}))["joy"], 1.0)

    def test_impulse_signs(self):
        p, a, d = impulse({"goal": -0.7, "norm": -0.7, "agent": "other"})      # гнев
        self.assertTrue(p < 0 and a > 0 and d > 0)
        p, a, d = impulse({"goal": -0.7, "norm": -0.7, "agent": "self"})       # раскаяние
        self.assertTrue(p < 0 and d < 0)


class StateT(unittest.TestCase):
    def test_scenarios_and_decay(self):
        st = PadState(now=0.0)
        self.assertEqual(st.value(0.0), BASELINE)
        self.assertIn("Тон обычный.", st.style(0.0)["notes"])
        st.apply("owner_thanks", now=0.0)
        s0 = st.style(0.0)
        self.assertGreater(s0["warmth"], 0.6)
        self.assertIn("Тон теплее обычного, но без лести.", s0["notes"])
        p0 = st.value(0.0)[0]
        p1 = st.value(HALF_LIFE[0])[0]
        self.assertAlmostEqual(p1 - BASELINE[0], (p0 - BASELINE[0]) / 2, places=6)       # период полураспада
        self.assertAlmostEqual(st.value(1e7)[0], BASELINE[0], places=4)                   # затухло к базовому

    def test_failure_makes_cautious_and_short(self):
        st = PadState(now=0.0)
        for _ in range(2):
            st.apply("task_failed", now=0.0)
        s = st.style(0.0)
        self.assertGreater(s["caution"], 0.45)
        self.assertGreater(s["brevity"], 0.5)
        self.assertLess(s["warmth"], 0.4)
        self.assertIn("Тон суше и собраннее обычного, без грубости.", s["notes"])
        self.assertTrue(any("фактами" in n for n in s["notes"]))
        late = st.style(3 * 3600)
        self.assertLess(late["caution"], s["caution"])
        self.assertIn("Тон обычный.", late["notes"])

    def test_clamp_and_log(self):
        st = PadState(now=0.0)
        for _ in range(20):
            st.apply({"goal": 1.0, "norm": 1.0, "agent": "self", "unexpected": 1.0}, now=0.0)
        self.assertTrue(all(-1.0 <= x <= 1.0 for x in st.value(0.0)))
        self.assertEqual(len(st.log), 20)
        self.assertTrue(st.prompt_line(0.0))

    def test_unknown_preset(self):
        with self.assertRaises(KeyError):
            PadState().apply("нет такого")


if __name__ == "__main__":
    unittest.main()
