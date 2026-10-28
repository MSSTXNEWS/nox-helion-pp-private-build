"""P04 original Python-host RAG: strict on-disk index JSON regression.

Local stdlib fixtures only. NO Ollama call, new DB, model download, GPU or EXE.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

WORKER = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "rag_python_compat.py"
spec = importlib.util.spec_from_file_location("nox_p04_existing_rag", WORKER)
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)

OWNER = "S-1-5-21-1100"


class RagIndexStrictJsonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nox-rag-index.json"
        self.index = rag.LocalRag("http://127.0.0.1:11434", "fixture-embed", self.path)

    def write(self, value: str) -> str:
        self.path.write_text(value, encoding="utf-8")
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def valid_root(self) -> str:
        return json.dumps({
            "schema": rag.INDEX_SCHEMA,
            "model": "fixture-embed",
            "vectorDimensions": 0,
            "sources": []
        }, separators=(",", ":"))

    def reject_unchanged(self, value: str, code: str) -> None:
        digest = self.write(value)
        with self.assertRaisesRegex(rag.RagHold, code):
            self.index._read()
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), digest)

    def test_existing_valid_empty_index_is_accepted(self):
        self.write(self.valid_root())
        result = self.index._read()
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["model"], "fixture-embed")
        self.assertFalse(self.index.delete_source(OWNER, "c1", "missing"))

    def test_duplicate_top_level_key_is_rejected(self):
        self.reject_unchanged(
            '{"schema":"NOX-RAG-INDEX-v1","schema":"NOX-RAG-INDEX-v1",'
            '"model":"fixture-embed","vectorDimensions":0,"sources":[]}',
            "RAG_INDEX_DUPLICATE_JSON_KEY",
        )

    def test_ambiguous_other_owner_nested_sid_is_rejected(self):
        # A duplicate ownerSid can be interpreted differently by two runtimes.
        self.reject_unchanged(
            '{"schema":"NOX-RAG-INDEX-v1","model":"fixture-embed",'
            '"vectorDimensions":0,"sources":[{"ownerSid":"S-1-5-21-9999",'
            '"ownerSid":"S-1-5-21-1100","conversationId":"c1",'
            '"sourceId":"source","chunks":[]}]}',
            "RAG_INDEX_DUPLICATE_JSON_KEY",
        )

    def test_duplicate_chunk_provenance_is_rejected(self):
        self.reject_unchanged(
            '{"schema":"NOX-RAG-INDEX-v1","model":"fixture-embed",'
            '"vectorDimensions":0,"sources":[{"ownerSid":"S-1-5-21-1100",'
            '"conversationId":"c1","sourceId":"s1","chunks":['
            '{"chunkIndex":0,"chunkSha256":"a",'
            '"chunkSha256":"b","text":"sample","vector":[]}]}]}',
            "RAG_INDEX_DUPLICATE_JSON_KEY",
        )

    def test_nan_in_unrelated_scope_is_rejected(self):
        self.reject_unchanged(
            self.valid_root()[:-1] + ',"untrustedMetric":NaN}',
            "RAG_INDEX_NONFINITE_NUMBER",
        )

    def test_infinity_and_negative_infinity_rejected(self):
        for value in ("Infinity", "-Infinity"):
            with self.subTest(value=value):
                self.reject_unchanged(
                    self.valid_root()[:-1] + ',"metric":' + value + '}',
                    "RAG_INDEX_NONFINITE_NUMBER",
                )

    def test_exponent_overflow_is_rejected(self):
        self.reject_unchanged(
            self.valid_root()[:-1] + ',"metric":1e9999}',
            "RAG_INDEX_NONFINITE_NUMBER",
        )

    def test_legitimate_string_with_nan_text_is_not_rejected(self):
        self.write(self.valid_root()[:-1] + ',"note":"NaN, Infinity and \\"quoted\\""}')
        self.assertEqual(self.index._read()["sources"], [])

    def test_malformed_json_returns_existing_hold(self):
        self.reject_unchanged('{"schema":', "RAG_INDEX_INVALID_JSON")

    def test_deep_json_returns_existing_hold_not_recursion_crash(self):
        deep = "[" * 1300 + "0" + "]" * 1300
        self.reject_unchanged(deep, "RAG_INDEX_INVALID_JSON")

    def test_no_false_index_creation_when_missing(self):
        self.assertEqual(self.index._read()["sources"], [])
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
