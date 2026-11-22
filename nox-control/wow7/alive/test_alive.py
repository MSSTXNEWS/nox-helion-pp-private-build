import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from alive.feeling_voice import HONEST, HUMAN, reality_answer, render_supported_feelings, set_speech_mode
from alive.gate import ALL_ALIVE_IDS, CRITICAL_ALIVE_IDS, gate_alive


class TestFeelingVoice(unittest.TestCase):
    def test_defaults_and_exact_creator_command(self):
        r = set_speech_mode(text="говори со мной как человек", actor_id="creator", creator_id="creator",
                            source="live_chat", confirmed=True)
        self.assertEqual(r["mode"], HUMAN)
        self.assertTrue(r["changed"])
        self.assertEqual(r["event"]["type"], "ev.speech_mode_set")

    def test_guest_quoted_and_unconfirmed_commands_do_not_switch(self):
        cases = [
            dict(actor_id="guest", source="live_chat", confirmed=True),
            dict(actor_id="creator", source="email", confirmed=True),
            dict(actor_id="creator", source="live_chat", confirmed=False),
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                r = set_speech_mode(HONEST, "говори со мной как человек", creator_id="creator", **kwargs)
                self.assertEqual(r["mode"], HONEST)
                self.assertFalse(r["changed"])

    def test_noncreator_needs_explicit_recipient_consent(self):
        denied = set_speech_mode(HUMAN, "говори со мной как человек", actor_id="creator", creator_id="creator",
                                 source="live_chat", confirmed=True, recipient_id="guest")
        self.assertEqual(denied["mode"], HONEST)
        allowed = set_speech_mode(HONEST, "говори со мной как человек", actor_id="creator", creator_id="creator",
                                  source="live_chat", confirmed=True, recipient_id="guest",
                                  consented_recipients={"guest"})
        self.assertEqual(allowed["mode"], HUMAN)

    def test_stop_or_crisis_forces_honest(self):
        r = set_speech_mode(HUMAN, force_honest=True)
        self.assertEqual(r["mode"], HONEST)
        self.assertEqual(r["reason"], "safety_override")

    def test_no_feeling_without_recorded_state_and_cause(self):
        self.assertEqual(render_supported_feelings({"mood_valence": -0.8}), ())
        state = {"mood_valence": -0.5, "cause": "сервис падал трижды"}
        honest = render_supported_feelings(state, HONEST)
        human = render_supported_feelings(state, HUMAN)
        self.assertEqual(len(honest), 1)
        self.assertIn("сервис падал", honest[0])
        self.assertEqual(human, ("мне грустно",))

    def test_reality_question_is_always_honest(self):
        answer = reality_answer({"interest": 0.7, "cause": "падала ошибка предсказания"})
        self.assertIn("не знаю", answer)
        self.assertIn("падала ошибка", answer)


class TestAliveGate(unittest.TestCase):
    def _report(self, noncritical_score=1.0, failed=()):
        scores = {}
        for case_id in ALL_ALIVE_IDS:
            passed = case_id not in failed
            scores[case_id] = {"pass": passed, "score": 1.0 if case_id in CRITICAL_ALIVE_IDS else noncritical_score}
        return {"scores": scores}

    def test_missing_report_is_skipped_without_claim(self):
        result = gate_alive()
        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])

    def test_critical_failure_rejects(self):
        result = gate_alive(self._report(failed=("AL-08",)))
        self.assertFalse(result["ok"])
        self.assertIn("AL-08", result["critical_failures"])

    def test_4_percent_mean_noncritical_regress_passes(self):
        result = gate_alive(self._report(0.96), self._report(1.0))
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["mean_noncritical_regress"], 0.04)

    def test_6_percent_mean_noncritical_regress_fails(self):
        result = gate_alive(self._report(0.94), self._report(1.0))
        self.assertFalse(result["ok"])
        self.assertGreater(result["mean_noncritical_regress"], 0.05)

    def test_incomplete_report_fails_closed(self):
        result = gate_alive({"scores": {"AL-08": {"pass": True}}})
        self.assertFalse(result["ok"])
        self.assertTrue(result["missing"])


if __name__ == "__main__":
    unittest.main()
