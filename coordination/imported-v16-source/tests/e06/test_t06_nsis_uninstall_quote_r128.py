"""R128 original NSIS uninstall quote staged from reviewed C09, source-only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location("r128",ROOT/"coordination/e06/t06_package_original_onehost.py")
OWNER=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(OWNER)
REVIEWED=ROOT/"stage/proposals/P01/C09/Installer/NOX-HELION-Setup.nsi"

class R128(unittest.TestCase):
    def with_stage(self,body):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        p=Path(t.name)/"Installer"/"NOX-HELION-Setup.nsi"
        p.parent.mkdir()
        p.write_bytes(("before\r\n"+body+"\r\nafter").encode())
        return p
    def test_bad_exact_original_fixed_no_other_changes(self):
        p=self.with_stage(OWNER.C07_UNINSTALL_LINE)
        result=OWNER.stage_c07_uninstall_quote(p,REVIEWED)
        self.assertTrue(result["changed"])
        self.assertFalse(result["release_accepted"])
        self.assertEqual(p.read_bytes(),("before\r\n"+OWNER.C09_UNINSTALL_LINE+"\r\nafter").encode())
    def test_approved_no_rewrite(self):
        p=self.with_stage(OWNER.C09_UNINSTALL_LINE)
        before=p.read_bytes()
        self.assertFalse(OWNER.stage_c07_uninstall_quote(p,REVIEWED)["changed"])
        self.assertEqual(before,p.read_bytes())
    def test_unknown_and_duplicate_fail_closed(self):
        for source in (OWNER.C07_UNINSTALL_LINE.replace("Uninstall.exe","calc.exe"),
                       OWNER.C07_UNINSTALL_LINE+"\n"+OWNER.C07_UNINSTALL_LINE):
            p=self.with_stage(source)
            before=p.read_bytes()
            with self.assertRaises(RuntimeError):
                OWNER.stage_c07_uninstall_quote(p,REVIEWED)
            self.assertEqual(p.read_bytes(),before)

if __name__=="__main__":unittest.main()
