import tempfile, unittest, os
import ui_mutator as U


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.t = [1000.0]
        self.m = U.UIMutator(self.d, clock=lambda: self.t[0])

    def test_whitelist_rejects(self):
        for bad in [{"vars": {"--evil": "1"}}, {"vars": {"--nox-accent": "url(http://x)"}},
                    {"vars": {"--nox-accent": "red"}}, {"vars": {"--nox-glow": 5}},
                    {"vars": {"--nox-accent": "#fff;}body{display:none"}}, {"vars": {"--nox-radius": "10px;x"}},
                    {"animation": {"name": "spin", "period_s": 3}}, {"animation": {"name": "pulse", "period_s": 0.1}},
                    {"selector": "body"}, {}, {"vars": {"--nox-glow": True}}]:
            with self.assertRaises(U.Rejected, msg=str(bad)):
                U.validate(bad)

    def test_normalize(self):
        n = U.validate({"vars": {"--nox-accent": "hsl(40, 60%, 55%)", "--nox-radius": 12, "--nox-glow": 0.5}})
        self.assertTrue(n["vars"]["--nox-accent"].startswith("#"))
        self.assertEqual(n["vars"]["--nox-radius"], "12px")

    def test_contrast_blocks_unreadable(self):
        r = self.m.propose({"vars": {"--nox-text": "#101010"}}, "хочу темнее")
        self.assertEqual(r["status"], "rejected")
        self.assertIn("контраст", r["error"])

    def test_reason_required(self):
        self.assertEqual(self.m.propose({"vars": {"--nox-glow": 0.5}}, " ")["status"], "rejected")

    def test_minor_applies_as_trial_and_autorollback(self):
        r = self.m.propose({"vars": {"--nox-glow": 0.5}}, "мягче свечение к вечеру")
        self.assertEqual(r["status"], "applied_trial")
        self.assertIn("--nox-glow: 0.5", open(self.m.css_path).read())
        self.t[0] += 100
        self.assertEqual(self.m.tick()["status"], "idle")
        self.t[0] += U.TRIAL_TTL_S
        self.assertEqual(self.m.tick()["status"], "auto_rolled_back")
        self.assertNotIn("--nox-glow", open(self.m.css_path).read().split("@keyframes")[0])

    def test_confirm_keeps(self):
        self.m.propose({"vars": {"--nox-glow": 0.5}}, "x")
        self.assertEqual(self.m.confirm()["status"], "confirmed")
        self.t[0] += 5000
        self.assertEqual(self.m.tick()["status"], "idle")
        self.assertEqual(self.m.st["vars"]["--nox-glow"], "0.5")

    def test_global_needs_owner(self):
        r = self.m.propose({"theme": "FORGE", "vars": {"--nox-bg": "#101820"}}, "азарт мастерства")
        self.assertEqual(r["status"], "pending_owner")
        self.assertEqual(self.m.st["vars"], {})
        self.assertIn("Мессир", r["ask"])
        a = self.m.approve(r["id"])
        self.assertEqual(a["status"], "applied")
        self.assertEqual(self.m.st["vars"]["--nox-bg"], "#101820")

    def test_owner_reject(self):
        r = self.m.propose({"vars": {"--nox-radius": 24}}, "острее")
        self.assertEqual(r["status"], "pending_owner")
        self.assertEqual(self.m.reject(r["id"])["status"], "rejected")
        self.assertEqual(self.m.st["pending"], [])

    def test_big_hue_shift_is_global(self):
        r = self.m.propose({"vars": {"--nox-accent": "#2040d0"}}, "хочу синий")
        self.assertEqual(r["status"], "pending_owner")

    def test_rollback_chain_and_reset(self):
        self.m.propose({"vars": {"--nox-glow": 0.5}}, "a")
        self.m.confirm()
        self.m.propose({"vars": {"--nox-blur": 12}}, "b")
        self.m.confirm()
        self.assertEqual(self.m.rollback()["status"], "rolled_back")
        self.assertNotIn("--nox-blur", self.m.st["vars"])
        self.assertIn("--nox-glow", self.m.st["vars"])
        self.m.reset()
        self.assertEqual(self.m.st["vars"], {})

    def test_one_trial_at_a_time(self):
        self.m.propose({"vars": {"--nox-glow": 0.5}}, "a")
        self.assertEqual(self.m.propose({"vars": {"--nox-blur": 12}}, "b")["status"], "rejected")

    def test_animation_rendered_and_persisted(self):
        self.m.propose({"animation": {"name": "breathe", "period_s": 8}}, "дыхание сцены")
        self.assertIn("nox-breathe 8.0s", open(self.m.css_path).read())
        m2 = U.UIMutator(self.d)
        self.assertEqual(m2.st["animation"]["name"], "breathe")

    def test_journal_has_why(self):
        self.m.propose({"vars": {"--nox-glow": 0.5}}, "причина-тест")
        from selfcommon import journal_read
        self.assertTrue(any(r.get("why") == "причина-тест" for r in journal_read(self.m.journal_path)))

    def test_dry_run_no_write(self):
        r = self.m.propose({"vars": {"--nox-glow": 0.5}}, "x", dry_run=True)
        self.assertEqual(r["status"], "dry_run")
        self.assertFalse(os.path.exists(self.m.state_path))


if __name__ == "__main__":
    unittest.main()
