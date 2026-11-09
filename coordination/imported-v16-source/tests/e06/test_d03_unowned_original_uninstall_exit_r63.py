"""SOURCE_ONLY NSIS owner-admission regression; physical E06/E07 are separate."""
from pathlib import Path
import unittest

BUILDER = Path(__file__).resolve().parents[2] / "coordination/e06/build_onehost_installer.ps1"

class D03UnownedUninstallExit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BUILDER.read_text(encoding="utf-8-sig")

    def test_missing_marker_fails_before_powershell(self):
        self.assertIn('IfFileExists "$INSTDIR\\nox-p01-owned.txt" D03OwnerMarkerPresent 0', self.source)
        self.assertIn('Abort "Uninstall owner marker missing; no files changed."', self.source)

    def test_wrong_root_fails_before_powershell(self):
        self.assertIn('StrCmp $INSTDIR "$LOCALAPPDATA\\Programs\\NOX HELION" D03UninstallRootTrusted 0', self.source)
        self.assertIn('Abort "Uninstall root not owned; no files changed."', self.source)

    def test_native_admission_and_noloss_are_still_enforced(self):
        for token in ("D03_NSIS_UNOWNED_ADMISSION_SECTION_HOLD",
                      "D03_NSIS_UNOWNED_'+$d03Admission.Name+'_PREIMAGE_HOLD",
                      "D03_NSIS_UNOWNED_'+$d03Admission.Name+'_READBACK_HOLD",
                      "D03_NSIS_UNOWNED_OWNER_ADMISSION_FAIL_CLOSED_STAGED",
                      "C11UninstallManifestHold:",
                      "P01_C09_REMOVER_REVIEWED_BLOB_HOLD"):
            self.assertIn(token, self.source)
        self.assertEqual(self.source.count("& $makensisPath /V2"), 1)

    def test_powershell_51_herestring_terminator(self):
        # PS 5.1 requires the closing '@ delimiter at column zero on its
        # own line: never concatenate a semicolon to the terminator.
        self.assertNotIn("\n'@;\n", self.source)
        self.assertEqual(self.source.count("D03_NSIS_UNOWNED_OWNER_ADMISSION_FAIL_CLOSED_STAGED"), 1)

if __name__ == "__main__":
    unittest.main()
