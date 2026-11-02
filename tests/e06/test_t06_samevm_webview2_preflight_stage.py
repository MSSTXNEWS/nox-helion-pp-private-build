"""Focused same-VM WebView2 staging regression (no network, no Windows PASS)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
DONOR = ROOT / "coordination/e06/build_onehost_installer.ps1"
spec = importlib.util.spec_from_file_location("t06_compile_owner_webview2_stage", SRC)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
LEGACY = (
    "# Official Microsoft WebView2 runtime detection uses registry pv, not Edge browser presence.\n"
    "$installed=$false\n"
    "foreach ($registryPath in @('Registry::HKEY_CURRENT_USER\\Software\\Microsoft\\EdgeUpdate\\Clients',"
    "'Registry::HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients')) {\n"
    "  $pv=(Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue).pv\n"
    "  if ($pv -and ([version]$pv).Major -gt 0) { $installed=$true }\n"
    "}\n"
    "if (-not $installed) { throw 'P01_WEBVIEW2_RUNTIME_MISSING: Install official Microsoft Evergreen WebView2 Runtime first; no silent download.' }\n"
    "Write-Host 'OTHER_ORIGINAL_INSTALLER_POLICY_UNCHANGED'\n"
)

class WebView2SameVmStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.r11 = self.root / "R11"
        path = self.r11 / "Installer"
        path.mkdir(parents=True)
        self.preflight = path / "Preflight-InstallPath.ps1"
        self.preflight.write_bytes(LEGACY.encode("utf-8"))
    def test_real_existing_donor_stages_runtime_gate_without_changing_owner_tail(self):
        before = self.preflight.read_bytes()
        owner.stage_exact_owner_webview2_registry_views(self.r11, DONOR)
        after = self.preflight.read_text("utf-8")
        self.assertNotEqual(before, self.preflight.read_bytes())
        for token in ("Registry32", "Registry64", "CurrentUser", "LocalMachine",
                      "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
                      "P01_WEBVIEW2_RUNTIME_MISSING", "OTHER_ORIGINAL_INSTALLER_POLICY_UNCHANGED"):
            self.assertIn(token, after)
        self.assertEqual(after.count("P01_WEBVIEW2_RUNTIME_MISSING"), 1)
        with self.assertRaisesRegex(RuntimeError, "ANCHOR_HOLD"):
            owner.stage_exact_owner_webview2_registry_views(self.r11, DONOR)
    def test_crlf_and_bom_are_preserved(self):
        self.preflight.write_bytes(b"\xef\xbb\xbf" + LEGACY.replace("\n", "\r\n").encode("utf-8"))
        owner.stage_exact_owner_webview2_registry_views(self.r11, DONOR)
        data = self.preflight.read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
    def test_drifted_legacy_fails_without_mutation(self):
        original = LEGACY.replace("Get-ItemProperty", "UnexpectedRegistryReader")
        self.preflight.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "PREIMAGE_HOLD"):
            owner.stage_exact_owner_webview2_registry_views(self.r11, DONOR)
        self.assertEqual(original, self.preflight.read_text("utf-8"))
    def test_unrelated_builder_changes_keep_exact_webview2_gate(self):
        benign = self.root / "changed-builder-scaffolding.ps1"
        benign.write_text(DONOR.read_text("utf-8") +
                          "\n# Independent E07/PS5.1 metadata; not part of runtime gate.\n",
                          encoding="utf-8")
        owner.stage_exact_owner_webview2_registry_views(self.r11, benign)
        staged = self.preflight.read_text("utf-8")
        self.assertIn("[Microsoft.Win32.RegistryView]::Registry32", staged)
        self.assertIn("[Microsoft.Win32.RegistryView]::Registry64", staged)
        self.assertIn("P01_WEBVIEW2_RUNTIME_MISSING", staged)

    def test_tampered_canonical_donor_fails_without_mutation(self):
        changed = DONOR.read_text("utf-8").replace(
            "[Microsoft.Win32.RegistryView]::Registry32",
            "[Microsoft.Win32.RegistryView]::Registry32_TAMPER", 1)
        tampered = self.root / "tampered.ps1"
        tampered.write_text(changed, "utf-8")
        with self.assertRaisesRegex(RuntimeError, "CANONICAL_DONOR_BLOCK_SHA_HOLD"):
            owner.stage_exact_owner_webview2_registry_views(self.r11, tampered)
        self.assertEqual(LEGACY.encode("utf-8"), self.preflight.read_bytes())

if __name__ == "__main__":
    unittest.main()
