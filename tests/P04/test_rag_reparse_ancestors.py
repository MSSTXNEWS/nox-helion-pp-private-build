"""P04 original-module regression for ancestor symlink / Windows reparse paths.

No Ollama/model downloads, CUDA, privileged operations or external network.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "rag_python_compat.py"
spec = importlib.util.spec_from_file_location("nox_p04_guarded_rag", SOURCE)
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)
SID = "S-1-5-21-1100"


class RagReparseAncestorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def index(self, path):
        return rag.LocalRag("http://127.0.0.1:11434/", "fixture-embed", path)

    def test_regular_index_still_ingests_cites_updates_and_deletes(self):
        item = self.index(self.root / "safe" / "index.json")
        with mock.patch.object(item, "_embeddings", return_value=[[1., 0., 0.]]):
            first = item.ingest_text(SID, "c1", "s1", "notes.md", "alpha")
            self.assertFalse(first["unchanged"])
            self.assertEqual(item.context(SID, "c1", "alpha")["sources"][0]["source_id"], "s1")
            item.ingest_text(SID, "c1", "s1", "notes.md", "updated alpha")
            self.assertTrue(item.delete_source(SID, "c1", "s1"))
            self.assertEqual(item.search(SID, "c1", "alpha"), [])

    def test_reparse_parent_is_denied_before_index_directory_creation(self):
        outside = self.root / "outside"
        outside.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("native symlinks not available")
        item = self.index(alias / "not-created" / "index.json")
        with mock.patch.object(item, "_embeddings", return_value=[[1., 0., 0.]]):
            with self.assertRaisesRegex(rag.RagHold, "RAG_ANCESTOR_REPARSE_BLOCKED"):
                item.ingest_text(SID, "c1", "s1", "notes.md", "alpha")
        self.assertFalse((outside / "not-created").exists())

    def test_index_file_symlink_is_denied(self):
        outside = self.root / "outside.txt"
        outside.write_text("untouched", encoding="utf-8")
        link = self.root / "index.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("native symlinks not available")
        with self.assertRaisesRegex(rag.RagHold, "RAG_INDEX_SYMLINK"):
            with self.index(link)._locked():
                pass
        self.assertEqual(outside.read_text(encoding="utf-8"), "untouched")

    def test_import_file_ancestor_link_is_denied_before_read(self):
        source = self.root / "outside"
        source.mkdir()
        (source / "notes.md").write_text("private", encoding="utf-8")
        alias = self.root / "alias"
        try:
            alias.symlink_to(source, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("native symlinks not available")
        item = self.index(self.root / "index.json")
        with mock.patch.object(item, "_embeddings", return_value=[[1., 0., 0.]]):
            with self.assertRaisesRegex(rag.RagHold, "RAG_ANCESTOR_REPARSE_BLOCKED"):
                item.ingest_file(SID, "c1", alias / "notes.md")
        self.assertFalse((self.root / "index.json").exists())

    def test_windows_reparse_flag_is_denied_even_without_symlink(self):
        target = self.root / "junction"
        target.mkdir()
        candidate = target / "index.json"
        original = Path.lstat
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        with mock.patch.object(rag.stat, "FILE_ATTRIBUTE_REPARSE_POINT", flag, create=True):
            def fake_lstat(path, *args, **kwargs):
                if path == target:
                    return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=flag)
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaisesRegex(rag.RagHold, "RAG_ANCESTOR_REPARSE_BLOCKED"):
                    rag._reject_reparse_ancestors(candidate)
        self.assertFalse(candidate.exists())

    def test_existing_parent_permission_failure_is_fail_closed(self):
        target = self.root / "unreadable"
        target.mkdir()
        original = Path.lstat
        def fake_lstat(path, *args, **kwargs):
            if path == target:
                raise PermissionError("synthetic denied")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", fake_lstat):
            with self.assertRaisesRegex(rag.RagHold, "RAG_ANCESTOR_UNREADABLE"):
                rag._reject_reparse_ancestors(target / "index.json")

    def test_absent_new_parent_is_not_false_positive(self):
        candidate = self.root / "new-folder" / "index.json"
        rag._reject_reparse_ancestors(candidate)
        self.assertFalse(candidate.parent.exists())


if __name__ == "__main__":
    unittest.main()
