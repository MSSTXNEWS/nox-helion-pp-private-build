from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).with_name("owner_smart_chat_acceptance.py")
SPEC = importlib.util.spec_from_file_location("owner_smart_chat_acceptance", SOURCE)
assert SPEC and SPEC.loader
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class MissingModuleDiagnosticTests(unittest.TestCase):
    def test_returns_only_valid_python_module_identifier(self):
        error = ModuleNotFoundError("message may contain paths and must not be copied")
        error.name = "fastapi.responses"
        self.assertEqual(QA.safe_missing_module_name(error), "fastapi.responses")
        self.assertNotIn("message may contain paths", QA.safe_missing_module_name(error))

    def test_rejects_path_like_malformed_and_unbounded_names(self):
        for value in (None, "", "../secret", "foo bar", "foo;bar", 7, "x" * 201):
            error = ModuleNotFoundError("opaque")
            error.name = value
            with self.subTest(value=value):
                self.assertIsNone(QA.safe_missing_module_name(error))

    def test_rejects_too_many_dotted_segments(self):
        error = ModuleNotFoundError("opaque")
        error.name = ".".join(["x"] * 17)
        self.assertIsNone(QA.safe_missing_module_name(error))

    def test_ignores_other_exceptions(self):
        self.assertIsNone(QA.safe_missing_module_name(ImportError("private path")))


if __name__ == "__main__":
    unittest.main()
