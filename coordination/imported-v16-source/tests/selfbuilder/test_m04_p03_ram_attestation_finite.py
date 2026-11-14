"""Original P03 review handoff must reject ambiguous hardware memory attestations.

No network/model downloads, and a passing proposal is still QUEUE_REVIEW_REQUIRED.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/model_admission.py"
spec = importlib.util.spec_from_file_location("nox_p03_model_admission_under_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ModelHardwareAttestationRegression(unittest.TestCase):
    def handoff(self, *, ram, policy=False):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "models.json"
            catalog.write_text(json.dumps({
                "schema": "NOX-CODING-LLM-CANDIDATE-REGISTRY-V3",
                "models": [{
                    "tag": "qwen2.5-coder:7b",
                    "commercial_policy": "APACHE_2_0_CANDIDATE",
                    "max_recommended_on_24gb": policy,
                }],
            }), encoding="utf-8")
            attestation = {
                "full_manifest_sha256": "a" * 64,
                "official_manifest_verified": True,
                "license_evidence_verified": True,
                "hardware_preflight_passed": True,
                "reviewer_independent": True,
                "immutable_revision": "reviewed-source-1",
                "rights_receipt_id": "rights-1",
                "owner_receipt_id": "consent-1",
                "installed_ram_gb": ram,
            }
            return module.p03_review_handoff(
                catalog_path=catalog, tag="qwen2.5-coder:7b",
                attestation=attestation, owner_consent=True)

    def test_attested_ram_must_be_finite_numeric_and_policy_flag_bool(self):
        # NaN/Inf bypass `< 48` in the old source; strings or booleans are not
        # hardware measurements. A string "false" bypassed the bool identity check.
        for ram, policy in [
            (float("nan"), False), (float("inf"), False),
            ("96", False), (True, False), (-1, False),
            (32, "false"),
        ]:
            with self.subTest(ram=ram, policy=policy):
                with self.assertRaisesRegex(ValueError, "(P03_INSTALLED_RAM_INVALID|CATALOG_RAM_POLICY_INVALID)"):
                    self.handoff(ram=ram, policy=policy)
        with self.assertRaisesRegex(ValueError, "MODEL_EXCEEDS_LOCAL_RESOURCE_POLICY"):
            self.handoff(ram=32)
        result = self.handoff(ram=48)
        self.assertEqual(result["status"], "P03_QUEUE_REVIEW_REQUIRED_NOT_DOWNLOADED")
        self.assertFalse(result["network_called"])
        self.assertFalse(result["training_performed"])


if __name__ == "__main__":
    unittest.main()
