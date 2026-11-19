"""Source-only tests for dynamic NOX proxy inspection."""
from __future__ import annotations

import json
import unittest

from nox_runpod.teacher_mesh.v76 import proxy_source_inspect_v2 as probe


def analyzer():
    namespace = {}
    exec(compile(probe.ANALYZER, "<proxy-source-analyzer>", "exec"), namespace)
    return namespace["analyze_source"]


class ProxySourceInspectTests(unittest.TestCase):
    def test_reports_context_functions_and_constant_slice_bounds_only(self):
        raw = b'''
API_KEY = "DO_NOT_PRINT_THIS_SECRET"
def _trim_ctx(messages):
    return messages[-16:]
def _build_messages(body):
    prompt = body["prompt"][:8000]
    return prompt
def prepare_payload(messages):
    return messages
def route(body):
    return prepare_payload(_trim_ctx(_build_messages(body)))
'''
        report = analyzer()(raw)
        self.assertEqual(report["source_bytes"], len(raw))
        self.assertEqual(report["functions"]["_trim_ctx"][0]["constant_slice_bounds"][0]["lower"], -16)
        self.assertEqual(report["functions"]["_build_messages"][0]["constant_slice_bounds"][0]["upper"], 8000)
        self.assertEqual(report["functions"]["prepare_payload"][0]["line"], 8)
        self.assertTrue(report["callsites"]["prepare_payload"])
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("DO_NOT_PRINT_THIS_SECRET", encoded)
        self.assertNotIn("prompt", encoded)
        self.assertIn("AST-only", report["analysis_note"])

    def test_missing_context_functions_are_explicitly_reported(self):
        report = analyzer()(b"def health():\\n    return True\\n")
        self.assertEqual(report["functions"]["_trim_ctx"], [])
        self.assertEqual(report["functions"]["_build_messages"], [])
        self.assertEqual(report["functions"]["prepare_payload"], [])

    def test_rejects_oversized_source(self):
        with self.assertRaisesRegex(ValueError, "HOLD_PROXY_SOURCE_SIZE"):
            analyzer()(b"x" * (probe.MAX_SOURCE_BYTES + 1))

    def test_rejects_invalid_source_without_echoing_contents(self):
        with self.assertRaisesRegex(ValueError, "HOLD_PROXY_SOURCE_PARSE"):
            analyzer()(b'password = "sensitive"\\ndef broken(:\\n')


if __name__ == "__main__":
    unittest.main()
