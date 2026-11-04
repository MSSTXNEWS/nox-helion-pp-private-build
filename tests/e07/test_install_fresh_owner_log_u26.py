"""Physical E07 original installer log provenance; source test, not release."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"coordination/e07/probe_final_same_setup.py"
sys.path.insert(0,str(PATH.parent))
spec=importlib.util.spec_from_file_location("nox_e07_fresh_install_owner_u26",PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

STAMP=b"[2026-11-05T01:30:22.1023956+01:00] "
class InstallOwnerEvidence(unittest.TestCase):
    def test_real_logged_start_and_end_not_untrusted_stdout(self):
        data=STAMP+b"ACTION_START install\r\n"+STAMP+b"ACTION_END install exit=0 stdout=Installed NOX source locally\r\n"
        result=module.classify_fresh_original_install_log(data)
        self.assertEqual(result,{"started":True,"owner_exit_code":0,"owner_exception":False})
        no=module.classify_fresh_original_install_log(b"stdout: ACTION_END install exit=0\n")
        self.assertIsNone(no["owner_exit_code"])
        fail=module.classify_fresh_original_install_log(STAMP+b"ACTION_START install\n"+
            STAMP+b"ACTION_END install exit=1 stderr=source file missing\n")
        self.assertEqual(fail["owner_exit_code"],1)
        self.assertTrue(fail["started"])
        self.assertTrue(module.classify_fresh_original_install_log(
            STAMP+b"ACTION_FAIL install System.InvalidOperationException\n")["owner_exception"])

    def test_multiple_forged_or_oversized_receipts_fail_closed(self):
        dup=STAMP+b"ACTION_END install exit=0\n"+STAMP+b"ACTION_END install exit=0\n"
        with self.assertRaisesRegex(module.e07.Hold,"E07_FINAL_INSTALL_DUPLICATE_OWNER_LOG_HOLD"):
            module.classify_fresh_original_install_log(dup)
        with self.assertRaisesRegex(module.e07.Hold,"E07_FINAL_INSTALL_LOG_BOUNDS_HOLD"):
            module.classify_fresh_original_install_log(b"x"*200001)
        with self.assertRaisesRegex(module.e07.Hold,"E07_FINAL_INSTALL_LOG_BOUNDS_HOLD"):
            module.classify_fresh_original_install_log("not bytes")

    def test_no_synthetic_install_or_model_permissions_pass(self):
        source=PATH.read_text(encoding="utf-8")
        self.assertIn("classify_fresh_original_install_log(handle.read(200000))",source)
        self.assertIn("E07_FINAL_INSTALL_OWNER_ACTION_NOT_STARTED_HOLD",source)
        self.assertIn("E07_FINAL_INSTALL_OWNER_NONZERO_EXIT_HOLD",source)
        self.assertIn('\"permissions_verified\":\"NOT_TESTED\"',source)
        self.assertNotIn('\"permissions_verified\":\"PASS\"',source)

if __name__=="__main__":
    unittest.main()
