"""Original Express P03 owner queue must fail closed on incomplete catalog RAM policy.

No model download, installation or Windows-native approval is performed here.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/model_admission.py"
spec = importlib.util.spec_from_file_location("original_express_p03_admission", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CatalogRamPolicyFailClosed(unittest.TestCase):
    def handoff(self, candidate):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "registry.json"
            catalog.write_text(json.dumps({
                "schema": "NOX-CODING-LLM-CANDIDATE-REGISTRY-V3",
                "models": [candidate],
            }), encoding="utf-8")
            return module.p03_review_handoff(
                catalog_path=catalog, tag="qwen2.5-coder:7b",
                owner_consent=True, attestation={
                    "full_manifest_sha256": "a" * 64,
                    "official_manifest_verified": True,
                    "license_evidence_verified": True,
                    "hardware_preflight_passed": True,
                    "reviewer_independent": True,
                    "immutable_revision": "source-1",
                    "rights_receipt_id": "rights-1",
                    "owner_receipt_id": "approval-1",
                    "installed_ram_gb": 24,
                })

    def model(self, **overrides):
        item = {"tag": "qwen2.5-coder:7b",
                "commercial_policy": "APACHE_2_0_CANDIDATE",
                "max_recommended_on_24gb": True}
        item.update(overrides)
        return item

    def test_missing_resource_policy_never_becomes_reviewed_proposal(self):
        incomplete = self.model()
        incomplete.pop("max_recommended_on_24gb")
        with self.assertRaisesRegex(ValueError, "CATALOG_RAM_POLICY_INVALID"):
            self.handoff(incomplete)

    def test_malformed_catalog_record_rejected_with_controlled_error(self):
        for candidate in (None, "corrupted", ["tag"], {}):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(ValueError, "CATALOG_MODEL_ENTRY_INVALID"):
                    self.handoff(candidate)

    def test_valid_small_model_still_review_only(self):
        result = self.handoff(self.model())
        self.assertEqual(result["status"], "P03_QUEUE_REVIEW_REQUIRED_NOT_DOWNLOADED")
        self.assertIs(result["network_called"], False)

    def test_large_model_24gb_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "MODEL_EXCEEDS_LOCAL_RESOURCE_POLICY"):
            self.handoff(self.model(max_recommended_on_24gb=False))

    def test_malformed_resource_policy_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CATALOG_RAM_POLICY_INVALID"):
            self.handoff(self.model(max_recommended_on_24gb="false"))


if __name__ == "__main__":
    unittest.main()
