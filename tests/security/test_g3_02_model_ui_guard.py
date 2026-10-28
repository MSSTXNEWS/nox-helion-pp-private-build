"""Offline source-pattern regression; does not claim installed Windows acceptance."""
import unittest
from coordination.security.g3_02_model_ui_guard import inspect_model_window


class ModelUiSecurityGateTests(unittest.TestCase):
    def test_detects_editable_vram_unlock_and_unverified_license(self):
        owner_source = '''
private readonly TextBox _availableVram = new();
if (!IsHttpsEvidence(artifact.LicenseEvidenceUrl)) return Block("missing", out reason);
if (!decimal.TryParse(_availableVram.Text, out var vram)) return false;
_download.IsEnabled = eligible;
'''
        result = inspect_model_window(owner_source)
        self.assertEqual("HOLD", result["status"])
        self.assertEqual({"MANUAL_VRAM_UNLOCKS_MODEL_UI", "LICENSE_URL_FORMAT_NOT_LICENSE_ATTESTATION"},
                         {f["code"] for f in result["findings"]})

    def test_no_false_pass_claim_on_unknown_source(self):
        result = inspect_model_window("class ModelWindow {}")
        self.assertTrue(result["review_required"])
        self.assertNotEqual("PASS", result["status"])
        self.assertFalse(result["findings"])

    def test_manual_vram_without_download_enable_is_not_the_pattern(self):
        source = 'decimal.TryParse(_availableVram.Text, out var vram);'
        self.assertFalse(inspect_model_window(source)["findings"])

    def test_reviewed_native_rights_callback_suppresses_only_license_pattern(self):
        source = '''
Func<ModelArtifactEvidence, bool> approved;
IsHttpsEvidence(artifact.LicenseEvidenceUrl);
decimal.TryParse(_availableVram.Text, out var vram);
_download.IsEnabled = eligible;
'''
        result = inspect_model_window(source)
        self.assertEqual(["MANUAL_VRAM_UNLOCKS_MODEL_UI"], [f["code"] for f in result["findings"]])


if __name__ == "__main__":
    unittest.main()
