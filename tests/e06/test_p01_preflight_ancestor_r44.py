"""R44: original P01 install preflight rejects ancestor junctions ABOVE LOCALAPPDATA.

This is a source/no-loss regression on non-Windows; the disposable physical
junction and PowerShell invocation execute ONLY on an actual Windows host.
No installed WPF/IPC/E07 PASS is inferred from these source checks.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "stage/proposals/P01/C09/Installer/Preflight-InstallPath.ps1"
PACKAGE = ROOT / "coordination/e06/t06_package_original_onehost.py"
SMOKE = ROOT / "coordination/e06/t06_samevm_installed_smoke.py"


class P01PreflightVolumeRootR44(unittest.TestCase):
    def test_ancestor_guard_reaches_drive_root(self):
        source = PREFLIGHT.read_text("utf-8-sig")
        first = source.index("# Never stage through a junction")
        last = source.index("# Verify the existing installer-owned marker")
        guard = source[first:last]
        self.assertIn("while ($cursor)", guard)
        self.assertIn("[IO.Path]::GetDirectoryName($cursor)", guard)
        self.assertIn("P01_INSTALL_REPARSE_ANCESTOR", guard)
        self.assertIn("-not $node.PSIsContainer", guard)
        self.assertIn("[IO.FileAttributes]::ReparsePoint", guard)
        self.assertNotIn("$localRoot", guard)
        self.assertNotIn("StartsWith($localRoot", guard)
        for owner_state in ("__p01_stage", "__p01_previous", "__p01_rollback_saved"):
            self.assertIn(owner_state, guard)

    def test_original_registry_consent_and_marker_preserved(self):
        source = PREFLIGHT.read_text("utf-8-sig")
        for required in ("P01_INSTALL_ROOT_INVALID", "P01_INSTALL_MARKER_INVALID",
                         "P01_WEBVIEW2_RUNTIME_MISSING", "Registry32",
                         "F3017226-FE2A-4295-8BDF-00C3A9A7E4C5",
                         "no silent download."):
            with self.subTest(required=required):
                self.assertIn(required, source)

    def test_staging_pins_follow_exact_git_blob(self):
        raw = PREFLIGHT.read_bytes()
        git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\\0" + raw).hexdigest()
        package_text = PACKAGE.read_text("utf-8")
        smoke_text = SMOKE.read_text("utf-8")
        self.assertIn('P01_REVIEWED_PREFLIGHT_GIT_BLOB = "' + git_blob + '"', package_text)
        self.assertIn('source.get("webview2_p01_source_git_blob")==\\n'
                      '                "' + git_blob + '"', smoke_text)

    @unittest.skipUnless(os.name == "nt", "Real PowerShell+junction requires Windows")
    def test_native_parent_junction_denied_even_above_localappdata(self):
        with tempfile.TemporaryDirectory(prefix="nox-p01-r44-") as work:
            root = Path(work)
            physical = root / "physical-profile"
            junction = root / "junction-profile"
            physical.mkdir()
            try:
                link = subprocess.run(
                    ["cmd.exe", "/d", "/c", 'mklink /J "' + str(junction) + '" "' + str(physical) + '"'],
                    capture_output=True, text=True, timeout=30, check=False)
                self.assertEqual(link.returncode, 0, link.stderr + link.stdout)
                env = dict(os.environ)
                env["LOCALAPPDATA"] = str(junction / "AppData" / "Local")
                target = str(junction / "AppData" / "Local" / "Programs" / "NOX HELION")
                check = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive",
                     "-ExecutionPolicy", "Bypass", "-File", str(PREFLIGHT),
                     "-InstallRoot", target],
                    env=env, capture_output=True, text=True, timeout=30, check=False)
                self.assertNotEqual(check.returncode, 0)
                self.assertIn("P01_INSTALL_REPARSE_ANCESTOR",
                              check.stdout + "\\n" + check.stderr)
            finally:
                if junction.exists() or junction.is_symlink():
                    os.rmdir(junction)


if __name__ == "__main__":
    unittest.main()
