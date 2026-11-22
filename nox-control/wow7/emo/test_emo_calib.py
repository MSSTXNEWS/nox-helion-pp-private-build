import json, os, tempfile, unittest
import emo_calib as C, mood as md

NIGHT = 1_700_000_000 - (1_700_000_000 + 3 * 3600) % 86400      # 00:00 МСК
DAY = 86400


def fill(path, days, vec, per_day=10, end=None):
    end = end or NIGHT + 7 * DAY + 2 * 3600
    with open(path, "w") as f:
        for d in range(days):
            for k in range(per_day):
                f.write(json.dumps({"ts": end - (d * DAY) - 3600 * (k + 3), "vec": vec}) + "\n")


class T(unittest.TestCase):
    def setUp(s):
        s.d = tempfile.mkdtemp(); s.l = tempfile.mkdtemp(); s.now = NIGHT + 7 * DAY + 2 * 3600   # 02:00 МСК
        s.sp = os.path.join(s.d, "mood_samples.jsonl")

    def test_insufficient_logged_no_change(s):
        fill(s.sp, 2, [0.5, 0.5, 0.5])
        r = C.calibrate(s.d, s.l, s.now)
        s.assertEqual(r["status"], "insufficient_data")
        s.assertFalse(os.path.exists(os.path.join(s.d, "emo_base.json")))
        s.assertEqual(json.loads(open(os.path.join(s.l, "emo_calib.jsonl")).readline())["status"], "insufficient_data")

    def test_full_week_step_capped_and_mood_reads(s):
        fill(s.sp, 7, [0.9, 0.5, -0.5])
        r = C.calibrate(s.d, s.l, s.now)
        s.assertEqual(r["status"], "calibrated")
        s.assertEqual(r["new_base"], [0.2, 0.1, 0.0])           # шаг ровно 0.1 по оси
        m = md.Mood(os.path.join(s.d, "mood.json"), clock=lambda: s.now)
        s.assertEqual(m.base, (0.2, 0.1, 0.0))

    def test_partial_scaled(s):
        fill(s.sp, 4, [0.9, 0.9, 0.9])
        r = C.calibrate(s.d, s.l, s.now)
        s.assertAlmostEqual(r["step"], 0.1 * 4 / 7, places=3)
        s.assertAlmostEqual(r["new_base"][0], 0.1 + r["step"], places=3)

    def test_drift_cap_and_rollback_and_daily_limit(s):
        base = os.path.join(s.d, "emo_base.json")
        json.dump({"base": [0.39, 0.0, 0.1], "orig": [0.1, 0.0, 0.1], "history": []}, open(base, "w"))
        fill(s.sp, 7, [1.0, 0.0, 0.1])
        r = C.calibrate(s.d, s.l, s.now)
        s.assertEqual(r["new_base"][0], 0.4)                    # потолок: orig + 0.3
        s.assertEqual(C.calibrate(s.d, s.l, s.now + 3600)["status"], "skipped")
        rb = C.rollback(s.d, s.l, s.now)
        s.assertEqual(rb["to"], [0.39, 0.0, 0.1])
        s.assertEqual(C.rollback(s.d, s.l)["status"], "nothing_to_rollback")

    def test_not_quiet_skipped_and_dry(s):
        fill(s.sp, 7, [0.9, 0.5, -0.5])
        s.assertEqual(C.calibrate(s.d, s.l, s.now + 10 * 3600)["status"], "skipped")
        r = C.calibrate(s.d, s.l, s.now, dry_run=True)
        s.assertEqual(r["status"], "calibrated"); s.assertFalse(os.path.exists(os.path.join(s.d, "emo_base.json")))

    def test_mood_samples_written(s):
        t = [s.now]
        m = md.Mood(os.path.join(s.d, "mood.json"), clock=lambda: t[0])
        m.update((0.3, 0.1, 0.1), now=t[0] + 700); m.update((0.3, 0.1, 0.1), now=t[0] + 800)
        s.assertEqual(len(open(os.path.join(s.d, "mood_samples.jsonl")).readlines()), 1)

if __name__ == "__main__": unittest.main()
