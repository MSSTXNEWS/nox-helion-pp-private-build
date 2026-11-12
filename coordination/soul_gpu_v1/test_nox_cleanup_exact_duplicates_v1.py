"""Offline tests of conservative NOX cleanup. No real deletion of Ollama."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import nox_cleanup_exact_duplicates_v1 as cleanup


class CleanupTests(unittest.TestCase):
    def test_exact_digest_alias_only_and_keep_unique_skills(self):
        current={"qwen3:8b":"a"*64,"qwen3:latest":"a"*64,
                 "qwen2.5-coder:7b":"b"*64,
                 "qwen3-embedding:0.6b":"c"*64,"qwen3:4b":"d"*64}
        options=cleanup.aliases(current,set(),set())
        self.assertEqual([v["delete"] for v in options],["qwen3:latest"])
        self.assertEqual(options[0]["keep"],"qwen3:8b")
        self.assertNotIn("qwen3:4b",[v["delete"] for v in options])

    def test_loaded_and_referenced_aliases_preserved(self):
        catalog={"old-name:latest":"1"*64,"current-name:latest":"1"*64}
        self.assertEqual(cleanup.aliases(catalog,{"old-name:latest"},
                                         {"current-name:latest"}),[])

    def test_receipt_guard_requires_complete_matching_sha(self):
        with TemporaryDirectory() as d:
            folder=Path(d)/("revision_"+("a"*12))
            folder.mkdir()
            model=folder/"model.safetensors"
            model.write_bytes(b"official fixture weights")
            sha=hashlib.sha256(model.read_bytes()).hexdigest()
            receipt={"revision":"a"*40,"model_id":"Qwen/Qwen3-0.6B",
                     "state":"SHA256_CHECKED",
                     "sha256":{"model.safetensors":sha},"created_utc":"2026-11-07"}
            (folder/"NOX_WEIGHTS_SHA256.json").write_text(json.dumps(receipt))
            self.assertIsNotNone(cleanup.snapshot_receipt(folder))
            model.write_bytes(b"tampered")
            self.assertIsNone(cleanup.snapshot_receipt(folder))

    def test_only_old_revisions_same_model_can_be_candidates(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            family=root/"brain"/"models"/"NOX_PRIME_V5"/"Qwen3-0.6B"
            for i,letter in enumerate(("a","b")):
                sub=family/("revision_"+letter*12)
                sub.mkdir(parents=True)
                source=sub/"model.safetensors"
                source.write_bytes(("official "+letter).encode())
                body={"revision":letter*40,"model_id":"Qwen/Qwen3-0.6B",
                      "state":"SHA256_CHECKED",
                      "sha256":{"model.safetensors":cleanup.sha256(source)},
                      "created_utc":"2026-11-0"+str(7+i)}
                (sub/"NOX_WEIGHTS_SHA256.json").write_text(json.dumps(body))
            results=cleanup.old_snapshots(root,[])
            self.assertEqual(len(results),1)
            self.assertIn("revision_"+("a"*12),results[0]["path"])
            self.assertTrue((family/("revision_"+("b"*12))).is_dir())

    def test_no_automatic_removal_without_execute(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/"brain"/"source"/"repo"/".git").mkdir(parents=True)
            current={"qwen3:8b":"a"*64,"duplicate:old":"a"*64}
            def provider(route):
                return {"models":[{"name":k,"digest":v} for k,v in current.items()]} if route=="/api/tags" else {"models":[]}
            with patch.object(cleanup,"process_commands",return_value=[]),\
                 patch.object(cleanup,"source_references",return_value=set()),\
                 patch.object(cleanup,"obsolete_boot_copies",return_value=[]):
                result=cleanup.cleanup(root,execute=False,client=provider)
            self.assertEqual(result["actually_removed"],0)
            self.assertEqual(result["candidate_aliases"],1)
            self.assertEqual(result["unique_trained_weights_removed"],0)

if __name__=="__main__":
    unittest.main()
