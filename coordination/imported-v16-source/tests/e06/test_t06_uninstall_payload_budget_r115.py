"""R115 source-level budget regression; no fabricated Windows/E07 acceptance."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[2]/"coordination/e06/t06_samevm_installed_smoke.py"

def load_original():
    spec=importlib.util.spec_from_file_location("nox_t06_uninstall_budget_r115",PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("T06_ORIGINAL_SMOKE_NOT_FOUND")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class OriginalNsisBudgetR115(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner=load_original()

    def test_small_manifest_preserves_30s_minimum(self):
        self.assertEqual(self.owner.original_nsis_uninstall_budget(1),30.0)

    def test_real_1004_owned_entries_get_finite_extra_time(self):
        self.assertAlmostEqual(self.owner.original_nsis_uninstall_budget(1004),100.32)

    def test_large_manifest_is_hard_capped(self):
        self.assertEqual(self.owner.original_nsis_uninstall_budget(50000),180.0)

    def test_untrusted_manifest_count_fails_closed(self):
        for value in (None,True,0,-1,50001,2.0,"1004"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError,"T06_NSIS_UNINSTALL_COUNT_UNTRUSTED"):
                    self.owner.original_nsis_uninstall_budget(value)

    def test_real_uninstall_verifier_still_called_after_quiescence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"NOX HELION"
            root.mkdir()
            file=root/"Accessibility.dll"
            file.write_bytes(b"original")
            with patch.object(self.owner,"verify_original_uninstall",side_effect=RuntimeError("T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS")) as verify:
                with self.assertRaisesRegex(RuntimeError,"T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS"):
                    self.owner.await_original_uninstall(root,(file,),timeout_seconds=.03,poll_seconds=.01)
                verify.assert_called_once_with(root,(file,))
            self.assertEqual(file.read_bytes(),b"original")

    def test_explicit_timeout_remains_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"NOX HELION"
            root.mkdir()
            with self.assertRaisesRegex(RuntimeError,"T06_NSIS_UNINSTALL_WAIT_BAD_INPUT"):
                self.owner.await_original_uninstall(root,(root/"owned.dll",),
                                                    timeout_seconds=181.0,poll_seconds=.01)

if __name__=="__main__":
    unittest.main()
