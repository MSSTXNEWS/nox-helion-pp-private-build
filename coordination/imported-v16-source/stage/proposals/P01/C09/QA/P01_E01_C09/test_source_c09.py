"""Offline structural regression guard; native PowerShell runs separately on Windows CI."""
import hashlib
import os
from pathlib import Path
import re
import unittest

R = Path(__file__).resolve().parents[2]
I = R/'Installer'
read=lambda p:p.read_text(encoding='utf-8')

class Guard(unittest.TestCase):
    def test_all_or_nothing_preflight_before_first_remove(self):
        s=read(I/'Remove-InstalledPayload.ps1')
        self.assertIn('# PHASE 1',s)
        self.assertIn('# PHASE 2',s)
        self.assertLess(s.index('foreach ($f in @($m.files))'),s.index('foreach ($entry in $checked)'))
        self.assertLess(s.index('foreach ($entry in $checked)'),s.index('foreach ($path in $verified) {\n  Remove-Item'))
        self.assertIn('Assert-VerifiedEntry $entry',s)
        self.assertIn('P01_UNINSTALL_MODIFIED_FILE',s)

    def test_owner_guard_and_fail_closed_manifest(self):
        s=read(I/'Remove-InstalledPayload.ps1')
        self.assertIn('P01_UNINSTALL_INVALID_OWNER_MARKER',s)
        self.assertIn('P01_UNINSTALL_EMPTY_MANIFEST',s)
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
        self.assertIn('P01_BUILD_OUTPUT_INSIDE_SOURCE',s)
        self.assertIn('P01_BUILD_UNSAFE_OUTPUT_PARENT',s)
        self.assertIn('P01_SKIP_PUBLISH_DISABLED_FOR_RELEASE_SAFETY',s)
        self.assertNotIn('Invoke-WebRequest',s)

    def test_manifest_file_and_rows(self):
        s=read(I/'Verify-Payload.ps1')
        for q in ['unsafe manifest','missing run ID','missing version','bad manifest row or SHA','unsafe Windows component','file count mismatch']:
            self.assertIn(q,s)

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

    def test_all_original_assets_unchanged(self):
        import zipfile
        orig=Path(os.environ.get('NOX_P01_C08_DONOR','/mnt/data/files/NOX_V16_E01_P01_C08_NOLOSS_HANDOFF.zip'))
        if not orig.exists(): self.skipTest('original ZIP available only in developer workspace')
        with zipfile.ZipFile(orig) as z:
            for name in ['R11/Assets/home.png','R11/Assets/menu.png','R11/Assets/menu_sections.png','R11/Assets/core01.png','R11/MainWindow.xaml','R11/MainWindow.xaml.cs','R11/Assets/index.html','R11/Packages/P04/train_qlora.py']:
                self.assertEqual(hashlib.sha256((R/name.removeprefix('R11/')).read_bytes()).hexdigest(),hashlib.sha256(z.read(name)).hexdigest(),name)

if __name__=='__main__':unittest.main()
