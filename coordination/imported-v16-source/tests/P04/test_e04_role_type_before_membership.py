"""Fail-closed tests for malformed JSON message-role shapes in existing P04 worker.

Run: python tests/P04/test_e04_role_type_before_membership.py
No GPU or weights are used; this does not prove any training run.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


WORKER = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
SPEC = importlib.util.spec_from_file_location("nox_p04_role_guard_under_test", WORKER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MessageRoleTypeGate(unittest.TestCase):
    def check(self, record, expected=None):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "fixture.jsonl"
            path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            if expected is None:
                with self.assertRaisesRegex(ValueError, "TRAIN_INVALID_MESSAGE_1"):
                    MODULE.validate_jsonl(path, "TRAIN")
            else:
                self.assertEqual(MODULE.validate_jsonl(path, "TRAIN"), expected)

    @staticmethod
    def messages(role):
        return {"messages": [
            {"role": "user", "content": "question"},
            {"role": role, "content": "answer"},
        ]}

    def test_role_json_array_rejected_without_raw_typeerror(self):
        self.check(self.messages(["assistant"]))

    def test_role_json_object_rejected_without_raw_typeerror(self):
        self.check(self.messages({"value": "assistant"}))

    def test_role_integer_rejected(self):
        self.check(self.messages(1))

    def test_role_boolean_rejected(self):
        self.check(self.messages(True))

    def test_role_null_rejected(self):
        self.check(self.messages(None))

    def test_unknown_role_string_rejected(self):
        self.check(self.messages("trainer"))

    def test_missing_role_rejected(self):
        self.check({"messages": [{"role": "user", "content": "q"}, {"content": "answer"}]})

    def test_valid_assistant_dialogue_remains_accepted(self):
        self.check(self.messages("assistant"), 1)

    def test_valid_text_record_remains_accepted(self):
        self.check({"text": "approved textual sample"}, 1)


if __name__ == "__main__":
    unittest.main()
