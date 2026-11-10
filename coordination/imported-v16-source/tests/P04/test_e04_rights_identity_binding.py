"""E04 actual-module verifier identity-binding regressions (CPU-only fixtures).

A mocked local verifier proves parser/comparison behavior, NOT dataset rights,
authorized model weights, NVIDIA training or installed Windows behavior.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_e04_rights_identity", SOURCE)
assert spec is not None and spec.loader is not None
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class RightsIdentityBindingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.train = root / "train.jsonl"
        self.holdout = root / "holdout.jsonl"
        self.manifest = root / "manifest.json"
        self.verifier = root / "local-verifier-stub"
        self.train.write_text('{"text":"alpha"}\n', encoding="utf-8")
        self.holdout.write_text('{"text":"bravo"}\n', encoding="utf-8")
        self.verifier.write_text("never executed by fixtures\n", encoding="utf-8")
        self.claims = {
            "schema": "nox-dataset-consent-v1",
            "rights_status": "APPROVED",
            "consent_status": "GRANTED",
            "dataset_id": "DataSet-A",
            "dataset_revision": "Revision-Ab",
            "license_id": "License-MiXeD",
            "owner_approval_id": "Approval-CaseA",
            "train_sha256": hashlib.sha256(self.train.read_bytes()).hexdigest(),
            "holdout_sha256": hashlib.sha256(self.holdout.read_bytes()).hexdigest(),
        }
        self.manifest.write_text(json.dumps(self.claims) + "\n", encoding="utf-8")
        self.attestation = {
            "schema": "nox-rights-attestation-v1",
            "status": "VERIFIED",
            "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "dataset_id": self.claims["dataset_id"],
            "dataset_revision": self.claims["dataset_revision"],
            "license_id": self.claims["license_id"],
            "owner_approval_id": self.claims["owner_approval_id"],
            "train_sha256": self.claims["train_sha256"],
            "holdout_sha256": self.claims["holdout_sha256"],
            "intent": "training",
            "attestation_id": "case-bound-001",
        }

    def verify(self, attestation=None):
        response = json.dumps(self.attestation if attestation is None else attestation)
        with patch.object(worker.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0, stdout=response)):
            return worker.verify_manifest(self.manifest, self.train, self.holdout, self.verifier)

    def test_exact_rights_identity_is_accepted_by_fixture(self):
        result = self.verify()
        self.assertEqual(result["_rights_attestation_id"], "case-bound-001")
        self.assertEqual(result["dataset_id"], "DataSet-A")

    def test_sha256_hex_case_does_not_change_digest_identity(self):
        for key in ("manifest_sha256", "train_sha256", "holdout_sha256"):
            with self.subTest(key=key):
                candidate = dict(self.attestation)
                candidate[key] = candidate[key].upper()
                self.verify(candidate)

    def test_dataset_and_authorization_identifiers_are_case_sensitive(self):
        for key in ("dataset_id", "dataset_revision", "license_id", "owner_approval_id"):
            with self.subTest(key=key):
                candidate = dict(self.attestation)
                candidate[key] = candidate[key].swapcase()
                with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
                    self.verify(candidate)

    def test_protocol_schema_status_and_intent_are_case_sensitive(self):
        for key in ("schema", "status", "intent"):
            with self.subTest(key=key):
                candidate = dict(self.attestation)
                candidate[key] = candidate[key].upper()
                with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
                    self.verify(candidate)

    def test_hex_sha_must_not_contain_non_hex_chars(self):
        candidate = dict(self.attestation)
        candidate["train_sha256"] = "g" + candidate["train_sha256"][1:]
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
            self.verify(candidate)

    def test_wrong_hex_sha_rejected(self):
        candidate = dict(self.attestation)
        candidate["holdout_sha256"] = "0" * 64 if candidate["holdout_sha256"] != "0" * 64 else "1" * 64
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
            self.verify(candidate)

    def test_empty_attestation_id_rejected(self):
        candidate = dict(self.attestation)
        candidate["attestation_id"] = "  "
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
            self.verify(candidate)

    def test_missing_authorization_claim_rejected(self):
        candidate = dict(self.attestation)
        del candidate["owner_approval_id"]
        with self.assertRaisesRegex(ValueError, "RIGHTS_VERIFIER_ATTESTATION_MISMATCH"):
            self.verify(candidate)


if __name__ == "__main__":
    unittest.main()
