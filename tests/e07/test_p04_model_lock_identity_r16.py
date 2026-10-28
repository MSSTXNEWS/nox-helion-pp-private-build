#!/usr/bin/env python3
"""W5·02 R16 source-level model lock/rights gate. No GPU, weights, SIP or runtime PASS."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINER = ROOT / "Packages/P04/train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_p04_lock_under_test", TRAINER)
p04 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p04)

class ModelLockIdentityQA(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="nox-lock-r16-")
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.model = self.root / "model"
        self.model.mkdir()
        (self.model / "config.json").write_bytes(b'{"source":"QA-placeholder-NOT-installed-model"}\n')
        self.lock = self.root / "model-lock.json"
        self.rev = "a" * 40
        self.valid = {
            "schema": "nox-model-lock-v1",
            "license_status": "APPROVED",
            "owner_approval_id": "approval-001",
            "model_id": "pinned-local-model-id",
            "revision": self.rev,
            "snapshot_sha256": p04.sha256_tree(self.model),
        }

    def check(self, **fields):
        lock = {**self.valid, **fields}
        self.lock.write_text(json.dumps(lock), encoding="utf-8")
        return p04.verify_model_lock(self.lock, self.model, self.rev)

    def test_valid_approved_identity(self):
        self.assertEqual(self.check()["owner_approval_id"], "approval-001")

    def test_reject_owner_true(self):
        with self.assertRaises(ValueError): self.check(owner_approval_id=True)

    def test_reject_owner_integer(self):
        with self.assertRaises(ValueError): self.check(owner_approval_id=777)

    def test_reject_owner_whitespace(self):
        with self.assertRaises(ValueError): self.check(owner_approval_id="   ")

    def test_reject_empty_model_id(self):
        with self.assertRaises(ValueError): self.check(model_id="")

    def test_reject_whitespace_model_id(self):
        with self.assertRaises(ValueError): self.check(model_id="   ")

    def test_reject_missing_owner(self):
        with self.assertRaises(ValueError): self.check(owner_approval_id="")

    def test_reject_mismatched_tree_sha(self):
        with self.assertRaises(ValueError): self.check(snapshot_sha256="b" * 64)

    def test_reject_revision_mismatch(self):
        with self.assertRaises(ValueError): self.check(revision="b" * 40)

    def test_reject_schema_mismatch(self):
        with self.assertRaises(ValueError): self.check(schema="nox-model-lock-v0")

if __name__ == "__main__":
    unittest.main(verbosity=2)
