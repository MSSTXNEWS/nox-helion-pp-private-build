"""Source-level regression for E06 WebView2 32-bit registry-view divergence.

This test does not replace Windows PowerShell, WPF startup, or E07. Run with:
python -m unittest discover -s tests/p01 -p test_webview2_registry32_preflight.py
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[2] /
          "stage/proposals/P01/C09/Installer/Preflight-InstallPath.ps1")


class WebView2NativeRegistryViewContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_original_install_path_and_marker_guards_preserved(self):
        self.assertIn("P01_INSTALL_ROOT_INVALID", self.source)
        self.assertIn("P01_INSTALL_REPARSE_ANCESTOR", self.source)
        self.assertIn("P01_INSTALL_MARKER_INVALID", self.source)

    def test_official_guid_and_original_provider_probes_retained(self):
        self.assertIn("Registry::HKEY_CURRENT_USER", self.source)
        self.assertIn("Registry::HKEY_LOCAL_MACHINE", self.source)
        self.assertIn("Get-ItemProperty -LiteralPath $p", self.source)
        self.assertIn("{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", self.source)

    def test_native_registry32_fallback_reads_only_official_runtime(self):
        self.assertIn("[Microsoft.Win32.RegistryHive]::LocalMachine", self.source)
        self.assertIn("[Microsoft.Win32.RegistryView]::Registry32", self.source)
        self.assertIn("OpenSubKey(", self.source)
        self.assertIn("SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", self.source)
        self.assertIn("GetValueKind('pv') -eq [Microsoft.Win32.RegistryValueKind]::String", self.source)
        self.assertIn("[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames", self.source)

    def test_invalid_version_cannot_set_installed(self):
        self.assertIn("$pv32 -is [string]", self.source)
        self.assertIn("$runtimeVersion32=[version]$pv32", self.source)
        self.assertIn("if ($runtimeVersion32.Major -gt 0)", self.source)
        self.assertIn("} catch { } finally {", self.source)
        self.assertIn("$client32.Dispose()", self.source)

    def test_missing_runtime_remains_strict_hold(self):
        denial = "if (-not $installed) { throw 'P01_WEBVIEW2_RUNTIME_MISSING:"
        self.assertEqual(self.source.count(denial), 1)
        self.assertLess(self.source.index("RegistryView]::Registry32"), self.source.index(denial))
        self.assertIn("no silent download.", self.source)
        self.assertNotIn("$installed=$true # bypass", self.source)


if __name__ == "__main__":
    unittest.main()
