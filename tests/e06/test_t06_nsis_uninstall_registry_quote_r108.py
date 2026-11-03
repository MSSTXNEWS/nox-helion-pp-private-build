"""R108 source-only original NSIS UninstallString quote/guard regression."""
from pathlib import Path
import unittest
import re
ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
REVIEWED = ROOT / "stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi"
BAD = "  WriteRegStr HKCU \"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_ID}\" \"UninstallString\" '\\\"$INSTDIR\\Uninstall.exe\\\"'"
APPROVED = "  WriteRegStr HKCU \"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_ID}\" \"UninstallString\" '\"$INSTDIR\\Uninstall.exe\"'"
def guarded_stage(sample):
    # Offline mirror of the original PowerShell's bounded exact-line admission.
    candidates = list(re.finditer(r'(?m)^[ \t]*WriteRegStr[ \t]+[^\r\n]*"UninstallString"[ \t]+[^\r\n]*', sample))
    if len(candidates) != 1:
        raise ValueError("P01_NSIS_UNINSTALL_REGISTRY_PREIMAGE_HOLD")
    match = candidates[0]
    raw = match.group(0)
    body = raw.lstrip(" \t")
    canonical = APPROVED.lstrip(" \t")
    pivot = canonical.index('"UninstallString" ') + len('"UninstallString" ')
    key = canonical[:pivot]
    allowed = (
        BAD.lstrip(" \t"), canonical,
        key + '"\\\"$INSTDIR\\Uninstall.exe\\\""',
        key + '"$INSTDIR\\Uninstall.exe"',
    )
    if body not in allowed:
        raise ValueError("P01_NSIS_UNINSTALL_REGISTRY_PREIMAGE_HOLD")
    approved_line = raw[:len(raw) - len(body)] + canonical
    result = sample[:match.start()] + approved_line + sample[match.end():]
    post = list(re.finditer(r'(?m)^[ \t]*WriteRegStr[ \t]+[^\r\n]*"UninstallString"[ \t]+[^\r\n]*', result))
    if len(post) != 1 or post[0].group(0) != approved_line:
        raise ValueError("P01_NSIS_UNINSTALL_REGISTRY_QUOTE_HOLD")
    return result
class TestNSISUninstallRegistryQuoteR108(unittest.TestCase):
    def test_malformed_original_is_repaired_without_other_text_loss(self):
        source = "prefix\n" + BAD + "\nsuffix"
        self.assertEqual(guarded_stage(source), "prefix\n" + APPROVED + "\nsuffix")
    def test_reviewed_original_is_idempotent(self):
        self.assertEqual(guarded_stage(APPROVED), APPROVED)
    def test_unknown_or_multiple_source_lines_are_refused(self):
        for sample in (BAD * 2, APPROVED * 2, "unowned", BAD + APPROVED):
            with self.subTest(sample=sample[:40]):
                with self.assertRaises(ValueError): guarded_stage(sample)
    def test_verified_r11_quote_variants_and_indentation(self):
        key = APPROVED.lstrip(" \t").split('"UninstallString" ')[0] + '"UninstallString" '
        for indent, value in (
            ("    ", BAD.lstrip(" \t")),
            ("\t", APPROVED.lstrip(" \t")),
            (" ", key + '"\\\"$INSTDIR\\Uninstall.exe\\\""'),
            ("  ", key + '"$INSTDIR\\Uninstall.exe"'),
        ):
            with self.subTest(indent=repr(indent), value=value):
                original = "before\r\n" + indent + value + "\r\nafter"
                expected = "before\r\n" + indent + APPROVED.lstrip(" \t") + "\r\nafter"
                self.assertEqual(guarded_stage(original), expected)
    def test_other_owner_or_unsafe_registry_value_refused(self):
        key = APPROVED.lstrip(" \t").split('"UninstallString" ')[0] + '"UninstallString" '
        for source in (
            key + '"calc.exe"',
            key.replace("HKCU", "HKLM") + '"$INSTDIR\\Uninstall.exe"',
            key.replace("APP_ID", "OTHER") + '"$INSTDIR\\Uninstall.exe"',
            APPROVED + "\n" + key + '"calc.exe"',
        ):
            with self.subTest(source=source[:60]):
                with self.assertRaises(ValueError):
                    guarded_stage(source)
    def test_builder_stages_after_c11_before_makensis(self):
        src = BUILDER.read_text(encoding="utf-8-sig")
        marker = "[IO.File]::WriteAllText($c11NsiPath,$c11NsiPatched"
        self.assertEqual(src.count("P01_NSIS_UNINSTALL_REGISTRY_QUOTE_STAGE_PASS"), 1)
        self.assertEqual(src.count("P01_NSIS_UNINSTALL_REGISTRY_PREIMAGE_HOLD"), 1)
        self.assertLess(src.index("C11_NSIS_ROLLBACK_FENCE_STAGE_HOLD"), src.index("$uninstallRegistryBad="))
        self.assertLess(src.index("P01_NSIS_UNINSTALL_REGISTRY_QUOTE_STAGE_PASS"), src.index(marker))
        self.assertLess(src.index(marker), src.index("& $makensisPath /V2"))
        self.assertIn("P01_C09_ORIGINAL_R11_PREIMAGE_SHA_HOLD", src)
    def test_reviewed_c09_matches_approved_registry_contract(self):
        txt = REVIEWED.read_text(encoding="utf-8-sig")
        self.assertEqual(txt.count(APPROVED), 1)
        self.assertNotIn(BAD, txt)
if __name__ == "__main__": unittest.main()
