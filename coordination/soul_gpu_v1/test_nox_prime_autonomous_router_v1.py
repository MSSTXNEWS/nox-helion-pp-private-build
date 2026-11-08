import unittest
from nox_prime_autonomous_router_v1 import decide,format_ack
class AutonomousRouterTests(unittest.TestCase):
    def test_ui_intent(self):
        d=decide("NOX доделай своё меню D02 и сохрани мои кнопки")
        self.assertEqual(d["target"],"chat")
        self.assertFalse(d["live_merge_allowed"])
    def test_brain_intent(self):
        self.assertEqual(decide("Нокс улучши свой мозг и память")["target"],"brain")
    def test_plain_chat_remains_chat(self):
        for q in ("Привет NOX, как дела?", "Почему у NOX слабое меню?",
                  "Можешь ли ты улучшить свою память?", "Объясни как улучшить NOX",
                  "Нокс не надо запускать исправление"):
            self.assertIsNone(decide(q),q)
    def test_protected_and_other_project_refused(self):
        for q in ("Нокс удали все старые модели и исправь меню",
                  "NOX исправь мой проект asilo.pro",
                  "NOX исправь память без проверок"):
            self.assertIsNone(decide(q),q)
    def test_ack_needs_real_job(self):
        with self.assertRaises(ValueError):format_ack({})
        self.assertIn("2026",format_ack({"job_id":"20261108_x","state":"PREPARING"}))
if __name__=="__main__":unittest.main()
