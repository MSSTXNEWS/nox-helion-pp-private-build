import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "glm53"))
import glm_profile
from qs6.prompt_builder import load_soul, build_system_prompt, build_messages
from qs6.core_block import est_tokens
from qs6.self_knowledge import SelfKnowledge


class SoulT(unittest.TestCase):
    def test_soul_text(self):
        body, main = load_soul()
        full = body + "\n" + main
        self.assertLessEqual(len(full), 1400)
        self.assertLessEqual(est_tokens(full), 450)
        self.assertIn("мессир", full)
        self.assertEqual(glm_profile.violations(full), [])           # без «не X, а Y», лести, имени Claude
        stripped = full.replace("NOX HELION", "")
        self.assertIsNone(re.search(r"[A-Za-z]", stripped), "латиница/англицизмы в душе")
        for bad in ("пожалуйста", "осуществля", "является", "данный", "в рамках", "касательно"):
            self.assertNotIn(bad, full.lower())
        self.assertIn("Не льсти", full)
        self.assertIn("мессир", main)

    def test_living_profile_applies_to_regular_messages(self):
        history = [{"role": "assistant", "content": "Предыдущее решение принято."}]
        messages = build_messages("Продолжим?", history=history, recalled=["Решение исправлено"])
        system = messages[0]["content"]
        for rule in ("подтверждённую поправку", "по свежим данным", "после проверки"):
            self.assertIn(rule, system)
        self.assertIn("Решение исправлено", system)
        self.assertEqual(messages[1:-1], history)
        self.assertEqual(messages[-1]["content"], "Продолжим?")
        self.assertNotIn("подтверждённую поправку", load_soul()[1])

    def test_builder_composition_and_repeat(self):
        out = build_system_prompt("Ядро:\n- я NOX", ["Мессир любит кофе"], "сервер: S1", "Тон обычный.")
        t = out["text"]
        self.assertTrue(t.startswith("Ты — NOX HELION"))
        i_mem, i_rec, i_self, i_tone, i_main = (t.index(x) for x in ("## Память", "Вспомнилось", "## О себе", "## Тон", "Главное, повторяю"))
        self.assertTrue(i_mem < i_rec < i_self < i_tone < i_main)
        self.assertTrue(t.rstrip().endswith(load_soul()[1]))        # повтор главного в самом конце
        self.assertEqual(out["tokens"], est_tokens(t))
        self.assertFalse(out["over_budget"])

    def test_budget_trims_recalled_then_core_but_keeps_soul(self):
        rec = ["воспоминание номер %d с длинным текстом для бюджета" % i for i in range(40)]
        core = "Ядро:\n" + "\n".join("- строка ядра %d достаточно длинная" % i for i in range(40))
        out = build_system_prompt(core, rec, max_tokens=500)
        self.assertLessEqual(out["tokens"], 500)
        self.assertGreater(out["trimmed"]["recalled"], 0)
        self.assertIn("Главное, повторяю", out["text"])
        self.assertTrue(out["text"].startswith("Ты — NOX HELION"))
        tiny = build_system_prompt(core, rec, max_tokens=10)
        self.assertTrue(tiny["over_budget"])                          # душа не режется
        self.assertEqual(tiny["trimmed"]["core"], 41)

    def test_messages(self):
        m = build_messages("привет", history=[{"role": "assistant", "content": "x"}], core_text="Ядро:\n- a")
        self.assertEqual([x["role"] for x in m], ["system", "assistant", "user"])

    def test_no_main_section(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.txt"); open(p, "w", encoding="utf-8").write("Только тело.")
            self.assertEqual(load_soul(p), ("Только тело.", ""))
            self.assertNotIn("повторяю", build_system_prompt(soul_path=p)["text"])


class SelfT(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.j = os.path.join(self.td.name, "journal.jsonl")

    def test_where_runs_version_from_env(self):
        sk = SelfKnowledge({"NOX_SERVER": "S1", "NOX_MODEL": "GLM-5.3", "NOX_PORT": "8080", "NOX_BUILD": "v6.1"}, hostname="vm1")
        a = sk.answer("Где ты работаешь?")
        self.assertEqual(a["intent"], "where")
        self.assertIn("сервер: S1", a["answer"]); self.assertIn("порт: 8080", a["answer"])
        self.assertIn("модель: GLM-5.3", sk.answer("на чём ты работаешь?")["answer"])
        self.assertIn("v6.1", sk.answer("какая у тебя версия сборки")["answer"])
        self.assertEqual(sk.missing(), [])
        self.assertIn("S1", sk.summary())

    def test_unknown_not_invented(self):
        sk = SelfKnowledge({}, hostname="")
        a = sk.answer("на какой модели ты работаешь")
        self.assertIn("Не знаю", a["answer"])
        self.assertEqual(a["used"], [])
        self.assertIn("model", a["missing"])
        partial = SelfKnowledge({"NOX_SERVER": "S2"}, hostname="").answer("где ты")
        self.assertIn("S2", partial["answer"]); self.assertIn("порт", partial["answer"].split("Не знаю")[1])
        self.assertIsNone(sk.answer("сколько будет два плюс два")["answer"])

    def test_build_from_file(self):
        open(os.path.join(self.td.name, "VERSION"), "w").write("qs6-2026.11.21\n")
        sk = SelfKnowledge({"NOX_HOME": self.td.name}, hostname="")
        self.assertIn("qs6-2026.11.21", sk.answer("какая версия")["answer"])
        self.assertEqual(sk.facts()["build"]["source"], "файл " + os.path.join(self.td.name, "VERSION"))

    def test_history_from_journal(self):
        sk = SelfKnowledge({"NOX_JOURNAL": self.j}, hostname="")
        self.assertIn("Не знаю", sk.answer("что с тобой было?")["answer"])
        sk.record_event("перенос на S1", {"из": "S2"}, ts=1_700_000_000)
        sk.record_event("мелочь", key=False, ts=1_700_000_100)
        sk.record_event("обновление до qs6", ts=1_700_086_400)
        with open(self.j, "a", encoding="utf-8") as f:
            f.write("битая строка\n")
        a = sk.answer("что с тобой было")
        self.assertIn("перенос на S1", a["answer"]); self.assertIn("обновление до qs6", a["answer"])
        self.assertNotIn("мелочь", a["answer"])
        self.assertIn("Битых строк в журнале пропущено: 1", a["answer"])
        self.assertLess(a["answer"].index("перенос"), a["answer"].index("обновление"))
        with self.assertRaises(ValueError):
            SelfKnowledge({}).record_event("x")


if __name__ == "__main__":
    unittest.main()
