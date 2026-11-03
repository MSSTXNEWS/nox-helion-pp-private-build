"""Fast SOURCE-only guard for original Express E06 <-> MENU10 SHA pins.

This is not GUI, installed setup, or E07 acceptance. It detects stale owner
script pins before the much longer Windows NSIS job is scheduled.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MENU = ROOT / "coordination" / "mega814"
BUILDER = ROOT / "coordination" / "e06" / "build_onehost_installer.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "nox-v16-e06-d02-onehost.yml"

OWNER_FILES = (
    ("menuStage", "stage_original_r11.py"),
    ("menuGate", "qa_source_gate.py"),
    ("menuPublisher", "publish_onehost_payload.py"),
)


def canonical_git_blob(raw: bytes) -> str:
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ValueError("MENU10_BARE_CR_SOURCE_HOLD")
    canonical = raw.replace(b"\r\n", b"\n")
    return hashlib.sha1(
        b"blob " + str(len(canonical)).encode("ascii") + b"\0" + canonical
    ).hexdigest()


def expected_pin(builder: str, label: str) -> str:
    matches = re.findall(
        r"@\{Path=\$" + re.escape(label) + r";Blob='([0-9a-f]{40})'\}",
        builder,
    )
    if len(matches) != 1:
        raise ValueError("MENU10_" + label + "_PIN_MISSING_OR_DUPLICATE_HOLD")
    return matches[0]


class Menu10BuilderPinParity(unittest.TestCase):
    def test_all_three_e06_owner_script_pins_match_current_git_bytes(self):
        builder = BUILDER.read_text("utf-8-sig")
        for label, filename in OWNER_FILES:
            with self.subTest(label=label):
                path = MENU / filename
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(
                    canonical_git_blob(path.read_bytes()),
                    expected_pin(builder, label),
                    "MENU10_STALE_" + label + "_BLOB_PIN_HOLD",
                )

    def test_approved_menu_is_required_for_nsis_manifest_not_only_source(self):
        builder = BUILDER.read_text("utf-8-sig")
        workflow = WORKFLOW.read_text("utf-8-sig")
        self.assertIn("-IncludeMega814", workflow)
        for token in (
            "MEGAB_APPROVED_MENU10_SOURCE_QA_HOLD",
            "MEGAB_OWNER_R11_MENU10_STAGE_HOLD",
            "MEGAB_APPROVED_MENU10_PUBLISHED_PAYLOAD_HOLD",
            "MEGAB_OWNER_MENU10_CANONICAL_IMAGE_SHA_HOLD",
            "MEGAB_MENU10_NSIS_MANIFEST_ASSET_MISSING",
        ):
            with self.subTest(token=token):
                self.assertIn(token, builder)
        for asset in (
            "Assets/mega814/menu10.png",
            "Assets/mega814/mega814.mjs",
            "Assets/mega814/mega814.css",
            "Assets/mega814/menu-v2-193.json",
            "Assets/mega814/MEGA814_RECEIPT.json",
        ):
            with self.subTest(asset=asset):
                self.assertIn(asset, builder)

    def test_stale_byte_change_cannot_preserve_pin(self):
        path = MENU / "stage_original_r11.py"
        original = path.read_bytes()
        self.assertNotEqual(
            canonical_git_blob(original),
            canonical_git_blob(original + b"\n# drift\n"),
        )
        builder = BUILDER.read_text("utf-8-sig")
        old = expected_pin(builder, "menuStage")
        mutated_builder = builder.replace(old, "0" * 40, 1)
        self.assertEqual(expected_pin(mutated_builder, "menuStage"), "0" * 40)
        self.assertNotEqual(canonical_git_blob(original), "0" * 40)


if __name__ == "__main__":
    unittest.main()
