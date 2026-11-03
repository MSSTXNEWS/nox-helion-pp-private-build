"""R108 source-only original NSIS UninstallString quote/guard regression."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
REVIEWED = ROOT / "stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi"
BAD = "  WriteRegStr HKCU \"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_ID}\" \"UninstallString\" '\\\"$INSTDIR\\Uninstall.exe\\\"'"
APPROVED = "  WriteRegStr HKCU \"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_ID}\" \"UninstallString\" '\"$INSTDIR\\Uninstall.exe\"'"
def guarded_stage(sample):
    wrong, good = sample.count(BAD), sample.count(APPROVED)
    if wrong == 1 and good == 0:
        sample = sample.replace(BAD, APPROVED)
    elif wrong != 0 or good != 1:
        raise ValueError("P01_NSIS_UNINSTALL_REGISTRY_PREIMAGE_HOLD")
    assert sample.count(BAD) == 0 and sample.count(APPROVED) == 1
    return sample
class TestNSISUninstallRegistryQuoteR108(unittest.TestCase):
    def test_malformed_original_is_repaired_without_other_text_loss(self):
        source = "prefix\n" + BAD + "\nsuffix"
        self.assertEqual(guarded_stage(source), "prefix\n" + APPROVED + "\nsuffix")
    def test_reviewed_original_is_idempotent(self):
        self.assertEqual(guarded_stage(APPROVED), APPROVED)
    def test_unknown_or_multiple_source_lines_are_refused(self):
        for sample in (BAD * 2, APPROVED * 2, "unowned", BAD + APPROVED):
            with self.subTest(sample=sample[:40]):
                with self.assertRaises(ValueError): guarded_stage(sample)
    def test_builder_stages_after_c11_before_makensis(self):
        src = BUILDER.read_text(encoding="utf-8-sig")
        marker = "[IO.File]::WriteAllText($c11NsiPath,$c11NsiPatched"
        self.assertEqual(src.count("P01_NSIS_UNINSTALL_REGISTRY_QUOTE_STAGE_PASS"), 1)
        self.assertEqual(src.count("P01_NSIS_UNINSTALL_REGISTRY_PREIMAGE_HOLD"), 1)
        self.assertLess(src.index("C11_NSIS_ROLLBACK_FENCE_STAGE_HOLD"), src.index("$uninstallRegistryBad="))
        self.assertLess(src.index("P01_NSIS_UNINSTALL_REGISTRY_QUOTE_STAGE_PASS"), src.index(marker))
        self.assertLess(src.index(marker), src.index("& $makensisPath /V2"))
        self.assertIn("P01_C09_ORIGINAL_R11_PREIMAGE_SHA_HOLD", src)
    def test_reviewed_c09_matches_approved_registry_contract(self):
        txt = REVIEWED.read_text(encoding="utf-8-sig")
        self.assertEqual(txt.count(APPROVED), 1)
        self.assertNotIn(BAD, txt)
if __name__ == "__main__": unittest.main()
