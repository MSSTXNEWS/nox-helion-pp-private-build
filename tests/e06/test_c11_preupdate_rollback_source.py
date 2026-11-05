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


    def test_saved_rollback_slot_refuses_second_update_before_staging(self):
        """The original R11 owner is immutable; B03 stages only a safe check."""
        builder = BUILDER.read_text(encoding="utf-8")
        donor = ORIGINAL.read_text(encoding="utf-8")
        pattern = r"\$c11SavedRollback(Original|Replacement)=@'\n(?P<body>.*?)\n'@"
        matches = {m.group(1): m.group("body") for m in re.finditer(pattern, builder, re.DOTALL)}
        self.assertEqual(set(matches), {"Original", "Replacement"})
        old, new = matches["Original"], matches["Replacement"]
        self.assertEqual(donor.count(old), 1)
        self.assertNotIn("C11CheckSavedRollback:", donor)
        staged = donor.replace(old, new, 1)
        self.assertEqual(staged.count("C11CheckSavedRollback:"), 1)
        self.assertIn('IfFileExists "$BackupDir" 0 C11CheckSavedRollback', staged)
        self.assertIn('IfFileExists "$INSTDIR.__p01_rollback_saved" 0 Preflight', staged)
        self.assertIn('Abort "Rollback-save exists; preserve it before another update."', staged)
        self.assertLess(staged.index("C11CheckSavedRollback:"), staged.index("  Preflight:"))
        self.assertLess(staged.index("C11CheckSavedRollback:"), staged.index("  StagePayload:"))
        self.assertLess(builder.index("C11_NSIS_SAVED_ROLLBACK_SLOT_FENCE_STAGED"),
                        builder.index("& $makensisPath"))
        self.assertEqual(staged.replace(new, old, 1), donor)


    def test_owned_marker_write_and_close_fail_before_activation(self):
        """Disposable C11 NSIS must not activate an incomplete ownership marker."""
        builder = BUILDER.read_text(encoding="utf-8")
        donor = ORIGINAL.read_text(encoding="utf-8")
        marker = re.search(
            r"\$c11MarkerOriginal=@'\n(?P<old>.*?)\n'@\n\$c11MarkerGuard=@'\n(?P<new>.*?)\n'@",
            builder, re.DOTALL)
        self.assertIsNotNone(marker)
        old, new = marker.group("old"), marker.group("new")
        self.assertEqual(donor.count(old), 1)
        self.assertNotIn("Ownership marker absent; activation refused.", donor)
        staged = donor.replace(old, new, 1)
        self.assertEqual(staged.count('FileWrite $2 "NOXHELION.P01 V16$\\r$\\n"'), 1)
        self.assertIn("ClearErrors\n  FileWrite $2", new)
        self.assertIn('IfErrors 0 +3\n    FileClose $2\n    Abort "Could not write ownership marker."', new)
        self.assertIn('IfErrors 0 +2\n    Abort "Could not close ownership marker."', new)
        self.assertIn('IfFileExists "$StageDir\\nox-p01-owned.txt" +2 0', new)
        self.assertLess(staged.index("Ownership marker absent; activation refused."),
                        staged.index('Rename "$INSTDIR" "$BackupDir"'))
        self.assertLess(builder.index("C11_NSIS_MARKER_WRITE_GATE_STAGED"),
                        builder.index("& $makensisPath"))
        self.assertEqual(staged.replace(new, old, 1), donor)



if __name__ == "__main__":
    unittest.main()
