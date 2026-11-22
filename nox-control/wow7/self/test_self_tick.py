import json, os, tempfile, unittest, calendar
import self_tick as S


class T(unittest.TestCase):
    def test_tick_end_to_end(self):
        d = tempfile.mkdtemp()
        json.dump({"pad": {"p": 0.6, "a": 0.4, "d": 0.2}}, open(os.path.join(d, "mood.json"), "w"))
        json.dump({"mood_label": "бодрое", "music": {"bpm": 90, "mode": "major", "intensity": 0.7}, "scene": {"hex": "#d9a441"}}, open(os.path.join(d, "mood_ui.json"), "w"))
        noon = calendar.timegm((2026, 11, 22, 9, 0, 0))  # 12:00 МСК
        r = S.tick(d, now=noon)
        self.assertFalse(r["night"])
        self.assertTrue(r["voice"]["changed"])
        sm = json.load(open(os.path.join(d, "soundscape_mood.json")))
        self.assertEqual(sm["bpm"], 90)
        self.assertFalse(sm["quiet"])
        self.assertIn(r["ui"]["status"], ("applied_trial", "pending_owner", "rejected"))
        night = calendar.timegm((2026, 11, 22, 21, 0, 0))  # 00:00 МСК
        self.assertTrue(S.tick(d, dry=True, now=night)["soundscape_mood"]["quiet"])

    def test_empty_state(self):
        r = S.tick(tempfile.mkdtemp(), dry=True)
        self.assertEqual(r["mood"], (0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
