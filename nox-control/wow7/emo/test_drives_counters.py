import os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import drives as dv


def mk(t):
    return dv.Drives(path=os.path.join(tempfile.mkdtemp(), "d.json"), clock=lambda: t[0])


class TestCounterDelta(unittest.TestCase):
    def test_repeated_snapshot_does_not_satisfy_twice(self):
        t = [0.0]; d = mk(t)
        d.level["mastery"] = 0.9
        d.tick({"tasks_done_1h": 3}, now=0.0)
        after_first = d.level["mastery"]
        self.assertAlmostEqual(after_first, 0.9 - 0.10 * 3)
        for i in range(5):                                   # тот же снимок ещё 5 раз
            d.tick({"tasks_done_1h": 3}, now=0.0)
        self.assertAlmostEqual(d.level["mastery"], after_first)

    def test_new_work_counts_only_the_increment(self):
        t = [0.0]; d = mk(t)
        d.level["knowledge"] = 0.9
        d.tick({"new_facts_1h": 2}, now=0.0)
        lv = d.level["knowledge"]
        d.tick({"new_facts_1h": 5}, now=0.0)
        self.assertAlmostEqual(d.level["knowledge"], lv - 0.08 * 3)

    def test_window_shrink_is_not_new_work_and_restart_keeps_baseline(self):
        t = [0.0]; d = mk(t)
        d.tick({"tasks_done_1h": 4}, now=0.0)
        d.level["mastery"] = 0.7
        d.tick({"tasks_done_1h": 2}, now=0.0)                # окно сдвинулось: 0 прироста
        self.assertAlmostEqual(d.level["mastery"], 0.7)
        d.save()
        d2 = dv.Drives(path=d.path, clock=lambda: t[0])
        d2.level["mastery"] = 0.7
        d2.tick({"tasks_done_1h": 2}, now=0.0)               # после перезапуска тот же снимок не засчитывается
        self.assertAlmostEqual(d2.level["mastery"], 0.7)

    def test_other_signals_unchanged(self):
        t = [0.0]; d = mk(t)
        d.tick({"vast_hours_left": 4}, now=0.0)
        self.assertGreater(d.fear["vanish"], 0.5)


if __name__ == "__main__":
    unittest.main()
