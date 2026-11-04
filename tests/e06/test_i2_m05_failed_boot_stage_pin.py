"""Exact-source staging regression for the M05 failed-A1-boot lease rollback donor.

This test is intentionally fail-closed: it must fail until I0 atomically
integrates the M05 owner donor AND the matching E06 stage SHA pin.
No native owner capability is fabricated or asserted by this test.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "coordination/e06/stage_native_stdio.py"
OWNER = ROOT / "coordination/e06/e06_native_stdio_owner.py"
EXPECTED_OWNER_BLOB = "037a2c8a2e769779d657df5ccdccf61d1968a992"
OWNER_DEST = "helion/e06_native_stdio_owner.py"


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class M05FailedBootStagePin(unittest.TestCase):
    def test_exact_owner_pin_is_staged(self) -> None:
        source = STAGE.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(STAGE))
        entry = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "ADDONS" for t in node.targets)
        )
        addons = ast.literal_eval(entry.value)
        matches = [
            (rel, dest, sha) for rel, dest, sha in addons
            if rel == "coordination/e06/e06_native_stdio_owner.py"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1], OWNER_DEST)
        self.assertEqual(matches[0][2], EXPECTED_OWNER_BLOB)
        self.assertEqual(git_blob(OWNER.read_bytes()), EXPECTED_OWNER_BLOB)

    def test_failed_native_a1_boot_releases_lease_without_bypassing_hold(self) -> None:
        code = OWNER.read_text(encoding="utf-8")
        ast.parse(code, filename=str(OWNER))
        self.assertIn("except BaseException:", code)
        self.assertIn("with lease_lock:", code)
        self.assertIn('leases.pop((session.chat_id, "evolution.autonomy.read"), None)', code)
        self.assertIn("A1_NATIVE_SIGNED_COMPONENTS_FACTORY_HOLD", code)


if __name__ == "__main__":
    unittest.main()
