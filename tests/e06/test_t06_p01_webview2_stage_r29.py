"""R29: original R11 NSIS preflight must use reviewed P01 HKLM Registry32.
Pure source and staging tests; never an installed WebView2/E07 PASS.
"""
from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "coordination/e06/t06_package_original_onehost.py"
APPROVED = ROOT / "stage/proposals/P01/C09/Installer/Preflight-InstallPath.ps1"
SMOKE = ROOT / "coordination/e06/t06_samevm_installed_smoke.py"
spec = importlib.util.spec_from_file_location("nox_r29_p01_package", PKG)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OriginalR11WebView2StagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reviewed = APPROVED.read_bytes().replace(b"\r\n", b"\n").decode("utf-8-sig")
        if (cls.reviewed.count(module.P01_WEBVIEW2_START) != 1 or
            cls.reviewed.count(module.P01_WEBVIEW2_END) != 1 or
            cls.reviewed.count("# E06: real Windows native winreg found") != 1):
            raise AssertionError("R29_REVIEWED_P01_SOURCE_DRIFT")
        first = cls.reviewed.index("# E06: real Windows native winreg found")
        last = cls.reviewed.index(module.P01_WEBVIEW2_END)
        cls.legacy = cls.reviewed[:first] + cls.reviewed[last:]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.owner = self.root / "Original-R11-Preflight-InstallPath.ps1"

    def test_legacy_owner_replaces_only_webview2_and_is_idempotent(self):
        self.owner.write_text(self.legacy, encoding="utf-8")
        first = module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        self.assertTrue(first["changed"])
        self.assertFalse(first["runtime_installed_verified"])
        self.assertFalse(first["e07_accepted"])
        self.assertEqual(self.owner.read_text("utf-8"), self.reviewed)
        second = module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        self.assertFalse(second["changed"])
        self.assertEqual(first["sha256"], second["sha256"])

    def test_original_bom_crlf_preserved_and_reviewed_crlf_idempotent(self):
        marker = b"\xef\xbb\xbf"
        self.owner.write_bytes(marker + self.legacy.replace("\n", "\r\n").encode())
        module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        staged = self.owner.read_bytes()
        self.assertEqual(staged, marker + self.reviewed.replace("\n", "\r\n").encode())
        second = module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        self.assertFalse(second["changed"])
        self.assertEqual(self.owner.read_bytes(), staged)

    def test_unknown_owner_denied_without_write(self):
        wrong = self.legacy.replace("Get-ItemProperty", "Untrusted-Ingress")
        self.owner.write_text(wrong, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_OR_PARTIALLY_PATCHED"):
            module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        self.assertEqual(self.owner.read_text("utf-8"), wrong)

    def test_unpinned_approved_source_denied_without_write(self):
        self.owner.write_text(self.legacy, encoding="utf-8")
        tampered = self.root / "tampered.ps1"
        tampered.write_text(self.reviewed + "\n# drift", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "REVIEWED_SOURCE_GIT_BLOB_DRIFT"):
            module.stage_reviewed_webview2_preflight(self.owner, tampered)
        self.assertEqual(self.owner.read_text("utf-8"), self.legacy)

    def test_missing_anchor_denied_without_write(self):
        wrong = self.legacy.replace(module.P01_WEBVIEW2_START, "# replaced")
        self.owner.write_text(wrong, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_ANCHOR_DRIFT"):
            module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        self.assertEqual(self.owner.read_text("utf-8"), wrong)

    def test_already_e06_staged_registry32_is_byte_verified_not_overwritten(self):
        donor = (ROOT / "coordination/e06/build_onehost_installer.ps1").read_text("utf-8")
        begin = "$webviewReplacement=@'\n"
        end = "\n'@"
        self.assertEqual(donor.count(begin), 1)
        inner = donor.split(begin, 1)[1].split(end, 1)[0] + "\n"
        start = self.legacy.index(module.P01_WEBVIEW2_START)
        stop = self.legacy.index(module.P01_WEBVIEW2_END)
        staged = self.legacy[:start] + inner + self.legacy[stop:]
        self.owner.write_text(staged, encoding="utf-8")
        result = module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        self.assertFalse(result["changed"])
        self.assertFalse(result["e07_accepted"])
        self.assertEqual(result["e06_donor_git_blob"],
                         "cd53dcd0171b3082a602e347d73bb311ee2ef370")
        self.assertEqual(self.owner.read_text("utf-8"), staged)

    def test_unpinned_alternate_preflight_is_rejected_without_mutation(self):
        donor = (ROOT / "coordination/e06/build_onehost_installer.ps1").read_text("utf-8")
        inner = donor.split("$webviewReplacement=@'\n",1)[1].split("\n'@",1)[0] + "\n"
        start = self.legacy.index(module.P01_WEBVIEW2_START)
        stop = self.legacy.index(module.P01_WEBVIEW2_END)
        staged = (self.legacy[:start] + inner + self.legacy[stop:]).replace(
            "Registry32", "Registry32_TAMPER",1)
        self.owner.write_text(staged, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "E06_STAGED_BYTES_DRIFT"):
            module.stage_reviewed_webview2_preflight(self.owner, APPROVED)
        self.assertEqual(self.owner.read_text("utf-8"), staged)

    def test_source_lock_and_real_t06_nsis_wiring(self):
        source = PKG.read_text("utf-8")
        smoke = SMOKE.read_text("utf-8")
        self.assertIn('installer_dir/"Preflight-InstallPath.ps1"', source)
        self.assertIn('"webview2_p01_preflight_sha256":webview_proof["sha256"]', source)
        self.assertIn('BUILD/"R11/Installer/Preflight-InstallPath.ps1"', smoke)
        self.assertIn("T06_ORIGINAL_NSIS_WEBVIEW2_PREFLIGHT_SOURCELOCK_HOLD", smoke)
        self.assertIn('require(fresh["code"]==0,"T06_WEBVIEW2_RUNTIME_STILL_MISSING_AFTER_INSTALL")', smoke)


if __name__ == "__main__":
    unittest.main()
