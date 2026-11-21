import os, sys, json, tempfile, unittest
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disturb_check import DisturbCheck, load_config


def dt(h, m=0, day=10):
    return datetime(2026, 11, day, h, m)


class T(unittest.TestCase):
    def mk(self, **kw):
        return DisturbCheck(load_config(data=kw))

    def test_ok_daytime(self):
        r = self.mk().decide(dt(14), dt(13, 30))
        self.assertTrue(r.allow); self.assertEqual(r.code, "ok")

    def test_night_blocks_and_critical_passes(self):
        c = self.mk()
        self.assertEqual(c.decide(dt(2), dt(1, 50)).code, "night")
        self.assertEqual(c.decide(dt(23, 30), dt(23, 0), "high").code, "night")
        self.assertTrue(c.decide(dt(3), None, "critical").allow)

    def test_dnd_window(self):
        c = self.mk(dnd_windows=[["13:00", "15:00"]])
        self.assertEqual(c.decide(dt(14), dt(13, 0)).code, "dnd")
        self.assertTrue(c.decide(dt(14), dt(13, 0), "high").allow)
        self.assertTrue(c.decide(dt(15, 1), dt(14, 0)).allow)

    def test_busy_and_away(self):
        c = self.mk()
        self.assertEqual(c.decide(dt(12), dt(11, 58)).code, "busy")
        self.assertEqual(c.decide(dt(20), dt(2)).code, "away")

    def test_daily_limit_and_gap(self):
        c = self.mk(max_proactive_per_day=2, min_gap_minutes=30)
        c.record_sent(dt(9)); 
        self.assertEqual(c.decide(dt(9, 10), dt(8)).code, "gap")
        c.record_sent(dt(11))
        self.assertEqual(c.decide(dt(15), dt(14)).code, "daily_limit")
        self.assertTrue(c.decide(dt(15), dt(14), "high").allow)
        self.assertTrue(c.decide(dt(9, 0, 11), dt(8, 0, 11)).allow)  # новые сутки

    def test_sensors_ignored_without_consent(self):
        c = self.mk()
        r = c.decide(dt(14), dt(13), sensors={"camera_presence": False, "mic_speech": True})
        self.assertTrue(r.allow); self.assertEqual(r.used_sensors, [])
        self.assertIn("нет согласия", r.reason)

    def test_sensors_with_consent(self):
        c = self.mk(consent={"camera": True, "microphone": True})
        r = c.decide(dt(14), dt(13), sensors={"camera_presence": False})
        self.assertEqual(r.code, "absent"); self.assertEqual(r.used_sensors, ["camera"])
        r = c.decide(dt(14), dt(13), sensors={"mic_speech": True})
        self.assertEqual(r.code, "speech")
        r = c.decide(dt(14), dt(13), sensors={"camera_presence": True, "mic_speech": False})
        self.assertTrue(r.allow)

    def test_default_consent_off_and_file_config(self):
        self.assertFalse(load_config()["consent"]["camera"])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            json.dump({"night_start": "00:00", "night_end": "00:00", "consent": {"camera": True}}, open(p, "w"))
            cfg = load_config(p)
            self.assertTrue(cfg["consent"]["camera"]); self.assertFalse(cfg["consent"]["microphone"])
            self.assertTrue(DisturbCheck(cfg).decide(dt(3), dt(2, 30)).allow)  # окно нулевой длины


if __name__ == "__main__":
    unittest.main()
