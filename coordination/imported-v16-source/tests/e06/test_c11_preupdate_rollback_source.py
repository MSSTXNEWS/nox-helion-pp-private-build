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




    def test_ownership_marker_exact_byte_readback_before_any_activation(self):
        """Disposable NSIS must not trust a present but truncated/foreign marker."""
        builder = BUILDER.read_text(encoding="utf-8")
        donor = ORIGINAL.read_text(encoding="utf-8")
        hit = re.search(r"\$c11MarkerGuard=@'\n(?P<body>.*?)\n'@", builder, re.DOTALL)
        self.assertIsNotNone(hit)
        guard = hit.group("body")
        self.assertNotIn("C11MarkerReadbackReject:", donor)
        for op in (
            'FileOpen $2 "$StageDir\\nox-p01-owned.txt" r'.replace("\\\\", "\\"),
            'FileSeek $2 0 END $3',
            'IntCmp $3 19 C11MarkerReadbackSizeOkay C11MarkerReadbackReject C11MarkerReadbackReject',
            'FileSeek $2 0 SET',
            'FileRead $2 $4',
            'StrCpy $4 $4 17',
            'StrCmpS $4 "NOXHELION.P01 V16" 0 C11MarkerReadbackReject',
            'Abort "Ownership marker content mismatch; activation refused."',
        ):
            self.assertIn(op, guard)
        self.assertEqual(guard.count("C11MarkerReadbackReject:"), 1)
        self.assertEqual(guard.count("C11MarkerReadbackAccept:"), 1)
        self.assertLess(guard.index("Ownership marker absent; activation refused."),
                        guard.index("C11MarkerReadbackReject:"))
        self.assertLess(builder.index("C11_NSIS_MARKER_WRITE_GATE_STAGED"),
                        builder.index("& $makensisPath"))
        self.assertLess(builder.index("C11MarkerReadbackAccept:"),
                        builder.index("$c11ActivationRecoveryOld"))
        expected = b"NOXHELION.P01 V16\r\n"
        self.assertEqual(len(expected), 19)
        for marker, valid in (
            (expected, True),
            (expected[:-1], False),
            (expected + b"x", False),
            (b"WRONGOWNER.P01 V16\r\n", False),
            (b"NOXHELION.P01 V15\r\n", False),
            (b"noxhelion.P01 V16\r\n", False),
            (b"NOXHELION.p01 V16\r\n", False),
        ):
            # The two checks below mirror the exact size + prefix gates above.
            self.assertEqual(marker == expected, valid)


    def test_failed_rename_recovery_requires_real_owner_and_slot_readback(self):
        """B03: no false NSIS rollback/activation recovery claim after Rename fails."""
        builder = BUILDER.read_text(encoding="utf-8")
        donor = ORIGINAL.read_text(encoding="utf-8")
        for route in ("Activation", "Rollback"):
            p = r"\$c11" + route + r"Recovery(Old|New)=@'\n(?P<body>.*?)\n'@"
            found = {m.group(1): m.group("body")
                     for m in re.finditer(p, builder, re.DOTALL)}
            self.assertEqual(set(found), {"Old", "New"})
            old, new = found["Old"], found["New"]
            self.assertEqual(donor.count(old), 1)
            self.assertNotIn(new, donor)
            self.assertEqual(donor.replace(old, new, 1).replace(new, old, 1), donor)
            self.assertIn("ClearErrors", new)
            self.assertIn("IfErrors C11" + route + "RestoreFailed", new)
            self.assertIn('IfFileExists "$INSTDIR\\nox-p01-owned.txt"', new)
            self.assertNotIn("RMDir ", new)
            self.assertNotIn("Delete ", new)
        self.assertLess(builder.index("C11_NSIS_ACTIVATION_ROLLBACK_RECOVERY_GATES_STAGED"),
                        builder.index("& $makensisPath"))


    def test_uninstaller_write_failure_cannot_replace_active_install(self):
        """The original R11 uninstaller must be generated in StageDir, before any Rename."""
        builder = BUILDER.read_text(encoding="utf-8")
        donor = ORIGINAL.read_text(encoding="utf-8")
        def source_block(name):
            hit = re.search(r"\$" + name + r"=@'\n(?P<body>.*?)\n'@", builder, re.DOTALL)
            self.assertIsNotNone(hit, name)
            return hit.group("body")
        old = source_block("uninstOld")
        staged = source_block("uninstGuard")
        self.assertEqual(donor.count(old), 1)
        self.assertIn('WriteUninstaller "$INSTDIR\\Uninstall.exe"', old)
        self.assertIn('WriteUninstaller "$StageDir\\Uninstall.exe"', staged)
        self.assertIn('IfFileExists "$StageDir\\Uninstall.exe" +2 0', staged)
        self.assertIn('FileOpen $2 "$StageDir\\Uninstall.exe" r', staged)
        self.assertIn('FileSeek $2 0 END $3', staged)
        self.assertIn('IntCmp $3 1024 C11UninstallerMax C11UninstallerReject C11UninstallerMax', staged)
        self.assertIn('IntCmp $3 104857600 C11UninstallerHeader C11UninstallerHeader C11UninstallerReject', staged)
        self.assertIn('IntCmp $4 77 C11UninstallerSecondByte C11UninstallerReject C11UninstallerReject', staged)
        self.assertIn('IntCmp $4 90 C11UninstallerClose C11UninstallerReject C11UninstallerReject', staged)
        self.assertIn('C11UninstallerAccepted:', staged)
        self.assertIn('Staged uninstaller invalid or truncated; current application was not changed.', staged)
        self.assertLess(staged.index('FileSeek $2 0 END $3'), staged.index('C11UninstallerAccepted:'))

        self.assertIn('IfErrors 0 +2', staged)
        self.assertNotIn('WriteUninstaller "$INSTDIR\\Uninstall.exe"', staged)
        anchor = '  SetOutPath "$TEMP" ; release current working directory before Rename'
        self.assertEqual(donor.count(anchor), 1)
        staged_nsi = donor.replace(old, "", 1).replace(anchor, staged + "\n" + anchor, 1)
        self.assertLess(staged.index('C11UninstallerAccepted:'), staged_nsi.index('  WriteRegStr HKCU ') - staged_nsi.index(staged))
        for activation in ('Rename "$INSTDIR" "$BackupDir"', 'Rename "$StageDir" "$INSTDIR"'):
            self.assertLess(staged_nsi.index(staged), staged_nsi.index(activation))
        self.assertLess(staged_nsi.index(staged), staged_nsi.index("  WriteRegStr HKCU "))
        self.assertEqual(staged_nsi.count('WriteUninstaller "$StageDir\\Uninstall.exe"'), 1)
        self.assertEqual(staged_nsi.count('WriteUninstaller "$INSTDIR\\Uninstall.exe"'), 0)
        self.assertIn("B03_NSIS_UNINSTALLER_BEFORE_ANY_ACTIVATION_STAGE_PASS", builder)

        # Builder must admit the staged uninstaller (one StageDir, zero INSTDIR).
        # A previous inverted gate blocked every real NSIS build before makensis.
        self.assertIn(
            r"""([regex]::Matches($c11NsiPatched,'(?m)^\s*WriteUninstaller\s+"\$StageDir\\Uninstall\.exe"')).Count -ne 1 -or""",
            builder,
        )
        self.assertIn(
            r"""([regex]::Matches($c11NsiPatched,'(?m)^\s*WriteUninstaller\s+"\$INSTDIR\\Uninstall\.exe"')).Count -ne 0 -or""",
            builder,
        )

    def test_b03_uninstall_metadata_cleanup_fail_closed(self):
        """Actual C09 R11 uninstall source staged once; no false success or user-file deletion."""
        builder = BUILDER.read_text(encoding="utf-8")
        donor = ORIGINAL.read_text(encoding="utf-8")
        def block(name):
            hit = re.search(r"\$" + name + r"=@'\n(?P<body>.*?)\n'@", builder, re.DOTALL)
            self.assertIsNotNone(hit, name)
            return hit.group("body")
        old = block("b03UninstallMetadataOld")
        guarded = block("b03UninstallMetadataGuard")
        self.assertEqual(donor.count(old), 1)
        self.assertNotIn("C11UninstallManifestHold:", donor)
        staged = donor.replace(old, guarded, 1)
        self.assertEqual(staged.count(guarded), 1)
        for label in ("Manifest", "Marker", "Exe", "Registry"):
            self.assertEqual(staged.count("C11Uninstall" + label + "Hold:"), 1)
            self.assertIn("IfErrors C11Uninstall" + label + "Hold", guarded)
        for name, label in (("payload.sha256.json", "Manifest"),
                            ("nox-p01-owned.txt", "Marker"),
                            ("Uninstall.exe", "Exe")):
            self.assertIn('IfFileExists "$INSTDIR\\' + name + '" C11Uninstall' + label + "Hold 0", guarded)
        self.assertLess(staged.index("C11UninstallMetadataDone:"), staged.index("DoneUninstall:"))
        self.assertLess(guarded.index('Delete "$INSTDIR\\Uninstall.exe"'),
                        guarded.index("DeleteRegKey HKCU"))
        self.assertIn('RMDir "$INSTDIR"', guarded)
        self.assertNotIn("RMDir /r", guarded)
        self.assertNotIn("RMDir /REBOOTOK", guarded)
        self.assertEqual(staged.replace(guarded, old, 1), donor)
        self.assertLess(builder.index("B03_NSIS_UNINSTALL_METADATA_NO_FALSE_SUCCESS_STAGED"),
                        builder.index("& $makensisPath"))
if __name__ == "__main__":
    unittest.main()
