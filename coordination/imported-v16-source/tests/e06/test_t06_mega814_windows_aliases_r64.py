"""Original NOX MEGA814 physical staging rejects Windows name aliases.

Source regression only. No GUI, native SID/ACL or independent E07 claim.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coordination/e06"))
import t06_local_onehost_bridge as bridge


class OriginalMega814WindowsNames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "original-14"
        self.folder.mkdir()
        self.entries = []
        for index in range(14):
            name = f"asset-{index:02d}.png"
            raw = f"NOX-original-fixture-{index}".encode("ascii")
            (self.folder / name).write_bytes(raw)
            self.entries.append({"name": name, "bytes": len(raw),
                                 "sha256": hashlib.sha256(raw).hexdigest()})

    def test_canonical_original_fourteen_still_pass(self):
        self.assertEqual(bridge.verify_mega814_payload_files(
            self.folder, {"files": self.entries}), 14)

    def test_unsafe_windows_names_hold_before_reading_asset(self):
        invalid = ("CON.png", "nul.txt", "PRN", "AUX.tar", "COM1.dll",
                   "LPT9.css", "COM\u00b9.js", "CONOUT$.png",
                   "original.png.", "e\u0301.png", "bad\x01.png", ".hidden")
        for bad in invalid:
            with self.subTest(name=repr(bad)):
                altered = [dict(x) for x in self.entries]
                altered[0]["name"] = bad
                with self.assertRaisesRegex(RuntimeError,
                        "NOX_MEGA814_RESOURCE_NAME_INVALID_OR_DUPLICATE"):
                    bridge.verify_mega814_payload_files(
                        self.folder, {"files": altered})

    def test_case_fold_duplicate_still_hold(self):
        altered = [dict(x) for x in self.entries]
        altered[1]["name"] = altered[0]["name"].upper()
        with self.assertRaisesRegex(RuntimeError,
                "NOX_MEGA814_RESOURCE_NAME_INVALID_OR_DUPLICATE"):
            bridge.verify_mega814_payload_files(self.folder, {"files": altered})


if __name__ == "__main__":
    unittest.main()
