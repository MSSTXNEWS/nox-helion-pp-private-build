"""Verify exact latest D02 E06 identity without upgrading historical E07."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/"coordination/e07/independent_setup_e07.py"
sys.path.insert(0,str(TARGET.parent))
spec=importlib.util.spec_from_file_location("nox_e07_current_pins",TARGET)
e07=importlib.util.module_from_spec(spec)
spec.loader.exec_module(e07)


class CurrentD02Identity(unittest.TestCase):
    def test_physical_e06_receipt_identity_pinned(self):
        self.assertEqual(e07.CURRENT_D02_SOURCE_SHA,
                         "5f44122bf01328fb2fbefbba0a40946d0be0df6e")
        self.assertEqual(e07.CURRENT_D02_SETUP_SHA,
                         "c8a190224e94d529df63827e832f1e8628ec0c034c400cedbaa2846116e28b2a")
        self.assertEqual(e07.CURRENT_D02_SETUP_SIZE,169682978)
        self.assertEqual(e07.CURRENT_D02_BUILD_ID,"NOX-V16-9a812040d0b6abed4fa1c953")
        self.assertEqual(e07.CURRENT_D02_OWNED_COUNT,1013)

    def test_same_vm_receipts_do_not_count_as_independent_e07(self):
        actual={"install":{"code":0},"verify":{"code":0},"update":{"code":0},
                "rollback":{"code":0},"uninstall":{"code":0},
                "uninstall_owned_files_checked":1013}
        self.assertTrue(e07.samevm_lifecycle_verified(actual,expected_owned_files=1013))
        actual["uninstall_owned_files_checked"]=1012
        self.assertFalse(e07.samevm_lifecycle_verified(actual,expected_owned_files=1013))

    def test_release_still_requires_current_physical_visual_and_functions(self):
        source=TARGET.read_text(encoding="utf-8")
        self.assertIn('if args.artifact_kind == "d02-current":',source)
        self.assertIn('if candidate == "d02-current":',source)
        self.assertIn('visual.get("reduced_motion") == "PASS"',source)
        self.assertIn('item.get("permissions_verified") == "PASS"',source)
        self.assertIn('item.get("function_verified") == "PASS"',source)


if __name__=="__main__":
    unittest.main()
