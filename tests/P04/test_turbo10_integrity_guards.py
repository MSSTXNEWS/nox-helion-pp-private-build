"""Ten P04 real-module regressions: RAG safety, GPU workload bounds, merge.
No model pull, no training, no synthetic GPU success; designed for Windows/Linux.
"""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SID = "S-1-5-21-1100"


def load_module(name, filename):
    src = ROOT / "Packages" / "P04" / filename
    spec = importlib.util.spec_from_file_location(name, src)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rag = load_module("turbo10_p04_rag", "rag_python_compat.py")
train = load_module("turbo10_p04_train", "train_qlora.py")
merge = load_module("turbo10_p04_merge", "merge_qlora_adapter.py")


class Turbo10IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.index_path = self.root / "index.json"
        self.rag = rag.LocalRag("http://127.0.0.1:11434", "fixture-model", self.index_path)
        with mock.patch.object(self.rag, "_embeddings", return_value=[[1.0, 0.0]]):
            self.rag.ingest_text(SID, "c1", "s1", "notes.md", "original source")

    def mutate(self, transform):
        doc = json.loads(self.index_path.read_text(encoding="utf-8"))
        transform(doc)
        self.index_path.write_text(json.dumps(doc), encoding="utf-8")

    def test_01_duplicate_source_identity_is_fail_closed(self):
        self.mutate(lambda doc: doc["sources"].append(copy.deepcopy(doc["sources"][0])))
        with self.assertRaisesRegex(rag.RagHold, "RAG_INDEX_DUPLICATE_SOURCE_ID"):
            self.rag.delete_conversation(SID, "c1")

    def test_02_non_object_source_is_fail_closed(self):
        self.mutate(lambda doc: doc["sources"].append(None))
        with self.assertRaisesRegex(rag.RagHold, "RAG_INDEX_SOURCE_SCHEMA_INVALID"):
            self.rag.delete_conversation(SID, "c1")

    def test_03_bad_source_scope_is_fail_closed(self):
        self.mutate(lambda doc: doc["sources"][0].update({"ownerSid": 23}))
        with self.assertRaisesRegex(rag.RagHold, "RAG_INDEX_SOURCE_SCHEMA_INVALID"):
            self.rag.delete_conversation(SID, "c1")

    def test_04_boolean_chunk_index_is_not_int(self):
        self.mutate(lambda doc: doc["sources"][0]["chunks"][0].update({"chunkIndex": True}))
        with self.assertRaisesRegex(rag.RagHold, "RAG_CHUNK_INDEX_INVALID"):
            with mock.patch.object(self.rag, "_embeddings", return_value=[[1.0, 0.0]]):
                self.rag.search(SID, "c1", "hello")

    def test_05_negative_chunk_index_rejected(self):
        self.mutate(lambda doc: doc["sources"][0]["chunks"][0].update({"chunkIndex": -1}))
        with self.assertRaisesRegex(rag.RagHold, "RAG_CHUNK_INDEX_INVALID"):
            with mock.patch.object(self.rag, "_embeddings", return_value=[[1.0, 0.0]]):
                self.rag.search(SID, "c1", "hello")

    def test_06_duplicate_chunk_reference_rejected(self):
        def duplicate(doc):
            chunks = doc["sources"][0]["chunks"]
            chunks.append(copy.deepcopy(chunks[0]))
        self.mutate(duplicate)
        with self.assertRaisesRegex(rag.RagHold, "RAG_CHUNK_INDEX_INVALID"):
            with mock.patch.object(self.rag, "_embeddings", return_value=[[1.0, 0.0]]):
                self.rag.search(SID, "c1", "hello")

    def test_07_invalid_query_and_delete_source_ids_rejected(self):
        with self.assertRaisesRegex(rag.RagHold, "RAG_QUERY_INVALID"):
            self.rag.search(SID, "c1", "bad\x00query")
        with self.assertRaisesRegex(rag.RagHold, "RAG_SOURCE_ID_INVALID"):
            self.rag.delete_source(SID, "c1", "bad\nsource")
        self.assertTrue(self.index_path.exists())

    def test_08_oversized_hit_does_not_starve_smaller_citation(self):
        hits = [
            {"source_id": "big", "title": "big.md", "text": "A" * (rag.MAX_CONTEXT_CHARS + 5),
             "chunk_index": 0, "chunk_sha256": "a" * 64},
            {"source_id": "small", "title": "ok.md", "text": "useful",
             "chunk_index": 0, "chunk_sha256": "b" * 64},
        ]
        with mock.patch.object(self.rag, "search", return_value=hits):
            result = self.rag.context(SID, "c1", "hello")
        self.assertEqual([x["source_id"] for x in result["sources"]], ["small"])
        self.assertIn("useful", result["context"])

    def test_09_gpu_profile_limits_reject_nan_and_oversized_steps(self):
        profile = train.PROFILES["ECO"]
        for steps, epochs, save, ev in ((profile["max_steps"] + 1, 1.0, 1, 1),
                                        (1, float("nan"), 1, 1),
                                        (1, float("inf"), 1, 1),
                                        (1, 1.0, 2, 1)):
            with self.subTest(steps=steps, epochs=epochs, save=save):
                with self.assertRaises(ValueError):
                    train.validate_training_limits(profile, steps, epochs, save, ev)
        train.validate_training_limits(profile, 2, 1.0, 1, 1)

    def test_10_training_and_merge_reparse_ancestors_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("native symlinks require permission on this runner")
        for func in (train.reject_reparse_ancestors, merge.reject_reparse_ancestors):
            with self.subTest(implementation=func.__module__):
                with self.assertRaises(ValueError):
                    func(alias / "new" / "model")
        self.assertFalse((outside / "new").exists())


if __name__ == "__main__":
    unittest.main()
