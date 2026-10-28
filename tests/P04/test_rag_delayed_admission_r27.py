"""Actual LocalRag file-index lifecycle tests; embedding delay is deterministic."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "Packages/P04/rag_python_compat.py"
spec = importlib.util.spec_from_file_location("rag_delayed_admission_r27", SOURCE)
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)
OWNER = "S-1-5-21-1100"
OTHER = "S-1-5-21-2200"


class DelayedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.index = rag.LocalRag("http://127.0.0.1:11434", "fixture",
                                 Path(self.temp.name) / "index.json")
        self.put("original private knowledge")

    def put(self, text, owner=OWNER, source="source1"):
        with patch.object(self.index, "_embeddings", return_value=[[1.0, 0.0]]):
            return self.index.ingest_text(owner, "chat", source, "source.md", text)

    def read(self):
        with patch.object(self.index, "_embeddings", return_value=[[1.0, 0.0]]):
            return self.index.search(OWNER, "chat", "query")

    def delayed(self, action):
        def embed(_values):
            action()
            return [[1.0, 0.0]]
        return patch.object(self.index, "_embeddings", side_effect=embed)

    def test_search_does_not_publish_deleted_source_after_embedding(self):
        with self.delayed(lambda: self.index.delete_source(OWNER, "chat", "source1")):
            self.assertEqual(self.index.search(OWNER, "chat", "query"), [])

    def test_search_reloads_updated_source_after_embedding(self):
        with self.delayed(lambda: self.put("current replacement knowledge")):
            hits = self.index.search(OWNER, "chat", "query")
        self.assertEqual([h["text"] for h in hits], ["current replacement knowledge"])

    def test_pending_upsert_does_not_resurrect_deleted_source(self):
        with self.delayed(lambda: self.index.delete_source(OWNER, "chat", "source1")):
            with self.assertRaisesRegex(rag.RagHold, "RAG_SOURCE_CHANGED_DURING_EMBEDDING"):
                self.index.ingest_text(OWNER, "chat", "source1", "source.md", "stale update")
        self.assertEqual(self.read(), [])

    def test_pending_upsert_does_not_overwrite_newer_source(self):
        with self.delayed(lambda: self.put("newer concurrent knowledge")):
            with self.assertRaisesRegex(rag.RagHold, "RAG_SOURCE_CHANGED_DURING_EMBEDDING"):
                self.index.ingest_text(OWNER, "chat", "source1", "source.md", "stale update")
        self.assertEqual([h["text"] for h in self.read()], ["newer concurrent knowledge"])

    def test_unrelated_owner_write_does_not_block_current_upsert(self):
        with self.delayed(lambda: self.put("other owner", OTHER)):
            receipt = self.index.ingest_text(OWNER, "chat", "source1", "source.md", "fresh update")
        self.assertFalse(receipt["unchanged"])
        self.assertEqual([h["text"] for h in self.read()], ["fresh update"])

    def test_p02_callback_does_not_return_context_after_owner_revoked(self):
        sid = [OWNER]
        callback = rag.p02_callback(self.index, lambda _t, _p: sid[0])
        with self.delayed(lambda: sid.__setitem__(0, OTHER)):
            with self.assertRaisesRegex(rag.RagHold, "RAG_OWNER_CHANGED_DURING_CONTEXT"):
                callback("tenant", "principal", "chat", "query")

    def test_p02_stable_owner_still_returns_verified_context(self):
        callback = rag.p02_callback(self.index, lambda _t, _p: OWNER)
        with patch.object(self.index, "_embeddings", return_value=[[1.0, 0.0]]):
            result = callback("tenant", "principal", "chat", "query")
        self.assertIn("original private knowledge", result["context"])
        self.assertTrue(result["sources"][0]["verified"])


if __name__ == "__main__":
    unittest.main()
