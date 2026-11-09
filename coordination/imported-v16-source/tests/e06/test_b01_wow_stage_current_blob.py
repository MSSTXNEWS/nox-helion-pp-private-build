"""B01 fail-closed reviewed WOW200 Git source pin regression, SOURCE_ONLY.

No Windows release or SourceLock-729 physical acceptance inferred from this test.
The approved WOW200 UI is updated by independent original-UI owners; E06 and
manual T06 MUST pin the SAME actual stage Git blob before any disposable build.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
WOW = ROOT / "integrations/wow200/stage_wow200.py"
E06 = ROOT / "coordination/e06/build_onehost_installer.ps1"
T06 = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"


def reviewed_blob(path: Path) -> str:
    original = path.read_bytes()
    canonical = original.replace(b"\r\n", b"\n")
    if b"\r" in canonical:
        raise ValueError("B01_BARE_CR_SOURCE_HOLD")
    return hashlib.sha1(
        b"blob " + str(len(canonical)).encode("ascii") + b"\0" + canonical
    ).hexdigest()


class B01CurrentWowSourcePins(unittest.TestCase):
    def test_both_builders_pin_current_original_wow_stage(self):
        actual = reviewed_blob(WOW)
        e06 = E06.read_text(encoding="utf-8")
        t06 = T06.read_text(encoding="utf-8")
        e06_pins = re.findall(
            r"\$wowScriptBlob\s+-cne\s+'([0-9a-f]{40})'", e06)
        t06_pins = re.findall(
            r'\("WOW200","integrations/wow200/stage_wow200.py",\s*"([0-9a-f]{40})"\)', t06)
        self.assertEqual(e06_pins, [actual], "E06_D02_REVIEWED_STAGE_SOURCE_DRIFT_HOLD")
        self.assertEqual(t06_pins, [actual], "T06_D02_REVIEWED_STAGE_SOURCE_DRIFT_HOLD")

    def test_88_d02_no_loss_and_fail_closed_are_preserved(self):
        e06 = E06.read_text(encoding="utf-8")
        wow = WOW.read_text(encoding="utf-8")
        self.assertIn("$wowDeclaredCount -ne 88", e06)
        self.assertIn("$wowUniqueCount -ne 88", e06)
        self.assertIn("D02_WOW_STAGE_RECEIPT_FILESET_HOLD", e06)
        self.assertIn("D02_PINNED_STAGE_SCRIPT_SHA_HOLD", e06)
        self.assertIn("D02_ORIGINAL_INDEX_SHA_NOT_IN_SOURCELOCK", e06)
        self.assertIn("CANONICAL_D02_SHA_HOLD", wow)
        self.assertIn("WOW_STAGE_SOURCE_OR_DESTINATION_COLLISION_HOLD", wow)
        self.assertIn('"release_accepted":False', wow)

    def test_one_byte_stage_source_drift_changes_git_identity(self):
        payload = WOW.read_bytes().replace(b"\r\n", b"\n")
        digest = reviewed_blob(WOW)
        mutation = payload + b"\n# B01 test-only unexpected drift\n"
        changed = hashlib.sha1(
            b"blob " + str(len(mutation)).encode("ascii") + b"\0" + mutation
        ).hexdigest()
        self.assertNotEqual(digest, changed)


if __name__ == "__main__":
    unittest.main()
