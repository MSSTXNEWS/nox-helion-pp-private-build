#!/usr/bin/env python3
"""Regression: live Resonance must not silently clip the current owner turn.

Source-only. Extracts the pure prompt builder to avoid importing native GPU,
S03 or bridge services; it does not certify deployed inference or S03 readback.
"""
import ast
import unittest
from pathlib import Path


def _load_builder():
    source = Path(__file__).with_name("nox_bridge.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    builder = next(node for node in module.body
                   if isinstance(node, ast.FunctionDef) and node.name == "build_msgs")
    ns = {"_style": lambda: "", "IDENTITY": "NOX", "STATIC_RULES": " rules"}
    exec(compile(ast.Module(body=[builder], type_ignores=[]),
                 "nox_bridge.py", "exec"), ns)
    return ns["build_msgs"]


class FullCurrentTurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = staticmethod(_load_builder())

    def test_current_very_long_user_message_is_byte_equivalent(self):
        user = "Пожалуйста, проанализируй весь ввод. " + "RU ES 🌍 " * 350 + " FINAL_OWNER_INSTRUCTION_9c2d"
        history = [
            {"role": "user", "content": "Первый вопрос"},
            {"role": "assistant", "content": "Первый ответ"},
            {"role": "user", "content": user},
        ]
        out = self.build(history, user, "", "Эмоция: спокойствие")
        self.assertEqual(out[-1]["role"], "user")
        self.assertTrue(out[-1]["content"].endswith(user))
        self.assertEqual(out[-1]["content"].count("FINAL_OWNER_INSTRUCTION_9c2d"), 1)
        self.assertIn("Первый ответ", out[-2]["content"])

    def test_current_unchanged_without_history(self):
        user = "u" * 2000 + " END"
        out = self.build([], user, "", "")
        self.assertTrue(out[-1]["content"].endswith(user))

    def test_all_prior_context_is_kept_byte_exact_without_hidden_window(self):
        # Source-only: model context capacity and S03 persistence are not proven.
        history = []
        for i in range(8):
            history.extend([{"role": "user", "content": f"past-{i}-🌍" + "Ю" * 1600},
                            {"role": "assistant", "content": f"answer-{i}-✅" + "A" * 1100}])
        user = "latest full request"
        history.append({"role": "user", "content": user})
        out = self.build(history, user, "", "")
        self.assertEqual(len(out), len(history) + 1)
        for i, message in enumerate(history[:-1], 1):
            self.assertEqual(out[i], message)
        self.assertTrue(out[-1]["content"].endswith(user))


    def test_recalled_memory_is_not_silently_sliced_to_500_chars(self):
        memory = "Источник S03: " + ("важный полный контекст 🌍" * 80) + "\\nПроверенный хвост 9b82"
        user = "Учитывай всю подтверждённую память"
        out = self.build([{"role": "user", "content": user}], user, memory, "")
        self.assertIn("Память: " + memory + "\\n", out[-1]["content"])
        self.assertEqual(out[-1]["content"].count("Проверенный хвост 9b82"), 1)

    def test_s03_memory_admission_preserves_full_unicode_and_holds_on_overflow(self):
        source = Path(__file__).with_name("nox_bridge.py").read_text(encoding="utf-8")
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == "trim_mem")
        env = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     "nox_bridge.py", "exec"), env)
        admit = env["trim_mem"]
        data = ("М1 — память 🌍 и источник\\n" * 900) + "Завершение ✔"
        self.assertEqual(admit(data), data)
        with self.assertRaisesRegex(ValueError, "S03_MEMORY_CONTEXT_OVER_BUDGET"):
            admit("п" * 17000)
        with self.assertRaisesRegex(TypeError, "S03_MEMORY_FORMAT_NON_TEXT"):
            admit(["wrong", "type"])


if __name__ == "__main__":
    unittest.main()
