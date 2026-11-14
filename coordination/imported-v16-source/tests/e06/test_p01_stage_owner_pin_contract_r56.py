"""R56: original P01 MENU10 and eight UI files must match pinned checkout bytes."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / "integrations/wow200/stage_wow200.py"
spec = importlib.util.spec_from_file_location("nox_wow200_stage_r56", source)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class OriginalMenuStageR56(unittest.TestCase):
    def test_all_nine_native_p01_sources_are_git_blob_pinned(self):
        self.assertEqual(len(owner.P01_OWNER_BLOBS), 9)
        with tempfile.TemporaryDirectory() as temp:
            plans, content = owner.p01_owner_stage_plan(ROOT, Path(temp))
            self.assertEqual(len(plans), 9)
            for path, expected in owner.P01_OWNER_BLOBS.items():
                self.assertEqual(owner.gitsha(content[ROOT / path]), expected, path)

    def test_eight_menu_v2_dependencies_have_exact_sha256(self):
        self.assertEqual(len(owner.MENU_V2_SHA256), 8)
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(len(owner.menu_stage_plan(ROOT, Path(temp))), 8)
            for path, expected in owner.MENU_V2_SHA256.items():
                actual = hashlib.sha256(owner.canonical_menu_bytes(ROOT / path)).hexdigest()
                self.assertEqual(actual, expected, path)

    def test_tampering_one_original_route_blocks_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp)
            for path in owner.P01_OWNER_BLOBS:
                target = checkout / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / path).read_bytes())
            target = checkout / "proposals/P01/WOW-MAX10/route-dispatch.mjs"
            target.write_bytes(target.read_bytes() + b"\\n// tampered\\n")
            with self.assertRaisesRegex(ValueError, "P01_MENU10_SOURCE_BLOB_HOLD"):
                owner.p01_owner_stage_plan(checkout, checkout / "stage")


if __name__ == "__main__":
    unittest.main()
