import unittest, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_profile as P
class T(unittest.TestCase):
    def test_effort(self):
        self.assertEqual(P.pick_effort("привет"), "low")
        self.assertEqual(P.pick_effort("напиши функцию на python"), "max")
        self.assertEqual(P.pick_effort("сравни два подхода и объясни почему"), "high")
        self.assertEqual(P.pick_effort("x", "ultra"), "high")     # G03: неверное значение не включает max
        self.assertEqual(P.pick_effort("x", "low"), "low")
    def test_build(self):
        b, e = P.build_request({"messages": [{"role": "user", "content": "привет"}], "max_tokens": 10})
        self.assertEqual(e, "low"); self.assertGreaterEqual(b["max_tokens"], 2048)
        self.assertEqual(b["temperature"], 1.0); self.assertEqual(b["min_p"], 0.01); self.assertTrue(b["cache_prompt"])
        self.assertEqual(b["messages"][0]["role"], "system"); self.assertIn("Напоминание", b["messages"][-1]["content"])
        self.assertEqual(b["chat_template_kwargs"]["reasoning_effort"], "low")
    def test_history(self):
        h = [{"role": "assistant", "content": "<think>x</think>ответ", "reasoning_content": "r"}, {"role": "user", "content": "q"}]
        self.assertEqual(P.clean_history(h, False)[0]["content"], "ответ"); self.assertNotIn("reasoning_content", P.clean_history(h, False)[0])
        self.assertIn("reasoning_content", P.clean_history(h, True)[0])
    def test_violations(self):
        self.assertIn("not_x_but_y", P.violations("Это не ошибка, а особенность"))
        self.assertIn("names_self_claude", P.violations("Я — Claude"))
        self.assertIn("flattery_opener", P.violations("Отличный вопрос! Да."))
        self.assertEqual(P.violations("Нормальный ответ."), [])
    def test_length(self):
        r = P.length_check("напиши ровно 3 слова", "один два три"); self.assertTrue(r["ok"])
        self.assertFalse(P.length_check("в 5 предложениях", "Раз. Два.")["ok"])
    def test_post(self):
        r = P.postprocess({"choices": [{"message": {"content": "<think>x</think>Привет"}}]}, "привет")
        self.assertEqual(r["nox"]["memory_text"], "Привет")
    def test_misc(self):
        self.assertIn("Цель:", P.task_prompt("g", ["a"])); self.assertIn("- f1", P.compact_facts(["f1"]))
if __name__ == "__main__": unittest.main()
