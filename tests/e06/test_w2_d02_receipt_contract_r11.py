"""E06-owned regression: one original WOW200 receipt count across CI and NSIS.

Source-contract checks only. Windows installer acceptance requires actual E07.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/nox-v16-e06-d02-onehost.yml"
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
STAGE = ROOT / "integrations/wow200/stage_wow200.py"
OWNER_TEST = ROOT / "integrations/wow200/tests/test_stage_wow200.py"

class D02ReceiptContractTests(unittest.TestCase):
    def test_owner_stage_writes_actual_copied_count(self):
        text = STAGE.read_text(encoding="utf-8")
        self.assertIn('"count":len(copied)', text)

    def test_owner_unit_test_proves_65_receipt_entries(self):
        text = OWNER_TEST.read_text(encoding="utf-8")
        self.assertIn("self.assertEqual(len(receipt['files']),65)", text)

    def test_onehost_builder_accepts_same_65_count(self):
        text = BUILDER.read_text(encoding="utf-8")
        self.assertRegex(text, r"\$wowReceipt\.count\s+-ne\s+65\b")

    def test_actions_stage_gate_accepts_same_65_count(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"\$receipt\.count\s+-ne\s+65\b", text)), 1)
        self.assertNotRegex(text, r"\$receipt\.count\s+-ne\s+64\b")

    def test_manifest_parity_hidden_files_and_numeric_version(self):
        text = BUILDER.read_text(encoding="utf-8")
        self.assertIn("Get-ChildItem -LiteralPath $payload -File -Recurse -Force", text)
        self.assertIn("version='16.0.0'", text)
        self.assertIn("'/DAPP_VERSION=16.0.0'", text)

if __name__ == "__main__":
    unittest.main()
