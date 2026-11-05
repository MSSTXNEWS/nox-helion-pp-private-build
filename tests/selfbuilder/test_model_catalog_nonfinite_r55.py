"""R55: original P03 model catalog and native attestation fail closed on ambiguity."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from nox_selfbuilder.model_admission import model_candidates, p03_review_handoff


class NativeModelCatalogAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "reviewed.json"
        self.data = {"schema": "NOX-CODING-LLM-CANDIDATE-REGISTRY-V3",
                     "models": [{"tag": "qwen2.5-coder:7b", "commercial_policy": "APACHE_2_0_CANDIDATE",
                                 "max_recommended_on_24gb": True}]}
        self.attestation = {"full_manifest_sha256": "a"*64,
                            "official_manifest_verified": True,
                            "license_evidence_verified": True,
                            "hardware_preflight_passed": True,
                            "reviewer_independent": True,
                            "immutable_revision": "manifest-v1",
                            "rights_receipt_id": "rights-v1",
                            "owner_receipt_id": "owner-v1"}

    def write_catalog(self, raw=None):
        self.path.write_text(raw or json.dumps(self.data), encoding="utf8")

    def test_valid_finite_catalog_and_review_only_handoff(self):
        self.data["metadata"] = {"confidence": 0.5}
        self.write_catalog()
        self.assertEqual(len(model_candidates(self.path)), 1)
        result = p03_review_handoff(catalog_path=self.path, tag="qwen2.5-coder:7b",
                                    attestation=self.attestation, owner_consent=True)
        self.assertEqual(result["status"], "P03_QUEUE_REVIEW_REQUIRED_NOT_DOWNLOADED")
        self.assertIs(result["network_called"], False)
        self.assertIs(result["training_performed"], False)

    def test_nan_constant_cannot_validate_rights_catalog(self):
        self.data["metadata"] = {"confidence": float("nan")}
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "CATALOG_NONFINITE_JSON"):
            model_candidates(self.path)

    def test_nested_infinity_constant_cannot_validate_catalog(self):
        self.data["models"][0]["unreviewed"] = {"NaN": float("inf")}
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "CATALOG_NONFINITE_JSON"):
            model_candidates(self.path)

    def test_exponential_overflow_float_cannot_validate_catalog(self):
        self.write_catalog(json.dumps(self.data).replace('"models":', '"risk_score": 1e9999, "models":', 1))
        with self.assertRaisesRegex(ValueError, "CATALOG_NONFINITE_JSON"):
            model_candidates(self.path)

    def test_malformed_native_attestation_must_be_hold_not_crash(self):
        self.write_catalog()
        for invalid in (None, [], 1, "rights=ok"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "NATIVE_P03_ATTESTATION_INCOMPLETE"):
                    p03_review_handoff(catalog_path=self.path, tag="qwen2.5-coder:7b",
                                       attestation=invalid, owner_consent=True)

    def test_owner_consent_still_mandatory(self):
        self.write_catalog()
        with self.assertRaisesRegex(PermissionError, "OWNER_APPROVAL_REQUIRED"):
            p03_review_handoff(catalog_path=self.path, tag="qwen2.5-coder:7b",
                               attestation=self.attestation, owner_consent=False)


if __name__ == "__main__":
    unittest.main()
