import os, tempfile, unittest
import voice_designer as vd


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.t = [1000.0]
        self.v = vd.VoiceDesigner(self.d, clock=lambda: self.t[0])

    def test_targets_within_band(self):
        for phase in vd.PHASES:
            for mood in [(1, 1, 1), (-1, -1, -1), (0, 0, 0)]:
                nums, why = vd.target_numbers(mood, phase)
                b = vd.PHASE_BASE[phase]
                for k, v in nums.items():
                    self.assertLessEqual(abs(v - b[k]), vd.BAND[k] + 1e-9)
                self.assertTrue(why)

    def test_phase_deeper_with_age(self):
        self.assertLess(vd.PHASE_BASE["elder"]["pitch_st"], vd.PHASE_BASE["newborn"]["pitch_st"])

    def test_decide_writes_journal_with_reason(self):
        r = self.v.decide((0.8, 0.7, 0.2), "adult")
        self.assertTrue(r["changed"])
        self.assertTrue(any("радость" in w for w in r["why"]))
        self.assertEqual(len(self.v.why()), 1)
        self.assertTrue(os.path.exists(self.v.profile_path))

    def test_hysteresis_and_step_limit(self):
        self.v.decide((0, 0, 0), "adult")
        p0 = self.v.current().pitch_st
        self.t[0] += 10
        self.assertFalse(self.v.decide((1, 1, 0), "adult")["changed"])
        self.t[0] += vd.MIN_DWELL_S + 1
        self.v.decide((1, 1, 0), "adult")
        self.assertLessEqual(abs(self.v.current().pitch_st - p0), vd.MAX_STEP["pitch_st"] + 1e-9)

    def test_rollback(self):
        self.v.decide((0, 0, 0), "adult")
        a = self.v.current().pitch_st
        self.t[0] += vd.MIN_DWELL_S + 1
        self.v.decide((1, 1, 0), "adult")
        self.assertNotEqual(self.v.current().pitch_st, a)
        self.assertTrue(self.v.rollback()["rolled_back"])
        self.assertEqual(self.v.current().pitch_st, a)
        self.assertEqual(self.v.why(1)[0]["action"], "rollback")

    def test_license_filter(self):
        self.assertEqual(vd.pick_backend("ru", True, {"xtts_clone", "silero_ru"}), "xtts_clone")
        self.assertEqual(vd.pick_backend("ru", False, {"xtts_clone", "silero_ru"}), None)
        self.assertEqual(vd.pick_backend("ru", False, {"espeech_clone", "xtts_clone"}), "espeech_clone")
        self.assertEqual(vd.pick_backend("en", False), "kokoro_mix")

    def test_kokoro_mix_sums_to_one_and_string(self):
        s = vd.base_spec("adult")
        m = vd.kokoro_mix_weights(s)
        self.assertAlmostEqual(sum(m.values()), 1.0, places=2)
        self.assertIn("*", vd.kokoro_voice_string(m))

    def test_ffmpeg_and_parler(self):
        s = vd.base_spec("adult")
        f = vd.build_ffmpeg_filter(s)
        self.assertIn("asetrate=", f)
        self.assertIn("equalizer", f)
        self.assertIn("man", vd.parler_description(s))

    def test_no_backend(self):
        v = vd.VoiceDesigner(self.d, allow_noncommercial=False, installed={"silero_ru"})
        self.assertFalse(v.decide((0, 0, 0))["changed"])

    def test_night_softer(self):
        a, _ = vd.target_numbers((0, 0, 0), "adult", False)
        b, _ = vd.target_numbers((0, 0, 0), "adult", True)
        self.assertLess(b["rate"], a["rate"])


if __name__ == "__main__":
    unittest.main()
