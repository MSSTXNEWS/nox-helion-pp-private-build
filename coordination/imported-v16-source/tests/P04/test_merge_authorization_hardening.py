"""Real merge_qlora_adapter module safety regressions, CPU/offline only.

These are authorization/parser and filesystem guards, NOT CUDA training,
checkpoint proof, an executed LoRA merge, or installed Windows acceptance.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "merge_qlora_adapter.py"
spec = importlib.util.spec_from_file_location("e04_r10_merge", MODULE)
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


class MergeAuthorizationR10(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.train = self.root / "train.jsonl"
        self.holdout = self.root / "holdout.jsonl"
        self.train.write_text('{"text":"training sample"}\n', encoding="utf-8")
        self.holdout.write_text('{"text":"evaluation sample"}\n', encoding="utf-8")
        self.manifest = self.root / "consent.json"
        self.verifier = self.root / "verifier.exe"
        self.verifier.write_bytes(b"mock-only; never executed")
        self.payload = {
            "schema": "nox-dataset-consent-v1",
            "rights_status": "APPROVED",
            "consent_status": "GRANTED",
            "dataset_id": "CaseSensitiveDataset",
            "dataset_revision": "RevA",
            "license_id": "License-IdA",
            "owner_approval_id": "Approval-CaseA",
            "train_sha256": hashlib.sha256(self.train.read_bytes()).hexdigest(),
            "holdout_sha256": hashlib.sha256(self.holdout.read_bytes()).hexdigest(),
        }
        self.write_manifest()
        self.receipt = {
            "id": self.payload["dataset_id"],
            "revision": self.payload["dataset_revision"],
            "license_id": self.payload["license_id"],
            "owner_approval_id": self.payload["owner_approval_id"],
            "train_sha256": self.payload["train_sha256"],
            "holdout_sha256": self.payload["holdout_sha256"],
        }

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.payload), encoding="utf-8")

    def response(self):
        return {
            "schema": "nox-rights-attestation-v1",
            "status": "VERIFIED",
            "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "dataset_id": self.payload["dataset_id"],
            "dataset_revision": self.payload["dataset_revision"],
            "license_id": self.payload["license_id"],
            "owner_approval_id": self.payload["owner_approval_id"],
            "train_sha256": self.payload["train_sha256"],
            "holdout_sha256": self.payload["holdout_sha256"],
            "intent": "training",
            "attestation_id": "verifier-receipt-R10",
        }

    def verify_with(self, attestation, receipt=None):
        if isinstance(attestation, str):
            stdout = attestation
        else:
            stdout = json.dumps(attestation)
        if receipt is None:
            receipt = dict(self.receipt)
        if isinstance(attestation, dict):
            receipt["rights_attestation_id"] = attestation["attestation_id"]
            receipt["rights_attestation_sha256"] = hashlib.sha256(
                json.dumps(attestation, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        fake = types.SimpleNamespace(returncode=0, stdout=stdout)
        with mock.patch.object(merge.subprocess, "run", return_value=fake):
            return merge.verify_dataset_attestation(self.manifest, self.verifier, receipt)

    def test_01_valid_exact_rights_match(self):
        self.assertEqual(self.verify_with(self.response())["dataset_id"], "CaseSensitiveDataset")

    def test_02_hex_case_is_only_permitted_case_variation(self):
        attestation = self.response()
        attestation["train_sha256"] = attestation["train_sha256"].upper()
        attestation["holdout_sha256"] = attestation["holdout_sha256"].upper()
        attestation["manifest_sha256"] = attestation["manifest_sha256"].upper()
        receipt = dict(self.receipt)
        receipt["train_sha256"] = receipt["train_sha256"].upper()
        receipt["holdout_sha256"] = receipt["holdout_sha256"].upper()
        self.assertEqual(self.verify_with(attestation, receipt)["schema"], "nox-dataset-consent-v1")

    def test_03_dataset_identity_wrong_case_rejected(self):
        receipt = dict(self.receipt)
        receipt["id"] = receipt["id"].lower()
        with self.assertRaisesRegex(ValueError, "TRAINING_RECEIPT_DATASET_MISMATCH"):
            self.verify_with(self.response(), receipt)

    def test_04_license_identity_wrong_case_rejected(self):
        attestation = self.response()
        attestation["license_id"] = attestation["license_id"].lower()
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
            self.verify_with(attestation)

    def test_05_intent_wrong_case_rejected(self):
        attestation = self.response()
        attestation["intent"] = "TRAINING"
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
            self.verify_with(attestation)

    def test_06_nested_duplicate_manifest_key_rejected(self):
        self.manifest.write_text('{"schema":"nox-dataset-consent-v1","meta":{"id":"X","id":"Y"}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "MERGE_JSON_DUPLICATE_KEY"):
            merge.read_object(self.manifest)

    def test_07_duplicate_verifier_reply_key_rejected(self):
        raw = '{"status":"VERIFIED","status":"VERIFIED"}'
        with self.assertRaisesRegex(ValueError, "MERGE_JSON_DUPLICATE_KEY"):
            merge.parse_strict_json_object(raw, maximum=65_536)

    def test_08_nonfinite_nan_and_inf_rejected(self):
        for literal in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(literal=literal):
                with self.assertRaisesRegex(ValueError, "MERGE_JSON_NONFINITE"):
                    merge.parse_strict_json_object('{"unsafe":' + literal + "}")

    def test_09_oversized_verifier_reply_rejected(self):
        with self.assertRaisesRegex(ValueError, "MERGE_JSON_TOO_LARGE"):
            merge.parse_strict_json_object("{" + "x" * 65_536 + "}", maximum=65_536)

    def test_10_valid_model_tree_digest_matches_trainer_contract(self):
        tree = self.root / "model"
        tree.mkdir()
        (tree / "config.json").write_text("{}", encoding="utf-8")
        (tree / "weights.safetensors").write_bytes(b"synthetic, not model weights")
        self.assertRegex(merge.tree_sha256(tree), r"^[0-9a-f]{64}$")

    def test_11_symlink_in_tree_rejected(self):
        tree = self.root / "model"
        tree.mkdir()
        (tree / "config.json").write_text("{}", encoding="utf-8")
        alias = tree / "alias"
        try:
            alias.symlink_to(tree / "config.json")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "SYMLINK_IN_MODEL_TREE"):
            merge.tree_sha256(tree)

    def test_12_windows_reparse_root_is_denied_without_symlink(self):
        tree = self.root / "model"
        tree.mkdir()
        (tree / "config.json").write_text("{}", encoding="utf-8")
        old = Path.lstat
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        def fake_lstat(path, *args, **kwargs):
            if path == tree:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=flag)
            return old(path, *args, **kwargs)
        with mock.patch.object(merge.stat, "FILE_ATTRIBUTE_REPARSE_POINT", flag, create=True):
            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaisesRegex(ValueError, "MERGE_PATH_REPARSE_ANCESTOR|REPARSE_POINT_IN_MODEL_TREE"):
                    merge.tree_sha256(tree)

    def test_13_windows_reparse_entry_denied_without_symlink(self):
        tree = self.root / "model"
        tree.mkdir()
        target = tree / "weights.safetensors"
        target.write_bytes(b"fixture")
        old = Path.lstat
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        def fake_lstat(path, *args, **kwargs):
            if path == target:
                return types.SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=flag)
            return old(path, *args, **kwargs)
        with mock.patch.object(merge.stat, "FILE_ATTRIBUTE_REPARSE_POINT", flag, create=True):
            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaisesRegex(ValueError, "REPARSE_POINT_IN_MODEL_TREE"):
                    merge.tree_sha256(tree)

    def test_14_no_empty_digest_for_receipt_only_tree(self):
        tree = self.root / "output"
        tree.mkdir()
        (tree / "merge-receipt.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "MODEL_TREE_EMPTY"):
            merge.tree_sha256(tree, skip_merge_receipt=True)


if __name__ == "__main__":
    unittest.main()
