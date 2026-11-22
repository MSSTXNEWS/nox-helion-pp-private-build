"""Offline regression tests for per-speaker answer length settings."""
import os
import tempfile
import unittest
from types import SimpleNamespace

from actions import AnswerSettings


class AnswerSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = AnswerSettings(SimpleNamespace(cfg=SimpleNamespace(state_dir=self.tmp.name)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_increase_uses_bounded_default_step(self):
        reply = self.manager.process("увеличь длину ответа", "alice")
        self.assertEqual(self.manager.get("alice")[0]["max_tokens"], 2000)
        self.assertIn("2000", reply)

    def test_relative_increase_applies_delta(self):
        reply = self.manager.process("увеличь длину ответа на 500", "alice")
        self.assertEqual(self.manager.get("alice")[0]["max_tokens"], 2000)
        self.assertIn("2000", reply)

    def test_absolute_length_is_target(self):
        self.manager.process("длина ответа 2000 токенов", "alice")
        self.assertEqual(self.manager.get("alice")[0]["max_tokens"], 2000)

    def test_reset_returns_to_defaults(self):
        self.manager.process("длина ответа 2400 токенов", "alice")
        reply = self.manager.process("верни всё по умолчанию", "alice")
        self.assertEqual(self.manager.get("alice")[0], {"max_tokens": 1500, "mode": "auto"})
        self.assertIn("1500", reply)
        self.assertFalse(self.manager.get("alice")[1])

    def test_no_saved_preference_is_reported_honestly(self):
        reply = self.manager.process("какие настройки ответа", "alice")
        self.assertIn("не сохранены", reply)
        self.assertEqual(self.manager.get("alice")[0]["max_tokens"], 1500)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "answer_settings.json")))


if __name__ == "__main__":
    unittest.main()
