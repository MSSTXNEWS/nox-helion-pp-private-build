"""M04 provenance regression for original src/nox_selfbuilder/model_admission.py.

Run against current PR source (RED):
  NOX_MODEL_ADMISSION_SOURCE=/path/to/model_admission.py python -m unittest -v test_m04_candidate_registry_duplicate_keys.py
Run against the M04 donor (GREEN) with same command and donor path.
No weights, network request or native approval are exercised.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(os.environ.get("NOX_MODEL_ADMISSION_SOURCE", str(
    Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/model_admission.py")))
spec = importlib.util.spec_from_file_location("nox_m04_original_candidate_registry", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class P03RegistryDuplicateKeyRegression(unittest.TestCase):
    def write_catalog(self, text):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = Path(td.name) / "catalog.json"
        p.write_text(text, encoding="utf-8")
        return p

    def test_duplicate_nested_license_claim_rejected(self):
        ambiguous = ('{"schema":"NOX-CODING-LLM-CANDIDATE-REGISTRY-V3",'
                     '"models":[{"tag":"qwen2.5-coder:0.5b",'
                     '"commercial_policy":"RESTRICTED",'
                     '"commercial_policy":"APACHE_2_0_CANDIDATE"}]}')
        with self.assertRaisesRegex(ValueError, "CATALOG_DUPLICATE_JSON_KEY"):
            module.model_candidates(self.write_catalog(ambiguous))

    def test_duplicate_root_schema_claim_rejected(self):
        ambiguous = ('{"schema":"UNREVIEWED",'
                     '"schema":"NOX-CODING-LLM-CANDIDATE-REGISTRY-V3",'
                     '"models":[]}')
        with self.assertRaisesRegex(ValueError, "CATALOG_DUPLICATE_JSON_KEY"):
            module.model_candidates(self.write_catalog(ambiguous))

    def test_valid_candidate_remains_uninstalled_review_only(self):
        catalog = self.write_catalog(json.dumps({
            "schema": "NOX-CODING-LLM-CANDIDATE-REGISTRY-V3",
            "models": [{"tag": "qwen2.5-coder:0.5b",
                        "commercial_policy": "APACHE_2_0_CANDIDATE"}]}))
        attestation = {"full_manifest_sha256": "a" * 64,
                       "official_manifest_verified": True,
                       "license_evidence_verified": True,
                       "hardware_preflight_passed": True,
                       "reviewer_independent": True,
                       "immutable_revision": "sample",
                       "rights_receipt_id": "sample",
                       "owner_receipt_id": "sample"}
        receipt = module.p03_review_handoff(
            catalog_path=catalog, tag="qwen2.5-coder:0.5b",
            attestation=attestation, owner_consent=True)
        self.assertEqual(receipt["status"], "P03_QUEUE_REVIEW_REQUIRED_NOT_DOWNLOADED")
        self.assertIs(receipt["network_called"], False)
        self.assertEqual(receipt["connector"], "EXISTING_P03_ONLY")


if __name__ == "__main__":
    unittest.main()
