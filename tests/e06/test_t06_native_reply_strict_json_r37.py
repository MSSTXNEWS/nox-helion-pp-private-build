"""MB3/R37: original T06 frozen-native source/EXE/P03 replies must be unambiguous.

Importing the builder would extract the original archive and start Windows
processes. Extract the exact committed function AST instead; this is a focused
source-level regression, NOT a Windows IPC or independent E07 acceptance.
"""
from __future__ import annotations
import ast
import json
from pathlib import Path
import unittest

BUILDER = Path(__file__).resolve().parents[2] / "coordination/e06/t06_native_proven_builder.py"


def parser_from_original_source():
    source = BUILDER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(BUILDER))
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == "strict_native_json"]
    if len(nodes) != 1:
        raise AssertionError("one original T06 native JSON parser required")
    namespace = {"json": json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(BUILDER), "exec"), namespace)
    return namespace["strict_native_json"], source


class T06NativeReplyStrictJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parse, cls.builder_source = parser_from_original_source()

    def test_valid_explicit_response_preserved(self):
        reply = self.parse(
            b'{"protocol":"NOX-P02-NATIVE-v1","status":"HOLD","errorCode":"NATIVE_PROVIDER_HOLD"}',
            "T06_UNTRUSTED_NATIVE_JSON")
        self.assertEqual(reply["status"], "HOLD")
        self.assertEqual(reply["errorCode"], "NATIVE_PROVIDER_HOLD")

    def test_duplicate_native_reply_keys_rejected_at_all_depths(self):
        for raw in (
            b'{"status":"OK","status":"HOLD"}',
            b'{"runId":"one","runId":"two"}',
            b'{"result":{"models":[],"models":["spoof"]}}',
        ):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                self.parse(raw, "T06_UNTRUSTED_NATIVE_JSON")

    def test_nonfinite_invalid_utf8_and_truncated_reply_rejected(self):
        for raw in (
            b'{"status":"OK","value":NaN}',
            b'{"status":"OK","value":Infinity}',
            b'{"status":"OK","value":-Infinity}',
            b'{"status":"OK"', b"\\xff",
        ):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                self.parse(raw, "T06_UNTRUSTED_NATIVE_JSON")

    def test_nonobject_frame_rejected(self):
        for raw in (b"null", b"[]", b'"OK"', b"true"):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                self.parse(raw, "T06_UNTRUSTED_NATIVE_JSON")

    def test_exact_three_native_source_exe_and_p03_acceptance_calls(self):
        for call in (
            'response=strict_native_json(stdout[4:],"T06_NATIVE_ORIGINAL_RESPONSE_JSON_HOLD")',
            'answer=strict_native_json(raw_reply[4:],"T06_NATIVE_PYTHON_EXE_RESPONSE_JSON_HOLD")',
            'p03_answer=strict_native_json(p03_result.stdout[4:],"T06_FROZEN_MODEL_CENTER_JSON_HOLD")',
        ):
            with self.subTest(call=call):
                self.assertIn(call, self.builder_source)
        self.assertEqual(self.builder_source.count("strict_native_json("), 4)


if __name__ == "__main__":
    unittest.main()
