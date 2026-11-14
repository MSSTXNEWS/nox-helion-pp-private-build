"""Actual P04 module regression: file-import fd/path provenance consistency.

Synthetic metadata changes are test fixtures, NOT physical race-free Windows
handle proofs. No Ollama, GPU, network calls, or model downloads.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "rag_python_compat.py"
spec = importlib.util.spec_from_file_location("p04_rag_file_consistency", SOURCE)
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)

OWNER = "S-1-5-21-1100"


class RagImportConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "file.md"
        self.source.write_text("alpha original source", encoding="utf-8")
        self.index_path = self.root / "rag-index.json"
        self.index = rag.LocalRag("http://127.0.0.1:11434/", "fixture-embed",
                                  self.index_path)

    def _metadata_switch(self, **updates):
        """Return a stat hook that changes only the post-open pathname snapshot."""
        real_stat = os.stat

        def changed(path, *args, **kwargs):
            original = real_stat(path, *args, **kwargs)
            if (isinstance(path, (str, os.PathLike))
                    and Path(path) == self.source
                    and kwargs.get("follow_symlinks") is False):
                keys = ("st_mode", "st_size", "st_mtime_ns", "st_dev", "st_ino")
                fields = {key: getattr(original, key) for key in keys}
                fields.update(updates)
                return types.SimpleNamespace(**fields)
            return original

        return changed

    def _assert_import_denied_without_embedding(self, changed):
        with mock.patch.object(rag.os, "stat", side_effect=changed):
            with mock.patch.object(self.index, "_embeddings",
                                   side_effect=AssertionError("must not embed")):
                with self.assertRaisesRegex(rag.RagHold,
                                            "RAG_FILE_CHANGED_DURING_READ"):
                    self.index.ingest_file(OWNER, "chat-1", self.source)
        self.assertFalse(self.index_path.exists(), "Denied import must not be indexed")

    def test_stable_regular_file_still_ingests_searches_and_deletes(self):
        with mock.patch.object(self.index, "_embeddings", return_value=[[1.0, 0.0]]):
            receipt = self.index.ingest_file(OWNER, "chat-1", self.source)
            self.assertEqual(receipt["indexed_chunks"], 1)
            self.assertEqual(len(receipt["sha256"]), 64)
            hits = self.index.search(OWNER, "chat-1", "alpha")
            self.assertEqual(len(hits), 1)
            self.assertIn("alpha", hits[0]["text"])
        self.assertTrue(self.index.delete_source(OWNER, "chat-1", receipt["source_id"]))

    def test_simulated_mtime_change_after_open_blocks_provenance(self):
        old = self.source.stat()
        self._assert_import_denied_without_embedding(
            self._metadata_switch(st_mtime_ns=old.st_mtime_ns + 1))

    def test_simulated_size_change_after_open_blocks_provenance(self):
        old = self.source.stat()
        self._assert_import_denied_without_embedding(
            self._metadata_switch(st_size=old.st_size + 1))

    def test_simulated_replacement_with_nonregular_path_blocks_provenance(self):
        self._assert_import_denied_without_embedding(
            self._metadata_switch(st_mode=stat.S_IFLNK))

    def test_simulated_inode_swap_blocks_provenance_when_supported(self):
        old = self.source.stat()
        if not old.st_ino:
            self.skipTest("filesystem does not expose a stable inode")
        self._assert_import_denied_without_embedding(
            self._metadata_switch(st_ino=old.st_ino + 1))


if __name__ == "__main__":
    unittest.main()
