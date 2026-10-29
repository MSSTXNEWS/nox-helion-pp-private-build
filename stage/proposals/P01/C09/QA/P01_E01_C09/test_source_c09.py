"""Offline source guards for C11 + R29; no native execution is implied."""
import hashlib
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

R = Path(__file__).resolve().parents[2]
I = R/'Installer'
read=lambda p:p.read_text(encoding='utf-8')

class Guard(unittest.TestCase):
    def test_all_or_nothing_preflight_before_first_remove(self):
        s=read(I/'Remove-InstalledPayload.ps1')
        self.assertIn('# PHASE 1',s)
        self.assertIn('# PHASE 2',s)
        self.assertLess(s.index('foreach ($f in @($m.files))'),s.index('foreach ($entry in $checked)'))
        phase2=s.index('# PHASE 2')
        phase3=s.index('# PHASE 3')
        delete=s.index('Remove-Item -LiteralPath $entry.Full')
        self.assertLess(phase2,phase3)
        self.assertLess(phase3,delete)
        self.assertRegex(s[phase2:phase3],r'foreach \(\$entry in \$checked\)\s*\{\s*try \{ Assert-VerifiedEntry \$entry \}')
        self.assertIn('P01_UNINSTALL_FILE_CHANGED_DURING_COMMIT',s[phase2:phase3])
        self.assertRegex(s[phase3:delete],r'foreach \(\$entry in \$checked\)\s*\{\s*# C11:[^\n]*\n\s*Assert-VerifiedEntry \$entry\s*$')
        self.assertIn("if (-not $registered.Contains('NOX.P01.Shell.exe'))",s[:phase2])
        self.assertNotRegex(s[:phase3],r'(?m)^\s*Remove-Item\b')
        self.assertIn('P01_UNINSTALL_MODIFIED_FILE',s)

    def test_owner_guard_and_fail_closed_manifest(self):
        s=read(I/'Remove-InstalledPayload.ps1')
        self.assertIn('P01_UNINSTALL_INVALID_OWNER_MARKER',s)
        self.assertIn("if ($null -eq $m.files -or @($m.files).Count -lt 1 -or @($m.files).Count -gt 50000) { throw 'P01_UNINSTALL_INVALID_MANIFEST_LENGTH' }",s)
        self.assertIn('P01_UNINSTALL_DUPLICATE_PATH',s)
        self.assertIn('P01_UNINSTALL_METADATA_REPARSE',s)
        self.assertIn('TryParse',s)

    def test_path_and_ads_block(self):
        s=read(I/'Remove-InstalledPayload.ps1')
        for q in ['P01_UNINSTALL_BAD_PATH','P01_UNINSTALL_PATH_ESCAPE','ReparsePoint','COM[1-9]','[. ]$']:
            self.assertIn(q,s)

    def test_installer_update_marker_and_recovery(self):
        s=read(I/'Preflight-InstallPath.ps1')
        self.assertIn('P01_INSTALL_MARKER_INVALID',s)
        n=read(I/'NOX-HELION-Setup.nsi')
        self.assertIn('RequestExecutionLevel user',n)
        self.assertIn('__p01_rollback_saved',n)
        self.assertNotIn('RMDir /r "$INSTDIR"',n)

    def test_builder_output_and_source_protection(self):
        s=read(I/'Build-NSIS.ps1')
        overlap=s[s.index('if ($rootCandidate -ieq $sourceCanonical'):s.index('$sourceCursor=')]
        self.assertIn('P01_BUILD_SOURCE_OUTPUT_OVERLAP',overlap)
        self.assertIn("$rootCandidate.StartsWith($sourceCanonical+'\\'",overlap)
        self.assertIn("$sourceCanonical.StartsWith($rootCandidate.TrimEnd('\\')+'\\'",overlap)
        self.assertIn('P01_BUILD_UNSAFE_OUTPUT_PARENT',s)
        self.assertIn('P01_BUILD_UNSAFE_SOURCE_DIRECTORY',s)
        self.assertLess(s.index('P01_BUILD_UNSAFE_OUTPUT_PARENT'),s.index('New-Item -ItemType Directory'))
        self.assertIn('P01_SKIP_PUBLISH_DISABLED_FOR_RELEASE_SAFETY',s)
        self.assertNotIn('Invoke-WebRequest',s)

    def test_manifest_file_and_rows(self):
        s=read(I/'Verify-Payload.ps1')
        for q in ['unsafe manifest','invalid run ID','invalid version','bad manifest row or SHA','unsafe Windows component','file count mismatch']:
            self.assertIn(q,s)
        self.assertIn("$m.runId -isnot [string] -or $m.runId -ceq 'P01-UNSET'",s)
        self.assertIn("$m.runId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$'",s)
        self.assertIn("$m.version -isnot [string] -or $m.version -cnotmatch '^[0-9]{1,5}\\.[0-9]{1,5}\\.[0-9]{1,5}(\\.[0-9]{1,5})?$'",s)

    def test_prerequisites_read_only(self):
        s=read(I/'Get-P01Prerequisites.ps1')
        for q in ['python.exe','ollama.exe','git.exe','winget.exe','downloadsPerformed=0','LOCAL_PATH_ONLY']:
            self.assertIn(q,s)
        self.assertNotIn('Invoke-WebRequest',s)

    def test_native_fixture_ten_cases(self):
        s=read(R/'QA/P01_E01_C09/Test-P01Native-C09.ps1')
        self.assertEqual(s.count('$passed++'),10)
        for q in ['tampered-late','missing-late','duplicate','escape','reserved','owner-marker','bad-length','bad-digest','unknown-user-data-deleted','prerequisite-probe']:
            self.assertIn(q,s)
        self.assertIn("$records+=@([ordered]@{path='NOX.P01.Shell.exe'",s)
        self.assertIn("'clean-entrypoint-remained'",s)

    def test_verifier_rejects_deleted_safety_checks(self):
        # Mutation probes ensure the repaired verifier still catches regressions.
        cases=[
            ('Remove-InstalledPayload.ps1', 'test_all_or_nothing_preflight_before_first_remove',
             '  Assert-VerifiedEntry $entry\n  Remove-Item', '  Remove-Item'),
            ('Remove-InstalledPayload.ps1', 'test_all_or_nothing_preflight_before_first_remove',
             'try { Assert-VerifiedEntry $entry } catch', 'try { $null } catch'),
            ('Remove-InstalledPayload.ps1', 'test_owner_guard_and_fail_closed_manifest',
             '@($m.files).Count -lt 1', '@($m.files).Count -lt 0'),
            ('Build-NSIS.ps1', 'test_builder_output_and_source_protection',
             "$sourceCanonical.StartsWith($rootCandidate.TrimEnd('\\')+'\\'", "$sourceCanonical.EndsWith($rootCandidate.TrimEnd('\\')+'\\'"),
            ('Verify-Payload.ps1', 'test_manifest_file_and_rows',
             "[A-Za-z0-9._:-]{1,127}", ".*"),
        ]
        for file,method,before,after in cases:
            original=read(I/file)
            self.assertIn(before,original)
            with self.subTest(file=file,guard=method), patch(__name__+'.read',return_value=original.replace(before,after)):
                with self.assertRaises(AssertionError):getattr(Guard(method),method)()

    def test_all_original_assets_unchanged(self):
        import zipfile
        orig=Path(os.environ.get('NOX_P01_C08_DONOR','/mnt/data/files/NOX_V16_E01_P01_C08_NOLOSS_HANDOFF.zip'))
        if not orig.exists(): self.skipTest('original ZIP available only in developer workspace')
        with zipfile.ZipFile(orig) as z:
            for name in ['R11/Assets/home.png','R11/Assets/menu.png','R11/Assets/menu_sections.png','R11/Assets/core01.png','R11/MainWindow.xaml','R11/MainWindow.xaml.cs','R11/Assets/index.html','R11/Packages/P04/train_qlora.py']:
                self.assertEqual(hashlib.sha256((R/name.removeprefix('R11/')).read_bytes()).hexdigest(),hashlib.sha256(z.read(name)).hexdigest(),name)

if __name__=='__main__':unittest.main()
