"""C11 exact owner NSIS source contract; source-only, NOT Windows acceptance."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
ORIGINAL = ROOT / "stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi"
ANCHOR = '  SetOutPath "$TEMP" ; release current working directory before Rename'


class C11RollbackSafetyTest(unittest.TestCase):
    def test_original_nsis_has_one_strict_activation_preimage(self):
        donor = ORIGINAL.read_text(encoding="utf-8")
        self.assertEqual(donor.count(ANCHOR), 1)
        self.assertEqual(donor.count('Rename "$INSTDIR" "$BackupDir"'), 1)
        self.assertIn('Verify-Payload.ps1', donor)
        self.assertNotIn('C11OldPayloadChecked', donor)

    def test_staged_installer_rejects_unverified_previous_version(self):
        builder = BUILDER.read_text(encoding="utf-8")
        donor = ORIGINAL.read_text(encoding="utf-8")
        match = re.search(r"\$c11Guard=@'\n(?P<body>.*?)\n'@", builder, re.DOTALL)
        self.assertIsNotNone(match, "missing build-time NSIS patch")
        guard = match.group("body")
        stage = donor.replace(ANCHOR, guard + "\n" + ANCHOR)
        self.assertEqual(stage.count("C11OldPayloadChecked:"), 1)
        self.assertIn('IfFileExists "$INSTDIR\\nox-p01-owned.txt" 0 C11OldPayloadChecked', guard)
        self.assertIn('-Root "$INSTDIR" -Manifest "$INSTDIR\\payload.sha256.json" -AllowInstalledMetadata', guard)
        self.assertIn('Abort "Existing application payload is not rollback-safe; update refused."', guard)
        self.assertLess(stage.index(guard), stage.index('Rename "$INSTDIR" "$BackupDir"'))
        self.assertLess(builder.index("C11_NSIS_ROLLBACK_OLD_PAYLOAD_SHA_GATE_STAGED"),
                        builder.index('& $makensisPath'))
        self.assertEqual(stage.replace(guard + "\n", "", 1), donor)


if __name__ == "__main__":
    unittest.main()
